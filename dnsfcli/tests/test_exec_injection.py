"""Adversarial tests for the --exec command-injection defense.

These drive the REAL rendering function (postprocess.render_exec_command) and
the REAL CLI path — not a reimplementation — with attacker-controlled field
values, including the quoted-placeholder vectors that a naive shlex.quote()
defense misses. A prior version of this suite tested a local copy of the logic
and only the (safe) unquoted case, so it stayed green over a live RCE.
"""

from __future__ import annotations

import io
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dnsfcli.postprocess import render_exec_command


# --- the exact vectors reproduced during review (quoted placeholder + $()) ---

@pytest.mark.parametrize("template", [
    'echo "user={name}"',   # double-quoted: $() stays active inside "…"
    "echo '{name}'",        # single-quoted: value lands outside the quotes
    "echo {name}",          # bare
    'echo "$name"',         # $field form, double-quoted
])
@pytest.mark.parametrize("payload", [
    "$(touch /tmp/pwned)",
    "`touch /tmp/pwned`",
    "; touch /tmp/pwned",
    "&& touch /tmp/pwned",
    "| tee /tmp/pwned",
    "x\nrm -rf /",
    "$(id)",
    "-rf",          # option injection (e.g. `rm {name}` → `rm -rf`)
    "--all",        # option injection (e.g. `kubectl delete pod {name}` → `--all`)
    "--force",
])
def test_exec_refuses_shell_metacharacter_values(template, payload):
    """Any value with a shell-active character is flagged unsafe → caller refuses."""
    rendered, unsafe = render_exec_command(template, {"name": payload})
    assert unsafe == ["name"], (
        f"value {payload!r} in template {template!r} was NOT flagged unsafe "
        f"(rendered {rendered!r}) — this is the RCE path"
    )


@pytest.mark.parametrize("value", [
    "510528",
    "alpha-network",
    "hq.example.com",
    "Org_Name",
    "https://api.example.com/v1/x",
    "user@example.com",
    "New York",          # space is safe (shlex-quoted, not a metachar)
])
def test_exec_allows_inert_values(value):
    """Ordinary ids/names/domains/urls render and are NOT flagged unsafe."""
    rendered, unsafe = render_exec_command("curl https://h/{id}", {"id": value})
    assert unsafe == []
    # the value appears in the rendered command (shlex-quoted as needed)
    import shlex
    assert shlex.quote(value) in rendered


def test_exec_legit_substitution_exact():
    rendered, unsafe = render_exec_command("curl https://h/{id}", {"id": "510528"})
    assert (rendered, unsafe) == ("curl https://h/510528", [])


def test_exec_unknown_placeholder_left_verbatim():
    rendered, unsafe = render_exec_command("echo {missing}", {"id": "1"})
    assert rendered == "echo {missing}"
    assert unsafe == []


# --- integration: the real CLI path must not execute an injected command ------

def test_exec_cli_path_does_not_execute_injected_command(tmp_path, monkeypatch):
    """End-to-end through _make_dynamic_command: a malicious API field value must
    NOT run, and the run must report it skipped."""
    from dnsfcli import cli as _cli
    from dnsfcli import cliparams as _cliparams
    from dnsfcli import client as _client
    import contextlib

    marker = tmp_path / "PWNED"
    malicious = f"$(touch {marker})"

    def fake_request(self, method, path, params=None, json=None):
        return {"data": [{"id": "1", "name": malicious}], "meta": {"total_pages": 1}}

    for mod in (_cli, _cliparams):
        monkeypatch.setattr(mod, "get_api_key", lambda profile="default": "k", raising=False)
        monkeypatch.setattr(mod, "get_base_url", lambda profile="default": "https://api.dnsfilter.com", raising=False)
        monkeypatch.setattr(mod, "get_org_id", lambda profile="default": "1", raising=False)
    monkeypatch.setattr(_cli, "get_active_profile", lambda: "default", raising=False)
    monkeypatch.setattr(_client.DNSFilterClient, "request", fake_request)

    out = io.StringIO()
    cmd = _cli._make_dynamic_command("networks", "list")
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
        with pytest.raises(SystemExit):
            cmd.main(args=["--exec", 'echo "{name}"', "--no-progress"], standalone_mode=True)
    # The security property: the injected command must NOT have run.
    assert not marker.exists(), "injected command executed — RCE"
    # And the operator is told why nothing ran.
    assert "skipped" in out.getvalue() and "metacharacters" in out.getvalue()
