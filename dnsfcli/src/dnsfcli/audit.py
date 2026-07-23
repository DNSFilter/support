"""Append-only JSONL audit log for write API operations, plus a full history log."""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Serializes rotation across threads: log_event/log_history run on CSV batch
# and parallel-org worker threads, and the check-then-rename in
# _rotate_if_needed would otherwise race at the size boundary.
_rotate_lock = threading.Lock()
_write_lock = threading.Lock()   # serializes appends so concurrent lines don't interleave

_LOG_DIR   = Path.home() / ".local" / "share" / "dnsfcli"
_LOG_FILE  = _LOG_DIR / "audit.jsonl"

_HIST_FILE = _LOG_DIR / "history.jsonl"

# Rotate by size, not by line count. The old 50-line cap on the audit log
# meant a single bulk import overran its own trail mid-run and destroyed the
# record exactly when support needed it. Size-based rotation with several
# backups keeps a meaningful history (4 × 10 MB ≈ tens of thousands of events).
_MAX_BYTES    = 10 * 1024 * 1024   # rotate the active file once it reaches 10 MB
_BACKUP_COUNT = 3                  # keep .1 .. .3 alongside the active file

_WRITE_METHODS = frozenset({"POST", "PATCH", "PUT", "DELETE"})

import re

# Flags whose next token is a secret that must never be persisted to disk.
# --header can carry an Authorization value; --proxy URLs may embed user:pass.
_SECRET_FLAGS = frozenset({"--api-key", "-k", "--header", "-H", "--proxy"})

# Value-carrying flags whose payload can contain arbitrary secrets and so is
# redacted wholesale (dynamic API bodies, e.g. --body-json '{"client_secret":…}').
_REDACT_VALUE_FLAGS = frozenset({"--body-json", "--stdin-json", "--from-json"})

# Any --flag whose NAME matches this is treated as a secret. This catches the
# dynamic API params that become CLI flags — --client-secret, --payment-token,
# --new-password — plus anything similar added to the endpoint registry later,
# without the scrubber needing to know each one.
_SECRET_NAME_RE = re.compile(r"(secret|password|passwd|token|credential|api[-_]?key)", re.I)


def _flag_name(token: str) -> str | None:
    """The bare name of a --flag / --flag=value token, else None."""
    if token.startswith("--"):
        return token[2:].split("=", 1)[0]
    return None


def _is_secret_flag(token: str) -> bool:
    if token in _SECRET_FLAGS:
        return True
    name = _flag_name(token)
    return bool(name and _SECRET_NAME_RE.search(name))


def _scrub_argv(argv: list[str]) -> list[str]:
    """Return a copy of *argv* with secret values replaced by '***'.

    Handles: explicit secret flags; any --flag whose name looks like a secret
    (covers dynamic API params like --client-secret / --new-password);
    --flag=value forms; wholesale-redacted body flags; and --set name=value
    where the name looks like a secret.
    """
    out: list[str] = []
    skip_next = False
    prev = ""
    for token in argv:
        if skip_next:
            out.append("***")
            skip_next = False
            prev = token
            continue
        # --flag=value forms
        if token.startswith("--") and "=" in token:
            flag, _ = token.split("=", 1)
            if _is_secret_flag(flag) or flag in _REDACT_VALUE_FLAGS:
                out.append(f"{flag}=***")
                prev = token
                continue
        # --set name=value (or -s name=value): scrub the value if name is secret
        if prev in ("--set", "-s", "--add-field") and "=" in token:
            _n, _v = token.split("=", 1)
            if _SECRET_NAME_RE.search(_n):
                out.append(f"{_n}=***")
                prev = token
                continue
        # secret flag or wholesale-redacted flag whose value is the NEXT token
        if _is_secret_flag(token) or token in _REDACT_VALUE_FLAGS:
            out.append(token)
            skip_next = True
            prev = token
            continue
        out.append(token)
        prev = token
    return out


