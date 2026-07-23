"""HTTP client with automatic 429 throttle-retry and connection backoff."""

from __future__ import annotations

import logging
import random
import threading
import time
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_RETRYABLE_STATUS = {500, 502, 503, 504}
_MAX_RETRIES = 6
_MAX_429_RETRIES = 20  # upper bound so a persistently throttling server cannot hang forever
_BACKOFF_MIN = 1.0
_BACKOFF_MAX = 60.0

# DNSFilter rate limit: 2,000 req / 300 s.
#
# We target 80% of the sustained rate as the token REFILL rate, and keep a
# small fixed BURST so a fresh process doesn't fire a large opening volley.
# Over any 300 s window the worst case is BURST + REFILL*300 = 60 + 1600 =
# 1660 requests, comfortably under the 2000 hard limit. (The previous design
# started a 1600-token bucket full and refilled at 5.33/s, allowing ~3200
# requests in the first window — and it was per-client, so fan-out and watch
# ticks each got their own full bucket. Both are fixed here: small burst, and
# one shared limiter per API key per process.)
#
# SCOPE: this limiter is PER PROCESS. It bounds every request path within a
# single invocation (pagination, batch --concurrency, --each-org, --watch),
# but it does NOT coordinate across separate processes — running the same key
# in N concurrent processes (xargs -P, CI shards, cron fleets) multiplies the
# budget N×. This is client-side courtesy throttling to avoid tripping 429s in
# normal use, not an enforcement boundary; the server's own limit is the real
# ceiling. Cross-process coordination would need a shared on-disk token file.
_RATE_LIMIT_REFILL = 2_000 * 0.8 / 300   # ≈ 5.33 tokens/second (sustained)
_RATE_LIMIT_BURST  = 60                   # max opening burst, independent of rate


class _TokenBucket:
    """Thread-safe token bucket for proactive client-side rate limiting.

    Requests consume one token each. When the bucket is empty the caller
    blocks until enough tokens have refilled. This keeps the sustained
    request rate below the API's hard limit without needing a 429 first.

    Safe to share across threads (e.g. a ThreadPoolExecutor under
    ``--concurrency``): the token accounting is guarded by a lock, and the
    lock is released before sleeping so blocked callers don't serialise.
    """

    def __init__(self, capacity: float, refill_rate: float) -> None:
        self._capacity = capacity
        self._tokens = capacity
        self._refill_rate = refill_rate  # tokens per second
        self._last = time.monotonic()
        self._lock = threading.Lock()

    def set_refill(self, refill_rate: float) -> None:
        """Reconfigure the sustained refill rate (an explicit --rate wins)."""
        with self._lock:
            self._refill_rate = refill_rate

    def consume(self) -> None:
        """Block until a token is available, then consume it."""
        while True:
            with self._lock:
                now = time.monotonic()
                self._tokens = min(
                    self._capacity,
                    self._tokens + (now - self._last) * self._refill_rate,
                )
                self._last = now
                if self._tokens >= 1:
                    self._tokens -= 1
                    return
                wait = (1 - self._tokens) / self._refill_rate
            logger.debug("Rate limiter: bucket empty, sleeping %.3fs", wait)
            time.sleep(wait)  # released the lock above — don't sleep holding it


# One limiter per API key per process. All clients built for the same key —
# across --each-org iterations, --parallel-orgs workers, and watch ticks —
# share a single bucket so the key's real request budget is respected.
_limiter_registry: dict[str, _TokenBucket] = {}
_registry_lock = threading.Lock()


def _shared_limiter(api_key: str, refill_rate: float, explicit_rate: bool) -> _TokenBucket:
    with _registry_lock:
        bucket = _limiter_registry.get(api_key)
        if bucket is None:
            bucket = _TokenBucket(_RATE_LIMIT_BURST, refill_rate)
            _limiter_registry[api_key] = bucket
        elif explicit_rate:
            # A user-supplied --rate reconfigures the shared bucket, so it
            # wins over the default rate an earlier client may have set.
            bucket.set_refill(refill_rate)
        return bucket


