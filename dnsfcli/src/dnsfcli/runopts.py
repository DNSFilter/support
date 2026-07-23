"""Typed container for the options a single API run accepts.

Generated to mirror _run_api_call's keyword parameters exactly. Carrying
them as one object replaces a 100+-argument signature and lets the run
pipeline pass a single value instead of threading every flag by hand.
"""

from __future__ import annotations

from dataclasses import dataclass


from .auth import DEFAULT_PROFILE


@dataclass
class RunOptions:
    raw: bool = False
    verbose: bool = False
    api_key: str | None = None
    org_id: str | None = None
    csv_file: str | None = None
    csv_input: str | None = None
    show_template: bool = False
    show_plan: bool = False
    skip_confirm: bool = False
    columns: list[str] | None = None
    wait: bool = False
    profile: str = DEFAULT_PROFILE
    fetch_all: bool = False
    as_json: bool = False
    sort_by: list[str] | None = None
    limit: int | None = None
    json_file: str | None = None
    timeout: float | None = None
    filters: list[str] | None = None
    count_only: bool = False
    body_json: str | None = None
    page: int | None = None
    page_size: int | None = None
    as_jsonl: bool = False
    on_error: str = 'continue'
    concurrency: int = 1
    grep: str | None = None
    unique_field: str | None = None
    format_template: str | None = None
    csv_append: bool = False
    dry_run: bool = False
    json_input: str | None = None
    cache_ttl: int | None = None
    org_name: str | None = None
    set_fields: list[str] | None = None
    exclude_fields: list[str] | None = None
    merge_key: str | None = None
    rate: float | None = None
    truncate: int | None = None
    csv_delimiter: str = ','
    rename_fields: list[str] | None = None
    pick_field: str | None = None
    batch_size: int | None = None
    no_header: bool = False
    csv_header_case: str | None = None
    retry: int = 0
    errors_csv: str | None = None
    retry_errors_csv: str | None = None
    timing: bool = False
    group_by: str | None = None
    select_fields: list[str] | None = None
    sum_field: str | None = None
    avg_field: str | None = None
    min_field: str | None = None
    max_field: str | None = None
    map_fields: list[str] | None = None
    watch_changes_interval: int | None = None
    upsert: bool = False
    last: int | None = None
    sample: int | None = None
    fields_only: bool = False
    strip_nulls: bool = False
    max_pages: int | None = None
    max_errors: int | None = None
    null_as: str | None = None
    no_wrap: bool = False
    color_rules: list[tuple[str, str, str]] | None = None
    count_by: str | None = None
    not_null_field: str | None = None
    is_null_field: str | None = None
    since_filter: str | None = None
    extra_headers: list[str] | None = None
    insecure: bool = False
    no_progress: bool = False
    tee_file: str | None = None
    validate_only: bool = False
    confirm_each: bool = False
    diff_mode: bool = False
    skip_rows: int = 0
    max_rows: int | None = None
    add_fields: list[str] | None = None
    paginate_until: str | None = None
    batch_report: str | None = None
    org_csv: str | None = None
    color_scale: str | None = None
    format_preset: str | None = None
    flatten: bool = False
    strip_empties: bool = False
    csv_null_value: str | None = None
    watch_until_filter: str | None = None
    fail_on_empty: bool = False
    batch_delay: int | None = None
    connect_timeout: float | None = None
    proxy: str | None = None
    jq_expr: str | None = None
    max_wait: float | None = None
    alert_filter: str | None = None
    stats_field: str | None = None
    result_sink: list | None = None
    stdin_json: bool = False
    fail_on_pattern: str | None = None
    filter_mode: str = 'and'
    to_markdown: str | None = None
    output_schema: bool = False
    exec_cmd: str | None = None
    transforms: list[str] | None = None
    join_spec: str | None = None
