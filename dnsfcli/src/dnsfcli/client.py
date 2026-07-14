"""HTTP client with automatic 429 throttle-retry and connection backoff."""

from __future__ import annotations

import logging
import time
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_RETRYABLE_STATUS = {500, 502, 503, 504}
_MAX_RETRIES = 6
_MAX_429_RETRIES = 20  # upper bound so a persistently throttling server cannot hang forever
_BACKOFF_MIN = 1.0
_BACKOFF_MAX = 60.0

# DNSFilter rate limit: 2,000 req / 300 s. Target 80% to stay safely under.
_RATE_LIMIT_CAPACITY = 1_600        # burst budget (tokens)
_RATE_LIMIT_RATE     = 1_600 / 300  # refill rate (tokens/second ≈ 5.33/s)


class _TokenBucket:
    """Token bucket for proactive client-side rate limiting.

    Requests consume one token each. When the bucket is empty the caller
    blocks until enough tokens have refilled. This keeps the sustained
    request rate below the API's hard limit without needing a 429 first.
    """

    def __init__(self, capacity: float, refill_rate: float) -> None:
        self._capacity = capacity
        self._tokens = capacity
        self._refill_rate = refill_rate  # tokens per second
        self._last = time.monotonic()

    def consume(self) -> None:
        """Block until a token is available, then consume it."""
        while True:
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
            time.sleep(wait)


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


def _is_connection_error(exc: BaseException) -> bool:
    return isinstance(exc, (httpx.ConnectError, httpx.TimeoutException, httpx.RemoteProtocolError))


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
        """*rate*: max requests per second.  None uses the default 80 % of the
        API's 2 000 req/300 s limit.  Positive values scale the bucket capacity
        proportionally so the burst headroom stays constant relative to the rate.
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
            follow_redirects=False,
            verify=verify,
        )
        if proxy:
            _httpx_kwargs["proxy"] = proxy
        self._client = httpx.Client(**_httpx_kwargs)
        if rate is not None:
            effective_rate = max(0.01, float(rate))
            # Keep capacity / rate ratio the same as the default (300 s window)
            capacity = effective_rate * 300
            self._rate_limiter = _TokenBucket(capacity, effective_rate)
        else:
            self._rate_limiter = _TokenBucket(_RATE_LIMIT_CAPACITY, _RATE_LIMIT_RATE)

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
            retry_after = int(response.headers.get("Retry-After", 60))
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
        attempt = 0
        backoff = _BACKOFF_MIN
        throttle_retries = 0

        while True:
            attempt += 1
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
                wait = exc.retry_after
                logger.warning("Rate limited (429). Waiting %ds before retry %d...", wait, attempt)
                time.sleep(wait)

            except APIError:
                # All other API errors are non-retryable by design: 4xx are
                # caller mistakes, and 5xx are raised immediately rather than
                # retried (a failed write may still have been applied server-
                # side, so blind retry risks duplicates).
                raise

            except (httpx.ConnectError, httpx.TimeoutException, httpx.RemoteProtocolError) as exc:
                if attempt >= _MAX_RETRIES:
                    raise APIError(0, f"Connection failed after {_MAX_RETRIES} attempts: {exc}") from exc
                logger.warning(
                    "Connection error (%s). Backoff %.1fs (attempt %d/%d)...",
                    type(exc).__name__,
                    backoff,
                    attempt,
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
