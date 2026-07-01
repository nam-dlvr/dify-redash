"""
Tests for the Redash HTTP client (utils/redash_client.py).

Covers:
- Task 3.1: RedashClient class creation
- Task 3.2: Constructor with base_url and api_key, session headers
- Task 3.3: HTTPS URL validation (reject HTTP)
- Task 3.4: Connection timeout (30s) and read timeout (120s)
- Task 3.5: request() method with HTTP method, path, optional body/params
- Task 3.6: Retry logic for 429 responses
- Task 3.7: Error mapping (401, 403, 429 exhausted, 5xx, network failure, timeout)
- Task 3.8: API Key masking in log outputs
"""

import time
from unittest.mock import MagicMock, patch

import pytest
import requests

from utils.error_handler import ErrorCode, PluginError
from utils.redash_client import (
    CONNECTION_TIMEOUT,
    DEFAULT_RETRY_DELAY,
    MAX_RETRIES,
    READ_TIMEOUT,
    RedashClient,
    mask_api_key,
)


# ─── Task 3.8: API Key Masking ────────────────────────────────────────────────


class TestMaskApiKey:
    """Test API key masking utility (Task 3.8)."""

    def test_masks_long_key_showing_last_4_chars(self):
        key = "abcdefgh12345678"
        result = mask_api_key(key)
        assert result == "****5678"

    def test_masks_key_exactly_5_chars(self):
        result = mask_api_key("abcde")
        assert result == "****bcde"

    def test_masks_short_key_with_placeholder_only(self):
        result = mask_api_key("abc")
        assert result == "****"

    def test_masks_key_of_4_chars_with_placeholder_only(self):
        result = mask_api_key("abcd")
        assert result == "****"

    def test_masks_empty_key_with_placeholder_only(self):
        result = mask_api_key("")
        assert result == "****"


# ─── Task 3.2 & 3.3: Constructor ──────────────────────────────────────────────


class TestRedashClientConstructor:
    """Test constructor validates URL and sets up session (Tasks 3.2, 3.3)."""

    def test_accepts_https_url(self):
        client = RedashClient("https://redash.example.com", "test-api-key-1234")
        assert client.base_url == "https://redash.example.com"

    def test_strips_trailing_slash_from_base_url(self):
        client = RedashClient("https://redash.example.com/", "test-api-key-1234")
        assert client.base_url == "https://redash.example.com"

    def test_rejects_http_url(self):
        with pytest.raises(PluginError) as exc_info:
            RedashClient("http://redash.example.com", "test-api-key-1234")
        assert exc_info.value.error_code == ErrorCode.CONN_UNREACHABLE
        assert "HTTPS" in exc_info.value.message

    def test_rejects_empty_scheme_url(self):
        with pytest.raises(PluginError) as exc_info:
            RedashClient("redash.example.com", "test-api-key-1234")
        assert exc_info.value.error_code == ErrorCode.CONN_UNREACHABLE

    def test_sets_authorization_header(self):
        client = RedashClient("https://redash.example.com", "my-secret-key")
        assert client.session.headers["Authorization"] == "Key my-secret-key"

    def test_sets_content_type_header(self):
        client = RedashClient("https://redash.example.com", "my-secret-key")
        assert client.session.headers["Content-Type"] == "application/json"

    def test_stores_masked_key(self):
        client = RedashClient("https://redash.example.com", "abcdefgh1234")
        assert client._masked_key == "****1234"


# ─── Task 3.4: Timeout Configuration ──────────────────────────────────────────


class TestTimeoutConfiguration:
    """Test timeout constants are correctly defined (Task 3.4)."""

    def test_connection_timeout_is_30_seconds(self):
        assert CONNECTION_TIMEOUT == 30

    def test_read_timeout_is_120_seconds(self):
        assert READ_TIMEOUT == 120


# ─── Task 3.5: request() Method ───────────────────────────────────────────────


