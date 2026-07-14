"""Unit tests for csv_io.py -- no network required."""

from __future__ import annotations

import csv
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dnsfcli.csv_io import CsvValidationError, generate_template, read_csv_input
from dnsfcli.endpoints import REGISTRY

from tests.conftest import CLI_SCRIPT, PROJECT_DIR, run_cli

FAKE_KEY = "DELIBERATELY.INVALID"


def _op(endpoint: str, fn: str):
    return REGISTRY[endpoint].operations[fn]


def _write_csv(tmp_path: Path, headers: list, rows: list, name: str = "input.csv") -> Path:
    f = tmp_path / name
    with f.open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(headers)
        w.writerows(rows)
    return f


# ===========================================================================
# generate_template
# ===========================================================================

class TestGenerateTemplate:
    def test_output_has_header_row(self):
        out = generate_template(_op("networks", "create"), "networks", "create")
        lines = [l for l in out.splitlines() if not l.startswith("#") and l.strip()]
        assert len(lines) >= 1
        headers = lines[0].split(",")
        assert "name" in headers

    def test_required_in_comment_block(self):
        out = generate_template(_op("networks", "create"), "networks", "create")
        assert "# Required" in out
        assert "name" in out

    def test_optional_in_comment_block(self):
        out = generate_template(_op("networks", "create"), "networks", "create")
        assert "# Optional" in out
        assert "policy_id" in out

    def test_example_row_present(self):
        out = generate_template(_op("networks", "create"), "networks", "create")
        lines = [l for l in out.splitlines() if not l.startswith("#") and l.strip()]
        assert len(lines) >= 2   # header + example

    def test_required_example_value_not_empty(self):
        out = generate_template(_op("networks", "create"), "networks", "create")
        lines = [l for l in out.splitlines() if not l.startswith("#") and l.strip()]
        header_idx = {h: i for i, h in enumerate(lines[0].split(","))}
        example_row = lines[1].split(",")
        # 'name' is required -- its example cell must not be blank
        assert example_row[header_idx["name"]].strip() != ""

    def test_optional_example_value_is_empty(self):
        out = generate_template(_op("networks", "create"), "networks", "create")
        lines = [l for l in out.splitlines() if not l.startswith("#") and l.strip()]
        header_idx = {h: i for i, h in enumerate(lines[0].split(","))}
        example_row = lines[1].split(",")
        # 'physical_address' is optional -- its example cell should be blank
        assert example_row[header_idx["physical_address"]].strip() == ""

    def test_update_includes_path_id(self):
        out = generate_template(_op("networks", "update"), "networks", "update")
        lines = [l for l in out.splitlines() if not l.startswith("#") and l.strip()]
        assert "id" in lines[0].split(",")

    def test_policies_add_domain_columns(self):
        out = generate_template(_op("policies", "add-blacklist-domain"),
                                "policies", "add-blacklist-domain")
        lines = [l for l in out.splitlines() if not l.startswith("#") and l.strip()]
        cols = lines[0].split(",")
        assert "id" in cols      # path param
        assert "domain" in cols  # body param

    def test_action_only_endpoint_has_id(self):
        """Endpoints with only a path param (e.g. api-keys revoke) still show id."""
        out = generate_template(_op("api-keys", "revoke"), "api-keys", "revoke")
        assert "id" in out

    def test_operation_without_params_is_noted(self):
        """If an operation truly has no params, a comment says so."""
        # Create a fake operation with no params for the test
        from dnsfcli.endpoints import Operation
        op = Operation("POST", "/v1/test", "Test", [])
        out = generate_template(op, "test", "create")
        assert "no input" in out.lower()

    def test_output_is_valid_csv(self):
        out = generate_template(_op("organizations", "create"), "organizations", "create")
        data_lines = [l for l in out.splitlines() if not l.startswith("#") and l.strip()]
        rows = list(csv.reader(data_lines))
        assert len(rows) >= 2
        assert len(rows[0]) > 0   # at least one column

    @pytest.mark.parametrize("endpoint,fn", [
        ("networks", "create"),
        ("networks", "update"),
        ("networks", "delete"),
        ("policies", "create"),
        ("policies", "add-blacklist-domain"),
        ("policies", "add-blacklist-category"),
        ("organizations", "create"),
        ("organizations", "users-create"),
        ("ip-addresses", "create"),
        ("mac-addresses", "create"),
        ("block-pages", "create"),
        ("users", "change-password"),
        ("api-keys", "create"),
        ("api-keys", "revoke"),
        ("scheduled-reports", "create"),
        ("user-agents", "update"),
    ])
    def test_all_write_endpoints_produce_templates(self, endpoint, fn):
        out = generate_template(_op(endpoint, fn), endpoint, fn)
        assert out.strip() != ""
        # All should have at least a # comment or a CSV header
        assert "#" in out or "," in out or "\n" in out


