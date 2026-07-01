"""
Tests for the Redash provider (provider/redash.py).

Covers:
- Task 5.2: RedashProvider class extending ToolProvider
- Task 5.3: _validate_credentials() method - reject empty API Key, reject HTTP, test connectivity
- Task 5.4: Differentiated error responses: unreachable (CONN_001), invalid key (AUTH_001), timeout (CONN_002)
- Task 5.5: Successful validation and failed validation behavior
"""

from unittest.mock import MagicMock, patch

import pytest

from provider._dify_stubs import ToolProvider, ToolProviderCredentialValidationError
from provider.redash import RedashProvider, VALIDATION_TIMEOUT
from utils.error_handler import ErrorCode, PluginError


class TestRedashProviderClass:
    """Test RedashProvider class structure (Task 5.2)."""

    def test_extends_tool_provider(self):
        provider = RedashProvider()
        assert isinstance(provider, ToolProvider)

    def test_has_validate_credentials_method(self):
        provider = RedashProvider()
        assert hasattr(provider, "_validate_credentials")
        assert callable(provider._validate_credentials)


class TestValidateCredentialsEmptyApiKey:
    """Test rejection of empty API Key (Task 5.3)."""

    def test_rejects_empty_api_key(self):
        provider = RedashProvider()
        with pytest.raises(ToolProviderCredentialValidationError) as exc_info:
            provider._validate_credentials({
                "redash_url": "https://redash.example.com",
                "api_key": "",
            })
        assert "API Key" in str(exc_info.value)

    def test_rejects_whitespace_only_api_key(self):
        provider = RedashProvider()
        with pytest.raises(ToolProviderCredentialValidationError) as exc_info:
            provider._validate_credentials({
                "redash_url": "https://redash.example.com",
                "api_key": "   ",
            })
        assert "API Key" in str(exc_info.value)

    def test_rejects_missing_api_key(self):
        provider = RedashProvider()
        with pytest.raises(ToolProviderCredentialValidationError) as exc_info:
            provider._validate_credentials({
                "redash_url": "https://redash.example.com",
            })
        assert "API Key" in str(exc_info.value)


class TestValidateCredentialsHttpRejection:
    """Test rejection of HTTP URLs (Task 5.3)."""

    def test_rejects_http_url(self):
        provider = RedashProvider()
        with pytest.raises(ToolProviderCredentialValidationError) as exc_info:
            provider._validate_credentials({
                "redash_url": "http://redash.example.com",
                "api_key": "valid-api-key-1234",
            })
        assert "HTTPS" in str(exc_info.value)

    def test_rejects_http_url_case_insensitive(self):
        provider = RedashProvider()
        with pytest.raises(ToolProviderCredentialValidationError) as exc_info:
            provider._validate_credentials({
                "redash_url": "HTTP://redash.example.com",
                "api_key": "valid-api-key-1234",
            })
        assert "HTTPS" in str(exc_info.value)

    def test_rejects_empty_url(self):
        provider = RedashProvider()
        with pytest.raises(ToolProviderCredentialValidationError) as exc_info:
            provider._validate_credentials({
                "redash_url": "",
                "api_key": "valid-api-key-1234",
            })
        assert "URL" in str(exc_info.value)