# Body flags that carry a secret-bearing VALUE token in argv. --stdin-json is
# excluded: it is a boolean flag whose payload comes from stdin, not argv, so
# there is no value token to drop.
_VALUE_SECRET_BODY_FLAGS = frozenset({"--body-json", "--from-json"})


def mask_secret_keys(obj: Any) -> Any:
    """Return a copy of *obj* with values of secret-named keys replaced by '***',
    recursing into nested dicts AND lists. Used to redact request bodies / query
    params before they are printed (--verbose) or written to a diagnostic report.
    """
    if isinstance(obj, list):
        return [mask_secret_keys(x) for x in obj]
    if not isinstance(obj, dict):
        return obj
    out: dict[Any, Any] = {}
    for k, v in obj.items():
        if isinstance(k, str) and _SECRET_NAME_RE.search(k):
            out[k] = "***"          # mask regardless of value type (scalar/list/dict)
        else:
            out[k] = mask_secret_keys(v)   # recurse dicts and lists
    return out


def drop_secret_tokens(argv: list[str]) -> tuple[list[str], bool]:
    """Return (kept_tokens, dropped_any) with secret flag+value pairs REMOVED.

    Used for alias persistence: unlike ``_scrub_argv`` (which masks to '***' for
    the history log), an alias must *drop* the secret entirely — a stored
    ``--api-key ***`` would be a broken command, and the credential should come
    from the keychain/env when the alias is re-run. Detection is shared with
    ``_scrub_argv`` (explicit secret flags, the secret-name regex for dynamic
    params like --client-secret/--new-password, secret body flags, and
    --set/--add-field with a secret NAME).
    """
    out: list[str] = []
    dropped = False
    i, n = 0, len(argv)
    while i < n:
        tok = argv[i]
        # --flag=value form
        if tok.startswith("--") and "=" in tok:
            flag = tok.split("=", 1)[0]
            if _is_secret_flag(flag) or flag in _VALUE_SECRET_BODY_FLAGS:
                dropped = True
                i += 1
                continue
        # --set / --add-field NAME=VALUE where NAME looks secret (drop both tokens)
        if tok in ("--set", "-s", "--add-field") and i + 1 < n and "=" in argv[i + 1] \
                and _SECRET_NAME_RE.search(argv[i + 1].split("=", 1)[0]):
            dropped = True
            i += 2
            continue
        # secret flag consuming its following value token. Consume it
        # UNCONDITIONALLY (mirroring _scrub_argv): a secret value can itself
        # start with '-' (e.g. --new-password -p@ss), and leaving it behind
        # would persist the secret into the alias. These flags always take a
        # value, so a real (click-accepted) argv has one to drop.
        if _is_secret_flag(tok) or tok in _VALUE_SECRET_BODY_FLAGS:
            dropped = True
            i += 2 if i + 1 < n else 1
            continue
        out.append(tok)
        i += 1
    return out, dropped


def _ensure_private_dir() -> None:
    """Create the log directory owner-only; tighten it if it already exists."""
    _LOG_DIR.mkdir(parents=True, exist_ok=True)
    os.chmod(_LOG_DIR, 0o700)


def _append_private(path: Path, line: str) -> None:
    """Append *line* to *path*, creating the file 0600 and fixing looser perms.

    Serialized with _write_lock: O_APPEND is atomic per write() syscall, but a
    long JSON line (e.g. a big error body) can split across syscalls and
    interleave with another thread's line under --concurrency / --parallel-orgs.
    """
    data = line.encode("utf-8")
    with _write_lock:
        fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
        try:
            os.fchmod(fd, 0o600)  # tighten files created before this hardening
            os.write(fd, data)    # single syscall → no interleaving
        finally:
            os.close(fd)


def _backups(base: Path) -> list[Path]:
    """The rotation backup paths for *base*, newest (.1) first."""
    return [base.with_name(f"{base.name}.{i}") for i in range(1, _BACKUP_COUNT + 1)]


