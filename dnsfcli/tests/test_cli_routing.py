"""Integration tests for CLI routing, flag handling, and error output.

These call dnsfcli.py as a subprocess. No live API needed -- requests that
reach the network will fail with a 401, which we treat as "routing worked".
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

# Import helpers from conftest (pytest injects them automatically)
from tests.conftest import LIVE_API_KEY, assert_clean_error, run_cli

FAKE_KEY = "not-a-real-key"


# ---------------------------------------------------------------------------
# Help and discovery
# ---------------------------------------------------------------------------

class TestHelpAndDiscovery:
    def test_no_args_shows_help(self):
        result = run_cli(api_key=None)
        # Typer exits with code 2 when invoked with no sub-command
        assert result.returncode in (0, 2)
        assert "dnsfcli" in result.stdout.lower()

    def test_help_flag(self):
        result = run_cli("--help", api_key=None)
        assert result.returncode == 0
        assert "endpoints" in result.stdout
        assert "auth" in result.stdout

    def test_endpoints_command_lists_all(self):
        result = run_cli("endpoints", api_key=None)
        assert result.returncode == 0
        for ep in ("networks", "policies", "organizations", "users", "traffic-reports"):
            assert ep in result.stdout

    def test_endpoints_command_with_specific_endpoint(self):
        result = run_cli("endpoints", "networks", api_key=None)
        assert result.returncode == 0
        for fn in ("list", "show", "create", "update", "delete"):
            assert fn in result.stdout

    def test_endpoint_without_function_shows_available(self):
        result = run_cli("users", api_key=None)
        assert result.returncode == 0
        assert "Available functions" in result.stdout or "list" in result.stdout

    def test_function_help_flag(self):
        result = run_cli("users", "show", "--help", api_key=None)
        assert result.returncode == 0
        assert "--raw" in result.stdout
        assert "--api-key" in result.stdout


# ---------------------------------------------------------------------------
# Error handling -- clean errors with no traceback
# ---------------------------------------------------------------------------

class TestErrorHandling:
    def test_missing_required_path_param_shows_clean_error(self):
        result = run_cli("users", "show", api_key=FAKE_KEY)
        assert_clean_error(result)
        assert "--id" in result.stderr or "--id" in result.stdout

    def test_missing_id_for_network_show(self):
        result = run_cli("networks", "show", api_key=FAKE_KEY)
        assert_clean_error(result)

    def test_missing_id_for_policies_update(self):
        result = run_cli("policies", "update", "--name", "x", api_key=FAKE_KEY)
        assert_clean_error(result)

    def test_missing_path_param_nested_route(self):
        # organizations users-show needs --organization_id AND --id
        result = run_cli("organizations", "users-show", "--id", "1", api_key=FAKE_KEY)
        assert_clean_error(result)

    def test_unrecognised_api_key_shows_clean_error(self):
        # Use a syntactically valid but definitely-rejected key.
        # The OS keychain may hold a real token (making api_key=None succeed),
        # so we must pass an explicit bad key to reliably exercise the error path.
        result = run_cli("users", "list", api_key="DELIBERATELY.INVALID.KEY")
        assert_clean_error(result)

    def test_invalid_api_key_exits_non_zero(self):
        result = run_cli("users", "list", api_key=FAKE_KEY)
        assert result.returncode != 0
        assert "Traceback" not in result.stdout
        assert "Traceback" not in result.stderr

    def test_error_message_present_on_auth_failure(self):
        result = run_cli("users", "list", api_key=FAKE_KEY)
        combined = result.stdout + result.stderr
        assert "Error:" in combined


# ---------------------------------------------------------------------------
# --raw flag in all positions
# ---------------------------------------------------------------------------

class TestRawFlag:
    """All five positions for --raw should parse identically (no crash)."""

    def _raw_positions(self) -> list[tuple[str, list[str]]]:
        base = ["users", "list"]
        flags = ["--api-key", FAKE_KEY]
        return [
            ("after-all-flags",     base + flags + ["--raw"]),
            ("before-other-flags",  base + ["--raw"] + flags),
            ("between-ep-fn",       ["users", "--raw", "list"] + flags),
            ("before-endpoint",     ["--raw"] + base + flags),
            ("-r-shorthand",        ["-r"] + base + flags),
        ]

    @pytest.mark.parametrize("label,argv", [
        ("after-all-flags",    ["users", "list", "--api-key", FAKE_KEY, "--raw"]),
        ("before-other-flags", ["users", "list", "--raw", "--api-key", FAKE_KEY]),
        ("between-ep-fn",      ["users", "--raw", "list", "--api-key", FAKE_KEY]),
        ("before-endpoint",    ["--raw", "users", "list", "--api-key", FAKE_KEY]),
        ("-r-shorthand",       ["-r", "users", "list", "--api-key", FAKE_KEY]),
    ])
    def test_raw_flag_position(self, label, argv):
        """--raw in any position should not cause a routing or parse error."""
        import subprocess
        from tests.conftest import CLI_SCRIPT, PROJECT_DIR
        result = subprocess.run(
            [sys.executable, str(CLI_SCRIPT)] + argv,
            capture_output=True, text=True, cwd=str(PROJECT_DIR),
        )
        # With a fake key we expect a 401 error, but NO traceback and NO
        # "Error: flag" parse error -- the flag was understood.
        assert "Traceback" not in result.stdout
        assert "Traceback" not in result.stderr
        combined = result.stdout + result.stderr
        # Should not be "unknown option" error
        assert "unknown option" not in combined.lower()
        assert "no such option" not in combined.lower()


# ---------------------------------------------------------------------------
# --csv flag
# ---------------------------------------------------------------------------

# Three tests below exercise --to-csv against the real /v1/categories
# endpoint, so they need a token and network — same contract as test_live.py.
# Without the guard they pass on developer machines by silently falling back
# to keychain credentials, then fail in CI where no keychain exists.
_requires_live_key = pytest.mark.skipif(
    not LIVE_API_KEY, reason="requires DNSF_TEST_API_KEY (live API test)"
)


class TestCsvFlag:
    """--csv FILE should work regardless of where it appears in the command line."""

    @pytest.mark.live
    @_requires_live_key
    @pytest.mark.parametrize("argv_builder", [
        # after all other flags
        lambda f: ["categories", "list", "--api-key", LIVE_API_KEY, "--to-csv", f],
        # before endpoint
        lambda f: ["--to-csv", f, "categories", "list", "--api-key", LIVE_API_KEY],
        # between endpoint and function
        lambda f: ["categories", "--to-csv", f, "list", "--api-key", LIVE_API_KEY],
    ])
    def test_csv_creates_file(self, argv_builder, tmp_path):
        import subprocess
        from tests.conftest import CLI_SCRIPT, PROJECT_DIR
        out = str(tmp_path / "out.csv")
        argv = argv_builder(out)
        result = subprocess.run(
            [sys.executable, str(CLI_SCRIPT)] + argv,
            capture_output=True, text=True, cwd=str(PROJECT_DIR),
        )
        assert result.returncode == 0, f"Exit {result.returncode}: {result.stderr}"
        assert Path(out).exists(), "--csv did not create the file"

    @pytest.mark.live
    @_requires_live_key
    def test_csv_file_has_header_row(self, tmp_path):
        import subprocess, csv as csv_mod
        from tests.conftest import CLI_SCRIPT, PROJECT_DIR
        out = tmp_path / "out.csv"
        result = subprocess.run(
            [sys.executable, str(CLI_SCRIPT),
             "categories", "list", "--to-csv", str(out), "--api-key", LIVE_API_KEY],
            capture_output=True, text=True, cwd=str(PROJECT_DIR),
        )
        assert result.returncode == 0
        with out.open() as f:
            rows = list(csv_mod.reader(f))
        assert len(rows) >= 2          # header + at least one data row
        assert "id" in rows[0]         # DNSFilter categories always have an id

    @pytest.mark.live
    @_requires_live_key
    def test_csv_stdout_shows_success_message(self, tmp_path):
        import subprocess
        from tests.conftest import CLI_SCRIPT, PROJECT_DIR
        out = tmp_path / "out.csv"
        result = subprocess.run(
            [sys.executable, str(CLI_SCRIPT),
             "categories", "list", "--to-csv", str(out), "--api-key", LIVE_API_KEY],
            capture_output=True, text=True, cwd=str(PROJECT_DIR),
        )
        assert result.returncode == 0
        # Rich may wrap a long path across two lines; just check the key words
        assert "Wrote" in result.stdout
        assert out.name in result.stdout   # basename is always on one line

    def test_csv_with_fake_key_exits_cleanly(self, tmp_path):
        """--csv with a bad key should print a clean error and not create the file.
        Uses /users which requires auth (unlike /categories which is public)."""
        import subprocess
        from tests.conftest import CLI_SCRIPT, PROJECT_DIR
        out = tmp_path / "out.csv"
        result = subprocess.run(
            [sys.executable, str(CLI_SCRIPT),
             "users", "list", "--to-csv", str(out), "--api-key", "FAKE"],
            capture_output=True, text=True, cwd=str(PROJECT_DIR),
        )
        assert result.returncode != 0
        assert "Traceback" not in result.stdout + result.stderr
        assert not out.exists()   # file should not have been created on error

    def test_csv_help_shows_option(self):
        result = run_cli("categories", "list", "--help", api_key=None)
        assert result.returncode == 0
        assert "--to-csv" in result.stdout


# ---------------------------------------------------------------------------
# --verbose flag
# ---------------------------------------------------------------------------

class TestVerboseFlag:
    def test_verbose_shows_url(self):
        result = run_cli("networks", "list", "--verbose", "--api-key", FAKE_KEY)
        combined = result.stdout + result.stderr
        # Verbose mode should print the request URL
        assert "api.dnsfilter.com" in combined

    def test_verbose_shows_correct_path(self):
        result = run_cli("networks", "show", "--id", "1", "--verbose", "--api-key", FAKE_KEY)
        combined = result.stdout + result.stderr
        assert "/v1/networks/1" in combined

    def test_verbose_shows_post_body(self):
        result = run_cli(
            "policies", "add-blacklist-domain",
            "--id", "1", "--domain", "evil.com",
            "--verbose", "--api-key", FAKE_KEY,
        )
        combined = result.stdout + result.stderr
        assert "evil.com" in combined


# ---------------------------------------------------------------------------
# Path parameter substitution
# ---------------------------------------------------------------------------

class TestPathSubstitution:
    def test_id_substituted_in_verbose_url(self):
        result = run_cli("networks", "show", "--id", "42", "--verbose", "--api-key", FAKE_KEY)
        combined = result.stdout + result.stderr
        assert "/v1/networks/42" in combined

    def test_org_id_and_user_id_both_substituted(self):
        result = run_cli(
            "organizations", "users-show",
            "--organization_id", "10", "--id", "20",
            "--verbose", "--api-key", FAKE_KEY,
        )
        combined = result.stdout + result.stderr
        assert "/v1/organizations/10/users/20" in combined

    def test_nested_subnet_path(self):
        result = run_cli(
            "networks", "subnets-show",
            "--id", "5", "--subnet_id", "7",
            "--verbose", "--api-key", FAKE_KEY,
        )
        combined = result.stdout + result.stderr
        assert "/v1/networks/5/subnets/7" in combined

    def test_traffic_report_query_params_sent(self):
        result = run_cli(
            "traffic-reports", "total-requests",
            "--start_date", "2025-01-01",
            "--end_date", "2025-01-31",
            "--verbose", "--api-key", FAKE_KEY,
        )
        combined = result.stdout + result.stderr
        assert "2025-01-01" in combined


# ---------------------------------------------------------------------------
# Auth sub-commands (no network)
# ---------------------------------------------------------------------------

class TestAuthCommands:
    def test_auth_help(self):
        result = run_cli("auth", "--help", api_key=None)
        assert result.returncode == 0
        for cmd in ("setup", "show", "clear", "verify"):
            assert cmd in result.stdout

    def test_auth_show_when_no_credentials(self):
        # Should not crash even if no credentials are stored
        result = run_cli("auth", "show", api_key=None)
        assert result.returncode == 0
        assert "Traceback" not in result.stdout

    def test_version_flag(self):
        result = run_cli("--version", api_key=None)
        assert result.returncode == 0
        assert "dnsfcli" in result.stdout.lower() or "0.1" in result.stdout
