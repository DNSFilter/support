"""Rich-based output formatting for API responses.

Single resources   -> two-column key / value table, one row per leaf field.
                      Nested dicts are flattened to dotted keys (a.b.c: value).
                      Nested lists of primitives are comma-joined.
                      Nested lists of objects are expanded as sub-tables.

Lists of resources -> one row per resource, one column per top-level key.
                      Nested values in cells are summarised (never raw JSON).

CSV output         -> write_csv(data, path) flattens any response shape to a
                      standard RFC-4180 CSV file (headers on row 1).
"""

from __future__ import annotations

import csv
import json
import os
import re
import threading
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

# Serializes set_output_options so concurrent --parallel-orgs workers can't
# tear the console/err_console rebind.
_output_opts_lock = threading.Lock()

# Honour the NO_COLOR standard (https://no-color.org/) at import time.
_no_color: bool = bool(os.environ.get("NO_COLOR"))
_quiet: bool = False             # suppress success/info/warning chatter; data still prints
_quiet_ok: bool = False          # suppress success/info AND result data; keep warnings + errors
_suppress_data: bool = False     # --output none: print nothing at all
_truncate: int | None = None   # None → use the hardcoded default (60 chars)
_no_wrap: bool = False
_color_rules: list[tuple[str, str, str]] = []  # (field, value_regex, rich_style)
_color_scale: tuple[str, bool] | None = None   # (field, ascending) — gradient row coloring
_tee_path: str | None = None
_csv_null_value: str = ""        # written to CSV cells when value is None
_table_style: str | None = None  # Rich box style name for list tables (None = Rich default)
_log_fh: Any = None              # open file handle when --log-file is active

console = Console(no_color=_no_color)
err_console = Console(stderr=True, no_color=_no_color)


def _resolve_box(style: str) -> Any:
    """Map a style name to a rich.box constant (None = no border)."""
    import rich.box as _rb
    return {
        "rounded": _rb.ROUNDED, "simple": _rb.SIMPLE, "minimal": _rb.MINIMAL,
        "markdown": _rb.MARKDOWN, "horizontals": _rb.HORIZONTALS, "heavy": _rb.HEAVY,
        "double": _rb.DOUBLE, "ascii": _rb.ASCII, "none": None,
    }.get(style.lower(), _rb.ROUNDED)


def set_output_options(
    *,
    quiet: bool = False,
    no_color: bool = False,
    truncate: int | None = None,
    no_wrap: bool = False,
    color_rules: list[tuple[str, str, str]] | None = None,
    color_scale: str | None = None,
    tee: str | None = None,
    quiet_ok: bool = False,
    csv_null_value: str | None = None,
    table_style: str | None = None,
    log_file: str | None = None,
    suppress_data: bool = False,
) -> None:
    """Reconfigure module-level output flags.

    Call once early in app_entry(). It also runs once per --run inside
    _run_api_call; under --parallel-orgs that means concurrent worker threads
    may enter it at once, so the whole body is guarded by a lock to prevent a
    torn rebind of the shared console/err_console (a reader seeing a
    half-swapped pair). The arguments are invocation constants, so repeated
    calls converge on the same state.
    """
    with _output_opts_lock:
      _set_output_options_locked(
        quiet=quiet, no_color=no_color, truncate=truncate, no_wrap=no_wrap,
        color_rules=color_rules, color_scale=color_scale, tee=tee,
        quiet_ok=quiet_ok, csv_null_value=csv_null_value, table_style=table_style,
        log_file=log_file, suppress_data=suppress_data,
      )


