"""dnsfcli `config` command group (extracted from cli.py)."""

from __future__ import annotations

import os
from typing import Any

import typer

from ..apps import config_app
from ..config import config_path, load_config, save_config, write_private_text
from ..output import console, print_error, print_success, print_warning


@config_app.command("show")
def config_show() -> None:
    """Display the current configuration (file values + active path)."""
    from rich.table import Table as _Table
    cfg = load_config()
    path = config_path()
    console.print(f"[bold]Config file:[/bold] [dim]{path}[/dim] {'[green](exists)[/green]' if path.exists() else '[dim](not found — using defaults)[/dim]'}\n")
    tbl = _Table(show_header=False, box=None, padding=(0, 2))
    tbl.add_column("Key", style="bold cyan", no_wrap=True, min_width=16)
    tbl.add_column("Value")
    tbl.add_row("profile",  cfg.profile)
    tbl.add_row("timeout",  str(cfg.timeout))
    tbl.add_row("quiet",    str(cfg.quiet))
    tbl.add_row("no_color", str(cfg.no_color))
    if cfg.columns:
        for ep, cols in cfg.columns.items():
            tbl.add_row(f"columns.{ep}", ", ".join(cols))
    if cfg.column_presets:
        for name, cols in cfg.column_presets.items():
            tbl.add_row(f"preset.{name}", ", ".join(cols))
    if cfg.format_presets:
        for name, tmpl in cfg.format_presets.items():
            tbl.add_row(f"format.{name}", tmpl)
    if cfg.bundles:
        for bname, bvals in cfg.bundles.items():
            for bk, bv in bvals.items():
                tbl.add_row(f"bundle.{bname}.{bk}", str(bv))
    console.print(tbl)

@config_app.command("init")
def config_init(
    force: bool = typer.Option(False, "--force", "-f", help="Overwrite an existing config file without prompting."),
) -> None:
    """Scaffold a starter config.toml with commented documentation.

    Writes to the standard config path and opens it for editing.
    Run [bold]dnsfcli config show[/bold] to see the current path.
    """
    path = config_path()
    if path.exists() and not force:
        typer.confirm(f"Config file already exists at {path}. Overwrite?", abort=True)

    path.parent.mkdir(parents=True, exist_ok=True)

    template = """\
# dnsfcli configuration file
# Location: {path}
#
# All values are optional — dnsfcli works without this file.
# CLI flags and environment variables (DNSF_*, DNSFCLI_*) take precedence.

[defaults]
# Named credential profile to use when --profile is not supplied.
# profile = "default"

# Per-request read/write timeout in seconds.
# timeout = 30.0

# Suppress non-error output globally (same as --quiet on every call).
# quiet = false

# Disable ANSI colour output globally (same as --no-color or NO_COLOR env var).
# no_color = false

# Per-endpoint default column lists — override with --columns on the CLI.
# [columns]
# networks  = "id,name,status,policy_id"
# users     = "id,email,role"
# policies  = "id,name,type"

# Named column presets — use with --preset NAME on any command.
# [column_presets]
# compact   = "id,name,status"
# detailed  = "id,name,status,created_at,updated_at"

# Named format templates — use with --format-preset NAME on any command.
# [format_presets]
# summary  = "{{name}} ({{status}})"
# oneline  = "{{id}}  {{name}}"

# Command bundles — store a combination of flags as a named preset.
# Use with --bundle NAME on any command.
# Supported keys: columns, format, format_preset, sort, filter, filter_mode.
# [bundles.active]
# filter      = "status=active"
# sort        = "-created_at"
# columns     = "id,name,status,created_at"
# format_preset = "summary"

# Default settings for batch (--from-csv) operations.
# All values can be overridden per-command with the corresponding CLI flags.
# [batch]
# concurrency = 1          # number of parallel workers
# retry       = 0          # per-row retry attempts on transient errors
# on_error    = "continue" # "continue", "stop", or "report"
# max_errors  = 10         # abort after this many cumulative errors (omit for unlimited)
# batch_size  = 100        # chunk rows into groups of this size (omit to disable)
""".format(path=path)

    write_private_text(path, template)  # 0600 from creation; may hold secrets in [bundles]
    print_success(f"Config file created at {path}")
    console.print(f"[dim]Edit it with your preferred editor, then run [bold]dnsfcli config show[/bold] to verify.[/dim]")

@config_app.command("edit")
def config_edit() -> None:
    """Open the config file in $VISUAL / $EDITOR (falls back to vi).

    Creates the file with starter content first if it doesn't exist yet.
    """
    import subprocess as _sp
    path = config_path()
    if not path.exists():
        console.print(f"[dim]Config file not found — creating starter config at {path}[/dim]")
        path.parent.mkdir(parents=True, exist_ok=True)
        write_private_text(
            path,
            "# dnsfcli configuration\n[defaults]\n# profile = \"default\"\n# timeout = 30.0\n",
        )
    editor = os.environ.get("VISUAL") or os.environ.get("EDITOR") or "vi"
    _sp.run([editor, str(path)])

