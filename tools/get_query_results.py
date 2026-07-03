"""
Get Query Results Tool for the Redash Extension for Dify plugin.

Retrieves query results either from cache (by query_id) or by polling
a running job (by job_id). Supports the async query execution flow.

Addresses: Requirement 4 (AC 1-6)
"""

import json
import logging
import time
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

# Job polling configuration
MAX_POLL_ATTEMPTS = 60  # Maximum number of polling attempts
POLL_INTERVAL = 2  # Seconds between polls


class GetQueryResultsTool(Tool):
    """
    Retrieve query results from Redash.

    Supports two modes:
    1. By query_id: retrieves cached results (GET /api/queries/{id}/results)
    2. By job_id: polls a running job until completion and returns results

    Parameters:
    - query_id (optional): Positive integer ID of the query to retrieve cached results for
    - job_id (optional): Job ID from execute_query to poll for completion

    At least one of query_id or job_id must be provided.

    Returns:
    - JSON string with formatted query results or structured error
    """

    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage.TextMessage, None, None]:
        try:
            # Get parameters
            query_id = tool_parameters.get("query_id")
            job_id = tool_parameters.get("job_id")

            # Validate at least one is provided
            if query_id is None and (job_id is None or job_id == ""):
                error = PluginError(
                    error_code=ErrorCode.VALIDATION_ERROR,
                    message="Either query_id or job_id must be provided.",
                    details={"parameter": "query_id or job_id"},
                )
                yield self.create_text_message(json.dumps(format_error_response(error)))
                return

            # Create RedashClient with credentials
            credentials = self.runtime.credentials
            base_url = credentials.get("redash_url", "")
            api_key = credentials.get("api_key", "")
            client = RedashClient(base_url=base_url, api_key=api_key)

            # Mode 1: Poll by job_id
            if job_id and str(job_id).strip():
                job_id = str(job_id).strip()
                yield from self._poll_job(client, job_id)
                return

            # Mode 2: Get cached results by query_id
            if query_id is not None:
                try:
                    query_id = int(query_id)
                except (ValueError, TypeError):
                    error = PluginError(
                        error_code=ErrorCode.VALIDATION_ERROR,
                        message="Invalid query_id: must be a positive integer.",
                        details={"parameter": "query_id", "provided_value": str(query_id)},
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

                yield from self._get_cached_results(client, query_id)
                return

        except PluginError as e:
            logger.error("Get query results failed: %s (code: %s)", e.message, e.error_code.value)
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
            logger.error("Unexpected error in GetQueryResultsTool: %s", str(e))
            yield self.create_text_message(json.dumps(handle_unexpected_error(e)))

    def _poll_job(
        self, client: RedashClient, job_id: str
    ) -> Generator[ToolInvokeMessage.TextMessage, None, None]:
        """Poll a Redash job until completion and return results."""
        for attempt in range(MAX_POLL_ATTEMPTS):
            response = client.request("GET", f"/api/jobs/{job_id}")
            job = response.get("job", response)

            status = job.get("status")

            # Status 3 = success
            if status == 3:
                query_result_id = job.get("query_result_id")
                if query_result_id:
                    # Fetch the actual results
                    result_response = client.request("GET", f"/api/query_results/{query_result_id}")
                    formatter = ResponseFormatter()
                    formatted_results = formatter.format_results(result_response)
                    retrieval_timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                    formatted_results["metadata"]["retrieval_timestamp"] = retrieval_timestamp
                    yield self.create_text_message(json.dumps(formatted_results))
                    return
                else:
                    # No result ID yet, but job succeeded
                    yield self.create_text_message(json.dumps({
                        "status": "completed",
                        "message": "Job completed but no query_result_id found.",
                        "job_id": job_id,
                    }))
                    return

            # Status 4 = failure
            elif status == 4:
                error_message = job.get("error", "Query execution failed.")
                error = PluginError(
                    error_code=ErrorCode.QUERY_EXECUTION_ERROR,
                    message=f"Query execution failed: {error_message}",
                    details={"job_id": job_id, "status": status},
                )
                yield self.create_text_message(json.dumps(format_error_response(error)))
                return

            # Status 1 (pending) or 2 (started) - keep polling
            time.sleep(POLL_INTERVAL)

        # Exhausted all polling attempts
        yield self.create_text_message(json.dumps({
            "status": "timeout",
            "message": f"Job did not complete within {MAX_POLL_ATTEMPTS * POLL_INTERVAL} seconds.",
            "job_id": job_id,
        }))

    def _get_cached_results(
        self, client: RedashClient, query_id: int
    ) -> Generator[ToolInvokeMessage.TextMessage, None, None]:
        """Get cached results for a query."""
        response = client.request("GET", f"/api/queries/{query_id}/results")

        # Handle no cached results
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

        # Format results
        formatter = ResponseFormatter()
        formatted_results = formatter.format_results(response)
        retrieval_timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        formatted_results["metadata"]["retrieval_timestamp"] = retrieval_timestamp

        yield self.create_text_message(json.dumps(formatted_results))