def _set_output_options_locked(
    *, quiet, no_color, truncate, no_wrap, color_rules, color_scale, tee,
    quiet_ok, csv_null_value, table_style, log_file, suppress_data,
) -> None:
    # console/err_console are MUTATED in place, not reassigned, so they are
    # intentionally absent from this global declaration.
    global _quiet, _quiet_ok, _no_color, _truncate, _no_wrap, _color_rules, _color_scale, _tee_path, _csv_null_value, _table_style, _log_fh, _suppress_data
    _quiet = quiet or _quiet
    if suppress_data:
        _suppress_data = True
    _no_color = no_color or _no_color
    if quiet_ok:
        _quiet_ok = True
    if csv_null_value is not None:
        _csv_null_value = csv_null_value
    if table_style:
        _table_style = table_style
    if log_file:
        try:
            _log_fh = open(log_file, "a", encoding="utf-8")
        except OSError:
            _log_fh = None  # fall back to stderr if file can't be opened
        # (err_console.file is redirected below, in the in-place mutation block,
        #  so the imported err_console reference stays valid.)
    if no_wrap:
        _no_wrap = True
    if color_rules:
        _color_rules = color_rules
    if color_scale:
        _cs_raw = color_scale.strip()
        if ":" in _cs_raw:
            _cs_field, _cs_dir = _cs_raw.rsplit(":", 1)
            _color_scale = (_cs_field.strip(), _cs_dir.strip().lower() != "desc")
        else:
            _color_scale = (_cs_raw, True)
    if tee:
        _tee_path = tee
    if truncate is not None:
        # -1 means "no truncation" at the CLI level; store as None here
        _truncate = None if truncate < 0 else truncate

    # Mutate the EXISTING console objects in place rather than rebuilding and
    # rebinding them. Every module does `from .output import console,
    # err_console`, so those names must keep pointing at the same objects — an
    # in-place update is seen everywhere and needs no sys.modules trickery.
    # (record/no_color/file are all settable on a live rich.Console.)
    if _no_color:
        console.no_color = True
        err_console.no_color = True
    if _tee_path:
        console.record = True
    if _log_fh is not None:
        err_console.file = _log_fh
        err_console.no_color = True


_tee_raw: list[str] = []  # raw stdout text (--json/--jsonl/--pick) captured for --tee


def tee_write(text: str) -> None:
    """Record raw stdout text for --tee (modes that bypass the Rich console)."""
    if _tee_path:
        _tee_raw.append(text)


def flush_tee() -> None:
    """Write recorded console output to the --tee file (if set).

    Safe to call more than once — the record buffer is kept (clear=False) so a
    later flush rewrites the file with the full output, never truncates it.
    """
    if _tee_path:
        Path(_tee_path).parent.mkdir(parents=True, exist_ok=True)
        Path(_tee_path).write_text(
            console.export_text(clear=False) + "".join(_tee_raw), encoding="utf-8"
        )


# ---------------------------------------------------------------------------
# Envelope unwrapping
# ---------------------------------------------------------------------------

# Standard single-key envelope names.
_ENVELOPE_KEYS = ("data", "results", "items", "records")

# Keys that carry pagination / link metadata, not real payload.
_META_KEYS = frozenset({
    "meta", "pagination", "links", "total", "page", "per_page",
    "current_page", "last_page", "total_pages", "count",
})


def _unwrap(data: Any) -> Any:
    """Peel off a single-level JSON envelope and return the inner payload.

    Handles three patterns:
      1. Standard envelope  -- {"data": [...]}  or {"results": [...]}
      2. Resource-name wrap -- {"networks": [...], "meta": {...}}
         (exactly one non-meta key whose value is a list or dict)
      3. Everything else    -- returned as-is (single-resource dicts,
         deeply-nested objects, etc.)
    """
    if not isinstance(data, dict):
        return data

    # Pattern 1: well-known envelope key
    for key in _ENVELOPE_KEYS:
        if key in data and isinstance(data[key], (list, dict)):
            return data[key]

    # Pattern 2: one real-data key + optional meta keys
    data_keys = [k for k in data if k not in _META_KEYS]
    if len(data_keys) == 1:
        val = data[data_keys[0]]
        if isinstance(val, (list, dict)):
            return val

    return data


# ---------------------------------------------------------------------------
# Value rendering helpers
# ---------------------------------------------------------------------------

def _bool_str(v: bool) -> str:
    return "[green]yes[/green]" if v else "[red]no[/red]"


def _scalar_str(value: Any) -> str:
    """Render a leaf (non-container) value as a human-readable string."""
    if value is None:
        return "[dim]-[/dim]"
    if isinstance(value, bool):
        return _bool_str(value)
    return str(value)


