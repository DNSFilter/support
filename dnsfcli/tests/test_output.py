"""Unit tests for output.py -- no network required."""

from __future__ import annotations

import json
import sys
from io import StringIO
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dnsfcli.output import (
    _cell_str,
    _csv_cell,
    _flatten_kv,
    _rows_for_csv,
    _scalar_str,
    _unwrap,
    print_response,
    write_csv,
)


# ---------------------------------------------------------------------------
# _scalar_str
# ---------------------------------------------------------------------------

class TestScalarStr:
    def test_none(self):
        assert _scalar_str(None) == "[dim]-[/dim]"

    def test_true(self):
        assert _scalar_str(True) == "[green]yes[/green]"

    def test_false(self):
        assert _scalar_str(False) == "[red]no[/red]"

    def test_integer(self):
        assert _scalar_str(42) == "42"

    def test_string(self):
        assert _scalar_str("hello") == "hello"

    def test_float(self):
        assert _scalar_str(3.14) == "3.14"


# ---------------------------------------------------------------------------
# _cell_str
# ---------------------------------------------------------------------------

class TestCellStr:
    def test_none(self):
        assert _cell_str(None) == "[dim]-[/dim]"

    def test_bool_true(self):
        assert _cell_str(True) == "[green]yes[/green]"

    def test_bool_false(self):
        assert _cell_str(False) == "[red]no[/red]"

    def test_scalar_int(self):
        assert _cell_str(7) == "7"

    def test_empty_dict(self):
        assert _cell_str({}) == "[dim](empty)[/dim]"

    def test_empty_list(self):
        assert _cell_str([]) == "[dim](empty)[/dim]"

    def test_dict_summary(self):
        result = _cell_str({"name": "HQ", "enabled": True})
        assert "name=HQ" in result
        assert "enabled=" in result

    def test_dict_summary_truncated(self):
        # A dict with many long keys should be truncated to <= max_len + ellipsis
        big = {f"key_{i}": f"value_{i}" for i in range(20)}
        result = _cell_str(big, max_len=30)
        assert "…" in result

    def test_list_of_scalars(self):
        result = _cell_str(["a", "b", "c"])
        assert "a" in result and "b" in result and "c" in result

    def test_list_of_scalars_truncated(self):
        long_list = [str(i) for i in range(100)]
        result = _cell_str(long_list, max_len=10)
        assert "…" in result

    def test_list_of_dicts_shows_count(self):
        result = _cell_str([{"id": 1}, {"id": 2}, {"id": 3}])
        assert "3" in result
        assert "item" in result

    def test_list_of_dicts_singular(self):
        result = _cell_str([{"id": 1}])
        assert "1 item" in result


# ---------------------------------------------------------------------------
# _flatten_kv
# ---------------------------------------------------------------------------

class TestFlattenKv:
    def test_flat_dict(self):
        pairs = dict(_flatten_kv({"a": 1, "b": 2}))
        assert pairs == {"a": 1, "b": 2}

    def test_nested_dict(self):
        pairs = dict(_flatten_kv({"outer": {"inner": 42}}))
        assert pairs == {"outer.inner": 42}

    def test_deeply_nested(self):
        pairs = dict(_flatten_kv({"a": {"b": {"c": "deep"}}}))
        assert pairs == {"a.b.c": "deep"}

    def test_list_kept_as_is(self):
        pairs = dict(_flatten_kv({"tags": ["x", "y"]}))
        assert pairs == {"tags": ["x", "y"]}

    def test_list_of_dicts_kept_as_is(self):
        val = [{"id": 1}, {"id": 2}]
        pairs = dict(_flatten_kv({"items": val}))
        assert pairs == {"items": val}

    def test_empty_dict_keeps_key(self):
        pairs = dict(_flatten_kv({"meta": {}}))
        assert "meta" in pairs


# ---------------------------------------------------------------------------
# _unwrap
# ---------------------------------------------------------------------------

