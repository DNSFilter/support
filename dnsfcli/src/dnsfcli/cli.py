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

import ast
import json
import logging
import os
import sys
from typing import Any, Optional

import typer
from rich.console import Console
from rich.table import Table

from .auth import (
    DEFAULT_PROFILE,
    clear_all,
    clear_profile,
    credentials_summary,
    get_active_profile,
    get_api_key,
    get_base_url,
    get_org_id,
    list_profiles,
    set_active_profile,
    store_api_key,
    store_base_url,
    store_org_id,
)
from .audit import log_event, log_history
from .client import APIError, DNSFilterClient
from .config import config_path, load_config
from .endpoints import get_operation, list_endpoints, list_functions
from .output import (
    _unwrap,
    console,
    err_console,
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

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_loaded_env_files: set[str] = set()


def _load_env_file(path: str) -> None:
    """Load KEY=VALUE pairs from a .env file into os.environ (skips already-set vars).

    Idempotent per path — app_entry loads it early for envvar= resolution and
    _cmd loads it again; the second call (and its failure warning) is skipped.
    """
    if path in _loaded_env_files:
        return
    _loaded_env_files.add(path)
    import os as _os_ef
    try:
        with open(path, encoding="utf-8") as _ef_fh:
            for _ef_line in _ef_fh:
                _ef_line = _ef_line.strip()
                if not _ef_line or _ef_line.startswith("#"):
                    continue
                if "=" in _ef_line:
                    _ef_key, _, _ef_val = _ef_line.partition("=")
                    _ef_key = _ef_key.strip()
                    _ef_val = _ef_val.strip().strip('"').strip("'")
                    if _ef_key:
                        _os_ef.environ.setdefault(_ef_key, _ef_val)
    except OSError as _ef_exc:
        import sys as _sys_ef
        _sys_ef.stderr.write(f"Warning: --env-file: cannot read {path!r}: {_ef_exc}\n")


# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

app = typer.Typer(
    name="dnsfcli",
    help="Command-line interface for the DNSFilter API.\n\nUsage: dnsfcli [ENDPOINT] [FUNCTION] [OPTIONS]",
    add_completion=True,
    no_args_is_help=True,
    rich_markup_mode="rich",
    pretty_exceptions_enable=False,
)

auth_app = typer.Typer(help="Manage stored API credentials.", rich_markup_mode="rich")
app.add_typer(auth_app, name="auth")

audit_app = typer.Typer(help="View and manage the local audit log.", rich_markup_mode="rich")
app.add_typer(audit_app, name="audit")

# ---------------------------------------------------------------------------
# Argument parsing helpers
# ---------------------------------------------------------------------------


def _parse_extra_args(args: list[str]) -> dict[str, str]:
    """Parse --key value or --key=value pairs from the extra args list."""
    result: dict[str, str] = {}
    i = 0
    while i < len(args):
        token = args[i]
        if token.startswith("--"):
            key = token[2:]
            if "=" in key:
                k, v = key.split("=", 1)
                result[k] = v
            elif i + 1 < len(args) and not args[i + 1].startswith("--"):
                result[key] = args[i + 1]
                i += 1
            else:
                result[key] = "true"
        elif token.startswith("-") and len(token) == 2:
            # short flags like -v
            key = token[1:]
            if i + 1 < len(args) and not args[i + 1].startswith("-"):
                result[key] = args[i + 1]
                i += 1
            else:
                result[key] = "true"
        i += 1
    return result


def _api_key_flag_on_cli() -> bool:
    """True when --api-key/-k was literally typed on the command line.

    The Click options also accept DNSF_API_KEY via envvar=; the exposure
    warning must fire only for the flag form, not for the (recommended)
    environment variable.
    """
    return any(
        tok in ("--api-key", "-k") or tok.startswith(("--api-key=", "-k="))
        for tok in sys.argv[1:]
    )


def _normalize_param_keys(params: dict[str, Any]) -> dict[str, Any]:
    """Map dashed CLI param names to underscore API field names.

    Help text renders API params in dashed form (--organization-id), so both
    spellings must reach the API as the canonical underscore name. Called
    AFTER internal-flag cleanup, which matches on dashed names.
    """
    return {k.replace("-", "_"): v for k, v in params.items()}


def _coerce_value(value: str) -> Any:
    """Coerce a CLI string value to the most appropriate Python type.

    Order of attempts:
      1. boolean literals   "true" / "false"
      2. JSON array/object  "[…]" / "{…}"
      3. integer
      4. float
      5. plain string (returned as-is)
    """
    if value.lower() == "true":
        return True
    if value.lower() == "false":
        return False
    stripped = value.strip()
    if stripped.startswith(("[", "{")):
        try:
            import json as _json
            return _json.loads(stripped)
        except ValueError:
            pass
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        pass
    return value


def _build_path(
    template: str,
    params: dict[str, Any],
    *,
    raise_on_missing: bool = False,
) -> tuple[str, dict[str, Any]]:
    """Substitute path placeholders in *template* from *params*.

    If a required placeholder is missing:
      - ``raise_on_missing=True``  → raises ``ValueError`` (used by CSV row loop)
      - ``raise_on_missing=False`` → prints an error and calls ``sys.exit(1)``
    """
    remaining = dict(params)
    path = template
    import re
    from urllib.parse import quote as _urlquote
    for match in re.finditer(r"\{(\w+)\}", template):
        key = match.group(1)
        if key in remaining:
            # URL-encode so a value containing / ? # .. cannot alter the
            # request path shape (e.g. --id "../other").
            path = path.replace(
                f"{{{key}}}", _urlquote(str(remaining.pop(key)), safe="")
            )
        else:
            if raise_on_missing:
                raise ValueError(
                    f"Required path parameter '{key}' not provided"
                )
            print_error(
                f"Required path parameter [bold]--{key}[/bold] was not provided.",
                f"Path template: {template}",
            )
            sys.exit(1)
    return path, remaining


# ---------------------------------------------------------------------------
# auth sub-commands
# ---------------------------------------------------------------------------


@auth_app.command("setup")
def auth_setup(
    api_key: Optional[str] = typer.Option(None, "--api-key", "-k", help="DNSFilter API key (prompted if omitted)."),
    org_id: Optional[str] = typer.Option(None, "--org-id", "-o", help="Default organization ID (optional)."),
    base_url: Optional[str] = typer.Option(None, "--base-url", "-u", help="API base URL override."),
    profile: Optional[str] = typer.Option(None, "--profile", "-p", envvar="DNSF_PROFILE", help="Named credential profile to configure (default: active profile)."),
) -> None:
    """Store API credentials in the OS keychain."""
    effective_profile = profile or get_active_profile()
    if api_key is None:
        api_key = typer.prompt(f"DNSFilter API key [{effective_profile}]", hide_input=True)

    store_api_key(api_key.strip(), profile=effective_profile)
    print_success(f"API key stored in keychain (profile: {effective_profile}).")

    if org_id:
        store_org_id(org_id.strip(), profile=effective_profile)
        print_success(f"Default org ID '{org_id}' stored.")

    if base_url:
        store_base_url(base_url.strip(), profile=effective_profile)
        print_success(f"Base URL '{base_url}' stored.")


@auth_app.command("show")
def auth_show(
    profile: Optional[str] = typer.Option(None, "--profile", "-p", envvar="DNSF_PROFILE", help="Named credential profile to show (default: active profile)."),
) -> None:
    """Display stored credentials (key is masked)."""
    effective_profile = profile or get_active_profile()
    info = credentials_summary(profile=effective_profile)
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column("Field", style="bold cyan")
    table.add_column("Value")
    for k, v in info.items():
        table.add_row(k, v)
    console.print(table)


@auth_app.command("clear")
def auth_clear(
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt."),
    profile: Optional[str] = typer.Option(None, "--profile", "-p", envvar="DNSF_PROFILE", help="Named credential profile to clear (default: active profile)."),
    all_profiles: bool = typer.Option(False, "--all", help="Clear ALL profiles."),
) -> None:
    """Remove stored credentials from the keychain."""
    if all_profiles:
        if not yes:
            typer.confirm("Remove credentials for ALL profiles?", abort=True)
        clear_all()
        print_success("All credentials cleared.")
    else:
        effective_profile = profile or get_active_profile()
        if not yes:
            typer.confirm(f"Remove stored credentials for profile '{effective_profile}'?", abort=True)
        clear_profile(effective_profile)
        print_success(f"Credentials cleared (profile: {effective_profile}).")


@auth_app.command("verify")
def auth_verify(
    profile: Optional[str] = typer.Option(None, "--profile", "-p", envvar="DNSF_PROFILE", help="Named credential profile to verify (default: active profile)."),
    all_profiles: bool = typer.Option(False, "--all", "-a", help="Test every configured profile and report pass/fail for each."),
) -> None:
    """Test stored API credentials by calling /organizations."""
    import time as _time_av
    if all_profiles:
        profiles_to_test = list_profiles()
        any_failed = False
        tbl = Table(show_header=True, header_style="bold cyan")
        tbl.add_column("Profile", no_wrap=True)
        tbl.add_column("Status")
        tbl.add_column("Latency", justify="right")
        tbl.add_column("Detail")
        for p in profiles_to_test:
            _key = get_api_key(profile=p)
            if not _key:
                tbl.add_row(p, "[dim]no key[/dim]", "[dim]—[/dim]", "[dim]run dnsfcli auth setup[/dim]")
                any_failed = True
                continue
            _base = get_base_url(profile=p)
            _t0 = _time_av.perf_counter()
            try:
                with DNSFilterClient(api_key=_key, base_url=_base) as _cl:
                    _cl.get("/v1/organizations")
                _ms = int((_time_av.perf_counter() - _t0) * 1000)
                from .auth import store_last_verified as _slv
                _slv(profile=p)
                tbl.add_row(p, "[green]✓ ok[/green]", f"{_ms}ms", "")
            except APIError as exc:
                _ms = int((_time_av.perf_counter() - _t0) * 1000)
                tbl.add_row(p, "[red]✗ fail[/red]", f"{_ms}ms", str(exc))
                any_failed = True
        console.print(tbl)
        if any_failed:
            raise typer.Exit(code=1)
        return
    effective_profile = profile or get_active_profile()
    api_key = get_api_key(profile=effective_profile)
    if not api_key:
        print_error(f"No API key stored for profile '{effective_profile}'. Run [bold]dnsfcli auth setup[/bold] first.")
        raise typer.Exit(code=1)
    base_url = get_base_url(profile=effective_profile)
    _t0 = _time_av.perf_counter()
    with DNSFilterClient(api_key=api_key, base_url=base_url) as client:
        try:
            client.get("/v1/organizations")
            _ms = int((_time_av.perf_counter() - _t0) * 1000)
            from .auth import store_last_verified as _slv_single
            _slv_single(profile=effective_profile)
            print_success(f"Credentials are valid (profile: {effective_profile}, {_ms}ms).")
        except APIError as exc:
            print_error(f"Verification failed: {exc}")
            raise typer.Exit(code=1)


@auth_app.command("list")
def auth_list() -> None:
    """List all configured credential profiles."""
    from .auth import get_last_verified as _glv
    profiles = list_profiles()
    active = get_active_profile()
    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("Profile")
    table.add_column("Active")
    table.add_column("API Key")
    table.add_column("Org ID")
    table.add_column("Base URL")
    table.add_column("Last Verified")
    for p in profiles:
        info = credentials_summary(profile=p)
        marker = "[green]✓[/green]" if p == active else ""
        last_v = _glv(profile=p) or "[dim]never[/dim]"
        table.add_row(p, marker, info["api_key"], info["org_id"], info["base_url"], last_v)
    console.print(table)


@auth_app.command("use")
def auth_use(
    profile_name: str = typer.Argument(..., help="Profile name to make active."),
) -> None:
    """Set the active credential profile used when --profile is not specified."""
    profiles = list_profiles()
    if profile_name not in profiles:
        print_warning(
            f"Profile '{profile_name}' has no stored credentials yet. "
            f"Run [bold]dnsfcli auth setup --profile {profile_name}[/bold] to configure it."
        )
    set_active_profile(profile_name)
    print_success(f"Active profile set to '{profile_name}'.")


@auth_app.command("check-expiry")
def auth_check_expiry(
    days: int = typer.Option(30, "--days", "-d", help="Warn if last verification is older than N days."),
    all_profiles: bool = typer.Option(False, "--all", "-a", help="Check all configured profiles."),
) -> None:
    """Warn if API credentials have not been verified recently.

    Uses the timestamp recorded by `dnsfcli auth verify`.  Run verify first
    if the timestamp is missing.

    Example:

      dnsfcli auth check-expiry --days 7
    """
    import datetime
    from .auth import get_last_verified as _glv_exp

    def _check(p: str) -> bool:
        ts = _glv_exp(profile=p)
        if not ts:
            print_warning(f"Profile '{p}': never verified — run [bold]dnsfcli auth verify --profile {p}[/bold]")
            return False
        try:
            verified_at = datetime.datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ")
            age_days = (datetime.datetime.utcnow() - verified_at).days
            if age_days > days:
                print_warning(
                    f"Profile '{p}': last verified {age_days} days ago ({ts}) — "
                    f"run [bold]dnsfcli auth verify --profile {p}[/bold] to refresh."
                )
                return False
            else:
                print_success(f"Profile '{p}': last verified {age_days} day(s) ago ({ts}) — OK.")
                return True
        except ValueError:
            print_warning(f"Profile '{p}': unrecognized timestamp format {ts!r}")
            return False

    if all_profiles:
        _profiles = list_profiles()
        any_stale = any(not _check(p) for p in _profiles)
        if any_stale:
            raise typer.Exit(code=1)
    else:
        effective = get_active_profile()
        if not _check(effective):
            raise typer.Exit(code=1)


@auth_app.command("whoami")
def auth_whoami(
    profile: Optional[str] = typer.Option(None, "--profile", "-p", envvar="DNSF_PROFILE", help="Profile to inspect (default: active profile)."),
) -> None:
    """Show the active credential profile at a glance.

    Displays the profile name, a redacted API key prefix, base URL, and org ID.
    """
    effective = profile or get_active_profile()
    key = get_api_key(profile=effective)
    org = get_org_id(profile=effective)
    base = get_base_url(profile=effective)

    key_display = f"{key[:8]}…" if key and len(key) > 8 else (key or "[dim]not set[/dim]")

    from rich.table import Table as _Table
    tbl = _Table(show_header=False, box=None, padding=(0, 2))
    tbl.add_column("Key", style="bold cyan", no_wrap=True, min_width=12)
    tbl.add_column("Value")
    tbl.add_row("Profile", f"[bold]{effective}[/bold]")
    tbl.add_row("API key", key_display)
    tbl.add_row("Base URL", base or "[dim]not set[/dim]")
    tbl.add_row("Org ID", org or "[dim]not set[/dim]")
    console.print(tbl)


@auth_app.command("copy")
def auth_copy_cmd(
    source: str = typer.Argument(..., help="Profile to copy credentials from."),
    dest: str = typer.Argument(..., help="Profile to copy credentials to."),
) -> None:
    """Duplicate an existing credential profile under a new name.

    Example:

      dnsfcli auth copy default staging
    """
    from .auth import get_api_key as _get_key, get_org_id as _get_org, get_base_url as _get_base
    from .auth import store_api_key as _store_key, store_org_id as _store_org, store_base_url as _store_base

    src_key = _get_key(profile=source)
    if not src_key:
        print_error(f"No credentials found for profile '{source}'.")
        raise typer.Exit(1)
    src_org = _get_org(profile=source)
    src_base = _get_base(profile=source)

    _store_key(src_key, profile=dest)
    if src_org:
        _store_org(src_org, profile=dest)
    _store_base(src_base, profile=dest)
    print_success(f"Copied profile [bold]{source}[/bold] → [bold]{dest}[/bold]")


@auth_app.command("export")
def auth_export(
    profile: Optional[str] = typer.Option(None, "--profile", "-p", envvar="DNSF_PROFILE", help="Profile to export (default: active profile)."),
    shell: str = typer.Option("bash", "--shell", "-s", help="Shell syntax: bash, fish, powershell."),
) -> None:
    """Print shell export statements for the stored credentials.

    Useful for CI/CD pipelines and environments where the OS keychain
    is unavailable.  Pipe into eval or source to activate in the current shell.

    Example:

      eval "$(dnsfcli auth export)"
    """
    effective_profile = profile or get_active_profile()
    api_key_val  = get_api_key(profile=effective_profile)
    org_id_val   = get_org_id(profile=effective_profile)
    base_url_val = get_base_url(profile=effective_profile)

    if not api_key_val:
        print_error(f"No credentials stored for profile '{effective_profile}'. Run [bold]dnsfcli auth setup[/bold] first.")
        raise typer.Exit(1)

    shell_lower = shell.lower()

    import shlex as _shlex_ae

    def _export(key: str, value: str) -> str:
        if shell_lower == "fish":
            return f"set -gx {key} {_shlex_ae.quote(value)};"
        if shell_lower in ("powershell", "pwsh"):
            # PowerShell single-quoted strings are literal; embedded single
            # quotes are escaped by doubling.
            escaped = value.replace("'", "''")
            return f"$env:{key} = '{escaped}'"
        return f"export {key}={_shlex_ae.quote(value)}"

    lines = [_export("DNSF_API_KEY", api_key_val)]
    if org_id_val:
        lines.append(_export("DNSF_ORG_ID", org_id_val))
    if base_url_val and base_url_val != "https://api.dnsfilter.com":
        lines.append(_export("DNSF_BASE_URL", base_url_val))
    if effective_profile != "default":
        lines.append(_export("DNSF_PROFILE", effective_profile))

    import sys as _sys_ae
    if _sys_ae.stderr.isatty():
        err_console.print(
            "[bold yellow]Warning:[/bold yellow] printing credential to stdout. "
            "Ensure your terminal scrollback and shell history are secured.",
            highlight=False,
        )
    for line in lines:
        console.print(line, highlight=False, markup=False)


# ---------------------------------------------------------------------------
# audit sub-commands
# ---------------------------------------------------------------------------


@audit_app.command("show")
def audit_show(
    last: int = typer.Option(20, "--last", "-n", help="Show the N most recent events."),
    since: Optional[str] = typer.Option(None, "--since", help="Only show events on or after this date (YYYY-MM-DD)."),
    endpoint: Optional[str] = typer.Option(None, "--endpoint", "-e", help="Filter by endpoint name."),
) -> None:
    """Display recent write operations from the audit log."""
    from .audit import log_path, read_events
    from rich.table import Table

    since_ts = f"{since}T00:00:00Z" if since else None
    events = read_events(last=last, since=since_ts, endpoint_filter=endpoint)

    if not events:
        console.print(f"[dim]No audit events found. Log: {log_path()}[/dim]")
        return

    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("Timestamp", style="dim", no_wrap=True)
    table.add_column("Org")
    table.add_column("Endpoint")
    table.add_column("Function")
    table.add_column("Method")
    table.add_column("Path")
    table.add_column("Status")

    for e in events:
        status = str(e.get("status", ""))
        status_style = "green" if str(status).startswith("2") else "red"
        if e.get("error"):
            status = f"{status} ✗"
        table.add_row(
            e.get("ts", ""),
            str(e.get("org_id") or ""),
            e.get("endpoint", ""),
            e.get("function", ""),
            e.get("method", ""),
            e.get("path", ""),
            f"[{status_style}]{status}[/{status_style}]",
        )

    console.print(table)
    console.print(f"[dim]Log: {log_path()}[/dim]")


@audit_app.command("clear")
def audit_clear(
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt."),
) -> None:
    """Delete the audit log and its rotation backup."""
    from .audit import clear_log, log_path
    if not yes:
        typer.confirm(f"Delete audit log at {log_path()}?", abort=True)
    clear_log()
    print_success("Audit log cleared.")


@audit_app.command("export")
def audit_export_cmd(
    out: str = typer.Option(..., "--out", "-o", help="Output CSV file path."),
    last: int = typer.Option(1000, "--last", "-n", help="Export the N most recent events (default 1000)."),
    since: Optional[str] = typer.Option(None, "--since", help="Only export events on or after this date (YYYY-MM-DD)."),
    endpoint: Optional[str] = typer.Option(None, "--endpoint", "-e", help="Filter by endpoint name."),
) -> None:
    """Export the audit log to a CSV file.

    Examples:

      dnsfcli audit export --out audit.csv

      dnsfcli audit export --out audit.csv --since 2025-01-01
    """
    from .audit import read_events
    import csv as _csv

    since_ts = f"{since}T00:00:00Z" if since else None
    events = read_events(last=last, since=since_ts, endpoint_filter=endpoint)

    if not events:
        console.print("[dim]No audit events to export.[/dim]")
        return

    fields = ["ts", "org_id", "endpoint", "function", "method", "path", "status", "error"]
    import pathlib as _pl
    _pl.Path(out).parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", newline="", encoding="utf-8") as fh:
        w = _csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(events)
    print_success(f"Exported {len(events)} event(s) to {out}")


# ---------------------------------------------------------------------------
# endpoints sub-command (discovery / help)
# ---------------------------------------------------------------------------


@app.command("endpoints")
def show_endpoints(
    endpoint: Optional[str] = typer.Argument(None, help="Show functions for a specific endpoint."),
) -> None:
    """List known API endpoints and their available functions."""
    if endpoint:
        funcs = list_functions(endpoint)
        console.print(f"[bold cyan]{endpoint}[/bold cyan] functions:")
        for fn in funcs:
            console.print(f"  [green]{fn}[/green]")
    else:
        eps = list_endpoints()
        table = Table("Endpoint", "Functions", show_header=True, header_style="bold cyan")
        from .endpoints import REGISTRY
        for name in eps:
            ep = REGISTRY[name]
            fns = ", ".join(sorted(ep.operations.keys()))
            table.add_row(name, fns)
        console.print(table)
        console.print("\n[dim]Run [bold]dnsfcli ENDPOINT[/bold] to list one endpoint's functions.[/dim]")


# ---------------------------------------------------------------------------
# doctor — diagnostics / health check
# ---------------------------------------------------------------------------


@app.command("doctor")
def doctor(
    profile: Optional[str] = typer.Option(None, "--profile", "-p", envvar="DNSF_PROFILE", help="Profile to check (default: active profile)."),
) -> None:
    """Check credentials, connectivity, and configuration.

    Runs a series of non-destructive checks and reports their status.
    Exits 0 when all checks pass, 1 otherwise.
    """
    from . import __version__
    import sys as _sys

    effective_profile = profile or get_active_profile()
    all_ok = True

    console.print(f"\n[bold]dnsfcli[/bold] [dim]{__version__}[/dim]  •  Python {_sys.version.split()[0]}\n")

    # ── Config file ───────────────────────────────────────────────────────────
    cfg_path = config_path()
    if cfg_path.exists():
        import tomllib as _doctor_toml
        try:
            with open(cfg_path, "rb") as _cfg_fh:
                _doctor_toml.load(_cfg_fh)
            console.print(f"[green]✓[/green] Config file found and parses: [dim]{cfg_path}[/dim]")
        except Exception as _cfg_exc:
            console.print(
                f"[red]✗[/red] Config file exists but does NOT parse — defaults are in use.\n"
                f"    [dim]{cfg_path}[/dim]\n"
                f"    [red]{_cfg_exc}[/red]"
            )
            all_ok = False
    else:
        console.print(f"[dim]  Config file not found (optional): {cfg_path}[/dim]")

    # ── Credentials ───────────────────────────────────────────────────────────
    api_key_val  = get_api_key(profile=effective_profile)
    org_id_val   = get_org_id(profile=effective_profile)
    base_url_val = get_base_url(profile=effective_profile)

    if api_key_val:
        masked = f"{api_key_val[:6]}…{api_key_val[-4:]}" if len(api_key_val) > 10 else "***"
        console.print(f"[green]✓[/green] API key stored (profile: {effective_profile}): [dim]{masked}[/dim]")
    else:
        console.print(f"[red]✗[/red] No API key for profile '{effective_profile}'. Run [bold]dnsfcli auth setup[/bold].")
        all_ok = False

    if org_id_val:
        console.print(f"[green]✓[/green] Default org ID: [dim]{org_id_val}[/dim]")
    else:
        console.print("[dim]  No default org ID set (optional — pass --org-id per call or set DNSF_ORG_ID).[/dim]")

    if base_url_val != "https://api.dnsfilter.com":
        console.print(f"[yellow]  Non-default base URL:[/yellow] [dim]{base_url_val}[/dim]")
    else:
        console.print(f"[green]✓[/green] Base URL: [dim]{base_url_val}[/dim]")

    # ── Connectivity ─────────────────────────────────────────────────────────
    if api_key_val:
        import re as _re
        base = _re.sub(r"/v\d+/*$", "", base_url_val.rstrip("/"))
        console.print("\n[dim]Testing API connectivity…[/dim]")
        try:
            with DNSFilterClient(api_key=api_key_val, base_url=base, timeout=10.0) as client:
                client.get("/v1/organizations")
            console.print("[green]✓[/green] API reachable and credentials valid.")
        except APIError as exc:
            if exc.status_code == 401:
                console.print(f"[red]✗[/red] Authentication failed (401). Check your API key.")
            elif exc.status_code == 403:
                console.print(f"[red]✗[/red] Forbidden (403). Key may lack required permissions.")
            else:
                console.print(f"[red]✗[/red] API error {exc.status_code}: {exc.message}")
            all_ok = False
        except Exception as exc:
            console.print(f"[red]✗[/red] Could not reach API: {exc}")
            all_ok = False
    else:
        console.print("\n[dim]Skipping connectivity check (no API key).[/dim]")

    console.print()
    if all_ok:
        console.print("[bold green]All checks passed.[/bold green]")
    else:
        console.print("[bold red]Some checks failed.[/bold red]")
        raise typer.Exit(1)


# ---------------------------------------------------------------------------
# lookupdomain — human-readable domain classification
# ---------------------------------------------------------------------------


@app.command("lookupdomain")
def lookupdomain(
    domain: str = typer.Argument(
        ...,
        help="Domain name to look up (e.g. example.com). "
             "Pass a comma-separated list to look up multiple domains at once.",
    ),
    api_key: Optional[str] = typer.Option(
        None, "--api-key", envvar="DNSF_API_KEY",
        help="Override stored API key for this call.",
    ),
    raw: bool = typer.Option(False, "--raw", "-r", help="Print raw JSON response."),
    profile: Optional[str] = typer.Option(None, "--profile", "-p", envvar="DNSF_PROFILE", help="Named credential profile to use."),
) -> None:
    """Look up one or more domains and display their category names in plain English.

    Pass a single domain or a comma-separated list.  Category IDs are
    automatically resolved to human-readable names.

    Examples:

      python dnsfcli.py lookupdomain google.com

      python dnsfcli.py lookupdomain google.com,facebook.com,malware.wicar.org

      python dnsfcli.py lookupdomain malware.example.com --raw
    """
    import re as _re

    effective_profile = profile or get_active_profile()
    resolved_key = api_key or get_api_key(profile=effective_profile)
    if not resolved_key:
        print_error(
            "No API key found. Set one with [bold]dnsfcli auth setup[/bold] "
            "or pass [bold]--api-key[/bold]."
        )
        raise typer.Exit(1)
    if api_key and _api_key_flag_on_cli():
        print_warning(
            "API key passed via [bold]--api-key[/bold]. "
            "It may be exposed in: shell history (~/.zsh_history, ~/.bash_history), "
            "process listings (ps aux), and CI/CD logs. "
            "Prefer [bold]dnsfcli auth setup[/bold] or the "
            "[bold]DNSF_API_KEY[/bold] environment variable."
        )

    base_url = _re.sub(
        r"/v\d+/*$",
        "",
        (get_base_url(profile=effective_profile) or "https://api.dnsfilter.com").rstrip("/"),
    )
    if not base_url.startswith("https://"):
        print_error(f"Base URL must use HTTPS. Got: {base_url!r}. Update it with [bold]dnsfcli auth setup --base-url[/bold].")
        raise typer.Exit(1)
    if base_url != "https://api.dnsfilter.com":
        print_warning(f"Non-default base URL in use: {base_url}")

    # Support comma-separated list for bulk lookup
    domains_list = [d.strip() for d in domain.split(",") if d.strip()]
    is_bulk = len(domains_list) > 1

    try:
        with DNSFilterClient(api_key=resolved_key, base_url=base_url) as client:

            # ── Step 1: classify the domain(s) ───────────────────────────────
            try:
                if is_bulk:
                    lookup = client.get("/v1/domains/bulk_lookup", params={"fqdns": domain})
                else:
                    lookup = client.get("/v1/domains/user_lookup", params={"fqdn": domains_list[0]})
            except APIError as exc:
                print_error(f"Domain lookup failed: {exc}")
                raise typer.Exit(1)

            if raw:
                console.print_json(json.dumps(lookup))
                return

            # Normalise to a dict of {domain_name: domain_obj}
            raw_data = (lookup or {}).get("data") if isinstance(lookup, dict) else None
            if not raw_data:
                console.print(f"[yellow]No classification data found for[/yellow] [bold]{domain}[/bold]")
                return

            # Bulk: data is {"google.com": {...}, "facebook.com": {...}}
            # Single: data is {"id": ..., "type": "domains", ...}
            if is_bulk and isinstance(raw_data, dict) and not raw_data.get("type"):
                domain_map = raw_data  # already keyed by domain name
            else:
                domain_map = {domains_list[0]: raw_data}  # wrap single result

            # ── Step 2: collect all category IDs across all domains ───────────
            all_cat_ids: set[str] = set()
            all_app_ids: set[str] = set()
            for d_obj in domain_map.values():
                if not isinstance(d_obj, dict):
                    continue
                rels = d_obj.get("relationships", {})
                all_cat_ids.update(
                    str(c["id"]) for c in rels.get("categories", {}).get("data", []) if c.get("id")
                )
                all_app_ids.update(
                    str(a["id"]) for a in rels.get("applications", {}).get("data", []) if a.get("id")
                )

            # Variables kept for single-domain backward compat (used below)
            attrs = list(domain_map.values())[0].get("attributes", {}) if len(domain_map) == 1 else {}
            cat_ids = list(all_cat_ids)
            app_ids = list(all_app_ids)

            # ── Step 2: resolve category IDs → names ─────────────────────────
            cat_names: list[str] = []
            # Defined up front: the bulk-mode renderer below references these
            # maps even when the lookup is skipped or fails with APIError.
            id_to_name: dict[str, str] = {}
            app_id_to_name: dict[str, str] = {}
            if cat_ids:
                try:
                    cats_raw = client.get("/v1/categories/all")
                    # Response may be a list or {"data": [...]}
                    cats_list = (
                        cats_raw
                        if isinstance(cats_raw, list)
                        else cats_raw.get("data", [])
                        if isinstance(cats_raw, dict)
                        else []
                    )
                    for c in cats_list:
                        if isinstance(c, dict):
                            cid  = str(c.get("id", ""))
                            name = (
                                c.get("attributes", {}).get("name")
                                or c.get("name")
                                or f"Category {cid}"
                            )
                            if cid:
                                id_to_name[cid] = name
                    cat_names = [id_to_name.get(cid, f"Category {cid}") for cid in cat_ids]
                except APIError:
                    cat_names = [f"Category {cid}" for cid in cat_ids]

            # ── Step 3: resolve application IDs → names ──────────────────────
            app_names: list[str] = []
            if app_ids:
                try:
                    apps_raw = client.get("/v1/applications/all")
                    apps_list = (
                        apps_raw
                        if isinstance(apps_raw, list)
                        else apps_raw.get("data", [])
                        if isinstance(apps_raw, dict)
                        else []
                    )
                    for a in apps_list:
                        if isinstance(a, dict):
                            aid  = str(a.get("id", ""))
                            name = (
                                a.get("attributes", {}).get("name")
                                or a.get("name")
                                or f"Application {aid}"
                            )
                            if aid:
                                app_id_to_name[aid] = name
                    app_names = [app_id_to_name.get(aid, f"Application {aid}") for aid in app_ids]
                except APIError:
                    app_names = [f"Application {aid}" for aid in app_ids]

            # ── Step 4: render human-readable output ──────────────────────────
            from rich.panel import Panel

            if is_bulk:
                # Multi-domain: one row per domain in a table
                tbl = Table(
                    show_header=True, header_style="bold cyan",
                    padding=(0, 2), expand=False,
                )
                tbl.add_column("Domain",       no_wrap=True)
                tbl.add_column("Categories",   overflow="fold")
                tbl.add_column("Applications", overflow="fold")

                for d_name, d_obj in domain_map.items():
                    if not isinstance(d_obj, dict):
                        continue
                    d_rels = d_obj.get("relationships", {})
                    d_cat_ids = [
                        str(c["id"])
                        for c in d_rels.get("categories", {}).get("data", [])
                        if c.get("id")
                    ]
                    d_app_ids = [
                        str(a["id"])
                        for a in d_rels.get("applications", {}).get("data", [])
                        if a.get("id")
                    ]
                    d_cat_names = [id_to_name.get(cid, f"Category {cid}") for cid in d_cat_ids]
                    d_app_names = [app_id_to_name.get(aid, f"Application {aid}") for aid in d_app_ids]
                    tbl.add_row(
                        d_name,
                        ", ".join(d_cat_names) if d_cat_names else "[dim]None[/dim]",
                        ", ".join(d_app_names) if d_app_names else "[dim]None[/dim]",
                    )

                n = len(domain_map)
                console.print(Panel(
                    tbl,
                    title=f"[bold]Domain Lookup: {n} domain{'s' if n != 1 else ''}[/bold]",
                    expand=False,
                ))
            else:
                # Single domain: key/value panel
                tbl = Table(show_header=False, box=None, padding=(0, 2), expand=False)
                tbl.add_column("Field", style="bold cyan", no_wrap=True, min_width=16)
                tbl.add_column("Value", overflow="fold")

                tbl.add_row("Domain",       attrs.get("name", domains_list[0]))
                tbl.add_row("Host",         attrs.get("host", domains_list[0]))
                tbl.add_row(
                    "Categories",
                    ", ".join(cat_names) if cat_names else "[dim]None[/dim]",
                )
                tbl.add_row(
                    "Applications",
                    ", ".join(app_names) if app_names else "[dim]None[/dim]",
                )

                console.print(Panel(
                    tbl,
                    title=f"[bold]Domain Lookup: {domains_list[0]}[/bold]",
                    expand=False,
                ))

    except SystemExit:
        raise
    except Exception as exc:
        print_error(f"Unexpected error: {exc}")
        sys.exit(1)


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
    _run_api_call(ctx, endpoint, function, raw=raw, verbose=verbose, api_key=api_key, org_id=org_id)


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

def _confirm_destructive(description: str, skip: bool) -> None:
    """Prompt the user to confirm a destructive operation; exits if they decline."""
    if skip:
        return
    console.print(f"\n[bold yellow]Warning:[/bold yellow] {description}")
    console.print("[yellow]This action cannot be undone.[/yellow]")
    try:
        typer.confirm("Proceed?", abort=True)
    except typer.Abort:
        console.print("[dim]Aborted.[/dim]")
        sys.exit(1)


def _confirm_batch(description: str, skip: bool) -> None:
    """Prompt the user to confirm a multi-row write batch; exits if they decline."""
    if skip:
        return
    console.print(f"\n{description}")
    try:
        typer.confirm("Proceed?", abort=True)
    except typer.Abort:
        console.print("[dim]Aborted.[/dim]")
        sys.exit(1)


def _preview_confirm_batch(
    rows: list[dict[str, Any]],
    operation: Any,
    endpoint: str,
    function: str,
    skip: bool,
) -> None:
    """Show a preview table of the first few batch rows then ask for confirmation."""
    if skip:
        return
    n = len(rows)
    PREVIEW_MAX = 5
    if rows:
        all_keys = list(rows[0].keys())[:8]
        tbl = Table(
            title=f"Batch preview — {n} row(s)  →  {operation.method} {operation.path_template}",
            header_style="bold cyan",
            show_header=True,
        )
        for k in all_keys:
            tbl.add_column(str(k), overflow="fold", max_width=28)
        for row in rows[:PREVIEW_MAX]:
            tbl.add_row(*[str(row.get(k, ""))[:28] for k in all_keys])
        if n > PREVIEW_MAX:
            tbl.add_row(*["[dim]…[/dim]" for _ in all_keys])
        console.print(tbl)
    console.print(
        f"\n[bold yellow]About to execute {n} API call(s)[/bold yellow] "
        f"([dim]{endpoint} {function}[/dim])."
    )
    try:
        typer.confirm("Proceed?", abort=True)
    except typer.Abort:
        console.print("[dim]Aborted.[/dim]")
        sys.exit(1)


def _apply_exclude(items: list[Any], fields: list[str]) -> list[Any]:
    """Remove *fields* from every dict item (other items are passed through unchanged)."""
    field_set = set(fields)
    result = []
    for item in items:
        if isinstance(item, dict):
            result.append({k: v for k, v in item.items() if k not in field_set})
        else:
            result.append(item)
    return result


def _apply_renames(items: list[Any], renames: list[str]) -> list[Any]:
    """Rename fields in each item.  Each rename expr is 'FROM=TO'."""
    parsed: list[tuple[str, str]] = []
    for expr in renames:
        if "=" in expr:
            src, _, dst = expr.partition("=")
            src = src.strip()
            dst = dst.strip()
            if src and dst:
                parsed.append((src, dst))
    if not parsed:
        return items
    result = []
    for item in items:
        if isinstance(item, dict):
            new_item = dict(item)
            for src, dst in parsed:
                if src in new_item:
                    new_item[dst] = new_item.pop(src)
            result.append(new_item)
        else:
            result.append(item)
    return result


def _apply_pick(items: list[Any], field: str) -> list[str]:
    """Extract *field* (supports dot-notation) from each item; return one string per item."""
    parts = field.split(".")
    out: list[str] = []
    for item in items:
        obj: Any = item
        for part in parts:
            if isinstance(obj, dict):
                obj = obj.get(part)
            else:
                obj = None
                break
        if obj is not None:
            out.append(str(obj))
    return out


def _apply_sum(items: list[Any], field: str) -> float:
    """Sum numeric values of *field* across all dict items."""
    total = 0.0
    for item in items:
        if isinstance(item, dict):
            v = item.get(field)
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                total += v
    return total


def _apply_avg(items: list[Any], field: str) -> float | None:
    """Average numeric values of *field* across all dict items; None if no values."""
    total = 0.0
    count = 0
    for item in items:
        if isinstance(item, dict):
            v = item.get(field)
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                total += v
                count += 1
    return total / count if count else None


def _apply_min(items: list[Any], field: str) -> float | None:
    """Minimum numeric value of *field* across all dict items; None if no values."""
    nums = [item.get(field) for item in items if isinstance(item, dict)]
    nums = [v for v in nums if isinstance(v, (int, float)) and not isinstance(v, bool)]
    return min(nums) if nums else None


def _apply_max(items: list[Any], field: str) -> float | None:
    """Maximum numeric value of *field* across all dict items; None if no values."""
    nums = [item.get(field) for item in items if isinstance(item, dict)]
    nums = [v for v in nums if isinstance(v, (int, float)) and not isinstance(v, bool)]
    return max(nums) if nums else None


def _apply_group_by(items: list[Any], field: str) -> list[dict[str, Any]]:
    """Return a count table: one row per distinct *field* value, sorted descending."""
    parts = field.split(".")
    counts: dict[str, int] = {}
    for item in items:
        obj: Any = item
        for part in parts:
            if isinstance(obj, dict):
                obj = obj.get(part)
            else:
                obj = None
                break
        key = str(obj) if obj is not None else "(none)"
        counts[key] = counts.get(key, 0) + 1
    return [
        {field: k, "count": v}
        for k, v in sorted(counts.items(), key=lambda x: -x[1])
    ]


def _apply_select(items: list[Any], fields: list[str]) -> list[Any]:
    """Keep only *fields* in each dict item (other items are passed through unchanged)."""
    field_set = set(fields)
    result = []
    for item in items:
        if isinstance(item, dict):
            result.append({k: v for k, v in item.items() if k in field_set})
        else:
            result.append(item)
    return result


def _apply_null_as(obj: Any, replacement: str) -> Any:
    """Recursively replace None values with *replacement* string."""
    if obj is None:
        return replacement
    if isinstance(obj, list):
        return [_apply_null_as(item, replacement) for item in obj]
    if isinstance(obj, dict):
        return {k: _apply_null_as(v, replacement) for k, v in obj.items()}
    return obj


def _apply_count_by(items: list[Any], field: str) -> list[dict[str, Any]]:
    """Return a frequency table with a pct column, sorted descending by count."""
    parts = field.split(".")
    counts: dict[str, int] = {}
    for item in items:
        obj: Any = item
        for part in parts:
            if isinstance(obj, dict):
                obj = obj.get(part)
            else:
                obj = None
                break
        key = str(obj) if obj is not None else "(none)"
        counts[key] = counts.get(key, 0) + 1
    total = sum(counts.values()) or 1
    return [
        {field: k, "count": v, "pct": f"{v / total * 100:.1f}%"}
        for k, v in sorted(counts.items(), key=lambda x: -x[1])
    ]


def _apply_map_fields(items: list[Any], map_specs: list[str]) -> list[Any]:
    """Apply named transformations to field values.

    Each spec has the form ``FIELD=TRANSFORM`` where TRANSFORM is one of:
    ``upper``, ``lower``, ``strip``, ``title``, ``truncate:N``.
    Specs for unknown fields are silently ignored.
    """
    transforms: list[tuple[str, str]] = []
    for spec in map_specs:
        if "=" not in spec:
            continue
        field, transform = spec.split("=", 1)
        transforms.append((field.strip(), transform.strip()))

    def _apply_one(value: Any, transform: str) -> Any:
        if not isinstance(value, str):
            value = str(value) if value is not None else value
        if value is None:
            return value
        t = transform.lower()
        if t == "upper":
            return value.upper()
        if t == "lower":
            return value.lower()
        if t == "strip":
            return value.strip()
        if t == "title":
            return value.title()
        if t.startswith("truncate:"):
            try:
                n = int(t[9:])
                return value[:n]
            except ValueError:
                return value
        return value

    result = []
    for item in items:
        if isinstance(item, dict):
            new_item = dict(item)
            for field, transform in transforms:
                if field in new_item:
                    new_item[field] = _apply_one(new_item[field], transform)
            result.append(new_item)
        else:
            result.append(item)
    return result


def _apply_flatten(items: list[Any], separator: str = ".") -> list[Any]:
    """Flatten nested dict objects to dot-notation keys."""
    def _flat(obj: dict[str, Any], prefix: str = "") -> dict[str, Any]:
        result: dict[str, Any] = {}
        for k, v in obj.items():
            key = f"{prefix}{separator}{k}" if prefix else k
            if isinstance(v, dict) and v:
                result.update(_flat(v, key))
            else:
                result[key] = v
        return result
    return [_flat(item) if isinstance(item, dict) else item for item in items]


class _WatchUntilSatisfied(Exception):
    """Raised inside _run_api_call to signal that --watch-until condition is met."""


def _apply_jq(result: Any, expr: str) -> Any:
    """Extract a value via a dot-separated path (e.g. 'data.0.attributes.name')."""
    parts = expr.split(".")
    current = result
    for part in parts:
        if current is None:
            return None
        if isinstance(current, list):
            try:
                current = current[int(part)]
            except (ValueError, IndexError):
                print_warning(f"--jq: index '{part}' out of range or not an integer")
                return result
        elif isinstance(current, dict):
            if part not in current:
                print_warning(f"--jq: key '{part}' not found in result")
                return result
            current = current[part]
        else:
            print_warning(f"--jq: cannot traverse '{part}' on a {type(current).__name__}")
            return result
    return current


def _show_watch_diff(old_data: Any, new_data: Any) -> None:
    """Print a compact diff summary between two watch-loop iterations."""
    import json as _json

    def _to_set(d: Any) -> set[str]:
        items = d if isinstance(d, list) else ([d] if d is not None else [])
        return {_json.dumps(item, sort_keys=True, default=str) for item in items}

    old_set = _to_set(old_data)
    new_set = _to_set(new_data)
    added = len(new_set - old_set)
    removed = len(old_set - new_set)
    if not added and not removed:
        console.print("[dim]  Δ (no changes)[/dim]")
    else:
        parts = []
        if added:
            parts.append(f"[green]+{added} added[/green]")
        if removed:
            parts.append(f"[red]-{removed} removed[/red]")
        console.print("  Δ " + "  ".join(parts))


def _compute_stats(items: list[Any], field: str) -> None:
    """Print min/max/mean/count for a numeric field across *items*."""
    values: list[float] = []
    for item in items:
        if isinstance(item, dict):
            v = item.get(field)
            try:
                values.append(float(v))  # type: ignore[arg-type]
            except (TypeError, ValueError):
                pass
    if not values:
        console.print(f"[dim]--stats {field!r}: no numeric values found[/dim]")
        return
    n = len(values)
    console.print(
        f"[dim]  stats({field}): n={n}  min={min(values):g}  max={max(values):g}"
        f"  mean={sum(values)/n:g}[/dim]"
    )


def _show_dry_run(
    method: str,
    base_url: str,
    path: str,
    query_params: dict[str, Any],
    json_body: dict[str, Any] | None,
) -> None:
    """Print the HTTP request that *would* be sent, then return (no actual call)."""
    import json as _json
    from rich.panel import Panel

    tbl = Table(show_header=False, box=None, padding=(0, 2), expand=False)
    tbl.add_column("Field", style="bold cyan", min_width=12, no_wrap=True)
    tbl.add_column("Value", overflow="fold")

    tbl.add_row("Method", f"[bold]{method}[/bold]")
    tbl.add_row("URL",    f"{base_url}{path}")
    if query_params:
        tbl.add_row("Query",  str(query_params))
    if json_body:
        tbl.add_row("Body",   _json.dumps(json_body, indent=2, default=str))

    console.print(Panel(tbl, title="[bold]Dry Run — no request sent[/bold]", expand=False))
    console.print("\n[dim]Remove [bold]--dry-run[/bold] to execute.[/dim]")


# ---------------------------------------------------------------------------
# The workhorse: build and fire the API request
# ---------------------------------------------------------------------------


_ROW_CONTEXT_FIELDS = ("name", "id", "email", "address", "fqdn", "domain")


def _is_auth_error(err: str | None) -> bool:
    return bool(err and ("authentication failed" in err or "authorization denied" in err))


def _row_context(row: dict[str, Any]) -> str:
    """Return a short '[field=value, ...]' string for the most identifying fields of a row."""
    parts = [f"{k}={row[k]!r}" for k in _ROW_CONTEXT_FIELDS if k in row]
    return f" [{', '.join(parts[:2])}]" if parts else ""


def _execute_csv_rows(
    rows: list[dict[str, Any]],
    operation: Any,
    endpoint: str,
    function: str,
    client: Any,
    *,
    verbose: bool,
    csv_output: str | None,
    org_id: str | None = None,
    columns: list[str] | None = None,
    on_error: str = "continue",
    concurrency: int = 1,
    csv_delimiter: str = ",",
    retry: int = 0,
    errors_csv: str | None = None,
    upsert: bool = False,
    max_errors: int | None = None,
    confirm_each: bool = False,
    validate_only: bool = False,
    no_progress: bool = False,
    batch_delay: int | None = None,
    diff_mode: bool = False,
    batch_report_path: str | None = None,
) -> None:
    """Execute one API call per CSV row and report per-row results."""
    import threading
    import time as _time
    from . import output as _out_mod
    from rich.progress import Progress, SpinnerColumn, BarColumn, MofNCompleteColumn, TextColumn

    n = len(rows)
    _use_bar = not verbose and not _out_mod._quiet and not no_progress

    # --validate-only: check required params without making API calls
    if validate_only:
        required = {p.name for p in operation.params if p.required}
        errors_found = 0
        for i, row_params in enumerate(rows, start=1):
            missing = required - set(row_params.keys())
            if missing:
                err_console.print(f"  Row {i}{_row_context(row_params)}: missing required field(s): {', '.join(sorted(missing))}")
                errors_found += 1
        if errors_found:
            console.print(f"[bold red]Validation failed:[/bold red] {errors_found} row(s) have errors.")
            sys.exit(1)
        console.print(f"[bold green]Validation passed:[/bold green] {n} row(s) look OK.")
        return

    if verbose:
        console.print(f"\nProcessing {n} row{'s' if n != 1 else ''} from CSV...\n")

    known_kinds: dict[str, str] = {p.name: p.kind for p in operation.params}

    def _execute_row(i: int, row_params: dict[str, Any]) -> tuple[bool, Any, str | None]:
        """Execute one row. Returns (ok, result_or_None, error_str_or_None)."""
        # CIDR expansion
        if (endpoint == "ip-addresses" and function == "create"
                and "/" in str(row_params.get("address", ""))):
            cidr = str(row_params["address"])
            body_base = {k: v for k, v in row_params.items() if k != "address"}
            if not _use_bar:
                console.print(f"\n  Row {i}: expanding CIDR [bold]{cidr}[/bold]")
            try:
                _create_ips_from_cidr(cidr, body_base, client, verbose=verbose, csv_output=csv_output)
                return True, None, None
            except SystemExit:
                return False, None, "CIDR expansion failed"

        try:
            path, remaining = _build_path(operation.path_template, dict(row_params), raise_on_missing=True)
        except ValueError as exc:
            return False, None, str(exc)

        method = operation.method
        query_params: dict[str, Any] = {}
        body_params: dict[str, Any] = {}
        for key, val in remaining.items():
            kind = known_kinds.get(key)
            if kind == "query" or (kind is None and method in ("GET", "DELETE")):
                query_params[key] = val
            else:
                body_params[key] = val

        json_body: dict[str, Any] | None = None
        if body_params or operation.body_key:
            if operation.body_key:
                top_names = {p.name for p in operation.params if p.top_level}
                top = {k: v for k, v in body_params.items() if k in top_names}
                nested = {k: v for k, v in body_params.items() if k not in top_names}
                json_body = {**top, operation.body_key: nested}
            else:
                json_body = body_params

        if verbose:
            print_info(f"Row {i}: {method} {path}")
            if json_body:
                print_info(f"  Body: {json_body}")

        # --diff-mode: fetch current state and show field changes before PATCH/PUT
        if diff_mode and method in ("PATCH", "PUT") and json_body:
            try:
                _current = client.get(path)
                if isinstance(_current, dict):
                    _current_data = _current
                    for _dk in ("data", "results", "items", "records"):
                        if _dk in _current and isinstance(_current[_dk], dict):
                            _current_data = _current[_dk]
                            break
                    _flat_body = json_body
                    if operation.body_key and operation.body_key in json_body:
                        _flat_body = {**{k: v for k, v in json_body.items() if k != operation.body_key}, **json_body[operation.body_key]}
                    _changed = {k: (_current_data.get(k), v) for k, v in _flat_body.items() if _current_data.get(k) != v}
                    if _changed:
                        from rich.table import Table as _DiffTable
                        _dt = _DiffTable(title=f"Row {i} changes", show_header=True, header_style="bold cyan")
                        _dt.add_column("Field")
                        _dt.add_column("Before")
                        _dt.add_column("After")
                        for _field, (_old, _new) in _changed.items():
                            _dt.add_row(_field, str(_old), f"[bold]{_new}[/bold]")
                        console.print(_dt)
                    else:
                        console.print(f"  [dim]Row {i}: no changes detected (diff-mode)[/dim]")
            except Exception:
                pass

        _attempts = retry + 1
        _last_exc: APIError | None = None
        for _attempt in range(_attempts):
            try:
                _row_method = method
                _row_path = path
                result = client.request(method, path, params=query_params or None, json=json_body)
                log_event(endpoint, function, _row_method, _row_path, 200, org_id)
                rid: Any = None
                if isinstance(result, dict):
                    rid = result.get("id")
                    if rid is None:
                        for v in result.values():
                            if isinstance(v, dict) and "id" in v:
                                rid = v["id"]
                                break
                id_str = f" (id: {rid})" if rid is not None else ""
                if not _use_bar:
                    console.print(f"  Row {i}: [green]✓[/green]{id_str}")
                return True, result, None
            except APIError as exc:
                # --upsert: 409 on POST → retry as PATCH on the conflicting resource
                if upsert and method == "POST" and exc.status_code == 409:
                    _upsert_id: Any = None
                    if isinstance(exc.body, dict):
                        _ub = exc.body
                        _upsert_id = (
                            _ub.get("id")
                            or (_ub.get("data") or {}).get("id")
                            or (_unwrap(_ub) or {}).get("id") if isinstance(_unwrap(_ub), dict) else None
                        )
                    if _upsert_id is None:
                        _last_exc = exc
                        break
                    _row_path = f"{path}/{_upsert_id}"
                    try:
                        result = client.request("PATCH", _row_path, json=json_body)
                        log_event(endpoint, function, "PATCH", _row_path, 200, org_id)
                        rid = result.get("id") if isinstance(result, dict) else None
                        id_str = f" (id: {rid})" if rid is not None else ""
                        if not _use_bar:
                            console.print(f"  Row {i}: [green]✓[/green] (upserted){id_str}")
                        return True, result, None
                    except APIError as _patch_exc:
                        _last_exc = _patch_exc
                        break
                _last_exc = exc
                if exc.status_code >= 500 and _attempt < _attempts - 1:
                    _wait = 2 ** _attempt
                    if verbose:
                        print_info(f"  Row {i}: 5xx ({exc.status_code}), retry {_attempt + 1}/{retry} in {_wait}s")
                    _time.sleep(_wait)
                else:
                    break
        assert _last_exc is not None
        log_event(endpoint, function, method, path, _last_exc.status_code, org_id, error=str(_last_exc))
        _err_str = str(_last_exc)
        if _last_exc.status_code == 401:
            _err_str += " — authentication failed (API key invalid or expired; run: dnsfcli auth setup)"
        elif _last_exc.status_code == 403:
            _err_str += " — authorization denied (insufficient permissions for this org/operation)"
        return False, None, _err_str

    succeeded = 0
    failed = 0
    results: list[Any] = []
    failed_row_inputs: list[dict[str, Any]] = []
    failed_reasons: list[str] = []
    _report_rows: list[dict[str, Any]] = [] if batch_report_path else []
    stop_flag = threading.Event()

    _prog_ctx: Any = None
    _task_id: Any = None
    if _use_bar:
        _prog_ctx = Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            MofNCompleteColumn(),
            TextColumn("[dim]{task.fields[ok]}✓  {task.fields[err]}✗[/dim]"),
            transient=True,
            console=err_console,
        )
        _task_id = _prog_ctx.add_task("Batch", total=n, ok=0, err=0)
        _prog_ctx.__enter__()

    try:
        if concurrency > 1:
            from concurrent.futures import ThreadPoolExecutor, as_completed
            futures_map: dict[Any, tuple[int, dict[str, Any]]] = {}
            with ThreadPoolExecutor(max_workers=concurrency) as pool:
                for i, row_params in enumerate(rows, start=1):
                    if stop_flag.is_set():
                        break
                    f = pool.submit(_execute_row, i, row_params)
                    futures_map[f] = (i, row_params)
                for f in as_completed(futures_map):
                    ok, result, err = f.result()
                    row_i, row_p = futures_map[f]
                    if batch_report_path:
                        _report_rows.append({"row": row_i, "ok": ok, "error": err, "input": row_p})
                    if ok:
                        succeeded += 1
                        if result is not None:
                            results.append(result)
                    else:
                        failed += 1
                        failed_row_inputs.append(row_p)
                        failed_reasons.append(err or "unknown error")
                        err_console.print(f"  Row {row_i}{_row_context(row_p)}: [red]✗[/red] {err}")
                        if _is_auth_error(err):
                            err_console.print(f"[bold red]Auth error — stopping batch (further rows will fail too).[/bold red]")
                            stop_flag.set()
                        elif on_error == "stop" or (max_errors is not None and failed >= max_errors):
                            stop_flag.set()
                    if _prog_ctx and _task_id is not None:
                        _prog_ctx.update(_task_id, advance=1, ok=succeeded, err=failed)
        else:
            for i, row_params in enumerate(rows, start=1):
                if confirm_each:
                    ctx_str = _row_context(row_params)
                    console.print(f"[dim]Row {i}/{n}{ctx_str}[/dim]")
                    if not typer.confirm(f"  Process row {i}?", default=True):
                        console.print(f"  [dim]Row {i}: skipped.[/dim]")
                        continue
                ok, result, err = _execute_row(i, row_params)
                if batch_report_path:
                    _report_rows.append({"row": i, "ok": ok, "error": err, "input": row_params})
                if ok:
                    succeeded += 1
                    if result is not None:
                        results.append(result)
                else:
                    failed += 1
                    failed_row_inputs.append(row_params)
                    failed_reasons.append(err or "unknown error")
                    _err_target = err_console if _use_bar else console
                    _err_target.print(f"  Row {i}{_row_context(row_params)}: [red]✗[/red] {err}")
                    if _is_auth_error(err):
                        _err_target.print("[bold red]Auth error — stopping batch (further rows will fail too).[/bold red]")
                        break
                    _stop_now = on_error == "stop" or (max_errors is not None and failed >= max_errors)
                    if _stop_now:
                        if not _use_bar:
                            if max_errors is not None and failed >= max_errors:
                                console.print(f"[dim]Stopping after {failed} error(s) (--max-errors {max_errors}).[/dim]")
                            else:
                                console.print("[dim]Stopping on first error (--on-error stop).[/dim]")
                        break
                if _prog_ctx and _task_id is not None:
                    _prog_ctx.update(_task_id, advance=1, ok=succeeded, err=failed)
                if batch_delay and i < n:
                    _time.sleep(batch_delay / 1000.0)
    finally:
        if _prog_ctx:
            _prog_ctx.__exit__(None, None, None)

    console.print()
    if failed == 0:
        console.print(f"[bold green]Done:[/bold green] {succeeded}/{n} row(s) succeeded")
    else:
        console.print(
            f"[bold yellow]Done:[/bold yellow] "
            f"{succeeded} succeeded, {failed} failed (out of {n})"
        )
        if failed_reasons:
            _reason_counts: dict[str, int] = {}
            for _r in failed_reasons:
                # Key by the HTTP status prefix if present (e.g. "HTTP 422: ...")
                import re as _re_reason
                _m = _re_reason.match(r"HTTP (\d+)", _r)
                _key = f"HTTP {_m.group(1)}" if _m else _r[:60]
                _reason_counts[_key] = _reason_counts.get(_key, 0) + 1
            _breakdown = ", ".join(f"{cnt}× {k}" for k, cnt in sorted(_reason_counts.items(), key=lambda x: -x[1]))
            console.print(f"[dim]Error breakdown: {_breakdown}[/dim]")

    if csv_output and results:
        written = write_csv(results, csv_output, columns=columns, delimiter=csv_delimiter)
        print_success(f"Wrote {written} result row(s) to {csv_output}")

    if errors_csv and failed_row_inputs:
        written_err = write_csv(failed_row_inputs, errors_csv, delimiter=csv_delimiter)
        print_success(f"Wrote {written_err} failed input row(s) to {errors_csv}")
        console.print(f"[dim]Retry failed rows with: --retry-errors-csv {errors_csv}[/dim]")

    if batch_report_path and _report_rows:
        import json as _json_br
        import datetime as _dt_br
        _br_doc = {
            "timestamp": _dt_br.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
            "total": n, "succeeded": succeeded, "failed": failed,
            "rows": _report_rows,
        }
        try:
            import pathlib as _pl_br
            _pl_br.Path(batch_report_path).write_text(_json_br.dumps(_br_doc, indent=2, default=str), encoding="utf-8")
            print_success(f"Wrote batch report to {batch_report_path}")
        except OSError as _br_exc:
            print_warning(f"--batch-report: could not write {batch_report_path}: {_br_exc}")

    if failed > 0 and on_error != "report":
        sys.exit(1)