def _cell_str(value: Any, *, max_len: int = 60) -> str:
    """Render *any* value for use inside a table cell -- never raw JSON.

    - None/bool/scalars: plain string
    - dict: "key=val, key=val …" summary (truncated)
    - list of scalars: comma-joined (truncated)
    - list of dicts: "(N items)"

    The effective truncation limit is the lesser of *max_len* and the global
    ``_truncate`` setting (when set via ``--truncate``).
    """
    effective_max = max_len if _truncate is None else min(max_len, _truncate)
    if value is None:
        return "[dim]-[/dim]"
    if isinstance(value, bool):
        return _bool_str(value)
    if isinstance(value, dict):
        if not value:
            return "[dim](empty)[/dim]"
        parts = []
        for k, v in value.items():
            parts.append(f"{k}={_scalar_str(v)}")
        summary = ", ".join(parts)
        if effective_max and len(summary) > effective_max:
            summary = summary[:effective_max].rsplit(",", 1)[0] + " …"
        return summary
    if isinstance(value, list):
        if not value:
            return "[dim](empty)[/dim]"
        if value and isinstance(value[0], dict):
            return f"[dim]({len(value)} item{'s' if len(value) != 1 else ''})[/dim]"
        parts = [_scalar_str(i) for i in value]
        joined = ", ".join(parts)
        if effective_max and len(joined) > effective_max:
            joined = joined[:effective_max].rsplit(",", 1)[0] + " …"
        return joined
    return str(value)


# ---------------------------------------------------------------------------
# Dict flattening for key/value display
# ---------------------------------------------------------------------------

def _flatten_kv(obj: Any, prefix: str = "") -> list[tuple[str, Any]]:
    """Recursively flatten *obj* into (dotted_key, leaf_value) pairs.

    Lists of dicts are NOT flattened here -- they are kept as-is so the
    caller can render them as sub-tables.
    """
    if not isinstance(obj, dict):
        return [(prefix, obj)] if prefix else []

    pairs: list[tuple[str, Any]] = []
    for k, v in obj.items():
        key = f"{prefix}.{k}" if prefix else k
        if isinstance(v, dict) and v:
            pairs.extend(_flatten_kv(v, key))
        else:
            pairs.append((key, v))
    return pairs


# ---------------------------------------------------------------------------
# Renderers
# ---------------------------------------------------------------------------

def _render_kv_table(payload: dict[str, Any], title: str = "", columns: list[str] | None = None) -> None:
    """Render a single resource as a two-column key:value table.

    Nested dicts are flattened to dotted keys.
    Nested lists of dicts are shown as indented sub-tables after the main block.
    When *columns* is provided only those keys are shown.
    """
    flat_pairs: list[tuple[str, Any]] = []
    sub_lists: list[tuple[str, list[dict]]] = []   # (key, rows) for nested object-lists

    for k, v in payload.items():
        if isinstance(v, list) and v and isinstance(v[0], dict):
            sub_lists.append((k, v))
        elif isinstance(v, dict) and v:
            flat_pairs.extend(_flatten_kv(v, k))
        else:
            flat_pairs.append((k, v))

    if columns:
        col_set = set(columns)
        flat_pairs = [(k, v) for k, v in flat_pairs if k in col_set]

    # Main key:value table
    tbl = Table(show_header=False, box=None, padding=(0, 2), expand=False)
    tbl.add_column("Key", style="bold cyan", no_wrap=True, min_width=20)
    tbl.add_column("Value", overflow="fold")

    for key, val in flat_pairs:
        tbl.add_row(key, _cell_str(val))

    if title:
        console.print(Panel(tbl, title=f"[bold]{title}[/bold]", expand=False))
    else:
        console.print(tbl)

    # Nested object-lists as titled sub-tables
    for list_key, rows in sub_lists:
        _render_list_table(rows, title=list_key, columns=columns)


