"""Regression tests for the shared, thread-safe token-bucket rate limiter.

These cover the three concurrency/rate findings from internal review:
  - the bucket must not permit a large opening burst (was 1600 full);
  - one limiter must be shared per API key (was per client instance, so
    fan-out and watch ticks each got a fresh full bucket);
  - consume() must be thread-safe under --concurrency.
"""

from __future__ import annotations

import sys
import threading
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dnsfcli import client as client_mod
from dnsfcli.client import (
    _RATE_LIMIT_BURST,
    _RATE_LIMIT_REFILL,
    _TokenBucket,
    _reset_limiter_registry,
    _shared_limiter,
)


@pytest.fixture(autouse=True)
def _clean_registry():
    _reset_limiter_registry()
    yield
    _reset_limiter_registry()


class _FakeClock:
    """Deterministic monotonic clock so bucket tests don't depend on sleep."""

    def __init__(self) -> None:
        self.t = 1000.0

    def time(self) -> float:
        return self.t

    def sleep(self, dt: float) -> None:
        self.t += dt


class TestBurstBudget:
    def test_opening_burst_is_bounded(self, monkeypatch):
        """A fresh bucket must not allow anywhere near a full-window's requests
        instantly — the old design allowed 1600."""
        clock = _FakeClock()
        monkeypatch.setattr(client_mod.time, "monotonic", clock.time)
        monkeypatch.setattr(client_mod.time, "sleep", clock.sleep)

        bucket = _TokenBucket(_RATE_LIMIT_BURST, _RATE_LIMIT_REFILL)
        # Consume the full burst without advancing the clock.
        for _ in range(_RATE_LIMIT_BURST):
            bucket.consume()
        # The very next consume must block (advance the fake clock via sleep).
        before = clock.t
        bucket.consume()
        assert clock.t > before, "bucket did not throttle after its burst"

    def test_worst_case_window_under_api_limit(self):
        """burst + refill*300 must stay under the 2000 req / 300 s hard limit."""
        worst_case = _RATE_LIMIT_BURST + _RATE_LIMIT_REFILL * 300
        assert worst_case < 2000, f"{worst_case} requests possible in one window"

    def test_refill_replenishes_at_rate(self, monkeypatch):
        clock = _FakeClock()
        monkeypatch.setattr(client_mod.time, "monotonic", clock.time)
        monkeypatch.setattr(client_mod.time, "sleep", clock.sleep)

        bucket = _TokenBucket(_RATE_LIMIT_BURST, _RATE_LIMIT_REFILL)
        for _ in range(_RATE_LIMIT_BURST):
            bucket.consume()            # empty the bucket; last-refill time = now
        assert bucket._tokens == pytest.approx(0.0, abs=1e-6)

        # After 10 idle seconds the bucket must have refilled ~refill*10 tokens.
        # One more consume triggers the refill accounting; check the balance
        # directly rather than looping (no clock-condition spin).
        clock.t += 10
        bucket.consume()
        assert bucket._tokens == pytest.approx(_RATE_LIMIT_REFILL * 10 - 1, abs=0.5)


class TestSharedLimiter:
    def test_same_key_shares_one_bucket(self):
        a = _shared_limiter("KEY-A", _RATE_LIMIT_REFILL, explicit_rate=False)
        b = _shared_limiter("KEY-A", _RATE_LIMIT_REFILL, explicit_rate=False)
        assert a is b, "clients with the same API key must share one limiter"

    def test_different_keys_get_separate_buckets(self):
        a = _shared_limiter("KEY-A", _RATE_LIMIT_REFILL, explicit_rate=False)
        b = _shared_limiter("KEY-B", _RATE_LIMIT_REFILL, explicit_rate=False)
        assert a is not b

    def test_clients_reuse_the_shared_bucket(self):
        c1 = client_mod.DNSFilterClient(api_key="SHARED", base_url="https://api.dnsfilter.com")
        c2 = client_mod.DNSFilterClient(api_key="SHARED", base_url="https://api.dnsfilter.com")
        assert c1._rate_limiter is c2._rate_limiter
        c1.close()
        c2.close()

    def test_explicit_rate_reconfigures_shared_bucket(self):
        _shared_limiter("KEY-R", _RATE_LIMIT_REFILL, explicit_rate=False)
        bucket = _shared_limiter("KEY-R", 2.0, explicit_rate=True)
        assert bucket._refill_rate == 2.0


class TestThreadSafety:
    def test_consume_does_not_overdraw_under_threads(self, monkeypatch):
        """Concurrent consumers must not drive the bucket below zero — the
        lockless version's read-modify-write let threads over-consume."""
        # No real sleeping: give a big burst so no consumer needs to block,
        # then assert the accounting stayed exact under contention.
        bucket = _TokenBucket(capacity=500, refill_rate=0.0)
        monkeypatch.setattr(client_mod.time, "monotonic", lambda: 1000.0)  # freeze refill

        consumed = []
        barrier = threading.Barrier(10)

        def worker():
            barrier.wait()
            for _ in range(50):
                bucket.consume()
                consumed.append(1)

        threads = [threading.Thread(target=worker) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # 10 × 50 = 500 tokens consumed from a 500 bucket → exactly empty,
        # never negative. With frozen refill, tokens can't have gone below 0.
        assert len(consumed) == 500
        assert bucket._tokens == pytest.approx(0.0, abs=1e-6)
        assert bucket._tokens >= -1e-9