def _reset_limiter_registry() -> None:
    """Clear the process-wide limiter registry (test isolation only)."""
    with _registry_lock:
        _limiter_registry.clear()


class APIError(Exception):
    def __init__(self, status_code: int, message: str, body: Any = None) -> None:
        self.status_code = status_code
        self.message = message
        self.body = body
        super().__init__(f"HTTP {status_code}: {message}")


class RateLimitError(APIError):
    def __init__(self, retry_after: int, body: Any = None) -> None:
        self.retry_after = retry_after
        super().__init__(429, f"Rate limited - retry after {retry_after}s", body)


_RETRY_AFTER_MAX = 300  # cap an absurd/hostile value so we never hang for hours


def _parse_retry_after(value: str | None, default: int = 60) -> int:
    """Parse a Retry-After header value into seconds, never raising.

    RFC 7231 permits either a number of seconds OR an HTTP-date; the old
    bare int() crashed with a traceback on the date form. Falls back to
    *default* on anything unparseable and caps the result.
    """
    if not value:
        return default
    value = value.strip()
    try:
        return max(0, min(int(value), _RETRY_AFTER_MAX))
    except ValueError:
        pass
    try:
        from datetime import datetime, timezone
        from email.utils import parsedate_to_datetime
        when = parsedate_to_datetime(value)
        if when is not None:
            if when.tzinfo is None:
                when = when.replace(tzinfo=timezone.utc)
            delta = (when - datetime.now(timezone.utc)).total_seconds()
            return max(0, min(int(delta), _RETRY_AFTER_MAX))
    except (TypeError, ValueError):
        pass
    return default


