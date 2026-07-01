"""
Redash provider for Dify plugin.

Implements credential validation for the Redash integration provider.
Validates HTTPS URL, non-empty API key, and connectivity to the Redash instance.

Addresses: Requirement 1 (AC 2-9), Requirement 10 (AC 1, 4, 8)
"""

import logging
from typing import Any

try:
    from dify_plugin import ToolProvider
    from dify_plugin.errors.tool import ToolProviderCredentialValidationError
except ImportError:
    # Stubs for development/testing when Dify SDK is not available
    from provider._dify_stubs import ToolProvider, ToolProviderCredentialValidationError

from utils.error_handler import ErrorCode, PluginError
from utils.redash_client import RedashClient


logger = logging.getLogger(__name__)

# Validation timeout for credential check (seconds)
VALIDATION_TIMEOUT = 10


class RedashProvider(ToolProvider):
    """
    Redash provider that validates credentials for the Dify plugin.

    Validates:
    - API Key is non-empty (Req 10, AC 8)
    - URL uses HTTPS scheme (Req 10, AC 4)
    - Connectivity to Redash instance via GET /api/session (Req 1, AC 3)

    Error differentiation (Req 1, AC 4-6):
    - Unreachable URL → CONN_001
    - Invalid API Key → AUTH_001
    - Connection timeout → CONN_002
    """

    def _validate_credentials(self, credentials: dict[str, Any]) -> None:
        """
        Validate Redash provider credentials.

        Steps:
        1. Extract redash_url and api_key from credentials
        2. Reject empty API Key (Req 10, AC 8)
        3. Reject HTTP URLs - HTTPS required (Req 10, AC 4)
        4. Create RedashClient (validates URL scheme internally)
        5. Test connectivity with GET /api/session using 10s timeout (Req 1, AC 3)
        6. Map errors to ToolProviderCredentialValidationError

        Args:
            credentials: Dictionary containing 'redash_url' and 'api_key'

        Raises:
            ToolProviderCredentialValidationError: If validation fails
        """
        redash_url = credentials.get("redash_url", "").strip()
        api_key = credentials.get("api_key", "").strip()

        # Validate API Key is non-empty (Req 10, AC 8)
        if not api_key:
            raise ToolProviderCredentialValidationError(
                "A valid API Key is required. Please provide your Redash API key."
            )

        # Validate URL uses HTTPS (Req 10, AC 4)
        if redash_url.lower().startswith("http://"):
            raise ToolProviderCredentialValidationError(
                "HTTPS is required for Redash API communication. "
                "Please provide an HTTPS URL (e.g., https://your-redash-instance.example.com)."
            )

        # Validate URL is not empty
        if not redash_url:
            raise ToolProviderCredentialValidationError(
                "A valid Redash instance URL is required."
            )

        try:
            # Create client - this also validates URL scheme (Req 10, AC 1)
            client = RedashClient(base_url=redash_url, api_key=api_key)

            # Test connectivity with GET /api/session using 10-second timeout (Req 1, AC 3)
            client.request("GET", "/api/session", timeout=(VALIDATION_TIMEOUT, VALIDATION_TIMEOUT))

            logger.info(
                "Redash credentials validated successfully for %s",
                redash_url,
            )

        except PluginError as e:
            # Map PluginError to Dify's ToolProviderCredentialValidationError
            # with differentiated messages based on error code
            if e.error_code == ErrorCode.CONN_UNREACHABLE:
                # Unreachable URL (Req 1, AC 4) → CONN_001
                raise ToolProviderCredentialValidationError(
                    f"Unable to connect to the Redash instance at {redash_url}. "
                    "Please verify the URL is correct and the instance is accessible."
                ) from e
            elif e.error_code == ErrorCode.AUTH_INVALID_CREDENTIALS:
                # Invalid API Key (Req 1, AC 5) → AUTH_001
                raise ToolProviderCredentialValidationError(
                    "Authentication failed: the provided API Key is invalid or expired. "
                    "Please verify your Redash API key."
                ) from e
            elif e.error_code == ErrorCode.CONN_TIMEOUT:
                # Connection timeout (Req 1, AC 6) → CONN_002
                raise ToolProviderCredentialValidationError(
                    "Connection to the Redash instance timed out. "
                    "Please verify the URL is correct and the instance is responsive."
                ) from e
            else:
                # Other errors
                raise ToolProviderCredentialValidationError(
                    f"Credential validation failed: {e.message}"
                ) from e

        except Exception as e:
            logger.error("Unexpected error during credential validation: %s", str(e))
            raise ToolProviderCredentialValidationError(
                "An unexpected error occurred during credential validation. "
                "Please try again or contact support."
            ) from e
