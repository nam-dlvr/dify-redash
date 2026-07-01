"""
Get Query Results Tool for the Redash Extension for Dify plugin.

Retrieves cached results for a saved Redash query without triggering
a new execution. Uses GET /api/queries/{id}/results to fetch the most
recent cached results.

Addresses: Requirement 4 (AC 1-6)
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any, Generator

try:
    from dify_plugin import Tool
    from dify_plugin.entities.tool import ToolInvokeMessage
except ImportError:
    from tools._dify_stubs import Tool, ToolInvokeMessage

from utils.error_handler import ErrorCode, PluginError, format_error_response, handle_unexpected_error
from utils.redash_client import RedashClient
from utils.response_formatter import ResponseFormatter


logger = logging.getLogger(__name__)


class GetQueryResultsTool(Tool):
    """
    Retrieve cached results for a saved Redash query.

    Parameters:
    - query_id (required): Positive integer ID of the query to retrieve results for

    Returns:
    - JSON string with formatted cached query results or structured error
    """

    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage.TextMessage, None, None]:
        """
        Invoke the Get Query Results tool.

        Steps:
        1. Validate query_id is a positive integer (Task 8.3)
        2. Create RedashClient with provider credentials
        3. Call GET /api/queries/{id}/results (Task 8.4)
        4. Handle no cached results (Task 8.6)
        5. Format results with ResponseFormatter (Task 8.5)
        6. Add retrieval_timestamp to metadata (Task 8.5)
        7. Handle errors: not found (Task 8.7)

        Args:
            tool_parameters: Dict with 'query_id' (required).

        Yields:
            ToolInvokeMessage.TextMessage with JSON response.
        """
        try:
            # Step 1: Validate query_id (Task 8.3)
            query_id = tool_parameters.get("query_id")
            if query_id is None:
                error = PluginError(
                    error_code=ErrorCode.VALIDATION_ERROR,
                    message="query_id is required.",
                    details={"parameter": "query_id"},
                )
                yield self.create_text_message(json.dumps(format_error_response(error)))
                return

            try:
                query_id = int(query_id)
            except (ValueError, TypeError):
                error = PluginError(
                    error_code=ErrorCode.VALIDATION_ERROR,
                    message="Invalid query_id: must be a positive integer.",
                    details={"parameter": "query_id", "provided_value": str(tool_parameters.get("query_id"))},
                )
                yield self.create_text_message(json.dumps(format_error_response(error)))
                return

            if query_id <= 0:
                error = PluginError(
                    error_code=ErrorCode.VALIDATION_ERROR,
                    message="Invalid query_id: must be a positive integer.",
                    details={"parameter": "query_id", "provided_value": query_id},
                )
                yield self.create_text_message(json.dumps(format_error_response(error)))
                return

            # Step 2: Create RedashClient with credentials
            credentials = self.runtime.credentials
            base_url = credentials.get("redash_url", "")
            api_key = credentials.get("api_key", "")

            client = RedashClient(base_url=base_url, api_key=api_key)

            # Step 3: Call GET /api/queries/{id}/results (Task 8.4)
            try:
                response = client.request(
                    "GET",
                    f"/api/queries/{query_id}/results",
                )
            except PluginError as e:
                # Re-raise to be caught by the outer PluginError handler
                raise

            # Step 4: Handle no cached results (Task 8.6)
            # When Redash returns a response but there's no query_result data
            query_result = response.get("query_result")
            if query_result is None:
                result = {
                    "message": f"No cached results available for query ID {query_id}. "
                               "The query may not have been executed yet, or cached results have expired.",
                    "query_id": query_id,
                }
                yield self.create_text_message(json.dumps(result))
                return

            data = query_result.get("data")
            if data is None or (data.get("rows") is None and data.get("columns") is None):
                result = {
                    "message": f"No cached results available for query ID {query_id}. "
                               "The query may not have been executed yet, or cached results have expired.",
                    "query_id": query_id,
                }
                yield self.create_text_message(json.dumps(result))
                return

            # Step 5: Format results with ResponseFormatter (Task 8.5)
            formatter = ResponseFormatter()
            formatted_results = formatter.format_results(response)

            # Step 6: Add retrieval_timestamp to metadata (Task 8.5)
            retrieval_timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            formatted_results["metadata"]["retrieval_timestamp"] = retrieval_timestamp

            yield self.create_text_message(json.dumps(formatted_results))

        except PluginError as e:
            # Handle known errors
            logger.error("Get query results failed: %s (code: %s)", e.message, e.error_code.value)

            # Map 404 to QUERY_001 (Task 8.7)
            if e.details and e.details.get("http_status") == 404:
                not_found_error = PluginError(
                    error_code=ErrorCode.QUERY_NOT_FOUND,
                    message=f"Query with ID {tool_parameters.get('query_id')} was not found.",
                    details={"query_id": tool_parameters.get("query_id")},
                )
                yield self.create_text_message(json.dumps(format_error_response(not_found_error)))
            else:
                yield self.create_text_message(json.dumps(format_error_response(e)))

        except Exception as e:
            # Handle unexpected errors
            logger.error("Unexpected error in GetQueryResultsTool: %s", str(e))
            yield self.create_text_message(json.dumps(handle_unexpected_error(e)))
