"""Append-only JSONL audit log for write API operations, plus a full history log."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_LOG_DIR   = Path.home() / ".local" / "share" / "dnsfcli"
_LOG_FILE  = _LOG_DIR / "audit.jsonl"
_LOG_BAK   = _LOG_DIR / "audit.jsonl.1"
_ROTATE_AT = 50  # lines before rotating to .1

_HIST_FILE     = _LOG_DIR / "history.jsonl"
_HIST_BAK      = _LOG_DIR / "history.jsonl.1"
_HIST_ROTATE_AT = 1_000

_WRITE_METHODS = frozenset({"POST", "PATCH", "PUT", "DELETE"})

# Flags whose next token is a secret that must never be persisted to disk.
# --header can carry an Authorization value; --proxy URLs may embed user:pass.
_SECRET_FLAGS = frozenset({"--api-key", "-k", "--header", "-H", "--proxy"})


def _scrub_argv(argv: list[str]) -> list[str]:
    """Return a copy of *argv* with secret flag values replaced by '***'."""
    out: list[str] = []
    skip_next = False
    for token in argv:
        if skip_next:
            out.append("***")
            skip_next = False
            continue
        if token in _SECRET_FLAGS:
            out.append(token)
            skip_next = True
        elif any(token.startswith(f"{f}=") for f in _SECRET_FLAGS):
            flag, _ = token.split("=", 1)
            out.append(f"{flag}=***")
        else:
            out.append(token)
    return out


def _ensure_private_dir() -> None:
    """Create the log directory owner-only; tighten it if it already exists."""
    _LOG_DIR.mkdir(parents=True, exist_ok=True)
    os.chmod(_LOG_DIR, 0o700)


def _append_private(path: Path, line: str) -> None:
    """Append *line* to *path*, creating the file 0600 and fixing looser perms."""
    fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
    with os.fdopen(fd, "a", encoding="utf-8") as fh:
        os.chmod(path, 0o600)  # tighten files created before this hardening
        fh.write(line)


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
    """Append one write-operation event; rotate the log file when it reaches _ROTATE_AT lines."""
    if method not in _WRITE_METHODS:
        return

    try:
        _ensure_private_dir()

        if _LOG_FILE.exists():
            with _LOG_FILE.open(encoding="utf-8") as fh:
                line_count = sum(1 for _ in fh)
            if line_count >= _ROTATE_AT:
                _LOG_FILE.rename(_LOG_BAK)  # overwrites existing .1 backup

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
    events: list[dict[str, Any]] = []
    for log_file in (_LOG_FILE, _LOG_BAK):
        if not log_file.exists():
            continue
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

        if _HIST_FILE.exists():
            with _HIST_FILE.open(encoding="utf-8") as fh:
                line_count = sum(1 for _ in fh)
            if line_count >= _HIST_ROTATE_AT:
                _HIST_FILE.rename(_HIST_BAK)

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
    events: list[dict[str, Any]] = []
    for log_file in (_HIST_FILE, _HIST_BAK):
        if not log_file.exists():
            continue
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


def history_path() -> Path:
    return _HIST_FILE


def log_path() -> Path:
    return _LOG_FILE


def clear_log() -> None:
    """Delete the audit log and its rotation backup."""
    for f in (_LOG_FILE, _LOG_BAK):
        try:
            f.unlink()
        except FileNotFoundError:
            pass


def clear_history() -> None:
    """Delete the history log and its rotation backup."""
    for f in (_HIST_FILE, _HIST_BAK):
        try:
            f.unlink()
        except FileNotFoundError:
            pass