class TestUnwrap:
    def test_passthrough_non_dict(self):
        assert _unwrap([1, 2, 3]) == [1, 2, 3]
        assert _unwrap("string") == "string"
        assert _unwrap(None) is None

    def test_standard_data_envelope(self):
        result = _unwrap({"data": [{"id": 1}]})
        assert result == [{"id": 1}]

    def test_standard_results_envelope(self):
        result = _unwrap({"results": [{"id": 2}]})
        assert result == [{"id": 2}]

    def test_resource_name_wrap(self):
        result = _unwrap({"networks": [{"id": 1}, {"id": 2}], "meta": {"total": 2}})
        assert result == [{"id": 1}, {"id": 2}]

    def test_resource_name_wrap_no_meta(self):
        result = _unwrap({"policies": [{"id": 5}]})
        assert result == [{"id": 5}]

    def test_no_envelope_single_resource(self):
        # Dict with multiple non-meta keys should NOT be unwrapped
        obj = {"id": 1, "name": "HQ", "policy_id": 7}
        assert _unwrap(obj) is obj

    def test_meta_only_is_not_unwrapped(self):
        # All keys are meta keys -- should return as-is
        obj = {"meta": {"total": 0}}
        assert _unwrap(obj) is obj


# ---------------------------------------------------------------------------
# print_response (smoke tests via captured stdout)
# ---------------------------------------------------------------------------

class TestPrintResponse:
    def _capture(self, data, csv_file: str | None = None, **kwargs) -> str:
        """Run print_response and return its rich-stripped text output."""
        from rich.console import Console
        import dnsfcli.output as out_mod

        buf = StringIO()
        old_console = out_mod.console
        out_mod.console = Console(file=buf, highlight=False, markup=False)
        try:
            if csv_file:
                from dnsfcli.output import write_csv
                write_csv(data, csv_file)
            else:
                print_response(data, **kwargs)
        finally:
            out_mod.console = old_console
        return buf.getvalue()

    def test_none_response(self):
        output = self._capture(None)
        assert "no content" in output.lower()

    def test_raw_produces_json(self):
        output = self._capture({"id": 1, "name": "test"}, raw=True)
        parsed = json.loads(output.strip())
        assert parsed["id"] == 1

    def test_single_resource_shows_keys(self):
        output = self._capture({"id": 42, "name": "HQ", "enabled": True})
        assert "id" in output
        assert "42" in output
        assert "HQ" in output

    def test_nested_dict_flattened(self):
        output = self._capture({
            "id": 1,
            "settings": {"block_adult": True, "threshold": 90}
        })
        assert "settings.block_adult" in output
        assert "settings.threshold" in output
        assert "90" in output

    def test_list_response_shows_table(self):
        output = self._capture([
            {"id": 1, "name": "Alpha"},
            {"id": 2, "name": "Beta"},
        ])
        assert "Alpha" in output
        assert "Beta" in output
        assert "name" in output

    def test_resource_wrap_unwrapped(self):
        output = self._capture({
            "networks": [{"id": 1, "name": "HQ"}],
            "meta": {"total": 1}
        })
        assert "HQ" in output
        assert "Total: 1" in output

    def test_bool_shown_as_yes_no(self):
        output = self._capture({"active": True, "deleted": False})
        assert "yes" in output
        assert "no" in output

    def test_none_values_shown_as_dash(self):
        output = self._capture({"ip": None, "name": "Test"})
        assert "-" in output

    def test_empty_list_shown(self):
        output = self._capture({"tags": [], "name": "X"})
        assert "empty" in output.lower()

    def test_csv_flag_writes_file_not_stdout(self, tmp_path):
        out = tmp_path / "out.csv"
        output = self._capture([{"id": 1, "name": "A"}, {"id": 2, "name": "B"}], csv_file=str(out))
        # stdout should be empty (no table printed)
        assert "id" not in output
        assert out.exists()

    def test_nested_list_of_objects_is_subtable(self):
        output = self._capture({
            "id": 5,
            "blocked_categories": [{"id": 10, "name": "Adult"}, {"id": 11, "name": "Gambling"}]
        })
        assert "Adult" in output
        assert "Gambling" in output


# ---------------------------------------------------------------------------
# _csv_cell
# ---------------------------------------------------------------------------

class TestCsvCell:
    def test_none_is_empty_string(self):
        assert _csv_cell(None) == ""

    def test_bool_true(self):
        assert _csv_cell(True) == "true"

    def test_bool_false(self):
        assert _csv_cell(False) == "false"

    def test_integer(self):
        assert _csv_cell(42) == "42"

    def test_string(self):
        assert _csv_cell("hello") == "hello"

    def test_dict_is_compact_json(self):
        result = _csv_cell({"a": 1})
        assert result == '{"a":1}'

    def test_list_is_compact_json(self):
        result = _csv_cell([1, 2, 3])
        assert result == "[1,2,3]"


# ---------------------------------------------------------------------------
# _rows_for_csv
# ---------------------------------------------------------------------------

