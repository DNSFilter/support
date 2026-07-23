"""dnsfcli `alias` command group (extracted from cli.py)."""

from __future__ import annotations

import os
import sys

import typer

from ..apps import alias_app
from ..output import console, print_error, print_success


def _alias_path() -> "Path":
    from ..config import config_path as _cp
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
    # Atomic write (temp 0600 + os.replace): a crash mid-write must not leave a
    # truncated aliases.toml, which _load_aliases would silently discard.
    tmp = p.with_name(f"{p.name}.{os.getpid()}.tmp")
    try:
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            os.chmod(tmp, 0o600)
            fh.write("".join(lines))
        os.replace(tmp, p)
    finally:
        try:
            tmp.unlink()
        except FileNotFoundError:
            pass

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
    # Imported lazily to avoid an import cycle: cli.py imports the command
    # modules for registration, so this module can't import cli at load time.
    from ..cli import _make_dynamic_command
    cmd = _make_dynamic_command(ep, fn)
    try:
        cmd.main(args=remaining_args, standalone_mode=True)
    except SystemExit as exc:
        sys.exit(exc.code)