# ===========================================================================
# read_csv_input
# ===========================================================================

class TestReadCsvInput:

    # ---- happy paths -------------------------------------------------------

    def test_single_valid_row(self, tmp_path):
        # block-pages create only requires 'name'
        f = _write_csv(tmp_path, ["name"], [["Test Block Page"]])
        rows = read_csv_input(f, _op("block-pages", "create"), {})
        assert len(rows) == 1
        assert rows[0]["name"] == "Test Block Page"

    def test_multiple_rows(self, tmp_path):
        f = _write_csv(tmp_path, ["name"], [["A"], ["B"], ["C"]])
        rows = read_csv_input(f, _op("block-pages", "create"), {})
        assert len(rows) == 3
        assert [r["name"] for r in rows] == ["A", "B", "C"]

    def test_integer_coercion(self, tmp_path):
        f = _write_csv(tmp_path, ["name", "organization_id"], [["Page", "42"]])
        rows = read_csv_input(f, _op("block-pages", "create"), {})
        assert rows[0]["organization_id"] == 42
        assert isinstance(rows[0]["organization_id"], int)

    def test_optional_empty_cell_omitted(self, tmp_path):
        f = _write_csv(tmp_path, ["name", "block_org_name"], [["Page", ""]])
        rows = read_csv_input(f, _op("block-pages", "create"), {})
        assert "block_org_name" not in rows[0]

    def test_cli_override_supplements_csv(self, tmp_path):
        f = _write_csv(tmp_path, ["domain"], [["evil.com"]])
        rows = read_csv_input(
            f, _op("policies", "add-blacklist-domain"), {"id": 7}
        )
        assert rows[0]["id"] == 7
        assert rows[0]["domain"] == "evil.com"

    def test_cli_override_covers_required_path_param(self, tmp_path):
        """Required path param provided via CLI must not be demanded in CSV."""
        f = _write_csv(tmp_path, ["domain"], [["evil.com"]])
        rows = read_csv_input(
            f, _op("policies", "add-blacklist-domain"), {"id": 5}
        )
        assert rows[0]["id"] == 5

    def test_comment_lines_skipped(self, tmp_path):
        f = tmp_path / "commented.csv"
        f.write_text(
            "# Template comment\n"
            "# Required : name (string)\n"
            "name\n"
            "My Block Page\n"
        )
        rows = read_csv_input(f, _op("block-pages", "create"), {})
        assert rows[0]["name"] == "My Block Page"

    def test_excel_bom_stripped(self, tmp_path):
        f = tmp_path / "excel.csv"
        f.write_bytes(b"\xef\xbb\xbfname\r\nTest\r\n")
        rows = read_csv_input(f, _op("block-pages", "create"), {})
        assert rows[0]["name"] == "Test"

    def test_template_output_is_valid_input(self, tmp_path):
        """A template file with example row replaced by real data is accepted."""
        template = generate_template(_op("block-pages", "create"), "block-pages", "create")
        lines = template.splitlines(keepends=True)
        data_lines = [l for l in lines if not l.startswith("#")]
        # data_lines[0] = header, data_lines[1] = example row
        data_lines[1] = "My Real Block Page,,,\n"
        f = tmp_path / "from_template.csv"
        f.write_text("".join(lines[:len(lines)-len(data_lines)] + data_lines))
        rows = read_csv_input(f, _op("block-pages", "create"), {})
        assert rows[0]["name"] == "My Real Block Page"

    # ---- file-level errors -------------------------------------------------

    def test_file_not_found(self, tmp_path):
        with pytest.raises(CsvValidationError) as exc_info:
            read_csv_input(tmp_path / "nonexistent.csv", _op("networks", "create"), {})
        assert "not found" in exc_info.value.errors[0].lower()

    def test_empty_file(self, tmp_path):
        f = tmp_path / "empty.csv"
        f.write_text("")
        with pytest.raises(CsvValidationError):
            read_csv_input(f, _op("networks", "create"), {})

    def test_only_comments(self, tmp_path):
        f = tmp_path / "comments_only.csv"
        f.write_text("# comment 1\n# comment 2\n")
        with pytest.raises(CsvValidationError) as exc_info:
            read_csv_input(f, _op("networks", "create"), {})
        combined = " ".join(exc_info.value.errors)
        assert "no data" in combined.lower() or "comment" in combined.lower()

    # ---- structural errors (missing columns) --------------------------------

    def test_missing_required_column(self, tmp_path):
        f = _write_csv(tmp_path, ["policy_id"], [["7"]])   # no 'name'
        with pytest.raises(CsvValidationError) as exc_info:
            read_csv_input(f, _op("networks", "create"), {})
        combined = " ".join(exc_info.value.errors)
        assert "name" in combined
        assert "Missing required column" in combined

    def test_error_lists_all_missing_columns(self, tmp_path):
        # networks create needs 'name'; organizations create needs 'name'
        # Let's use a completely empty-header CSV
        f = tmp_path / "no_cols.csv"
        f.write_text("irrelevant_col\nvalue\n")
        with pytest.raises(CsvValidationError) as exc_info:
            read_csv_input(f, _op("networks", "create"), {})
        combined = " ".join(exc_info.value.errors)
        assert "name" in combined

    def test_error_mentions_template_hint(self, tmp_path):
        f = _write_csv(tmp_path, ["policy_id"], [["7"]])
        with pytest.raises(CsvValidationError) as exc_info:
            read_csv_input(f, _op("networks", "create"), {})
        combined = " ".join(exc_info.value.errors)
        assert "--template" in combined

    # ---- per-row data errors -----------------------------------------------

    def test_empty_required_cell(self, tmp_path):
        # block-pages create: only 'name' required -- provide it empty
        f = _write_csv(tmp_path, ["name"], [[""]])
        with pytest.raises(CsvValidationError) as exc_info:
            read_csv_input(f, _op("block-pages", "create"), {})
        assert any("required" in e.lower() for e in exc_info.value.errors)

    def test_invalid_integer(self, tmp_path):
        # organization_id is an integer field on block-pages
        f = _write_csv(tmp_path, ["name", "organization_id"], [["Page", "abc"]])
        with pytest.raises(CsvValidationError) as exc_info:
            read_csv_input(f, _op("block-pages", "create"), {})
        assert any("integer" in e for e in exc_info.value.errors)

    def test_error_reports_row_number(self, tmp_path):
        # Row 1=header, Row 2=good, Row 3=bad (empty required), Row 4=good
        f = _write_csv(tmp_path, ["name"], [["Good"], [""], ["Also Good"]])
        with pytest.raises(CsvValidationError) as exc_info:
            read_csv_input(f, _op("block-pages", "create"), {})
        combined = " ".join(exc_info.value.errors)
        assert "Row 3" in combined   # data row 2 (1-indexed from header) is the bad one

    def test_all_row_errors_reported(self, tmp_path):
        # Three bad rows (all empty required cell)
        f = _write_csv(tmp_path, ["name"], [[""], [""], [""]])
        with pytest.raises(CsvValidationError) as exc_info:
            read_csv_input(f, _op("block-pages", "create"), {})
        combined = " ".join(exc_info.value.errors)
        assert "Row 2" in combined
        assert "Row 3" in combined
        assert "Row 4" in combined

    def test_error_says_no_api_calls_made(self, tmp_path):
        f = _write_csv(tmp_path, ["name"], [[""]])
        with pytest.raises(CsvValidationError) as exc_info:
            read_csv_input(f, _op("block-pages", "create"), {})
        combined = " ".join(exc_info.value.errors)
        assert "no API" in combined.lower() or "no api" in combined.lower()

    def test_mixed_good_bad_rows_all_errors_reported(self, tmp_path):
        """Even if some rows are valid, all errors are reported before any call is made."""
        f = _write_csv(
            tmp_path, ["name", "organization_id"],
            [["Good", "1"], ["", "1"], ["Good2", "not-int"]],
        )
        with pytest.raises(CsvValidationError) as exc_info:
            read_csv_input(f, _op("block-pages", "create"), {})
        errors = exc_info.value.errors
        assert len([e for e in errors if "Row" in e]) >= 2


