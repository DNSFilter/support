"""Dynamic-command option table and grouped --help rendering.

Every ``dnsfcli <endpoint> <function>`` command carries the same ~120 generic
flags (output shaping, filtering, pagination, batch, request tuning, auth).
Declaring them inline made :func:`dnsfcli.cli._make_dynamic_command` a 450-line
wall of decorators; they live here instead as a table applied by
:func:`add_dynamic_options`, so that function reads as orchestration.

The option definitions are moved verbatim from the original decorator stack —
same param declarations, same ``rich_help_panel`` groups, same order — so the
generated command and its ``--help`` output are byte-for-byte unchanged.
"""

from __future__ import annotations

from typing import Any

import click


class _PanelOption(click.Option):
    """click.Option subclass that carries a rich_help_panel label for grouped help."""

    def __init__(self, *args: Any, rich_help_panel: str = "Options", **kwargs: Any) -> None:
        self.rich_help_panel = rich_help_panel
        super().__init__(*args, **kwargs)


class _GroupedCommand(click.Command):
    """click.Command subclass that renders --help with options grouped by panel."""

    def format_help(self, ctx: Any, formatter: Any) -> None:
        self.format_usage(ctx, formatter)
        if self.help:
            formatter.write_paragraph()
            with formatter.indentation():
                formatter.write_text(self.help)
        self._format_grouped_options(ctx, formatter)
        self._format_api_params(ctx, formatter)
        self.format_epilog(ctx, formatter)

    def _format_api_params(self, ctx: Any, formatter: Any) -> None:
        try:
            from .endpoints import REGISTRY
            op = REGISTRY[self.endpoint].operations[self.function]
        except KeyError:
            return
        if not op.params:
            return
        rows: list[tuple[str, str]] = []
        for p in op.params:
            req_tag = "[required]" if p.required else "[optional]"
            desc = p.description or ""
            rows.append((
                f"--{p.name.replace('_', '-')}",
                f"{p.type_hint}  {req_tag}  {desc}",
            ))
        with formatter.section("API Parameters"):
            formatter.write_dl(rows)

    def _format_grouped_options(self, ctx: Any, formatter: Any) -> None:
        panels: dict[str, list[Any]] = {}
        for param in self.params:
            panel = getattr(param, "rich_help_panel", "Options")
            panels.setdefault(panel, []).append(param)

        panel_order = [
            "Output", "Filtering", "Pagination", "Export", "Batch",
            "Request", "Auth / Profile", "Options",
        ]
        shown: set[str] = set()
        for panel_name in panel_order:
            if panel_name not in panels:
                continue
            shown.add(panel_name)
            records = [r for p in panels[panel_name] if (r := p.get_help_record(ctx)) is not None]
            if records:
                with formatter.section(panel_name):
                    formatter.write_dl(records)
        for panel_name, params in panels.items():
            if panel_name in shown:
                continue
            records = [r for p in params if (r := p.get_help_record(ctx)) is not None]
            if records:
                with formatter.section(panel_name):
                    formatter.write_dl(records)


