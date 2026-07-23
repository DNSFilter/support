"""Regression tests for the pipeline-correctness review findings (batch C):
--all --limit overshoot, --sort on mixed-type fields, --wait exit code on job
failure, and organization_id coercion.
"""

from __future__ import annotations

import contextlib
import io
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dnsfcli import cli as _cli
from dnsfcli import cliparams as _cliparams
from dnsfcli import client as _client


def _install(monkeypatch, route, org=None):
    def fake_request(self, method, path, params=None, json=None):
        return route(method, path, params, json)
    for mod in (_cli, _cliparams):
        monkeypatch.setattr(mod, "get_api_key", lambda profile="default": "k", raising=False)
        monkeypatch.setattr(mod, "get_base_url", lambda profile="default": "https://api.dnsfilter.com", raising=False)
        monkeypatch.setattr(mod, "get_org_id", lambda profile="default": org, raising=False)
    monkeypatch.setattr(_cli, "get_active_profile", lambda: "default", raising=False)
    monkeypatch.setattr(_client.DNSFilterClient, "request", fake_request)


def _run(endpoint, function, args):
    out = io.StringIO()
    code = 0
    cmd = _cli._make_dynamic_command(endpoint, function)
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
        try:
            cmd.main(args=args, standalone_mode=True)
        except SystemExit as e:
            code = e.code if isinstance(e.code, int) else (0 if e.code is None else 1)
    return code, out.getvalue()


# --- R2-2: --all --limit N returns exactly N -----------------------------------

def test_all_with_limit_returns_exactly_n(monkeypatch):
    # 3 items/page across 2 pages = 6 items available.
    def route(method, path, params, json):
        page = int((params or {}).get("page[number]", 1) or 1)
        base = (page - 1) * 3
        return {"data": [{"id": str(base + i)} for i in range(3)],
                "meta": {"total_pages": 2}}
    _install(monkeypatch, route)
    code, out = _run("networks", "list", ["--all", "--limit", "4", "--json"])
    import json as _j
    data = _j.loads(out)
    rows = data if isinstance(data, list) else data.get("data", data)
    assert len(rows) == 4, f"--all --limit 4 returned {len(rows)} rows, expected 4"


# --- R2-4: --sort on a mixed-type field must not crash -------------------------

def test_sort_mixed_types_does_not_crash(monkeypatch):
    def route(method, path, params, json):
        return {"data": [{"v": 10}, {"v": "abc"}, {"v": None}, {"v": 2}],
                "meta": {"total_pages": 1}}
    _install(monkeypatch, route)
    code, out = _run("networks", "list", ["--sort", "v", "--json"])
    assert code == 0, f"--sort on mixed types crashed: {out}"
    assert "not supported between" not in out


# --- R2-3: --wait exit code reflects job outcome -------------------------------

def _fake_job_client(status_sequence):
    """A client whose poll GETs walk through status_sequence."""
    seq = list(status_sequence)

    class _C:
        def __init__(self, *a, **k):
            pass

        def request(self, method, path, params=None, json=None):
            return {"data": {"id": "job1", "status": seq.pop(0) if seq else "done"}}

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    return _C


def test_wait_returns_false_on_terminal_error(monkeypatch):
    from dnsfcli import jobs
    monkeypatch.setattr("time.sleep", lambda *_: None)
    monkeypatch.setattr(jobs, "DNSFilterClient", _fake_job_client(["failed"]))
    # a real poll op for domains? use a known endpoint/function with poll target;
    # _wait_for_job only needs get_operation(endpoint, poll_function) to resolve.
    from dnsfcli.endpoints import REGISTRY
    ep = next(iter(REGISTRY))
    fn = next(iter(REGISTRY[ep].operations))
    ok = jobs._wait_for_job(
        {"data": {"id": "job1"}}, ep, fn, "k", "https://api.dnsfilter.com", "1",
        raw=False, title="t", columns=None,
    )
    assert ok is False


def test_wait_returns_true_on_success(monkeypatch):
    from dnsfcli import jobs
    monkeypatch.setattr("time.sleep", lambda *_: None)
    monkeypatch.setattr(jobs, "DNSFilterClient", _fake_job_client(["completed"]))
    from dnsfcli.endpoints import REGISTRY
    ep = next(iter(REGISTRY))
    fn = next(iter(REGISTRY[ep].operations))
    ok = jobs._wait_for_job(
        {"data": {"id": "job1"}}, ep, fn, "k", "https://api.dnsfilter.com", "1",
        raw=False, title="t", columns=None,
    )
    assert ok is True


# --- R2-6: organization_id coercion --------------------------------------------

def test_coerce_org_id():
    from dnsfcli.cli import _coerce_org_id
    assert _coerce_org_id("802315") == 802315
    assert _coerce_org_id("  42 ") == 42
    assert _coerce_org_id("acme-uuid-01") == "acme-uuid-01"  # non-numeric passes through, no crash
