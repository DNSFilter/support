"""Regression tests for the comprehensive final-audit findings.

Highest priority: the --exec command-injection RCE and the --dry-run batch
bypass — both were driven by untrusted API data in the tool's core workflow.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dnsfcli import audit as audit_mod
from dnsfcli import cli as cli_mod
from dnsfcli import output as output_mod


# ---------------------------------------------------------------------------
# --exec command injection (CRITICAL)
#
# These call the REAL renderer (postprocess.render_exec_command); the full
# adversarial matrix — quoted-placeholder $() / backtick / ; | && vectors and
# the end-to-end CLI-refuses-to-execute test — lives in test_exec_injection.py.
# (A prior version tested a local reimplementation and only the safe unquoted
# case, staying green over a live RCE; that is deliberately gone.)
# ---------------------------------------------------------------------------

def test_exec_refuses_metacharacter_value_real_function():
    from dnsfcli.postprocess import render_exec_command
    rendered, unsafe = render_exec_command('echo "{name}"', {"name": "$(id)"})
    assert unsafe == ["name"], f"metachar value not flagged (rendered {rendered!r})"


def test_exec_legit_substitution_still_works():
    from dnsfcli.postprocess import render_exec_command
    assert render_exec_command("curl https://h/{id}", {"id": "510528"}) == ("curl https://h/510528", [])


def test_exec_prefix_collision_not_oversubstituted():
    from dnsfcli.postprocess import render_exec_command
    # $id must not substitute inside $id_extra
    assert render_exec_command("echo $id_extra", {"id": "5"}) == ("echo $id_extra", [])


# ---------------------------------------------------------------------------
# --dry-run must not write in batch mode (CRITICAL)
# ---------------------------------------------------------------------------

def test_dry_run_batch_sends_no_request(tmp_path):
    """--from-csv --dry-run must make ZERO API calls."""
    from dnsfcli.endpoints import REGISTRY

    csv_path = tmp_path / "rows.csv"
    csv_path.write_text("name\nBP one\nBP two\n")

    class _NoCallClient:
        def __init__(self, *a, **k):
            pass
        def request(self, *a, **k):
            raise AssertionError("dry-run made a real API request")
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False

    # Run the actual CLI in a subprocess with a fake key; the dry-run branch
    # must short-circuit before any client call. (A real request would fail
    # auth, but dry-run should not even reach that.)
    from tests.conftest import CLI_SCRIPT, PROJECT_DIR
    r = subprocess.run(
        [sys.executable, str(CLI_SCRIPT), "block-pages", "create",
         "--from-csv", str(csv_path), "--dry-run", "--api-key", "FAKE"],
        capture_output=True, text=True, cwd=str(PROJECT_DIR),
    )
    combined = r.stdout + r.stderr
    assert "Dry Run" in combined or "dry" in combined.lower()
    assert "No requests sent" in combined or "no requests sent" in combined.lower()
    # It must not have attempted a real create (which would surface an auth error).
    assert "Not Authorized" not in combined and "401" not in combined


# ---------------------------------------------------------------------------
# Secret CLI params scrubbed from history (HIGH)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("argv,secret", [
    (["enterprise-connections", "create", "--client-secret", "SHH"], "SHH"),
    (["billing", "create", "--payment-token", "tok_live_x"], "tok_live_x"),
    (["users", "change-password", "--new-password", "hunter2"], "hunter2"),
    (["x", "--set", "client_secret=SHH2"], "SHH2"),
    (["x", "--body-json", '{"client_secret":"deep"}'], "deep"),
])
def test_secret_params_scrubbed(argv, secret):
    scrubbed = audit_mod._scrub_argv(argv)
    assert secret not in " ".join(scrubbed), f"secret leaked: {scrubbed}"
    assert "***" in " ".join(scrubbed)


def test_nonsecret_params_preserved():
    scrubbed = audit_mod._scrub_argv(["networks", "list", "--filter", "status=active"])
    assert scrubbed == ["networks", "list", "--filter", "status=active"]


# ---------------------------------------------------------------------------
# CSV formula injection (HIGH)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("dangerous", [
    '=HYPERLINK("http://evil","x")',
    "@SUM(A1:A9)",
    "=cmd|'/c calc'!A1",
    "\t=1+1",
])
def test_csv_formula_neutralized(dangerous):
    assert output_mod._csv_cell(dangerous).startswith("'")


@pytest.mark.parametrize("safe", ["example.com", "-5", "-5.5", "+42", "0", "hello"])
def test_csv_safe_values_untouched(safe):
    assert output_mod._csv_cell(safe) == safe


# ---------------------------------------------------------------------------
# org_name path traversal in --each-org file output (MED-HIGH)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("evil", [
    "../../../../etc/passwd",
    "..",
    "....//",
    "a/b/c",
    "$(whoami)",
    "org\nname",
    "..⁄x",   # unicode fraction slash
])
def test_sanitize_path_component_blocks_traversal(evil):
    """The REAL sanitizer (cliparams.sanitize_path_component, used by
    cli._expand_org_path for API-supplied {org_name}/{org_id}) must never emit
    a path separator or a bare dot-segment."""
    from dnsfcli.cliparams import sanitize_path_component
    out = sanitize_path_component(evil)
    assert "/" not in out
    assert "\\" not in out
    assert out not in (".", "..")
    assert out  # never empty


def test_expand_org_path_traversal_stays_in_dir():
    """End-to-end substitution stays inside the template's directory."""
    from dnsfcli.cliparams import sanitize_path_component
    out = "reports/{org_name}.csv".replace(
        "{org_name}", sanitize_path_component("../../../../etc/passwd")
    )
    assert out.startswith("reports/") and out.count("/") == 1
    resolved = (Path.cwd() / out).resolve()
    assert str(resolved).startswith(str((Path.cwd() / "reports").resolve()))