def _create_ips_from_cidr(
    cidr: str,
    body_base: dict[str, Any],
    client: Any,
    verbose: bool,
    csv_output: str | None,
    columns: list[str] | None = None,
) -> None:
    """Expand a CIDR block and register all host addresses against a network.

    Strategy (fewest possible API calls):
      1. Attempt a single PATCH to /v1/networks/{network_id} passing all host
         addresses in ``ip_addresses_attributes``.  This handles an entire /24
         in one round-trip.
      2. If the batch fails because some IPs already exist elsewhere in
         DNSFilter, parse the error response to identify which indices failed,
         strip those addresses, and retry the remainder in a second batch call.
         Retries continue until either the batch succeeds or no retries remain.
      3. If the network_id is missing, or the batch keeps failing for a
         non-duplicate reason, fall back to individual POST calls so partial
         progress is captured.

    Network address (x.x.x.0) and broadcast (x.x.x.255) are excluded for
    prefix <= /30 via ``ip_network.hosts()``.  /31 and /32 include every
    address per RFC 3021.

    Hard limit: /16 (65,536 addresses).
    """
    import ipaddress

    try:
        network = ipaddress.ip_network(cidr, strict=False)
    except ValueError as exc:
        print_error(f"Invalid CIDR notation '{cidr}': {exc}")
        sys.exit(1)

    hosts: list[Any] = list(network) if network.prefixlen >= 31 else list(network.hosts())
    total = len(hosts)

    if total > 65_536:
        print_error(
            f"{cidr} contains {total:,} addresses. "
            "Maximum supported is 65,536 (/16). Please split into smaller blocks."
        )
        sys.exit(1)

    console.print(
        f"Expanding [bold]{cidr}[/bold] → "
        f"[bold]{total:,}[/bold] host address{'es' if total != 1 else ''}."
    )

    network_id = body_base.get("network_id")

    # ── Batch path via networks update ────────────────────────────────────────
    if network_id:
        ip_attrs = [{"address": str(h)} for h in hosts]
        n_pending = len(ip_attrs)

        if verbose:
            print_info(f"Batch: PATCH /v1/networks/{network_id} with {n_pending} IP(s)")

        for _once in [1]:  # single-iteration loop; break exits to individual-call fallback

            try:
                result = client.patch(
                    f"/v1/networks/{network_id}",
                    json={"network": {"ip_addresses_attributes": ip_attrs}},
                )
                # Success — all IPs registered in one call
                console.print(
                    f"\n[bold green]Done:[/bold green] "
                    f"{n_pending} IP address{'es' if n_pending != 1 else ''} "
                    f"registered in [bold]1 API call[/bold]."
                )
                if csv_output and isinstance(result, dict):
                    write_csv(result, csv_output, columns=columns)
                    print_success(f"Wrote result to {csv_output}")
                return

            except APIError as exc:
                # The networks update endpoint returns 422 with an unindexed error
                # format when duplicates exist — it reports how many IPs failed but
                # not which ones.  We can't selectively retry, so fall through to
                # individual calls which give clear per-IP success/failure feedback.
                is_duplicate = (
                    isinstance(exc.body, dict)
                    and any(
                        "already" in " ".join(str(v) for v in (val if isinstance(val, list) else [val]))
                        for val in exc.body.values()
                    )
                )
                if is_duplicate:
                    dup_count = sum(
                        1 for val in exc.body.values()
                        if isinstance(val, list) and val and "already" in str(val[0])
                    )
                    console.print(
                        f"\n[yellow]{dup_count} IP address{'es' if dup_count != 1 else ''} in "
                        f"this block already exist in DNSFilter.[/yellow] "
                        "Falling back to individual calls to identify which ones...\n"
                    )
                else:
                    console.print(
                        f"[yellow]Batch call failed: {exc}.[/yellow] "
                        "Falling back to individual calls.\n"
                    )
                break  # exit retry loop → fall through to individual calls

        # fall through to individual calls if the batch did not return

    # ── Individual-call fallback ───────────────────────────────────────────────
    console.print(
        f"[dim]Using individual calls "
        f"({'network_id not provided' if not network_id else 'batch retries exhausted'}).[/dim]\n"
    )

    succeeded = 0
    failed    = 0
    ind_results: list[Any] = []

    for i, host_ip in enumerate(hosts, start=1):
        ip_str = str(host_ip)
        body   = {**body_base, "address": ip_str}

        if verbose:
            print_info(f"[{i}/{total}] POST /v1/ip_addresses  {ip_str}")

        try:
            result = client.request("POST", "/v1/ip_addresses", json=body)
            succeeded += 1
            rid: Any = None
            if isinstance(result, dict):
                rid = result.get("id") or (result.get("data") or {}).get("id")
            id_str = f" [dim](id: {rid})[/dim]" if rid else ""
            console.print(f"  [{i}/{total}] [green]✓[/green] {ip_str}{id_str}")
            if result is not None:
                ind_results.append(result)
        except APIError as exc:
            failed += 1
            console.print(f"  [{i}/{total}] [red]✗[/red] {ip_str}: {exc}")

    console.print()
    if failed == 0:
        console.print(
            f"[bold green]Done:[/bold green] "
            f"{succeeded}/{total} IP address{'es' if total != 1 else ''} created."
        )
    else:
        console.print(
            f"[bold yellow]Done:[/bold yellow] "
            f"{succeeded} created, {failed} failed (out of {total})."
        )

    if csv_output and ind_results:
        n = write_csv(ind_results, csv_output, columns=columns)
        print_success(f"Wrote {n} result row(s) to {csv_output}")

    if failed > 0:
        sys.exit(1)


