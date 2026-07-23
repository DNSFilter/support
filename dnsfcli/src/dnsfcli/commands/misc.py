"""dnsfcli `misc` command group (extracted from cli.py)."""

from __future__ import annotations

import json
import sys
from typing import Optional

import typer
from rich.panel import Panel
from rich.table import Table

from ..apps import app, completion_app
from ..auth import get_active_profile, get_api_key, get_base_url, get_org_id
from ..client import APIError, DNSFilterClient
from ..cliparams import _api_key_flag_on_cli
from ..config import config_path
from ..endpoints import get_operation, list_endpoints, list_functions
from ..output import console, print_error, print_success, print_warning
from ..postprocess import _enrich_domain_result


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
        from ..endpoints import REGISTRY
        for name in eps:
            ep = REGISTRY[name]
            fns = ", ".join(sorted(ep.operations.keys()))
            table.add_row(name, fns)
        console.print(table)
        console.print("\n[dim]Run [bold]dnsfcli ENDPOINT[/bold] to list one endpoint's functions.[/dim]")

@app.command("doctor")
def doctor(
    profile: Optional[str] = typer.Option(None, "--profile", "-p", envvar="DNSF_PROFILE", help="Profile to check (default: active profile)."),
) -> None:
    """Check credentials, connectivity, and configuration.

    Runs a series of non-destructive checks and reports their status.
    Exits 0 when all checks pass, 1 otherwise.
    """
    from .. import __version__
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
    from ..endpoints import get_operation
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