def _render_list_table(rows: list[dict[str, Any]], title: str = "", columns: list[str] | None = None) -> None:
    """Render a list of dicts as a multi-column table.

    Each top-level key becomes a column. Nested values are rendered via
    _cell_str so no raw JSON ever appears.

    When *columns* is provided only those columns are shown (in the order
    given). Unknown column names are silently ignored.

    When a list of non-JSON:API flat dicts would produce too many columns
    (> 10) — e.g. organizations/users-list — each row is rendered as its own
    kv panel instead so nothing wraps illegibly.
    """
    if not rows:
        console.print(f"[dim]{title}: (empty)[/dim]" if title else "[dim](empty)[/dim]")
        return

    all_keys = list(rows[0].keys())
    active_columns = columns if columns else all_keys

    # Non-JSON:API flat objects with many fields render as panels, not as a
    # very-wide table.  JSON:API resources always have a "type" key and are
    # rendered as a table regardless of column count.
    if not columns and "type" not in rows[0] and len(active_columns) > 10:
        if title:
            console.print(f"[bold]{title}[/bold]")
        for i, row in enumerate(rows):
            _render_kv_table(row, title=f"[{i + 1}/{len(rows)}]", columns=columns)
        return

    col_max_width = _truncate if _truncate is not None else 60
    _box_kwargs = {"box": _resolve_box(_table_style)} if _table_style is not None else {}
    tbl = Table(
        title=title or None,
        show_header=True,
        header_style="bold cyan",
        expand=False,
        **_box_kwargs,
    )
    for col in active_columns:
        tbl.add_column(str(col), overflow="fold", no_wrap=_no_wrap, max_width=col_max_width)

    # Pre-compute color scale range if needed
    _cs_range: tuple[str, bool, float, float] | None = None
    if _color_scale:
        _cs_field_name, _cs_asc = _color_scale
        _cs_nums = [
            row.get(_cs_field_name) for row in rows
            if isinstance(row, dict) and isinstance(row.get(_cs_field_name), (int, float))
            and not isinstance(row.get(_cs_field_name), bool)
        ]
        if _cs_nums:
            _cs_range = (_cs_field_name, _cs_asc, float(min(_cs_nums)), float(max(_cs_nums)))

    _CS_PALETTE = ["red1", "dark_orange3", "yellow3", "chartreuse3", "green3"]

    import re as _re_cr
    for row in rows:
        row_style: str | None = None
        if _color_rules and isinstance(row, dict):
            for _cr_field, _cr_val, _cr_style in _color_rules:
                _cv = str(row.get(_cr_field, ""))
                if _re_cr.search(_cr_val, _cv, _re_cr.IGNORECASE):
                    row_style = _cr_style
                    break
        if row_style is None and _cs_range and isinstance(row, dict):
            _cs_fn, _cs_ascending, _cs_lo, _cs_hi = _cs_range
            _cs_v = row.get(_cs_fn)
            if isinstance(_cs_v, (int, float)) and not isinstance(_cs_v, bool):
                _ratio = (_cs_v - _cs_lo) / (_cs_hi - _cs_lo) if _cs_hi > _cs_lo else 0.5
                if not _cs_ascending:
                    _ratio = 1.0 - _ratio
                _cs_idx = min(int(_ratio * len(_CS_PALETTE)), len(_CS_PALETTE) - 1)
                row_style = _CS_PALETTE[_cs_idx]
        tbl.add_row(*[_cell_str(row.get(col)) for col in active_columns], style=row_style)

    console.print(tbl)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def print_response(data: Any, *, raw: bool = False, title: str = "", columns: list[str] | None = None) -> None:
    """Format and print an API response -- never raw JSON (unless --raw).

    --quiet suppresses chatter but NOT result data; data is hidden only by
    --output none (_suppress_data) or --quiet-ok (nothing unless a failure).
    """
    if _suppress_data or _quiet_ok:
        return
    if data is None:
        console.print("[green]OK[/green] [dim]-- no content returned.[/dim]")
        return

    if raw:
        console.print_json(json.dumps(data, indent=2, default=str))
        return

    payload = _unwrap(data)

    # ---- list of objects ---------------------------------------------------
    if isinstance(payload, list):
        if not payload:
            console.print("[dim](empty list)[/dim]")
        elif isinstance(payload[0], dict):
            # A single non-JSON:API flat dict (e.g. org settings) renders better
            # as a key:value panel than a very-wide multi-column table.
            if len(payload) == 1 and "type" not in payload[0]:
                _render_kv_table(payload[0], title=title, columns=columns)
            else:
                _render_list_table(payload, title=title, columns=columns)
        else:
            # List of scalars
            for item in payload:
                console.print(_scalar_str(item))

        # Show pagination hint if the outer envelope contained metadata
        if isinstance(data, dict):
            meta = data.get("meta") or data.get("pagination") or {}
            total = meta.get("total") or data.get("total")
            if total is not None:
                console.print(f"[dim]Total: {total}[/dim]")
        return

    # ---- single object -----------------------------------------------------
    if isinstance(payload, dict):
        _render_kv_table(payload, title=title)
        return

    # ---- scalar / fallback -------------------------------------------------
    console.print(_scalar_str(payload))


