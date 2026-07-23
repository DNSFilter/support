"""Regression tests for the second internal-review batch:
  - Retry-After accepts an HTTP-date without crashing;
  - cache files are written 0600 in a 0700 dir;
  - the stdin CSV temp file is deleted after use;
  - --errors-to-csv is streamed (survives an interrupt mid-batch).
"""

from __future__ import annotations

import os
import stat
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dnsfcli.client import _RETRY_AFTER_MAX, _parse_retry_after


# ---------------------------------------------------------------------------
# Finding 4 — Retry-After parsing
# ---------------------------------------------------------------------------

class TestRetryAfter:
    def test_integer_seconds(self):
        assert _parse_retry_after("30") == 30

    def test_http_date_does_not_crash(self):
        # The form that used to raise ValueError under bare int().
        val = _parse_retry_after("Wed, 21 Oct 2099 07:28:00 GMT")
        assert isinstance(val, int)
        assert 0 <= val <= _RETRY_AFTER_MAX

    def test_past_http_date_clamps_to_zero(self):
        assert _parse_retry_after("Wed, 21 Oct 2015 07:28:00 GMT") == 0

    def test_garbage_falls_back_to_default(self):
        assert _parse_retry_after("not-a-date", default=42) == 42

    def test_missing_header_uses_default(self):
        assert _parse_retry_after(None, default=60) == 60

    def test_absurd_value_is_capped(self):
        assert _parse_retry_after("999999") == _RETRY_AFTER_MAX


# ---------------------------------------------------------------------------
# Finding 2 — cache file permissions
# ---------------------------------------------------------------------------

def test_cache_files_are_owner_only(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    from dnsfcli import cache as cache_mod

    cache_mod.put("some-key", {"secret": "policy contents"})
    d = cache_mod.cache_dir()
    cache_file = d / "some-key.json"
    assert cache_file.exists()

    file_mode = stat.S_IMODE(cache_file.stat().st_mode)
    dir_mode = stat.S_IMODE(d.stat().st_mode)
    assert file_mode == 0o600, f"cache file is {oct(file_mode)}, expected 0600"
    assert dir_mode == 0o700, f"cache dir is {oct(dir_mode)}, expected 0700"


# ---------------------------------------------------------------------------
# Finding 3 — stdin temp file cleanup
# ---------------------------------------------------------------------------

def test_stdin_temp_file_is_deleted(monkeypatch):
    import io
    from dnsfcli.csv_io import read_csv_input
    from dnsfcli.endpoints import REGISTRY

    op = REGISTRY["block-pages"].operations["create"]
    monkeypatch.setattr("sys.stdin", io.StringIO("name\nMy Block Page\n"))

    created: list[str] = []
    real_ntf = __import__("tempfile").NamedTemporaryFile

    def _tracking_ntf(*a, **k):
        fh = real_ntf(*a, **k)
        created.append(fh.name)
        return fh

    monkeypatch.setattr("tempfile.NamedTemporaryFile", _tracking_ntf)

    rows = read_csv_input("-", op, {})
    assert rows[0]["name"] == "My Block Page"
    assert created, "no temp file was created for stdin"
    for name in created:
        assert not os.path.exists(name), f"stdin temp file leaked: {name}"


# ---------------------------------------------------------------------------
# Finding 1 — --errors-to-csv is streamed (survives an interrupt)
# ---------------------------------------------------------------------------

def test_errors_csv_is_written_before_interrupt(tmp_path):
    """Rows that failed before a Ctrl-C must already be on disk — the whole
    point of the checkpoint. The old end-of-run write left nothing."""
    import csv as _csv

    from dnsfcli import batch as batch_mod
    from dnsfcli import cli as cli_mod
    from dnsfcli.client import APIError
    from dnsfcli.endpoints import REGISTRY

    op = REGISTRY["block-pages"].operations["create"]
    errors_path = str(tmp_path / "failed.csv")

    class _FailThenInterrupt:
        def __init__(self):
            self.n = 0

        def request(self, method, path, params=None, json=None):
            self.n += 1
            if self.n <= 2:
                raise APIError(400, "bad row")     # rows 1-2 fail → streamed
            raise KeyboardInterrupt                 # row 3 simulates Ctrl-C

    rows = [{"name": f"bp-{i}"} for i in range(10)]

    with pytest.raises(KeyboardInterrupt):
        batch_mod._execute_csv_rows(
            rows, op, "block-pages", "create", _FailThenInterrupt(),
            verbose=False, csv_output=None,
            on_error="continue", concurrency=1, no_progress=True,
            errors_csv=errors_path,
        )

    # The interrupt aborted the run, but the two rows that already failed must
    # be on disk as a resume checkpoint.
    assert os.path.exists(errors_path), "no checkpoint written before interrupt"
    with open(errors_path, newline="") as fh:
        recorded = list(_csv.DictReader(fh))
    names = {r["name"] for r in recorded}
    assert names == {"bp-0", "bp-1"}, f"checkpoint incomplete: {names}"