def _estimate_duration(n_calls: int) -> str:
    """Return a human-readable time estimate for *n_calls* API calls."""
    if n_calls == 0:
        return "< 1 second"
    if n_calls == 1:
        return "~1 second"
    if n_calls <= 5:
        return f"~{n_calls * 2} seconds"
    if n_calls <= 30:
        return f"~{n_calls * 1.5:.0f} seconds"
    # DNSFilter allows 2,000 req / 300 s ≈ 6.67 req/s sustained
    RATE = 6.67
    secs = n_calls / RATE
    if secs < 60:
        return f"~{secs:.0f} seconds"
    if secs < 3600:
        return f"~{secs / 60:.1f} minutes"
    return f"~{secs / 3600:.1f} hours"


def _show_plan(
    endpoint: str,
    function: str,
    operation: Any,
    params: dict[str, Any],
    csv_input: str | None,
) -> None:
    """Print a dry-run summary without touching the API, then exit cleanly."""
    import ipaddress as _ip
    from rich.panel import Panel

    method_verb = {
        "POST":   "create",
        "PATCH":  "update",
        "PUT":    "update",
        "DELETE": "delete",
    }.get(operation.method, operation.method)

    # ── Derive body params the same way _run_api_call would ──────────────────
    known_kinds: dict[str, str] = {p.name: p.kind for p in operation.params}
    body_params: dict[str, Any] = {
        k: v for k, v in params.items()
        if known_kinds.get(k) == "body"
        or (known_kinds.get(k) is None and operation.method not in ("GET", "DELETE"))
    }

    api_calls = 1
    total_records = 1
    notes: list[str] = []

    # Human-readable singular / plural noun for the resource
    _SINGULAR: dict[str, str] = {
        "agent-local-users":       "agent local user",
        "api-keys":                "API key",
        "application-categories":  "application category",
        "applications":            "application",
        "billing":                 "billing record",
        "block-pages":             "block page",
        "categories":              "category",
        "collections":             "collection",
        "current-user":            "user",
        "dictionary":              "entry",
        "domains":                 "domain",
        "enterprise-connections":  "enterprise connection",
        "invoices":                "invoice",
        "ip-addresses":            "IP address",
        "mac-addresses":           "MAC address",
        "metrics":                 "metric",
        "networks":                "network",
        "notes":                   "note",
        "organizations":           "organization",
        "policies":                "policy",
        "policy-ips":              "policy IP",
        "psa-integrations":        "PSA integration",
        "scheduled-policies":      "scheduled policy",
        "scheduled-reports":       "scheduled report",
        "traffic-reports":         "traffic report",
        "trials":                  "trial",
        "user-agent-bulk-deletes": "bulk delete job",
        "user-agent-bulk-updates": "bulk update job",
        "user-agent-cleanups":     "cleanup job",
        "user-agent-csv-exports":  "CSV export job",
        "user-agent-releases":     "agent release",
        "user-agents":             "agent",
        "users":                   "user",
        "v2-agent-local-users":    "agent local user",
        "v2-current-user":         "user",
        "v2-cyber-sight":          "Cyber Sight export",
        "v2-dictionary":           "entry",
        "v2-networks":             "network export",
        "v2-user-agents":          "agent",
    }
    record_noun = _SINGULAR.get(endpoint, endpoint.replace("-", " "))

    # ── CIDR expansion ────────────────────────────────────────────────────────
    address = str(body_params.get("address", ""))
    if "/" in address and endpoint == "ip-addresses" and function == "create":
        try:
            net   = _ip.ip_network(address, strict=False)
            hosts = len(list(net)) if net.prefixlen >= 31 else len(list(net.hosts()))
            api_calls     = 1
            total_records = hosts
            record_noun   = "IP address"
            net_id = params.get("network_id", "?")
            notes.append(
                f"{address} expands to {hosts:,} host addresses; "
                f"sent as 1 batch PATCH /v1/networks/{net_id}"
            )
        except ValueError as exc:
            notes.append(f"[red]Invalid CIDR: {exc}[/red]")

    # ── CSV input ─────────────────────────────────────────────────────────────
    elif csv_input:
        try:
            from .csv_io import read_csv_input, CsvValidationError
            rows = read_csv_input(csv_input, operation, params)
            n_rows = len(rows)

            if endpoint == "ip-addresses" and function == "create":
                # Each CIDR row becomes 1 batch PATCH call; plain IPs are 1 call each
                cidr_calls   = 0
                cidr_records = 0
                plain_calls  = 0

                for row in rows:
                    addr = str(row.get("address", ""))
                    if "/" in addr:
                        cidr_calls += 1
                        try:
                            net = _ip.ip_network(addr, strict=False)
                            cidr_records += (
                                len(list(net)) if net.prefixlen >= 31
                                else len(list(net.hosts()))
                            )
                        except ValueError:
                            cidr_records += 1
                    else:
                        plain_calls += 1

                api_calls     = cidr_calls + plain_calls
                total_records = cidr_records + plain_calls
                record_noun   = "IP address"

                if cidr_calls:
                    notes.append(
                        f"{cidr_calls} CIDR row{'s' if cidr_calls != 1 else ''} → "
                        f"{cidr_records:,} IP addresses "
                        f"({cidr_calls} batch call{'s' if cidr_calls != 1 else ''})"
                    )
                if plain_calls:
                    notes.append(
                        f"{plain_calls} plain IP row{'s' if plain_calls != 1 else ''} → "
                        f"{plain_calls} individual call{'s' if plain_calls != 1 else ''}"
                    )
            else:
                api_calls     = n_rows
                total_records = n_rows
                notes.append(
                    f"{n_rows} CSV row{'s' if n_rows != 1 else ''} → "
                    f"{n_rows} API call{'s' if n_rows != 1 else ''}"
                )

        except Exception as exc:
            notes.append(f"[yellow]Could not preview CSV: {exc}[/yellow]")

    # ── Plain single call ─────────────────────────────────────────────────────

    # ── Pluralise record noun ─────────────────────────────────────────────────
    def _pluralise(noun: str) -> str:
        if noun.endswith("y") and not noun.endswith("ay") and not noun.endswith("ey"):
            return noun[:-1] + "ies"       # policy → policies
        if noun[-1:] in ("s", "x", "z") or noun.endswith("ch") or noun.endswith("sh"):
            return noun + "es"             # address → addresses
        return noun + "s"                  # network → networks

    record_noun_pl = _pluralise(record_noun) if total_records != 1 else record_noun

    duration = _estimate_duration(api_calls)

    # ── Render ────────────────────────────────────────────────────────────────
    tbl = Table(show_header=False, box=None, padding=(0, 2), expand=False)
    tbl.add_column("Field", style="bold cyan", no_wrap=True, min_width=18)
    tbl.add_column("Value", overflow="fold")

    tbl.add_row("Endpoint",      f"{endpoint} {function}")
    tbl.add_row("HTTP method",   f"{operation.method} {operation.path_template}")
    tbl.add_row(
        "Would " + method_verb,
        f"[bold]{total_records:,}[/bold] "
        f"{record_noun_pl if total_records != 1 else record_noun}",
    )
    tbl.add_row("API calls",     f"[bold]{api_calls:,}[/bold]")
    tbl.add_row("Est. duration", duration)
    for note in notes:
        tbl.add_row("", f"[dim]{note}[/dim]")

    console.print(Panel(tbl, title=f"[bold]Plan: {endpoint} {function}[/bold]", expand=False))
    console.print(
        "\n[dim]No changes made. "
        "Remove [bold]--plan[/bold] to execute.[/dim]"
    )


