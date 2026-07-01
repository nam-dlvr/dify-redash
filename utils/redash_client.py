"""
Centralized HTTP client for Redash API communication.

Handles authentication, HTTPS enforcement, timeouts, retry logic for rate limits,
error mapping, and API key masking in logs.

Addresses: Requirement 9 (AC 1-5, 8), Requirement 10 (AC 1-7)
"""

import logging
import time
from urllib.parse import urlparse

import requests

from utils.error_handler import ErrorCode, PluginError


logger = logging.getLogger(__name__)

# Masking constants
_MASK_PLACEHOLDER = "****"
_VISIBLE_CHARS = 4

# Timeout configuration (seconds)
CONNECTION_TIMEOUT = 30
READ_TIMEOUT = 120

# Retry configuration
MAX_RETRIES = 3
DEFAULT_RETRY_DELAY = 5  # seconds


def mask_api_key(api_key: str) -> str:
    """
    Mask an API key for safe display in logs.

    Shows only the last 4 characters with a fixed placeholder for the remainder.

    Args:
        api_key: The raw API key string.

    Returns:
        Masked string, e.g. "****ab1f"
    """
    if len(api_key) <= _VISIBLE_CHARS:
        return _MASK_PLACEHOLDER
    return f"{_MASK_PLACEHOLDER}{api_key[-_VISIBLE_CHARS:]}"


