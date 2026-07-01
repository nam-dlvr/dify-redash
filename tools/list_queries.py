"""
List Queries Tool for the Redash Extension for Dify plugin.

Retrieves saved queries from the Redash API with optional pagination and
search filtering. Returns a list of query objects with ID, name, description,
data source, and dates.

Addresses: Requirement 2 (AC 1-9)
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

# Pagination defaults and limits (Req 2, AC 3-4, 7)
DEFAULT_PAGE_SIZE = 25
MIN_PAGE_SIZE = 1
MAX_PAGE_SIZE = 250


class ListQueriesTool(Tool):
    """
    List saved queries from the connected Redash instance.

    Parameters:
    - page_size (optional): Number of queries to return (1-250, default 25)
    - search (optional): Filter queries by name (case-insensitive substring match)

    Returns:
    - JSON string with list of query objects or structured error
    """

    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage.TextMessage, None, None]:
        """
        Invoke the List Queries tool.

        Steps:
        1. Extract and validate parameters (Req 2, AC 3-4, 7)
        2. Create RedashClient with provider credentials
        3. Call GET /api/queries with pagination and search params (Req 2, AC 1)
        4. Map response to standardized output (Req 2, AC 2)
        5. Apply case-insensitive filtering if search provided (Req 2, AC 5)
        6. Return results or structured error (Req 2, AC 6, 8)

        Args:
            tool_parameters: Dict with optional 'page_size' and 'search' keys.

        Yields:
            ToolInvokeMessage.TextMessage with JSON response.
        """
        try:
            # Step 1: Validate page_size (Req 2, AC 3, 4, 7)
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

            # Extract search term (Req 2, AC 5)
            search = tool_parameters.get("search")

            # Step 2: Create RedashClient with credentials
            credentials = self.runtime.credentials
            base_url = credentials.get("redash_url", "")
            api_key = credentials.get("api_key", "")

            client = RedashClient(base_url=base_url, api_key=api_key)

            # Step 3: Call GET /api/queries with params (Req 2, AC 1)
            params: dict[str, Any] = {"page_size": page_size}
            if search:
                params["q"] = search

            response = client.request("GET", "/api/queries", params=params)

            # Step 4: Extract query list from response
            # Redash API returns {"count": N, "page": P, "page_size": S, "results": [...]}
            results = response.get("results", [])

            # Step 5: Map response to standardized output (Req 2, AC 2)
            queries = []
            for query in results:
                queries.append({
                    "id": query.get("id"),
                    "name": query.get("name"),
                    "description": query.get("description"),
                    "data_source_id": query.get("data_source_id"),
                    "created_at": query.get("created_at"),
                    "updated_at": query.get("updated_at"),
                })

            # Step 6: Apply additional client-side case-insensitive filtering (Req 2, AC 5)
            # The Redash API's `q` parameter does server-side search, but we also
            # apply client-side filtering for case-insensitive substring matching
            # against the query name to ensure consistent behavior.
            if search:
                search_lower = search.lower()
                queries = [q for q in queries if q.get("name") and search_lower in q["name"].lower()]

            # Return results (Req 2, AC 8 - empty list if no results)
            yield self.create_text_message(json.dumps({"queries": queries}))

        except PluginError as e:
            # Return structured error (Req 2, AC 6)
            logger.error("List queries failed: %s (code: %s)", e.message, e.error_code.value)
            yield self.create_text_message(json.dumps(format_error_response(e)))

        except Exception as e:
            # Handle unexpected errors (Req 9, AC 6)
            logger.error("Unexpected error in ListQueriesTool: %s", str(e))
            yield self.create_text_message(json.dumps(handle_unexpected_error(e)))
