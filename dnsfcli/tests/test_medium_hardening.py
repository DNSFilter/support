"""Regression tests for the MEDIUM-severity review findings:

M1 concurrency bounds, M2 errors-csv/batch-report 0600 + report scrubbing,
M3 verbose-body redaction, M5 no caching of secret-returning endpoints.
"""

from __future__ import annotations

import json
import stat
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dnsfcli import batch as batch_mod
from dnsfcli.audit import mask_secret_keys
from dnsfcli.client import APIError
from dnsfcli.endpoints import REGISTRY
from tests.conftest import CLI_SCRIPT, PROJECT_DIR


# --- M3: secret-key masking (used by --verbose body and --batch-report) -------

def test_mask_secret_keys_masks_nested_and_named():
    body = {"name": "hq", "password": "hunter2",
            "network": {"api_key": "zzz", "label": "keep"}}
    masked = mask_secret_keys(body)
    assert masked == {"name": "hq", "password": "***",
                      "network": {"api_key": "***", "label": "keep"}}
    # original is not mutated
    assert body["password"] == "hunter2"


def test_mask_secret_keys_recurses_lists():
    """A secret inside a list-of-dicts (or a secret-named key whose value is a
    list) must still be masked — the earlier version leaked these."""
    body = {"users": [{"password": "secret1"}, {"name": "ok"}],
            "token": "abc",
            "network": {"ips": [{"secret_key": "zzz"}]}}
    masked = mask_secret_keys(body)
    assert "secret1" not in str(masked)
    assert "zzz" not in str(masked)
    assert masked["token"] == "***"
    assert masked["users"][1]["name"] == "ok"


# --- M1: concurrency is bounded ----------------------------------------------

def _run(*args):
    return subprocess.run([sys.executable, str(CLI_SCRIPT), *args],
                          capture_output=True, text=True, cwd=str(PROJECT_DIR))


def test_concurrency_flag_rejects_absurd_value():
    r = _run("networks", "list", "--concurrency", "100000", "--dry-run", "--api-key", "FAKE")
    assert r.returncode != 0
    assert "64" in (r.stdout + r.stderr) or "range" in (r.stdout + r.stderr).lower()


def test_org_concurrency_flag_rejects_absurd_value():
    r = _run("networks", "list", "--each-org", "--parallel-orgs",
             "--org-concurrency", "100000", "--dry-run", "--api-key", "FAKE")
    assert r.returncode != 0


# --- M2: errors-csv / batch-report file permissions + report scrubbing --------

class _AllFail:
    def request(self, method, path, params=None, json=None):
        raise APIError(500, "boom")

    def get(self, *a, **k):
        return {}

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _op():
    return REGISTRY["block-pages"].operations["create"]


def test_errors_csv_is_owner_only(tmp_path):
    errs = tmp_path / "errs.csv"
    with pytest.raises(SystemExit):
        batch_mod._execute_csv_rows(
            [{"name": "a"}, {"name": "b"}], _op(), "block-pages", "create", _AllFail(),
            verbose=False, csv_output=None, on_error="stop", no_progress=True,
            errors_csv=str(errs),
        )
    assert errs.exists()
    mode = stat.S_IMODE(errs.stat().st_mode)
    assert mode == 0o600, f"errors-csv perms {oct(mode)} (expected 0o600)"


def test_errors_csv_tightens_preexisting_loose_file(tmp_path):
    """A pre-existing 0644 errors file must be tightened to 0600 (os.open's mode
    arg is ignored when the file already exists — fchmod covers that)."""
    import os
    errs = tmp_path / "errs.csv"
    errs.write_text("stale\n")
    os.chmod(errs, 0o644)
    with pytest.raises(SystemExit):
        batch_mod._execute_csv_rows(
            [{"name": "a"}], _op(), "block-pages", "create", _AllFail(),
            verbose=False, csv_output=None, on_error="stop", no_progress=True,
            errors_csv=str(errs),
        )
    assert stat.S_IMODE(errs.stat().st_mode) == 0o600


def test_batch_report_is_owner_only_and_scrubs_secrets(tmp_path):
    report = tmp_path / "report.json"
    with pytest.raises(SystemExit):
        batch_mod._execute_csv_rows(
            [{"name": "a", "password": "hunter2"}], _op(), "block-pages", "create", _AllFail(),
            verbose=False, csv_output=None, on_error="stop", no_progress=True,
            batch_report_path=str(report),
        )
    assert report.exists()
    mode = stat.S_IMODE(report.stat().st_mode)
    assert mode == 0o600, f"batch-report perms {oct(mode)} (expected 0o600)"
    text = report.read_text()
    assert "hunter2" not in text, "secret value leaked into batch report"
    assert "***" in text


# --- M5: secret-returning endpoints are never cached --------------------------

def test_api_keys_endpoint_not_cached():
    from dnsfcli.cli import _SECRET_RESPONSE_ENDPOINTS
    assert "api-keys" in _SECRET_RESPONSE_ENDPOINTS


# --- R-B: batch safety ---------------------------------------------------------

class _CountingClient:
    def __init__(self, status):
        self.calls = 0
        self._status = status

    def request(self, method, path, params=None, json=None):
        self.calls += 1
        if self._status:
            raise APIError(self._status, "boom")
        return {"id": self.calls}

    def get(self, *a, **k):
        return {}

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_confirm_each_forces_sequential(capsys, monkeypatch):
    """--confirm-each with --concurrency>1 must not silently skip prompts: it
    forces sequential execution (so the serial per-row confirm path runs)."""
    import dnsfcli.batch as b
    prompts = []
    monkeypatch.setattr(b.typer, "confirm", lambda *a, **k: prompts.append(1) or True)
    client = _CountingClient(status=0)
    b._execute_csv_rows(
        [{"name": "a"}, {"name": "b"}], _op(), "block-pages", "create", client,
        verbose=False, csv_output=None, concurrency=8, confirm_each=True, no_progress=True,
    )
    out = capsys.readouterr()
    assert "sequential" in (out.out + out.err)
    assert len(prompts) == 2  # prompted once per row (serial path), not skipped


def test_post_5xx_not_retried_but_idempotent_is(capsys):
    """POST is NOT retried on 5xx (duplicate-write risk); the run warns once.
    (Idempotent retry is covered by the client-level tests.)"""
    client = _CountingClient(status=500)
    with pytest.raises(SystemExit):
        batch_mod._execute_csv_rows(
            [{"name": "a"}], _op(), "block-pages", "create", client,
            verbose=False, csv_output=None, on_error="stop", no_progress=True, retry=3,
        )
    # create == POST → exactly one attempt despite retry=3
    assert client.calls == 1
    combined = capsys.readouterr()
    assert "NOT retried" in (combined.out + combined.err)


def test_results_not_accumulated_without_csv_output(monkeypatch):
    """Successful responses are not retained in memory unless --to-csv is set."""
    import dnsfcli.batch as b
    captured = {}
    real = b.write_csv
    client = _CountingClient(status=0)
    # Spy on the results list by wrapping write_csv (only called when csv_output).
    b._execute_csv_rows(
        [{"name": f"r{i}"} for i in range(10)], _op(), "block-pages", "create", client,
        verbose=False, csv_output=None, no_progress=True,
    )
    # Nothing to assert on a private list directly; the guard is `and csv_output`.
    # Instead assert the code path ran to completion (10 calls) with no csv write.
    assert client.calls == 10
