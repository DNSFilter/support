"""Characterization harness: run a CLI invocation in-process against canned
responses and capture (stdout, stderr, exit code) as a normalized string.

The point is a behavioral safety net for refactoring the request-build and
post-processing pipeline: snapshot the observable output of a matrix of flag
combinations now, and any future change that alters behavior shows up as a
snapshot diff. Runs in-process (monkeypatching the HTTP layer + auth getters)
because the tool enforces an HTTPS base URL and reads credentials from the
keychain, so a plain mock server can't be injected.
"""

from __future__ import annotations

import contextlib
import io
import os
import re
import sys
from pathlib import Path

SRC = Path(__file__).parent.parent.parent / "src"
sys.path.insert(0, str(SRC))

os.environ["COLUMNS"] = "120"   # fixed width → deterministic table rendering
os.environ["NO_COLOR"] = "1"

from dnsfcli import client as _client_mod          # noqa: E402
from dnsfcli import cliparams as _cliparams_mod      # noqa: E402
from dnsfcli import csv_io as _csvio_mod             # noqa: E402
from dnsfcli import output as _output_mod           # noqa: E402
from dnsfcli import cli as _cli                      # noqa: E402
from . import fixtures                               # noqa: E402


def _reset_output_state() -> None:
    """Reset output module globals to import defaults so cases don't bleed."""
    _output_mod._quiet = False
    _output_mod._quiet_ok = False
    _output_mod._no_color = True
    _output_mod._suppress_data = False
    _output_mod._truncate = None
    _output_mod._no_wrap = False
    _output_mod._color_rules = []
    _output_mod._color_scale = None
    _output_mod._tee_path = None
    _output_mod._csv_null_value = ""
    _output_mod._table_style = None
    _output_mod._log_fh = None
    _output_mod._tee_raw = []
    _output_mod.console.no_color = True
    _output_mod.console.record = False
    _output_mod.err_console.no_color = True


class _TTYStringIO(io.StringIO):
    """A StringIO that claims to be a TTY, so the CLI's non-TTY→JSON auto-switch
    does not fire and the Rich table renderer / --columns path is exercised."""

    def isatty(self) -> bool:  # noqa: D401
        return True


def run_case(endpoint: str, function: str, args: list[str], force_tty: bool = False) -> str:
    """Run one dynamic-command invocation and return a normalized transcript."""
    out_buf: io.StringIO = _TTYStringIO() if force_tty else io.StringIO()
    err_buf = io.StringIO()
    exit_code = 0

    # credentials without touching the keychain. Each module does
    # `from .auth import get_*`, so it holds its OWN binding — patch every
    # module on the exercised path (cli resolves some getters directly;
    # credential resolution lives in cliparams; batch CSV validation in csv_io).
    patches = {
        "get_api_key": lambda profile="default": "test-key",
        "get_base_url": lambda profile="default": "https://api.dnsfilter.com",
        "get_org_id": lambda profile="default": "802315",
        "get_active_profile": lambda: "default",
    }
    _patch_targets = [_cli, _cliparams_mod, _csvio_mod]
    # (name, module) pairs that actually have the attribute
    saved = {
        (name, mod): getattr(mod, name)
        for name in patches for mod in _patch_targets if hasattr(mod, name)
    }
    saved_request = _client_mod.DNSFilterClient.request
    # Save the RAW underlying `_file` (normally None → Rich resolves it to the
    # live sys.stdout/stderr on each access). Reading the `.file` property here
    # would materialize the current stream and pin it, which then breaks
    # capsys-based tests that swap sys.stderr later in the run.
    saved_files = (_output_mod.console._file, _output_mod.err_console._file)

    def fake_request(self, method, path, params=None, json=None):
        return fixtures.respond(method, path, params, json)

    try:
        _reset_output_state()
        for (name, mod) in saved:
            setattr(mod, name, patches[name])
        _client_mod.DNSFilterClient.request = fake_request
        _client_mod._reset_limiter_registry()
        _output_mod.console.file = out_buf
        _output_mod.err_console.file = err_buf
        with contextlib.redirect_stdout(out_buf), contextlib.redirect_stderr(err_buf):
            cmd = _cli._make_dynamic_command(endpoint, function)
            try:
                cmd.main(args=args, standalone_mode=True)
            except SystemExit as exc:
                exit_code = exc.code if isinstance(exc.code, int) else (0 if exc.code is None else 1)
    finally:
        for (name, mod), val in saved.items():
            setattr(mod, name, val)
        _client_mod.DNSFilterClient.request = saved_request
        _output_mod.console._file, _output_mod.err_console._file = saved_files
        _reset_output_state()

    return _transcript(endpoint, function, args, out_buf.getvalue(), err_buf.getvalue(), exit_code)


_TS_RE = re.compile(r"\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}")


def _normalize(text: str) -> str:
    text = _TS_RE.sub("<TS>", text)
    # strip trailing whitespace per line (rich pads tables to width)
    return "\n".join(line.rstrip() for line in text.splitlines())


def _transcript(endpoint, function, args, out, err, code) -> str:
    return (
        f"$ dnsfcli {endpoint} {function} {' '.join(args)}\n"
        f"--- exit: {code} ---\n"
        f"--- stdout ---\n{_normalize(out)}\n"
        f"--- stderr ---\n{_normalize(err)}\n"
    )