class TestValidateCredentialsConnectivity:
    """Test connectivity validation with GET /api/session (Task 5.3)."""

    @patch("provider.redash.RedashClient")
    def test_calls_api_session_with_10s_timeout(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.request.return_value = {"user": {"name": "Test User"}}
        mock_client_cls.return_value = mock_client

        provider = RedashProvider()
        provider._validate_credentials({
            "redash_url": "https://redash.example.com",
            "api_key": "valid-api-key-1234",
        })

        mock_client_cls.assert_called_once_with(
            base_url="https://redash.example.com",
            api_key="valid-api-key-1234",
        )
        mock_client.request.assert_called_once_with(
            "GET", "/api/session",
            timeout=(VALIDATION_TIMEOUT, VALIDATION_TIMEOUT),
        )

    @patch("provider.redash.RedashClient")
    def test_successful_validation_does_not_raise(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.request.return_value = {"user": {"name": "Test User"}}
        mock_client_cls.return_value = mock_client

        provider = RedashProvider()
        # Should not raise
        provider._validate_credentials({
            "redash_url": "https://redash.example.com",
            "api_key": "valid-api-key-1234",
        })


class TestDifferentiatedErrorResponses:
    """Test differentiated error mapping (Task 5.4)."""

    @patch("provider.redash.RedashClient")
    def test_unreachable_url_maps_to_connection_error(self, mock_client_cls):
        """Unreachable URL → CONN_001 → ToolProviderCredentialValidationError."""
        mock_client = MagicMock()
        mock_client.request.side_effect = PluginError(
            error_code=ErrorCode.CONN_UNREACHABLE,
            message="Unable to connect to the Redash instance.",
            details={"host": "redash.example.com", "error_type": "ConnectionError"},
        )
        mock_client_cls.return_value = mock_client

        provider = RedashProvider()
        with pytest.raises(ToolProviderCredentialValidationError) as exc_info:
            provider._validate_credentials({
                "redash_url": "https://redash.example.com",
                "api_key": "valid-api-key-1234",
            })
        assert "Unable to connect" in str(exc_info.value)

    @patch("provider.redash.RedashClient")
    def test_invalid_api_key_maps_to_auth_error(self, mock_client_cls):
        """Invalid API Key → AUTH_001 → ToolProviderCredentialValidationError."""
        mock_client = MagicMock()
        mock_client.request.side_effect = PluginError(
            error_code=ErrorCode.AUTH_INVALID_CREDENTIALS,
            message="Authentication failed: invalid or expired API credentials.",
            details={"http_status": 401},
        )
        mock_client_cls.return_value = mock_client

        provider = RedashProvider()
        with pytest.raises(ToolProviderCredentialValidationError) as exc_info:
            provider._validate_credentials({
                "redash_url": "https://redash.example.com",
                "api_key": "invalid-key",
            })
        assert "Authentication failed" in str(exc_info.value)
        assert "API Key" in str(exc_info.value)

    @patch("provider.redash.RedashClient")
    def test_connection_timeout_maps_to_timeout_error(self, mock_client_cls):
        """Connection timeout → CONN_002 → ToolProviderCredentialValidationError."""
        mock_client = MagicMock()
        mock_client.request.side_effect = PluginError(
            error_code=ErrorCode.CONN_TIMEOUT,
            message="Connection to Redash timed out.",
            details={"host": "redash.example.com", "timeout_type": "connection"},
        )
        mock_client_cls.return_value = mock_client

        provider = RedashProvider()
        with pytest.raises(ToolProviderCredentialValidationError) as exc_info:
            provider._validate_credentials({
                "redash_url": "https://redash.example.com",
                "api_key": "valid-api-key-1234",
            })
        assert "timed out" in str(exc_info.value)

    @patch("provider.redash.RedashClient")
    def test_unexpected_error_maps_to_generic_error(self, mock_client_cls):
        """Unexpected errors are caught and wrapped."""
        mock_client = MagicMock()
        mock_client.request.side_effect = RuntimeError("Something unexpected")
        mock_client_cls.return_value = mock_client

        provider = RedashProvider()
        with pytest.raises(ToolProviderCredentialValidationError) as exc_info:
            provider._validate_credentials({
                "redash_url": "https://redash.example.com",
                "api_key": "valid-api-key-1234",
            })
        assert "unexpected error" in str(exc_info.value).lower()


class TestSuccessfulValidationExposesTools:
    """Test that successful validation enables tool exposure (Task 5.5)."""

    @patch("provider.redash.RedashClient")
    def test_successful_validation_completes_without_error(self, mock_client_cls):
        """
        Successful validation exposes tools to agents.
        In Dify's architecture, if _validate_credentials() returns without raising,
        the tools are automatically exposed to agents within 5 seconds.
        """
        mock_client = MagicMock()
        mock_client.request.return_value = {"user": {"id": 1, "name": "Admin"}}
        mock_client_cls.return_value = mock_client

        provider = RedashProvider()
        # No exception means validation passed → tools will be exposed
        result = provider._validate_credentials({
            "redash_url": "https://redash.example.com",
            "api_key": "valid-api-key-1234",
        })
        # _validate_credentials returns None on success
        assert result is None


class TestFailedValidationPreventsToolExposure:
    """Test that failed validation prevents tool exposure (Task 5.5)."""

    def test_empty_api_key_prevents_tool_exposure(self):
        """Failed validation raises error → tools are NOT exposed."""
        provider = RedashProvider()
        with pytest.raises(ToolProviderCredentialValidationError):
            provider._validate_credentials({
                "redash_url": "https://redash.example.com",
                "api_key": "",
            })

    def test_http_url_prevents_tool_exposure(self):
        """HTTP URL rejection raises error → tools are NOT exposed."""
        provider = RedashProvider()
        with pytest.raises(ToolProviderCredentialValidationError):
            provider._validate_credentials({
                "redash_url": "http://redash.example.com",
                "api_key": "valid-api-key-1234",
            })

    @patch("provider.redash.RedashClient")
    def test_unreachable_host_prevents_tool_exposure(self, mock_client_cls):
        """Unreachable host raises error → tools are NOT exposed."""
        mock_client = MagicMock()
        mock_client.request.side_effect = PluginError(
            error_code=ErrorCode.CONN_UNREACHABLE,
            message="Unable to connect.",
            details={"host": "bad-host.example.com"},
        )
        mock_client_cls.return_value = mock_client

        provider = RedashProvider()
        with pytest.raises(ToolProviderCredentialValidationError):
            provider._validate_credentials({
                "redash_url": "https://bad-host.example.com",
                "api_key": "valid-api-key-1234",
            })

    @patch("provider.redash.RedashClient")
    def test_invalid_key_prevents_tool_exposure(self, mock_client_cls):
        """Invalid API key raises error → tools are NOT exposed."""
        mock_client = MagicMock()
        mock_client.request.side_effect = PluginError(
            error_code=ErrorCode.AUTH_INVALID_CREDENTIALS,
            message="Auth failed.",
            details={"http_status": 401},
        )
        mock_client_cls.return_value = mock_client

        provider = RedashProvider()
        with pytest.raises(ToolProviderCredentialValidationError):
            provider._validate_credentials({
                "redash_url": "https://redash.example.com",
                "api_key": "bad-key",
            })