class TestRequestMethod:
    """Test the request() method functionality (Task 3.5)."""

    def setup_method(self):
        self.client = RedashClient("https://redash.example.com", "test-key-abcd")

    @patch.object(requests.Session, "request")
    def test_makes_get_request(self, mock_request):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"results": []}
        mock_response.content = b'{"results": []}'
        mock_request.return_value = mock_response

        result = self.client.request("GET", "/api/queries")

        mock_request.assert_called_once_with(
            method="GET",
            url="https://redash.example.com/api/queries",
            timeout=(30, 120),
        )
        assert result == {"results": []}

    @patch.object(requests.Session, "request")
    def test_makes_post_request_with_json_body(self, mock_request):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"id": 1}
        mock_response.content = b'{"id": 1}'
        mock_request.return_value = mock_response

        result = self.client.request("POST", "/api/queries/1/results", json={"parameters": {"x": 1}})

        mock_request.assert_called_once_with(
            method="POST",
            url="https://redash.example.com/api/queries/1/results",
            timeout=(30, 120),
            json={"parameters": {"x": 1}},
        )
        assert result == {"id": 1}

    @patch.object(requests.Session, "request")
    def test_makes_get_request_with_params(self, mock_request):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"count": 10}
        mock_response.content = b'{"count": 10}'
        mock_request.return_value = mock_response

        result = self.client.request("GET", "/api/queries", params={"page_size": 25})

        mock_request.assert_called_once_with(
            method="GET",
            url="https://redash.example.com/api/queries",
            timeout=(30, 120),
            params={"page_size": 25},
        )
        assert result == {"count": 10}

    @patch.object(requests.Session, "request")
    def test_returns_empty_dict_for_204_no_content(self, mock_request):
        mock_response = MagicMock()
        mock_response.status_code = 204
        mock_response.content = b""
        mock_response.raise_for_status = MagicMock()
        mock_request.return_value = mock_response

        result = self.client.request("DELETE", "/api/queries/1")
        assert result == {}

    @patch.object(requests.Session, "request")
    def test_passes_custom_timeout(self, mock_request):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {}
        mock_response.content = b"{}"
        mock_request.return_value = mock_response

        self.client.request("GET", "/api/session", timeout=(10, 10))

        mock_request.assert_called_once_with(
            method="GET",
            url="https://redash.example.com/api/session",
            timeout=(10, 10),
        )


# ─── Task 3.6: Retry Logic for 429 ───────────────────────────────────────────


class TestRetryLogic:
    """Test retry logic for HTTP 429 responses (Task 3.6)."""

    def setup_method(self):
        self.client = RedashClient("https://redash.example.com", "test-key-abcd")

    @patch("utils.redash_client.time.sleep")
    @patch.object(requests.Session, "request")
    def test_retries_on_429_then_succeeds(self, mock_request, mock_sleep):
        response_429 = MagicMock()
        response_429.status_code = 429
        response_429.headers = {}

        response_200 = MagicMock()
        response_200.status_code = 200
        response_200.json.return_value = {"ok": True}
        response_200.content = b'{"ok": true}'

        mock_request.side_effect = [response_429, response_200]

        result = self.client.request("GET", "/api/queries")
        assert result == {"ok": True}
        mock_sleep.assert_called_once_with(DEFAULT_RETRY_DELAY)

    @patch("utils.redash_client.time.sleep")
    @patch.object(requests.Session, "request")
    def test_uses_retry_after_header(self, mock_request, mock_sleep):
        response_429 = MagicMock()
        response_429.status_code = 429
        response_429.headers = {"Retry-After": "10"}

        response_200 = MagicMock()
        response_200.status_code = 200
        response_200.json.return_value = {"data": []}
        response_200.content = b'{"data": []}'

        mock_request.side_effect = [response_429, response_200]

        result = self.client.request("GET", "/api/queries")
        assert result == {"data": []}
        mock_sleep.assert_called_once_with(10.0)

    @patch("utils.redash_client.time.sleep")
    @patch.object(requests.Session, "request")
    def test_raises_rate_limit_error_after_max_retries(self, mock_request, mock_sleep):
        response_429 = MagicMock()
        response_429.status_code = 429
        response_429.headers = {}

        mock_request.return_value = response_429

        with pytest.raises(PluginError) as exc_info:
            self.client.request("GET", "/api/queries")

        assert exc_info.value.error_code == ErrorCode.RATE_LIMIT_EXCEEDED
        # Flow: request→429→attempts=1→sleep→request→429→attempts=2→sleep→request→429→attempts=3→raise
        # So sleep is called MAX_RETRIES - 1 times (last attempt raises immediately)
        # Wait, let me trace: 1st 429 → attempts=1 < 3 → sleep, 2nd 429 → attempts=2 < 3 → sleep, 3rd 429 → attempts=3 >= 3 → raise
        # That's 2 sleeps. But there's an initial request + 2 sleeps then one more request = 3 retried requests total
        # Actually: initial + retry1 + retry2 + retry3(raises) = 4 request calls but only 2 complete sleeps before raising on 3rd excess
        # Let's just verify the key behavior: error is raised, and we got 3 retries
        # Flow: request→429→attempts=1→sleep→request→429→attempts=2→sleep→request→429→attempts=3→raise
        # That's 2 sleeps and 3 total requests. The 3rd 429 triggers the raise, no sleep after it.
        assert mock_sleep.call_count == MAX_RETRIES - 1
        assert mock_request.call_count == MAX_RETRIES

    @patch("utils.redash_client.time.sleep")
    @patch.object(requests.Session, "request")
    def test_uses_default_delay_for_invalid_retry_after(self, mock_request, mock_sleep):
        response_429 = MagicMock()
        response_429.status_code = 429
        response_429.headers = {"Retry-After": "invalid"}

        response_200 = MagicMock()
        response_200.status_code = 200
        response_200.json.return_value = {}
        response_200.content = b"{}"

        mock_request.side_effect = [response_429, response_200]

        self.client.request("GET", "/api/queries")
        mock_sleep.assert_called_once_with(DEFAULT_RETRY_DELAY)