def _rotate_if_needed(base: Path) -> None:
    """Roll *base* to .1 (shifting .1→.2, …) once it reaches _MAX_BYTES.

    Locked so concurrent writers can't both observe the threshold and run the
    rename chain at once (which would drop or interleave backups).
    """
    with _rotate_lock:
        try:
            if not base.exists() or base.stat().st_size < _MAX_BYTES:
                return
        except OSError:
            return
        backups = _backups(base)
        # Drop the oldest, then shift each backup down one slot, then base → .1.
        for older, newer in zip(reversed(backups[:-1]), reversed(backups[1:])):
            # older is .N, newer is .N+1 — move .N into .N+1's slot.
            if older.exists():
                older.replace(newer)
        base.replace(backups[0])


def _log_files(base: Path) -> list[Path]:
    """Active file plus every existing backup — the full readable set."""
    return [p for p in (base, *_backups(base)) if p.exists()]


def _read_log(
    base: Path,
    last: int | None,
    since: str | None,
    endpoint_filter: str | None,
) -> list[dict[str, Any]]:
    """Return parsed events from *base* and its backups, newest first."""
    events: list[dict[str, Any]] = []
    for log_file in _log_files(base):
        try:
            with log_file.open(encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        events.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
        except OSError:
            continue
    events.sort(key=lambda e: e.get("ts", ""), reverse=True)
    if endpoint_filter:
        events = [e for e in events if e.get("endpoint") == endpoint_filter]
    if since:
        events = [e for e in events if e.get("ts", "") >= since]
    if last is not None:
        events = events[:last]
    return events


def log_event(
    endpoint: str,
    function: str,
    method: str,
    path: str,
    status: int,
    org_id: str | None,
    *,
    error: str | None = None,
) -> None:
    """Append one write-operation event; rotate the log file by size."""
    if method not in _WRITE_METHODS:
        return

    try:
        _ensure_private_dir()
        _rotate_if_needed(_LOG_FILE)

        entry: dict[str, Any] = {
            "ts":       datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "org_id":   org_id,
            "endpoint": endpoint,
            "function": function,
            "method":   method,
            "path":     path,
            "status":   status,
        }
        if error:
            entry["error"] = error

        _append_private(_LOG_FILE, json.dumps(entry) + "\n")
    except OSError:
        pass  # audit writes are best-effort — never crash the main operation


def read_events(
    last: int | None = None,
    since: str | None = None,
    endpoint_filter: str | None = None,
) -> list[dict[str, Any]]:
    """Return logged events, newest first, from current and rotated log files."""
    return _read_log(_LOG_FILE, last, since, endpoint_filter)


def log_history(
    endpoint: str,
    function: str,
    method: str,
    path: str,
    status: int,
    org_id: str | None,
    *,
    error: str | None = None,
    argv: list[str] | None = None,
) -> None:
    """Append every API call (reads and writes) to the history log."""
    try:
        _ensure_private_dir()
        _rotate_if_needed(_HIST_FILE)

        entry: dict[str, Any] = {
            "ts":       datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "org_id":   org_id,
            "endpoint": endpoint,
            "function": function,
            "method":   method,
            "path":     path,
            "status":   status,
        }
        if error:
            entry["error"] = error
        if argv is not None:
            entry["argv"] = _scrub_argv(argv)

        _append_private(_HIST_FILE, json.dumps(entry) + "\n")
    except OSError:
        pass


def read_history(
    last: int | None = None,
    since: str | None = None,
    endpoint_filter: str | None = None,
) -> list[dict[str, Any]]:
    """Return history events (all methods), newest first."""
    return _read_log(_HIST_FILE, last, since, endpoint_filter)


def history_path() -> Path:
    return _HIST_FILE


def log_path() -> Path:
    return _LOG_FILE


def clear_log() -> None:
    """Delete the audit log and all its rotation backups."""
    for f in (_LOG_FILE, *_backups(_LOG_FILE)):
        try:
            f.unlink()
        except FileNotFoundError:
            pass


def clear_history() -> None:
    """Delete the history log and all its rotation backups."""
    for f in (_HIST_FILE, *_backups(_HIST_FILE)):
        try:
            f.unlink()
        except FileNotFoundError:
            pass
