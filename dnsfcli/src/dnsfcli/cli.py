"""Typer-based CLI for the DNSFilter API.

Command format:
    dnsfcli [endpoint] [function] [--param value ...]

Examples:
    dnsfcli auth setup
    dnsfcli users list
    dnsfcli users show --id 42
    dnsfcli networks create --name "HQ" --policy_id 7
    dnsfcli policies update --id 3 --name "Strict"
    dnsfcli networks delete --id 9
    dnsfcli query_logs list --start 2024-01-01 --end 2024-01-02
"""

from __future__ import annotations

import logging
import os
import sys
from typing import Any, Optional

import typer
from rich.table import Table

from .auth import (
    KeychainError,
    get_active_profile,
    get_api_key,
    get_base_url,
    get_org_id,
)
from .audit import log_event, log_history
from .client import APIError, DNSFilterClient
from .config import load_config
from .endpoints import get_operation, list_endpoints, list_functions
from .output import (
    _unwrap,
    console,
    err_console,
    is_quiet,
    print_error,
    print_info,
    print_response,
    print_success,
    print_warning,
    set_output_options,
    tee_write,
    write_csv,
    write_json,
)
from .cliparams import (
    RESERVED_CLI_FLAGS,
    _build_path,
    _coerce_value,
    _load_env_file,
    _normalize_param_keys,
    _parse_extra_args,
    resolve_http_context,
    sanitize_path_component,
)
from .batch import _create_ips_from_cidr, dispatch_from_csv, dispatch_from_json
from .pagination import _fetch_all_pages, _warn_if_partial
from .runopts import RunOptions
from .jobs import _wait_for_job
from .preview import (
    _confirm_destructive,
    _show_dry_run,
    _show_plan,
)
from .postprocess import (
    _WatchUntilSatisfied,
    _apply_count_by,
    _apply_exclude,
    _apply_filters,
    _apply_flatten,
    _apply_grep,
    _apply_group_by,
    _apply_jq,
    _apply_map_fields,
    _apply_max,
    _apply_min,
    _apply_avg,
    _apply_null_as,
    _apply_pick,
    _apply_renames,
    _apply_select,
    _apply_sum,
    _apply_transforms,
    _apply_unique,
    _compute_stats,
    _enrich_domain_result,
    _render_format_template,
    _show_watch_diff,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------





# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

from .apps import app
# The sub-apps (auth_app, config_app, …) live in apps.py and are wired to `app`
# there; the command modules attach their handlers by importing those objects
# from .apps directly. Importing the commands package (at the bottom of this
# module, to avoid an import cycle) runs those module-level Typer decorators and
# so registers every sub-command.

# ---------------------------------------------------------------------------
# Argument parsing helpers
# ---------------------------------------------------------------------------












# ---------------------------------------------------------------------------
# auth sub-commands
# ---------------------------------------------------------------------------






















# ---------------------------------------------------------------------------
# audit sub-commands
# ---------------------------------------------------------------------------








# ---------------------------------------------------------------------------
# endpoints sub-command (discovery / help)
# ---------------------------------------------------------------------------




# ---------------------------------------------------------------------------
# doctor — diagnostics / health check
# ---------------------------------------------------------------------------




# ---------------------------------------------------------------------------
# lookupdomain — human-readable domain classification
# ---------------------------------------------------------------------------




# ---------------------------------------------------------------------------
# Main dynamic API command
# ---------------------------------------------------------------------------


@app.command(
    "call",
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
    hidden=True,
)
def _explicit_call(
    ctx: typer.Context,
    endpoint: str = typer.Argument(..., help="API endpoint (e.g. users, networks)."),
    function: str = typer.Argument(..., help="Function (list, show, create, update, delete)."),
    raw: bool = typer.Option(False, "--raw", "-r", help="Print raw JSON response."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable verbose/debug logging."),
    api_key: Optional[str] = typer.Option(None, "--api-key", envvar="DNSF_API_KEY", help="Override stored API key.", show_default=False),
    org_id: Optional[str] = typer.Option(None, "--org-id", envvar="DNSF_ORG_ID", help="Override stored org ID.", show_default=False),
) -> None:
    """Explicit call sub-command (alias for the default positional form)."""
    _run_api_call(ctx, endpoint, function, RunOptions(raw=raw, verbose=verbose, api_key=api_key, org_id=org_id))


@app.callback(invoke_without_command=True)
def _main_callback(
    ctx: typer.Context,
    version: bool = typer.Option(False, "--version", is_eager=True, help="Show version and exit."),
) -> None:
    if version:
        from . import __version__
        console.print(f"dnsfcli {__version__}")
        raise typer.Exit()


# ---------------------------------------------------------------------------
# Destructive-operation confirmation
# ---------------------------------------------------------------------------

















































# ---------------------------------------------------------------------------
# The workhorse: build and fire the API request
# ---------------------------------------------------------------------------






















# ---------------------------------------------------------------------------
# Async job polling helpers (used by --wait)
# ---------------------------------------------------------------------------

# Status values that mean the job is done (success or failure).



























# Endpoints whose GET responses contain secret key material — never written to
# the on-disk response cache, even under --cache-ttl.
_SECRET_RESPONSE_ENDPOINTS = frozenset({"api-keys"})


def _coerce_org_id(value: str) -> Any:
    """Coerce an organization id for the request body.

    The DNSFilter API models organization_id as an integer, so numeric values
    are sent as ints. A non-numeric stored/env/--org-id value is passed through
    unchanged rather than crashing with 'invalid literal for int()' — the server
    then validates it and returns a clean error.
    """
    s = str(value).strip()
    return int(s) if s.isdigit() else s


def _run_api_call(
    ctx: typer.Context,
    endpoint: str,
    function: str,
    opts: "RunOptions",
) -> None:
    # Unpack RunOptions into locals; the body below is unchanged, so this
    # is a pure rebinding (no behavior change vs the old 100+-param form).
    raw = opts.raw
    verbose = opts.verbose
    api_key = opts.api_key
    org_id = opts.org_id
    csv_file = opts.csv_file
    csv_input = opts.csv_input
    show_template = opts.show_template
    show_plan = opts.show_plan
    skip_confirm = opts.skip_confirm
    columns = opts.columns
    wait = opts.wait
    profile = opts.profile
    fetch_all = opts.fetch_all
    as_json = opts.as_json
    sort_by = opts.sort_by
    limit = opts.limit
    json_file = opts.json_file
    timeout = opts.timeout
    filters = opts.filters
    count_only = opts.count_only
    body_json = opts.body_json
    page = opts.page
    page_size = opts.page_size
    as_jsonl = opts.as_jsonl
    on_error = opts.on_error
    concurrency = opts.concurrency
    grep = opts.grep
    unique_field = opts.unique_field
    format_template = opts.format_template
    csv_append = opts.csv_append
    dry_run = opts.dry_run
    json_input = opts.json_input
    cache_ttl = opts.cache_ttl
    org_name = opts.org_name
    set_fields = opts.set_fields
    exclude_fields = opts.exclude_fields
    merge_key = opts.merge_key
    rate = opts.rate
    truncate = opts.truncate
    csv_delimiter = opts.csv_delimiter
    rename_fields = opts.rename_fields
    pick_field = opts.pick_field
    batch_size = opts.batch_size
    no_header = opts.no_header
    csv_header_case = opts.csv_header_case
    retry = opts.retry
    errors_csv = opts.errors_csv
    retry_errors_csv = opts.retry_errors_csv
    timing = opts.timing
    group_by = opts.group_by
    select_fields = opts.select_fields
    sum_field = opts.sum_field
    avg_field = opts.avg_field
    min_field = opts.min_field
    max_field = opts.max_field
    map_fields = opts.map_fields
    watch_changes_interval = opts.watch_changes_interval
    upsert = opts.upsert
    last = opts.last
    sample = opts.sample
    fields_only = opts.fields_only
    strip_nulls = opts.strip_nulls
    max_pages = opts.max_pages
    max_errors = opts.max_errors
    null_as = opts.null_as
    no_wrap = opts.no_wrap
    color_rules = opts.color_rules
    count_by = opts.count_by
    not_null_field = opts.not_null_field
    is_null_field = opts.is_null_field
    since_filter = opts.since_filter
    extra_headers = opts.extra_headers
    insecure = opts.insecure
    no_progress = opts.no_progress
    tee_file = opts.tee_file
    validate_only = opts.validate_only
    confirm_each = opts.confirm_each
    diff_mode = opts.diff_mode
    skip_rows = opts.skip_rows
    max_rows = opts.max_rows
    add_fields = opts.add_fields
    paginate_until = opts.paginate_until
    batch_report = opts.batch_report
    org_csv = opts.org_csv
    color_scale = opts.color_scale
    format_preset = opts.format_preset
    flatten = opts.flatten
    strip_empties = opts.strip_empties
    csv_null_value = opts.csv_null_value
    watch_until_filter = opts.watch_until_filter
    fail_on_empty = opts.fail_on_empty
    batch_delay = opts.batch_delay
    connect_timeout = opts.connect_timeout
    proxy = opts.proxy
    jq_expr = opts.jq_expr
    max_wait = opts.max_wait
    alert_filter = opts.alert_filter
    stats_field = opts.stats_field
    result_sink = opts.result_sink
    stdin_json = opts.stdin_json
    fail_on_pattern = opts.fail_on_pattern
    filter_mode = opts.filter_mode
    to_markdown = opts.to_markdown
    output_schema = opts.output_schema
    exec_cmd = opts.exec_cmd
    transforms = opts.transforms
    join_spec = opts.join_spec
    if verbose:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.WARNING)

    # --truncate / --no-wrap / --color-if / --tee / --csv-null: apply early so all output respects it
    if truncate is not None or no_wrap or color_rules or tee_file or csv_null_value is not None or color_scale:
        set_output_options(truncate=truncate, no_wrap=no_wrap, color_rules=color_rules or [], tee=tee_file, csv_null_value=csv_null_value, color_scale=color_scale)

    # Resolve timeout: explicit CLI value > config file > hardcoded default
    cfg = load_config()
    effective_timeout = timeout if timeout is not None else cfg.timeout

    # Config-based column defaults (CLI --columns overrides)
    if columns is None and endpoint in cfg.columns:
        columns = cfg.columns[endpoint]

    operation = get_operation(endpoint, function)

    # --template: print a blank CSV and exit -- no auth or network needed
    if show_template:
        from .csv_io import generate_template
        sys.stdout.write(generate_template(operation, endpoint, function))
        return

    # --plan with no CSV needs no auth either (CSV validation may need it for
    # accurate row counts, but a basic plan is still useful without a key).
    # Only applies to write operations — GET is read-only, nothing to plan.
    if show_plan and not csv_input and operation.method in ("POST", "PATCH", "PUT", "DELETE"):
        resolved_org_early = org_id or get_org_id(profile=profile)
        extra_early: dict[str, str] = _parse_extra_args(ctx.args)
        params_early: dict[str, Any] = {k: _coerce_value(v) for k, v in extra_early.items()}
        for flag in RESERVED_CLI_FLAGS:
            params_early.pop(flag, None)
        params_early = _normalize_param_keys(params_early)
        if resolved_org_early and "organization_id" not in params_early:
            if any(p.name == "organization_id" for p in operation.params):
                params_early["organization_id"] = _coerce_org_id(resolved_org_early)
        _show_plan(endpoint, function, operation, params_early, None)
        return

    # Resolve credentials + base URL and build the shared client kwargs
    # (warnings + missing-key / non-HTTPS exits happen inside).
    resolved_key, resolved_org, base_url, _ck_base = resolve_http_context(opts)

    # --since FIELD DATE: translate to an extra --filter FIELD>=DATE entry
    if since_filter:
        _sf_parts = since_filter.split(None, 1)
        if len(_sf_parts) == 2:
            _sf_field, _sf_date = _sf_parts
            import re as _re_since
            if not _re_since.match(r'^\d{4}-\d{2}-\d{2}(T[\d:+Z.-]+)?$', _sf_date):
                print_warning(f"--since: date {_sf_date!r} is not in YYYY-MM-DD format; passing through as-is")
            filters = list(filters or []) + [f"{_sf_field}>={_sf_date}"]
        else:
            print_warning(f"--since: expected 'FIELD DATE', got {since_filter!r}")

    # --org-name: resolve a name pattern → org ID before parsing extra args
    if org_name and not org_id:
        try:
            with DNSFilterClient(**{**_ck_base, "timeout": effective_timeout}) as _cl:
                # Paginate: the match must consider every org, not just page 1,
                # or a name on page 2+ yields a false "no organization matches".
                _orgs_raw, _orgs_items = _fetch_all_pages(
                    _cl, "GET", "/v1/organizations", None, None, show_progress=False,
                )
            _orgs = _orgs_items if _orgs_items else _unwrap(_orgs_raw)
            if not isinstance(_orgs, list):
                _orgs = [_orgs_raw] if isinstance(_orgs_raw, dict) else []
            import re as _re_orgname
            _matches = [
                o for o in _orgs
                if isinstance(o, dict) and _re_orgname.search(
                    org_name,
                    str((o.get("attributes") or {}).get("name") or o.get("name") or ""),
                    _re_orgname.IGNORECASE,
                )
            ]
            if not _matches:
                print_error(f"--org-name: no organization matches {org_name!r}")
                sys.exit(1)
            if len(_matches) > 1:
                names = ", ".join(
                    str((o.get("attributes") or {}).get("name") or o.get("name") or o.get("id"))
                    for o in _matches
                )
                print_error(f"--org-name: {len(_matches)} organizations match {org_name!r}: {names}")
                sys.exit(1)
            resolved_org = str(_matches[0].get("id", ""))
        except APIError as exc:
            print_error(f"--org-name: failed to list organizations: {exc}")
            sys.exit(1)

    # operation is already resolved above (before the show_template check)

    # Parse caller-supplied --key value pairs from ctx.args
    extra: dict[str, str] = _parse_extra_args(ctx.args)
    params: dict[str, Any] = {k: _coerce_value(v) for k, v in extra.items()}

    # --stdin-json: read entire stdin as JSON and merge into request params
    if stdin_json:
        import json as _json_stdin
        if sys.stdin.isatty():
            err_console.print("[dim]Reading JSON from stdin — press Ctrl-D when done…[/dim]")
        _stdin_raw = sys.stdin.read().strip()
        if _stdin_raw:
            try:
                _stdin_body = _json_stdin.loads(_stdin_raw)
                if isinstance(_stdin_body, dict):
                    params.update(_stdin_body)
                else:
                    print_warning("--stdin-json: top-level value must be a JSON object ({…}); ignored.")
            except _json_stdin.JSONDecodeError as _sj_exc:
                print_warning(f"--stdin-json: invalid JSON on stdin: {_sj_exc}")
    # Stdin chaining: any param value of "-" is replaced with a line read from stdin.
    # Enables: dnsfcli networks list --pick id | dnsfcli networks show --id -
    # (skipped when --stdin-json is active since stdin is already consumed)
    elif "-" in params.values():
        _stdin_lines = [ln.strip() for ln in sys.stdin.read().splitlines() if ln.strip()]
        _stdin_line = _stdin_lines[0] if _stdin_lines else ""
        if len(_stdin_lines) > 1:
            print_warning(
                f"stdin had {len(_stdin_lines)} values but '-' takes only the first "
                f"({_stdin_line!r}). To act on every value, loop in the shell or use --from-csv."
            )
        params = {k: (_stdin_line if v == "-" else v) for k, v in params.items()}

    # Remove our own reserved flags that may have leaked in
    for flag in RESERVED_CLI_FLAGS:
        params.pop(flag, None)
    params = _normalize_param_keys(params)

    # Note: CSV column aliases (fqdns→domain, notes→note, etc.) are handled in
    # csv_io._COL_ALIASES, validated against each operation's actual params.
    # We deliberately avoid CLI-level param aliases here — they would remap
    # params globally and break any endpoint whose spec param IS the aliased
    # name (e.g. policies add-blacklist-domain uses --domain, not --fqdn).

    # Inject org_id into params if the operation can use it and none provided
    if resolved_org and "organization_id" not in params:
        if any(p.name == "organization_id" for p in operation.params):
            params["organization_id"] = _coerce_org_id(resolved_org)

    # --page / --page-size: manual pagination — inject as query params
    if page is not None:
        params["page[number]"] = page
    if page_size is not None:
        params["page[size]"] = page_size

    # --merge-key FIELD: look up the resource id by matching FIELD value
    if merge_key and "id" not in params:
        import re as _mk_re
        _mk_field = merge_key.strip()
        _mk_val = params.get(_mk_field)
        if _mk_val is None:
            print_error(f"--merge-key: no value for field '{_mk_field}' in current params.")
            sys.exit(1)
        _mk_list_path = _mk_re.sub(r"/\{[^/]+\}$", "", operation.path_template)
        _mk_query: dict[str, Any] = {}
        if resolved_org and any(p.name == "organization_id" for p in operation.params):
            _mk_query["organization_id"] = resolved_org
        try:
            with DNSFilterClient(**{**_ck_base, "org_id": resolved_org, "timeout": effective_timeout, "rate": rate}) as _mk_cl:
                # Paginate: scan every page for the matching row, or a resource
                # on page 2+ reports a false "no {endpoint} found" — and with
                # --upsert that turns into a spurious duplicate create.
                _mk_raw, _mk_all = _fetch_all_pages(
                    _mk_cl, "GET", _mk_list_path, _mk_query or None, None, show_progress=False,
                )
            _mk_items = _mk_all if _mk_all else _unwrap(_mk_raw)
            if not isinstance(_mk_items, list):
                print_error(f"--merge-key: expected a list from {_mk_list_path}; got unexpected format.")
                sys.exit(1)
            for _mk_item in _mk_items:
                if not isinstance(_mk_item, dict):
                    continue
                if str(_mk_item.get(_mk_field, "")).lower() == str(_mk_val).lower():
                    params["id"] = _mk_item["id"]
                    if verbose:
                        print_info(f"--merge-key: {_mk_field}={_mk_val!r} → id={params['id']}")
                    break
            else:
                print_error(f"--merge-key: no {endpoint} found where {_mk_field}={_mk_val!r}")
                sys.exit(1)
        except APIError as exc:
            print_error(f"--merge-key: failed to list {endpoint}: {exc}")
            sys.exit(1)

    # --plan: show a dry-run summary and exit — only meaningful for write ops
    if show_plan:
        if operation.method in ("POST", "PATCH", "PUT", "DELETE"):
            _show_plan(endpoint, function, operation, params, csv_input)
        else:
            console.print(
                f"[yellow]--plan is only available for write operations "
                f"(POST/PATCH/PUT/DELETE). "
                f"{endpoint} {function} is a {operation.method} — "
                f"it reads data and makes no changes.[/yellow]"
            )
        return

    # --retry-errors-csv: treat the errors file as the csv input
    if retry_errors_csv and not csv_input:
        csv_input = retry_errors_csv

    # --from-csv: validate the file then loop over rows (dispatch in batch.py)
    if csv_input:
        dispatch_from_csv(
            csv_input, opts=opts, operation=operation, endpoint=endpoint,
            function=function, params=params,
            client_kwargs={**_ck_base, "org_id": resolved_org, "timeout": effective_timeout, "rate": rate},
            resolved_org=resolved_org, columns=columns,
        )
        return

    # --from-json: batch from a JSON array, one API call per object (dispatch in batch.py)
    if json_input:
        dispatch_from_json(
            json_input, opts=opts, operation=operation, endpoint=endpoint,
            function=function, params=params,
            client_kwargs={**_ck_base, "org_id": resolved_org, "timeout": effective_timeout, "rate": rate},
            resolved_org=resolved_org, columns=columns,
        )
        return

    # Validate required non-path params before making the API call.
    # (Path params are checked inside _build_path; query/body must be checked here.)
    missing_required = [
        p.name for p in operation.params
        if p.required and p.kind != "path" and p.name not in params
    ]
    if missing_required:
        for name in missing_required:
            p_obj = next(p for p in operation.params if p.name == name)
            print_error(
                f"Required {'query' if p_obj.kind == 'query' else 'body'} parameter "
                f"[bold]--{name}[/bold] was not provided.",
                f"Type: {p_obj.type_hint}  Description: {p_obj.description}",
            )
        sys.exit(1)

    # Build the URL path, consuming path params from `params`
    path, remaining = _build_path(operation.path_template, params)

    # Split remaining into query params vs body based on HTTP method
    method = operation.method
    query_params: dict[str, Any] = {}
    body_params: dict[str, Any] = {}

    # Determine expected kinds from the registry definition when available
    known_param_kinds: dict[str, str] = {p.name: p.kind for p in operation.params}

    for key, val in remaining.items():
        kind = known_param_kinds.get(key)
        if kind == "query" or (kind is None and method in ("GET", "DELETE")):
            query_params[key] = val
        else:
            body_params[key] = val

    # CIDR expansion: if ip-addresses create receives an address with a '/' prefix,
    # expand it to individual host IPs and loop one create call per address.
    if (endpoint == "ip-addresses" and function == "create"
            and "/" in str(body_params.get("address", ""))):
        cidr = str(body_params.pop("address"))
        if dry_run:
            import ipaddress as _ipa
            try:
                _net = _ipa.ip_network(cidr, strict=False)
                _hostcount = _net.num_addresses
            except ValueError:
                _hostcount = "?"
            print_info(
                f"[dry-run] Would expand CIDR {cidr} and POST up to {_hostcount} "
                f"ip-address record(s); no requests sent."
            )
            return
        with DNSFilterClient(**{**_ck_base, "org_id": resolved_org, "timeout": effective_timeout, "rate": rate}) as client:
            _create_ips_from_cidr(
                cidr, body_params, client,
                verbose=verbose, csv_output=csv_file, columns=columns,
                org_id=resolved_org,
            )
        return

    # Wrap body params under a resource key when the endpoint requires it.
    # When top_level=True params are present, they stay at root; others go under body_key.
    json_body: dict[str, Any] | None = None
    if body_params or operation.body_key:
        if operation.body_key:
            top_names = {p.name for p in operation.params if p.top_level}
            top = {k: v for k, v in body_params.items() if k in top_names}
            nested = {k: v for k, v in body_params.items() if k not in top_names}
            json_body = {**top, operation.body_key: nested}
        else:
            json_body = body_params

    # --set FIELD=VALUE: merge individual field overrides into the request body
    if set_fields:
        for _expr in set_fields:
            if "=" not in _expr:
                print_error(f"--set: expected FIELD=VALUE, got {_expr!r}")
                sys.exit(1)
            _sf_key, _, _sf_val = _expr.partition("=")
            body_params[_sf_key.strip()] = _coerce_value(_sf_val.strip())
        # Rebuild json_body to include the new fields
        if operation.body_key:
            top_names = {p.name for p in operation.params if p.top_level}
            top = {k: v for k, v in body_params.items() if k in top_names}
            nested = {k: v for k, v in body_params.items() if k not in top_names}
            json_body = {**top, operation.body_key: nested}
        else:
            json_body = body_params if body_params else json_body

    # --body-json: merge raw JSON string (or @file.json) into the request body
    if body_json is not None:
        import json as _json
        raw_src = body_json.strip()
        if raw_src.startswith("@"):
            _bj_filename = raw_src[1:]
            try:
                if _bj_filename == "-":
                    raw_src = sys.stdin.read()
                else:
                    with open(_bj_filename, encoding="utf-8") as _bj_fh:
                        raw_src = _bj_fh.read()
            except OSError as exc:
                print_error(f"--body-json: cannot read file: {exc}")
                sys.exit(1)
        try:
            extra_body = _json.loads(raw_src)
        except _json.JSONDecodeError as exc:
            print_error(f"--body-json: invalid JSON: {exc}")
            sys.exit(1)
        if not isinstance(extra_body, dict):
            print_error("--body-json: top-level value must be a JSON object ({...}).")
            sys.exit(1)
        # Merge: --body-json takes precedence over individual --key value flags
        json_body = {**(json_body or {}), **extra_body}

    if method == "DELETE" or operation.destructive:
        _confirm_destructive(
            f"About to run [bold]{endpoint} {function}[/bold] "
            f"([dim]{method} {path}[/dim]).",
            skip_confirm,
        )

    if verbose:
        from .audit import mask_secret_keys as _mask_body
        print_info(f"[dim]{method}[/dim] {base_url}{path}")
        if query_params:
            # Redact secret-named params (query and body) so nothing sensitive is
            # printed or, under --tee, written to the tee file.
            print_info(f"Query: {_mask_body(query_params)}")
        if json_body:
            print_info(f"Body:  {_mask_body(json_body)}")

    # --dry-run: show the resolved request and exit without making any API call
    if dry_run:
        _show_dry_run(method, base_url, path, query_params, json_body)
        return

    with DNSFilterClient(**{**_ck_base, "org_id": resolved_org, "timeout": effective_timeout, "rate": rate}) as client:
        try:
            result: Any = None
            _from_cache = False

            # Never persist responses that contain key material to disk, even
            # with --cache-ttl (api-keys endpoints return secret values).
            _cache_ok = bool(cache_ttl) and method == "GET" and endpoint not in _SECRET_RESPONSE_ENDPOINTS
            if cache_ttl and method == "GET" and endpoint in _SECRET_RESPONSE_ENDPOINTS:
                print_warning(
                    f"--cache-ttl ignored for '{endpoint}': responses contain secret "
                    f"key material and are never written to the on-disk cache."
                )

            # --cache-ttl: serve GET from cache if still fresh
            if _cache_ok:
                from . import cache as _cache_mod
                import hashlib as _hl_cache
                # Scope the cache entry to the credential + host so a response
                # cached under one API key/account is never served to another.
                _cred_scope = _hl_cache.sha256(
                    f"{resolved_key}\x00{base_url}".encode()
                ).hexdigest()[:16]
                _ck = _cache_mod.make_key(endpoint, function, path, query_params, cred_scope=_cred_scope)
                _cached = _cache_mod.get(_ck, cache_ttl)
                if _cached is not None:
                    if verbose:
                        print_info(f"Cache hit (ttl={cache_ttl}s): {_ck}")
                    result = _cached
                    _from_cache = True

            # Track effective method/path (may change if --upsert falls back to PATCH)
            _eff_method = method
            _eff_path = path

            if not _from_cache:
                import time as _t_mod
                _t0 = _t_mod.perf_counter() if timing else 0.0
                # --all: fetch every page and merge the items
                if fetch_all and method == "GET":
                    result, all_items = _fetch_all_pages(
                        client, method, path, query_params or None, json_body,
                        limit=limit, max_pages=max_pages, verbose=verbose,
                        show_progress=not no_progress and not (as_json or as_jsonl or format_template is not None),
                        paginate_until=paginate_until,
                    )
                    if all_items:
                        if isinstance(result, dict):
                            result = {**result, "data": all_items}
                        else:
                            result = all_items
                elif upsert and method == "POST":
                    try:
                        result = client.request("POST", path, params=query_params or None, json=json_body)
                    except APIError as _upsert_exc:
                        if _upsert_exc.status_code != 409:
                            raise
                        # Extract the existing resource ID from the 409 body
                        _upsert_id: Any = None
                        if isinstance(_upsert_exc.body, dict):
                            _ub = _upsert_exc.body
                            _upsert_id = (
                                _ub.get("id")
                                or (_ub.get("data") or {}).get("id")
                                or (_unwrap(_ub) or {}).get("id") if isinstance(_unwrap(_ub), dict) else None
                            )
                        if _upsert_id is None:
                            print_error(
                                "--upsert: POST returned 409 but the response body has no 'id' "
                                "field. Add --merge-key FIELD to pre-resolve the existing resource ID."
                            )
                            sys.exit(1)
                        _eff_path = f"{path}/{_upsert_id}"
                        _eff_method = "PATCH"
                        if verbose:
                            print_info(f"--upsert: 409 conflict (id={_upsert_id}) → PATCH {base_url}{_eff_path}")
                        result = client.request("PATCH", _eff_path, json=json_body)
                else:
                    result = client.request(
                        method,
                        path,
                        params=query_params or None,
                        json=json_body,
                    )
                if timing:
                    _ms = int((_t_mod.perf_counter() - _t0) * 1000)
                    err_console.print(f"[dim]{_eff_method} {_eff_path} — {_ms}ms[/dim]")

                # Store result in cache for subsequent calls
                if _cache_ok:
                    _cache_mod.put(_ck, result)

            log_event(endpoint, function, _eff_method, _eff_path, 200, resolved_org)
            log_history(endpoint, function, _eff_method, _eff_path, 200, resolved_org, argv=sys.argv[1:])

            # Enrich domain responses: resolve category / application IDs → names.
            # Applies to domains/user-lookup and domains/bulk-lookup so users see
            # "Information Technology" instead of "(1 item)" / "(N items)".
            if endpoint == "domains" and function in ("user-lookup", "bulk-lookup") and not raw:
                result = _enrich_domain_result(result, client)

            # --filter / --grep / --unique / --sort / --limit / --last / --sample / --exclude / --rename / --select / --group-by / --count-by / --not-null / --is-null / --map / --add-field / --transform / --join post-processing
            if (filters or grep or unique_field or sort_by or exclude_fields or rename_fields or select_fields or group_by or count_by or not_null_field or is_null_field or map_fields or add_fields or transforms or join_spec or last is not None or sample is not None or (limit is not None and not fetch_all)) and not isinstance(result, str):
                payload = _unwrap(result)
                if isinstance(payload, list):
                    if filters:
                        try:
                            before = len(payload)
                            payload = _apply_filters(payload, filters, mode=filter_mode)
                            if verbose:
                                _fmode = f"[OR]" if filter_mode == "or" else ""
                                print_info(f"Filter{_fmode}: {before} → {len(payload)} item(s) matched.")
                        except ValueError as exc:
                            print_error(str(exc))
                            sys.exit(1)
                    if not_null_field:
                        before = len(payload)
                        payload = [item for item in payload if isinstance(item, dict) and item.get(not_null_field) is not None]
                        if verbose:
                            print_info(f"Not-null '{not_null_field}': {before} → {len(payload)} item(s).")
                    if is_null_field:
                        before = len(payload)
                        payload = [item for item in payload if isinstance(item, dict) and item.get(is_null_field) is None]
                        if verbose:
                            print_info(f"Is-null '{is_null_field}': {before} → {len(payload)} item(s).")
                    if grep:
                        before = len(payload)
                        payload = _apply_grep(payload, grep)
                        if verbose:
                            print_info(f"Grep: {before} → {len(payload)} item(s) matched.")
                    if unique_field:
                        before = len(payload)
                        payload = _apply_unique(payload, unique_field)
                        if verbose:
                            print_info(f"Unique: {before} → {len(payload)} distinct value(s).")
                    if sort_by:
                        def _sort_key(v: Any) -> tuple:
                            # Type-ranked so a field that is a number on some rows
                            # and a string on others never triggers a TypeError
                            # ('<' not supported between str and int). Nulls sort
                            # first; the heterogeneous last element is only ever
                            # compared within the same rank (same type).
                            if v is None:
                                return (0, 0, 0.0)
                            if isinstance(v, bool):
                                return (1, 0, float(v))
                            if isinstance(v, (int, float)):
                                return (1, 1, float(v))
                            return (1, 2, str(v))

                        for _sk in reversed(sort_by):
                            _sk_field = _sk.lstrip("-")
                            _sk_rev = _sk.startswith("-")
                            payload = sorted(
                                payload,
                                key=lambda x, f=_sk_field: _sort_key(x.get(f)) if isinstance(x, dict) else _sort_key(x),
                                reverse=_sk_rev,
                            )
                    if limit is not None:
                        payload = payload[:limit]
                    if last is not None:
                        payload = payload[-last:]
                    if sample is not None:
                        payload = payload[:sample]
                    if exclude_fields:
                        payload = _apply_exclude(payload, exclude_fields)
                    if rename_fields:
                        payload = _apply_renames(payload, rename_fields)
                    if select_fields:
                        payload = _apply_select(payload, select_fields)
                    if group_by:
                        payload = _apply_group_by(payload, group_by)
                    if count_by:
                        payload = _apply_count_by(payload, count_by)
                    if map_fields:
                        payload = _apply_map_fields(payload, map_fields)
                    if add_fields:
                        _inject: dict[str, Any] = {}
                        for _af in add_fields:
                            if "=" in _af:
                                _afk, _afv = _af.split("=", 1)
                                _inject[_afk.strip()] = _afv
                        if _inject:
                            payload = [{**item, **_inject} if isinstance(item, dict) else item for item in payload]
                    if transforms:
                        payload = _apply_transforms(payload, transforms)
                    if join_spec:
                        _js = join_spec.strip()
                        if " on " in _js:
                            _j_ep, _j_keys = _js.split(" on ", 1)
                        elif ":" in _js:
                            _j_ep, _j_keys = _js.split(":", 1)
                        else:
                            _j_ep, _j_keys = "", ""
                            print_warning(f"--join: invalid spec {join_spec!r} — use ENDPOINT:LOCAL=REMOTE")
                        import re as _re_join
                        _j_ep_clean = _j_ep.strip()
                        if _j_ep_clean and not _re_join.fullmatch(r"[A-Za-z0-9_\-/]+", _j_ep_clean):
                            print_warning(
                                f"--join: endpoint {_j_ep_clean!r} contains invalid "
                                f"characters; skipping join."
                            )
                            _j_ep = ""
                        elif ".." in _j_ep_clean:
                            print_warning(f"--join: '..' not allowed in endpoint; skipping join.")
                            _j_ep = ""
                        if _j_ep and "=" in _j_keys:
                            _j_local, _j_remote = _j_keys.split("=", 1)
                            _j_local = _j_local.strip()
                            _j_remote = _j_remote.strip()
                            try:
                                # Paginate the remote table, or records on
                                # page 2+ silently fail to enrich (empty _{name}).
                                _j_raw, _j_all = _fetch_all_pages(
                                    client, "GET", f"/v1/{_j_ep_clean}",
                                    None, None, show_progress=False,
                                )
                                _j_recs = _j_all if _j_all else _unwrap(_j_raw)
                                if not isinstance(_j_recs, list):
                                    _j_recs = [_j_raw] if isinstance(_j_raw, dict) else []
                                _j_lookup: dict[str, Any] = {}
                                for _jr in _j_recs:
                                    if isinstance(_jr, dict):
                                        _jrk = str(_jr.get(_j_remote, ""))
                                        if _jrk:
                                            _j_lookup[_jrk] = _jr
                                _j_fname = _j_ep.strip().rstrip("s")
                                _j_hits = 0
                                _new_payload: list[Any] = []
                                for _ji in payload:
                                    if isinstance(_ji, dict):
                                        _jmatch = _j_lookup.get(str(_ji.get(_j_local, "")), {})
                                        if _jmatch:
                                            _j_hits += 1
                                        _new_payload.append({**_ji, f"_{_j_fname}": _jmatch})
                                    else:
                                        _new_payload.append(_ji)
                                payload = _new_payload
                                if verbose:
                                    print_info(f"--join: matched {_j_hits} of {len(payload)} record(s) from {_j_ep!r}.")
                            except Exception as _je:
                                print_warning(f"--join: failed to fetch {_j_ep!r}: {_je}")
                    # Put processed list back; keep outer envelope if present
                    if isinstance(result, dict):
                        for k in ("data", "results", "items", "records"):
                            if k in result:
                                result = {**result, k: payload}
                                break
                        else:
                            result = payload
                    else:
                        result = payload

            # --exclude / --select on single-object responses (lists already handled above)
            if exclude_fields and isinstance(result, dict) and not isinstance(result, str):
                _excl_payload = _unwrap(result)
                if isinstance(_excl_payload, dict):
                    _excl_payload = {k: v for k, v in _excl_payload.items() if k not in set(exclude_fields)}
                    result = _excl_payload

            if select_fields and isinstance(result, dict) and not isinstance(result, str):
                _sel_payload = _unwrap(result)
                if isinstance(_sel_payload, dict):
                    _sel_payload = {k: v for k, v in _sel_payload.items() if k in set(select_fields)}
                    result = _sel_payload

            # --flatten: expand nested dict objects to dot-notation keys
            if flatten and not isinstance(result, str):
                _fl_payload = _unwrap(result)
                if isinstance(_fl_payload, list):
                    _fl_payload = _apply_flatten(_fl_payload)
                    if isinstance(result, dict):
                        for _flk in ("data", "results", "items", "records"):
                            if _flk in result:
                                result = {**result, _flk: _fl_payload}
                                break
                        else:
                            result = _fl_payload
                    else:
                        result = _fl_payload

            # --strip-nulls: remove keys with None values from every result object
            if strip_nulls and not isinstance(result, str):
                _sn_payload = _unwrap(result)
                if isinstance(_sn_payload, list):
                    _sn_payload = [
                        {k: v for k, v in item.items() if v is not None} if isinstance(item, dict) else item
                        for item in _sn_payload
                    ]
                    if isinstance(result, dict):
                        for _k in ("data", "results", "items", "records"):
                            if _k in result:
                                result = {**result, _k: _sn_payload}
                                break
                        else:
                            result = _sn_payload
                    else:
                        result = _sn_payload
                elif isinstance(_sn_payload, dict):
                    result = {k: v for k, v in _sn_payload.items() if v is not None}

            # --strip-empties: remove keys with null, empty-string, empty-list, empty-dict values
            if strip_empties and not isinstance(result, str):
                def _is_empty_val(v: Any) -> bool:
                    return v is None or v == "" or v == [] or v == {}
                _se_payload = _unwrap(result)
                if isinstance(_se_payload, list):
                    _se_payload = [
                        {k: v for k, v in item.items() if not _is_empty_val(v)} if isinstance(item, dict) else item
                        for item in _se_payload
                    ]
                    if isinstance(result, dict):
                        for _sek in ("data", "results", "items", "records"):
                            if _sek in result:
                                result = {**result, _sek: _se_payload}
                                break
                        else:
                            result = _se_payload
                    else:
                        result = _se_payload
                elif isinstance(_se_payload, dict):
                    result = {k: v for k, v in _se_payload.items() if not _is_empty_val(v)}

            # --null-as STR: replace None values with a custom string before output
            if null_as is not None and not isinstance(result, str):
                result = _apply_null_as(result, null_as)

            # --jq: extract a dotted-path value from the result before any
            # output or fail-on checks, so what prints IS the extracted value.
            if jq_expr and not isinstance(result, str):
                result = _apply_jq(result, jq_expr)

            # Warn when a flag combination means one flag silently wins:
            # single-value output modes bypass the export branches entirely,
            # and --json/--jsonl take precedence over table-oriented exports.
            _early_mode = next((name for name, active in (
                ("--count",         count_only),
                ("--format",        format_template is not None),
                ("--pick",          pick_field is not None),
                ("--sum",           sum_field is not None),
                ("--avg",           avg_field is not None),
                ("--min",           min_field is not None),
                ("--max",           max_field is not None),
                ("--fields",        fields_only),
                ("--output-schema", output_schema),
            ) if active), None)
            if _early_mode:
                for _exp_name, _exp_val in (
                    ("--to-csv", csv_file), ("--to-json", json_file),
                    ("--to-markdown", to_markdown), ("--tee", tee_file),
                ):
                    if _exp_val:
                        print_warning(f"{_exp_name} is ignored when combined with {_early_mode}.")
            elif (as_json and "--json" in sys.argv[1:]) or (as_jsonl and "--jsonl" in sys.argv[1:]):
                # Explicit flag only — TTY auto-JSON must not trigger warnings.
                _fmt_flag = "--json" if as_json else "--jsonl"
                if csv_file:
                    print_warning(f"--to-csv is ignored with {_fmt_flag}.")
                if to_markdown:
                    print_warning(f"--to-markdown is ignored with {_fmt_flag}.")
                if tee_file:
                    print_warning(f"--tee captures no output with {_fmt_flag}.")
                if columns:
                    print_warning(f"--columns is ignored with {_fmt_flag} — filter fields with --select or --exclude.")

            # --fail-on-empty: exit non-zero when result list is empty
            if fail_on_empty and not isinstance(result, str):
                _warn_if_partial(result, fetch_all, "--fail-on-empty")
                _foe_payload = _unwrap(result)
                if isinstance(_foe_payload, list) and len(_foe_payload) == 0:
                    err_console.print("[bold red]No results.[/bold red]")
                    sys.exit(1)

            # --fail-on-pattern: exit non-zero when any result matches the expression
            if fail_on_pattern and not isinstance(result, str):
                _warn_if_partial(result, fetch_all, "--fail-on-pattern")
                _fop_payload = _unwrap(result)
                if isinstance(_fop_payload, list):
                    try:
                        _fop_matched = _apply_filters(_fop_payload, [fail_on_pattern])
                        if _fop_matched:
                            err_console.print(
                                f"[bold red]--fail-on-pattern: {len(_fop_matched)} item(s) matched "
                                f"[dim]{fail_on_pattern}[/dim][/bold red]"
                            )
                            sys.exit(1)
                    except ValueError as _fop_exc:
                        # A malformed guard expression must FAIL, not silently
                        # pass — otherwise a typo'd pattern disables the CI check.
                        print_error(f"--fail-on-pattern: invalid expression: {_fop_exc}")
                        sys.exit(2)

            # --fields: print available field names from the first result object and exit
            if fields_only and not isinstance(result, str):
                _f_payload = _unwrap(result)
                _f_first: Any = None
                if isinstance(_f_payload, list) and _f_payload:
                    _f_first = _f_payload[0]
                elif isinstance(_f_payload, dict):
                    _f_first = _f_payload
                if isinstance(_f_first, dict):
                    for _fk in _f_first:
                        sys.stdout.write(_fk + "\n")
                        tee_write(_fk + "\n")
                else:
                    console.print("[dim]No fields found in response.[/dim]")
                return

            # --output-schema: print field names, types, and sample values then exit
            if output_schema and not isinstance(result, str):
                _os_payload = _unwrap(result)
                _os_first: Any = None
                if isinstance(_os_payload, list) and _os_payload:
                    _os_first = _os_payload[0]
                elif isinstance(_os_payload, dict):
                    _os_first = _os_payload
                if isinstance(_os_first, dict):
                    import rich.table as _rich_tbl
                    _os_tbl = _rich_tbl.Table("field", "type", "example", title=f"{endpoint} {function} — schema")
                    for _osk, _osv in _os_first.items():
                        _os_tbl.add_row(str(_osk), type(_osv).__name__, str(_osv)[:60])
                    console.print(_os_tbl)
                else:
                    console.print("[dim]No schema found in response.[/dim]")
                return

            title = f"{endpoint} {function}"

            # --count: just show how many items, nothing else
            if count_only:
                _warn_if_partial(result, fetch_all, "--count")
                payload_for_count = _unwrap(result)
                if isinstance(payload_for_count, list):
                    noun = endpoint.rstrip("s") if endpoint.endswith("s") else endpoint
                    console.print(f"[bold]{len(payload_for_count)}[/bold] [dim]{noun}(s)[/dim]")
                elif result is None:
                    console.print("[dim]0[/dim]")
                else:
                    console.print("[dim]1[/dim]")
                return

            # --format: render each item through a Go-style template
            if format_template is not None:
                payload_for_fmt = _unwrap(result)
                items_for_fmt = payload_for_fmt if isinstance(payload_for_fmt, list) else [payload_for_fmt]
                _render_format_template(items_for_fmt, format_template)
                return

            # --pick: extract a single field path from every item and print one value per line
            if pick_field is not None:
                payload_for_pick = _unwrap(result)
                items_for_pick = payload_for_pick if isinstance(payload_for_pick, list) else [payload_for_pick]
                for val in _apply_pick(items_for_pick, pick_field):
                    sys.stdout.write(val + "\n")
                    tee_write(val + "\n")
                return

            # --sum / --avg: aggregate a numeric field and print one value
            if sum_field is not None:
                _warn_if_partial(result, fetch_all, "--sum")
                _sum_payload = _unwrap(result)
                _sum_items = _sum_payload if isinstance(_sum_payload, list) else [_sum_payload]
                _sum_val = _apply_sum(_sum_items, sum_field)
                _sum_display = int(_sum_val) if _sum_val == int(_sum_val) else _sum_val
                console.print(f"[bold]{_sum_display}[/bold]  [dim]sum({sum_field})[/dim]")
                return

            if avg_field is not None:
                _warn_if_partial(result, fetch_all, "--avg")
                _avg_payload = _unwrap(result)
                _avg_items = _avg_payload if isinstance(_avg_payload, list) else [_avg_payload]
                _avg_val = _apply_avg(_avg_items, avg_field)
                if _avg_val is None:
                    console.print(f"[dim]no numeric values found for '{avg_field}'[/dim]")
                else:
                    console.print(f"[bold]{_avg_val:.4g}[/bold]  [dim]avg({avg_field})[/dim]")
                return

            if min_field is not None:
                _warn_if_partial(result, fetch_all, "--min")
                _min_payload = _unwrap(result)
                _min_items = _min_payload if isinstance(_min_payload, list) else [_min_payload]
                _min_val = _apply_min(_min_items, min_field)
                if _min_val is None:
                    console.print(f"[dim]no numeric values found for '{min_field}'[/dim]")
                else:
                    _min_display = int(_min_val) if _min_val == int(_min_val) else _min_val
                    console.print(f"[bold]{_min_display}[/bold]  [dim]min({min_field})[/dim]")
                return

            if max_field is not None:
                _warn_if_partial(result, fetch_all, "--max")
                _max_payload = _unwrap(result)
                _max_items = _max_payload if isinstance(_max_payload, list) else [_max_payload]
                _max_val = _apply_max(_max_items, max_field)
                if _max_val is None:
                    console.print(f"[dim]no numeric values found for '{max_field}'[/dim]")
                else:
                    _max_display = int(_max_val) if _max_val == int(_max_val) else _max_val
                    console.print(f"[bold]{_max_display}[/bold]  [dim]max({max_field})[/dim]")
                return

            # Some endpoints (e.g. user-agents csv) return raw text/csv, not JSON.
            if isinstance(result, str):
                if csv_file == "-":
                    sys.stdout.write(result)
                elif csv_file:
                    import pathlib
                    pathlib.Path(csv_file).parent.mkdir(parents=True, exist_ok=True)
                    pathlib.Path(csv_file).write_text(result, encoding="utf-8")
                    lines = result.strip().splitlines()
                    print_success(
                        f"Wrote {max(0, len(lines)-1)} row{'s' if len(lines) != 2 else ''} "
                        f"to {csv_file}"
                    )
                else:
                    console.print(result)
            elif json_file:
                write_json(result, json_file)
                print_success(f"Wrote JSON to {json_file}")
            elif as_jsonl:
                import json as _json
                payload_items = _unwrap(result)
                items = payload_items if isinstance(payload_items, list) else [payload_items]
                for item in items:
                    _jsonl_line = _json.dumps(item, default=str) + "\n"
                    sys.stdout.write(_jsonl_line)
                    tee_write(_jsonl_line)
            elif as_json:
                import json as _json
                _json_text = _json.dumps(_unwrap(result), indent=2, default=str) + "\n"
                sys.stdout.write(_json_text)
                tee_write(_json_text)
            elif csv_file == "-":
                import csv as _csv, io as _io
                from .output import _rows_for_csv
                headers, rows_data = _rows_for_csv(result, columns=columns)
                if csv_header_case == "lower":
                    headers = [h.lower() for h in headers]
                elif csv_header_case == "upper":
                    headers = [h.upper() for h in headers]
                elif csv_header_case == "title":
                    headers = [h.replace("_", " ").title().replace(" ", "_") for h in headers]
                buf = _io.StringIO()
                w = _csv.writer(buf, delimiter=csv_delimiter)
                if not no_header:
                    w.writerow(headers)
                w.writerows(rows_data)
                sys.stdout.write(buf.getvalue())
                tee_write(buf.getvalue())
            elif csv_file:
                n = write_csv(result, csv_file, columns=columns, append=csv_append, delimiter=csv_delimiter, no_header=no_header, header_case=csv_header_case)
                verb = "Appended" if csv_append else "Wrote"
                print_success(f"{verb} {n} row{'s' if n != 1 else ''} to {csv_file}")
            elif to_markdown:
                from .output import render_markdown_table as _md_render
                _md_payload = _unwrap(result)
                _md_items = _md_payload if isinstance(_md_payload, list) else ([_md_payload] if isinstance(_md_payload, dict) else [])
                _md_cols = columns or (list(_md_items[0].keys()) if _md_items and isinstance(_md_items[0], dict) else None)
                _md_text = _md_render(_md_items, columns=_md_cols)
                import pathlib as _pl_md
                if to_markdown == "-":
                    sys.stdout.write(_md_text)
                else:
                    _pl_md.Path(to_markdown).write_text(_md_text, encoding="utf-8")
                    _md_rows_count = len(_md_items)
                    print_success(f"Wrote {_md_rows_count} row{'s' if _md_rows_count != 1 else ''} to {to_markdown}")
            else:
                print_response(result, raw=raw, title=title, columns=columns)
                # Pagination hint: show total count when the response has more items than shown
                if not fetch_all and isinstance(result, dict):
                    _pg_meta = result.get("meta") or result.get("pagination") or {}
                    _pg_total = (_pg_meta.get("total") if isinstance(_pg_meta, dict) else None) or result.get("total")
                    _pg_payload = _unwrap(result)
                    _pg_shown = len(_pg_payload) if isinstance(_pg_payload, list) else None
                    if _pg_total and _pg_shown and int(_pg_total) > _pg_shown:
                        console.print(f"[dim]Showing {_pg_shown} of {_pg_total} — use --all to fetch everything[/dim]")
                    elif (not _pg_total and _pg_shown and _pg_shown >= 10 and page is None
                          and any(p.name == "page" for p in operation.params)):
                        console.print(
                            f"[dim]Got {_pg_shown} result(s) — this endpoint supports pagination; "
                            f"use --all to fetch all pages or --page N for a specific page[/dim]"
                        )

            # --tee: flush recorded console output to file
            if tee_file:
                from .output import flush_tee
                flush_tee()

            # --exec: run a shell command for each result item with {field}/$field
            # substitution. render_exec_command() shell-quotes each value AND flags
            # any value containing a shell-active character; we REFUSE to run such
            # an item, because shlex.quote alone is not safe when the operator
            # quotes the placeholder ("{name}" / '{name}') and the value is
            # attacker-controlled API data (org name, device label, domain note).
            if exec_cmd and not isinstance(result, str):
                import subprocess as _sp
                from .postprocess import render_exec_command
                _exc_payload = _unwrap(result)
                _exc_items = _exc_payload if isinstance(_exc_payload, list) else ([_exc_payload] if isinstance(_exc_payload, dict) else [])
                _exc_ok = _exc_fail = _exc_skipped = 0
                for _exc_item in _exc_items:
                    if isinstance(_exc_item, dict):
                        _exc_rendered, _exc_unsafe = render_exec_command(exec_cmd, _exc_item)
                        if _exc_unsafe:
                            print_warning(
                                f"--exec: skipped an item — field(s) "
                                f"{', '.join(sorted(set(_exc_unsafe)))} contain shell "
                                f"metacharacters that could be unsafe in a command; not executed."
                            )
                            _exc_skipped += 1
                            _exc_fail += 1
                            continue
                    else:
                        _exc_rendered = exec_cmd
                    try:
                        _exc_rc = _sp.run(_exc_rendered, shell=True).returncode
                        if _exc_rc == 0:
                            _exc_ok += 1
                        else:
                            _exc_fail += 1
                    except Exception as _exc_err:
                        print_warning(f"--exec: {_exc_err}")
                        _exc_fail += 1
                if not is_quiet():
                    _exc_skip_note = f", {_exc_skipped} skipped (unsafe)" if _exc_skipped else ""
                    console.print(f"[dim]--exec: {_exc_ok} succeeded, {_exc_fail} failed{_exc_skip_note}[/dim]")

            # --watch-until: raise signal when filter condition is satisfied
            if watch_until_filter and not isinstance(result, str):
                _wu_payload = _unwrap(result)
                _wu_items = (
                    _wu_payload if isinstance(_wu_payload, list)
                    else [_wu_payload] if isinstance(_wu_payload, dict) else []
                )
                if _wu_items:
                    try:
                        _wu_matched = _apply_filters(_wu_items, [watch_until_filter])
                    except ValueError:
                        _wu_matched = []
                    if _wu_matched:
                        console.print(
                            f"[bold green]--watch-until:[/bold green] "
                            f"condition [dim]{watch_until_filter}[/dim] matched."
                        )
                        raise _WatchUntilSatisfied()

            # --stats: print a numeric-field summary footer
            if stats_field and not isinstance(result, str):
                _st_payload = _unwrap(result)
                if isinstance(_st_payload, list):
                    _compute_stats(_st_payload, stats_field)

            # --alert: ring terminal bell + print banner when filter matches
            if alert_filter and not isinstance(result, str):
                _al_payload = _unwrap(result)
                _al_items = (
                    _al_payload if isinstance(_al_payload, list)
                    else ([_al_payload] if isinstance(_al_payload, dict) else [])
                )
                if _al_items:
                    try:
                        _al_matched = _apply_filters(_al_items, [alert_filter])
                    except ValueError:
                        _al_matched = []
                    if _al_matched:
                        import sys as _sys_al
                        _sys_al.stderr.write("\a")
                        _sys_al.stderr.flush()
                        console.print(
                            f"[bold yellow]⚠ --alert:[/bold yellow] "
                            f"filter [dim]{alert_filter}[/dim] matched {len(_al_matched)} item(s)."
                        )

            # --result-sink: pass processed result back to caller (used by --watch-diff)
            if result_sink is not None:
                result_sink.append(_unwrap(result) if not isinstance(result, str) else result)

            # --wait: if this operation is async and has a poll target, block until done
            if wait and not operation.poll_on:
                print_warning(
                    f"--wait has no effect on '{endpoint} {function}' "
                    f"(this operation does not support async polling). "
                    f"Remove --wait or use an endpoint that returns a job ID."
                )
            if wait and operation.poll_on and not isinstance(result, str):
                _job_ok = _wait_for_job(
                    result, endpoint, operation.poll_on,
                    resolved_key, base_url, resolved_org,
                    raw=raw, title=title, columns=columns,
                    max_wait=max_wait,
                )
                if not _job_ok:
                    # The async job failed / timed out / was unconfirmable — do
                    # not report success to a CI pipeline that used --wait.
                    sys.exit(1)

            # --watch-changes: poll and show only what changed between ticks
            if watch_changes_interval:
                import time as _wc_time
                import datetime as _wc_dt

                def _wc_key(item: Any, i: int) -> str:
                    if isinstance(item, dict):
                        for _k in ("id", "uuid", "name"):
                            if _k in item:
                                return str(item[_k])
                    return str(i)

                _wc_prev = _unwrap(result)
                if not isinstance(_wc_prev, list):
                    _wc_prev = [_wc_prev] if isinstance(_wc_prev, dict) else []
                _wc_prev_map = {_wc_key(item, i): item for i, item in enumerate(_wc_prev)}

                err_console.print(
                    f"[dim]Watching every {watch_changes_interval}s — "
                    f"{len(_wc_prev)} item(s) in initial snapshot. Ctrl-C to stop.[/dim]"
                )
                try:
                    while True:
                        _wc_time.sleep(watch_changes_interval)
                        try:
                            _wc_new_result = client.request(method, path, params=query_params or None, json=json_body)
                        except APIError as _wc_exc:
                            err_console.print(f"[dim]Poll error: {_wc_exc}[/dim]")
                            continue
                        _wc_new = _unwrap(_wc_new_result)
                        if not isinstance(_wc_new, list):
                            _wc_new = [_wc_new] if isinstance(_wc_new, dict) else []
                        _wc_new_map = {_wc_key(item, i): item for i, item in enumerate(_wc_new)}

                        added   = [v for k, v in _wc_new_map.items() if k not in _wc_prev_map]
                        removed = [v for k, v in _wc_prev_map.items() if k not in _wc_new_map]
                        changed = [
                            (_wc_prev_map[k], _wc_new_map[k])
                            for k in _wc_new_map
                            if k in _wc_prev_map and _wc_prev_map[k] != _wc_new_map[k]
                        ]

                        if not added and not removed and not changed:
                            _wc_prev_map = _wc_new_map
                            continue

                        _wc_ts = _wc_dt.datetime.now().strftime("%H:%M:%S")
                        console.rule(f"[dim]{_wc_ts}[/dim]")

                        _wc_all = added + removed + [b for b, _ in changed] + [a for _, a in changed]
                        _wc_cols: list[str] = []
                        _wc_seen: set[str] = set()
                        for _wc_item in _wc_all:
                            if isinstance(_wc_item, dict):
                                for _wc_c in _wc_item:
                                    if _wc_c not in _wc_seen:
                                        _wc_seen.add(_wc_c)
                                        _wc_cols.append(_wc_c)
                        _wc_cols = _wc_cols[:8]

                        if added:
                            _wc_tbl = Table(title=f"[green]+ {len(added)} added[/green]", header_style="bold green")
                            for _wc_c in _wc_cols:
                                _wc_tbl.add_column(str(_wc_c), overflow="fold", max_width=40)
                            for _wc_item in added:
                                _wc_tbl.add_row(*[str(_wc_item.get(_wc_c, ""))[:40] if isinstance(_wc_item, dict) else "" for _wc_c in _wc_cols])
                            console.print(_wc_tbl)

                        if removed:
                            _wc_tbl = Table(title=f"[red]− {len(removed)} removed[/red]", header_style="bold red")
                            for _wc_c in _wc_cols:
                                _wc_tbl.add_column(str(_wc_c), overflow="fold", max_width=40)
                            for _wc_item in removed:
                                _wc_tbl.add_row(*[str(_wc_item.get(_wc_c, ""))[:40] if isinstance(_wc_item, dict) else "" for _wc_c in _wc_cols])
                            console.print(_wc_tbl)

                        for _wc_b, _wc_a in changed:
                            _wc_id = _wc_key(_wc_b, 0)
                            _wc_diff_keys = sorted(
                                c for c in set(list(_wc_b) + list(_wc_a))
                                if isinstance(_wc_b, dict) and isinstance(_wc_a, dict)
                                and _wc_b.get(c) != _wc_a.get(c)
                            )
                            _wc_tbl = Table(title=f"[yellow]~ changed id={_wc_id}[/yellow]", header_style="bold yellow")
                            _wc_tbl.add_column("field", no_wrap=True)
                            _wc_tbl.add_column("before", overflow="fold")
                            _wc_tbl.add_column("after",  overflow="fold")
                            for _wc_dk in _wc_diff_keys:
                                _wc_tbl.add_row(
                                    _wc_dk,
                                    str(_wc_b.get(_wc_dk, ""))[:60] if isinstance(_wc_b, dict) else "",
                                    str(_wc_a.get(_wc_dk, ""))[:60] if isinstance(_wc_a, dict) else "",
                                )
                            console.print(_wc_tbl)

                        _wc_prev_map = _wc_new_map
                except KeyboardInterrupt:
                    console.print("\n[dim]Stopped.[/dim]")
        except APIError as exc:
            log_event(endpoint, function, method, path, exc.status_code, resolved_org, error=str(exc))
            log_history(endpoint, function, method, path, exc.status_code, resolved_org, error=str(exc), argv=sys.argv[1:])
            print_error(str(exc), exc.body)
            _hint: str | None = None
            if exc.status_code == 422:
                _hint = "Hint: run with --verbose to see the full request/response, or check the API Parameters section in --help."
            elif exc.status_code == 409 and method == "POST":
                _hint = "Hint: resource may already exist — try --upsert to update it instead of creating."
            elif exc.status_code == 404:
                _hint = f"Hint: resource not found — run [bold]dnsfcli {endpoint} list[/bold] to check available IDs."
            elif exc.status_code == 403:
                _hint = "Hint: insufficient permissions — run [bold]dnsfcli auth verify[/bold] to check your API key."
            elif exc.status_code == 401:
                _hint = "Hint: authentication failed — run [bold]dnsfcli auth setup[/bold] to reconfigure your API key."
            if _hint:
                console.print(f"[dim]{_hint}[/dim]")
            sys.exit(1)


# ---------------------------------------------------------------------------
# Config sub-app
# ---------------------------------------------------------------------------



















# ---------------------------------------------------------------------------
# Alias sub-app
# ---------------------------------------------------------------------------

















# ---------------------------------------------------------------------------
# history sub-app
# ---------------------------------------------------------------------------















# ---------------------------------------------------------------------------
# diff command
# ---------------------------------------------------------------------------






# ---------------------------------------------------------------------------
# cache sub-commands
# ---------------------------------------------------------------------------







# ---------------------------------------------------------------------------
# schema command — show operation details
# ---------------------------------------------------------------------------




# ---------------------------------------------------------------------------
# env command — show recognized environment variables
# ---------------------------------------------------------------------------




# ---------------------------------------------------------------------------
# Shell completion
# ---------------------------------------------------------------------------







def _patch_resolve_context_for_typer() -> None:
    """Monkey-patch Click/Typer's _resolve_context to traverse Typer's TyperGroup.

    Click's _resolve_context uses `isinstance(command, click.Group)` to decide
    whether to recurse into sub-commands.  Typer's TyperGroup is NOT a subclass
    of click.Group (it inherits from typer._click.core.Command), so Click
    stops at the top level and completion never sees nested endpoints.

    Typer also ships its own copy of shell_completion in typer._click.shell_completion,
    and Typer's ZshComplete.get_completions calls the Typer copy, not Click's.
    We replace _resolve_context in BOTH modules with a duck-typed version.
    """
    def _patched_resolve_context(cli, ctx_args, prog_name, args):
        ctx_args["resilient_parsing"] = True
        with cli.make_context(prog_name, args.copy(), **ctx_args) as ctx:
            args = ctx._protected_args + ctx.args
            while args:
                command = ctx.command
                # Duck-type: any command with resolve_command() acts as a group.
                # This covers both click.Group and Typer's TyperGroup.
                if hasattr(command, "resolve_command"):
                    if not getattr(command, "chain", False):
                        name, cmd, args = command.resolve_command(ctx, args)
                        if cmd is None:
                            return ctx
                        with cmd.make_context(
                            name, args, parent=ctx, resilient_parsing=True
                        ) as sub_ctx:
                            ctx = sub_ctx
                            args = ctx._protected_args + ctx.args
                    else:
                        sub_ctx = ctx
                        while args:
                            name, cmd, args = command.resolve_command(ctx, args)
                            if cmd is None:
                                return ctx
                            with cmd.make_context(
                                name,
                                args,
                                parent=ctx,
                                allow_extra_args=True,
                                allow_interspersed_args=False,
                                resilient_parsing=True,
                            ) as sub_sub_ctx:
                                sub_ctx = sub_sub_ctx
                                args = sub_ctx.args
                        ctx = sub_ctx
                        args = [*sub_ctx._protected_args, *sub_ctx.args]
                else:
                    break
        return ctx

    import click.shell_completion as _click_sc
    _click_sc._resolve_context = _patched_resolve_context

    try:
        import typer._click.shell_completion as _typer_sc
        _typer_sc._resolve_context = _patched_resolve_context
    except (ImportError, AttributeError):
        pass


def _populate_dynamic_commands(click_app: Any) -> None:
    """Register all REGISTRY endpoints as Click sub-groups in *click_app*.

    This is called when shell completion is being performed so the completion
    engine sees every endpoint name and its function names.  It is NOT called
    during normal invocations — routing happens in app_entry() instead.
    """
    import click
    from .endpoints import REGISTRY

    existing = set(click_app.commands.keys()) if hasattr(click_app, "commands") else set()

    for ep_name in sorted(REGISTRY.keys()):
        if ep_name in existing:
            continue  # static commands take precedence
        ep_obj = REGISTRY[ep_name]

        # We need a fresh group variable per endpoint (avoid closure capture issues).
        ep_group = click.Group(
            name=ep_name,
            help=f"Commands for the {ep_name} endpoint.",
        )
        for fn_name in sorted(ep_obj.operations.keys()):
            cmd = _make_dynamic_command(ep_name, fn_name)
            ep_group.add_command(cmd, name=fn_name)

        click_app.add_command(ep_group, name=ep_name)


# ---------------------------------------------------------------------------
# Dynamic catch-all: intercept unknown sub-commands as (endpoint, function)
# ---------------------------------------------------------------------------


def _make_dynamic_command(endpoint: str, function: str) -> Any:
    """Return a Click command that handles [endpoint] [function] [...args]."""
    import click
    from .cliopts import _GroupedCommand, add_dynamic_options

    def _cmd(
        ctx: Any,
        raw: bool,
        verbose: bool,
        api_key: str | None,
        org_id: str | None,
        csv_file: str | None,
        csv_input: str | None,
        show_template: bool,
        show_plan: bool,
        skip_confirm: bool,
        columns_str: str | None,
        wait: bool,
        profile: str | None,
        fetch_all: bool,
        as_json: bool,
        no_color: bool,
        quiet: bool,
        sort_by: tuple[str, ...],
        limit: int | None,
        json_file: str | None,
        timeout: float | None,
        filters: tuple[str, ...],
        count_only: bool,
        body_json: str | None,
        page: int | None,
        page_size: int | None,
        as_jsonl: bool,
        on_error: str | None,
        concurrency: int | None,
        watch_interval: int | None,
        grep: str | None,
        unique_field: str | None,
        format_template: str | None,
        csv_append: bool,
        dry_run: bool,
        json_input: str | None,
        cache_ttl: int | None,
        each_org: bool,
        org_name: str | None,
        set_fields: tuple[str, ...],
        exclude_str: str | None,
        merge_key: str | None,
        rate: float | None,
        truncate: int | None,
        csv_delimiter: str,
        no_header: bool,
        csv_header_case: str | None,
        retry: int | None,
        errors_csv: str | None,
        retry_errors_csv: str | None,
        rename_fields: tuple[str, ...],
        pick_field: str | None,
        batch_size: int | None,
        timing: bool,
        group_by: str | None,
        select_fields_str: str | None,
        sum_field: str | None,
        avg_field: str | None,
        min_field: str | None,
        max_field: str | None,
        map_fields: tuple[str, ...],
        watch_changes_interval: int | None,
        upsert: bool,
        last: int | None,
        sample: int | None,
        fields_only: bool,
        strip_nulls: bool,
        max_pages: int | None,
        max_errors: int | None,
        save_as: str | None,
        null_as: str | None,
        no_wrap: bool,
        color_rules_raw: tuple[str, ...],
        count_by: str | None,
        not_null_field: str | None,
        is_null_field: str | None,
        since_filter: str | None,
        extra_headers_raw: tuple[str, ...],
        insecure: bool,
        no_progress: bool,
        tee_file: str | None,
        output_format: str | None,
        validate_only: bool,
        confirm_each: bool,
        diff_mode: bool,
        preset: str | None,
        parallel_orgs: bool,
        org_concurrency: int,
        org_filter: str | None,
        max_orgs: int | None,
        flatten: bool,
        strip_empties: bool,
        csv_null_value: str | None,
        watch_until_filter: str | None,
        fail_on_empty: bool,
        quiet_ok: bool,
        batch_delay: int | None,
        connect_timeout: float | None,
        proxy: str | None,
        jq_expr: str | None,
        max_wait: float | None,
        watch_diff: bool,
        alert_filter: str | None,
        table_style: str | None,
        stats_field: str | None,
        env_file: str | None,
        log_file: str | None,
        stdin_json: bool,
        skip_rows: int,
        max_rows: int | None,
        add_fields: tuple[str, ...],
        paginate_until: str | None,
        batch_report: str | None,
        org_csv: str | None,
        color_scale: str | None,
        format_preset: str | None,
        fail_on_pattern: str | None,
        filter_mode: str,
        to_markdown: str | None,
        output_schema: bool,
        exec_cmd: str | None,
        transforms: tuple[str, ...],
        join_spec: str | None,
        bundle: str | None,
    ) -> None:
        import time as _time
        if env_file:
            _load_env_file(env_file)
        if no_color or quiet or quiet_ok or csv_null_value is not None or table_style or log_file or color_scale:
            set_output_options(no_color=no_color, quiet=quiet, quiet_ok=quiet_ok, csv_null_value=csv_null_value, table_style=table_style, log_file=log_file, color_scale=color_scale)
        columns = [c.strip() for c in columns_str.split(",") if c.strip()] if columns_str else None
        exclude_fields = [f.strip() for f in exclude_str.split(",") if f.strip()] if exclude_str else None
        select_fields = [f.strip() for f in select_fields_str.split(",") if f.strip()] if select_fields_str else None
        effective_profile = profile if profile is not None else get_active_profile()

        # Resolve batch defaults: CLI flag → config file → hardcoded default
        _cfg = load_config()
        _bcfg = _cfg.batch

        # --bundle: apply named flag bundle from config as defaults (CLI flags override)
        if bundle:
            _bvals = _cfg.bundles.get(bundle)
            if _bvals:
                if "columns" in _bvals and not columns_str:
                    columns = [c.strip() for c in str(_bvals["columns"]).split(",") if c.strip()]
                if "format" in _bvals and format_template is None:
                    format_template = str(_bvals["format"])
                if "format_preset" in _bvals and format_preset is None:
                    _fp_b = _cfg.format_presets.get(str(_bvals["format_preset"]))
                    if _fp_b:
                        format_template = _fp_b
                if "sort" in _bvals and not sort_by:
                    sort_by = tuple(str(_bvals["sort"]).split(","))
                if "filter" in _bvals and not filters:
                    filters = (str(_bvals["filter"]),)
                if "filter_mode" in _bvals and filter_mode == "and":
                    filter_mode = str(_bvals["filter_mode"])
                if "columns_preset" in _bvals and not columns_str and not columns:
                    _bp_cols = _cfg.column_presets.get(str(_bvals["columns_preset"]))
                    if _bp_cols:
                        columns = _bp_cols
            else:
                print_warning(f"--bundle: no bundle named {bundle!r} found in config.")

        # --preset: load named column preset from config (overrides --columns)
        if preset:
            _preset_cols = _cfg.column_presets.get(preset)
            if _preset_cols:
                columns = _preset_cols
            else:
                print_warning(f"--preset: no preset named {preset!r} found in config. Use: dnsfcli config set preset.{preset} col1,col2")

        # --format-preset: load named format template from config (overrides --format)
        if format_preset:
            _fp_tmpl = _cfg.format_presets.get(format_preset)
            if _fp_tmpl:
                format_template = _fp_tmpl
            else:
                print_warning(f"--format-preset: no preset named {format_preset!r} found in config. Use: dnsfcli config set format.{format_preset} '{{{{.field}}}}'")
        _eff_concurrency: int = concurrency if concurrency is not None else _bcfg.concurrency
        _eff_retry:       int = retry if retry is not None else _bcfg.retry
        _eff_on_error:    str = on_error if on_error is not None else _bcfg.on_error
        _eff_max_errors: int | None = max_errors if max_errors is not None else _bcfg.max_errors
        _eff_batch_size: int | None = batch_size if batch_size is not None else _bcfg.batch_size

        # Parse --color-if FIELD:REGEX=STYLE into (field, regex, style) tuples
        color_rules: list[tuple[str, str, str]] = []
        for _cr_raw in color_rules_raw:
            if "=" in _cr_raw and ":" in _cr_raw.split("=", 1)[0]:
                _cr_field_regex, _cr_style = _cr_raw.rsplit("=", 1)
                _cr_field, _cr_regex = _cr_field_regex.split(":", 1)
                color_rules.append((_cr_field, _cr_regex, _cr_style))
            else:
                print_warning(f"--color-if: ignored malformed entry {_cr_raw!r} (expected FIELD:REGEX=STYLE)")

        # --output FORMAT: map to existing flags
        _effective_as_json = as_json
        _effective_as_jsonl = as_jsonl
        _effective_raw = raw
        _effective_csv_file = csv_file
        if output_format:
            _fmt = output_format.lower()
            if _fmt == "json":
                _effective_as_json = True
            elif _fmt == "jsonl":
                _effective_as_jsonl = True
            elif _fmt == "raw":
                _effective_raw = True
            elif _fmt == "csv":
                _effective_csv_file = _effective_csv_file or "-"
            elif _fmt == "none":
                from .output import set_output_options as _so
                _so(quiet=True, suppress_data=True)
            # "table" → no-op (default)

        # TTY auto-detection: non-interactive stdout with no explicit format → JSON
        if (not sys.stdout.isatty()
                and not _effective_as_json and not _effective_as_jsonl and not _effective_raw
                and not _effective_csv_file and not json_file
                and not format_template and not count_only
                and not pick_field and not group_by
                and not sum_field and not avg_field and not min_field and not max_field
                and not fields_only and not to_markdown and not output_schema):
            _effective_as_json = True

        # --save-as: persist this invocation as a named alias before running.
        # Secret-bearing flags are dropped (not stored) — the keychain / env
        # supplies credentials when the alias is re-run.
        if save_as:
            import shlex as _shlex
            from .audit import drop_secret_tokens
            # alias persistence lives in the alias command module; import lazily
            # to avoid an import cycle (cli imports commands for registration).
            from .commands.alias import _load_aliases, _save_aliases
            # Strip --save-as itself, then drop EVERY secret-bearing flag (same
            # coverage as the history scrubber: --api-key/--header/--proxy, the
            # secret-name regex for dynamic params like --client-secret /
            # --new-password, --body-json/--from-json, and --set secret=…) so no
            # credential or secret is persisted into the alias file.
            _raw_argv = sys.argv[1:]
            _pre: list[str] = []
            _ax = 0
            while _ax < len(_raw_argv):
                _tok = _raw_argv[_ax]
                if _tok == "--save-as" and _ax + 1 < len(_raw_argv):
                    _ax += 2
                elif _tok.startswith("--save-as="):
                    _ax += 1
                else:
                    _pre.append(_tok)
                    _ax += 1
            _alias_tokens, _dropped_secrets = drop_secret_tokens(_pre)
            if _dropped_secrets:
                print_warning(
                    "Secret-bearing flags (e.g. --api-key / --header / --proxy / "
                    "--client-secret / --body-json) were not saved with the alias. "
                    "Supply credentials via 'dnsfcli auth setup' or environment "
                    "variables so the alias works when re-run."
                )
            _alias_cmd = " ".join(_shlex.quote(t) for t in _alias_tokens)
            _aliases = _load_aliases()
            _existed = save_as in _aliases
            _aliases[save_as] = _alias_cmd
            _save_aliases(_aliases)
            print_success(f"{'Updated' if _existed else 'Saved'} alias [bold]{save_as}[/bold] → {_alias_cmd}")

        def _run_once(
            org_id_override: str | None = None,
            result_sink: list | None = None,
            _csv_override: str | None = None,
            _json_override: str | None = None,
        ) -> None:
            _eff_csv  = _csv_override  if _csv_override  is not None else _effective_csv_file
            _eff_json = _json_override if _json_override is not None else json_file
            _run_api_call(
                ctx, endpoint, function, RunOptions(
                raw=_effective_raw, verbose=verbose,
                api_key=api_key, org_id=org_id_override or org_id,
                csv_file=_eff_csv,
                csv_input=csv_input,
                show_template=show_template,
                show_plan=show_plan,
                skip_confirm=skip_confirm,
                columns=columns,
                wait=wait,
                profile=effective_profile,
                fetch_all=fetch_all,
                as_json=_effective_as_json,
                sort_by=list(sort_by) if sort_by else None,
                limit=limit,
                json_file=_eff_json,
                timeout=timeout,
                filters=list(filters) or None,
                count_only=count_only,
                body_json=body_json,
                page=page,
                page_size=page_size,
                as_jsonl=_effective_as_jsonl,
                on_error=_eff_on_error,
                concurrency=_eff_concurrency,
                grep=grep,
                unique_field=unique_field,
                format_template=format_template,
                csv_append=csv_append,
                dry_run=dry_run,
                json_input=json_input,
                cache_ttl=cache_ttl,
                org_name=org_name,
                set_fields=list(set_fields) or None,
                exclude_fields=exclude_fields,
                merge_key=merge_key,
                rate=rate,
                truncate=truncate,
                csv_delimiter=csv_delimiter,
                csv_header_case=csv_header_case,
                rename_fields=list(rename_fields) or None,
                pick_field=pick_field,
                batch_size=_eff_batch_size,
                no_header=no_header,
                retry=_eff_retry,
                errors_csv=errors_csv,
                retry_errors_csv=retry_errors_csv,
                timing=timing,
                group_by=group_by,
                select_fields=select_fields,
                sum_field=sum_field,
                avg_field=avg_field,
                min_field=min_field,
                max_field=max_field,
                map_fields=list(map_fields) or None,
                watch_changes_interval=watch_changes_interval,
                upsert=upsert,
                last=last,
                sample=sample,
                fields_only=fields_only,
                strip_nulls=strip_nulls,
                max_pages=max_pages,
                max_errors=_eff_max_errors,
                null_as=null_as,
                no_wrap=no_wrap,
                color_rules=color_rules or None,
                count_by=count_by,
                not_null_field=not_null_field,
                is_null_field=is_null_field,
                since_filter=since_filter,
                extra_headers=list(extra_headers_raw) or None,
                insecure=insecure,
                no_progress=no_progress,
                tee_file=tee_file,
                validate_only=validate_only,
                confirm_each=confirm_each,
                diff_mode=diff_mode,
                flatten=flatten,
                strip_empties=strip_empties,
                csv_null_value=csv_null_value,
                watch_until_filter=watch_until_filter,
                fail_on_empty=fail_on_empty,
                batch_delay=batch_delay,
                connect_timeout=connect_timeout,
                proxy=proxy,
                jq_expr=jq_expr,
                max_wait=max_wait,
                alert_filter=alert_filter,
                stats_field=stats_field,
                stdin_json=stdin_json,
                skip_rows=skip_rows,
                max_rows=max_rows,
                add_fields=list(add_fields) or None,
                paginate_until=paginate_until,
                batch_report=batch_report,
                org_csv=org_csv,
                color_scale=color_scale,
                format_preset=format_preset,
                fail_on_pattern=fail_on_pattern,
                filter_mode=filter_mode,
                to_markdown=to_markdown,
                output_schema=output_schema,
                exec_cmd=exec_cmd,
                transforms=list(transforms) or None,
                join_spec=join_spec,
                result_sink=result_sink,
            ))

        def _expand_org_path(path: str | None, org_id: str, org_name: str) -> str | None:
            if path is None:
                return None
            # org_id / org_name come from the API (attacker-controllable tenant
            # data in an MSP setting) and are substituted into an output FILE
            # path, so each is reduced to a safe basename (see
            # cliparams.sanitize_path_component) — no '/' or '..' can survive.
            return (
                path.replace("{org_id}", sanitize_path_component(org_id))
                    .replace("{org_name}", sanitize_path_component(org_name))
            )

        # --each-org: fetch all organizations and loop
        if each_org:
            if watch_interval:
                print_warning("--watch is ignored when combined with --each-org.")
            import re as _re_eo
            _eo_key = api_key or get_api_key(profile=effective_profile)
            if not _eo_key:
                print_error("No API key found. Run [bold]dnsfcli auth setup[/bold] first.")
                sys.exit(1)
            _eo_base = _re_eo.sub(r"/v\d+/*$", "", get_base_url(profile=effective_profile).rstrip("/"))
            # --org-csv: load org list from a CSV file instead of the API
            if org_csv:
                import csv as _org_csv_mod
                from pathlib import Path as _OrgPath
                _oc_path = _OrgPath(org_csv)
                if not _oc_path.exists():
                    print_error(f"--org-csv: file not found: {org_csv}")
                    sys.exit(1)
                _eo_orgs = []
                with _oc_path.open(encoding="utf-8-sig") as _oc_fh:
                    _oc_reader = _org_csv_mod.DictReader(_oc_fh)
                    for _oc_row in _oc_reader:
                        _oc_id = (_oc_row.get("id") or _oc_row.get("org_id") or "").strip()
                        _oc_name = (_oc_row.get("name") or _oc_row.get("org_name") or "").strip()
                        if _oc_id:
                            _eo_orgs.append({"id": _oc_id, "name": _oc_name or f"Org {_oc_id}"})
                if not _eo_orgs:
                    print_error(f"--org-csv: no rows with an 'id' or 'org_id' column found in {org_csv}")
                    sys.exit(1)
                console.print(f"[dim]--org-csv: loaded {len(_eo_orgs)} org(s) from {org_csv}[/dim]")
            else:
                try:
                    with DNSFilterClient(api_key=_eo_key, base_url=_eo_base) as _eo_cl:
                        # Paginate: an MSP can have more organizations than fit
                        # on one page, and a partial fan-out reported as success
                        # is the worst failure mode for a fleet audit.
                        _eo_raw, _eo_items = _fetch_all_pages(
                            _eo_cl, "GET", "/v1/organizations",
                            None, None, show_progress=False,
                        )
                    _eo_orgs = _eo_items if _eo_items else _unwrap(_eo_raw)
                    if not isinstance(_eo_orgs, list):
                        _eo_orgs = [_eo_raw] if isinstance(_eo_raw, dict) else []
                except APIError as exc:
                    print_error(f"--each-org: failed to list organizations: {exc}")
                    sys.exit(1)
            if org_filter:
                import re as _re_of
                try:
                    _re_of.compile(org_filter)
                except _re_of.error as _re_err:
                    print_error(f"--org-filter: invalid regex {org_filter!r}: {_re_err}")
                    sys.exit(1)
                _of_before = len(_eo_orgs)
                _eo_orgs = [
                    o for o in _eo_orgs
                    if isinstance(o, dict) and _re_of.search(
                        org_filter,
                        str((o.get("attributes") or {}).get("name") or o.get("name") or ""),
                        _re_of.IGNORECASE,
                    )
                ]
                console.print(f"[dim]--org-filter: {_of_before} → {len(_eo_orgs)} org(s) matching {org_filter!r}[/dim]")
            if max_orgs is not None and len(_eo_orgs) > max_orgs:
                console.print(f"[dim]--max-orgs: capping at {max_orgs} of {len(_eo_orgs)} org(s)[/dim]")
                _eo_orgs = _eo_orgs[:max_orgs]
            # Fan-out volume warning: N orgs each run the full command (× pages
            # when --all). It is rate-limited, but a large uncapped run against
            # one key can take a long time — surface it so it is not a surprise.
            if len(_eo_orgs) > 25 and max_orgs is None:
                _fanout_note = " (each paginated with --all)" if fetch_all else ""
                print_warning(
                    f"--each-org will run this command across {len(_eo_orgs)} organizations"
                    f"{_fanout_note}. This makes many requests on one API key and may take "
                    f"a while; use --max-orgs to cap it."
                )
            if parallel_orgs:
                from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait as _fwait
                import threading as _threading
                _print_lock = _threading.Lock()

                # Progress bars use the shared err_console, and Rich permits only
                # one live display per console — concurrent workers entering a
                # Progress would raise LiveError and lose those orgs. Disable
                # progress for the whole parallel run. (no_progress is read from
                # this scope by _run_once → _run_api_call.)
                no_progress = True

                # Guard against concurrent workers clobbering one output file:
                # a file sink must include a per-org placeholder so each worker
                # writes its own file.
                for _sink_flag, _sink_val in (("--to-csv", _effective_csv_file), ("--to-json", json_file)):
                    if _sink_val and _sink_val != "-" and "{org_id}" not in _sink_val and "{org_name}" not in _sink_val:
                        print_error(
                            f"--parallel-orgs with {_sink_flag} requires a per-org placeholder "
                            f"in the path (e.g. {_sink_flag} \"report-{{org_name}}.csv\"); otherwise "
                            f"every org would overwrite the same file."
                        )
                        sys.exit(1)
                # Warn that stdout output from multiple orgs will interleave.
                if not _effective_csv_file and not json_file:
                    print_warning(
                        "--parallel-orgs streams multiple orgs to stdout; output may "
                        "interleave. Use --to-csv/--to-json with a {org_name} placeholder "
                        "for cleanly separated per-org files."
                    )

                _stop = _threading.Event()

                def _run_org_parallel(org_item: Any) -> None:
                    if _stop.is_set():
                        return
                    _oid = str(org_item.get("id", ""))
                    _attrs = org_item.get("attributes") or {}
                    _oname = _attrs.get("name") or org_item.get("name") or f"Org {_oid}"
                    # Header under the lock so the org-separator lines stay whole;
                    # the body runs UNLOCKED to keep orgs genuinely parallel. In
                    # the clean mode (per-org file output) the body goes to that
                    # org's own file, so stdout only carries these headers.
                    with _print_lock:
                        console.rule(f"[bold]{_oname}[/bold] [dim](id: {_oid})[/dim]")
                    try:
                        _run_once(
                            org_id_override=_oid,
                            _csv_override=_expand_org_path(_effective_csv_file, _oid, _oname),
                            _json_override=_expand_org_path(json_file, _oid, _oname),
                        )
                    except SystemExit:
                        pass

                # Bound in-flight work to org_concurrency and honour Ctrl-C:
                # submit as slots free, and cancel not-yet-started orgs on stop.
                _org_iter = iter(_eo_orgs)
                _futs: set = set()
                try:
                    with ThreadPoolExecutor(max_workers=max(1, min(org_concurrency, 32))) as _pool:
                        def _submit_next_org() -> bool:
                            nxt = next(_org_iter, None)
                            if nxt is None:
                                return False
                            _futs.add(_pool.submit(_run_org_parallel, nxt))
                            return True

                        for _ in range(max(1, org_concurrency)):
                            if not _submit_next_org():
                                break
                        while _futs:
                            _done, _ = _fwait(_futs, return_when=FIRST_COMPLETED)
                            for _fut in _done:
                                _futs.discard(_fut)
                                try:
                                    _fut.result()
                                except Exception as _e:
                                    print_error(f"--parallel-orgs worker error: {_e}")
                                _submit_next_org()
                except KeyboardInterrupt:
                    _stop.set()
                    for _f in _futs:
                        _f.cancel()
                    console.print("\n[dim]Stopped — cancelling remaining organizations.[/dim]")
            else:
                for _eo_org in _eo_orgs:
                    _eo_oid = str(_eo_org.get("id", ""))
                    _eo_attrs = _eo_org.get("attributes") or {}
                    _eo_oname = _eo_attrs.get("name") or _eo_org.get("name") or f"Org {_eo_oid}"
                    console.rule(f"[bold]{_eo_oname}[/bold] [dim](id: {_eo_oid})[/dim]")
                    try:
                        _run_once(
                            org_id_override=_eo_oid,
                            _csv_override=_expand_org_path(_effective_csv_file, _eo_oid, _eo_oname),
                            _json_override=_expand_org_path(json_file, _eo_oid, _eo_oname),
                        )
                    except SystemExit:
                        pass  # continue with next org
            from .output import flush_tee as _ft_eo
            _ft_eo()
            return

        if watch_interval:
            import datetime as _dt
            import random as _random
            if fetch_all:
                print_warning(
                    "--watch with --all refetches every page each tick; "
                    "use a longer interval to avoid burning the rate budget."
                )
            _wd_prev: Any = None
            try:
                while True:
                    ts = _dt.datetime.now().strftime("%H:%M:%S")
                    console.rule(f"[dim]{ts}  (every {watch_interval}s — Ctrl-C to stop)[/dim]")
                    _wd_sink: list = [] if watch_diff else None
                    try:
                        _run_once(result_sink=_wd_sink)
                    except _WatchUntilSatisfied:
                        console.print("[bold green]Watch stopped (--watch-until condition met).[/bold green]")
                        return
                    except SystemExit:
                        pass  # keep watching even if a single iteration errors
                    except Exception as exc:
                        print_error(f"Unexpected error: {exc}")
                    if watch_diff and _wd_sink:
                        _wd_new = _wd_sink[0]
                        if _wd_prev is not None:
                            _show_watch_diff(_wd_prev, _wd_new)
                        _wd_prev = _wd_new
                    # Small jitter so many watchers (or many --each-org runs)
                    # don't align their polls into synchronized bursts.
                    _time.sleep(watch_interval + _random.uniform(0, min(2.0, watch_interval * 0.1)))
            except KeyboardInterrupt:
                console.print("\n[dim]Stopped.[/dim]")
            finally:
                from .output import flush_tee as _ft_watch
                _ft_watch()
        else:
            try:
                _run_once()
            except SystemExit:
                raise
            except Exception as exc:
                print_error(f"Unexpected error: {exc}")
                sys.exit(1)
            finally:
                # Runs on early-return output modes and sys.exit paths too, so
                # --tee always captures whatever was printed.
                from .output import flush_tee as _ft_final
                _ft_final()

    # Assemble the command: pass_context innermost, then the shared option
    # stack (see cliopts.add_dynamic_options), then the grouped-help wrapper.
    _cmd = click.pass_context(_cmd)
    _cmd = add_dynamic_options(_cmd)
    command = click.command(
        name=function,
        cls=_GroupedCommand,
        context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
        help=f"Call {endpoint}/{function} on the DNSFilter API.",
    )(_cmd)
    # _GroupedCommand._format_api_params reads these to render the API-params
    # section of --help (previously closed over via the enclosing scope).
    command.endpoint = endpoint
    command.function = function
    return command


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def app_entry(_alias_depth: int = 0) -> None:
    """Entry point that pre-processes argv to route (endpoint, function) pairs."""
    import os
    import sys
    import click

    # Build the standard typer Click group
    click_app = typer.main.get_command(app)

    args = sys.argv[1:]

    # ---------------------------------------------------------------------------
    # Early env-file scan: load --env-file before config/credential resolution so
    # env vars like DNSF_API_KEY are visible to Click's envvar= processing.
    # ---------------------------------------------------------------------------
    for _ef_idx, _ef_arg in enumerate(args):
        if _ef_arg == "--env-file" and _ef_idx + 1 < len(args):
            _load_env_file(args[_ef_idx + 1])
            break
        if _ef_arg.startswith("--env-file="):
            _load_env_file(_ef_arg[len("--env-file="):])
            break

    # ---------------------------------------------------------------------------
    # Early output-option detection: apply --quiet / --no-color / NO_COLOR before
    # any output can happen.  Also load the config file for its defaults.
    # ---------------------------------------------------------------------------
    cfg = load_config()
    _early_quiet    = "--quiet" in args or "-q" in args or cfg.quiet or bool(os.environ.get("DNSFCLI_QUIET"))
    _early_no_color = "--no-color" in args or bool(os.environ.get("NO_COLOR")) or bool(os.environ.get("DNSFCLI_NO_COLOR")) or cfg.no_color
    if _early_quiet or _early_no_color:
        set_output_options(quiet=_early_quiet, no_color=_early_no_color)

    # ---------------------------------------------------------------------------
    # Shell-completion mode: populate all dynamic endpoint commands so the
    # completion engine sees them, then delegate entirely to Click.
    #
    # Two triggers:
    #   1. _DNSFCLI_COMPLETE (or _DNSFCLI_PY_COMPLETE) env var set by the
    #      completion script at tab-press time.
    #   2. --show-completion or --install-completion in the raw args (script
    #      generation / installation — we still want endpoints visible so the
    #      generated script references them correctly, though that's a no-op
    #      for Typer's script generator, it prevents routing confusion).
    # ---------------------------------------------------------------------------
    prog_norm = os.path.basename(sys.argv[0]).replace("-", "_").replace(".", "_").upper()
    _completion_env_vars = (f"_{prog_norm}_COMPLETE", "_DNSFCLI_COMPLETE")
    is_completion = (
        any(os.environ.get(v) for v in _completion_env_vars)
        or "--show-completion" in args
        or "--install-completion" in args
    )
    if is_completion:
        _populate_dynamic_commands(click_app)
        # Patch click's _resolve_context so it handles TyperGroup, which is NOT
        # a subclass of click.Group even though it has resolve_command().
        # Without this patch, completion stops at the top level and never
        # recurses into endpoint groups.
        _patch_resolve_context_for_typer()
        # Pass prog_name="dnsfcli" so Click derives the correct complete var
        # (_DNSFCLI_COMPLETE) regardless of how the script is invoked
        # (e.g. "dnsfcli.py" during development vs. "dnsfcli" when installed).
        try:
            click_app.main(args=args, prog_name="dnsfcli", standalone_mode=True)
        except SystemExit as exc:
            sys.exit(exc.code)
        return

    # ---------------------------------------------------------------------------
    # Hoist global flags so they work regardless of where the user placed them
    # (e.g. `dnsfcli --raw users show --id 1` or `dnsfcli --to-csv out.csv users list`).
    # Bool flags and value-bearing flags are both handled here.
    # ---------------------------------------------------------------------------
    _BOOL_FLAGS: frozenset[str] = frozenset({"--raw", "-r", "--template", "--plan", "--wait", "--all", "--json", "--no-color", "--quiet", "-q", "--count", "--jsonl", "--append", "--dry-run", "--each-org", "--no-header", "--timing", "--upsert", "--fields", "--strip-nulls", "--no-wrap", "--validate-only", "--confirm-each", "--diff-mode", "--no-progress", "--insecure", "--parallel-orgs", "--flatten", "--strip-empties", "--fail-on-empty", "--quiet-ok", "--watch-diff", "--stdin-json", "--output-schema", "-v", "-y"})
    _VALUE_FLAGS: frozenset[str] = frozenset({"--to-csv", "--from-csv", "--columns", "--profile", "--sort", "--limit", "--last", "--to-json", "--timeout", "--filter", "--body-json", "--page", "--page-size", "--on-error", "--concurrency", "--watch", "--grep", "--unique", "--format", "--from-json", "--cache-ttl", "--org-name", "--set", "--exclude", "--merge-key", "--rate", "--truncate", "--csv-delimiter", "--retry", "--errors-to-csv", "--retry-errors-csv", "--csv-header-case", "--rename", "--pick", "--batch-size", "--group-by", "--select", "--sum", "--avg", "--min", "--max", "--map", "--watch-changes", "--max-pages", "--max-errors", "--sample", "--save-as", "--null-as", "--since", "--not-null", "--is-null", "--header", "--color-if", "--count-by", "--tee", "--output", "--org-concurrency", "--csv-null", "--watch-until", "--delay", "--org-filter", "--max-orgs", "--preset", "--connect-timeout", "--proxy", "--jq", "--max-wait", "--alert", "--table-style", "--stats", "--env-file", "--log-file", "--skip-rows", "--max-rows", "--add-field", "--paginate-until", "--org-csv", "--batch-report", "--color-scale", "--format-preset", "--fail-on-pattern", "--filter-mode", "--to-markdown", "--exec", "--transform", "--join", "--bundle"})

    injected: list[str] = []
    clean_args: list[str] = []
    i = 0
    while i < len(args):
        token = args[i]
        if token in _BOOL_FLAGS:
            injected.append("--raw" if token in ("-r",) else token)   # normalise -r
        elif token in _VALUE_FLAGS:
            # Consume the flag AND its following value token. The value may
            # itself start with '-' (--truncate -1, --sort -created_at), so
            # take the next token unconditionally — same as Click would.
            if i + 1 < len(args):
                injected.extend([token, args[i + 1]])
                i += 1                        # skip value token
            else:
                clean_args.append(token)      # no value -- pass through; Click will error
        else:
            clean_args.append(token)
        i += 1
    args = clean_args  # routing uses the flag-stripped list

    static_commands = set(click_app.commands.keys()) if hasattr(click_app, "commands") else set()

    # If the first real arg is a known static sub-command (auth, endpoints, …)
    # or looks like a flag, hand off to Typer/Click unchanged. Wrap it in the
    # same safety net as the dynamic path so a keychain/backend failure (or any
    # unhandled error) in auth/config/etc. surfaces as a clean message, not a
    # raw traceback to a non-technical user.
    if not args or args[0].startswith("-") or args[0] in static_commands:
        try:
            app()
        except SystemExit:
            raise
        except KeychainError as exc:
            print_error(str(exc))
            sys.exit(1)
        except Exception as exc:
            print_error(f"Unexpected error: {exc}")
            sys.exit(1)
        return

    # First arg is an endpoint; second (if non-flag) is the function.
    endpoint = args[0]

    # Direct alias invocation: `dnsfcli NAME [args]` where NAME is a saved
    # alias (and not a real endpoint, which always takes precedence).
    if endpoint not in list_endpoints():
        from .commands.alias import _load_aliases  # lazy: avoids an import cycle
        _aliases = _load_aliases()
        if endpoint in _aliases:
            if _alias_depth >= 5:
                print_error(f"Alias '{endpoint}' expands recursively — aborting.")
                sys.exit(1)
            import shlex as _shlex_alias
            _alias_argv = _shlex_alias.split(_aliases[endpoint])
            sys.argv = [sys.argv[0]] + _alias_argv + args[1:] + injected
            return app_entry(_alias_depth=_alias_depth + 1)
        # Unknown endpoint (and not an alias): error with suggestions, exit 1.
        import difflib as _difflib
        print_error(f"Unknown endpoint '{endpoint}'.")
        _suggestions = _difflib.get_close_matches(
            endpoint, list_endpoints() + list(_aliases), n=3, cutoff=0.6
        )
        if _suggestions:
            console.print(f"Did you mean: [bold]{', '.join(_suggestions)}[/bold]?")
        console.print("[dim]Run [bold]dnsfcli endpoints[/bold] to list available endpoints.[/dim]")
        sys.exit(1)

    if len(args) >= 2 and not args[1].startswith("-"):
        function = args[1]
        _known_fns = list_functions(endpoint)
        if function not in _known_fns:
            import difflib as _difflib
            print_error(f"Unknown function '{function}' for endpoint '{endpoint}'.")
            _fn_sugg = _difflib.get_close_matches(function, _known_fns, n=3, cutoff=0.6)
            if _fn_sugg:
                console.print(f"Did you mean: [bold]{', '.join(_fn_sugg)}[/bold]?")
            console.print(f"Available functions: {', '.join(_known_fns)}")
            sys.exit(1)
        remaining = args[2:] + injected   # append hoisted flags at the end
    else:
        # No function provided -- show available functions for this endpoint.
        console.print(f"[bold]Endpoint:[/bold] {endpoint}")
        funcs = list_functions(endpoint)
        console.print(f"Available functions: {', '.join(funcs)}")
        console.print(f"\nUsage: [bold]dnsfcli {endpoint} [FUNCTION] [OPTIONS][/bold]")
        sys.exit(0)

    # Build a transient Click command and invoke it
    cmd = _make_dynamic_command(endpoint, function)
    try:
        cmd.main(args=remaining, standalone_mode=True)
    except SystemExit as exc:
        sys.exit(exc.code)
    except Exception as exc:
        # Final safety net -- nothing should reach here, but if it does,
        # print cleanly rather than dumping a traceback.
        print_error(f"Unexpected error: {exc}")
        sys.exit(1)


# Register all sub-command groups (auth, audit, config, alias, history, diff,
# cache, misc). Imported last so cli's own helpers are defined first, avoiding
# any import cycle with modules that reference them.
from . import commands  # noqa: E402,F401
