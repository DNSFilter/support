"""Smoke tests for app_entry routing and every extracted sub-command group.

These exercise the code paths that the phase-2 module split touched — in
particular the direct-alias / unknown-endpoint branch of app_entry, whose
call to _load_aliases (moved to commands/alias.py) was a regression the rest
of the suite did not cover. Each command is run as a real subprocess and must
not dump a traceback.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from tests.conftest import CLI_SCRIPT, PROJECT_DIR


def _run(*args):
    return subprocess.run(
        [sys.executable, str(CLI_SCRIPT), *args],
        capture_output=True, text=True, cwd=str(PROJECT_DIR),
    )


@pytest.mark.parametrize("args", [
    ["config", "show"],
    ["endpoints"],
    ["auth", "show"],
    ["audit", "show"],
    ["cache", "show"],
    ["alias", "list"],
    ["env"],
    ["schema", "networks", "list"],
    ["completion", "show", "bash"],
    ["--help"],
    ["auth", "--help"],
    ["config", "--help"],
    ["history", "--help"],
    ["diff", "--help"],
])
def test_command_group_no_traceback(args):
    """Every extracted sub-command group loads and runs without a traceback."""
    r = _run(*args)
    assert "Traceback (most recent call last)" not in (r.stdout + r.stderr), \
        f"{args} dumped a traceback:\n{r.stdout}\n{r.stderr}"


def test_unknown_first_arg_routes_cleanly():
    """An unknown first arg hits app_entry's alias/endpoint branch (which
    calls _load_aliases) — it must give a clean error, not a NameError."""
    r = _run("definitely-not-a-real-endpoint")
    combined = r.stdout + r.stderr
    assert "Traceback" not in combined
    assert r.returncode != 0
    assert "Unknown endpoint" in combined


def test_save_as_persists_alias(tmp_path):
    """`--save-as` on a dynamic command must save the alias, not NameError.
    (_load_aliases/_save_aliases moved to commands/alias.py in the refactor;
    the _cmd --save-as block referencing them was an uncovered regression.)"""
    save = _run("networks", "list", "--save-as", "smoke-saveas", "--dry-run", "--api-key", "FAKE")
    try:
        combined = save.stdout + save.stderr
        assert "Traceback" not in combined
        assert "Saved alias" in combined or "Updated alias" in combined
        listing = _run("alias", "list")
        assert "smoke-saveas" in (listing.stdout + listing.stderr)
    finally:
        _run("alias", "delete", "smoke-saveas")


def test_domain_enrichment_helper_shared():
    """_enrich_domain_result is used by both _run_api_call and lookupdomain;
    it must resolve to one shared implementation (it was left in commands/misc
    while _run_api_call still referenced it — an uncovered NameError path)."""
    from dnsfcli.cli import _enrich_domain_result as from_cli
    from dnsfcli.commands.misc import _enrich_domain_result as from_misc
    from dnsfcli.postprocess import _enrich_domain_result as from_pp
    assert from_cli is from_misc is from_pp


def test_direct_alias_invocation_routes(tmp_path):
    """`dnsfcli <alias>` must resolve a saved alias through app_entry
    (the branch that regressed after the command-module split)."""
    # Save an alias, invoke it directly with --dry-run (no network), clean up.
    setup = _run("alias", "set", "routing-smoke", "networks list --limit 1")
    assert setup.returncode == 0
    try:
        r = _run("routing-smoke", "--dry-run", "--api-key", "FAKE")
        combined = r.stdout + r.stderr
        assert "Traceback" not in combined
        assert "Dry Run" in combined or "dry run" in combined.lower()
    finally:
        _run("alias", "delete", "routing-smoke")