# The full option stack, in source (top-to-bottom) order. Each entry is a
# click.option(...) partial that add_dynamic_options() applies to the command.
_OPTION_SPECS = [
    click.option("--raw", "-r", cls=_PanelOption, rich_help_panel="Output",
        is_flag=True, default=False, help="Print raw JSON instead of formatted output."),
    click.option("--json", "as_json", cls=_PanelOption, rich_help_panel="Output",
        is_flag=True, default=False, help="Output clean JSON to stdout (no Rich formatting). Useful for piping to jq."),
    click.option("--jsonl", "as_jsonl", cls=_PanelOption, rich_help_panel="Output",
        is_flag=True, default=False, help="Output one JSON object per line (JSON Lines format), useful for piping to jq."),
    click.option("--no-color", "no_color", cls=_PanelOption, rich_help_panel="Output",
        is_flag=True, default=False, envvar="DNSFCLI_NO_COLOR",
        help="Disable ANSI colour output.  [env: DNSFCLI_NO_COLOR]"),
    click.option("--quiet", "-q", "quiet", cls=_PanelOption, rich_help_panel="Output",
        is_flag=True, default=False, envvar="DNSFCLI_QUIET",
        help="Suppress non-error output.  [env: DNSFCLI_QUIET]"),
    click.option("--columns", "columns_str", cls=_PanelOption, rich_help_panel="Output",
        default=None, metavar="COLS", envvar="DNSFCLI_COLUMNS",
        help="Comma-separated list of columns to include in output.  [env: DNSFCLI_COLUMNS]"),
    click.option("--format", "format_template", cls=_PanelOption, rich_help_panel="Output",
        default=None, metavar="TEMPLATE",
        help=r"Format each result using a Go-style template. Example: --format '{{.id}}: {{.name}}'"),
    click.option("--pick", "pick_field", cls=_PanelOption, rich_help_panel="Output",
        default=None, metavar="FIELD",
        help="Extract a single field (dot-notation) and print one value per line."),
    click.option("--sort", "sort_by", cls=_PanelOption, rich_help_panel="Output",
        multiple=True, metavar="FIELD",
        help="Sort results by FIELD (prefix with '-' for descending, e.g. -created_at). Repeatable for multi-field sort."),
    click.option("--limit", "limit", cls=_PanelOption, rich_help_panel="Output",
        default=None, type=int, metavar="N",
        help="Cap results at N items (applied after --sort and --all pagination)."),
    click.option("--last", "last", cls=_PanelOption, rich_help_panel="Output",
        default=None, type=int, metavar="N",
        help="Keep only the last N items from the result list (applied after --sort)."),
    click.option("--sample", "sample", cls=_PanelOption, rich_help_panel="Output",
        default=None, type=click.IntRange(min=1), metavar="N",
        help="Show only the first N items client-side (after filters/sort, before output). Unlike --limit, does not affect the server query."),
    click.option("--select", "select_fields_str", cls=_PanelOption, rich_help_panel="Output",
        default=None, metavar="FIELDS",
        help="Comma-separated fields to keep in each result object (inverse of --exclude)."),
    click.option("--exclude", "exclude_str", cls=_PanelOption, rich_help_panel="Output",
        default=None, metavar="FIELDS",
        help="Comma-separated list of fields to remove from each result object."),
    click.option("--rename", "rename_fields", cls=_PanelOption, rich_help_panel="Output",
        multiple=True, metavar="FROM=TO",
        help="Rename a result field (repeatable). Example: --rename org_id=organization_id"),
    click.option("--group-by", "group_by", cls=_PanelOption, rich_help_panel="Output",
        default=None, metavar="FIELD",
        help="Aggregate list results into a count-per-value table grouped by FIELD."),
    click.option("--sum", "sum_field", cls=_PanelOption, rich_help_panel="Output",
        default=None, metavar="FIELD",
        help="Sum the numeric values of FIELD across all results and print the total."),
    click.option("--avg", "avg_field", cls=_PanelOption, rich_help_panel="Output",
        default=None, metavar="FIELD",
        help="Average the numeric values of FIELD across all results and print the mean."),
    click.option("--min", "min_field", cls=_PanelOption, rich_help_panel="Output",
        default=None, metavar="FIELD",
        help="Print the minimum numeric value of FIELD across all results."),
    click.option("--max", "max_field", cls=_PanelOption, rich_help_panel="Output",
        default=None, metavar="FIELD",
        help="Print the maximum numeric value of FIELD across all results."),
    click.option("--map", "map_fields", cls=_PanelOption, rich_help_panel="Output",
        multiple=True, metavar="FIELD=TRANSFORM",
        help="Transform a result field value (repeatable). TRANSFORM: upper, lower, strip, title, truncate:N."),
    click.option("--truncate", "truncate", cls=_PanelOption, rich_help_panel="Output",
        default=None, type=int, metavar="N",
        help="Truncate cell values to N characters in table output. Use -1 to disable truncation."),
    click.option("--count", "count_only", cls=_PanelOption, rich_help_panel="Output",
        is_flag=True, default=False,
        help="Print only the number of results, not the results themselves."),
    click.option("--filter", "filters", cls=_PanelOption, rich_help_panel="Filtering",
        multiple=True, metavar="EXPR",
        help="Client-side filter (repeatable, AND). "
        "Forms: field=value  field!=value  field~substr  field>N  field<N  field>=N  field<=N."),
    click.option("--grep", "grep", cls=_PanelOption, rich_help_panel="Filtering",
        default=None, metavar="PATTERN",
        help="Keep only results where any field value matches PATTERN (regex, case-insensitive)."),
    click.option("--unique", "unique_field", cls=_PanelOption, rich_help_panel="Filtering",
        default=None, metavar="FIELD",
        help="Deduplicate results, keeping the first item for each distinct value of FIELD."),
    click.option("--page", "page", cls=_PanelOption, rich_help_panel="Pagination",
        default=None, type=int, metavar="N",
        help="Fetch a specific page number (server-side pagination)."),
    click.option("--page-size", "page_size", cls=_PanelOption, rich_help_panel="Pagination",
        default=None, type=int, metavar="N",
        help="Number of items per page (server-side pagination)."),
    click.option("--all", "fetch_all", cls=_PanelOption, rich_help_panel="Pagination",
        is_flag=True, default=False,
        help="Auto-paginate: fetch every page and combine all results."),
    click.option("--to-csv", "csv_file", cls=_PanelOption, rich_help_panel="Export",
        default=None, metavar="FILE",
        help="Write results to FILE as CSV. Accepts any path the running user can access; "
        "scripts constructing this path from external input must sanitize it first."),
    click.option("--to-json", "json_file", cls=_PanelOption, rich_help_panel="Export",
        default=None, metavar="FILE",
        help="Write the unwrapped result as pretty-printed JSON to FILE."),
    click.option("--append", "csv_append", cls=_PanelOption, rich_help_panel="Export",
        is_flag=True, default=False,
        help="Append to --to-csv file instead of overwriting (header is written only when file is empty)."),
    click.option("--no-header", "no_header", cls=_PanelOption, rich_help_panel="Export",
        is_flag=True, default=False,
        help="Omit the header row from CSV output (--to-csv / --to-csv -)."),
    click.option("--csv-header-case", "csv_header_case", cls=_PanelOption, rich_help_panel="Export",
        default=None, type=click.Choice(["lower", "upper", "title"], case_sensitive=False),
        help="Normalize CSV column names: lower (id, policy_id), upper (ID, POLICY_ID), title (Id, Policy_Id)."),
    click.option("--csv-delimiter", "csv_delimiter", cls=_PanelOption, rich_help_panel="Export",
        default=",", metavar="CHAR", envvar="DNSFCLI_CSV_DELIMITER",
        help="Field delimiter for CSV input/output (default: comma).  [env: DNSFCLI_CSV_DELIMITER]"),
    click.option("--from-csv", "csv_input", cls=_PanelOption, rich_help_panel="Batch",
        default=None, metavar="FILE",
        help="Read input rows from a CSV file (one API call per row). "
        "Accepts any path the running user can access; "
        "scripts constructing this path from external input must sanitize it first."),
    click.option("--from-json", "json_input", cls=_PanelOption, rich_help_panel="Batch",
        default=None, metavar="FILE|-",
        help="Read a JSON array and execute one API call per element. Use '-' for stdin."),
    click.option("--template", "show_template", cls=_PanelOption, rich_help_panel="Batch",
        is_flag=True, default=False,
        help="Print a blank CSV input template for this operation and exit."),
    click.option("--plan", "show_plan", cls=_PanelOption, rich_help_panel="Batch",
        is_flag=True, default=False,
        help="Show a dry-run summary (calls, records, duration) without executing."),
    click.option("--on-error", "on_error", cls=_PanelOption, rich_help_panel="Batch",
        default=None, type=click.Choice(["continue", "stop", "report"], case_sensitive=False),
        help="Batch error strategy: 'continue' keeps going and exits 1 if any row failed, 'stop' halts on first failure, 'report' processes all rows and always exits 0 (log failures, never break CI). Default: continue."),
    click.option("--concurrency", "concurrency", cls=_PanelOption, rich_help_panel="Batch",
        default=None, type=click.IntRange(min=1, max=64), metavar="N", envvar="DNSFCLI_CONCURRENCY",
        help="Parallel workers for --from-csv batch operations (default: 1, max: 64).  [env: DNSFCLI_CONCURRENCY]"),
    click.option("--batch-size", "batch_size", cls=_PanelOption, rich_help_panel="Batch",
        default=None, type=int, metavar="N",
        help="Split --from-csv / --from-json input into chunks of N rows each."),
    click.option("--retry", "retry", cls=_PanelOption, rich_help_panel="Batch",
        default=None, type=int, metavar="N",
        help="Retry failed batch rows up to N times on 5xx, with exponential back-off. Default: 0. "
        "Only idempotent methods (GET/PUT/DELETE) are retried; POST/PATCH rows are NOT retried "
        "(a failed write may have applied server-side, so retrying could create duplicates) — "
        "re-run the --errors-to-csv file after checking."),
    click.option("--errors-to-csv", "errors_csv", cls=_PanelOption, rich_help_panel="Batch",
        default=None, metavar="FILE",
        help="Write input rows that failed (after retries) to FILE for later reprocessing."),
    click.option("--retry-errors-csv", "retry_errors_csv", cls=_PanelOption, rich_help_panel="Batch",
        default=None, metavar="FILE",
        help="Re-run only the failed rows from a previous --errors-to-csv FILE. Equivalent to --from-csv FILE but semantically signals a retry pass."),
    click.option("--upsert", "upsert", cls=_PanelOption, rich_help_panel="Batch",
        is_flag=True, default=False,
        help="On POST: if the API returns 409 Conflict, automatically retry as PATCH on the existing resource."),
    click.option("--max-errors", "max_errors", cls=_PanelOption, rich_help_panel="Batch",
        default=None, type=int, metavar="N",
        help="Stop batch processing after N cumulative failures (between --on-error continue and stop)."),
    click.option("--body-json", "body_json", cls=_PanelOption, rich_help_panel="Request",
        default=None, metavar="JSON|@FILE",
        help="Merge raw JSON into the request body. Prefix with '@' to read from a file."),
    click.option("--set", "set_fields", cls=_PanelOption, rich_help_panel="Request",
        multiple=True, metavar="FIELD=VALUE",
        help="Set a single body field (repeatable). Shorthand for simple --body-json updates."),
    click.option("--merge-key", "merge_key", cls=_PanelOption, rich_help_panel="Request",
        default=None, metavar="FIELD",
        help="Look up the resource id by matching FIELD against the list endpoint, then inject id."),
    click.option("--dry-run", "dry_run", cls=_PanelOption, rich_help_panel="Request",
        is_flag=True, default=False,
        help="Print the resolved HTTP request (method, URL, body) without executing it."),
    click.option("--wait", "wait", cls=_PanelOption, rich_help_panel="Request",
        is_flag=True, default=False,
        help="For async operations: poll until the job completes, then display the final result. "
             "Exits non-zero if the job fails, times out (--max-wait), or its status can't be determined."),
    click.option("--timing", "timing", cls=_PanelOption, rich_help_panel="Request",
        is_flag=True, default=False,
        help="Print request duration to stderr after each API call."),
    click.option("--rate", "rate", cls=_PanelOption, rich_help_panel="Request",
        default=None, type=float, metavar="REQ/S",
        help="Override the client-side rate limit (requests per second). Default: 80%% of API limit."),
    click.option("--timeout", "timeout", cls=_PanelOption, rich_help_panel="Request",
        default=None, type=float, metavar="SECS", envvar="DNSFCLI_TIMEOUT",
        help="Per-request read/write timeout in seconds.  [env: DNSFCLI_TIMEOUT]"),
    click.option("--cache-ttl", "cache_ttl", cls=_PanelOption, rich_help_panel="Request",
        default=None, type=int, metavar="SECS",
        help="Cache GET responses for SECS seconds (stored in ~/.cache/dnsfcli/)."),
    click.option("--env-file", "env_file", cls=_PanelOption, rich_help_panel="Auth / Profile",
        default=None, metavar="FILE",
        help="Load environment variables (DNSF_API_KEY, DNSF_ORG_ID, etc.) from a .env file before resolving credentials."),
    click.option("--log-file", "log_file", cls=_PanelOption, rich_help_panel="Output",
        default=None, metavar="FILE",
        help="Append all warnings/errors/progress output to FILE instead of stderr (keeps stdout clean for piping)."),
    click.option("--stdin-json", "stdin_json", cls=_PanelOption, rich_help_panel="Request",
        is_flag=True, default=False,
        help="Read the full request body as JSON from stdin. Enables: cat payload.json | dnsfcli networks create --stdin-json."),
    click.option("--watch", "watch_interval", cls=_PanelOption, rich_help_panel="Request",
        default=None, type=click.IntRange(min=5), metavar="SECS",
        help="Re-run this command every SECS seconds until interrupted (Ctrl-C). "
        "Minimum 5s; 10s+ recommended, especially with --all (each tick refetches every page)."),
    click.option("--watch-changes", "watch_changes_interval", cls=_PanelOption, rich_help_panel="Request",
        default=None, type=click.IntRange(min=5), metavar="SECS",
        help="Poll every SECS seconds and print only what changed (added/removed/updated rows). Minimum 5s."),
    click.option("--max-pages", "max_pages", cls=_PanelOption, rich_help_panel="Pagination",
        default=None, type=int, metavar="N",
        help="Cap --all pagination at N pages (safety valve for large endpoints)."),
    click.option("--fields", "fields_only", cls=_PanelOption, rich_help_panel="Output",
        is_flag=True, default=False,
        help="Print available field names from the first result object and exit."),
    click.option("--strip-nulls", "strip_nulls", cls=_PanelOption, rich_help_panel="Output",
        is_flag=True, default=False,
        help="Remove keys with null values from each result object before output."),
    click.option("--save-as", "save_as", cls=_PanelOption, rich_help_panel="Options",
        default=None, metavar="NAME",
        help="Save the current command as a named alias after running it."),
    click.option("--null-as", "null_as", cls=_PanelOption, rich_help_panel="Output",
        default=None, metavar="STR",
        help="Replace null (None) values with STR before output (e.g. --null-as N/A)."),
    click.option("--no-wrap", "no_wrap", cls=_PanelOption, rich_help_panel="Output",
        is_flag=True, default=False,
        help="Disable word-wrap in table cells (show full values in a wider table)."),
    click.option("--color-if", "color_rules_raw", cls=_PanelOption, rich_help_panel="Output",
        multiple=True, metavar="FIELD:REGEX=STYLE",
        help="Conditionally color rows where FIELD matches REGEX with the given Rich style. Repeatable."),
    click.option("--count-by", "count_by", cls=_PanelOption, rich_help_panel="Output",
        default=None, metavar="FIELD",
        help="Show a frequency table for FIELD with a percentage column."),
    click.option("--not-null", "not_null_field", cls=_PanelOption, rich_help_panel="Filtering",
        default=None, metavar="FIELD",
        help="Keep only rows where FIELD is not null."),
    click.option("--is-null", "is_null_field", cls=_PanelOption, rich_help_panel="Filtering",
        default=None, metavar="FIELD",
        help="Keep only rows where FIELD is null."),
    click.option("--since", "since_filter", cls=_PanelOption, rich_help_panel="Filtering",
        default=None, metavar="FIELD DATE",
        help="Shorthand for --filter FIELD>=DATE. Example: --since updated_at 2025-01-01"),
    click.option("--header", "extra_headers_raw", cls=_PanelOption, rich_help_panel="Request",
        multiple=True, metavar="KEY=VALUE",
        help="Add a custom HTTP request header (repeatable). Example: --header X-Trace-Id=abc"),
    click.option("--insecure", "insecure", cls=_PanelOption, rich_help_panel="Request",
        is_flag=True, default=False,
        help="Skip TLS certificate verification. Do not use in production."),
    click.option("--no-progress", "no_progress", cls=_PanelOption, rich_help_panel="Options",
        is_flag=True, default=False,
        help="Disable progress bars for --all pagination and batch operations."),
    click.option("--tee", "tee_file", cls=_PanelOption, rich_help_panel="Export",
        default=None, metavar="FILE",
        help="Write plain-text console output to FILE in addition to stdout."),
    click.option("--output", "output_format", cls=_PanelOption, rich_help_panel="Output",
        default=None, type=click.Choice(["table", "json", "jsonl", "raw", "csv", "none"], case_sensitive=False),
        help="Unified output format: table (default), json, jsonl, raw, csv, or none (suppress all output, use exit code only)."),
    click.option("--validate-only", "validate_only", cls=_PanelOption, rich_help_panel="Batch",
        is_flag=True, default=False,
        help="Validate --from-csv / --from-json input rows without making any API calls."),
    click.option("--confirm-each", "confirm_each", cls=_PanelOption, rich_help_panel="Batch",
        is_flag=True, default=False,
        help="Prompt for confirmation before processing each batch row."),
    click.option("--diff-mode", "diff_mode", cls=_PanelOption, rich_help_panel="Batch",
        is_flag=True, default=False,
        help="Before each PATCH/PUT batch row, fetch the current resource state and show a field-change table."),
    click.option("--skip-rows", "skip_rows", cls=_PanelOption, rich_help_panel="Batch",
        default=0, type=int, metavar="N",
        help="Skip the first N input rows from --from-csv / --from-json (e.g. to resume an interrupted batch)."),
    click.option("--max-rows", "max_rows", cls=_PanelOption, rich_help_panel="Batch",
        default=None, type=click.IntRange(min=1), metavar="N",
        help="Process at most N input rows from --from-csv / --from-json."),
    click.option("--batch-report", "batch_report", cls=_PanelOption, rich_help_panel="Batch",
        default=None, metavar="FILE",
        help="Write a JSON summary of the batch run (per-row outcomes, counts) to FILE."),
    click.option("--preset", "preset", cls=_PanelOption, rich_help_panel="Output",
        default=None, metavar="NAME",
        help="Apply a named column preset from config (column_presets.NAME). Overrides --columns."),
    click.option("--format-preset", "format_preset", cls=_PanelOption, rich_help_panel="Output",
        default=None, metavar="NAME",
        help="Apply a named --format template from config (format_presets.NAME). Overrides --format."),
    click.option("--add-field", "add_fields", cls=_PanelOption, rich_help_panel="Output",
        multiple=True, metavar="FIELD=VALUE",
        help="Inject a static FIELD=VALUE into every result item before output (repeatable)."),
    click.option("--paginate-until", "paginate_until", cls=_PanelOption, rich_help_panel="Pagination",
        default=None, metavar="EXPR",
        help="Stop --all pagination when any item on a page matches EXPR (same filter syntax as --filter)."),
    click.option("--org-csv", "org_csv", cls=_PanelOption, rich_help_panel="Auth / Profile",
        default=None, metavar="FILE",
        help="Supply the org list for --each-org from a CSV file (columns: id, name) instead of the API."),
    click.option("--color-scale", "color_scale", cls=_PanelOption, rich_help_panel="Output",
        default=None, metavar="FIELD[:asc|desc]",
        help="Color rows by a numeric FIELD on a red→green gradient. Suffix :desc reverses (green=low)."),
    click.option("--parallel-orgs", "parallel_orgs", cls=_PanelOption, rich_help_panel="Auth / Profile",
        is_flag=True, default=False,
        help="Run --each-org concurrently instead of sequentially."),
    click.option("--org-concurrency", "org_concurrency", cls=_PanelOption, rich_help_panel="Auth / Profile",
        default=4, type=click.IntRange(min=1, max=32), metavar="N",
        help="Max parallel org workers when --parallel-orgs is set (default: 4, max: 32)."),
    click.option("--org-filter", "org_filter", cls=_PanelOption, rich_help_panel="Auth / Profile",
        default=None, metavar="REGEX",
        help="Filter organizations by name regex when --each-org is used."),
    click.option("--max-orgs", "max_orgs", cls=_PanelOption, rich_help_panel="Auth / Profile",
        default=None, type=click.IntRange(min=1), metavar="N",
        help="Cap --each-org at N organizations (useful for dry-runs before running across all orgs)."),
    click.option("--flatten", "flatten", cls=_PanelOption, rich_help_panel="Output",
        is_flag=True, default=False,
        help="Flatten nested dict objects to dot-notation keys before output."),
    click.option("--strip-empties", "strip_empties", cls=_PanelOption, rich_help_panel="Output",
        is_flag=True, default=False,
        help="Remove keys with null, empty-string, empty-list, or empty-dict values (extends --strip-nulls)."),
    click.option("--csv-null", "csv_null_value", cls=_PanelOption, rich_help_panel="Export",
        default=None, metavar="STR",
        help="String to write in CSV cells when a value is null (default: empty string)."),
    click.option("--watch-until", "watch_until_filter", cls=_PanelOption, rich_help_panel="Request",
        default=None, metavar="EXPR",
        help="Stop --watch loop when any result matches EXPR (same syntax as --filter)."),
    click.option("--fail-on-empty", "fail_on_empty", cls=_PanelOption, rich_help_panel="Options",
        is_flag=True, default=False,
        help="Exit non-zero when the result list is empty. Useful for CI/monitoring scripts."),
    click.option("--quiet-ok", "quiet_ok", cls=_PanelOption, rich_help_panel="Output",
        is_flag=True, default=False,
        help="Suppress normal output (table, success messages) but keep warnings and errors visible."),
    click.option("--delay", "batch_delay", cls=_PanelOption, rich_help_panel="Batch",
        default=None, type=int, metavar="MS",
        help="Wait MS milliseconds between batch row API calls (sequential mode only)."),
    click.option("--connect-timeout", "connect_timeout", cls=_PanelOption, rich_help_panel="Request",
        default=None, type=float, metavar="SECS",
        help="TCP connect timeout in seconds (default: 10). Separate from read/write timeout."),
    click.option("--proxy", "proxy", cls=_PanelOption, rich_help_panel="Request",
        default=None, metavar="URL",
        help="HTTP/HTTPS proxy URL (e.g. http://proxy.corp:8080)."),
    click.option("--jq", "jq_expr", cls=_PanelOption, rich_help_panel="Output",
        default=None, metavar="PATH",
        help="Extract a value via dot-separated path before output (e.g. data.0.attributes.name)."),
    click.option("--max-wait", "max_wait", cls=_PanelOption, rich_help_panel="Request",
        default=None, type=float, metavar="SECS",
        help="Abort --wait polling after this many seconds (default: unlimited)."),
    click.option("--watch-diff", "watch_diff", cls=_PanelOption, rich_help_panel="Request",
        is_flag=True, default=False,
        help="In --watch mode, print a summary of rows added/removed since the previous iteration."),
    click.option("--alert", "alert_filter", cls=_PanelOption, rich_help_panel="Request",
        default=None, metavar="EXPR",
        help="Ring terminal bell + print banner when EXPR matches (same syntax as --filter). Continues watching."),
    click.option("--table-style", "table_style", cls=_PanelOption, rich_help_panel="Output",
        default=None, metavar="STYLE",
        help="Rich table box style: rounded, simple, minimal, markdown, horizontals, heavy, double, ascii, none."),
    click.option("--stats", "stats_field", cls=_PanelOption, rich_help_panel="Output",
        default=None, metavar="FIELD",
        help="Print min/max/mean/count for a numeric field in the result list."),
    click.option("--api-key", cls=_PanelOption, rich_help_panel="Auth / Profile",
        envvar="DNSF_API_KEY", default=None, help="Override stored API key."),
    click.option("--org-id", cls=_PanelOption, rich_help_panel="Auth / Profile",
        envvar="DNSF_ORG_ID", default=None, help="Override stored org ID."),
    click.option("--profile", "profile", cls=_PanelOption, rich_help_panel="Auth / Profile",
        default=None, metavar="PROFILE", envvar="DNSF_PROFILE",
        help="Named credential profile to use (overrides active profile)."),
    click.option("--org-name", "org_name", cls=_PanelOption, rich_help_panel="Auth / Profile",
        default=None, metavar="PATTERN",
        help="Resolve an organization by name (regex) instead of --org-id."),
    click.option("--each-org", "each_org", cls=_PanelOption, rich_help_panel="Auth / Profile",
        is_flag=True, default=False,
        help="Repeat the command for every organization in the account, printing a header per org."),
    click.option("--verbose", "-v", cls=_PanelOption, rich_help_panel="Options",
        is_flag=True, default=False, help="Show request URL and body."),
    click.option("--yes", "-y", "skip_confirm", cls=_PanelOption, rich_help_panel="Options",
        is_flag=True, default=False,
        help="Skip confirmation prompt for destructive operations."),
    click.option("--fail-on-pattern", "fail_on_pattern", cls=_PanelOption, rich_help_panel="Options",
        default=None, metavar="EXPR",
        help="Exit non-zero if any result item matches EXPR (same filter syntax as --filter)."),
    click.option("--filter-mode", "filter_mode", cls=_PanelOption, rich_help_panel="Filtering",
        default="and", type=click.Choice(["and", "or"], case_sensitive=False),
        help="Combine multiple --filter expressions with AND (default) or OR logic."),
    click.option("--to-markdown", "to_markdown", cls=_PanelOption, rich_help_panel="Export",
        default=None, metavar="FILE",
        help="Write results as a GFM Markdown table to FILE (use '-' for stdout)."),
    click.option("--output-schema", "output_schema", cls=_PanelOption, rich_help_panel="Output",
        is_flag=True, default=False,
        help="Print field names, types, and sample values from the response then exit."),
    click.option("--exec", "exec_cmd", cls=_PanelOption, rich_help_panel="Output",
        default=None, metavar="CMD",
        help="Run CMD for each result item with {field} or $field substitution (e.g. --exec 'curl -X POST http://hook/$id')."),
    click.option("--transform", "transforms", cls=_PanelOption, rich_help_panel="Output",
        multiple=True, metavar="FIELD=EXPR",
        help="Add or overwrite FIELD by evaluating EXPR against each item (e.g. --transform ratio=blocked/total). Repeatable."),
    click.option("--join", "join_spec", cls=_PanelOption, rich_help_panel="Filtering",
        default=None, metavar="ENDPOINT:LOCAL=REMOTE",
        help="Client-side join: fetch ENDPOINT and attach matching records as a nested field (e.g. --join policies:policy_id=id)."),
    click.option("--bundle", "bundle", cls=_PanelOption, rich_help_panel="Options",
        default=None, metavar="NAME",
        help="Apply a named flag bundle from config [bundles.NAME] as defaults (CLI flags override bundle values)."),
]


def add_dynamic_options(fn: Any) -> Any:
    """Apply the full dynamic-command option stack to *fn* and return it.

    Faithful to the original decorator stack: options are applied in reverse
    source order so that, after Click reverses ``__click_params__``, the final
    parameter order (and therefore grouped ``--help`` rendering) is identical.
    ``click.pass_context`` is applied by the caller as the innermost decorator.
    """
    for spec in reversed(_OPTION_SPECS):
        fn = spec(fn)
    return fn