# ---------------------------------------------------------------------------
# CSV export
# ---------------------------------------------------------------------------

def _csv_cell(value: Any) -> str:
    """Render a value as a plain CSV cell string (no Rich markup).

    Neutralizes spreadsheet formula injection: exported data is exactly the
    untrusted content this tool handles (customer domains, notes, threat
    feeds), and a value beginning with = + - @ (optionally after whitespace)
    is executed as a formula when the CSV is opened in Excel/Sheets. We
    prefix such values with a single quote so the spreadsheet treats them as
    literal text, per the OWASP CSV-injection guidance.
    """
    if value is None:
        return _csv_null_value
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (dict, list)):
        # Compact JSON for nested containers -- still machine-readable
        rendered = json.dumps(value, separators=(",", ":"), default=str)
    else:
        rendered = str(value)
    return _neutralize_formula(rendered)


def _neutralize_formula(text: str) -> str:
    """Prefix a leading formula-trigger character with a single quote.

    `=` `@` tab and CR always trigger. `+`/`-` also trigger a formula, but a
    plain negative/signed number is legitimate data, so those are neutralized
    only when the value is not numeric (avoids mangling e.g. -5 into '-5).
    """
    stripped = text.lstrip()
    if not stripped:
        return text
    lead = stripped[0]
    if lead in ("=", "@", "\t", "\r"):
        return "'" + text
    if lead in ("+", "-"):
        try:
            float(stripped)          # a real signed number → safe, leave as-is
        except ValueError:
            return "'" + text
    return text


def _rows_for_csv(data: Any, columns: list[str] | None = None) -> tuple[list[str], list[list[str]]]:
    """Return (headers, data_rows) ready to feed into csv.writer.

    - List of objects  : one row per item; nested dicts are dotted-key-flattened.
    - Single object    : one data row.
    - List of scalars  : single "value" column.
    - Scalar           : single "value" column, single row.

    When *columns* is provided only those headers (in that order) are included.
    """
    payload = _unwrap(data)

    if isinstance(payload, list):
        if not payload:
            return ["(empty)"], []

        if isinstance(payload[0], dict):
            # Collect all keys across all rows so we never miss a sparse field
            headers: list[str] = []
            seen: set[str] = set()
            flat_rows: list[dict[str, Any]] = []
            for item in payload:
                flat = dict(_flatten_kv(item) if isinstance(item, dict) else [("value", item)])
                flat_rows.append(flat)
                for k in flat:
                    if k not in seen:
                        seen.add(k)
                        headers.append(k)
            if columns:
                headers = [h for h in columns if h in seen]
            rows = [[_csv_cell(row.get(h)) for h in headers] for row in flat_rows]
            return headers, rows

        # List of scalars
        return ["value"], [[_csv_cell(v)] for v in payload]

    if isinstance(payload, dict):
        flat = dict(_flatten_kv(payload))
        if columns:
            flat = {k: v for k, v in flat.items() if k in columns}
        return list(flat.keys()), [[_csv_cell(v) for v in flat.values()]]

    # Bare scalar (e.g. a plain string or number from the API)
    return ["value"], [[_csv_cell(payload)]]


