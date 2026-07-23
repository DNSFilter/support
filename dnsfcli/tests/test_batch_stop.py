"""Regression test: --on-error stop / --max-errors must halt a CONCURRENT batch.

The old executor submitted every row to the pool before consuming any result,
and never cancelled futures — so under --concurrency the stop flag was a no-op
and all rows ran regardless. This exercises the concurrent path directly.
"""

from __future__ import annotations

import sys
import threading
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dnsfcli import batch as batch_mod
from dnsfcli import cli as cli_mod  # noqa: F401  (kept for REGISTRY/helpers used elsewhere)
from dnsfcli.client import APIError
from dnsfcli.endpoints import REGISTRY


class _RecordingClient:
    """Fake client: records each request, sleeps briefly to force real overlap,
    and fails the very first row so `on_error=stop` should trip early."""

    def __init__(self) -> None:
        self.calls = 0
        self._lock = threading.Lock()

    def request(self, method, path, params=None, json=None):
        with self._lock:
            self.calls += 1
            n = self.calls
        time.sleep(0.02)  # keep rows overlapping so the stop has rows to cancel
        if n == 1:
            raise APIError(400, "deliberate failure to trigger stop")
        return {"id": n}

    # Unused verbs / context-manager plumbing the batch code may touch.
    def get(self, *a, **k):
        return {}

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _rows(count):
    # block-pages create requires only 'name'
    return [{"name": f"row-{i}"} for i in range(count)]


def test_concurrent_batch_stops_on_error(monkeypatch, capsys):
    op = REGISTRY["block-pages"].operations["create"]
    client = _RecordingClient()
    rows = _rows(200)

    with pytest.raises(SystemExit):
        # on_error="stop" should abort the run after the first failure; with
        # 200 rows at concurrency 4 and a 20ms per-row delay, a correct
        # implementation executes only a small fraction before stopping.
        batch_mod._execute_csv_rows(
            rows, op, "block-pages", "create", client,
            verbose=False, csv_output=None,
            on_error="stop", concurrency=4, no_progress=True,
        )

    # The essential property: NOT every row ran. The old code executed all 200.
    assert client.calls < len(rows), f"stop was a no-op: {client.calls}/{len(rows)} ran"
    # And it stopped promptly rather than draining most of the batch.
    assert client.calls <= 40, f"stop was too slow: {client.calls} rows ran"


def test_concurrent_batch_max_errors(monkeypatch):
    """--max-errors N should also stop the concurrent batch near N failures."""
    op = REGISTRY["block-pages"].operations["create"]

    class _AllFail(_RecordingClient):
        def request(self, method, path, params=None, json=None):
            with self._lock:
                self.calls += 1
            time.sleep(0.02)
            raise APIError(400, "fail")

    client = _AllFail()
    with pytest.raises(SystemExit):
        batch_mod._execute_csv_rows(
            _rows(200), op, "block-pages", "create", client,
            verbose=False, csv_output=None,
            on_error="continue", max_errors=5, concurrency=4, no_progress=True,
        )
    # Should stop shortly after hitting 5 errors, not run all 200.
    assert client.calls < 200