@config_app.command("set")
def config_set_cmd(
    key: str = typer.Argument(..., help="Config key to set. Use dot-notation for columns: columns.networks"),
    value: str = typer.Argument(..., help="Value to set. Booleans: true/false. For columns: comma-separated list."),
) -> None:
    """Set a config value without editing the file directly.

    Examples:

      dnsfcli config set timeout 60
      dnsfcli config set quiet true
      dnsfcli config set profile production
      dnsfcli config set columns.networks id,name,status,policy_id
    """
    from ..config import load_config, save_config, config_path
    cfg = load_config()

    _TOP_LEVEL_KEYS = {"profile", "no_color", "quiet", "timeout"}
    _BATCH_KEYS = {"concurrency", "retry", "on_error", "max_errors", "batch_size"}

    if key.startswith("columns."):
        ep = key[len("columns."):]
        if not ep:
            print_error("columns key must be columns.ENDPOINT, e.g. columns.networks")
            raise typer.Exit(1)
        cfg.columns[ep] = [c.strip() for c in value.split(",") if c.strip()]
    elif key.startswith("preset."):
        _preset_name = key[len("preset."):]
        if not _preset_name:
            print_error("preset key must be preset.NAME, e.g. preset.compact")
            raise typer.Exit(1)
        cfg.column_presets[_preset_name] = [c.strip() for c in value.split(",") if c.strip()]
    elif key.startswith("format."):
        _fmt_name = key[len("format."):]
        if not _fmt_name:
            print_error("format key must be format.NAME, e.g. format.summary")
            raise typer.Exit(1)
        cfg.format_presets[_fmt_name] = value
    elif key.startswith("bundle."):
        _bnd_parts = key[len("bundle."):].split(".", 1)
        if len(_bnd_parts) < 2 or not _bnd_parts[0] or not _bnd_parts[1]:
            print_error("bundle key must be bundle.NAME.flag, e.g. bundle.audit.columns")
            raise typer.Exit(1)
        _bnd_name, _bnd_flag = _bnd_parts
        if _bnd_name not in cfg.bundles:
            cfg.bundles[_bnd_name] = {}
        cfg.bundles[_bnd_name][_bnd_flag] = value
    elif key.startswith("batch."):
        bk = key[len("batch."):]
        if bk not in _BATCH_KEYS:
            print_error(
                f"Unknown batch key: {bk!r}. Valid batch keys: {', '.join(sorted(_BATCH_KEYS))}"
            )
            raise typer.Exit(1)
        if bk in ("concurrency", "retry"):
            try:
                setattr(cfg.batch, bk, int(value))
            except ValueError:
                print_error(f"batch.{bk} must be an integer, got {value!r}")
                raise typer.Exit(1)
        elif bk in ("max_errors", "batch_size"):
            if value.lower() in ("none", "null", ""):
                setattr(cfg.batch, bk, None)
            else:
                try:
                    setattr(cfg.batch, bk, int(value))
                except ValueError:
                    print_error(f"batch.{bk} must be an integer or 'none', got {value!r}")
                    raise typer.Exit(1)
        else:  # on_error
            if value not in ("continue", "stop", "report"):
                print_error(f"batch.on_error must be 'continue', 'stop', or 'report', got {value!r}")
                raise typer.Exit(1)
            cfg.batch.on_error = value
    elif key in _TOP_LEVEL_KEYS:
        if key == "timeout":
            try:
                setattr(cfg, key, float(value))
            except ValueError:
                print_error(f"timeout must be a number, got {value!r}")
                raise typer.Exit(1)
        elif key in ("quiet", "no_color"):
            if value.lower() in ("true", "1", "yes"):
                setattr(cfg, key, True)
            elif value.lower() in ("false", "0", "no"):
                setattr(cfg, key, False)
            else:
                print_error(f"{key} must be true or false, got {value!r}")
                raise typer.Exit(1)
        else:
            setattr(cfg, key, value)
    else:
        print_error(
            f"Unknown config key: {key!r}. "
            f"Valid keys: {', '.join(sorted(_TOP_LEVEL_KEYS))}, columns.ENDPOINT, preset.NAME, format.NAME, "
            f"bundle.NAME.flag, and batch.{{{','.join(sorted(_BATCH_KEYS))}}}"
        )
        raise typer.Exit(1)

    save_config(cfg)
    print_success(f"Set {key} = {value!r}  ({config_path()})")

