"""CSV input processing and blank template generation for write operations.

Usage patterns
--------------
  # Print a blank template, fill it in, then import:
  dnsfcli networks create --template > networks.csv
  dnsfcli networks create --from-csv networks.csv

  # Supply path params via CLI, body params via CSV:
  dnsfcli policies add-blacklist-domain --id 7 --from-csv domains.csv

  # Combine with --to-csv to save the API responses:
  dnsfcli networks create --from-csv networks.csv --to-csv results.csv

Template files
--------------
  Generated templates include # comment lines documenting required /
  optional fields.  read_csv_input() silently skips these lines, so the
  file can be fed straight back to --from-csv after the user fills it in.
  UTF-8 BOM (common in Excel exports) is also stripped automatically.
"""

from __future__ import annotations

import csv
import io
from pathlib import Path
from typing import Any

from .endpoints import Operation, Param


# ---------------------------------------------------------------------------
# Path safety
# ---------------------------------------------------------------------------

def _warn_if_traversal(filepath: str | Path) -> None:
    """Warn when a path contains '..' components.

    dnsfcli accepts any file path the running user can access.  This is
    intentional for interactive use, but automated pipelines that construct
    paths from external input should sanitize those values before passing
    them here — dnsfcli performs no containment of its own.
    """
    if ".." in Path(filepath).parts:
        import sys as _sys
        # Import here to avoid a circular import (csv_io ← output ← csv_io).
        from rich.console import Console
        _warn_console = Console(stderr=True)
        _warn_console.print(
            f"[bold yellow]Warning:[/bold yellow] Path contains '..' components: "
            f"[bold]{filepath}[/bold]\n"
            "If this path was constructed from external input, abort and sanitize it first.\n"
            "Pass [bold]--yes[/bold] to suppress this warning and proceed."
        )
        # Block in non-interactive (piped) contexts unless explicitly confirmed.
        if not _sys.stdin.isatty():
            _warn_console.print("[bold red]Aborting:[/bold red] path traversal detected in non-interactive mode.")
            _sys.exit(1)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_HINT_EXAMPLES: dict[str, str] = {
    "string":  "example text",
    "integer": "1",
    "boolean": "true",
    "array":   '["item1","item2"]',
    "object":  '{"key":"value"}',
}


def _example(p: Param) -> str:
    """Return an illustrative sample value for *p* (empty string for optional)."""
    if not p.required:
        return ""
    return _HINT_EXAMPLES.get(p.type_hint, "example")


def _template_params(operation: Operation) -> list[Param]:
    """Ordered column list for a template: path params first, then body params."""
    return (
        [p for p in operation.params if p.kind == "path"]
        + [p for p in operation.params if p.kind == "body"]
    )


# ---------------------------------------------------------------------------
# Template generation
# ---------------------------------------------------------------------------

def generate_template(operation: Operation, endpoint: str, function: str) -> str:
    """Return a ready-to-use CSV template string.

    The output has three sections:
      1. ``# comment`` lines naming required / optional columns and their types.
      2. A header row of column names.
      3. One example row (required fields get placeholder values; optional ones
         are left blank).

    ``read_csv_input`` silently ignores lines that start with ``#``, so the
    file can be fed back to ``--from-csv`` after the user fills it in.
    """
    params = _template_params(operation)
    if not params:
        return f"# dnsfcli {endpoint} {function}: no input parameters required\n"

    required = [p for p in params if p.required]
    optional = [p for p in params if not p.required]

    buf = io.StringIO()
    buf.write(f"# Template : dnsfcli {endpoint} {function}\n")
    if required:
        buf.write(
            "# Required : "
            + ", ".join(f"{p.name} ({p.type_hint})" for p in required)
            + "\n"
        )
    if optional:
        buf.write(
            "# Optional : "
            + ", ".join(f"{p.name} ({p.type_hint})" for p in optional)
            + "\n"
        )

    # Fetch the stored org ID so the example row is immediately usable.
    # Falls back to the generic "1" placeholder if none is configured.
    real_org_id: str | None = None
    try:
        from .auth import get_org_id
        real_org_id = get_org_id()
    except Exception:
        pass

    def _example_cell(p: Param) -> str:
        if p.name == "organization_id" and real_org_id:
            return real_org_id
        return _example(p)

    writer = csv.writer(buf)
    writer.writerow([p.name for p in params])
    writer.writerow([_example_cell(p) for p in params])
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Validation error
# ---------------------------------------------------------------------------