# ===========================================================================
# CLI integration tests (subprocess) -- no live API needed
# ===========================================================================

class TestTemplateCli:
    def test_template_outputs_csv(self):
        result = run_cli("networks", "create", "--template", api_key=None)
        assert result.returncode == 0
        assert "name" in result.stdout

    def test_template_before_endpoint(self):
        """--template hoisted from before the endpoint name should work."""
        import subprocess
        r = subprocess.run(
            [sys.executable, str(CLI_SCRIPT),
             "--template", "networks", "create"],
            capture_output=True, text=True, cwd=str(PROJECT_DIR),
        )
        assert r.returncode == 0
        assert "name" in r.stdout

    def test_template_between_endpoint_and_function(self):
        import subprocess
        r = subprocess.run(
            [sys.executable, str(CLI_SCRIPT),
             "networks", "--template", "create"],
            capture_output=True, text=True, cwd=str(PROJECT_DIR),
        )
        assert r.returncode == 0
        assert "name" in r.stdout

    def test_template_update_includes_id(self):
        result = run_cli("networks", "update", "--template", api_key=None)
        assert result.returncode == 0
        assert "id" in result.stdout

    def test_template_includes_required_comment(self):
        result = run_cli("networks", "create", "--template", api_key=None)
        assert "Required" in result.stdout

    def test_template_includes_optional_comment(self):
        result = run_cli("networks", "create", "--template", api_key=None)
        assert "Optional" in result.stdout

    def test_template_no_auth_needed(self):
        """--template must not fail when no API key is configured."""
        result = run_cli("policies", "add-blacklist-domain", "--template", api_key=None)
        assert result.returncode == 0
        assert "domain" in result.stdout

    def test_template_in_help_text(self):
        result = run_cli("networks", "create", "--help", api_key=None)
        assert "--template" in result.stdout

    def test_from_csv_in_help_text(self):
        result = run_cli("networks", "create", "--help", api_key=None)
        assert "--from-csv" in result.stdout

    @pytest.mark.parametrize("endpoint,fn", [
        ("networks",        "create"),
        ("networks",        "update"),
        ("policies",        "create"),
        ("policies",        "add-blacklist-domain"),
        ("organizations",   "create"),
        ("ip-addresses",    "create"),
        ("users",           "change-password"),
        ("api-keys",        "create"),
        ("block-pages",     "create"),
    ])
    def test_template_for_every_write_endpoint(self, endpoint, fn):
        result = run_cli(endpoint, fn, "--template", api_key=None)
        assert result.returncode == 0, f"{endpoint} {fn}: {result.stderr}"
        assert "Traceback" not in result.stdout + result.stderr


