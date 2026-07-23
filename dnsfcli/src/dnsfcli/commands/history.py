"""dnsfcli `history` command group (extracted from cli.py)."""

from __future__ import annotations

import sys
from typing import Optional

import typer
from rich.table import Table

from ..apps import history_app
from ..audit import clear_history, history_path, read_history
from ..output import console, print_error, print_success


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
    from ..audit import history_path, read_history

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
    from ..audit import read_history

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
    from ..audit import read_history, history_path

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
    from ..audit import clear_history, history_path
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
    from ..audit import read_history
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
    from ..audit import read_history, history_path
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
