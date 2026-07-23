"""dnsfcli `diff` command group (extracted from cli.py)."""

from __future__ import annotations

from typing import Any

import typer
from rich.panel import Panel
from rich.table import Table

from ..apps import app
from ..auth import get_api_key, get_base_url, get_org_id
from ..client import APIError, DNSFilterClient
from ..cliparams import _build_path
from ..endpoints import get_operation
from ..output import _unwrap, console, print_error


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