# ─── Task 3.7: Error Mapping ──────────────────────────────────────────────────


class TestErrorMapping:
    """Test error mapping for various HTTP responses and failures (Task 3.7)."""

    def setup_method(self):
        self.client = RedashClient("https://redash.example.com", "test-key-abcd")

    @patch.object(requests.Session, "request")
    def test_401_raises_authentication_error(self, mock_request):
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_request.return_value = mock_response

        with pytest.raises(PluginError) as exc_info:
            self.client.request("GET", "/api/session")

        assert exc_info.value.error_code == ErrorCode.AUTH_INVALID_CREDENTIALS
        assert exc_info.value.details == {"http_status": 401}

    @patch.object(requests.Session, "request")
    def test_403_raises_permission_error(self, mock_request):
        mock_response = MagicMock()
        mock_response.status_code = 403
        mock_request.return_value = mock_response

        with pytest.raises(PluginError) as exc_info:
            self.client.request("GET", "/api/queries/1")

        assert exc_info.value.error_code == ErrorCode.AUTH_INSUFFICIENT_PERMISSIONS
        assert exc_info.value.details == {"http_status": 403}

    @patch.object(requests.Session, "request")
    def test_500_raises_server_error(self, mock_request):
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_request.return_value = mock_response

        with pytest.raises(PluginError) as exc_info:
            self.client.request("GET", "/api/queries")

        assert exc_info.value.error_code == ErrorCode.SERVER_ERROR
        assert exc_info.value.details == {"http_status": 500}

    @patch.object(requests.Session, "request")
    def test_502_raises_server_error(self, mock_request):
        mock_response = MagicMock()
        mock_response.status_code = 502
        mock_request.return_value = mock_response

        with pytest.raises(PluginError) as exc_info:
            self.client.request("GET", "/api/queries")

        assert exc_info.value.error_code == ErrorCode.SERVER_ERROR
        assert exc_info.value.details == {"http_status": 502}

    @patch.object(requests.Session, "request")
    def test_connection_timeout_raises_timeout_error(self, mock_request):
        mock_request.side_effect = requests.exceptions.ConnectTimeout()

        with pytest.raises(PluginError) as exc_info:
            self.client.request("GET", "/api/queries")

        assert exc_info.value.error_code == ErrorCode.CONN_TIMEOUT
        assert exc_info.value.details["timeout_type"] == "connection"
        assert exc_info.value.details["host"] == "redash.example.com"

    @patch.object(requests.Session, "request")
    def test_read_timeout_raises_timeout_error(self, mock_request):
        mock_request.side_effect = requests.exceptions.ReadTimeout()

        with pytest.raises(PluginError) as exc_info:
            self.client.request("GET", "/api/queries")

        assert exc_info.value.error_code == ErrorCode.CONN_TIMEOUT
        assert exc_info.value.details["timeout_type"] == "read"
        assert exc_info.value.details["host"] == "redash.example.com"

    @patch.object(requests.Session, "request")
    def test_connection_error_raises_connection_error(self, mock_request):
        mock_request.side_effect = requests.exceptions.ConnectionError("Connection refused")

        with pytest.raises(PluginError) as exc_info:
            self.client.request("GET", "/api/queries")

        assert exc_info.value.error_code == ErrorCode.CONN_UNREACHABLE
        assert exc_info.value.details["host"] == "redash.example.com"
        assert exc_info.value.details["error_type"] == "ConnectionError"
