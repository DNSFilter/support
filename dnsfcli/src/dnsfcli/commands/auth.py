"""dnsfcli `auth` command group (extracted from cli.py)."""

from __future__ import annotations

from typing import Optional

import typer
from rich.table import Table

from ..apps import auth_app
from ..auth import clear_all, clear_profile, credentials_summary, get_active_profile, get_api_key, get_base_url, get_org_id, list_profiles, set_active_profile, store_api_key, store_base_url, store_org_id
from ..client import APIError, DNSFilterClient
from ..output import console, err_console, print_error, print_success, print_warning


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
                from ..auth import store_last_verified as _slv
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
            from ..auth import store_last_verified as _slv_single
            _slv_single(profile=effective_profile)
            print_success(f"Credentials are valid (profile: {effective_profile}, {_ms}ms).")
        except APIError as exc:
            print_error(f"Verification failed: {exc}")
            raise typer.Exit(code=1)

@auth_app.command("list")
def auth_list() -> None:
    """List all configured credential profiles."""
    from ..auth import get_last_verified as _glv
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
    from ..auth import get_last_verified as _glv_exp

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
    from ..auth import get_api_key as _get_key, get_org_id as _get_org, get_base_url as _get_base
    from ..auth import store_api_key as _store_key, store_org_id as _store_org, store_base_url as _store_base

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
