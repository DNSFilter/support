"""Unit tests for the HTTP client's retry and backoff logic -- no network required."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dnsfcli.client import APIError, DNSFilterClient, RateLimitError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_response(
    status_code: int,
    json_body: dict | None = None,
    headers: dict | None = None,
    reason: str = "",
) -> MagicMock:
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.headers = headers or {}
    resp.reason_phrase = reason or str(status_code)
    resp.is_success = 200 <= status_code < 300
    resp.content = b"{}" if json_body is not None else b""
    resp.text = str(json_body) if json_body else ""
    if json_body is not None:
        resp.json.return_value = json_body
    return resp


def _make_client() -> DNSFilterClient:
    return DNSFilterClient(api_key="test-key", base_url="https://api.dnsfilter.com")


# ---------------------------------------------------------------------------
# Successful requests
# ---------------------------------------------------------------------------

class TestSuccessfulRequests:
    def test_get_returns_parsed_json(self):
        resp = _make_response(200, {"id": 1, "name": "test"})
        with patch("httpx.Client.request", return_value=resp):
            client = _make_client()
            result = client.get("/v1/networks")
        assert result == {"id": 1, "name": "test"}

    def test_post_returns_parsed_json(self):
        resp = _make_response(201, {"id": 99})
        with patch("httpx.Client.request", return_value=resp):
            client = _make_client()
            result = client.post("/v1/networks", json={"name": "test"})
        assert result["id"] == 99

    def test_204_returns_none(self):
        resp = _make_response(204)
        with patch("httpx.Client.request", return_value=resp):
            client = _make_client()
            result = client.delete("/v1/networks/1")
        assert result is None

    def test_bearer_auth_header_set(self):
        resp = _make_response(200, {})
        with patch("httpx.Client.request", return_value=resp) as mock_req:
            client = _make_client()
            client.get("/v1/test")
        _, kwargs = mock_req.call_args
        # The Authorization header is set on the Client, not per-request kwargs.
        # Verify the client was constructed with Bearer header.
        assert client._client.headers.get("Authorization") == "Bearer test-key"

    def test_base_url_version_suffix_stripped(self):
        """A stored base_url like https://api.dnsfilter.com/v1 must not double the prefix."""
        resp = _make_response(200, {})
        with patch("httpx.Client.request", return_value=resp) as mock_req:
            client = DNSFilterClient(
                api_key="k",
                base_url="https://api.dnsfilter.com/v1",   # stale stored value
            )
            client.get("/v1/networks")
        assert client._client.base_url == httpx.URL("https://api.dnsfilter.com")


# ---------------------------------------------------------------------------
# 429 throttle-retry
# ---------------------------------------------------------------------------

class TestRateLimitRetry:
    def test_retries_after_429(self):
        responses = [
            _make_response(429, {"error": "rate limited"}, headers={"Retry-After": "0"}),
            _make_response(200, {"id": 1}),
        ]
        with patch("httpx.Client.request", side_effect=responses):
            with patch("dnsfcli.client.time.sleep") as mock_sleep:
                client = _make_client()
                result = client.get("/v1/test")
        assert result == {"id": 1}
        mock_sleep.assert_called_once_with(0)

    def test_retry_after_header_respected(self):
        responses = [
            _make_response(429, headers={"Retry-After": "5"}),
            _make_response(200, {"ok": True}),
        ]
        with patch("httpx.Client.request", side_effect=responses):
            with patch("dnsfcli.client.time.sleep") as mock_sleep:
                result = _make_client().get("/v1/test")
        mock_sleep.assert_called_once_with(5)

    def test_default_retry_after_when_header_missing(self):
        responses = [
            _make_response(429),   # no Retry-After header
            _make_response(200, {"ok": True}),
        ]
        with patch("httpx.Client.request", side_effect=responses):
            with patch("dnsfcli.client.time.sleep") as mock_sleep:
                result = _make_client().get("/v1/test")
        # Should sleep for the default (60s per client.py)
        mock_sleep.assert_called_once_with(60)

    def test_retries_multiple_times_on_429(self):
        """The client has no hard cap on 429 retries -- it keeps sleeping and retrying
        until the server responds with a non-429 status."""
        responses = (
            [_make_response(429, headers={"Retry-After": "0"})] * 5
            + [_make_response(200, {"ok": True})]
        )
        sleep_calls: list[float] = []
        with patch("httpx.Client.request", side_effect=responses):
            with patch("dnsfcli.client.time.sleep", side_effect=lambda t: sleep_calls.append(t)):
                result = _make_client().get("/v1/test")
        assert result == {"ok": True}
        assert len(sleep_calls) == 5  # slept once per 429


# ---------------------------------------------------------------------------
# 5xx backoff retry
# ---------------------------------------------------------------------------

