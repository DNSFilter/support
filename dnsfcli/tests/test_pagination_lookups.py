"""Behavioral proof that the multi-page lookups actually consider page 2+.

Replaces brittle inspect.getsource "the string _fetch_all_pages appears near
the call site" assertions (which survive the mutation 'call it but use a
single-page result') with end-to-end runs where the matching record exists
ONLY on page 2. If any lookup regressed to a single-page GET, these fail.
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


def _paged(items_by_page: dict[int, list], total_pages: int):
    def _resp(params):
        page = int((params or {}).get("page[number]", 1) or 1)
        return {"data": items_by_page.get(page, []), "meta": {"total_pages": total_pages}}
    return _resp


def _install(monkeypatch, route):
    """route(method, path, params) -> json response."""
    def fake_request(self, method, path, params=None, json=None):
        return route(method, path, params)
    for mod in (_cli, _cliparams):
        monkeypatch.setattr(mod, "get_api_key", lambda profile="default": "k", raising=False)
        monkeypatch.setattr(mod, "get_base_url", lambda profile="default": "https://api.dnsfilter.com", raising=False)
        monkeypatch.setattr(mod, "get_org_id", lambda profile="default": None, raising=False)
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


def test_org_name_resolves_match_on_page_2(monkeypatch):
    orgs = _paged({
        1: [{"id": "1", "attributes": {"name": "Acme"}}],
        2: [{"id": "2", "attributes": {"name": "Zeta Corp"}}],
    }, total_pages=2)

    def route(method, path, params):
        if path.startswith("/v1/organizations"):
            return orgs(params)
        return {"data": [], "meta": {"total_pages": 1}}

    _install(monkeypatch, route)
    # Zeta exists only on page 2; a single-page lookup would error "no org matches".
    code, out = _run("networks", "list", ["--org-name", "Zeta", "--dry-run"])
    assert "no organization matches" not in out, out
    assert code == 0, out


def test_each_org_lists_page_2(monkeypatch):
    orgs = _paged({
        1: [{"id": "1", "attributes": {"name": "Acme"}}],
        2: [{"id": "2", "attributes": {"name": "Beta"}}],
    }, total_pages=2)

    def route(method, path, params):
        if path.startswith("/v1/organizations"):
            return orgs(params)
        return {"data": [], "meta": {"total_pages": 1}}

    _install(monkeypatch, route)
    # --each-org must iterate BOTH orgs; the page-2 org's header must appear.
    code, out = _run("networks", "list", ["--each-org", "--dry-run"])
    assert "Acme" in out and "Beta" in out, f"page-2 org missing from fan-out:\n{out}"


def test_join_matches_remote_on_page_2(monkeypatch):
    # primary result references policy id "P2", which lives only on page 2 of policies
    def route(method, path, params):
        if path.startswith("/v1/networks") and not path.rstrip("/").split("/")[-1].isdigit():
            return {"data": [{"id": "1", "name": "n1", "policy_id": "P2"}], "meta": {"total_pages": 1}}
        if path.startswith("/v1/policies"):
            page = int((params or {}).get("page[number]", 1) or 1)
            data = [{"id": "P1", "label": "first"}] if page == 1 else [{"id": "P2", "label": "second"}]
            return {"data": data, "meta": {"total_pages": 2}}
        return {"data": [], "meta": {"total_pages": 1}}

    _install(monkeypatch, route)
    code, out = _run("networks", "list", ["--join", "policies:policy_id=id", "--json"])
    # If the join fetched only page 1 of policies, "second" (P2) would be missing.
    assert "second" in out, f"--join did not match a remote record on page 2:\n{out}"