class RedashClient:
    """
    Centralized HTTP client for Redash API communication.

    Configuration:
    - Connection timeout: 30 seconds (Req 10, AC 5)
    - Read timeout: 120 seconds (Req 10, AC 6)
    - Protocol: HTTPS only (Req 10, AC 1)
    - Auth: API Key in Authorization header (Req 10, AC 2)
    - Key masking: Last 4 chars visible in logs (Req 10, AC 3)
    """

    def __init__(self, base_url: str, api_key: str) -> None:
        """
        Initialize the Redash HTTP client.

        Args:
            base_url: The base URL of the Redash instance (must be HTTPS).
            api_key: The Redash API key for authentication.

        Raises:
            PluginError: If the URL uses HTTP instead of HTTPS.
        """
        # Validate HTTPS (Req 10, AC 1, AC 4)
        parsed = urlparse(base_url)
        if parsed.scheme.lower() == "http":
            raise PluginError(
                error_code=ErrorCode.CONN_UNREACHABLE,
                message="HTTPS is required for Redash API communication. HTTP URLs are not allowed.",
                details={"url_scheme": parsed.scheme},
            )
        if parsed.scheme.lower() != "https":
            raise PluginError(
                error_code=ErrorCode.CONN_UNREACHABLE,
                message="Invalid URL scheme. HTTPS is required for Redash API communication.",
                details={"url_scheme": parsed.scheme},
            )

        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self._masked_key = mask_api_key(api_key)

        # Configure session with auth and content-type headers (Req 10, AC 2)
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Key {api_key}",
                "Content-Type": "application/json",
            }
        )

        logger.info(
            "RedashClient initialized for %s (API key: %s)",
            self.base_url,
            self._masked_key,
        )

    def request(self, method: str, path: str, **kwargs) -> dict:
        """
        Make an authenticated request to the Redash API with retry logic for 429.

        Retry strategy (Req 9, AC 3-4):
        - On 429: use Retry-After header if present, else 5s fixed delay
        - Maximum 3 retry attempts
        - After exhaustion: raise RateLimitError

        Error mapping:
        - 401 -> AuthenticationError (Req 9, AC 1)
        - 403 -> PermissionError (Req 9, AC 2)
        - 429 -> retry, then RateLimitError (Req 9, AC 3-4)
        - 5xx -> ServerError with status code (Req 9, AC 8)
        - Network failure -> ConnectionError with host and error type (Req 9, AC 5)
        - Timeout -> TimeoutError (Req 10, AC 7)

        Args:
            method: HTTP method (GET, POST, PUT, DELETE, etc.)
            path: API path to append to base_url (e.g., "/api/queries")
            **kwargs: Additional keyword arguments passed to requests:
                - json: Request body as dict
                - params: Query parameters as dict
                - timeout: Override default timeout tuple

        Returns:
            Parsed JSON response as a dict.

        Raises:
            PluginError: On any API or network error, mapped to appropriate error code.
        """
        url = f"{self.base_url}{path}"
        timeout = kwargs.pop("timeout", (CONNECTION_TIMEOUT, READ_TIMEOUT))

        logger.debug(
            "Request: %s %s (API key: %s)",
            method.upper(),
            url,
            self._masked_key,
        )

        attempts = 0

        while True:
            try:
                response = self.session.request(
                    method=method,
                    url=url,
                    timeout=timeout,
                    **kwargs,
                )
            except requests.exceptions.ConnectTimeout:
                logger.error(
                    "Connection timeout to %s (API key: %s)",
                    self.base_url,
                    self._masked_key,
                )
                raise PluginError(
                    error_code=ErrorCode.CONN_TIMEOUT,
                    message="Connection to Redash timed out.",
                    details={"host": urlparse(self.base_url).hostname, "timeout_type": "connection"},
                )
            except requests.exceptions.ReadTimeout:
                logger.error(
                    "Read timeout from %s (API key: %s)",
                    self.base_url,
                    self._masked_key,
                )
                raise PluginError(
                    error_code=ErrorCode.CONN_TIMEOUT,
                    message="Redash request timed out waiting for a response.",
                    details={"host": urlparse(self.base_url).hostname, "timeout_type": "read"},
                )
            except requests.exceptions.ConnectionError as exc:
                host = urlparse(self.base_url).hostname
                error_type = type(exc).__name__
                logger.error(
                    "Connection error to %s: %s (API key: %s)",
                    host,
                    error_type,
                    self._masked_key,
                )
                raise PluginError(
                    error_code=ErrorCode.CONN_UNREACHABLE,
                    message="Unable to connect to the Redash instance.",
                    details={"host": host, "error_type": error_type},
                )

            # Handle rate limiting with retries (Req 9, AC 3-4)
            if response.status_code == 429:
                attempts += 1
                if attempts >= MAX_RETRIES:
                    logger.warning(
                        "Rate limit exhausted after %d attempts for %s (API key: %s)",
                        MAX_RETRIES,
                        url,
                        self._masked_key,
                    )
                    raise PluginError(
                        error_code=ErrorCode.RATE_LIMIT_EXCEEDED,
                        message="Redash API rate limit exceeded. Please try again later.",
                        details={"attempts": MAX_RETRIES},
                    )

                # Determine retry delay
                retry_after = response.headers.get("Retry-After")
                if retry_after is not None:
                    try:
                        delay = float(retry_after)
                    except (ValueError, TypeError):
                        delay = DEFAULT_RETRY_DELAY
                else:
                    delay = DEFAULT_RETRY_DELAY

                logger.info(
                    "Rate limited (429). Retrying in %.1f seconds (attempt %d/%d, API key: %s)",
                    delay,
                    attempts,
                    MAX_RETRIES,
                    self._masked_key,
                )
                time.sleep(delay)
                continue

            # Handle authentication error (Req 9, AC 1)
            if response.status_code == 401:
                logger.error(
                    "Authentication failed for %s (API key: %s)",
                    self.base_url,
                    self._masked_key,
                )
                raise PluginError(
                    error_code=ErrorCode.AUTH_INVALID_CREDENTIALS,
                    message="Authentication failed: invalid or expired API credentials.",
                    details={"http_status": 401},
                )

            # Handle permission error (Req 9, AC 2)
            if response.status_code == 403:
                logger.error(
                    "Permission denied for %s %s (API key: %s)",
                    method.upper(),
                    url,
                    self._masked_key,
                )
                raise PluginError(
                    error_code=ErrorCode.AUTH_INSUFFICIENT_PERMISSIONS,
                    message="Insufficient permissions for the requested resource.",
                    details={"http_status": 403},
                )

            # Handle server errors (Req 9, AC 8)
            if 500 <= response.status_code < 600:
                logger.error(
                    "Server error %d from %s (API key: %s)",
                    response.status_code,
                    url,
                    self._masked_key,
                )
                raise PluginError(
                    error_code=ErrorCode.SERVER_ERROR,
                    message="A Redash server-side error occurred.",
                    details={"http_status": response.status_code},
                )

            # Success - parse and return JSON
            response.raise_for_status()
            if response.status_code == 204 or not response.content:
                return {}
            return response.json()