class TestServerErrorBackoff:
    """5xx responses are raised as APIError immediately (no retry).
    Only connection-level errors (ConnectError, Timeout) trigger backoff retry."""

    def test_500_raises_api_error_immediately(self):
        """A single 500 should raise APIError on the first attempt -- no retry."""
        responses = [
            _make_response(500, reason="Internal Server Error"),
            _make_response(200, {"id": 2}),   # should never be reached
        ]
        with patch("httpx.Client.request", side_effect=responses) as mock_req:
            with pytest.raises(APIError) as exc_info:
                _make_client().get("/v1/test")
        assert exc_info.value.status_code == 500
        assert mock_req.call_count == 1   # only one attempt made

    def test_503_raises_api_error_immediately(self):
        resp = _make_response(503, reason="Service Unavailable")
        with patch("httpx.Client.request", return_value=resp):
            with pytest.raises(APIError) as exc_info:
                _make_client().get("/v1/test")
        assert exc_info.value.status_code == 503

    def test_502_raises_api_error_immediately(self):
        resp = _make_response(502)
        with patch("httpx.Client.request", return_value=resp):
            with pytest.raises(APIError) as exc_info:
                _make_client().get("/v1/test")
        assert exc_info.value.status_code == 502

    def test_backoff_increases_between_connection_retries(self):
        """Connection errors (not 5xx) use exponential backoff."""
        sleep_times: list[float] = []
        always_fail = httpx.ConnectError("always down")
        with patch("httpx.Client.request", side_effect=always_fail):
            with patch("dnsfcli.client.time.sleep", side_effect=lambda t: sleep_times.append(t)):
                with pytest.raises(APIError):
                    _make_client().get("/v1/test")
        assert len(sleep_times) >= 2
        for i in range(1, len(sleep_times)):
            assert sleep_times[i] >= sleep_times[i - 1]


# ---------------------------------------------------------------------------
# Connection errors
# ---------------------------------------------------------------------------

class TestConnectionErrors:
    def test_retries_on_connect_error(self):
        with patch("httpx.Client.request", side_effect=[
            httpx.ConnectError("connection refused"),
            _make_response(200, {"ok": True}),
        ]):
            with patch("dnsfcli.client.time.sleep"):
                result = _make_client().get("/v1/test")
        assert result is not None

    def test_retries_on_timeout(self):
        with patch("httpx.Client.request", side_effect=[
            httpx.TimeoutException("timed out"),
            _make_response(200, {"ok": True}),
        ]):
            with patch("dnsfcli.client.time.sleep"):
                result = _make_client().get("/v1/test")
        assert result is not None

    def test_raises_after_max_connection_retries(self):
        with patch("httpx.Client.request", side_effect=httpx.ConnectError("always down")):
            with patch("dnsfcli.client.time.sleep"):
                with pytest.raises(APIError):
                    _make_client().get("/v1/test")


# ---------------------------------------------------------------------------
# Non-retryable errors
# ---------------------------------------------------------------------------

class TestNonRetryableErrors:
    def test_401_raises_immediately(self):
        resp = _make_response(401, {"message": "Not Authorized"})
        with patch("httpx.Client.request", return_value=resp):
            with pytest.raises(APIError) as exc_info:
                _make_client().get("/v1/test")
        assert exc_info.value.status_code == 401

    def test_404_raises_immediately(self):
        resp = _make_response(404, {"message": "Not Found"})
        with patch("httpx.Client.request", return_value=resp):
            with pytest.raises(APIError) as exc_info:
                _make_client().get("/v1/test")
        assert exc_info.value.status_code == 404

    def test_422_raises_immediately(self):
        resp = _make_response(422, {"message": "Validation error"})
        with patch("httpx.Client.request", return_value=resp):
            with pytest.raises(APIError) as exc_info:
                _make_client().get("/v1/test")
        assert exc_info.value.status_code == 422

    def test_error_message_captured(self):
        resp = _make_response(400, {"message": "bad input"})
        with patch("httpx.Client.request", return_value=resp):
            with pytest.raises(APIError) as exc_info:
                _make_client().get("/v1/test")
        assert "bad input" in str(exc_info.value)


# ---------------------------------------------------------------------------
# Context manager
# ---------------------------------------------------------------------------

class TestContextManager:
    def test_context_manager_closes_client(self):
        with patch("httpx.Client.close") as mock_close:
            with _make_client():
                pass
        mock_close.assert_called_once()

    def test_client_usable_inside_context(self):
        resp = _make_response(200, {"id": 1})
        with patch("httpx.Client.request", return_value=resp):
            with _make_client() as client:
                result = client.get("/v1/test")
        assert result == {"id": 1}