def _enrich_domain_result(result: Any, client: Any) -> Any:
    """Resolve category and application IDs in a domain lookup response to names.

    Works for both user-lookup (single domain) and bulk-lookup (dict of domains).
    Replaces the relationships structure with plain name strings so the output
    renderer shows "Information Technology" instead of "(1 item)".
    """
    # Build lookup maps once, reused across all domains in the response
    id_to_cat: dict[str, str] = {}
    id_to_app: dict[str, str] = {}
    try:
        cats = client.get("/v1/categories/all")
        cats_list = cats if isinstance(cats, list) else (cats or {}).get("data", [])
        for c in cats_list or []:
            if isinstance(c, dict):
                cid = str(c.get("id", ""))
                name = (c.get("attributes") or {}).get("name") or c.get("name") or ""
                if cid and name:
                    id_to_cat[cid] = name
    except Exception:
        pass

    try:
        apps = client.get("/v1/applications/all")
        apps_list = apps if isinstance(apps, list) else (apps or {}).get("data", [])
        for a in apps_list or []:
            if isinstance(a, dict):
                aid = str(a.get("id", ""))
                name = (a.get("attributes") or {}).get("name") or a.get("name") or ""
                if aid and name:
                    id_to_app[aid] = name
    except Exception:
        pass

    def _resolve_domain_obj(obj: dict) -> dict:
        """Replace relationship id-lists with resolved name strings."""
        import copy
        obj = copy.deepcopy(obj)
        rels = obj.get("relationships", {})

        cat_ids = [str(c["id"]) for c in rels.get("categories",    {}).get("data", []) if c.get("id")]
        app_ids = [str(a["id"]) for a in rels.get("applications", {}).get("data", []) if a.get("id")]

        cat_names = [id_to_cat.get(cid, f"Category {cid}") for cid in cat_ids]
        app_names = [id_to_app.get(aid, f"Application {aid}") for aid in app_ids]

        # Replace the relationship block with plain resolved strings
        obj["categories"]    = ", ".join(cat_names) if cat_names else None
        obj["applications"]  = ", ".join(app_names) if app_names else None

        # Remove the raw relationships block so it doesn't clutter the output
        obj.pop("relationships", None)
        obj.pop("type", None)
        obj.pop("id",   None)

        return obj

    if not isinstance(result, dict):
        return result

    data = result.get("data")
    if data is None:
        return result

    # bulk-lookup: data is {"google.com": {...}, ...}
    if isinstance(data, dict) and not data.get("type"):
        enriched = {}
        for domain_name, domain_obj in data.items():
            if isinstance(domain_obj, dict):
                enriched[domain_name] = _resolve_domain_obj(domain_obj)
            else:
                enriched[domain_name] = domain_obj
        return {"data": enriched}

    # user-lookup: data is a single domain object
    if isinstance(data, dict):
        return {"data": _resolve_domain_obj(data)}

    return result


# ---------------------------------------------------------------------------
# Async job polling helpers (used by --wait)
# ---------------------------------------------------------------------------

# Status values that mean the job is done (success or failure).
_TERMINAL_OK: frozenset[str] = frozenset({
    "completed", "complete", "done", "success", "finished",
})
_TERMINAL_ERR: frozenset[str] = frozenset({
    "failed", "error", "errored",
})


def _find_job_status(data: Any) -> str | None:
    """Return the job status string from an API response, or None if not found."""
    if not isinstance(data, dict):
        return None
    for key in ("status", "state"):
        val = data.get(key)
        if isinstance(val, str):
            return val
    inner = data.get("data")
    if isinstance(inner, dict):
        for key in ("status", "state"):
            val = inner.get(key)
            if isinstance(val, str):
                return val
    return None


def _find_job_id(data: Any) -> Any:
    """Return the job ID from an API response (root or inside 'data' envelope)."""
    if not isinstance(data, dict):
        return None
    job_id = data.get("id")
    if job_id is not None:
        return job_id
    inner = data.get("data")
    if isinstance(inner, dict):
        return inner.get("id")
    return None


def _wait_for_job(
    initial_result: Any,
    endpoint: str,
    poll_function: str,
    resolved_key: str,
    base_url: str,
    resolved_org: str | None,
    raw: bool,
    title: str,
    columns: list[str] | None,
    max_wait: float | None = None,
) -> None:
    """Poll *endpoint*/*poll_function* until the job reaches a terminal state."""
    import time

    job_id = _find_job_id(initial_result)
    if job_id is None:
        print_warning("--wait: could not extract a job ID from the response; polling skipped.")
        return

    try:
        poll_op = get_operation(endpoint, poll_function)
    except Exception:
        print_warning(f"--wait: poll operation '{endpoint} {poll_function}' not found; polling skipped.")
        return

    poll_path, _ = _build_path(poll_op.path_template, {"id": job_id})

    interval = 3.0   # seconds between polls
    max_interval = 30.0
    attempt = 0

    console.print(f"[dim]Waiting for job {job_id} ({endpoint} {poll_function})…[/dim]")

    _wfj_deadline = time.monotonic() + max_wait if max_wait is not None else None
    with DNSFilterClient(api_key=resolved_key, base_url=base_url, org_id=resolved_org) as client:
        while True:
            attempt += 1
            time.sleep(interval)
            if _wfj_deadline is not None and time.monotonic() > _wfj_deadline:
                print_warning(f"--max-wait: {max_wait:.0f}s exceeded waiting for job {job_id}.")
                return
            interval = min(interval * 1.5, max_interval)

            try:
                result = client.request("GET", poll_path)
            except APIError as exc:
                print_error(f"Poll request failed: {exc}")
                return

            status = _find_job_status(result)

            if status is None:
                # Can't detect status; give up after a few tries to avoid an infinite loop
                if attempt >= 5:
                    print_warning("--wait: no recognizable status field found after 5 polls; showing last result.")
                    print_response(result, raw=raw, title=title, columns=columns)
                    return
                console.print(f"  [dim]Attempt {attempt}: status unknown, retrying in {interval:.0f}s…[/dim]")
                continue

            status_lower = status.lower()
            if status_lower in _TERMINAL_OK:
                console.print(f"[bold green]✓[/bold green] Job {job_id} {status_lower}.")
                print_response(result, raw=raw, title=title, columns=columns)
                return
            if status_lower in _TERMINAL_ERR:
                console.print(f"[bold red]✗[/bold red] Job {job_id} {status_lower}.")
                print_response(result, raw=raw, title=title, columns=columns)
                return

            console.print(f"  [dim]{status} — checking again in {interval:.0f}s (attempt {attempt})[/dim]")


def _parse_filter(expr: str) -> tuple[str, str, str]:
    """Parse a filter expression into (field, operator, value).

    Supported operators (checked in order of length so '>=' is not mis-parsed as '>'):
      field=value    exact match (string comparison after coercion)
      field!=value   not equal
      field~value    case-insensitive substring contains
      field>=value   >=
      field<=value   <=
      field>value    >
      field<value    <

    Raises ``ValueError`` for unrecognised expressions.
    """
    for op in ("!=", ">=", "<=", "~", "=", ">", "<"):
        if op in expr:
            field, _, value = expr.partition(op)
            field = field.strip()
            value = value.strip()
            if not field:
                raise ValueError(f"No field name in filter expression: {expr!r}")
            return field, op, value
    raise ValueError(
        f"Unrecognised filter expression: {expr!r}. "
        "Expected form: field=value, field!=value, field~value, field>=value, etc."
    )


_TRANSFORM_BUILTINS: dict[str, Any] = {
    "int": int, "float": float, "str": str, "len": len,
    "abs": abs, "round": round, "min": min, "max": max, "bool": bool,
}

# AST nodes permitted in --transform expressions. Attribute access is
# deliberately excluded — it is the escape hatch from any eval sandbox
# (e.g. ().__class__.__bases__). Dotted field access is not needed here
# because transforms operate on top-level response fields.
_TRANSFORM_ALLOWED_NODES: tuple = (
    ast.Expression, ast.BinOp, ast.UnaryOp, ast.BoolOp, ast.Compare, ast.IfExp,
    ast.Call, ast.Name, ast.Constant, ast.Subscript, ast.List, ast.Tuple,
    ast.Dict, ast.Load,
    # operators
    ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod, ast.Pow,
    ast.USub, ast.UAdd, ast.Not, ast.And, ast.Or,
    ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE,
    ast.In, ast.NotIn, ast.Is, ast.IsNot,
)


def _compile_transform_expr(expr: str):
    """Parse and validate a --transform expression; return a code object.

    Raises ``ValueError`` when the expression uses anything beyond arithmetic,
    comparisons, literals, field names, and the whitelisted builtin calls.
    """
    tree = ast.parse(expr, mode="eval")
    for node in ast.walk(tree):
        if not isinstance(node, _TRANSFORM_ALLOWED_NODES):
            raise ValueError(
                f"Unsupported syntax in transform expression {expr!r}: "
                f"{type(node).__name__}"
            )
        if isinstance(node, ast.Name) and node.id.startswith("__"):
            raise ValueError(f"Illegal name {node.id!r} in transform expression")
        if isinstance(node, ast.Call) and not (
            isinstance(node.func, ast.Name) and node.func.id in _TRANSFORM_BUILTINS
        ):
            raise ValueError(
                f"Only these functions may be called in a transform: "
                f"{', '.join(sorted(_TRANSFORM_BUILTINS))}"
            )
    return compile(tree, "<transform>", "eval")


def _apply_transforms(items: list[Any], transform_specs: list[str]) -> list[Any]:
    """Compute new or derived fields from restricted expressions.

    Each spec is FIELD=EXPR where EXPR may reference any existing field by name.
    Expressions are validated against an AST allowlist before evaluation:
    arithmetic, comparisons, literals, and calls to int, float, str, len, abs,
    round, min, max, bool. Attribute access and other syntax are rejected.
    """
    for spec in transform_specs:
        if "=" not in spec:
            continue
        _tf_field, _tf_expr = spec.split("=", 1)
        _tf_field = _tf_field.strip()
        _tf_expr = _tf_expr.strip()
        try:
            _code = _compile_transform_expr(_tf_expr)
        except (ValueError, SyntaxError) as exc:
            print_error(f"Invalid --transform expression: {exc}")
            sys.exit(1)
        _new: list[Any] = []
        for item in items:
            if isinstance(item, dict):
                _ns = {
                    **_TRANSFORM_BUILTINS,
                    **{k: v for k, v in item.items() if isinstance(k, str)},
                }
                try:
                    _val = eval(_code, {"__builtins__": {}}, _ns)  # noqa: S307 — AST-validated above
                    item = {**item, _tf_field: _val}
                except Exception:
                    pass
            _new.append(item)
        items = _new
    return items


def _apply_filters(items: list[Any], filters: list[str], mode: str = "and") -> list[Any]:
    """Return the subset of *items* that match *filters*.

    With mode='and' (default) ALL filters must match.  With mode='or' ANY filter
    is sufficient.  Each filter string is parsed by ``_parse_filter``.  Items that
    are not dicts are kept as-is when the field is absent.
    """
    import re as _re

    compiled: list[tuple[str, str, str]] = []
    for expr in filters:
        compiled.append(_parse_filter(expr))

    def _get(item: Any, field: str) -> Any:
        """Fetch a dotted or flat field from *item*."""
        if not isinstance(item, dict):
            return None
        if "." in field:
            parts = field.split(".", 1)
            return _get(item.get(parts[0]), parts[1])
        return item.get(field)

    def _matches(item: Any, field: str, op: str, raw_value: str) -> bool:
        cell = _get(item, field)
        # Coerce raw_value to the same type as cell when possible
        try:
            if isinstance(cell, bool):
                typed: Any = raw_value.lower() in ("1", "true", "yes")
            elif isinstance(cell, int):
                typed = int(raw_value)
            elif isinstance(cell, float):
                typed = float(raw_value)
            else:
                typed = raw_value
        except (ValueError, TypeError):
            typed = raw_value

        if op == "=":
            return str(cell).lower() == str(typed).lower() if cell is not None else (typed == "")
        if op == "!=":
            return str(cell).lower() != str(typed).lower() if cell is not None else (typed != "")
        if op == "~":
            return raw_value.lower() in str(cell).lower() if cell is not None else False
        if op == ">":
            try:
                return float(str(cell)) > float(str(typed))
            except (ValueError, TypeError):
                return str(cell) > str(typed)
        if op == "<":
            try:
                return float(str(cell)) < float(str(typed))
            except (ValueError, TypeError):
                return str(cell) < str(typed)
        if op == ">=":
            try:
                return float(str(cell)) >= float(str(typed))
            except (ValueError, TypeError):
                return str(cell) >= str(typed)
        if op == "<=":
            try:
                return float(str(cell)) <= float(str(typed))
            except (ValueError, TypeError):
                return str(cell) <= str(typed)
        return False

    _check = all if mode != "or" else any
    result = []
    for item in items:
        if _check(_matches(item, field, op, value) for field, op, value in compiled):
            result.append(item)
    return result


def _apply_grep(items: list[Any], pattern: str) -> list[Any]:
    """Return items where any leaf string value matches *pattern* (regex, case-insensitive)."""
    import re as _re
    try:
        rx = _re.compile(pattern, _re.IGNORECASE)
    except _re.error:
        rx = _re.compile(_re.escape(pattern), _re.IGNORECASE)

    def _leaf_strings(obj: Any):
        if isinstance(obj, dict):
            for v in obj.values():
                yield from _leaf_strings(v)
        elif isinstance(obj, list):
            for v in obj:
                yield from _leaf_strings(v)
        elif obj is not None:
            yield str(obj)

    return [item for item in items if any(rx.search(s) for s in _leaf_strings(item))]


def _apply_unique(items: list[Any], field: str) -> list[Any]:
    """Deduplicate *items* by *field* value, keeping the first occurrence."""
    seen: set[str] = set()
    result: list[Any] = []
    for item in items:
        key = str(item.get(field, "")) if isinstance(item, dict) else str(item)
        if key not in seen:
            seen.add(key)
            result.append(item)
    return result


def _render_format_template(items: list[Any], template: str) -> None:
    """Print each item rendered through a template.

    Both placeholder styles are accepted:
      Go-style   {{.field}}  (dotted paths supported: {{.meta.total}})
      Simple     {field}     (used when no Go-style placeholder is present)
    """
    import re as _re
    _PLACEHOLDER = _re.compile(r"\{\{\.([^}]+)\}\}")
    _SIMPLE = _re.compile(r"\{([A-Za-z0-9_][A-Za-z0-9_.]*)\}")
    pattern = _PLACEHOLDER if _PLACEHOLDER.search(template) else _SIMPLE

    def _get_nested(obj: Any, dotted_key: str) -> Any:
        for part in dotted_key.split("."):
            if isinstance(obj, dict):
                obj = obj.get(part)
            else:
                return None
        return obj

    single = not isinstance(items, list)
    rows = [items] if single else items
    for item in rows:
        def _sub(m: Any) -> str:
            val = _get_nested(item, m.group(1)) if isinstance(item, dict) else None
            return str(val) if val is not None else ""
        line = pattern.sub(_sub, template) + "\n"
        sys.stdout.write(line)
        tee_write(line)


def _fetch_all_pages(
    client: Any,
    method: str,
    path: str,
    params: dict[str, Any] | None,
    json_body: dict[str, Any] | None,
    *,
    limit: int | None = None,
    max_pages: int | None = None,
    verbose: bool = False,
    show_progress: bool = True,
    paginate_until: str | None = None,
) -> tuple[Any, list[Any]]:
    """Fetch every page of a paginated list response and return the combined items.

    Returns ``(last_raw_response, all_items)`` where *all_items* is the flat
    list of every item across all pages.  If the first response is not a list
    (single resource or non-paginated) the function returns immediately with
    an empty ``all_items`` list so callers can fall back to normal handling.
    """
    from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
    page_params = dict(params or {})
    all_items: list[Any] = []
    last_result: Any = None
    page_num = 1
    total_pages: int | None = None

    def _do_fetch() -> None:
        nonlocal last_result, page_num, total_pages

        use_bar = show_progress and not verbose
        progress_ctx: Any = (
            Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TaskProgressColumn(),
                TextColumn("[dim]{task.fields[items]} items[/dim]"),
                transient=True,
                console=err_console,
            )
            if use_bar else None
        )
        task_id: Any = None

        def _enter():
            nonlocal task_id
            if progress_ctx:
                progress_ctx.__enter__()
                task_id = progress_ctx.add_task(
                    "Fetching pages…",
                    total=None,
                    items=0,
                )

        def _update(fetched: int):
            if progress_ctx and task_id is not None:
                progress_ctx.update(
                    task_id,
                    completed=page_num - 1,
                    total=total_pages,
                    items=len(all_items),
                    description=f"Page {page_num}" + (f"/{total_pages}" if total_pages else ""),
                )

        def _exit():
            if progress_ctx:
                progress_ctx.__exit__(None, None, None)

        _enter()
        try:
            while True:
                page_params["page[number]"] = page_num
                result = client.request(method, path, params=page_params or None, json=json_body)
                last_result = result

                page_items = _unwrap(result)
                if not isinstance(page_items, list):
                    return

                all_items.extend(page_items)
                if verbose:
                    print_info(f"  Page {page_num}: +{len(page_items)} items (total: {len(all_items)})")

                if limit is not None and len(all_items) >= limit:
                    break

                if max_pages is not None and page_num >= max_pages:
                    break

                if paginate_until and page_items:
                    try:
                        _pu_matched = _apply_filters(page_items, [paginate_until])
                        if _pu_matched:
                            if verbose:
                                print_info(f"  --paginate-until: condition matched on page {page_num}, stopping.")
                            break
                    except (ValueError, Exception):
                        pass

                if isinstance(result, dict):
                    meta = result.get("meta") or {}
                    pagination = (
                        meta.get("pagination")
                        or meta.get("paging")
                        or (meta if ("total_pages" in meta or "last_page" in meta) else {})
                    )
                    tp = pagination.get("total_pages") or pagination.get("last_page")
                    if tp is not None:
                        total_pages = int(tp)

                _update(len(page_items))

                if total_pages is None or page_num >= total_pages:
                    break

                page_num += 1
        finally:
            _exit()

    _do_fetch()
    return last_result, all_items

    return last_result, all_items


