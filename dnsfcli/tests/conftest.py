"""Shared fixtures and helpers for dnsfcli tests."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

PROJECT_DIR = Path(__file__).parent.parent
SRC_DIR     = PROJECT_DIR / "src"
CLI_SCRIPT  = PROJECT_DIR / "dnsfcli.py"

sys.path.insert(0, str(SRC_DIR))


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    """Give every in-process test a fresh rate-limiter registry.

    The limiter is shared per API key for the life of a process — correct for
    the CLI (one process per invocation), but in the single pytest process it
    would otherwise let hundreds of same-key client constructions drain one
    bucket and make later tests block on real sleeps. Resetting per test keeps
    the suite fast and isolated. (Subprocess-based CLI tests are unaffected —
    they get their own process.)
    """
    try:
        from dnsfcli.client import _reset_limiter_registry
        _reset_limiter_registry()
    except Exception:
        pass
    yield

# ---------------------------------------------------------------------------
# API credentials
# ---------------------------------------------------------------------------

# Live tests require a real API key supplied via environment variable.
LIVE_API_KEY: str = os.environ.get("DNSF_TEST_API_KEY", "")

# ---------------------------------------------------------------------------
# CLI runner
# ---------------------------------------------------------------------------

def run_cli(
    *args: str,
    api_key: str | None = LIVE_API_KEY,
    raw: bool = False,
    extra: list[str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Invoke dnsfcli.py as a subprocess and return the CompletedProcess."""
    cmd = [sys.executable, str(CLI_SCRIPT)]
    cmd.extend(args)
    if api_key:
        cmd += ["--api-key", api_key]
    if raw:
        cmd += ["--raw"]
    if extra:
        cmd.extend(extra)
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=str(PROJECT_DIR),
    )


def assert_success(result: subprocess.CompletedProcess[str]) -> None:
    """Assert the CLI returned exit code 0 with no error output."""
    assert result.returncode == 0, (
        f"CLI exited {result.returncode}\n"
        f"stdout: {result.stdout[:500]}\n"
        f"stderr: {result.stderr[:500]}"
    )
    assert "Traceback" not in result.stdout
    assert "Traceback" not in result.stderr


def assert_clean_error(result: subprocess.CompletedProcess[str]) -> None:
    """Assert the CLI exited non-zero with a clean Error: line but no traceback."""
    assert result.returncode != 0
    assert "Traceback" not in result.stdout
    assert "Traceback" not in result.stderr
    combined = result.stdout + result.stderr
    assert "Error:" in combined


def json_output(result: subprocess.CompletedProcess[str]) -> Any:
    """Parse --raw JSON output from a successful CLI run."""
    assert_success(result)
    return json.loads(result.stdout.strip())


# ---------------------------------------------------------------------------
# Live API client fixture (used by Python-level live tests)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def api_client():
    """DNSFilterClient pointed at the live API with the test token."""
    sys.path.insert(0, str(SRC_DIR))
    from dnsfcli.client import DNSFilterClient
    client = DNSFilterClient(api_key=LIVE_API_KEY, base_url="https://api.dnsfilter.com")
    yield client
    client.close()


@pytest.fixture(scope="session")
def live_org_id(api_client) -> int:
    """Return the first organization ID visible to the test account."""
    resp = api_client.get("/v1/organizations")
    orgs = resp if isinstance(resp, list) else resp.get("organizations") or resp.get("data") or [resp]
    assert orgs, "No organizations found for test account"
    return orgs[0]["id"]


@pytest.fixture(scope="session")
def live_policy_id(api_client, live_org_id) -> int:
    """Return the first policy ID in the test account."""
    resp = api_client.get("/v1/policies")
    policies = resp if isinstance(resp, list) else resp.get("policies") or resp.get("data") or [resp]
    if not policies:
        pytest.skip("No policies available on test account")
    return policies[0]["id"]
