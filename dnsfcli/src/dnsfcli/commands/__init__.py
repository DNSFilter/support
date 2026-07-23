"""dnsfcli sub-command groups.

Importing this package imports every command module, whose module-level
Typer decorators register the handlers onto the shared app objects in
apps.py. cli.py imports this package for exactly that side effect.
"""

from . import auth, audit, config, alias, history, diff, cache, misc  # noqa: F401

__all__ = ["auth", "audit", "config", "alias", "history", "diff", "cache", "misc"]
