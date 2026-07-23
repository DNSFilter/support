"""Dry-run and plan previews, and destructive/batch confirmations.

These render what WOULD happen (or ask the user to confirm) without sending
any write request.
"""

from __future__ import annotations

import sys
from typing import Any

import typer
from rich.table import Table

from .jobs import _estimate_duration
from .output import console

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

    from .audit import mask_secret_keys

    tbl = Table(show_header=False, box=None, padding=(0, 2), expand=False)
    tbl.add_column("Field", style="bold cyan", min_width=12, no_wrap=True)
    tbl.add_column("Value", overflow="fold")

    tbl.add_row("Method", f"[bold]{method}[/bold]")
    tbl.add_row("URL",    f"{base_url}{path}")
    if query_params:
        # Redact secret-named params so a dry-run (which also flows to --tee) never
        # writes a secret to the terminal/file; non-secret fields show in full.
        tbl.add_row("Query",  str(mask_secret_keys(query_params)))
    if json_body:
        tbl.add_row("Body",   _json.dumps(mask_secret_keys(json_body), indent=2, default=str))

    console.print(Panel(tbl, title="[bold]Dry Run — no request sent[/bold]", expand=False))
    console.print("\n[dim]Remove [bold]--dry-run[/bold] to execute.[/dim]")


def _dry_run_batch_preview(
    rows: list[dict[str, Any]],
    operation: Any,
    endpoint: str,
    function: str,
    source: str,
) -> None:
    """Preview a batch write under --dry-run and send NOTHING."""
    from rich.panel import Panel
    n = len(rows)
    tbl = Table(show_header=False, box=None, padding=(0, 2), expand=False)
    tbl.add_column("Field", style="bold cyan", min_width=12, no_wrap=True)
    tbl.add_column("Value", overflow="fold")
    tbl.add_row("Operation", f"[bold]{operation.method}[/bold] {operation.path_template}")
    tbl.add_row("Command",   f"{endpoint} {function}")
    tbl.add_row("Source",    str(source))
    tbl.add_row("Rows",      f"{n} — would send {n} request(s)")
    if rows:
        import json as _json
        tbl.add_row("First row", _json.dumps(rows[0], indent=2, default=str))
    console.print(Panel(tbl, title="[bold]Dry Run — no requests sent[/bold]", expand=False))
    console.print("\n[dim]Remove [bold]--dry-run[/bold] to execute.[/dim]")


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
            from .csv_io import read_csv_input
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
