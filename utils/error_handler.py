"""
Error handling utilities for the Redash Extension for Dify plugin.

Provides structured error codes, a standard PluginError exception class,
and utilities for handling unexpected errors and formatting error responses.

Addresses: Requirement 9 (AC 6-7)
"""

import logging
import traceback
from enum import Enum
from typing import Any, Optional


logger = logging.getLogger(__name__)


class ErrorCode(str, Enum):
    """Unique error code identifiers categorized by type (Req 9, AC 7)."""

    AUTH_INVALID_CREDENTIALS = "AUTH_001"
    AUTH_INSUFFICIENT_PERMISSIONS = "AUTH_002"
    CONN_UNREACHABLE = "CONN_001"
    CONN_TIMEOUT = "CONN_002"
    RATE_LIMIT_EXCEEDED = "RATE_001"
    QUERY_NOT_FOUND = "QUERY_001"
    QUERY_TIMEOUT = "QUERY_002"
    QUERY_EXECUTION_ERROR = "QUERY_003"
    QUERY_INVALID_PARAMS = "QUERY_004"
    DASHBOARD_NOT_FOUND = "DASH_001"
    VALIDATION_ERROR = "VAL_001"
    SERVER_ERROR = "SERVER_001"
    UNEXPECTED_ERROR = "UNEXPECTED_001"


class PluginError(Exception):
    """
    Standard error response structure for the Redash plugin.

    Raised when a known error condition occurs. Can be caught and converted
    to a structured error response dict.

    Fields:
    - error_code: ErrorCode enum value
    - message: Non-specific description (no stack traces, file paths, etc.) (Req 9, AC 6)
    - details: Optional additional context (HTTP status, host, error type)
    """

    def __init__(
        self,
        error_code: ErrorCode,
        message: str,
        details: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(message)
        self.error_code = error_code
        self.message = message
        self.details = details

    def to_dict(self) -> dict[str, Any]:
        """Serialize the error to a dictionary for API responses."""
        result: dict[str, Any] = {
            "error": True,
            "error_code": self.error_code.value,
            "message": self.message,
        }
        if self.details is not None:
            result["details"] = self.details
        return result


def handle_unexpected_error(error: Exception) -> dict[str, Any]:
    """
    Handles unexpected errors by logging full details internally and returning
    a sanitized error response without stack traces, file paths, library names,
    or internal variable values (Req 9, AC 6).

    Args:
        error: The unexpected exception that was caught.

    Returns:
        A sanitized error response dict with error_code and a generic message.
    """
    # Log full error details internally for debugging
    logger.error(
        "Unexpected error occurred: %s: %s",
        type(error).__name__,
        str(error),
        exc_info=True,
    )

    # Return sanitized error without exposing internals
    sanitized_error = PluginError(
        error_code=ErrorCode.UNEXPECTED_ERROR,
        message="An unexpected error occurred. Please try again or contact support.",
    )
    return sanitized_error.to_dict()


def format_error_response(plugin_error: PluginError) -> dict[str, Any]:
    """
    Produces a consistent error response dict with error_code and message fields.

    This ensures all error responses follow the same structure regardless of
    the specific error type.

    Args:
        plugin_error: A PluginError instance containing the error details.

    Returns:
        A dict with error=True, error_code, message, and optional details.
    """
    return plugin_error.to_dict()