class CsvValidationError(Exception):
    """Raised when a CSV file fails structural or per-row validation."""

    def __init__(self, filepath: str, errors: list[str]) -> None:
        self.filepath = filepath
        self.errors = errors
        super().__init__(f"{len(errors)} error(s) in {filepath}")


# ---------------------------------------------------------------------------
# Type coercion
# ---------------------------------------------------------------------------

def _coerce(value: str, param: Param) -> Any:
    """Convert a raw CSV cell string to the expected Python type.

    Raises ``ValueError`` with a human-readable message on bad input.

    Arrays may be expressed as:
      - JSON:             ``["a","b","c"]``
      - Comma-separated:  ``a,b,c``   (each element is trimmed)
    """
    import json as _json

    stripped = value.strip()
    if param.type_hint == "integer":
        try:
            return int(stripped)
        except ValueError:
            raise ValueError(f"expected an integer, got {stripped!r}")
    if param.type_hint == "boolean":
        return stripped.lower() in ("1", "true", "yes", "on")
    if param.type_hint in ("array", "object"):
        # Try JSON first
        if stripped.startswith(("[", "{")):
            try:
                return _json.loads(stripped)
            except _json.JSONDecodeError:
                raise ValueError(f"expected valid JSON array/object, got {stripped!r}")
        # Comma-separated fallback for arrays
        if param.type_hint == "array":
            return [item.strip() for item in stripped.split(",") if item.strip()]
        raise ValueError(f"expected a JSON object, got {stripped!r}")
    return stripped


# ---------------------------------------------------------------------------
# CSV reader + validator
# ---------------------------------------------------------------------------