@config_app.command("unset")
def config_unset_cmd(
    key: str = typer.Argument(..., help="Config key to remove. Use dot-notation for columns: columns.networks"),
) -> None:
    """Remove a config key, reverting it to its built-in default.

    Examples:

      dnsfcli config unset timeout
      dnsfcli config unset columns.networks
    """
    from ..config import load_config, save_config, config_path
    cfg = load_config()

    _DEFAULTS: dict[str, Any] = {"profile": "default", "no_color": False, "quiet": False, "timeout": 30.0}

    if key.startswith("columns."):
        ep = key[len("columns."):]
        if ep not in cfg.columns:
            print_warning(f"columns.{ep} is not set — nothing to unset.")
            return
        del cfg.columns[ep]
    elif key.startswith("preset."):
        _preset_name = key[len("preset."):]
        if _preset_name not in cfg.column_presets:
            print_warning(f"preset.{_preset_name} is not set — nothing to unset.")
            return
        del cfg.column_presets[_preset_name]
    elif key.startswith("format."):
        _fmt_name = key[len("format."):]
        if _fmt_name not in cfg.format_presets:
            print_warning(f"format.{_fmt_name} is not set — nothing to unset.")
            return
        del cfg.format_presets[_fmt_name]
    elif key.startswith("bundle."):
        _bnd_parts = key[len("bundle."):].split(".", 1)
        if len(_bnd_parts) < 2 or not _bnd_parts[0] or not _bnd_parts[1]:
            print_error("bundle key must be bundle.NAME.flag, e.g. bundle.audit.columns")
            raise typer.Exit(1)
        _bnd_name, _bnd_flag = _bnd_parts
        if _bnd_name not in cfg.bundles or _bnd_flag not in cfg.bundles[_bnd_name]:
            print_warning(f"bundle.{_bnd_name}.{_bnd_flag} is not set — nothing to unset.")
            return
        del cfg.bundles[_bnd_name][_bnd_flag]
        if not cfg.bundles[_bnd_name]:
            del cfg.bundles[_bnd_name]
    elif key in _DEFAULTS:
        setattr(cfg, key, _DEFAULTS[key])
    else:
        print_error(
            f"Unknown config key: {key!r}. "
            f"Valid keys: {', '.join(sorted(_DEFAULTS))}, columns.ENDPOINT, preset.NAME, format.NAME, and bundle.NAME.flag"
        )
        raise typer.Exit(1)

    save_config(cfg)
    print_success(f"Unset {key}  ({config_path()})")

@config_app.command("reset")
def config_reset_cmd(
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt."),
) -> None:
    """Reset the config file to built-in defaults by deleting it.

    All settings will revert to their defaults on the next run.
    Credential profiles stored in the keychain are not affected.
    """
    from ..config import config_path as _cpath
    _cp = _cpath()
    if not _cp.exists():
        console.print("[dim]No config file found — already at defaults.[/dim]")
        return
    if not yes:
        typer.confirm(f"Delete config file at {_cp}?", abort=True)
    _cp.unlink()
    print_success(f"Config reset — deleted {_cp}")

@config_app.command("export")
def config_export_cmd(
    out: str = typer.Option(..., "--out", "-o", help="Output JSON file path."),
) -> None:
    """Export the current config to a portable JSON snapshot."""
    import json as _json
    from ..config import load_config as _lc
    from pathlib import Path as _Path
    cfg = _lc()
    data = {
        "defaults": {
            "profile": cfg.profile,
            "no_color": cfg.no_color,
            "quiet": cfg.quiet,
            "timeout": cfg.timeout,
        },
        "columns": {ep: ",".join(cols) for ep, cols in cfg.columns.items()},
    }
    _Path(out).parent.mkdir(parents=True, exist_ok=True)
    _Path(out).write_text(_json.dumps(data, indent=2), encoding="utf-8")
    print_success(f"Config exported to {out}")

@config_app.command("import")
def config_import_cmd(
    src: str = typer.Argument(..., help="JSON file previously created by 'config export'."),
    merge: bool = typer.Option(False, "--merge", "-m", help="Merge into existing config rather than replacing it."),
) -> None:
    """Import config from a JSON file created by 'config export'."""
    import json as _json
    from pathlib import Path as _Path
    from ..config import load_config as _lc, save_config as _sc, config_path as _cfgp, Config as _Config
    try:
        data = _json.loads(_Path(src).read_text(encoding="utf-8"))
    except (OSError, _json.JSONDecodeError) as exc:
        print_error(f"Cannot read {src}: {exc}")
        raise typer.Exit(1)

    if merge:
        cfg = _lc()
        defaults = data.get("defaults", {})
        if "profile" in defaults:
            cfg.profile = str(defaults["profile"])
        if "no_color" in defaults:
            cfg.no_color = bool(defaults["no_color"])
        if "quiet" in defaults:
            cfg.quiet = bool(defaults["quiet"])
        if "timeout" in defaults:
            cfg.timeout = float(defaults["timeout"])
        for ep, cols_str in data.get("columns", {}).items():
            cfg.columns[ep] = [c.strip() for c in str(cols_str).split(",") if c.strip()]
    else:
        try:
            cfg = _Config.from_dict(data)
        except Exception as exc:
            print_error(f"Invalid config format in {src}: {exc}")
            raise typer.Exit(1)

    _sc(cfg)
    print_success(f"Config imported from {src}  ({_cfgp()})")
