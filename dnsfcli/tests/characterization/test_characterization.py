"""Characterization / golden-snapshot tests.

Each case runs a CLI invocation against canned responses and compares the
normalized transcript to a committed snapshot. A snapshot diff means observable
behavior changed — intended after a real change (regenerate the snapshots),
a regression otherwise.

Regenerate after an intentional change:
    DNSFCLI_UPDATE_SNAPSHOTS=1 pytest tests/characterization -q
"""

from __future__ import annotations

import io
import os
import sys
from pathlib import Path

import pytest

from tests.characterization import cases as _cases
from tests.characterization.harness import run_case

SNAP_DIR = Path(__file__).parent / "snapshots"
UPDATE = os.environ.get("DNSFCLI_UPDATE_SNAPSHOTS") == "1"


@pytest.mark.parametrize("case", _cases.CASES, ids=[c[0] for c in _cases.CASES])
def test_characterization(case, monkeypatch):
    name, endpoint, function, args = case

    stdin_text = _cases.STDIN_CSV.get(name)
    if stdin_text is not None:
        monkeypatch.setattr(sys, "stdin", io.StringIO(stdin_text))

    transcript = run_case(endpoint, function, args, force_tty=name in _cases.FORCE_TTY_CASES)

    snap = SNAP_DIR / f"{name}.txt"
    if UPDATE or not snap.exists():
        snap.parent.mkdir(exist_ok=True)
        snap.write_text(transcript, encoding="utf-8")
        if not UPDATE:
            pytest.skip(f"generated new snapshot {snap.name}")
        return

    expected = snap.read_text(encoding="utf-8")
    assert transcript == expected, (
        f"\nBehavior changed for case '{name}'. If intended, regenerate with "
        f"DNSFCLI_UPDATE_SNAPSHOTS=1.\n\n--- expected ---\n{expected}\n"
        f"--- actual ---\n{transcript}"
    )
