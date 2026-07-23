"""dnsfcli `cache` command group (extracted from cli.py)."""

from __future__ import annotations


import typer

from ..apps import cache_app
from ..output import console, print_success


@cache_app.command("clear")
def cache_clear_cmd(
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation."),
) -> None:
    """Delete all cached API responses."""
    from .. import cache as _cache_mod
    d = _cache_mod.cache_dir()
    if not yes:
        typer.confirm(f"Delete all cached responses in {d}?", abort=True)
    _cache_mod.clear_all()
    print_success(f"Cache cleared: {d}")

@cache_app.command("show")
def cache_show_cmd() -> None:
    """Show the cache directory path and entry count."""
    from .. import cache as _cache_mod
    d = _cache_mod.cache_dir()
    if not d.exists():
        console.print(f"[dim]Cache directory does not exist yet: {d}[/dim]")
        return
    entries = list(d.glob("*.json"))
    console.print(f"[bold]Cache directory:[/bold] [dim]{d}[/dim]")
    console.print(f"[bold]Cached entries:[/bold]  {len(entries)}")
