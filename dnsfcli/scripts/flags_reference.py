"""Canonical global-flag reference shared by all three doc build scripts.

Update this file when flags change; every rebuilt guide picks it up.
"""

FLAG_GROUPS: list[tuple[str, list[tuple[str, str]]]] = [
    ("Output & format", [
        ("--raw, -r",           "Print the raw JSON response instead of the formatted table."),
        ("--json / --jsonl",    "JSON (or one object per line) on stdout. Automatic when output is piped."),
        ("--output FMT",        "Unified format switch: table, json, jsonl, raw, csv, or none."),
        ("--columns a,b,c",     "Limit table/CSV output to the named columns."),
        ("--preset NAME",       "Apply a named column preset from config (column_presets.NAME)."),
        ("--format TMPL",       "Render each row through a template — both \"{name} ({id})\" and \"{{.name}}\" styles work."),
        ("--format-preset N",   "Apply a named format template from config (format_presets.NAME)."),
        ("--bundle NAME",       "Apply a named command bundle from config (columns + filter + sort + format)."),
        ("--pick FIELD",        "Print a single field, one value per line — ideal for piping."),
        ("--jq PATH",           "Extract a dotted path (data.0.name) from the response before output."),
        ("--to-csv FILE",       "Write the response to FILE as CSV (use - for stdout)."),
        ("--to-json FILE",      "Write the response to FILE as JSON."),
        ("--to-markdown FILE",  "Write the response to FILE as a Markdown table (use - for stdout)."),
        ("--tee FILE",          "Save a copy of everything printed to FILE."),
        ("--quiet, -q",         "Suppress status chatter; result data still prints."),
        ("--no-color",          "Disable ANSI colour output (NO_COLOR env also honoured)."),
    ]),
    ("Filtering, sorting & aggregation", [
        ("--filter EXPR",       "Keep matching rows: field=value, field!=value, field~substr, field>N, >=, <, <=."),
        ("--filter-mode or",    "OR logic across multiple --filter flags (default: AND)."),
        ("--grep REGEX",        "Keep rows where any field matches the regex."),
        ("--unique FIELD",      "Drop rows with a duplicate value in FIELD."),
        ("--sort FIELD",        "Sort by field; prefix with - for descending (--sort -created_at)."),
        ("--limit N / --last N","Return at most N results / the last N results."),
        ("--count",             "Print the result count only."),
        ("--count-by FIELD",    "Frequency table of FIELD values."),
        ("--group-by FIELD",    "Group results by FIELD value."),
        ("--sum / --avg / --min / --max F", "Aggregate a numeric field and print one value."),
        ("--select a,b / --exclude a,b",    "Keep only (or remove) the named fields from every item."),
        ("--not-null F / --is-null F",      "Keep rows where FIELD is (or is not) null."),
    ]),
    ("Pagination", [
        ("--all",               "Fetch every page of paginated results."),
        ("--page N / --page-size N", "Request a specific page / page size."),
        ("--max-pages N",       "Cap the number of pages fetched by --all."),
        ("--paginate-until E",  "Stop --all pagination once any item matches filter expression E."),
    ]),
    ("Batch & CSV input", [
        ("--from-csv FILE",     "Read input rows from FILE — one API call per row (use - for stdin)."),
        ("--template",          "Print a blank CSV import template for this command and exit. No auth needed."),
        ("--skip-rows N / --max-rows N", "Resume an interrupted batch / cap rows processed."),
        ("--batch-report FILE", "Write a JSON run summary (per-row outcomes, counts) to FILE."),
        ("--on-error MODE",     "stop or continue when a batch row fails."),
        ("--errors-to-csv FILE","Write failed rows to FILE for later retry (--retry-errors-csv)."),
        ("--confirm-each",      "Prompt before each batch row."),
        ("--validate-only",     "Validate the CSV and exit without calling the API."),
        ("--dry-run / --plan",  "Show what would be sent without making any API calls."),
        ("--yes, -y",           "Skip confirmation prompts."),
    ]),
    ("Transformation", [
        ("--add-field K=V",     "Inject a static field into every result item."),
        ("--transform F=EXPR",  "Compute a new field from a restricted expression (ratio=blocked/total)."),
        ("--map FIELD=OP",      "Transform a field value: upper, lower, strip, title, truncate:N."),
        ("--join EP:LK=RK",     "Client-side join: fetch endpoint EP, match local key LK to remote key RK."),
        ("--rename A=B",        "Rename field A to B in the output."),
        ("--flatten",           "Flatten nested objects into dotted keys."),
        ("--strip-nulls",       "Remove null-valued keys from every item."),
    ]),
    ("Multi-organization", [
        ("--each-org",          "Run the command once per organization on the account."),
        ("--org-csv FILE",      "Load the --each-org organization list from a CSV file."),
        ("--org-filter REGEX",  "Restrict --each-org to organizations whose name matches."),
        ("--max-orgs N",        "Cap the number of organizations processed."),
        ("--parallel-orgs",     "Process organizations concurrently (--org-concurrency N)."),
    ]),
    ("Watch, monitor & CI", [
        ("--watch N",           "Re-run the command every N seconds (Ctrl-C to stop)."),
        ("--watch-until EXPR",  "Stop watching once any result matches the filter expression."),
        ("--watch-diff",        "Show only what changed between watch ticks."),
        ("--alert EXPR",        "Ring the terminal bell and print a banner when a result matches."),
        ("--fail-on-empty",     "Exit 1 when the result list is empty (messages go to stderr)."),
        ("--fail-on-pattern E", "Exit 1 when any result row matches filter expression E."),
        ("--exec CMD",          "Run a shell command per result row with {field} substitution (values are shell-quoted)."),
    ]),
    ("Connection & authentication", [
        ("--api-key TOKEN",     "Override the keychain token for this call only (prefer DNSF_API_KEY)."),
        ("--org-id ID",         "Override the stored organization ID for this call only."),
        ("--profile NAME",      "Use a named credential profile."),
        ("--timeout N / --connect-timeout N", "Read / connect timeouts in seconds."),
        ("--rate N",            "Client-side request-per-second cap."),
        ("--retry N",           "Retry attempts for failed batch rows."),
        ("--header K=V",        "Add a custom request header (scrubbed from history logs)."),
        ("--proxy URL",         "Route requests through a proxy (scrubbed from history logs)."),
        ("--env-file FILE",     "Load KEY=VALUE pairs into the environment before running."),
        ("--cache-ttl N",       "Serve identical GETs from a local cache for N seconds."),
    ]),
]


def _esc(t: str) -> str:
    return t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def render_flag_table_html() -> str:
    """Categorized brand-styled HTML table used by the PDF/MD/DOCX renderers."""
    td = 'padding:4px 9px; border-bottom:1px solid #e5e5e5;'
    rows = []
    for group, flags in FLAG_GROUPS:
        rows.append(
            f'<tr><td colspan="2" style="padding:8px 9px 4px; font-weight:bold; '
            f'font-size:0.95em; color:#3427fd; border-bottom:2px solid #3427fd;">{_esc(group)}</td></tr>'
        )
        for flag, desc in flags:
            rows.append(
                f'<tr><td style="{td} font-family:monospace; white-space:nowrap;">{_esc(flag)}</td>'
                f'<td style="{td}">{_esc(desc)}</td></tr>'
            )
    return (
        '<table style="width:100%; border-collapse:collapse; font-size:0.78em; margin:0.8em 0;">\n'
        '<tbody>\n' + "\n".join(rows) + '\n</tbody>\n</table>\n'
    )
