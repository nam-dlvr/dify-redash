"""
List Dashboards Tool for the Redash Extension for Dify plugin.

Retrieves dashboards from the Redash API with optional pagination and
search filtering. Returns a list of dashboard objects with ID, name, slug,
and dates.

Addresses: Requirement 5 (AC 1-8)
"""

import json
import logging
from typing import Any, Generator

try:
    from dify_plugin import Tool
    from dify_plugin.entities.tool import ToolInvokeMessage
except ImportError:
    from tools._dify_stubs import Tool, ToolInvokeMessage

from utils.error_handler import ErrorCode, PluginError, format_error_response, handle_unexpected_error
from utils.redash_client import RedashClient


logger = logging.getLogger(__name__)

# Pagination defaults and limits (Req 5, AC 3-4)
DEFAULT_PAGE_SIZE = 25
MIN_PAGE_SIZE = 1
MAX_PAGE_SIZE = 250
DEFAULT_PAGE = 1

# Search validation (Req 5, AC 5)
MIN_SEARCH_LENGTH = 1
MAX_SEARCH_LENGTH = 200


class ListDashboardsTool(Tool):
    """
    List dashboards from the connected Redash instance.

    Parameters:
    - page_size (optional): Number of dashboards to return (1-250, default 25)
    - page (optional): Page number for pagination (default 1)
    - search (optional): Filter dashboards by name (case-insensitive substring, 1-200 chars)

    Returns:
    - JSON string with list of dashboard objects or structured error
    """

    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage.TextMessage, None, None]:
        """
        Invoke the List Dashboards tool.

        Steps:
        1. Extract and validate parameters (Req 5, AC 3-5)
        2. Create RedashClient with provider credentials
        3. Call GET /api/dashboards with pagination and search params (Req 5, AC 1)
        4. Map response to standardized output (Req 5, AC 2)
        5. Return results or structured error (Req 5, AC 6-7)

        Args:
            tool_parameters: Dict with optional 'page_size', 'page', and 'search' keys.

        Yields:
            ToolInvokeMessage.TextMessage with JSON response.
        """
        try:
            # Step 1: Validate page_size (Req 5, AC 3)
            page_size = tool_parameters.get("page_size")
            if page_size is not None:
                try:
                    page_size = int(page_size)
                except (ValueError, TypeError):
                    error = PluginError(
                        error_code=ErrorCode.VALIDATION_ERROR,
                        message="Invalid page_size: must be a number between 1 and 250.",
                        details={"parameter": "page_size", "provided_value": str(tool_parameters.get("page_size"))},
                    )
                    yield self.create_text_message(json.dumps(format_error_response(error)))
                    return

                if page_size < MIN_PAGE_SIZE or page_size > MAX_PAGE_SIZE:
                    error = PluginError(
                        error_code=ErrorCode.VALIDATION_ERROR,
                        message=f"page_size must be between {MIN_PAGE_SIZE} and {MAX_PAGE_SIZE}.",
                        details={"parameter": "page_size", "provided_value": page_size, "min": MIN_PAGE_SIZE, "max": MAX_PAGE_SIZE},
                    )
                    yield self.create_text_message(json.dumps(format_error_response(error)))
                    return
            else:
                page_size = DEFAULT_PAGE_SIZE

            # Validate page number (Req 5, AC 4)
            page = tool_parameters.get("page")
            if page is not None:
                try:
                    page = int(page)
                except (ValueError, TypeError):
                    error = PluginError(
                        error_code=ErrorCode.VALIDATION_ERROR,
                        message="Invalid page: must be a positive integer.",
                        details={"parameter": "page", "provided_value": str(tool_parameters.get("page"))},
                    )
                    yield self.create_text_message(json.dumps(format_error_response(error)))
                    return

                if page < 1:
                    error = PluginError(
                        error_code=ErrorCode.VALIDATION_ERROR,
                        message="page must be a positive integer.",
                        details={"parameter": "page", "provided_value": page},
                    )
                    yield self.create_text_message(json.dumps(format_error_response(error)))
                    return
            else:
                page = DEFAULT_PAGE

            # Validate search term (Req 5, AC 5)
            search = tool_parameters.get("search")
            if search is not None:
                if not isinstance(search, str) or len(search) < MIN_SEARCH_LENGTH or len(search) > MAX_SEARCH_LENGTH:
                    error = PluginError(
                        error_code=ErrorCode.VALIDATION_ERROR,
                        message=f"search term must be between {MIN_SEARCH_LENGTH} and {MAX_SEARCH_LENGTH} characters.",
                        details={"parameter": "search", "provided_value": str(search), "min_length": MIN_SEARCH_LENGTH, "max_length": MAX_SEARCH_LENGTH},
                    )
                    yield self.create_text_message(json.dumps(format_error_response(error)))
                    return

            # Step 2: Create RedashClient with credentials
            credentials = self.runtime.credentials
            base_url = credentials.get("redash_url", "")
            api_key = credentials.get("api_key", "")

            client = RedashClient(base_url=base_url, api_key=api_key)

            # Step 3: Call GET /api/dashboards with params (Req 5, AC 1)
            params: dict[str, Any] = {"page_size": page_size, "page": page}
            if search:
                params["q"] = search

            response = client.request("GET", "/api/dashboards", params=params)

            # Step 4: Extract dashboard list from response
            # Redash API returns {"count": N, "page": P, "page_size": S, "results": [...]}
            results = response.get("results", [])
            total_count = response.get("count", len(results))

            # Step 5: Map response to standardized output (Req 5, AC 2)
            dashboards = []
            for dashboard in results:
                dashboards.append({
                    "id": dashboard.get("id"),
                    "name": dashboard.get("name"),
                    "slug": dashboard.get("slug"),
                    "created_at": dashboard.get("created_at"),
                    "updated_at": dashboard.get("updated_at"),
                })

            # Return results (Req 5, AC 7 - empty list with total_count: 0 if no results)
            yield self.create_text_message(json.dumps({
                "dashboards": dashboards,
                "total_count": total_count if dashboards else 0,
            }))

        except PluginError as e:
            # Return structured error (Req 5, AC 6)
            logger.error("List dashboards failed: %s (code: %s)", e.message, e.error_code.value)
            yield self.create_text_message(json.dumps(format_error_response(e)))

        except Exception as e:
            # Handle unexpected errors (Req 9, AC 6)
            logger.error("Unexpected error in ListDashboardsTool: %s", str(e))
            yield self.create_text_message(json.dumps(handle_unexpected_error(e)))