class TestRowsForCsv:
    def test_list_of_dicts(self):
        headers, rows = _rows_for_csv([{"id": 1, "name": "A"}, {"id": 2, "name": "B"}])
        assert headers == ["id", "name"]
        assert rows == [["1", "A"], ["2", "B"]]

    def test_single_resource(self):
        headers, rows = _rows_for_csv({"id": 99, "name": "X", "active": True})
        assert "id" in headers
        assert "active" in headers
        assert len(rows) == 1
        assert "true" in rows[0]

    def test_nested_dict_flattened(self):
        headers, rows = _rows_for_csv({"id": 1, "settings": {"block": True, "level": 5}})
        assert "settings.block" in headers
        assert "settings.level" in headers

    def test_empty_list(self):
        headers, rows = _rows_for_csv([])
        assert rows == []

    def test_list_of_scalars(self):
        headers, rows = _rows_for_csv(["a", "b", "c"])
        assert headers == ["value"]
        assert rows == [["a"], ["b"], ["c"]]

    def test_scalar(self):
        headers, rows = _rows_for_csv("hello")
        assert headers == ["value"]
        assert rows == [["hello"]]

    def test_none_fields_are_empty_strings(self):
        headers, rows = _rows_for_csv([{"id": 1, "name": None}])
        assert rows[0][headers.index("name")] == ""

    def test_bool_fields_are_true_false(self):
        headers, rows = _rows_for_csv([{"active": True, "deleted": False}])
        assert rows[0][headers.index("active")] == "true"
        assert rows[0][headers.index("deleted")] == "false"

    def test_sparse_rows_padded(self):
        """When different rows have different keys, missing cells become empty."""
        data = [{"id": 1, "name": "A"}, {"id": 2, "extra": "only-on-second"}]
        headers, rows = _rows_for_csv(data)
        assert "extra" in headers
        extra_idx = headers.index("extra")
        assert rows[0][extra_idx] == ""      # first row has no "extra"
        assert rows[1][extra_idx] == "only-on-second"

    def test_resource_name_envelope_unwrapped(self):
        """A {"networks": [...], "meta": {...}} response should be unwrapped."""
        data = {"networks": [{"id": 1}, {"id": 2}], "meta": {"total": 2}}
        headers, rows = _rows_for_csv(data)
        assert "id" in headers
        assert len(rows) == 2


# ---------------------------------------------------------------------------
# write_csv (file I/O)
# ---------------------------------------------------------------------------

class TestWriteCsv:
    def test_creates_file(self, tmp_path):
        out = tmp_path / "out.csv"
        write_csv([{"id": 1}], out)
        assert out.exists()

    def test_row_count_returned(self, tmp_path):
        out = tmp_path / "out.csv"
        n = write_csv([{"id": 1}, {"id": 2}, {"id": 3}], out)
        assert n == 3

    def test_file_contents_valid_csv(self, tmp_path):
        out = tmp_path / "out.csv"
        write_csv([{"id": 1, "name": "HQ"}, {"id": 2, "name": "Branch"}], out)
        import csv as csv_mod
        with out.open() as f:
            reader = list(csv_mod.reader(f))
        assert reader[0] == ["id", "name"]
        assert reader[1] == ["1", "HQ"]
        assert reader[2] == ["2", "Branch"]

    def test_single_resource_one_data_row(self, tmp_path):
        out = tmp_path / "out.csv"
        n = write_csv({"id": 5, "name": "Policy"}, out)
        assert n == 1
        import csv as csv_mod
        with out.open() as f:
            rows = list(csv_mod.reader(f))
        assert len(rows) == 2  # header + 1 data row

    def test_nested_dict_flattened_in_file(self, tmp_path):
        out = tmp_path / "out.csv"
        write_csv({"id": 1, "settings": {"block": True}}, out)
        import csv as csv_mod
        with out.open() as f:
            rows = list(csv_mod.reader(f))
        assert "settings.block" in rows[0]

    def test_empty_list_writes_only_header(self, tmp_path):
        out = tmp_path / "out.csv"
        n = write_csv([], out)
        assert n == 0
        content = out.read_text()
        assert len(content.strip().splitlines()) == 1

    def test_creates_parent_directories(self, tmp_path):
        nested = tmp_path / "a" / "b" / "out.csv"
        write_csv([{"id": 1}], nested)
        assert nested.exists()

    def test_string_filepath_accepted(self, tmp_path):
        out = str(tmp_path / "out.csv")
        write_csv([{"id": 1}], out)
        assert Path(out).exists()
