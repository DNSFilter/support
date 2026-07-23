"""The flag-combination matrix for characterization.

Each case = (name, endpoint, function, args). Names are the snapshot filenames.
Coverage targets the two surfaces a future option-table / pipeline-split
refactor would touch: request building (via --dry-run) and result
post-processing + output dispatch (via canned responses).
"""

CASES: list[tuple[str, str, str, list[str]]] = [
    # ── request building (--dry-run, no response needed) ──────────────────
    ("dryrun_create", "networks", "create", ["--name", "HQ", "--organization-id", "802315", "--dry-run"]),
    ("dryrun_create_policy_ids", "networks", "create", ["--name", "HQ", "--organization-id", "802315", "--policy-ids", '["1","2"]', "--dry-run"]),
    ("dryrun_update_pathparam", "networks", "update", ["--id", "736401", "--name", "New", "--dry-run"]),
    ("dryrun_dashed_param", "networks", "create", ["--name", "HQ", "--organization-id", "802315", "--dry-run"]),
    ("dryrun_set_merge", "networks", "create", ["--name", "HQ", "--organization-id", "802315", "--set", "external_id=abc", "--dry-run"]),
    ("dryrun_body_json", "networks", "create", ["--body-json", '{"name":"HQ","organization_id":802315}', "--dry-run"]),
    ("dryrun_bodykey_wrap", "policies", "add-blacklist-domain", ["--id", "285109", "--domain", "evil.com", "--note", "n", "--dry-run"]),
    ("dryrun_query_param", "networks", "list", ["--page", "2", "--page-size", "10", "--dry-run"]),
    ("dryrun_batch_from_csv", "networks", "create", ["--from-csv", "-", "--dry-run"]),  # stdin handled by test

    # ── batch EXECUTION (guards the --from-csv / --from-json dispatch path) ──
    ("exec_from_csv", "networks", "create", ["--from-csv", "-", "--yes", "--no-progress"]),
    ("exec_from_csv_skiprows", "networks", "create", ["--from-csv", "-", "--yes", "--no-progress", "--skip-rows", "1"]),
    ("exec_from_json", "networks", "create", ["--from-json", "-", "--yes", "--no-progress"]),
    ("exec_from_csv_batchsize", "networks", "create", ["--from-csv", "-", "--yes", "--no-progress", "--batch-size", "1"]),

    # ── table rendering (force TTY so output is NOT auto-switched to JSON) ──
    ("tty_table_default", "networks", "list", []),
    ("tty_table_columns", "networks", "list", ["--columns", "id,name,status"]),
    ("tty_table_no_wrap", "networks", "list", ["--no-wrap"]),

    # ── output modes ──────────────────────────────────────────────────────
    ("list_table", "networks", "list", []),
    ("list_json", "networks", "list", ["--json"]),
    ("list_jsonl", "networks", "list", ["--jsonl"]),
    ("list_raw", "networks", "list", ["--raw"]),
    ("list_columns", "networks", "list", ["--columns", "id,name,status"]),
    ("list_to_csv_stdout", "networks", "list", ["--to-csv", "-"]),
    ("list_to_markdown_stdout", "networks", "list", ["--to-markdown", "-"]),
    ("list_pick", "networks", "list", ["--pick", "name"]),
    ("list_format_braces", "networks", "list", ["--format", "{id} {name} {status}"]),
    ("list_format_go", "networks", "list", ["--format", "{{.name}}"]),

    # ── filtering / sorting / limiting ──────────────────────────────────────
    ("filter_eq", "networks", "list", ["--filter", "status=active"]),
    ("filter_numeric_gt", "networks", "list", ["--filter", "blocked>10"]),
    ("filter_eq_numeric_string", "networks", "list", ["--filter", "total=100"]),
    ("filter_mode_or", "networks", "list", ["--filter", "status=error", "--filter", "name~char", "--filter-mode", "or"]),
    ("grep", "networks", "list", ["--grep", "active"]),
    ("sort_desc", "networks", "list", ["--sort", "-name"]),
    ("limit", "networks", "list", ["--limit", "1"]),
    ("last", "networks", "list", ["--last", "1"]),
    ("unique", "networks", "list", ["--unique", "status"]),
    ("not_null", "networks", "list", ["--not-null", "note"]),

    # ── aggregation ─────────────────────────────────────────────────────────
    ("count", "networks", "list", ["--count"]),
    ("sum", "networks", "list", ["--sum", "blocked"]),
    ("avg", "networks", "list", ["--avg", "total"]),
    ("min", "networks", "list", ["--min", "blocked"]),
    ("max", "networks", "list", ["--max", "total"]),
    ("group_by", "networks", "list", ["--group-by", "status"]),
    ("count_by", "networks", "list", ["--count-by", "status"]),

    # ── field shaping ───────────────────────────────────────────────────────
    ("select", "networks", "list", ["--select", "id,name"]),
    ("exclude", "networks", "list", ["--exclude", "note,blocked,total"]),
    ("rename", "networks", "list", ["--rename", "name=label", "--columns", "id,label"]),
    ("add_field", "networks", "list", ["--add-field", "src=export", "--columns", "id,src"]),
    ("transform", "networks", "list", ["--transform", "ratio=blocked/total", "--columns", "id,ratio"]),
    ("map_upper", "networks", "list", ["--map", "name=upper", "--columns", "id,name"]),
    ("strip_nulls", "networks", "list", ["--strip-nulls", "--json"]),
    ("jq", "networks", "list", ["--jq", "data.0.name"]),

    # ── pagination ──────────────────────────────────────────────────────────
    ("all_pages", "networks", "list", ["--all", "--pick", "id"]),
    ("all_count", "networks", "list", ["--all", "--count"]),
    ("max_pages_truncation_warn", "networks", "list", ["--all", "--max-pages", "1", "--count"]),

    # ── guards / exit codes ─────────────────────────────────────────────────
    ("fail_on_pattern_match", "networks", "list", ["--fail-on-pattern", "status=error"]),
    ("fail_on_pattern_bad_expr", "networks", "list", ["--fail-on-pattern", "!!bad"]),
    ("fields", "networks", "list", ["--fields"]),
    ("output_schema", "networks", "list", ["--output-schema"]),

    # ── multi-org / cross-resource ──────────────────────────────────────────
    ("each_org", "networks", "list", ["--each-org", "--pick", "id"]),
    ("org_name_resolve", "networks", "list", ["--org-name", "Acme", "--count"]),
    ("join", "networks", "list", ["--join", "policies:id=id", "--columns", "id,name"]),
]

# Cases that must run as if stdout is a TTY (exercise the Rich table renderer
# and --columns filtering, which the non-TTY JSON auto-switch would bypass).
FORCE_TTY_CASES = {"tty_table_default", "tty_table_columns", "tty_table_no_wrap"}

# Cases whose argv reads from stdin ('-'); the test supplies this text as stdin.
STDIN_CSV = {
    "dryrun_batch_from_csv": "name\nHQ\n",
    "exec_from_csv": "name\nHQ\nBranch\n",
    "exec_from_csv_skiprows": "name\nHQ\nBranch\n",
    "exec_from_json": '[{"name": "HQ"}, {"name": "Branch"}]',
    "exec_from_csv_batchsize": "name\nHQ\nBranch\n",
}