def write_csv(
    data: Any,
    filepath: str | Path,
    columns: list[str] | None = None,
    *,
    append: bool = False,
    delimiter: str = ",",
    no_header: bool = False,
    header_case: str | None = None,
) -> int:
    """Write *data* to *filepath* as a CSV file.

    Returns the number of data rows written (not counting the header row).
    Creates the immediate parent directory if it does not exist.

    When *append* is True the file is opened in append mode and the header
    row is omitted if the file already has content (so a second run extends
    rather than duplicates the header).

    When *columns* is provided only those columns are written (in that order).

    dnsfcli accepts any writable path the running user can access.  Callers
    that construct this path from external input are responsible for
    sanitizing it before passing it here.
    """
    from .csv_io import _warn_if_traversal
    _warn_if_traversal(filepath)
    path = Path(filepath)
    path.parent.mkdir(parents=True, exist_ok=True)
    headers, rows = _rows_for_csv(data, columns=columns)
    if header_case == "lower":
        headers = [h.lower() for h in headers]
    elif header_case == "upper":
        headers = [h.upper() for h in headers]
    elif header_case == "title":
        headers = [h.replace("_", " ").title().replace(" ", "_") for h in headers]
    mode = "a" if append else "w"
    write_header = not no_header and not (append and path.exists() and path.stat().st_size > 0)
    with path.open(mode, newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh, delimiter=delimiter)
        if write_header:
            writer.writerow(headers)
        writer.writerows(rows)
    return len(rows)


# ---------------------------------------------------------------------------
# Utility printers (used by auth commands and error paths)
# ---------------------------------------------------------------------------

_ERR_SECRET_KEY_RE = re.compile(r"(secret|password|passwd|token|credential|api[-_]?key)", re.I)


def print_error(message: str, detail: Any = None) -> None:
    # Errors are never suppressed by --quiet.
    err_console.print(f"[bold red]Error:[/bold red] {message}")
    if detail is None:
        return
    if isinstance(detail, dict):
        for k, v in detail.items():
            if v is not None:
                # An API validation-error body can echo the fields the client
                # submitted; redact any that look like a secret so a rejected
                # create/change-password doesn't print the value (also relevant
                # when err_console is redirected to --log-file).
                if isinstance(k, str) and _ERR_SECRET_KEY_RE.search(k):
                    v = "***"
                err_console.print(f"  [dim]{k}:[/dim] {v}")
    elif isinstance(detail, list):
        for item in detail:
            err_console.print(f"  [dim]-[/dim] {item}")
    else:
        err_console.print(f"  [dim]{detail}[/dim]")


def is_quiet() -> bool:
    """True when --quiet is active (suppress success/info chatter). Reads the
    live module state so callers outside this module (e.g. the --exec summary
    in cli.py) don't have to reach into a private global."""
    return _quiet


def print_success(message: str) -> None:
    if not _quiet and not _quiet_ok:
        console.print(f"[bold green]✓[/bold green] {message}")


def print_info(message: str) -> None:
    if not _quiet and not _quiet_ok:
        console.print(f"[bold blue]>[/bold blue] {message}")


def print_warning(message: str) -> None:
    if not _quiet:
        err_console.print(f"[bold yellow]![/bold yellow] {message}")


# ---------------------------------------------------------------------------
# Markdown table export
# ---------------------------------------------------------------------------

def render_markdown_table(items: list[Any], columns: list[str] | None = None) -> str:
    """Format *items* as a GFM Markdown table string."""
    if not items:
        return "_No results._\n"
    first = items[0]
    cols = columns or (list(first.keys()) if isinstance(first, dict) else [])
    if not cols:
        return "\n".join(str(i) for i in items) + "\n"
    lines: list[str] = []
    lines.append("| " + " | ".join(cols) + " |")
    lines.append("| " + " | ".join("---" for _ in cols) + " |")
    for item in items:
        if isinstance(item, dict):
            cells = [str(item.get(c, "")).replace("|", "\\|") for c in cols]
        else:
            cells = [str(item)] + [""] * (len(cols) - 1)
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# JSON export
# ---------------------------------------------------------------------------

def write_json(data: Any, filepath: str | Path) -> None:
    """Write the unwrapped *data* payload to *filepath* as pretty-printed JSON."""
    from .csv_io import _warn_if_traversal
    _warn_if_traversal(filepath)
    path = Path(filepath)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _unwrap(data)
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