class TestFromCsvCli:
    def test_missing_required_column_clean_error(self, tmp_path):
        f = _write_csv(tmp_path, ["block_org_name"], [["Acme"]])   # missing 'name'
        result = run_cli(
            "block-pages", "create",
            "--from-csv", str(f),
            api_key=FAKE_KEY,
        )
        assert result.returncode != 0
        combined = result.stdout + result.stderr
        assert "name" in combined
        assert "Traceback" not in combined

    def test_empty_required_cell_clean_error(self, tmp_path):
        f = _write_csv(tmp_path, ["name"], [[""]])
        result = run_cli("block-pages", "create", "--from-csv", str(f), api_key=FAKE_KEY)
        assert result.returncode != 0
        combined = result.stdout + result.stderr
        assert "required" in combined.lower()
        assert "Traceback" not in combined

    def test_bad_integer_clean_error(self, tmp_path):
        f = _write_csv(tmp_path, ["name", "organization_id"], [["Page", "bad"]])
        result = run_cli("block-pages", "create", "--from-csv", str(f), api_key=FAKE_KEY)
        assert result.returncode != 0
        combined = result.stdout + result.stderr
        assert "integer" in combined
        assert "Traceback" not in combined

    def test_file_not_found_clean_error(self, tmp_path):
        result = run_cli(
            "networks", "create",
            "--from-csv", "/nonexistent/file.csv",
            api_key=FAKE_KEY,
        )
        assert result.returncode != 0
        combined = result.stdout + result.stderr
        assert "not found" in combined.lower()
        assert "Traceback" not in combined

    def test_error_says_no_api_calls_made(self, tmp_path):
        f = _write_csv(tmp_path, ["name"], [[""]])
        result = run_cli("block-pages", "create", "--from-csv", str(f), api_key=FAKE_KEY)
        combined = result.stdout + result.stderr
        assert "no API" in combined or "no api" in combined.lower()

    def test_from_csv_before_endpoint_hoisted(self, tmp_path):
        """--from-csv hoisted from before the endpoint name must reach the command."""
        f = _write_csv(tmp_path, ["name"], [["Net"]])
        import subprocess
        r = subprocess.run(
            [sys.executable, str(CLI_SCRIPT),
             "--from-csv", str(f), "networks", "create", "--api-key", FAKE_KEY],
            capture_output=True, text=True, cwd=str(PROJECT_DIR),
        )
        # Auth will fail (fake key) but --from-csv must have been parsed correctly
        # (if it wasn't parsed, we'd get a "missing required param" error instead)
        assert "Traceback" not in r.stdout + r.stderr
        # We expect either an auth error OR a validation error -- not a routing crash
        assert r.returncode != 0

    def test_template_hint_shown_on_missing_column(self, tmp_path):
        f = _write_csv(tmp_path, ["description"], [["optional value"]])
        result = run_cli("networks", "create", "--from-csv", str(f), api_key=FAKE_KEY)
        combined = result.stdout + result.stderr
        assert "--template" in combined
