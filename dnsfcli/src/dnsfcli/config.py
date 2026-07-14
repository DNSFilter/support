"""User configuration file support.

Config file location (first found wins):
  $XDG_CONFIG_HOME/dnsfcli/config.toml   (if XDG_CONFIG_HOME is set)
  ~/.config/dnsfcli/config.toml           (default)

Example config.toml:

    [defaults]
    profile  = "production"
    no_color = false
    quiet    = false
    timeout  = 30.0

    # Per-endpoint default column lists — override with --columns on the CLI.
    [columns]
    networks  = "id,name,status,policy_id"
    users     = "id,email,role"
    policies  = "id,name,type"

Config values are overridden by environment variables, which are overridden by
CLI flags.
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class BatchDefaults:
    concurrency: int       = 1
    retry:       int       = 0
    on_error:    str       = "continue"
    max_errors:  int | None = None
    batch_size:  int | None = None


@dataclass
class Config:
    profile:  str   = "default"
    no_color: bool  = False
    quiet:    bool  = False
    timeout:  float = 30.0
    # Per-endpoint column defaults keyed by endpoint name.
    columns:         dict[str, list[str]]       = field(default_factory=dict)
    column_presets:  dict[str, list[str]]       = field(default_factory=dict)
    format_presets:  dict[str, str]             = field(default_factory=dict)
    bundles:         dict[str, dict[str, Any]]  = field(default_factory=dict)
    batch:           BatchDefaults              = field(default_factory=BatchDefaults)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Config":
        defaults = data.get("defaults", {})
        columns_raw = data.get("columns", {})
        columns: dict[str, list[str]] = {
            ep: [c.strip() for c in v.split(",") if c.strip()]
            for ep, v in columns_raw.items()
        }
        presets_raw = data.get("column_presets", {})
        column_presets: dict[str, list[str]] = {
            name: [c.strip() for c in v.split(",") if c.strip()]
            for name, v in presets_raw.items()
        }
        format_presets: dict[str, str] = {
            name: str(v)
            for name, v in data.get("format_presets", {}).items()
        }
        bundles_raw = data.get("bundles", {})
        bundles: dict[str, dict[str, Any]] = {
            name: dict(val) if isinstance(val, dict) else {}
            for name, val in bundles_raw.items()
        }
        batch_raw = data.get("batch", {})
        batch = BatchDefaults(
            concurrency = int(batch_raw.get("concurrency", 1)),
            retry       = int(batch_raw.get("retry", 0)),
            on_error    = str(batch_raw.get("on_error", "continue")),
            max_errors  = int(batch_raw["max_errors"]) if "max_errors" in batch_raw else None,
            batch_size  = int(batch_raw["batch_size"]) if "batch_size" in batch_raw else None,
        )
        return cls(
            profile         = str(defaults.get("profile", "default")),
            no_color        = bool(defaults.get("no_color", False)),
            quiet           = bool(defaults.get("quiet", False)),
            timeout         = float(defaults.get("timeout", 30.0)),
            columns         = columns,
            column_presets  = column_presets,
            format_presets  = format_presets,
            bundles         = bundles,
            batch           = batch,
        )


def config_path() -> Path:
    """Return the resolved path to the config file (may not exist)."""
    xdg = os.environ.get("XDG_CONFIG_HOME")
    base = Path(xdg) if xdg else Path.home() / ".config"
    return base / "dnsfcli" / "config.toml"


def load_config() -> Config:
    """Load the config file.  Returns default Config if file is absent or unreadable.

    A malformed file falls back to defaults but warns on stderr — silently
    losing the user's profiles/presets/bundles is worse than one noisy line.
    """
    path = config_path()
    if not path.exists():
        return Config()
    try:
        with open(path, "rb") as fh:
            data = tomllib.load(fh)
        return Config.from_dict(data)
    except Exception as exc:
        import sys
        sys.stderr.write(
            f"Warning: could not parse {path} ({exc}); using default configuration.\n"
        )
        return Config()


def _toml_value(v: Any) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, float):
        return repr(v)
    if isinstance(v, int):
        return str(v)
    return f'"{v}"'


def save_config(cfg: Config) -> None:
    """Persist *cfg* to the config file, creating parent directories as needed."""
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    lines: list[str] = ["[defaults]\n"]
    lines.append(f"profile  = {_toml_value(cfg.profile)}\n")
    lines.append(f"no_color = {_toml_value(cfg.no_color)}\n")
    lines.append(f"quiet    = {_toml_value(cfg.quiet)}\n")
    lines.append(f"timeout  = {_toml_value(cfg.timeout)}\n")

    if cfg.columns:
        lines.append("\n[columns]\n")
        for ep, cols in sorted(cfg.columns.items()):
            lines.append(f'{ep} = {_toml_value(",".join(cols))}\n')

    if cfg.column_presets:
        lines.append("\n[column_presets]\n")
        for name, cols in sorted(cfg.column_presets.items()):
            lines.append(f'{name} = {_toml_value(",".join(cols))}\n')

    if cfg.format_presets:
        lines.append("\n[format_presets]\n")
        for name, tmpl in sorted(cfg.format_presets.items()):
            lines.append(f'{name} = {_toml_value(tmpl)}\n')

    if cfg.bundles:
        for bname, bvals in sorted(cfg.bundles.items()):
            lines.append(f"\n[bundles.{bname}]\n")
            for bk, bv in sorted(bvals.items()):
                lines.append(f'{bk} = {_toml_value(bv)}\n')

    b = cfg.batch
    _batch_non_default = (
        b.concurrency != 1 or b.retry != 0 or b.on_error != "continue"
        or b.max_errors is not None or b.batch_size is not None
    )
    if _batch_non_default:
        lines.append("\n[batch]\n")
        if b.concurrency != 1:
            lines.append(f"concurrency = {_toml_value(b.concurrency)}\n")
        if b.retry != 0:
            lines.append(f"retry       = {_toml_value(b.retry)}\n")
        if b.on_error != "continue":
            lines.append(f'on_error    = {_toml_value(b.on_error)}\n')
        if b.max_errors is not None:
            lines.append(f"max_errors  = {_toml_value(b.max_errors)}\n")
        if b.batch_size is not None:
            lines.append(f"batch_size  = {_toml_value(b.batch_size)}\n")

    path.write_text("".join(lines), encoding="utf-8")
