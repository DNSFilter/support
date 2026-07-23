"""Simple file-based response cache for GET requests.

Cache location (first found wins):
  $XDG_CACHE_HOME/dnsfcli/   or   ~/.cache/dnsfcli/

Each entry is a JSON envelope ``{"ts": float, "payload": ...}`` stored under
a filename derived from a SHA-256 hash of the (endpoint, function, path,
query-params) tuple.  Stale entries are left on disk and silently ignored;
they are never removed automatically (use ``cache_clear()`` for that).

All public functions are best-effort: any IO error is swallowed so a broken
cache never interrupts normal CLI operation.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from pathlib import Path
from typing import Any


def _dir() -> Path:
    xdg = os.environ.get("XDG_CACHE_HOME")
    base = Path(xdg) if xdg else Path.home() / ".cache"
    return base / "dnsfcli"


def make_key(
    endpoint: str,
    function: str,
    path: str,
    params: dict[str, Any] | None,
    cred_scope: str = "",
) -> str:
    """Build the cache filename stem for a GET response.

    *cred_scope* MUST encode the credential + host the response was fetched
    under (the caller passes an opaque hash of the resolved API key + base URL).
    Without it, a response cached under one key/account would be served to a
    later invocation using a *different* key hitting the same path — a
    cross-account data disclosure for endpoints scoped only by the API token.
    """
    payload = json.dumps(
        {"e": endpoint, "f": function, "p": path,
         "q": sorted((params or {}).items()), "c": cred_scope},
    ).encode()
    digest = hashlib.sha256(payload).hexdigest()[:20]
    return f"{endpoint}-{function}-{digest}"


def get(key: str, ttl: int) -> Any | None:
    """Return cached payload if it exists and is younger than *ttl* seconds, else None."""
    cache_file = _dir() / f"{key}.json"
    if not cache_file.exists():
        return None
    try:
        envelope = json.loads(cache_file.read_text(encoding="utf-8"))
        if time.time() - envelope.get("ts", 0) < ttl:
            return envelope["payload"]
    except Exception:
        pass
    return None


def put(key: str, payload: Any) -> None:
    """Write *payload* to the cache (best-effort; never raises).

    Cached responses contain real API data (user lists, policy contents),
    so the directory and files are owner-only (0700/0600) — the same
    hardening applied to the audit log.
    """
    try:
        d = _dir()
        d.mkdir(parents=True, exist_ok=True)
        os.chmod(d, 0o700)
        data = json.dumps({"ts": time.time(), "payload": payload}, default=str)
        target = d / f"{key}.json"
        # Write to a unique temp file then atomically rename into place, so a
        # concurrent reader (or another writer of the same key) never sees a
        # half-written entry. os.replace is atomic within a filesystem.
        tmp = d / f"{key}.{os.getpid()}.{threading.get_ident()}.tmp"
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            os.chmod(tmp, 0o600)
            fh.write(data)
        os.replace(tmp, target)
    except Exception:
        pass


def clear_all() -> None:
    """Delete every cached response file."""
    d = _dir()
    if d.exists():
        for f in d.glob("*.json"):
            try:
                f.unlink()
            except Exception:
                pass


def cache_dir() -> Path:
    return _dir()