def read_csv_input(
    filepath: str | Path,
    operation: Operation,
    cli_overrides: dict[str, Any],
    delimiter: str = ",",
) -> list[dict[str, Any]]:
    """Read *filepath* and validate every row against *operation*'s parameters.

    Pass ``"-"`` as *filepath* to read from stdin.

    *cli_overrides* contains params already supplied on the command line.
    They supplement (and take priority over) CSV columns, so callers can do:

        --id 7 --from-csv domains.csv

    where ``id`` is provided once on the CLI and ``domain`` comes per-row.

    Returns a list of merged param dicts (one per data row) -- each ready
    to be split into path / query / body params and sent to the API.

    Raises :class:`CsvValidationError` with detailed messages on any of:
      - file not found / empty
      - missing required columns
      - bad per-row values (empty required cell, wrong type, …)

    **No API calls are made here.**
    """
    # ---- stdin support -------------------------------------------------------
    if str(filepath) == "-":
        import sys
        import tempfile
        content = sys.stdin.read()
        if not content.strip():
            raise CsvValidationError("-", ["No data received on stdin"])
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, encoding="utf-8") as tmp:
            tmp.write(content)
            filepath = tmp.name

    _warn_if_traversal(filepath)
    path = Path(filepath)

    # ---- file-level checks --------------------------------------------------
    if not path.exists():
        raise CsvValidationError(str(filepath), [f"File not found: {filepath}"])
    if path.stat().st_size == 0:
        raise CsvValidationError(str(filepath), ["File is empty"])

    # Strip UTF-8 BOM (Excel), skip blank lines and # comments
    raw_lines: list[str] = []
    with path.open(encoding="utf-8-sig") as fh:
        for line in fh:
            stripped = line.rstrip("\n\r")
            if stripped.lstrip().startswith("#") or not stripped.strip():
                continue
            raw_lines.append(stripped)

    if not raw_lines:
        raise CsvValidationError(str(filepath), [
            "File contains no data rows (only comments or blank lines)",
            "Run with --template to see the expected format",
        ])

    reader = csv.DictReader(raw_lines, delimiter=delimiter)
    if not reader.fieldnames:
        raise CsvValidationError(str(filepath), [
            "Could not parse a header row from the CSV",
            "Ensure the first non-comment line contains column names",
        ])

    # Normalise common column name aliases so users can supply familiar names
    # (e.g. 'fqdns', 'notes', 'url') without needing to rename their headers.
    _COL_ALIASES: dict[str, str] = {
        "fqdns":   "domain",   # policies add/remove domain
        "fqdn":    "domain",   # policies add/remove domain
        "url":     "domain",   # common alias
        "notes":   "note",     # policies add/remove domain
        "reason":  "note",     # common alias for note
    }
    original_fieldnames = list(reader.fieldnames)
    normalised_fieldnames = [
        _COL_ALIASES.get(h.strip(), h.strip()) for h in original_fieldnames
    ]
    if normalised_fieldnames != [h.strip() for h in original_fieldnames]:
        # Rebuild the reader with normalised headers by patching the fieldnames
        reader.fieldnames = normalised_fieldnames  # type: ignore[assignment]

    csv_headers: set[str] = set(normalised_fieldnames)

    # ---- structural validation (column presence) ----------------------------
    param_map: dict[str, Param] = {p.name: p for p in operation.params}
    required_names: set[str] = {
        p.name for p in operation.params
        if p.required and p.kind in ("body", "path")
    }
    # Required params not covered by CLI flags AND absent from CSV headers
    uncovered = required_names - set(cli_overrides.keys()) - csv_headers

    if uncovered:
        all_writeable = [p for p in operation.params if p.kind in ("body", "path")]
        req_list = ", ".join(
            f"{p.name} ({p.type_hint})" for p in all_writeable if p.required
        )
        opt_list = ", ".join(
            f"{p.name} ({p.type_hint})" for p in all_writeable if not p.required
        )
        errors: list[str] = [
            f"Missing required column(s): {', '.join(sorted(uncovered))}",
        ]
        if req_list:
            errors.append(f"  Required columns : {req_list}")
        if opt_list:
            errors.append(f"  Optional columns : {opt_list}")
        errors.append("  Run with --template to generate a blank example CSV")
        errors.append("\n  No API calls were made")
        raise CsvValidationError(str(filepath), errors)

    _CTX_KEYS = ("name", "id", "email", "address", "fqdn", "domain")

    def _row_ctx(row: dict[str, Any]) -> str:
        parts = [f"{k}={row[k]!r}" for k in _CTX_KEYS if row.get(k)]
        return f" [{', '.join(parts[:2])}]" if parts else ""

    # ---- per-row validation -------------------------------------------------
    valid_rows: list[dict[str, Any]] = []
    row_errors: list[str] = []

    for row_num, raw_row in enumerate(reader, start=2):  # row 1 is the header
        row_params: dict[str, Any] = dict(cli_overrides)   # CLI values win
        row_errs: list[str] = []

        for header_raw in (reader.fieldnames or []):
            header = header_raw.strip()
            cell = (raw_row.get(header_raw) or "").strip()
            param = param_map.get(header)

            if not cell:
                # Empty cell -- only an error when required and not in CLI
                if param and param.required and header not in cli_overrides:
                    row_errs.append(
                        f"  Row {row_num}: '{header}' is required but empty"
                    )
                continue  # skip empty optional fields

            if param:
                try:
                    row_params[header] = _coerce(cell, param)
                except ValueError as exc:
                    row_errs.append(f"  Row {row_num}: '{header}' -- {exc}")
                    continue
            else:
                row_params[header] = cell   # unknown column, pass through as-is

        if row_errs:
            ctx = _row_ctx(row_params)
            row_errors.extend(e + ctx for e in row_errs)
        else:
            valid_rows.append(row_params)

    if row_errors:
        summary = (
            f"\n  {len(row_errors)} error(s) found across "
            f"{sum(1 for e in row_errors if e.strip().startswith('Row'))} row(s) "
            f"-- no API calls were made"
        )
        raise CsvValidationError(str(filepath), row_errors + [summary])

    if not valid_rows:
        raise CsvValidationError(str(filepath), [
            "No valid data rows found after validation"
        ])

    return valid_rows
