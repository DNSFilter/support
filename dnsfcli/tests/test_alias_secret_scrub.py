"""--save-as must not persist any secret into the alias file.

The alias-save path previously dropped only --api-key/--header/--proxy, so
--new-password / --client-secret / --body-json / --set password= were stored
verbatim (and echoed on `alias list`). These test the shared drop-scrubber
directly and the end-to-end save-as path.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dnsfcli.audit import drop_secret_tokens
from tests.conftest import CLI_SCRIPT, PROJECT_DIR


@pytest.mark.parametrize("argv,must_drop", [
    (["networks", "list", "--api-key", "SECRET"], "SECRET"),
    (["networks", "list", "--api-key=SECRET"], "SECRET"),
    (["users", "create", "--new-password", "hunter2"], "hunter2"),
    (["users", "create", "--client-secret", "abc123"], "abc123"),
    (["x", "create", "--body-json", '{"password":"p"}'], "password"),
    (["x", "create", "--set", "api_key=zzz"], "zzz"),
    (["x", "create", "--header", "Authorization=Bearer tok"], "tok"),
    (["x", "create", "--proxy", "http://user:pw@h"], "pw@h"),
])
def test_drop_removes_secret_value(argv, must_drop):
    kept, dropped = drop_secret_tokens(argv)
    assert dropped is True
    assert must_drop not in " ".join(kept), f"secret {must_drop!r} survived in {kept}"


@pytest.mark.parametrize("argv,secret", [
    (["users", "create", "--new-password", "-p@ss"], "-p@ss"),   # value starts with '-'
    (["x", "create", "--api-key", "-weirdkey"], "-weirdkey"),
])
def test_drop_removes_leading_dash_secret_value(argv, secret):
    """A secret value that starts with '-' must still be dropped, not retained."""
    kept, dropped = drop_secret_tokens(argv)
    assert dropped is True
    assert secret not in kept, f"leading-dash secret {secret!r} survived in {kept}"


def test_drop_keeps_nonsecret_and_stdin_json():
    # --stdin-json is a boolean flag (payload from stdin, not argv): keep it and
    # do NOT consume the following token.
    kept, dropped = drop_secret_tokens(["networks", "create", "--stdin-json", "--yes"])
    assert kept == ["networks", "create", "--stdin-json", "--yes"]
    assert dropped is False


def test_drop_keeps_nonsecret_set():
    kept, dropped = drop_secret_tokens(["x", "create", "--set", "name=HQ", "--limit", "5"])
    assert kept == ["x", "create", "--set", "name=HQ", "--limit", "5"]
    assert dropped is False


def _run(*args):
    return subprocess.run([sys.executable, str(CLI_SCRIPT), *args],
                          capture_output=True, text=True, cwd=str(PROJECT_DIR))


def test_save_as_does_not_persist_password(tmp_path):
    """End-to-end: a --new-password must not land in the stored alias."""
    name = "scrub-test-alias"
    save = _run("networks", "list", "--new-password", "hunter2",
                "--save-as", name, "--dry-run", "--api-key", "FAKE")
    try:
        combined = save.stdout + save.stderr
        assert "Traceback" not in combined
        listing = _run("alias", "list")
        both = listing.stdout + listing.stderr
        assert "hunter2" not in both, "password persisted into alias file!"
        assert "FAKE" not in both, "api key persisted into alias file!"
    finally:
        _run("alias", "delete", name)
