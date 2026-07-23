"""dnsfcli `audit` command group (extracted from cli.py)."""

from __future__ import annotations

from typing import Optional

import typer
from rich.table import Table

from ..apps import audit_app
from ..audit import clear_log, log_path, read_events
from ..output import console, print_success


@audit_app.command("show")
def audit_show(
    last: int = typer.Option(20, "--last", "-n", help="Show the N most recent events."),
    since: Optional[str] = typer.Option(None, "--since", help="Only show events on or after this date (YYYY-MM-DD)."),
    endpoint: Optional[str] = typer.Option(None, "--endpoint", "-e", help="Filter by endpoint name."),
) -> None:
    """Display recent write operations from the audit log."""
    from ..audit import log_path, read_events
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
    from ..audit import clear_log, log_path
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
    from ..audit import read_events
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
