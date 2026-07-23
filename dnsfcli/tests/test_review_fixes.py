"""Regression tests for the remaining internal-review findings:
  - --each-org must paginate the organization list (not just page 1);
  - the audit log must rotate by size, not wipe itself at 50 lines.
"""

from __future__ import annotations

import inspect
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dnsfcli import audit as audit_mod
from dnsfcli import cli as cli_mod


# ---------------------------------------------------------------------------
# Finding 3 — --each-org pagination
# ---------------------------------------------------------------------------

class _PaginatedClient:
    """Fake client returning `pages` pages via the JSON:API meta contract."""

    def __init__(self, pages: list[list[dict]]) -> None:
        self._pages = pages

    def request(self, method, path, params=None, json=None):
        page = (params or {}).get("page[number]", 1)
        items = self._pages[page - 1] if 1 <= page <= len(self._pages) else []
        return {"data": items, "meta": {"total_pages": len(self._pages)}}

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_fetch_all_pages_aggregates_every_page():
    """The helper --each-org now uses must return items from ALL pages."""
    pages = [
        [{"id": "1"}, {"id": "2"}],
        [{"id": "3"}, {"id": "4"}],
        [{"id": "5"}],
    ]
    client = _PaginatedClient(pages)
    _last, items = cli_mod._fetch_all_pages(
        client, "GET", "/v1/organizations", None, None, show_progress=False,
    )
    assert [i["id"] for i in items] == ["1", "2", "3", "4", "5"]


# NOTE: --each-org multi-page listing is now proven behaviorally (a page-2 org
# appears in the fan-out) in tests/test_pagination_lookups.py, replacing the
# brittle inspect.getsource check that survived a "call it but use page 1" mutation.


# ---------------------------------------------------------------------------
# Finding 5 — size-based audit rotation
# ---------------------------------------------------------------------------

def test_audit_rotates_by_size_and_keeps_history(tmp_path, monkeypatch):
    log = tmp_path / "audit.jsonl"
    monkeypatch.setattr(audit_mod, "_LOG_DIR", tmp_path)
    monkeypatch.setattr(audit_mod, "_LOG_FILE", log)
    # Small cap so a few hundred events trigger several rotations.
    monkeypatch.setattr(audit_mod, "_MAX_BYTES", 15_000)
    monkeypatch.setattr(audit_mod, "_BACKUP_COUNT", 3)

    total = 300
    for i in range(total):
        audit_mod.log_event(
            "networks", "create", "POST", f"/v1/networks/{i}", 201, "802315",
        )

    # A rotation must have happened (the old 50-line cap would have discarded
    # everything but the last ~100 events).
    assert (tmp_path / "audit.jsonl.1").exists(), "no rotation occurred"

    # The active file stays bounded near the size cap, not unbounded.
    assert log.stat().st_size <= audit_mod._MAX_BYTES + 500

    # Crucially: far more than the old ~100-event ceiling survives, and every
    # event written within the backup capacity is still readable.
    events = audit_mod.read_events()
    assert len(events) == total, f"lost events across rotation: {len(events)}/{total}"

    # And clearing removes the active file plus every backup.
    audit_mod.clear_log()
    assert not log.exists()
    assert not (tmp_path / "audit.jsonl.1").exists()


def test_single_bulk_run_does_not_erase_its_own_trail(tmp_path, monkeypatch):
    """The concrete failure from review: a bulk import must not wipe the record
    of its own earliest rows mid-run."""
    log = tmp_path / "audit.jsonl"
    monkeypatch.setattr(audit_mod, "_LOG_DIR", tmp_path)
    monkeypatch.setattr(audit_mod, "_LOG_FILE", log)
    monkeypatch.setattr(audit_mod, "_MAX_BYTES", 15_000)
    monkeypatch.setattr(audit_mod, "_BACKUP_COUNT", 3)

    for i in range(150):
        audit_mod.log_event("networks", "create", "POST", f"/v1/networks/{i}", 201, "1")

    events = audit_mod.read_events()
    paths = {e["path"] for e in events}
    # The very first row of the run must still be on record.
    assert "/v1/networks/0" in paths
    assert "/v1/networks/149" in paths
