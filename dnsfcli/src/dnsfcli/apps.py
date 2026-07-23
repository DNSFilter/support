"""Typer application objects for dnsfcli.

Defined in one place so the command modules (commands/*.py) can register
their handlers onto the shared sub-apps without importing cli.py — which
would create an import cycle, since cli.py imports the command modules for
their registration side effects.
"""

from __future__ import annotations

import typer

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

config_app = typer.Typer(help="Manage the dnsfcli configuration file.", rich_markup_mode="rich")
app.add_typer(config_app, name="config")

alias_app = typer.Typer(help="Manage saved command aliases.", rich_markup_mode="rich")
app.add_typer(alias_app, name="alias")

history_app = typer.Typer(help="Browse and replay the full API call history.", rich_markup_mode="rich")
app.add_typer(history_app, name="history")

cache_app = typer.Typer(help="Manage the local response cache.", rich_markup_mode="rich")
app.add_typer(cache_app, name="cache")

completion_app = typer.Typer(help="Manage shell tab completion.", rich_markup_mode="rich")
app.add_typer(completion_app, name="completion")