class DNSFilterClient:
    def __init__(
        self,
        api_key: str,
        base_url: str,
        org_id: str | None = None,
        timeout: float = 30.0,
        rate: float | None = None,
        verify: bool = True,
        extra_headers: dict[str, str] | None = None,
        connect_timeout: float = 10.0,
        proxy: str | None = None,
    ) -> None:
        """*rate*: sustained max requests per second. None uses the default
        80 % of the API's 2 000 req/300 s limit. The limiter is shared per
        API key across every client in this process, so fan-out and watch
        loops all draw from one budget rather than each getting a fresh one.
        """
        self._org_id = org_id
        import re
        base_url = re.sub(r"/v\d+/*$", "", base_url.rstrip("/"))
        headers: dict[str, str] = {
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        if extra_headers:
            headers.update(extra_headers)
        _httpx_kwargs: dict[str, Any] = dict(
            base_url=base_url,
            headers=headers,
            timeout=httpx.Timeout(connect=connect_timeout, read=timeout, write=timeout, pool=5.0),
            # Bound concurrent sockets, but keep the pool at least as large as
            # the max batch worker count (--concurrency cap is 64) so workers
            # don't queue on the pool and spuriously hit PoolTimeout.
            limits=httpx.Limits(max_connections=64, max_keepalive_connections=32),
            follow_redirects=False,
            verify=verify,
        )
        if proxy:
            _httpx_kwargs["proxy"] = proxy
        self._client = httpx.Client(**_httpx_kwargs)
        explicit_rate = rate is not None
        if explicit_rate:
            requested = max(0.01, float(rate))
            # Clamp DOWN to the sustained budget: --rate may only slow this
            # process's limiter, never raise it above the safe rate (e.g.
            # --rate 100000 is capped). Note this cap is per-process (see the
            # SCOPE note on the module constants); it is not a cross-process
            # enforcement of the account's total budget.
            refill = min(requested, _RATE_LIMIT_REFILL)
            if requested > _RATE_LIMIT_REFILL:
                logger.warning(
                    "Requested --rate %.2f/s exceeds the safe sustained limit; "
                    "capping at %.2f/s.", requested, _RATE_LIMIT_REFILL,
                )
        else:
            refill = _RATE_LIMIT_REFILL
        self._rate_limiter = _shared_limiter(api_key, refill, explicit_rate)

    # ------------------------------------------------------------------
    # Internal request machinery
    # ------------------------------------------------------------------

    def _do_request(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
    ) -> Any:
        """Single attempt - raises on non-2xx. Caller handles retries."""
        self._rate_limiter.consume()
        response = self._client.request(method, path, params=params, json=json)

        if response.status_code == 429:
            retry_after = _parse_retry_after(response.headers.get("Retry-After"))
            try:
                body = response.json()
            except Exception:
                body = response.text
            raise RateLimitError(retry_after, body)

        if response.status_code in _RETRYABLE_STATUS:
            try:
                body = response.json()
            except Exception:
                body = response.text
            raise APIError(response.status_code, response.reason_phrase, body)

        if response.status_code == 204:
            return None

        if not response.is_success:
            body = None  # must be initialised before the try so the except path can reference it
            try:
                body = response.json()
                msg = body.get("message") or body.get("error") or response.reason_phrase
            except Exception:
                msg = response.text or response.reason_phrase
            raise APIError(response.status_code, msg, body if isinstance(body, dict) else None)

        if not response.content:
            return None
        # Return raw text for non-JSON content types (e.g. text/csv from user-agents csv).
        # When content-type is absent, assume JSON (the API always returns JSON).
        content_type = response.headers.get("content-type", "")
        if content_type and "json" not in content_type:
            return response.text
        return response.json()

    def request(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
    ) -> Any:
        """Request with 429-aware retry and exponential backoff for connection errors."""
        backoff = _BACKOFF_MIN
        # Independent counters: a long run of 429 throttles must NOT consume the
        # connection-error retry budget (and vice versa), so the two failure
        # classes each get their own cap.
        throttle_retries = 0
        conn_retries = 0

        while True:
            try:
                return self._do_request(method, path, params=params, json=json)

            except RateLimitError as exc:
                throttle_retries += 1
                if throttle_retries > _MAX_429_RETRIES:
                    raise APIError(
                        429,
                        f"Still rate limited after {_MAX_429_RETRIES} retries — giving up",
                        exc.body,
                    ) from exc
                # Add jitter so N concurrent workers throttled at the same instant
                # (they all receive the same Retry-After) don't wake in lockstep
                # and re-burst together.
                wait = exc.retry_after + random.uniform(0, 1)
                logger.warning("Rate limited (429). Waiting %.1fs before retry %d...", wait, throttle_retries)
                time.sleep(wait)

            except APIError:
                # All other API errors are non-retryable by design: 4xx are
                # caller mistakes, and 5xx are raised immediately rather than
                # retried (a failed write may still have been applied server-
                # side, so blind retry risks duplicates).
                raise

            except (httpx.ConnectError, httpx.TimeoutException, httpx.RemoteProtocolError) as exc:
                conn_retries += 1
                if conn_retries >= _MAX_RETRIES:
                    raise APIError(0, f"Connection failed after {_MAX_RETRIES} attempts: {exc}") from exc
                logger.warning(
                    "Connection error (%s). Backoff %.1fs (attempt %d/%d)...",
                    type(exc).__name__,
                    backoff,
                    conn_retries,
                    _MAX_RETRIES,
                )
                time.sleep(backoff)
                backoff = min(backoff * 2, _BACKOFF_MAX)

    # ------------------------------------------------------------------
    # Convenience verbs
    # ------------------------------------------------------------------

    def get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        return self.request("GET", path, params=params)

    def post(self, path: str, json: dict[str, Any] | None = None) -> Any:
        return self.request("POST", path, json=json)

    def patch(self, path: str, json: dict[str, Any] | None = None) -> Any:
        return self.request("PATCH", path, json=json)

    def put(self, path: str, json: dict[str, Any] | None = None) -> Any:
        return self.request("PUT", path, json=json)

    def delete(self, path: str, json: dict[str, Any] | None = None) -> Any:
        return self.request("DELETE", path, json=json)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "DNSFilterClient":
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()