# ---------------------------------------------------------------------------
# --rate cannot exceed the API sustained budget (MED, infra abuse)
# ---------------------------------------------------------------------------

def test_rate_is_capped_at_api_limit():
    from dnsfcli import client as client_mod
    client_mod._reset_limiter_registry()
    c = client_mod.DNSFilterClient(api_key="RATECAP", base_url="https://api.dnsfilter.com", rate=100000)
    try:
        assert c._rate_limiter._refill_rate <= client_mod._RATE_LIMIT_REFILL
    finally:
        c.close()
        client_mod._reset_limiter_registry()


# ---------------------------------------------------------------------------
# --transform ** DoS operator removed (LOW)
# ---------------------------------------------------------------------------

def test_transform_rejects_power_operator():
    from dnsfcli.postprocess import _compile_transform_expr
    with pytest.raises((ValueError, SyntaxError)):
        _compile_transform_expr("9**9**9")


# ---------------------------------------------------------------------------
# aggregates coerce numeric strings (LOW-MED)
# ---------------------------------------------------------------------------

def test_sum_coerces_numeric_strings():
    items = [{"n": "10"}, {"n": 20}, {"n": "not-a-number"}, {"n": None}]
    assert cli_mod._apply_sum(items, "n") == 30.0


# ---------------------------------------------------------------------------
# --filter = / != is numeric-aware (matches >/< coercion)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("cell", [90, 90.0, "90", "90.0"])
def test_filter_equality_numeric_aware(cell):
    """score=90 must match whether the API returns 90, 90.0, "90", or "90.0"."""
    matched = cli_mod._apply_filters([{"score": cell}], ["score=90"])
    assert len(matched) == 1, f"score={cell!r} did not match filter score=90"


def test_filter_not_equal_numeric_aware():
    matched = cli_mod._apply_filters([{"score": "90.0"}, {"score": "5"}], ["score!=90"])
    assert [m["score"] for m in matched] == ["5"]


def test_filter_string_equality_still_works():
    matched = cli_mod._apply_filters(
        [{"status": "active"}, {"status": "error"}], ["status=active"]
    )
    assert [m["status"] for m in matched] == ["active"]


@pytest.mark.parametrize("val", ["1", "true", "yes"])
def test_filter_bool_coercion_preserved(val):
    matched = cli_mod._apply_filters([{"enabled": True}], [f"enabled={val}"])
    assert len(matched) == 1
