"""
Execute Query Tool for the Redash Extension for Dify plugin.

Executes a saved Redash query by ID, supporting parameterized queries and
cache control via max_age. Returns structured rows with column metadata.

Addresses: Requirement 3 (AC 1-9)
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
from utils.response_formatter import ResponseFormatter


logger = logging.getLogger(__name__)

# Execution timeout in seconds (Req 3, AC 6)
EXECUTION_TIMEOUT = 120


class ExecuteQueryTool(Tool):
    """
    Execute a saved Redash query and retrieve results.

    Parameters:
    - query_id (required): Positive integer ID of the query to execute
    - parameters (optional): JSON string of key-value pairs for parameterized queries
    - max_age (optional): Non-negative integer; maximum cache age in seconds (0 forces fresh execution)

    Returns:
    - JSON string with formatted query results or structured error
    """

    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage.TextMessage, None, None]:
        """
        Invoke the Execute Query tool.

        Steps:
        1. Validate query_id is a positive integer (Req 3, AC 7)
        2. Validate max_age is non-negative integer if provided (Req 3, AC 7)
        3. Parse parameters JSON string if provided (Req 3, AC 2, 9)
        4. Create RedashClient with provider credentials
        5. Call POST /api/queries/{id}/results with parameters and max_age (Req 3, AC 1, 4)
        6. Format results with ResponseFormatter (Req 3, AC 3)
        7. Handle errors: not found, timeout, execution error, invalid params

        Args:
            tool_parameters: Dict with 'query_id' (required), 'parameters' (optional),
                and 'max_age' (optional).

        Yields:
            ToolInvokeMessage.TextMessage with JSON response.
        """
        try:
            # Step 1: Validate query_id (Req 3, AC 7)
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

            # Step 2: Validate max_age (Req 3, AC 7)
            max_age = tool_parameters.get("max_age")
            if max_age is not None:
                try:
                    max_age = int(max_age)
                except (ValueError, TypeError):
                    error = PluginError(
                        error_code=ErrorCode.VALIDATION_ERROR,
                        message="Invalid max_age: must be a non-negative integer.",
                        details={"parameter": "max_age", "provided_value": str(tool_parameters.get("max_age"))},
                    )
                    yield self.create_text_message(json.dumps(format_error_response(error)))
                    return

                if max_age < 0:
                    error = PluginError(
                        error_code=ErrorCode.VALIDATION_ERROR,
                        message="Invalid max_age: must be a non-negative integer.",
                        details={"parameter": "max_age", "provided_value": max_age},
                    )
                    yield self.create_text_message(json.dumps(format_error_response(error)))
                    return

            # Step 3: Parse parameters JSON (Req 3, AC 2, 9)
            params_dict: dict[str, Any] = {}
            parameters_str = tool_parameters.get("parameters")
            if parameters_str is not None and parameters_str != "":
                try:
                    params_dict = json.loads(parameters_str)
                except (json.JSONDecodeError, TypeError):
                    error = PluginError(
                        error_code=ErrorCode.QUERY_INVALID_PARAMS,
                        message="Invalid parameters: must be a valid JSON object of key-value pairs.",
                        details={"parameter": "parameters", "provided_value": str(parameters_str)},
                    )
                    yield self.create_text_message(json.dumps(format_error_response(error)))
                    return

                if not isinstance(params_dict, dict):
                    error = PluginError(
                        error_code=ErrorCode.QUERY_INVALID_PARAMS,
                        message="Invalid parameters: must be a JSON object (key-value pairs), not an array or scalar.",
                        details={"parameter": "parameters"},
                    )
                    yield self.create_text_message(json.dumps(format_error_response(error)))
                    return

            # Step 4: Create RedashClient with credentials
            credentials = self.runtime.credentials
            base_url = credentials.get("redash_url", "")
            api_key = credentials.get("api_key", "")

            client = RedashClient(base_url=base_url, api_key=api_key)

            # Step 5: Call POST /api/queries/{id}/results (Req 3, AC 1, 4)
            request_body: dict[str, Any] = {}
            if params_dict:
                request_body["parameters"] = params_dict
            if max_age is not None:
                request_body["max_age"] = max_age

            try:
                response = client.request(
                    "POST",
                    f"/api/queries/{query_id}/results",
                    json=request_body,
                    timeout=(30, EXECUTION_TIMEOUT),
                )
            except PluginError as e:
                # Map specific errors (Req 3, AC 5, 6, 8)
                if e.error_code == ErrorCode.CONN_TIMEOUT:
                    # Timeout during query execution → QUERY_002
                    timeout_error = PluginError(
                        error_code=ErrorCode.QUERY_TIMEOUT,
                        message="Query execution timed out. The query took longer than 120 seconds to complete.",
                        details={"query_id": query_id, "timeout_seconds": EXECUTION_TIMEOUT},
                    )
                    yield self.create_text_message(json.dumps(format_error_response(timeout_error)))
                    return
                else:
                    # Re-raise to be caught by the outer PluginError handler
                    raise

            # Check if the response indicates an error from Redash
            # Redash may return a job object for async queries or an error in the response
            if "job" in response:
                # The query is still running asynchronously - treat as execution error
                error = PluginError(
                    error_code=ErrorCode.QUERY_EXECUTION_ERROR,
                    message="Query execution is still in progress. The query did not complete within the expected time.",
                    details={"query_id": query_id, "job_status": response["job"].get("status")},
                )
                yield self.create_text_message(json.dumps(format_error_response(error)))
                return

            # Check for query execution errors in the response
            if "query_result" in response:
                query_result = response["query_result"]
                if query_result.get("data", {}).get("error"):
                    error_message = query_result["data"]["error"]
                    error = PluginError(
                        error_code=ErrorCode.QUERY_EXECUTION_ERROR,
                        message=f"Query execution failed: {error_message}",
                        details={"query_id": query_id},
                    )
                    yield self.create_text_message(json.dumps(format_error_response(error)))
                    return

            # Step 6: Format results (Req 3, AC 3)
            formatter = ResponseFormatter()
            formatted_results = formatter.format_results(response)

            yield self.create_text_message(json.dumps(formatted_results))

        except PluginError as e:
            # Handle known errors
            logger.error("Execute query failed: %s (code: %s)", e.message, e.error_code.value)

            # Map 404 to QUERY_001 (Req 3, AC 5)
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
            # Handle unexpected errors (Req 9, AC 6)
            logger.error("Unexpected error in ExecuteQueryTool: %s", str(e))
            yield self.create_text_message(json.dumps(handle_unexpected_error(e)))
