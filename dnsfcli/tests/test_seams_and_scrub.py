"""Direct tests for the refactor seams and secret-scrub coverage gaps.

- T6: _scrub_argv must mask --api-key / --header / --proxy (previously only the
  dynamic-name cases were asserted).
- Seam contracts: RESERVED_CLI_FLAGS matches the real option set,
  cliparams.resolve_http_context resolves/validates credentials, and
  batch.run_batch / dispatch_* exist with the expected signatures.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dnsfcli import cliparams
from dnsfcli.audit import _scrub_argv


# --- T6: history scrubber masks the explicit secret flags --------------------

@pytest.mark.parametrize("argv,secret", [
    (["networks", "list", "--api-key", "SECRETKEY"], "SECRETKEY"),
    (["networks", "list", "--api-key=SECRETKEY"], "SECRETKEY"),
    (["x", "create", "--header", "Authorization=Bearer tok123"], "tok123"),
    (["x", "create", "--proxy", "http://u:pw@h:8080"], "pw@h"),
])
def test_scrub_argv_masks_explicit_secret_flags(argv, secret):
    scrubbed = " ".join(_scrub_argv(argv))
    assert secret not in scrubbed, f"{secret!r} survived scrubbing: {scrubbed}"
    assert "***" in scrubbed


def test_scrub_argv_keeps_nonsecret():
    assert _scrub_argv(["networks", "list", "--limit", "5"]) == ["networks", "list", "--limit", "5"]


# --- Seam: RESERVED_CLI_FLAGS is consistent with the real option table --------

def test_reserved_flags_match_option_table():
    """Every generic option in cliopts._OPTION_SPECS (minus its leading '--')
    must be in RESERVED_CLI_FLAGS, so _run_api_call strips them all from the
    caller-supplied --key=value args. A drift here silently lets a reserved flag
    through as an API parameter."""
    from dnsfcli import cliopts
    declared = set()
    for spec in cliopts._OPTION_SPECS:
        # each spec is click.option(...) applied → inspect its param decls via a probe
        # Simpler: re-derive from the source names is brittle; instead apply to a
        # dummy and read the registered option's long name.
        def _probe(f):
            return f
        # click.option returns a decorator; apply to a throwaway to capture params
        fn = spec(_probe)
        for p in getattr(fn, "__click_params__", []):
            for opt in getattr(p, "opts", []):
                if opt.startswith("--"):
                    declared.add(opt[2:])
    missing = declared - set(cliparams.RESERVED_CLI_FLAGS)
    assert not missing, f"option(s) not in RESERVED_CLI_FLAGS: {sorted(missing)}"


# --- Seam: resolve_http_context ----------------------------------------------

def _opts(**over):
    base = dict(api_key=None, org_id=None, profile="default", insecure=False,
                proxy=None, connect_timeout=None, extra_headers=None)
    base.update(over)
    return types.SimpleNamespace(**base)


def test_resolve_http_context_happy_path(monkeypatch):
    monkeypatch.setattr(cliparams, "get_api_key", lambda profile="default": "K")
    monkeypatch.setattr(cliparams, "get_org_id", lambda profile="default": "42")
    monkeypatch.setattr(cliparams, "get_base_url", lambda profile="default": "https://api.dnsfilter.com")
    key, org, base, ck = cliparams.resolve_http_context(_opts())
    assert key == "K" and org == "42" and base == "https://api.dnsfilter.com"
    assert ck["api_key"] == "K" and ck["verify"] is True and ck["base_url"] == base


def test_resolve_http_context_exits_without_key(monkeypatch):
    monkeypatch.setattr(cliparams, "get_api_key", lambda profile="default": None)
    monkeypatch.setattr(cliparams, "get_base_url", lambda profile="default": "https://api.dnsfilter.com")
    with pytest.raises(SystemExit):
        cliparams.resolve_http_context(_opts())


def test_resolve_http_context_exits_on_non_https(monkeypatch):
    monkeypatch.setattr(cliparams, "get_api_key", lambda profile="default": "K")
    monkeypatch.setattr(cliparams, "get_org_id", lambda profile="default": None)
    monkeypatch.setattr(cliparams, "get_base_url", lambda profile="default": "http://insecure.example.com")
    with pytest.raises(SystemExit):
        cliparams.resolve_http_context(_opts())


def test_resolve_http_context_insecure_and_proxy(monkeypatch):
    monkeypatch.setattr(cliparams, "get_api_key", lambda profile="default": "K")
    monkeypatch.setattr(cliparams, "get_org_id", lambda profile="default": None)
    monkeypatch.setattr(cliparams, "get_base_url", lambda profile="default": "https://api.dnsfilter.com")
    _, _, _, ck = cliparams.resolve_http_context(_opts(insecure=True, proxy="http://p:8080"))
    assert ck["verify"] is False and ck["proxy"] == "http://p:8080"


# --- Seam: batch dispatch surface --------------------------------------------

def test_batch_dispatch_functions_exist():
    from dnsfcli import batch
    for name in ("run_batch", "dispatch_from_csv", "dispatch_from_json"):
        assert callable(getattr(batch, name)), f"batch.{name} missing"