def _run_api_call(
    ctx: typer.Context,
    endpoint: str,
    function: str,
    *,
    raw: bool,
    verbose: bool,
    api_key: str | None,
    org_id: str | None,
    csv_file: str | None = None,
    csv_input: str | None = None,
    show_template: bool = False,
    show_plan: bool = False,
    skip_confirm: bool = False,
    columns: list[str] | None = None,
    wait: bool = False,
    profile: str = DEFAULT_PROFILE,
    fetch_all: bool = False,
    as_json: bool = False,
    sort_by: list[str] | None = None,
    limit: int | None = None,
    json_file: str | None = None,
    timeout: float | None = None,
    filters: list[str] | None = None,
    count_only: bool = False,
    body_json: str | None = None,
    page: int | None = None,
    page_size: int | None = None,
    as_jsonl: bool = False,
    on_error: str = "continue",
    concurrency: int = 1,
    grep: str | None = None,
    unique_field: str | None = None,
    format_template: str | None = None,
    csv_append: bool = False,
    dry_run: bool = False,
    json_input: str | None = None,
    cache_ttl: int | None = None,
    org_name: str | None = None,
    set_fields: list[str] | None = None,
    exclude_fields: list[str] | None = None,
    merge_key: str | None = None,
    rate: float | None = None,
    truncate: int | None = None,
    csv_delimiter: str = ",",
    rename_fields: list[str] | None = None,
    pick_field: str | None = None,
    batch_size: int | None = None,
    no_header: bool = False,
    csv_header_case: str | None = None,
    retry: int = 0,
    errors_csv: str | None = None,
    retry_errors_csv: str | None = None,
    timing: bool = False,
    group_by: str | None = None,
    select_fields: list[str] | None = None,
    sum_field: str | None = None,
    avg_field: str | None = None,
    min_field: str | None = None,
    max_field: str | None = None,
    map_fields: list[str] | None = None,
    watch_changes_interval: int | None = None,
    upsert: bool = False,
    last: int | None = None,
    sample: int | None = None,
    fields_only: bool = False,
    strip_nulls: bool = False,
    max_pages: int | None = None,
    max_errors: int | None = None,
    null_as: str | None = None,
    no_wrap: bool = False,
    color_rules: list[tuple[str, str, str]] | None = None,
    count_by: str | None = None,
    not_null_field: str | None = None,
    is_null_field: str | None = None,
    since_filter: str | None = None,
    extra_headers: list[str] | None = None,
    insecure: bool = False,
    no_progress: bool = False,
    tee_file: str | None = None,
    validate_only: bool = False,
    confirm_each: bool = False,
    diff_mode: bool = False,
    skip_rows: int = 0,
    max_rows: int | None = None,
    add_fields: list[str] | None = None,
    paginate_until: str | None = None,
    batch_report: str | None = None,
    org_csv: str | None = None,
    color_scale: str | None = None,
    format_preset: str | None = None,
    flatten: bool = False,
    strip_empties: bool = False,
    csv_null_value: str | None = None,
    watch_until_filter: str | None = None,
    fail_on_empty: bool = False,
    batch_delay: int | None = None,
    connect_timeout: float | None = None,
    proxy: str | None = None,
    jq_expr: str | None = None,
    max_wait: float | None = None,
    alert_filter: str | None = None,
    stats_field: str | None = None,
    result_sink: list | None = None,
    stdin_json: bool = False,
    fail_on_pattern: str | None = None,
    filter_mode: str = "and",
    to_markdown: str | None = None,
    output_schema: bool = False,
    exec_cmd: str | None = None,
    transforms: list[str] | None = None,
    join_spec: str | None = None,
) -> None:
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
        import re as _re
        resolved_org_early = org_id or get_org_id(profile=profile)
        extra_early: dict[str, str] = _parse_extra_args(ctx.args)
        params_early: dict[str, Any] = {k: _coerce_value(v) for k, v in extra_early.items()}
        for flag in ("raw", "verbose", "api-key", "org-id", "to-csv", "from-csv", "template", "plan", "yes", "columns", "wait", "profile", "all", "json", "no-color", "quiet", "sort", "limit", "to-json", "timeout", "filter", "count", "body-json", "page", "page-size", "jsonl", "on-error", "concurrency", "grep", "unique", "format", "append", "dry-run", "from-json", "cache-ttl", "each-org", "org-name", "set", "exclude", "merge-key", "rate", "truncate", "csv-delimiter", "no-header", "retry", "errors-to-csv", "retry-errors-csv", "csv-header-case", "rename", "pick", "batch-size", "timing", "group-by", "select", "sum", "avg", "min", "max", "map", "watch-changes", "upsert", "last", "sample", "fields", "strip-nulls", "max-pages", "max-errors", "save-as", "null-as", "no-wrap", "color-if", "count-by", "not-null", "is-null", "since", "header", "insecure", "no-progress", "tee", "output", "validate-only", "confirm-each", "diff-mode", "parallel-orgs", "org-concurrency", "max-orgs", "preset", "flatten", "strip-empties", "csv-null", "watch-until", "fail-on-empty", "quiet-ok", "delay", "org-filter", "connect-timeout", "proxy", "jq", "max-wait", "watch-diff", "alert", "table-style", "stats", "env-file", "log-file", "stdin-json", "skip-rows", "max-rows", "add-field", "paginate-until", "org-csv", "batch-report", "color-scale", "format-preset", "fail-on-pattern", "filter-mode", "to-markdown", "output-schema", "exec", "transform", "join", "bundle"):
            params_early.pop(flag, None)
        params_early = _normalize_param_keys(params_early)
        if resolved_org_early and "organization_id" not in params_early:
            if any(p.name == "organization_id" for p in operation.params):
                params_early["organization_id"] = int(resolved_org_early)
        _show_plan(endpoint, function, operation, params_early, None)
        return

    resolved_key = api_key or get_api_key(profile=profile)
    if not resolved_key:
        print_error(
            "No API key found. Set one with [bold]dnsfcli auth setup[/bold] "
            "or pass [bold]--api-key[/bold] / env var [bold]DNSF_API_KEY[/bold]."
        )
        sys.exit(1)
    if api_key and _api_key_flag_on_cli():
        print_warning(
            "API key passed via [bold]--api-key[/bold]. "
            "It may be exposed in: shell history (~/.zsh_history, ~/.bash_history), "
            "process listings (ps aux), and CI/CD logs. "
            "Prefer [bold]dnsfcli auth setup[/bold] or the "
            "[bold]DNSF_API_KEY[/bold] environment variable."
        )

    import re
    resolved_org = org_id or get_org_id(profile=profile)
    # Normalise: strip any trailing /v1 or /v2 from the stored base URL so the
    # version-prefixed paths in the registry are never doubled.
    base_url = re.sub(r"/v\d+/*$", "", get_base_url(profile=profile).rstrip("/"))
    if not base_url.startswith("https://"):
        print_error(f"Base URL must use HTTPS. Got: {base_url!r}. Update it with [bold]dnsfcli auth setup --base-url[/bold].")
        sys.exit(1)
    if base_url != "https://api.dnsfilter.com":
        print_warning(f"Non-default base URL in use: {base_url}")

    # Parse --header KEY=VALUE list into a dict; --insecure skips TLS verification
    _parsed_headers: dict[str, str] | None = None
    if extra_headers:
        _parsed_headers = {}
        for _hdr in extra_headers:
            if "=" in _hdr:
                _hk, _hv = _hdr.split("=", 1)
                _parsed_headers[_hk.strip()] = _hv.strip()
            else:
                print_warning(f"--header: ignored malformed entry {_hdr!r} (expected KEY=VALUE)")
    if insecure:
        print_warning("TLS verification disabled (--insecure). Do not use in production.")
        if proxy:
            print_warning("--insecure + --proxy: TLS is disabled and a proxy is set. "
                          "Your API key and all request data will be visible to the proxy operator in plaintext.")

    # Build shared kwargs for every DNSFilterClient instantiation in this call
    _ck_base: dict[str, Any] = {
        "api_key": resolved_key,
        "base_url": base_url,
        "verify": not insecure,
        "extra_headers": _parsed_headers,
        **({"connect_timeout": connect_timeout} if connect_timeout is not None else {}),
        **({"proxy": proxy} if proxy else {}),
    }

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
                _orgs_raw = _cl.get("/v1/organizations")
            _orgs = _unwrap(_orgs_raw)
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
    for flag in ("raw", "verbose", "api-key", "org-id", "to-csv", "from-csv", "template", "plan", "yes", "columns", "wait", "profile", "all", "json", "no-color", "quiet", "sort", "limit", "to-json", "timeout", "filter", "count", "body-json", "page", "page-size", "jsonl", "on-error", "concurrency", "grep", "unique", "format", "append", "dry-run", "from-json", "cache-ttl", "each-org", "org-name", "set", "exclude", "merge-key", "rate", "truncate", "csv-delimiter", "no-header", "retry", "errors-to-csv", "retry-errors-csv", "csv-header-case", "rename", "pick", "batch-size", "timing", "group-by", "select", "sum", "avg", "min", "max", "map", "watch-changes", "upsert", "last", "sample", "fields", "strip-nulls", "max-pages", "max-errors", "save-as", "null-as", "no-wrap", "color-if", "count-by", "not-null", "is-null", "since", "header", "insecure", "no-progress", "tee", "output", "validate-only", "confirm-each", "diff-mode", "parallel-orgs", "org-concurrency", "max-orgs", "preset", "flatten", "strip-empties", "csv-null", "watch-until", "fail-on-empty", "quiet-ok", "delay", "org-filter", "connect-timeout", "proxy", "jq", "max-wait", "watch-diff", "alert", "table-style", "stats", "env-file", "log-file", "stdin-json", "skip-rows", "max-rows", "add-field", "paginate-until", "org-csv", "batch-report", "color-scale", "format-preset", "fail-on-pattern", "filter-mode", "to-markdown", "output-schema", "exec", "transform", "join", "bundle"):
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
            params["organization_id"] = int(resolved_org)

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
                _mk_result = _mk_cl.get(_mk_list_path, params=_mk_query or None)
            _mk_items = _unwrap(_mk_result)
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

    # --from-csv: validate the file then loop over rows
    if csv_input:
        from .csv_io import CsvValidationError, read_csv_input
        try:
            rows = read_csv_input(csv_input, operation, params, csv_delimiter)
        except CsvValidationError as exc:
            print_error(f"CSV validation failed for {exc.filepath}:")
            for err in exc.errors:
                err_console.print(f"  {err}")
            sys.exit(1)
        # --skip-rows / --max-rows: slice input before processing
        if skip_rows:
            console.print(f"[dim]--skip-rows: skipping first {skip_rows} row(s) ({len(rows)} total)[/dim]")
            rows = rows[skip_rows:]
        if max_rows is not None:
            rows = rows[:max_rows]
        n = len(rows)
        if operation.method == "DELETE" or operation.destructive:
            _confirm_destructive(
                f"About to execute {n} destructive "
                f"{'operation' if n == 1 else 'operations'} "
                f"({endpoint} {function}) from {csv_input}.",
                skip_confirm,
            )
        elif operation.method in ("POST", "PATCH", "PUT"):
            _preview_confirm_batch(rows, operation, endpoint, function, skip_confirm)
        _batches = [rows]
        if batch_size and batch_size > 0:
            _batches = [rows[i:i + batch_size] for i in range(0, len(rows), batch_size)]
        with DNSFilterClient(**{**_ck_base, "org_id": resolved_org, "timeout": effective_timeout, "rate": rate}) as client:
            for _batch_idx, _batch in enumerate(_batches):
                if len(_batches) > 1:
                    console.print(f"[dim]Batch {_batch_idx + 1}/{len(_batches)} ({len(_batch)} rows)[/dim]")
                _execute_csv_rows(
                    _batch, operation, endpoint, function, client,
                    verbose=verbose, csv_output=csv_file, org_id=resolved_org, columns=columns,
                    on_error=on_error, concurrency=concurrency, csv_delimiter=csv_delimiter,
                    retry=retry, errors_csv=errors_csv, upsert=upsert, max_errors=max_errors,
                    confirm_each=confirm_each, validate_only=validate_only, no_progress=no_progress,
                    batch_delay=batch_delay, diff_mode=diff_mode, batch_report_path=batch_report,
                )
        return

    # --from-json: batch execution from a JSON array (each object → one API call)
    if json_input:
        import json as _json
        src = json_input.strip()
        if src == "-":
            content = sys.stdin.read()
            src_label = "stdin"
        else:
            try:
                with open(src, encoding="utf-8") as _fh:
                    content = _fh.read()
                src_label = src
            except OSError as exc:
                print_error(f"--from-json: cannot read file: {exc}")
                sys.exit(1)
        try:
            json_data: Any = _json.loads(content)
        except _json.JSONDecodeError as exc:
            print_error(f"--from-json: invalid JSON: {exc}")
            sys.exit(1)
        if isinstance(json_data, dict):
            json_data = _unwrap(json_data)
        if not isinstance(json_data, list):
            print_error("--from-json: expected a JSON array ([...]).")
            sys.exit(1)
        if not json_data:
            print_error("--from-json: JSON array is empty.")
            sys.exit(1)
        if not all(isinstance(item, dict) for item in json_data):
            print_error("--from-json: every element of the JSON array must be an object ({...}).")
            sys.exit(1)
        # Merge: CLI params take priority over JSON fields
        json_rows = [{**item, **params} for item in json_data]
        if skip_rows:
            json_rows = json_rows[skip_rows:]
        if max_rows is not None:
            json_rows = json_rows[:max_rows]
        n = len(json_rows)
        if operation.method == "DELETE" or operation.destructive:
            _confirm_destructive(
                f"About to execute {n} destructive {'operation' if n == 1 else 'operations'} "
                f"({endpoint} {function}) from {src_label}.",
                skip_confirm,
            )
        elif operation.method in ("POST", "PATCH", "PUT"):
            _preview_confirm_batch(json_rows, operation, endpoint, function, skip_confirm)
        _json_batches = [json_rows]
        if batch_size and batch_size > 0:
            _json_batches = [json_rows[i:i + batch_size] for i in range(0, len(json_rows), batch_size)]
        with DNSFilterClient(**{**_ck_base, "org_id": resolved_org, "timeout": effective_timeout, "rate": rate}) as client:
            for _jb_idx, _jb in enumerate(_json_batches):
                if len(_json_batches) > 1:
                    console.print(f"[dim]Batch {_jb_idx + 1}/{len(_json_batches)} ({len(_jb)} rows)[/dim]")
                _execute_csv_rows(
                    _jb, operation, endpoint, function, client,
                    verbose=verbose, csv_output=csv_file, org_id=resolved_org, columns=columns,
                    on_error=on_error, concurrency=concurrency, csv_delimiter=csv_delimiter,
                    retry=retry, errors_csv=errors_csv, upsert=upsert, max_errors=max_errors,
                    confirm_each=confirm_each, validate_only=validate_only, no_progress=no_progress,
                    batch_delay=batch_delay, diff_mode=diff_mode, batch_report_path=batch_report,
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
        with DNSFilterClient(**{**_ck_base, "org_id": resolved_org, "timeout": effective_timeout, "rate": rate}) as client:
            _create_ips_from_cidr(
                cidr, body_params, client,
                verbose=verbose, csv_output=csv_file, columns=columns,
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
                    raw_src = open(_bj_filename, encoding="utf-8").read()
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
        print_info(f"[dim]{method}[/dim] {base_url}{path}")
        if query_params:
            print_info(f"Query: {query_params}")
        if json_body:
            print_info(f"Body:  {json_body}")

    # --dry-run: show the resolved request and exit without making any API call
    if dry_run:
        _show_dry_run(method, base_url, path, query_params, json_body)
        return

    with DNSFilterClient(**{**_ck_base, "org_id": resolved_org, "timeout": effective_timeout, "rate": rate}) as client:
        try:
            result: Any = None
            _from_cache = False

            # --cache-ttl: serve GET from cache if still fresh
            if cache_ttl and method == "GET":
                from . import cache as _cache_mod
                _ck = _cache_mod.make_key(endpoint, function, path, query_params)
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
                if cache_ttl and method == "GET":
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
                        for _sk in reversed(sort_by):
                            _sk_field = _sk.lstrip("-")
                            _sk_rev = _sk.startswith("-")
                            payload = sorted(
                                payload,
                                key=lambda x, f=_sk_field: (x.get(f) is None, x.get(f)) if isinstance(x, dict) else (False, x),
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
                        if _j_ep and "=" in _j_keys:
                            _j_local, _j_remote = _j_keys.split("=", 1)
                            _j_local = _j_local.strip()
                            _j_remote = _j_remote.strip()
                            try:
                                _j_raw = client.get(f"/v1/{_j_ep.strip()}")
                                _j_recs = _unwrap(_j_raw)
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
                _foe_payload = _unwrap(result)
                if isinstance(_foe_payload, list) and len(_foe_payload) == 0:
                    err_console.print("[bold red]No results.[/bold red]")
                    sys.exit(1)

            # --fail-on-pattern: exit non-zero when any result matches the expression
            if fail_on_pattern and not isinstance(result, str):
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
                        print_warning(f"--fail-on-pattern: {_fop_exc}")

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
                _sum_payload = _unwrap(result)
                _sum_items = _sum_payload if isinstance(_sum_payload, list) else [_sum_payload]
                _sum_val = _apply_sum(_sum_items, sum_field)
                _sum_display = int(_sum_val) if _sum_val == int(_sum_val) else _sum_val
                console.print(f"[bold]{_sum_display}[/bold]  [dim]sum({sum_field})[/dim]")
                return

            if avg_field is not None:
                _avg_payload = _unwrap(result)
                _avg_items = _avg_payload if isinstance(_avg_payload, list) else [_avg_payload]
                _avg_val = _apply_avg(_avg_items, avg_field)
                if _avg_val is None:
                    console.print(f"[dim]no numeric values found for '{avg_field}'[/dim]")
                else:
                    console.print(f"[bold]{_avg_val:.4g}[/bold]  [dim]avg({avg_field})[/dim]")
                return

            if min_field is not None:
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

            # --exec: run a shell command for each result item with {field} substitution.
            # Field values are shell-quoted via shlex.quote() before substitution so that
            # API response values containing shell metacharacters cannot inject commands.
            if exec_cmd and not isinstance(result, str):
                import subprocess as _sp
                import shlex as _shlex_exec
                _exc_payload = _unwrap(result)
                _exc_items = _exc_payload if isinstance(_exc_payload, list) else ([_exc_payload] if isinstance(_exc_payload, dict) else [])
                _exc_ok = _exc_fail = 0
                for _exc_item in _exc_items:
                    _exc_rendered = exec_cmd
                    if isinstance(_exc_item, dict):
                        for _ek, _ev in _exc_item.items():
                            _quoted = _shlex_exec.quote(str(_ev))
                            _exc_rendered = _exc_rendered.replace(f"{{{_ek}}}", _quoted).replace(f"${_ek}", _quoted)
                    try:
                        _exc_rc = _sp.run(_exc_rendered, shell=True).returncode
                        if _exc_rc == 0:
                            _exc_ok += 1
                        else:
                            _exc_fail += 1
                    except Exception as _exc_err:
                        print_warning(f"--exec: {_exc_err}")
                        _exc_fail += 1
                if not quiet:
                    console.print(f"[dim]--exec: {_exc_ok} succeeded, {_exc_fail} failed[/dim]")

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
                _wait_for_job(
                    result, endpoint, operation.poll_on,
                    resolved_key, base_url, resolved_org,
                    raw=raw, title=title, columns=columns,
                    max_wait=max_wait,
                )

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

config_app = typer.Typer(help="Manage the dnsfcli configuration file.", rich_markup_mode="rich")
app.add_typer(config_app, name="config")


@config_app.command("show")
def config_show() -> None:
    """Display the current configuration (file values + active path)."""
    from rich.table import Table as _Table
    cfg = load_config()
    path = config_path()
    console.print(f"[bold]Config file:[/bold] [dim]{path}[/dim] {'[green](exists)[/green]' if path.exists() else '[dim](not found — using defaults)[/dim]'}\n")
    tbl = _Table(show_header=False, box=None, padding=(0, 2))
    tbl.add_column("Key", style="bold cyan", no_wrap=True, min_width=16)
    tbl.add_column("Value")
    tbl.add_row("profile",  cfg.profile)
    tbl.add_row("timeout",  str(cfg.timeout))
    tbl.add_row("quiet",    str(cfg.quiet))
    tbl.add_row("no_color", str(cfg.no_color))
    if cfg.columns:
        for ep, cols in cfg.columns.items():
            tbl.add_row(f"columns.{ep}", ", ".join(cols))
    if cfg.column_presets:
        for name, cols in cfg.column_presets.items():
            tbl.add_row(f"preset.{name}", ", ".join(cols))
    if cfg.format_presets:
        for name, tmpl in cfg.format_presets.items():
            tbl.add_row(f"format.{name}", tmpl)
    if cfg.bundles:
        for bname, bvals in cfg.bundles.items():
            for bk, bv in bvals.items():
                tbl.add_row(f"bundle.{bname}.{bk}", str(bv))
    console.print(tbl)


@config_app.command("init")
def config_init(
    force: bool = typer.Option(False, "--force", "-f", help="Overwrite an existing config file without prompting."),
) -> None:
    """Scaffold a starter config.toml with commented documentation.

    Writes to the standard config path and opens it for editing.
    Run [bold]dnsfcli config show[/bold] to see the current path.
    """
    path = config_path()
    if path.exists() and not force:
        typer.confirm(f"Config file already exists at {path}. Overwrite?", abort=True)

    path.parent.mkdir(parents=True, exist_ok=True)

    template = """\
# dnsfcli configuration file
# Location: {path}
#
# All values are optional — dnsfcli works without this file.
# CLI flags and environment variables (DNSF_*, DNSFCLI_*) take precedence.

[defaults]
# Named credential profile to use when --profile is not supplied.
# profile = "default"

# Per-request read/write timeout in seconds.
# timeout = 30.0

# Suppress non-error output globally (same as --quiet on every call).
# quiet = false

# Disable ANSI colour output globally (same as --no-color or NO_COLOR env var).
# no_color = false

# Per-endpoint default column lists — override with --columns on the CLI.
# [columns]
# networks  = "id,name,status,policy_id"
# users     = "id,email,role"
# policies  = "id,name,type"

# Named column presets — use with --preset NAME on any command.
# [column_presets]
# compact   = "id,name,status"
# detailed  = "id,name,status,created_at,updated_at"

# Named format templates — use with --format-preset NAME on any command.
# [format_presets]
# summary  = "{{name}} ({{status}})"
# oneline  = "{{id}}  {{name}}"

# Command bundles — store a combination of flags as a named preset.
# Use with --bundle NAME on any command.
# Supported keys: columns, format, format_preset, sort, filter, filter_mode.
# [bundles.active]
# filter      = "status=active"
# sort        = "-created_at"
# columns     = "id,name,status,created_at"
# format_preset = "summary"

# Default settings for batch (--from-csv) operations.
# All values can be overridden per-command with the corresponding CLI flags.
# [batch]
# concurrency = 1          # number of parallel workers
# retry       = 0          # per-row retry attempts on transient errors
# on_error    = "continue" # "continue", "stop", or "report"
# max_errors  = 10         # abort after this many cumulative errors (omit for unlimited)
# batch_size  = 100        # chunk rows into groups of this size (omit to disable)
""".format(path=path)

    path.write_text(template, encoding="utf-8")
    print_success(f"Config file created at {path}")
    console.print(f"[dim]Edit it with your preferred editor, then run [bold]dnsfcli config show[/bold] to verify.[/dim]")


@config_app.command("edit")
def config_edit() -> None:
    """Open the config file in $VISUAL / $EDITOR (falls back to vi).

    Creates the file with starter content first if it doesn't exist yet.
    """
    import subprocess as _sp
    path = config_path()
    if not path.exists():
        console.print(f"[dim]Config file not found — creating starter config at {path}[/dim]")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "# dnsfcli configuration\n[defaults]\n# profile = \"default\"\n# timeout = 30.0\n",
            encoding="utf-8",
        )
    editor = os.environ.get("VISUAL") or os.environ.get("EDITOR") or "vi"
    _sp.run([editor, str(path)])


@config_app.command("set")
def config_set_cmd(
    key: str = typer.Argument(..., help="Config key to set. Use dot-notation for columns: columns.networks"),
    value: str = typer.Argument(..., help="Value to set. Booleans: true/false. For columns: comma-separated list."),
) -> None:
    """Set a config value without editing the file directly.

    Examples:

      dnsfcli config set timeout 60
      dnsfcli config set quiet true
      dnsfcli config set profile production
      dnsfcli config set columns.networks id,name,status,policy_id
    """
    from .config import load_config, save_config, config_path
    cfg = load_config()

    _TOP_LEVEL_KEYS = {"profile", "no_color", "quiet", "timeout"}
    _BATCH_KEYS = {"concurrency", "retry", "on_error", "max_errors", "batch_size"}

    if key.startswith("columns."):
        ep = key[len("columns."):]
        if not ep:
            print_error("columns key must be columns.ENDPOINT, e.g. columns.networks")
            raise typer.Exit(1)
        cfg.columns[ep] = [c.strip() for c in value.split(",") if c.strip()]
    elif key.startswith("preset."):
        _preset_name = key[len("preset."):]
        if not _preset_name:
            print_error("preset key must be preset.NAME, e.g. preset.compact")
            raise typer.Exit(1)
        cfg.column_presets[_preset_name] = [c.strip() for c in value.split(",") if c.strip()]
    elif key.startswith("format."):
        _fmt_name = key[len("format."):]
        if not _fmt_name:
            print_error("format key must be format.NAME, e.g. format.summary")
            raise typer.Exit(1)
        cfg.format_presets[_fmt_name] = value
    elif key.startswith("bundle."):
        _bnd_parts = key[len("bundle."):].split(".", 1)
        if len(_bnd_parts) < 2 or not _bnd_parts[0] or not _bnd_parts[1]:
            print_error("bundle key must be bundle.NAME.flag, e.g. bundle.audit.columns")
            raise typer.Exit(1)
        _bnd_name, _bnd_flag = _bnd_parts
        if _bnd_name not in cfg.bundles:
            cfg.bundles[_bnd_name] = {}
        cfg.bundles[_bnd_name][_bnd_flag] = value
    elif key.startswith("batch."):
        bk = key[len("batch."):]
        if bk not in _BATCH_KEYS:
            print_error(
                f"Unknown batch key: {bk!r}. Valid batch keys: {', '.join(sorted(_BATCH_KEYS))}"
            )
            raise typer.Exit(1)
        if bk in ("concurrency", "retry"):
            try:
                setattr(cfg.batch, bk, int(value))
            except ValueError:
                print_error(f"batch.{bk} must be an integer, got {value!r}")
                raise typer.Exit(1)
        elif bk in ("max_errors", "batch_size"):
            if value.lower() in ("none", "null", ""):
                setattr(cfg.batch, bk, None)
            else:
                try:
                    setattr(cfg.batch, bk, int(value))
                except ValueError:
                    print_error(f"batch.{bk} must be an integer or 'none', got {value!r}")
                    raise typer.Exit(1)
        else:  # on_error
            if value not in ("continue", "stop", "report"):
                print_error(f"batch.on_error must be 'continue', 'stop', or 'report', got {value!r}")
                raise typer.Exit(1)
            cfg.batch.on_error = value
    elif key in _TOP_LEVEL_KEYS:
        if key == "timeout":
            try:
                setattr(cfg, key, float(value))
            except ValueError:
                print_error(f"timeout must be a number, got {value!r}")
                raise typer.Exit(1)
        elif key in ("quiet", "no_color"):
            if value.lower() in ("true", "1", "yes"):
                setattr(cfg, key, True)
            elif value.lower() in ("false", "0", "no"):
                setattr(cfg, key, False)
            else:
                print_error(f"{key} must be true or false, got {value!r}")
                raise typer.Exit(1)
        else:
            setattr(cfg, key, value)
    else:
        print_error(
            f"Unknown config key: {key!r}. "
            f"Valid keys: {', '.join(sorted(_TOP_LEVEL_KEYS))}, columns.ENDPOINT, preset.NAME, format.NAME, "
            f"bundle.NAME.flag, and batch.{{{','.join(sorted(_BATCH_KEYS))}}}"
        )
        raise typer.Exit(1)

    save_config(cfg)
    print_success(f"Set {key} = {value!r}  ({config_path()})")


@config_app.command("unset")
def config_unset_cmd(
    key: str = typer.Argument(..., help="Config key to remove. Use dot-notation for columns: columns.networks"),
) -> None:
    """Remove a config key, reverting it to its built-in default.

    Examples:

      dnsfcli config unset timeout
      dnsfcli config unset columns.networks
    """
    from .config import load_config, save_config, config_path
    cfg = load_config()

    _DEFAULTS: dict[str, Any] = {"profile": "default", "no_color": False, "quiet": False, "timeout": 30.0}

    if key.startswith("columns."):
        ep = key[len("columns."):]
        if ep not in cfg.columns:
            print_warning(f"columns.{ep} is not set — nothing to unset.")
            return
        del cfg.columns[ep]
    elif key.startswith("preset."):
        _preset_name = key[len("preset."):]
        if _preset_name not in cfg.column_presets:
            print_warning(f"preset.{_preset_name} is not set — nothing to unset.")
            return
        del cfg.column_presets[_preset_name]
    elif key.startswith("format."):
        _fmt_name = key[len("format."):]
        if _fmt_name not in cfg.format_presets:
            print_warning(f"format.{_fmt_name} is not set — nothing to unset.")
            return
        del cfg.format_presets[_fmt_name]
    elif key.startswith("bundle."):
        _bnd_parts = key[len("bundle."):].split(".", 1)
        if len(_bnd_parts) < 2 or not _bnd_parts[0] or not _bnd_parts[1]:
            print_error("bundle key must be bundle.NAME.flag, e.g. bundle.audit.columns")
            raise typer.Exit(1)
        _bnd_name, _bnd_flag = _bnd_parts
        if _bnd_name not in cfg.bundles or _bnd_flag not in cfg.bundles[_bnd_name]:
            print_warning(f"bundle.{_bnd_name}.{_bnd_flag} is not set — nothing to unset.")
            return
        del cfg.bundles[_bnd_name][_bnd_flag]
        if not cfg.bundles[_bnd_name]:
            del cfg.bundles[_bnd_name]
    elif key in _DEFAULTS:
        setattr(cfg, key, _DEFAULTS[key])
    else:
        print_error(
            f"Unknown config key: {key!r}. "
            f"Valid keys: {', '.join(sorted(_DEFAULTS))}, columns.ENDPOINT, preset.NAME, format.NAME, and bundle.NAME.flag"
        )
        raise typer.Exit(1)

    save_config(cfg)
    print_success(f"Unset {key}  ({config_path()})")


@config_app.command("reset")
def config_reset_cmd(
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt."),
) -> None:
    """Reset the config file to built-in defaults by deleting it.

    All settings will revert to their defaults on the next run.
    Credential profiles stored in the keychain are not affected.
    """
    from .config import config_path as _cpath
    _cp = _cpath()
    if not _cp.exists():
        console.print("[dim]No config file found — already at defaults.[/dim]")
        return
    if not yes:
        typer.confirm(f"Delete config file at {_cp}?", abort=True)
    _cp.unlink()
    print_success(f"Config reset — deleted {_cp}")


@config_app.command("export")
def config_export_cmd(
    out: str = typer.Option(..., "--out", "-o", help="Output JSON file path."),
) -> None:
    """Export the current config to a portable JSON snapshot."""
    import json as _json
    from .config import load_config as _lc
    from pathlib import Path as _Path
    cfg = _lc()
    data = {
        "defaults": {
            "profile": cfg.profile,
            "no_color": cfg.no_color,
            "quiet": cfg.quiet,
            "timeout": cfg.timeout,
        },
        "columns": {ep: ",".join(cols) for ep, cols in cfg.columns.items()},
    }
    _Path(out).parent.mkdir(parents=True, exist_ok=True)
    _Path(out).write_text(_json.dumps(data, indent=2), encoding="utf-8")
    print_success(f"Config exported to {out}")


@config_app.command("import")
def config_import_cmd(
    src: str = typer.Argument(..., help="JSON file previously created by 'config export'."),
    merge: bool = typer.Option(False, "--merge", "-m", help="Merge into existing config rather than replacing it."),
) -> None:
    """Import config from a JSON file created by 'config export'."""
    import json as _json
    from pathlib import Path as _Path
    from .config import load_config as _lc, save_config as _sc, config_path as _cfgp, Config as _Config
    try:
        data = _json.loads(_Path(src).read_text(encoding="utf-8"))
    except (OSError, _json.JSONDecodeError) as exc:
        print_error(f"Cannot read {src}: {exc}")
        raise typer.Exit(1)

    if merge:
        cfg = _lc()
        defaults = data.get("defaults", {})
        if "profile" in defaults:
            cfg.profile = str(defaults["profile"])
        if "no_color" in defaults:
            cfg.no_color = bool(defaults["no_color"])
        if "quiet" in defaults:
            cfg.quiet = bool(defaults["quiet"])
        if "timeout" in defaults:
            cfg.timeout = float(defaults["timeout"])
        for ep, cols_str in data.get("columns", {}).items():
            cfg.columns[ep] = [c.strip() for c in str(cols_str).split(",") if c.strip()]
    else:
        try:
            cfg = _Config.from_dict(data)
        except Exception as exc:
            print_error(f"Invalid config format in {src}: {exc}")
            raise typer.Exit(1)

    _sc(cfg)
    print_success(f"Config imported from {src}  ({_cfgp()})")


# ---------------------------------------------------------------------------
# Alias sub-app
# ---------------------------------------------------------------------------

def _alias_path() -> "Path":
    from .config import config_path as _cp
    return _cp().parent / "aliases.toml"


def _load_aliases() -> dict[str, str]:
    import tomllib
    p = _alias_path()
    if not p.exists():
        return {}
    try:
        with open(p, "rb") as fh:
            data = tomllib.load(fh)
        return {k: str(v) for k, v in data.get("aliases", {}).items()}
    except Exception:
        return {}


def _save_aliases(aliases: dict[str, str]) -> None:
    p = _alias_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    lines = ["[aliases]\n"]
    for name, cmd in sorted(aliases.items()):
        # TOML basic string — escape backslashes and double-quotes
        escaped = cmd.replace("\\", "\\\\").replace('"', '\\"')
        lines.append(f'{name} = "{escaped}"\n')
    p.write_text("".join(lines), encoding="utf-8")
    os.chmod(p, 0o600)


alias_app = typer.Typer(help="Manage saved command aliases.", rich_markup_mode="rich")
app.add_typer(alias_app, name="alias")


@alias_app.command("set")
def alias_set(
    name: str = typer.Argument(..., help="Alias name (no spaces)."),
    command: str = typer.Argument(..., help="Command to save, e.g. 'networks list --filter status=active'."),
) -> None:
    """Save a command as a named alias.

    Example:

      dnsfcli alias set active-nets "networks list --filter status=active --columns id,name"
    """
    if " " in name:
        print_error("Alias name must not contain spaces.")
        raise typer.Exit(1)
    aliases = _load_aliases()
    existed = name in aliases
    aliases[name] = command
    _save_aliases(aliases)
    verb = "Updated" if existed else "Saved"
    print_success(f"{verb} alias [bold]{name}[/bold] → {command}")


@alias_app.command("list")
def alias_list() -> None:
    """List all saved aliases."""
    aliases = _load_aliases()
    if not aliases:
        console.print("[dim]No aliases saved. Use [bold]dnsfcli alias set NAME COMMAND[/bold] to create one.[/dim]")
        return
    from rich.table import Table as _Table
    tbl = _Table(show_header=True, header_style="bold cyan")
    tbl.add_column("Name", no_wrap=True)
    tbl.add_column("Command")
    for name, cmd in sorted(aliases.items()):
        tbl.add_row(name, cmd)
    console.print(tbl)
    console.print(f"[dim]Stored in: {_alias_path()}[/dim]")


@alias_app.command("delete")
def alias_delete(
    name: str = typer.Argument(..., help="Alias name to remove."),
) -> None:
    """Delete a saved alias."""
    aliases = _load_aliases()
    if name not in aliases:
        print_error(f"No alias named '{name}'.")
        raise typer.Exit(1)
    del aliases[name]
    _save_aliases(aliases)
    print_success(f"Deleted alias [bold]{name}[/bold].")


@alias_app.command("run")
def alias_run(
    name: str = typer.Argument(..., help="Alias name to run."),
    extra: list[str] = typer.Argument(None, help="Additional flags appended to the alias command."),
) -> None:
    """Run a saved alias, optionally adding extra flags.

    Example:

      dnsfcli alias run active-nets --limit 10
    """
    import shlex
    aliases = _load_aliases()
    if name not in aliases:
        print_error(f"No alias named '{name}'. Run [bold]dnsfcli alias list[/bold] to see available aliases.")
        raise typer.Exit(1)

    stored = aliases[name]
    alias_args = shlex.split(stored) + (list(extra) if extra else [])

    if len(alias_args) < 2:
        print_error(f"Alias '{name}' expands to {stored!r}, which needs at least an endpoint and function.")
        raise typer.Exit(1)

    ep, fn, remaining_args = alias_args[0], alias_args[1], alias_args[2:]
    cmd = _make_dynamic_command(ep, fn)
    try:
        cmd.main(args=remaining_args, standalone_mode=True)
    except SystemExit as exc:
        sys.exit(exc.code)


# ---------------------------------------------------------------------------
# history sub-app
# ---------------------------------------------------------------------------

history_app = typer.Typer(help="Browse and replay the full API call history.", rich_markup_mode="rich")
app.add_typer(history_app, name="history")


@history_app.command("show")
def history_show_cmd(
    last: int = typer.Option(30, "--last", "-n", help="Show the N most recent entries."),
    since: Optional[str] = typer.Option(None, "--since", help="Only show entries on or after this date (YYYY-MM-DD)."),
    endpoint: Optional[str] = typer.Option(None, "--endpoint", "-e", help="Filter by endpoint name."),
    method: Optional[str] = typer.Option(None, "--method", "-m", help="Filter by HTTP method (GET, POST, …)."),
) -> None:
    """Show a compact history of all recent API calls (reads and writes).

    Uses a full history log (reads + writes), unlike [bold]dnsfcli audit show[/bold]
    which tracks write operations only.
    """
    from .audit import history_path, read_history

    since_ts = f"{since}T00:00:00Z" if since else None
    events = read_history(last=last, since=since_ts, endpoint_filter=endpoint)

    if method:
        events = [e for e in events if e.get("method", "").upper() == method.upper()]

    if not events:
        console.print(f"[dim]No history entries found. Log: {history_path()}[/dim]")
        return

    tbl = Table(show_header=True, header_style="bold cyan")
    tbl.add_column("#", style="dim", no_wrap=True, justify="right")
    tbl.add_column("Timestamp", style="dim", no_wrap=True)
    tbl.add_column("Org")
    tbl.add_column("Command")
    tbl.add_column("Method", no_wrap=True)
    tbl.add_column("Status")

    for idx, e in enumerate(events, start=1):
        status = str(e.get("status", ""))
        status_style = "green" if str(status).startswith("2") else "red"
        if e.get("error"):
            status = f"{status} ✗"
        ep = e.get("endpoint", "")
        fn = e.get("function", "")
        tbl.add_row(
            str(idx),
            e.get("ts", ""),
            str(e.get("org_id") or ""),
            f"[bold]{ep}[/bold] {fn}",
            e.get("method", ""),
            f"[{status_style}]{status}[/{status_style}]",
        )

    console.print(tbl)
    console.print(f"[dim]Log: {history_path()}[/dim]")


@history_app.command("redo")
def history_redo_cmd(
    n: int = typer.Argument(1, help="History entry to re-run (1 = most recent)."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt."),
) -> None:
    """Re-run a previous API call from history.

    N is the row number shown by [bold]dnsfcli history show[/bold] (1 = most recent).

    Examples:

      dnsfcli history redo 1        # replay the most recent call
      dnsfcli history redo 3 --yes  # replay entry 3 without confirming
    """
    import shlex
    import subprocess
    from .audit import read_history

    events = read_history(last=n)
    if len(events) < n:
        print_error(f"History entry {n} not found (only {len(events)} entries available).")
        raise typer.Exit(1)

    entry = events[n - 1]
    argv = entry.get("argv")
    if not argv:
        print_error(
            f"History entry {n} has no stored command (it was recorded by an older version of dnsfcli).\n"
            "Run a new command first, then use [bold]history redo[/bold]."
        )
        raise typer.Exit(1)

    cmd_str = "dnsfcli " + " ".join(shlex.quote(a) for a in argv)
    console.print(f"[bold]Replay:[/bold] [cyan]{cmd_str}[/cyan]")
    console.print(f"  [dim]Recorded: {entry.get('ts', '?')}  org: {entry.get('org_id') or 'n/a'}[/dim]")

    if not yes:
        typer.confirm("Run this command?", abort=True)

    result = subprocess.run([sys.executable, "-m", "dnsfcli"] + argv)  # type: ignore[list-item]
    raise typer.Exit(result.returncode)


@history_app.command("search")
def history_search_cmd(
    query: str = typer.Argument(..., help="Search string matched against endpoint, function, path, and stored argv."),
    last: int = typer.Option(200, "--last", "-n", help="Limit search to the N most recent history entries (default 200)."),
) -> None:
    """Search history entries by endpoint, function, path, or stored command tokens.

    Examples:

      dnsfcli history search networks

      dnsfcli history search "--org-id 42"
    """
    from .audit import read_history, history_path

    events = read_history(last=last)
    lq = query.lower()
    matches = [
        e for e in events
        if lq in str(e.get("endpoint", "")).lower()
        or lq in str(e.get("function", "")).lower()
        or lq in str(e.get("path", "")).lower()
        or any(lq in str(a).lower() for a in (e.get("argv") or []))
    ]

    if not matches:
        console.print(f"[dim]No history entries matching {query!r}.[/dim]")
        return

    tbl = Table(show_header=True, header_style="bold cyan")
    tbl.add_column("Timestamp", style="dim", no_wrap=True)
    tbl.add_column("Org")
    tbl.add_column("Command")
    tbl.add_column("Status")

    for e in matches:
        status = str(e.get("status", ""))
        status_style = "green" if str(status).startswith("2") else "red"
        ep = e.get("endpoint", "")
        fn = e.get("function", "")
        tbl.add_row(
            e.get("ts", ""),
            str(e.get("org_id") or ""),
            f"[bold]{ep}[/bold] {fn}",
            f"[{status_style}]{status}[/{status_style}]",
        )

    console.print(tbl)
    console.print(f"[dim]{len(matches)} match(es) — Log: {history_path()}[/dim]")


@history_app.command("clear")
def history_clear_cmd(
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt."),
) -> None:
    """Delete the full history log and its rotation backup."""
    from .audit import clear_history, history_path
    if not yes:
        typer.confirm(f"Delete history log at {history_path()}?", abort=True)
    clear_history()
    print_success("History log cleared.")


@history_app.command("export")
def history_export_cmd(
    out: str = typer.Option(..., "--out", "-o", help="Output CSV file path."),
    last: int = typer.Option(1000, "--last", "-n", help="Export the N most recent entries (default 1000)."),
    since: Optional[str] = typer.Option(None, "--since", help="Only export entries on or after this date (YYYY-MM-DD)."),
    endpoint: Optional[str] = typer.Option(None, "--endpoint", "-e", help="Filter by endpoint name."),
) -> None:
    """Export the history log to a CSV file.

    Examples:

      dnsfcli history export --out history.csv

      dnsfcli history export --out history.csv --since 2025-01-01 --endpoint networks
    """
    from .audit import read_history
    import csv as _csv

    since_ts = f"{since}T00:00:00Z" if since else None
    events = read_history(last=last, since=since_ts, endpoint_filter=endpoint)

    if not events:
        console.print("[dim]No history entries to export.[/dim]")
        return

    fields = ["ts", "org_id", "endpoint", "function", "method", "path", "status", "error", "argv"]
    import pathlib as _pl
    _pl.Path(out).parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", newline="", encoding="utf-8") as fh:
        w = _csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for evt in events:
            row = dict(evt)
            if isinstance(row.get("argv"), list):
                row["argv"] = " ".join(row["argv"])
            w.writerow(row)
    print_success(f"Exported {len(events)} entry(ies) to {out}")


@history_app.command("stats")
def history_stats_cmd(
    last: int = typer.Option(1000, "--last", "-n", help="Analyze the N most recent history entries."),
) -> None:
    """Show usage statistics from the history log: top endpoints, error rate, hourly activity."""
    from .audit import read_history, history_path
    from collections import Counter

    events = read_history(last=last)
    if not events:
        console.print("[dim]No history entries found.[/dim]")
        return

    total = len(events)
    errors = sum(
        1 for e in events
        if e.get("error") or (isinstance(e.get("status"), int) and e.get("status", 0) >= 400)
    )
    endpoint_counts: Counter = Counter(
        f"{e.get('endpoint', '?')} {e.get('function', '?')}" for e in events
    )
    method_counts: Counter = Counter(e.get("method", "?") for e in events)
    hour_counts: Counter = Counter(e.get("ts", "")[:13] for e in events if e.get("ts"))

    console.print(f"\n[bold]History Stats[/bold]  [dim](last {total} entries — {history_path()})[/dim]\n")

    from rich.table import Table as _ST

    summary = _ST(show_header=False, box=None, padding=(0, 3))
    summary.add_column("Label", style="bold cyan", no_wrap=True)
    summary.add_column("Value", justify="right")
    summary.add_row("Total requests", str(total))
    summary.add_row("Errors / non-2xx", f"{errors} ({100 * errors / total:.1f}%)")
    for method, cnt in sorted(method_counts.items()):
        summary.add_row(f"  {method}", str(cnt))
    console.print(summary)

    tbl = _ST(title="Top Endpoints", header_style="bold cyan", title_style="bold", box=None)
    tbl.add_column("Endpoint · Function", overflow="fold")
    tbl.add_column("Count", justify="right")
    tbl.add_column("%", justify="right")
    for ep, cnt in endpoint_counts.most_common(15):
        tbl.add_row(ep, str(cnt), f"{100 * cnt / total:.1f}%")
    console.print(tbl)

    if hour_counts:
        recent = sorted(hour_counts.items())[-24:]
        activity = _ST(title="Hourly Activity (most recent)", header_style="bold cyan", title_style="bold", box=None)
        activity.add_column("Hour (UTC)")
        activity.add_column("Count", justify="right")
        activity.add_column("Bar")
        max_cnt = max(c for _, c in recent) or 1
        for hour, cnt in recent:
            bar = "█" * int(20 * cnt / max_cnt)
            activity.add_row(hour, str(cnt), f"[cyan]{bar}[/cyan]")
        console.print(activity)


# ---------------------------------------------------------------------------
# diff command
# ---------------------------------------------------------------------------


@app.command("diff")
def diff_cmd(
    before: str = typer.Option(..., "--before", "-b", help="Before snapshot JSON file (from --to-json)."),
    after: str = typer.Option(..., "--after", "-a", help="After snapshot JSON file (from --to-json)."),
    key: str = typer.Option("id", "--key", "-k", help="Field to use as unique identifier for matching items."),
    show_unchanged: bool = typer.Option(False, "--unchanged", help="Also show items that are identical in both snapshots."),
) -> None:
    """Compare two API snapshots and show what changed.

    Snapshots are JSON files produced by [bold]--to-json[/bold].

    Examples:

      dnsfcli networks list --to-json before.json
      # ... make changes ...
      dnsfcli networks list --to-json after.json
      dnsfcli diff --before before.json --after after.json
    """
    import json as _json
    from rich.panel import Panel

    def _load(filepath: str) -> Any:
        try:
            with open(filepath, encoding="utf-8") as fh:
                data = _json.load(fh)
        except FileNotFoundError:
            print_error(f"File not found: {filepath}")
            raise typer.Exit(1)
        except _json.JSONDecodeError as exc:
            print_error(f"Invalid JSON in {filepath}: {exc}")
            raise typer.Exit(1)
        return _unwrap(data)

    before_data = _load(before)
    after_data  = _load(after)

    # ── Dict comparison (single objects) ─────────────────────────────────────
    if isinstance(before_data, dict) and isinstance(after_data, dict):
        all_keys = sorted(set(before_data) | set(after_data))
        added = [k for k in all_keys if k not in before_data]
        removed = [k for k in all_keys if k not in after_data]
        changed = [k for k in all_keys if k in before_data and k in after_data and before_data[k] != after_data[k]]
        unchanged = [k for k in all_keys if k in before_data and k in after_data and before_data[k] == after_data[k]]

        if not added and not removed and not changed:
            console.print("[green]No differences found.[/green]")
            return

        tbl = Table(show_header=True, header_style="bold cyan")
        tbl.add_column("Field", no_wrap=True)
        tbl.add_column("Change")
        tbl.add_column("Before", overflow="fold")
        tbl.add_column("After",  overflow="fold")

        for k in added:
            tbl.add_row(k, "[green]+[/green]", "[dim]—[/dim]", str(after_data[k])[:80])
        for k in removed:
            tbl.add_row(k, "[red]−[/red]", str(before_data[k])[:80], "[dim]—[/dim]")
        for k in changed:
            tbl.add_row(k, "[yellow]~[/yellow]", str(before_data[k])[:80], str(after_data[k])[:80])
        if show_unchanged:
            for k in unchanged:
                tbl.add_row(k, "[dim]=[/dim]", str(before_data[k])[:80], str(after_data[k])[:80])

        console.print(Panel(tbl, title=f"[bold]Diff: {before} → {after}[/bold]", expand=False))
        summary_parts = []
        if added:
            summary_parts.append(f"[green]{len(added)} added[/green]")
        if removed:
            summary_parts.append(f"[red]{len(removed)} removed[/red]")
        if changed:
            summary_parts.append(f"[yellow]{len(changed)} changed[/yellow]")
        console.print("  ".join(summary_parts))
        return

    # ── List comparison (arrays of objects) ──────────────────────────────────
    if not isinstance(before_data, list):
        before_data = [before_data]
    if not isinstance(after_data, list):
        after_data = [after_data]

    before_map: dict[str, dict] = {}
    after_map:  dict[str, dict] = {}

    for item in before_data:
        if isinstance(item, dict):
            k = str(item.get(key, id(item)))
            before_map[k] = item

    for item in after_data:
        if isinstance(item, dict):
            k = str(item.get(key, id(item)))
            after_map[k] = item

    all_keys_set = sorted(set(before_map) | set(after_map))

    added_items:   list[dict] = []
    removed_items: list[dict] = []
    changed_pairs: list[tuple[dict, dict]] = []
    unchanged_items: list[dict] = []

    for k in all_keys_set:
        if k not in before_map:
            added_items.append(after_map[k])
        elif k not in after_map:
            removed_items.append(before_map[k])
        elif before_map[k] != after_map[k]:
            changed_pairs.append((before_map[k], after_map[k]))
        else:
            unchanged_items.append(before_map[k])

    if not added_items and not removed_items and not changed_pairs:
        console.print("[green]No differences found.[/green]")
        if unchanged_items:
            console.print(f"[dim]{len(unchanged_items)} item(s) unchanged.[/dim]")
        return

    # Determine display columns from all involved items
    _all_items = added_items + removed_items + [b for b, _ in changed_pairs] + [a for _, a in changed_pairs]
    _cols: list[str] = []
    _seen_cols: set[str] = set()
    for item in _all_items:
        for col in item:
            if col not in _seen_cols:
                _seen_cols.add(col)
                _cols.append(col)
    _cols = _cols[:10]  # cap for readability

    if added_items:
        tbl = Table(title=f"[green]+ Added ({len(added_items)})[/green]", header_style="bold green", show_header=True)
        for col in _cols:
            tbl.add_column(str(col), overflow="fold", max_width=40)
        for item in added_items:
            tbl.add_row(*[str(item.get(col, ""))[:40] for col in _cols])
        console.print(tbl)

    if removed_items:
        tbl = Table(title=f"[red]− Removed ({len(removed_items)})[/red]", header_style="bold red", show_header=True)
        for col in _cols:
            tbl.add_column(str(col), overflow="fold", max_width=40)
        for item in removed_items:
            tbl.add_row(*[str(item.get(col, ""))[:40] for col in _cols])
        console.print(tbl)

    if changed_pairs:
        for b_item, a_item in changed_pairs:
            item_key = str(b_item.get(key, "?"))
            diff_keys = [c for c in set(list(b_item) + list(a_item)) if b_item.get(c) != a_item.get(c)]
            tbl = Table(title=f"[yellow]~ Changed {key}={item_key}[/yellow]", header_style="bold yellow", show_header=True)
            tbl.add_column("Field",  style="bold", no_wrap=True)
            tbl.add_column("Before", overflow="fold")
            tbl.add_column("After",  overflow="fold")
            for dk in sorted(diff_keys):
                tbl.add_row(dk, str(b_item.get(dk, ""))[:60], str(a_item.get(dk, ""))[:60])
            console.print(tbl)

    if show_unchanged and unchanged_items:
        console.print(f"[dim]{len(unchanged_items)} item(s) unchanged.[/dim]")

    summary_parts = []
    if added_items:
        summary_parts.append(f"[green]+{len(added_items)} added[/green]")
    if removed_items:
        summary_parts.append(f"[red]−{len(removed_items)} removed[/red]")
    if changed_pairs:
        summary_parts.append(f"[yellow]~{len(changed_pairs)} changed[/yellow]")
    console.print("  ".join(summary_parts))


@app.command("compare")
def compare_cmd(
    endpoint: str = typer.Argument(..., help="API endpoint (e.g. networks, policies)."),
    function: str = typer.Argument("list", help="Endpoint function to call (default: list)."),
    profile_a: str = typer.Option(..., "--profile-a", "-A", help="First credential profile."),
    profile_b: str = typer.Option(..., "--profile-b", "-B", help="Second credential profile."),
    key: str = typer.Option("id", "--key", "-k", help="Field to use as unique identifier for matching."),
    show_unchanged: bool = typer.Option(False, "--unchanged", help="Also show items that are identical in both profiles."),
    ctx: typer.Context = typer.Option(None, is_eager=False, expose_value=False),
) -> None:
    """Fetch the same endpoint from two profiles and diff the results.

    Useful for comparing configurations across environments or organizations.

    Examples:

      dnsfcli compare networks list --profile-a prod --profile-b staging
      dnsfcli compare policies list --profile-a org1 --profile-b org2 --key name
    """
    import re as _re_cmp
    from rich.panel import Panel

    operation = get_operation(endpoint, function)

    def _fetch(profile: str) -> list[Any]:
        _key = get_api_key(profile=profile)
        if not _key:
            print_error(f"No API key found for profile {profile!r}.")
            raise typer.Exit(1)
        _base = _re_cmp.sub(r"/v\d+/*$", "", get_base_url(profile=profile).rstrip("/"))
        _org = get_org_id(profile=profile)
        path, _ = _build_path(operation.path_template, {})
        _q: dict[str, Any] = {}
        if _org and any(p.name == "organization_id" for p in operation.params):
            _q["organization_id"] = _org
        try:
            with DNSFilterClient(api_key=_key, base_url=_base, org_id=_org) as _cl:
                _result = _cl.request(operation.method, path, params=_q or None)
        except APIError as exc:
            print_error(f"Error fetching {endpoint} {function} from profile {profile!r}: {exc}")
            raise typer.Exit(1)
        _unwrapped = _unwrap(_result)
        if isinstance(_unwrapped, list):
            return _unwrapped
        if isinstance(_unwrapped, dict):
            return [_unwrapped]
        return []

    console.print(f"[dim]Fetching [bold]{endpoint} {function}[/bold] from profile [bold]{profile_a}[/bold]...[/dim]")
    data_a = _fetch(profile_a)
    console.print(f"[dim]Fetching [bold]{endpoint} {function}[/bold] from profile [bold]{profile_b}[/bold]...[/dim]")
    data_b = _fetch(profile_b)

    before_map: dict[str, dict] = {}
    after_map: dict[str, dict] = {}

    for item in data_a:
        if isinstance(item, dict):
            k = str(item.get(key, id(item)))
            before_map[k] = item

    for item in data_b:
        if isinstance(item, dict):
            k = str(item.get(key, id(item)))
            after_map[k] = item

    all_keys_set = sorted(set(before_map) | set(after_map))

    added_items:     list[dict] = []
    removed_items:   list[dict] = []
    changed_pairs:   list[tuple[dict, dict]] = []
    unchanged_items: list[dict] = []

    for k in all_keys_set:
        if k not in before_map:
            added_items.append(after_map[k])
        elif k not in after_map:
            removed_items.append(before_map[k])
        elif before_map[k] != after_map[k]:
            changed_pairs.append((before_map[k], after_map[k]))
        else:
            unchanged_items.append(before_map[k])

    if not added_items and not removed_items and not changed_pairs:
        console.print("[green]No differences found.[/green]")
        if unchanged_items:
            console.print(f"[dim]{len(unchanged_items)} item(s) identical across both profiles.[/dim]")
        return

    _all_items = added_items + removed_items + [b for b, _ in changed_pairs] + [a for _, a in changed_pairs]
    _cols: list[str] = []
    _seen_cols: set[str] = set()
    for _item in _all_items:
        for col in _item:
            if col not in _seen_cols:
                _seen_cols.add(col)
                _cols.append(col)
    _cols = _cols[:10]

    if added_items:
        tbl = Table(title=f"[green]+ Only in {profile_b} ({len(added_items)})[/green]", header_style="bold green", show_header=True)
        for col in _cols:
            tbl.add_column(str(col), overflow="fold", max_width=40)
        for _item in added_items:
            tbl.add_row(*[str(_item.get(col, ""))[:40] for col in _cols])
        console.print(tbl)

    if removed_items:
        tbl = Table(title=f"[red]− Only in {profile_a} ({len(removed_items)})[/red]", header_style="bold red", show_header=True)
        for col in _cols:
            tbl.add_column(str(col), overflow="fold", max_width=40)
        for _item in removed_items:
            tbl.add_row(*[str(_item.get(col, ""))[:40] for col in _cols])
        console.print(tbl)

    if changed_pairs:
        for b_item, a_item in changed_pairs:
            item_key = str(b_item.get(key, "?"))
            diff_keys = [c for c in set(list(b_item) + list(a_item)) if b_item.get(c) != a_item.get(c)]
            tbl = Table(title=f"[yellow]~ {key}={item_key}[/yellow]", header_style="bold yellow", show_header=True)
            tbl.add_column("Field",  style="bold", no_wrap=True)
            tbl.add_column(profile_a, overflow="fold")
            tbl.add_column(profile_b, overflow="fold")
            for dk in sorted(diff_keys):
                tbl.add_row(dk, str(b_item.get(dk, ""))[:60], str(a_item.get(dk, ""))[:60])
            console.print(tbl)

    if show_unchanged and unchanged_items:
        console.print(f"[dim]{len(unchanged_items)} item(s) identical across both profiles.[/dim]")

    summary_parts = []
    if added_items:
        summary_parts.append(f"[green]+{len(added_items)} only in {profile_b}[/green]")
    if removed_items:
        summary_parts.append(f"[red]−{len(removed_items)} only in {profile_a}[/red]")
    if changed_pairs:
        summary_parts.append(f"[yellow]~{len(changed_pairs)} differ[/yellow]")
    console.print("  ".join(summary_parts))


# ---------------------------------------------------------------------------
# cache sub-commands
# ---------------------------------------------------------------------------

cache_app = typer.Typer(help="Manage the local response cache.", rich_markup_mode="rich")
app.add_typer(cache_app, name="cache")


@cache_app.command("clear")
def cache_clear_cmd(
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation."),
) -> None:
    """Delete all cached API responses."""
    from . import cache as _cache_mod
    d = _cache_mod.cache_dir()
    if not yes:
        typer.confirm(f"Delete all cached responses in {d}?", abort=True)
    _cache_mod.clear_all()
    print_success(f"Cache cleared: {d}")


@cache_app.command("show")
def cache_show_cmd() -> None:
    """Show the cache directory path and entry count."""
    from . import cache as _cache_mod
    d = _cache_mod.cache_dir()
    if not d.exists():
        console.print(f"[dim]Cache directory does not exist yet: {d}[/dim]")
        return
    entries = list(d.glob("*.json"))
    console.print(f"[bold]Cache directory:[/bold] [dim]{d}[/dim]")
    console.print(f"[bold]Cached entries:[/bold]  {len(entries)}")


# ---------------------------------------------------------------------------
# schema command — show operation details
# ---------------------------------------------------------------------------


@app.command("schema")
def schema_cmd(
    endpoint: str = typer.Argument(..., help="Endpoint name (e.g. networks, users)."),
    function: str = typer.Argument(..., help="Function name (e.g. list, show, create)."),
) -> None:
    """Show the schema (method, path, parameters) for an endpoint/function.

    Examples:

      dnsfcli schema networks list

      dnsfcli schema policies create
    """
    from .endpoints import get_operation
    from rich.panel import Panel

    try:
        op = get_operation(endpoint, function)
    except Exception:
        print_error(f"Unknown endpoint/function: {endpoint} {function}")
        console.print("[dim]Run [bold]dnsfcli endpoints[/bold] to list known endpoints.[/dim]")
        raise typer.Exit(1)

    tbl = Table(show_header=False, box=None, padding=(0, 2))
    tbl.add_column("Field", style="bold cyan", no_wrap=True, min_width=16)
    tbl.add_column("Value")
    tbl.add_row("Method",        f"[bold]{op.method}[/bold]")
    tbl.add_row("Path template", op.path_template)
    if op.description:
        tbl.add_row("Description", op.description)
    if op.body_key:
        tbl.add_row("Body key", op.body_key)
    if op.destructive:
        tbl.add_row("Destructive", "[red]yes[/red]")
    if op.poll_on:
        tbl.add_row("Poll on", op.poll_on)
    console.print(Panel(tbl, title=f"[bold]{endpoint} {function}[/bold]", expand=False))

    if op.params:
        param_tbl = Table(show_header=True, header_style="bold cyan")
        param_tbl.add_column("Name",        no_wrap=True)
        param_tbl.add_column("Kind",        no_wrap=True)
        param_tbl.add_column("Type",        no_wrap=True)
        param_tbl.add_column("Required",    no_wrap=True)
        param_tbl.add_column("Description", overflow="fold")
        for p in op.params:
            req_style = "green" if p.required else "dim"
            param_tbl.add_row(
                p.name,
                p.kind,
                p.type_hint,
                f"[{req_style}]{'yes' if p.required else 'no'}[/{req_style}]",
                p.description or "",
            )
        console.print(param_tbl)
    else:
        console.print("[dim]No parameters defined for this operation.[/dim]")


# ---------------------------------------------------------------------------
# env command — show recognized environment variables
# ---------------------------------------------------------------------------


@app.command("env")
def env_cmd() -> None:
    """Show all DNSF_* and DNSFCLI_* environment variables and their current values.

    Useful for diagnosing which settings are active in the current shell session.
    """
    import os

    ENV_VARS: list[tuple[str, str]] = [
        ("DNSF_API_KEY",          "API key for authentication (masked in output)"),
        ("DNSF_ORG_ID",           "Default organization ID"),
        ("DNSF_BASE_URL",         "API base URL override"),
        ("DNSF_PROFILE",          "Credential profile name"),
        ("DNSFCLI_COLUMNS",       "Default column list for output (comma-separated)"),
        ("DNSFCLI_TIMEOUT",       "Request timeout in seconds"),
        ("DNSFCLI_QUIET",         "Suppress non-error output (1/true)"),
        ("DNSFCLI_NO_COLOR",      "Disable ANSI colour output (1/true)"),
        ("DNSFCLI_CONCURRENCY",   "Parallel workers for batch operations"),
        ("DNSFCLI_CSV_DELIMITER", "Field delimiter for CSV input/output"),
        ("NO_COLOR",              "Disable ANSI colour output — standard convention"),
    ]

    tbl = Table(show_header=True, header_style="bold cyan")
    tbl.add_column("Variable",    no_wrap=True, style="bold")
    tbl.add_column("Value",       overflow="fold")
    tbl.add_column("Description", overflow="fold")

    for var, desc in ENV_VARS:
        val = os.environ.get(var)
        if val is None:
            val_str = "[dim](not set)[/dim]"
        elif "KEY" in var:
            val_str = f"[dim]{val[:6]}…{val[-4:]}[/dim]" if len(val) > 10 else "[dim]***[/dim]"
        else:
            val_str = val

        tbl.add_row(var, val_str, desc)

    console.print(tbl)
    console.print(f"\n[dim]Config file: {config_path()}[/dim]")


# ---------------------------------------------------------------------------
# Shell completion
# ---------------------------------------------------------------------------

completion_app = typer.Typer(help="Manage shell tab completion.", rich_markup_mode="rich")
app.add_typer(completion_app, name="completion")


@completion_app.command("show")
def completion_show(
    shell: str = typer.Argument("zsh", help="Shell type: zsh, bash, fish."),
) -> None:
    """Print the completion script for SHELL to stdout.

    Pipe it into your shell config or install it automatically with
    [bold]dnsfcli completion install[/bold].

    Example — one-shot activation for zsh:

      eval "$(dnsfcli completion show zsh)"
    """
    from typer._completion_shared import get_completion_script, Shells

    shell_lower = shell.lower()
    valid = {s.value for s in Shells}
    if shell_lower not in valid:
        print_error(f"Unsupported shell: {shell!r}. Choose from: {', '.join(sorted(valid))}")
        raise typer.Exit(1)

    prog_name = "dnsfcli"
    complete_var = f"_{prog_name.upper()}_COMPLETE"
    script = get_completion_script(prog_name=prog_name, complete_var=complete_var, shell=shell_lower)
    console.print(script, highlight=False, markup=False)


@completion_app.command("install")
def completion_install(
    shell: str = typer.Argument("zsh", help="Shell type: zsh, bash, fish."),
) -> None:
    """Install completion for SHELL and print where it was written.

    After installing, restart your terminal or source your shell config.

    Example:

      dnsfcli completion install zsh
    """
    from typer._completion_shared import install as typer_install, Shells

    shell_lower = shell.lower()
    valid = {s.value for s in Shells}
    if shell_lower not in valid:
        print_error(f"Unsupported shell: {shell!r}. Choose from: {', '.join(sorted(valid))}")
        raise typer.Exit(1)

    prog_name = "dnsfcli"
    complete_var = f"_{prog_name.upper()}_COMPLETE"
    detected_shell, path = typer_install(shell=shell_lower, prog_name=prog_name, complete_var=complete_var)
    print_success(f"{detected_shell} completion installed in {path}")
    console.print("[dim]Restart your terminal or source your shell config for it to take effect.[/dim]")


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
                op = REGISTRY[endpoint].operations[function]
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

    @click.command(
        name=function,
        cls=_GroupedCommand,
        context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
        help=f"Call {endpoint}/{function} on the DNSFilter API.",
    )
    @click.option("--raw", "-r", cls=_PanelOption, rich_help_panel="Output",
                  is_flag=True, default=False, help="Print raw JSON instead of formatted output.")
    @click.option("--json", "as_json", cls=_PanelOption, rich_help_panel="Output",
                  is_flag=True, default=False, help="Output clean JSON to stdout (no Rich formatting). Useful for piping to jq.")
    @click.option("--jsonl", "as_jsonl", cls=_PanelOption, rich_help_panel="Output",
                  is_flag=True, default=False, help="Output one JSON object per line (JSON Lines format), useful for piping to jq.")
    @click.option("--no-color", "no_color", cls=_PanelOption, rich_help_panel="Output",
                  is_flag=True, default=False, envvar="DNSFCLI_NO_COLOR",
                  help="Disable ANSI colour output.  [env: DNSFCLI_NO_COLOR]")
    @click.option("--quiet", "-q", "quiet", cls=_PanelOption, rich_help_panel="Output",
                  is_flag=True, default=False, envvar="DNSFCLI_QUIET",
                  help="Suppress non-error output.  [env: DNSFCLI_QUIET]")
    @click.option("--columns", "columns_str", cls=_PanelOption, rich_help_panel="Output",
                  default=None, metavar="COLS", envvar="DNSFCLI_COLUMNS",
                  help="Comma-separated list of columns to include in output.  [env: DNSFCLI_COLUMNS]")
    @click.option("--format", "format_template", cls=_PanelOption, rich_help_panel="Output",
                  default=None, metavar="TEMPLATE",
                  help=r"Format each result using a Go-style template. Example: --format '{{.id}}: {{.name}}'")
    @click.option("--pick", "pick_field", cls=_PanelOption, rich_help_panel="Output",
                  default=None, metavar="FIELD",
                  help="Extract a single field (dot-notation) and print one value per line.")
    @click.option("--sort", "sort_by", cls=_PanelOption, rich_help_panel="Output",
                  multiple=True, metavar="FIELD",
                  help="Sort results by FIELD (prefix with '-' for descending, e.g. -created_at). Repeatable for multi-field sort.")
    @click.option("--limit", "limit", cls=_PanelOption, rich_help_panel="Output",
                  default=None, type=int, metavar="N",
                  help="Cap results at N items (applied after --sort and --all pagination).")
    @click.option("--last", "last", cls=_PanelOption, rich_help_panel="Output",
                  default=None, type=int, metavar="N",
                  help="Keep only the last N items from the result list (applied after --sort).")
    @click.option("--sample", "sample", cls=_PanelOption, rich_help_panel="Output",
                  default=None, type=click.IntRange(min=1), metavar="N",
                  help="Show only the first N items client-side (after filters/sort, before output). Unlike --limit, does not affect the server query.")
    @click.option("--select", "select_fields_str", cls=_PanelOption, rich_help_panel="Output",
                  default=None, metavar="FIELDS",
                  help="Comma-separated fields to keep in each result object (inverse of --exclude).")
    @click.option("--exclude", "exclude_str", cls=_PanelOption, rich_help_panel="Output",
                  default=None, metavar="FIELDS",
                  help="Comma-separated list of fields to remove from each result object.")
    @click.option("--rename", "rename_fields", cls=_PanelOption, rich_help_panel="Output",
                  multiple=True, metavar="FROM=TO",
                  help="Rename a result field (repeatable). Example: --rename org_id=organization_id")
    @click.option("--group-by", "group_by", cls=_PanelOption, rich_help_panel="Output",
                  default=None, metavar="FIELD",
                  help="Aggregate list results into a count-per-value table grouped by FIELD.")
    @click.option("--sum", "sum_field", cls=_PanelOption, rich_help_panel="Output",
                  default=None, metavar="FIELD",
                  help="Sum the numeric values of FIELD across all results and print the total.")
    @click.option("--avg", "avg_field", cls=_PanelOption, rich_help_panel="Output",
                  default=None, metavar="FIELD",
                  help="Average the numeric values of FIELD across all results and print the mean.")
    @click.option("--min", "min_field", cls=_PanelOption, rich_help_panel="Output",
                  default=None, metavar="FIELD",
                  help="Print the minimum numeric value of FIELD across all results.")
    @click.option("--max", "max_field", cls=_PanelOption, rich_help_panel="Output",
                  default=None, metavar="FIELD",
                  help="Print the maximum numeric value of FIELD across all results.")
    @click.option("--map", "map_fields", cls=_PanelOption, rich_help_panel="Output",
                  multiple=True, metavar="FIELD=TRANSFORM",
                  help="Transform a result field value (repeatable). TRANSFORM: upper, lower, strip, title, truncate:N.")
    @click.option("--truncate", "truncate", cls=_PanelOption, rich_help_panel="Output",
                  default=None, type=int, metavar="N",
                  help="Truncate cell values to N characters in table output. Use -1 to disable truncation.")
    @click.option("--count", "count_only", cls=_PanelOption, rich_help_panel="Output",
                  is_flag=True, default=False,
                  help="Print only the number of results, not the results themselves.")
    @click.option("--filter", "filters", cls=_PanelOption, rich_help_panel="Filtering",
                  multiple=True, metavar="EXPR",
                  help="Client-side filter (repeatable, AND). "
                       "Forms: field=value  field!=value  field~substr  field>N  field<N  field>=N  field<=N.")
    @click.option("--grep", "grep", cls=_PanelOption, rich_help_panel="Filtering",
                  default=None, metavar="PATTERN",
                  help="Keep only results where any field value matches PATTERN (regex, case-insensitive).")
    @click.option("--unique", "unique_field", cls=_PanelOption, rich_help_panel="Filtering",
                  default=None, metavar="FIELD",
                  help="Deduplicate results, keeping the first item for each distinct value of FIELD.")
    @click.option("--page", "page", cls=_PanelOption, rich_help_panel="Pagination",
                  default=None, type=int, metavar="N",
                  help="Fetch a specific page number (server-side pagination).")
    @click.option("--page-size", "page_size", cls=_PanelOption, rich_help_panel="Pagination",
                  default=None, type=int, metavar="N",
                  help="Number of items per page (server-side pagination).")
    @click.option("--all", "fetch_all", cls=_PanelOption, rich_help_panel="Pagination",
                  is_flag=True, default=False,
                  help="Auto-paginate: fetch every page and combine all results.")
    @click.option("--to-csv", "csv_file", cls=_PanelOption, rich_help_panel="Export",
                  default=None, metavar="FILE",
                  help="Write results to FILE as CSV. Accepts any path the running user can access; "
                       "scripts constructing this path from external input must sanitize it first.")
    @click.option("--to-json", "json_file", cls=_PanelOption, rich_help_panel="Export",
                  default=None, metavar="FILE",
                  help="Write the unwrapped result as pretty-printed JSON to FILE.")
    @click.option("--append", "csv_append", cls=_PanelOption, rich_help_panel="Export",
                  is_flag=True, default=False,
                  help="Append to --to-csv file instead of overwriting (header is written only when file is empty).")
    @click.option("--no-header", "no_header", cls=_PanelOption, rich_help_panel="Export",
                  is_flag=True, default=False,
                  help="Omit the header row from CSV output (--to-csv / --to-csv -).")
    @click.option("--csv-header-case", "csv_header_case", cls=_PanelOption, rich_help_panel="Export",
                  default=None, type=click.Choice(["lower", "upper", "title"], case_sensitive=False),
                  help="Normalize CSV column names: lower (id, policy_id), upper (ID, POLICY_ID), title (Id, Policy_Id).")
    @click.option("--csv-delimiter", "csv_delimiter", cls=_PanelOption, rich_help_panel="Export",
                  default=",", metavar="CHAR", envvar="DNSFCLI_CSV_DELIMITER",
                  help="Field delimiter for CSV input/output (default: comma).  [env: DNSFCLI_CSV_DELIMITER]")
    @click.option("--from-csv", "csv_input", cls=_PanelOption, rich_help_panel="Batch",
                  default=None, metavar="FILE",
                  help="Read input rows from a CSV file (one API call per row). "
                       "Accepts any path the running user can access; "
                       "scripts constructing this path from external input must sanitize it first.")
    @click.option("--from-json", "json_input", cls=_PanelOption, rich_help_panel="Batch",
                  default=None, metavar="FILE|-",
                  help="Read a JSON array and execute one API call per element. Use '-' for stdin.")
    @click.option("--template", "show_template", cls=_PanelOption, rich_help_panel="Batch",
                  is_flag=True, default=False,
                  help="Print a blank CSV input template for this operation and exit.")
    @click.option("--plan", "show_plan", cls=_PanelOption, rich_help_panel="Batch",
                  is_flag=True, default=False,
                  help="Show a dry-run summary (calls, records, duration) without executing.")
    @click.option("--on-error", "on_error", cls=_PanelOption, rich_help_panel="Batch",
                  default=None, type=click.Choice(["continue", "stop", "report"], case_sensitive=False),
                  help="Batch error strategy: 'continue' keeps going and exits 1 if any row failed, 'stop' halts on first failure, 'report' processes all rows and always exits 0 (log failures, never break CI). Default: continue.")
    @click.option("--concurrency", "concurrency", cls=_PanelOption, rich_help_panel="Batch",
                  default=None, type=int, metavar="N", envvar="DNSFCLI_CONCURRENCY",
                  help="Parallel workers for --from-csv batch operations (default: 1).  [env: DNSFCLI_CONCURRENCY]")
    @click.option("--batch-size", "batch_size", cls=_PanelOption, rich_help_panel="Batch",
                  default=None, type=int, metavar="N",
                  help="Split --from-csv / --from-json input into chunks of N rows each.")
    @click.option("--retry", "retry", cls=_PanelOption, rich_help_panel="Batch",
                  default=None, type=int, metavar="N",
                  help="Retry failed batch rows up to N times (5xx errors only, exponential back-off). Default: 0.")
    @click.option("--errors-to-csv", "errors_csv", cls=_PanelOption, rich_help_panel="Batch",
                  default=None, metavar="FILE",
                  help="Write input rows that failed (after retries) to FILE for later reprocessing.")
    @click.option("--retry-errors-csv", "retry_errors_csv", cls=_PanelOption, rich_help_panel="Batch",
                  default=None, metavar="FILE",
                  help="Re-run only the failed rows from a previous --errors-to-csv FILE. Equivalent to --from-csv FILE but semantically signals a retry pass.")
    @click.option("--upsert", "upsert", cls=_PanelOption, rich_help_panel="Batch",
                  is_flag=True, default=False,
                  help="On POST: if the API returns 409 Conflict, automatically retry as PATCH on the existing resource.")
    @click.option("--max-errors", "max_errors", cls=_PanelOption, rich_help_panel="Batch",
                  default=None, type=int, metavar="N",
                  help="Stop batch processing after N cumulative failures (between --on-error continue and stop).")
    @click.option("--body-json", "body_json", cls=_PanelOption, rich_help_panel="Request",
                  default=None, metavar="JSON|@FILE",
                  help="Merge raw JSON into the request body. Prefix with '@' to read from a file.")
    @click.option("--set", "set_fields", cls=_PanelOption, rich_help_panel="Request",
                  multiple=True, metavar="FIELD=VALUE",
                  help="Set a single body field (repeatable). Shorthand for simple --body-json updates.")
    @click.option("--merge-key", "merge_key", cls=_PanelOption, rich_help_panel="Request",
                  default=None, metavar="FIELD",
                  help="Look up the resource id by matching FIELD against the list endpoint, then inject id.")
    @click.option("--dry-run", "dry_run", cls=_PanelOption, rich_help_panel="Request",
                  is_flag=True, default=False,
                  help="Print the resolved HTTP request (method, URL, body) without executing it.")
    @click.option("--wait", "wait", cls=_PanelOption, rich_help_panel="Request",
                  is_flag=True, default=False,
                  help="For async operations: poll until the job completes, then display the final result.")
    @click.option("--timing", "timing", cls=_PanelOption, rich_help_panel="Request",
                  is_flag=True, default=False,
                  help="Print request duration to stderr after each API call.")
    @click.option("--rate", "rate", cls=_PanelOption, rich_help_panel="Request",
                  default=None, type=float, metavar="REQ/S",
                  help="Override the client-side rate limit (requests per second). Default: 80%% of API limit.")
    @click.option("--timeout", "timeout", cls=_PanelOption, rich_help_panel="Request",
                  default=None, type=float, metavar="SECS", envvar="DNSFCLI_TIMEOUT",
                  help="Per-request read/write timeout in seconds.  [env: DNSFCLI_TIMEOUT]")
    @click.option("--cache-ttl", "cache_ttl", cls=_PanelOption, rich_help_panel="Request",
                  default=None, type=int, metavar="SECS",
                  help="Cache GET responses for SECS seconds (stored in ~/.cache/dnsfcli/).")
    @click.option("--env-file", "env_file", cls=_PanelOption, rich_help_panel="Auth / Profile",
                  default=None, metavar="FILE",
                  help="Load environment variables (DNSF_API_KEY, DNSF_ORG_ID, etc.) from a .env file before resolving credentials.")
    @click.option("--log-file", "log_file", cls=_PanelOption, rich_help_panel="Output",
                  default=None, metavar="FILE",
                  help="Append all warnings/errors/progress output to FILE instead of stderr (keeps stdout clean for piping).")
    @click.option("--stdin-json", "stdin_json", cls=_PanelOption, rich_help_panel="Request",
                  is_flag=True, default=False,
                  help="Read the full request body as JSON from stdin. Enables: cat payload.json | dnsfcli networks create --stdin-json.")
    @click.option("--watch", "watch_interval", cls=_PanelOption, rich_help_panel="Request",
                  default=None, type=click.IntRange(min=1), metavar="SECS",
                  help="Re-run this command every SECS seconds until interrupted (Ctrl-C). Minimum: 1.")
    @click.option("--watch-changes", "watch_changes_interval", cls=_PanelOption, rich_help_panel="Request",
                  default=None, type=click.IntRange(min=1), metavar="SECS",
                  help="Poll every SECS seconds and print only what changed (added/removed/updated rows). Minimum: 1.")
    @click.option("--max-pages", "max_pages", cls=_PanelOption, rich_help_panel="Pagination",
                  default=None, type=int, metavar="N",
                  help="Cap --all pagination at N pages (safety valve for large endpoints).")
    @click.option("--fields", "fields_only", cls=_PanelOption, rich_help_panel="Output",
                  is_flag=True, default=False,
                  help="Print available field names from the first result object and exit.")
    @click.option("--strip-nulls", "strip_nulls", cls=_PanelOption, rich_help_panel="Output",
                  is_flag=True, default=False,
                  help="Remove keys with null values from each result object before output.")
    @click.option("--save-as", "save_as", cls=_PanelOption, rich_help_panel="Options",
                  default=None, metavar="NAME",
                  help="Save the current command as a named alias after running it.")
    @click.option("--null-as", "null_as", cls=_PanelOption, rich_help_panel="Output",
                  default=None, metavar="STR",
                  help="Replace null (None) values with STR before output (e.g. --null-as N/A).")
    @click.option("--no-wrap", "no_wrap", cls=_PanelOption, rich_help_panel="Output",
                  is_flag=True, default=False,
                  help="Disable word-wrap in table cells (show full values in a wider table).")
    @click.option("--color-if", "color_rules_raw", cls=_PanelOption, rich_help_panel="Output",
                  multiple=True, metavar="FIELD:REGEX=STYLE",
                  help="Conditionally color rows where FIELD matches REGEX with the given Rich style. Repeatable.")
    @click.option("--count-by", "count_by", cls=_PanelOption, rich_help_panel="Output",
                  default=None, metavar="FIELD",
                  help="Show a frequency table for FIELD with a percentage column.")
    @click.option("--not-null", "not_null_field", cls=_PanelOption, rich_help_panel="Filtering",
                  default=None, metavar="FIELD",
                  help="Keep only rows where FIELD is not null.")
    @click.option("--is-null", "is_null_field", cls=_PanelOption, rich_help_panel="Filtering",
                  default=None, metavar="FIELD",
                  help="Keep only rows where FIELD is null.")
    @click.option("--since", "since_filter", cls=_PanelOption, rich_help_panel="Filtering",
                  default=None, metavar="FIELD DATE",
                  help="Shorthand for --filter FIELD>=DATE. Example: --since updated_at 2025-01-01")
    @click.option("--header", "extra_headers_raw", cls=_PanelOption, rich_help_panel="Request",
                  multiple=True, metavar="KEY=VALUE",
                  help="Add a custom HTTP request header (repeatable). Example: --header X-Trace-Id=abc")
    @click.option("--insecure", "insecure", cls=_PanelOption, rich_help_panel="Request",
                  is_flag=True, default=False,
                  help="Skip TLS certificate verification. Do not use in production.")
    @click.option("--no-progress", "no_progress", cls=_PanelOption, rich_help_panel="Options",
                  is_flag=True, default=False,
                  help="Disable progress bars for --all pagination and batch operations.")
    @click.option("--tee", "tee_file", cls=_PanelOption, rich_help_panel="Export",
                  default=None, metavar="FILE",
                  help="Write plain-text console output to FILE in addition to stdout.")
    @click.option("--output", "output_format", cls=_PanelOption, rich_help_panel="Output",
                  default=None, type=click.Choice(["table", "json", "jsonl", "raw", "csv", "none"], case_sensitive=False),
                  help="Unified output format: table (default), json, jsonl, raw, csv, or none (suppress all output, use exit code only).")
    @click.option("--validate-only", "validate_only", cls=_PanelOption, rich_help_panel="Batch",
                  is_flag=True, default=False,
                  help="Validate --from-csv / --from-json input rows without making any API calls.")
    @click.option("--confirm-each", "confirm_each", cls=_PanelOption, rich_help_panel="Batch",
                  is_flag=True, default=False,
                  help="Prompt for confirmation before processing each batch row.")
    @click.option("--diff-mode", "diff_mode", cls=_PanelOption, rich_help_panel="Batch",
                  is_flag=True, default=False,
                  help="Before each PATCH/PUT batch row, fetch the current resource state and show a field-change table.")
    @click.option("--skip-rows", "skip_rows", cls=_PanelOption, rich_help_panel="Batch",
                  default=0, type=int, metavar="N",
                  help="Skip the first N input rows from --from-csv / --from-json (e.g. to resume an interrupted batch).")
    @click.option("--max-rows", "max_rows", cls=_PanelOption, rich_help_panel="Batch",
                  default=None, type=click.IntRange(min=1), metavar="N",
                  help="Process at most N input rows from --from-csv / --from-json.")
    @click.option("--batch-report", "batch_report", cls=_PanelOption, rich_help_panel="Batch",
                  default=None, metavar="FILE",
                  help="Write a JSON summary of the batch run (per-row outcomes, counts) to FILE.")
    @click.option("--preset", "preset", cls=_PanelOption, rich_help_panel="Output",
                  default=None, metavar="NAME",
                  help="Apply a named column preset from config (column_presets.NAME). Overrides --columns.")
    @click.option("--format-preset", "format_preset", cls=_PanelOption, rich_help_panel="Output",
                  default=None, metavar="NAME",
                  help="Apply a named --format template from config (format_presets.NAME). Overrides --format.")
    @click.option("--add-field", "add_fields", cls=_PanelOption, rich_help_panel="Output",
                  multiple=True, metavar="FIELD=VALUE",
                  help="Inject a static FIELD=VALUE into every result item before output (repeatable).")
    @click.option("--paginate-until", "paginate_until", cls=_PanelOption, rich_help_panel="Pagination",
                  default=None, metavar="EXPR",
                  help="Stop --all pagination when any item on a page matches EXPR (same filter syntax as --filter).")
    @click.option("--org-csv", "org_csv", cls=_PanelOption, rich_help_panel="Auth / Profile",
                  default=None, metavar="FILE",
                  help="Supply the org list for --each-org from a CSV file (columns: id, name) instead of the API.")
    @click.option("--color-scale", "color_scale", cls=_PanelOption, rich_help_panel="Output",
                  default=None, metavar="FIELD[:asc|desc]",
                  help="Color rows by a numeric FIELD on a red→green gradient. Suffix :desc reverses (green=low).")
    @click.option("--parallel-orgs", "parallel_orgs", cls=_PanelOption, rich_help_panel="Auth / Profile",
                  is_flag=True, default=False,
                  help="Run --each-org concurrently instead of sequentially.")
    @click.option("--org-concurrency", "org_concurrency", cls=_PanelOption, rich_help_panel="Auth / Profile",
                  default=4, type=int, metavar="N",
                  help="Max parallel org workers when --parallel-orgs is set (default: 4).")
    @click.option("--org-filter", "org_filter", cls=_PanelOption, rich_help_panel="Auth / Profile",
                  default=None, metavar="REGEX",
                  help="Filter organizations by name regex when --each-org is used.")
    @click.option("--max-orgs", "max_orgs", cls=_PanelOption, rich_help_panel="Auth / Profile",
                  default=None, type=click.IntRange(min=1), metavar="N",
                  help="Cap --each-org at N organizations (useful for dry-runs before running across all orgs).")
    @click.option("--flatten", "flatten", cls=_PanelOption, rich_help_panel="Output",
                  is_flag=True, default=False,
                  help="Flatten nested dict objects to dot-notation keys before output.")
    @click.option("--strip-empties", "strip_empties", cls=_PanelOption, rich_help_panel="Output",
                  is_flag=True, default=False,
                  help="Remove keys with null, empty-string, empty-list, or empty-dict values (extends --strip-nulls).")
    @click.option("--csv-null", "csv_null_value", cls=_PanelOption, rich_help_panel="Export",
                  default=None, metavar="STR",
                  help="String to write in CSV cells when a value is null (default: empty string).")
    @click.option("--watch-until", "watch_until_filter", cls=_PanelOption, rich_help_panel="Request",
                  default=None, metavar="EXPR",
                  help="Stop --watch loop when any result matches EXPR (same syntax as --filter).")
    @click.option("--fail-on-empty", "fail_on_empty", cls=_PanelOption, rich_help_panel="Options",
                  is_flag=True, default=False,
                  help="Exit non-zero when the result list is empty. Useful for CI/monitoring scripts.")
    @click.option("--quiet-ok", "quiet_ok", cls=_PanelOption, rich_help_panel="Output",
                  is_flag=True, default=False,
                  help="Suppress normal output (table, success messages) but keep warnings and errors visible.")
    @click.option("--delay", "batch_delay", cls=_PanelOption, rich_help_panel="Batch",
                  default=None, type=int, metavar="MS",
                  help="Wait MS milliseconds between batch row API calls (sequential mode only).")
    @click.option("--connect-timeout", "connect_timeout", cls=_PanelOption, rich_help_panel="Request",
                  default=None, type=float, metavar="SECS",
                  help="TCP connect timeout in seconds (default: 10). Separate from read/write timeout.")
    @click.option("--proxy", "proxy", cls=_PanelOption, rich_help_panel="Request",
                  default=None, metavar="URL",
                  help="HTTP/HTTPS proxy URL (e.g. http://proxy.corp:8080).")
    @click.option("--jq", "jq_expr", cls=_PanelOption, rich_help_panel="Output",
                  default=None, metavar="PATH",
                  help="Extract a value via dot-separated path before output (e.g. data.0.attributes.name).")
    @click.option("--max-wait", "max_wait", cls=_PanelOption, rich_help_panel="Request",
                  default=None, type=float, metavar="SECS",
                  help="Abort --wait polling after this many seconds (default: unlimited).")
    @click.option("--watch-diff", "watch_diff", cls=_PanelOption, rich_help_panel="Request",
                  is_flag=True, default=False,
                  help="In --watch mode, print a summary of rows added/removed since the previous iteration.")
    @click.option("--alert", "alert_filter", cls=_PanelOption, rich_help_panel="Request",
                  default=None, metavar="EXPR",
                  help="Ring terminal bell + print banner when EXPR matches (same syntax as --filter). Continues watching.")
    @click.option("--table-style", "table_style", cls=_PanelOption, rich_help_panel="Output",
                  default=None, metavar="STYLE",
                  help="Rich table box style: rounded, simple, minimal, markdown, horizontals, heavy, double, ascii, none.")
    @click.option("--stats", "stats_field", cls=_PanelOption, rich_help_panel="Output",
                  default=None, metavar="FIELD",
                  help="Print min/max/mean/count for a numeric field in the result list.")
    @click.option("--api-key", cls=_PanelOption, rich_help_panel="Auth / Profile",
                  envvar="DNSF_API_KEY", default=None, help="Override stored API key.")
    @click.option("--org-id", cls=_PanelOption, rich_help_panel="Auth / Profile",
                  envvar="DNSF_ORG_ID", default=None, help="Override stored org ID.")
    @click.option("--profile", "profile", cls=_PanelOption, rich_help_panel="Auth / Profile",
                  default=None, metavar="PROFILE", envvar="DNSF_PROFILE",
                  help="Named credential profile to use (overrides active profile).")
    @click.option("--org-name", "org_name", cls=_PanelOption, rich_help_panel="Auth / Profile",
                  default=None, metavar="PATTERN",
                  help="Resolve an organization by name (regex) instead of --org-id.")
    @click.option("--each-org", "each_org", cls=_PanelOption, rich_help_panel="Auth / Profile",
                  is_flag=True, default=False,
                  help="Repeat the command for every organization in the account, printing a header per org.")
    @click.option("--verbose", "-v", cls=_PanelOption, rich_help_panel="Options",
                  is_flag=True, default=False, help="Show request URL and body.")
    @click.option("--yes", "-y", "skip_confirm", cls=_PanelOption, rich_help_panel="Options",
                  is_flag=True, default=False,
                  help="Skip confirmation prompt for destructive operations.")
    @click.option("--fail-on-pattern", "fail_on_pattern", cls=_PanelOption, rich_help_panel="Options",
                  default=None, metavar="EXPR",
                  help="Exit non-zero if any result item matches EXPR (same filter syntax as --filter).")
    @click.option("--filter-mode", "filter_mode", cls=_PanelOption, rich_help_panel="Filtering",
                  default="and", type=click.Choice(["and", "or"], case_sensitive=False),
                  help="Combine multiple --filter expressions with AND (default) or OR logic.")
    @click.option("--to-markdown", "to_markdown", cls=_PanelOption, rich_help_panel="Export",
                  default=None, metavar="FILE",
                  help="Write results as a GFM Markdown table to FILE (use '-' for stdout).")
    @click.option("--output-schema", "output_schema", cls=_PanelOption, rich_help_panel="Output",
                  is_flag=True, default=False,
                  help="Print field names, types, and sample values from the response then exit.")
    @click.option("--exec", "exec_cmd", cls=_PanelOption, rich_help_panel="Output",
                  default=None, metavar="CMD",
                  help="Run CMD for each result item with {field} or $field substitution (e.g. --exec 'curl -X POST http://hook/$id').")
    @click.option("--transform", "transforms", cls=_PanelOption, rich_help_panel="Output",
                  multiple=True, metavar="FIELD=EXPR",
                  help="Add or overwrite FIELD by evaluating EXPR against each item (e.g. --transform ratio=blocked/total). Repeatable.")
    @click.option("--join", "join_spec", cls=_PanelOption, rich_help_panel="Filtering",
                  default=None, metavar="ENDPOINT:LOCAL=REMOTE",
                  help="Client-side join: fetch ENDPOINT and attach matching records as a nested field (e.g. --join policies:policy_id=id).")
    @click.option("--bundle", "bundle", cls=_PanelOption, rich_help_panel="Options",
                  default=None, metavar="NAME",
                  help="Apply a named flag bundle from config [bundles.NAME] as defaults (CLI flags override bundle values).")
    @click.pass_context
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
            from .audit import _SECRET_FLAGS as _ALIAS_SECRET_FLAGS
            _raw_argv = sys.argv[1:]
            _alias_tokens: list[str] = []
            _dropped_secrets = False
            _ax = 0
            while _ax < len(_raw_argv):
                _tok = _raw_argv[_ax]
                if _tok == "--save-as" and _ax + 1 < len(_raw_argv):
                    _ax += 2
                elif _tok in _ALIAS_SECRET_FLAGS and _ax + 1 < len(_raw_argv):
                    _dropped_secrets = True
                    _ax += 2
                elif any(_tok.startswith(f"{f}=") for f in _ALIAS_SECRET_FLAGS):
                    _dropped_secrets = True
                    _ax += 1
                else:
                    _alias_tokens.append(_tok)
                    _ax += 1
            if _dropped_secrets:
                print_warning(
                    "Secret-bearing flags (--api-key/--header/--proxy) were not saved "
                    "with the alias. Configure credentials via 'dnsfcli auth setup' or "
                    "environment variables so the alias works when re-run."
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
                ctx, endpoint, function,
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
            )

        def _expand_org_path(path: str | None, org_id: str, org_name: str) -> str | None:
            if path is None:
                return None
            return path.replace("{org_id}", org_id).replace("{org_name}", org_name)

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
                        _eo_raw = _eo_cl.get("/v1/organizations")
                    _eo_orgs = _unwrap(_eo_raw)
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
            if parallel_orgs:
                from concurrent.futures import ThreadPoolExecutor, as_completed as _as_completed
                import threading as _threading
                _print_lock = _threading.Lock()

                def _run_org_parallel(org_item: Any) -> None:
                    _oid = str(org_item.get("id", ""))
                    _attrs = org_item.get("attributes") or {}
                    _oname = _attrs.get("name") or org_item.get("name") or f"Org {_oid}"
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

                with ThreadPoolExecutor(max_workers=max(1, org_concurrency)) as _pool:
                    _futs = [_pool.submit(_run_org_parallel, org) for org in _eo_orgs]
                    for _fut in _as_completed(_futs):
                        try:
                            _fut.result()
                        except Exception as _e:
                            print_error(f"--parallel-orgs worker error: {_e}")
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
                    _time.sleep(watch_interval)
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

    return _cmd


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
    # or looks like a flag, hand off to Typer/Click unchanged.
    if not args or args[0].startswith("-") or args[0] in static_commands:
        app()
        return

    # First arg is an endpoint; second (if non-flag) is the function.
    endpoint = args[0]

    # Direct alias invocation: `dnsfcli NAME [args]` where NAME is a saved
    # alias (and not a real endpoint, which always takes precedence).
    if endpoint not in list_endpoints():
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
