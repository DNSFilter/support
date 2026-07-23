"""Regression tests for the broader audit pass:
  - lookup paths (--org-name / --merge-key / --join) paginate;
  - _fetch_all_pages warns (once) on a bad --paginate-until expr and on
    --max-pages truncation;
  - keychain write failures raise a clean KeychainError, not a traceback;
  - --fail-on-pattern with a bad expression fails instead of exiting 0.
"""

from __future__ import annotations

import inspect
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dnsfcli import cli as cli_mod


# ---------------------------------------------------------------------------
# Pagination lookups (P1/P2/P3) — source guards + mechanism
# ---------------------------------------------------------------------------

class _Paged:
    """Fake client serving `pages` pages via the JSON:API meta contract."""

    def __init__(self, pages):
        self._pages = pages
        self.pages_fetched = 0

    def request(self, method, path, params=None, json=None):
        page = (params or {}).get("page[number]", 1)
        self.pages_fetched = max(self.pages_fetched, page)
        items = self._pages[page - 1] if 1 <= page <= len(self._pages) else []
        return {"data": items, "meta": {"total_pages": len(self._pages)}}

    def get(self, path, params=None):
        return self.request("GET", path, params=params)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


# NOTE: --org-name / --merge-key / --join pagination is now proven behaviorally
# (matching record on page 2) in tests/test_pagination_lookups.py, replacing the
# brittle inspect.getsource "_fetch_all_pages appears near the call site" checks.


def test_fetch_all_pages_walks_every_page():
    client = _Paged([[{"id": "1"}], [{"id": "2"}], [{"id": "3"}]])
    _last, items = cli_mod._fetch_all_pages(
        client, "GET", "/v1/policies", None, None, show_progress=False,
    )
    assert [i["id"] for i in items] == ["1", "2", "3"]
    assert client.pages_fetched == 3


# ---------------------------------------------------------------------------
# --max-pages truncation warning (P4)
# ---------------------------------------------------------------------------

def test_max_pages_truncation_warns(capsys):
    client = _Paged([[{"id": str(i)}] for i in range(5)])  # 5 pages available
    _last, items = cli_mod._fetch_all_pages(
        client, "GET", "/v1/policies", None, None,
        max_pages=2, show_progress=False,
    )
    assert len(items) == 2                     # only 2 of 5 pages fetched
    err = capsys.readouterr().err
    assert "max-pages" in err and "partial" in err, "no truncation warning emitted"


def test_no_warning_when_not_truncated(capsys):
    client = _Paged([[{"id": "1"}], [{"id": "2"}]])  # exactly 2 pages
    cli_mod._fetch_all_pages(
        client, "GET", "/v1/policies", None, None,
        max_pages=5, show_progress=False,
    )
    err = capsys.readouterr().err
    assert "max-pages" not in err, "spurious truncation warning"


# ---------------------------------------------------------------------------
# Keychain error handling (R1)
# ---------------------------------------------------------------------------

def test_keychain_write_failure_raises_clean_error(monkeypatch):
    import keyring.errors
    from dnsfcli import auth as auth_mod

    def _boom(*a, **k):
        raise keyring.errors.KeyringError("no backend available")

    monkeypatch.setattr(auth_mod.keyring, "set_password", _boom)
    with pytest.raises(auth_mod.KeychainError) as excinfo:
        auth_mod.store_api_key("some-key")
    # User-facing guidance, not a raw backend traceback.
    assert "keychain" in str(excinfo.value).lower()
    assert "DNSF_API_KEY" in str(excinfo.value)
