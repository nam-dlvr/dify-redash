"""
Get Dashboard Details Tool for the Redash Extension for Dify plugin.

Retrieves detailed information about a specific Redash dashboard including
its widgets, associated queries, and optionally cached query results.

Addresses: Requirement 6 (AC 1-8)
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


class GetDashboardDetailsTool(Tool):
    """
    Retrieve detailed information about a specific Redash dashboard.

    Parameters:
    - dashboard_slug (required): Non-empty string slug identifier of the dashboard
    - include_results (optional): Boolean, whether to include cached query results (default false)

    Returns:
    - JSON string with dashboard details and widget information, or structured error
    """

    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage.TextMessage, None, None]:
        """
        Invoke the Get Dashboard Details tool.

        Steps:
        1. Validate dashboard_slug is non-empty and not whitespace-only (Task 10.3)
        2. Create RedashClient with provider credentials
        3. Call GET /api/dashboards/{slug} (Task 10.4)
        4. Map response to structured output (Task 10.5)
        5. If include_results=true, fetch cached results for widgets with queries (Task 10.6)
        6. Handle errors: not found (Task 10.7)

        Args:
            tool_parameters: Dict with 'dashboard_slug' (required) and 'include_results' (optional).

        Yields:
            ToolInvokeMessage.TextMessage with JSON response.
        """
        try:
            # Step 1: Validate dashboard_slug (Task 10.3, Req 6 AC 8)
            dashboard_slug = tool_parameters.get("dashboard_slug")
            if dashboard_slug is None or not isinstance(dashboard_slug, str) or not dashboard_slug.strip():
                error = PluginError(
                    error_code=ErrorCode.VALIDATION_ERROR,
                    message="A valid dashboard slug is required. The dashboard_slug parameter must be a non-empty string.",
                    details={"parameter": "dashboard_slug"},
                )
                yield self.create_text_message(json.dumps(format_error_response(error)))
                return

            dashboard_slug = dashboard_slug.strip()

            # Extract include_results parameter (default: false)
            include_results = tool_parameters.get("include_results", False)
            if isinstance(include_results, str):
                include_results = include_results.lower() in ("true", "1", "yes")

            # Step 2: Create RedashClient with credentials
            credentials = self.runtime.credentials
            base_url = credentials.get("redash_url", "")
            api_key = credentials.get("api_key", "")

            client = RedashClient(base_url=base_url, api_key=api_key)

            # Step 3: Call GET /api/dashboards/{slug} (Task 10.4, Req 6 AC 1)
            try:
                response = client.request("GET", f"/api/dashboards/{dashboard_slug}")
            except PluginError as e:
                # Check for 404 → dashboard not found (Task 10.7, Req 6 AC 5)
                if e.details and e.details.get("http_status") == 404:
                    not_found_error = PluginError(
                        error_code=ErrorCode.DASHBOARD_NOT_FOUND,
                        message=f"Dashboard with slug '{dashboard_slug}' was not found.",
                        details={"dashboard_slug": dashboard_slug},
                    )
                    yield self.create_text_message(json.dumps(format_error_response(not_found_error)))
                    return
                raise

            # Step 4: Map response to structured output (Task 10.5, Req 6 AC 2-3)
            widgets = self._extract_widgets(response.get("widgets", []))

            result: dict[str, Any] = {
                "name": response.get("name"),
                "slug": response.get("slug"),
                "created_at": response.get("created_at"),
                "updated_at": response.get("updated_at"),
                "widgets": widgets,
            }

            # Step 5: If include_results=true, fetch cached results (Task 10.6, Req 6 AC 4)
            if include_results:
                result["widgets"] = self._fetch_widget_results(client, widgets)

            yield self.create_text_message(json.dumps(result))

        except PluginError as e:
            # Handle known errors (Task 10.7, Req 6 AC 7)
            logger.error("Get dashboard details failed: %s (code: %s)", e.message, e.error_code.value)
            yield self.create_text_message(json.dumps(format_error_response(e)))

        except Exception as e:
            # Handle unexpected errors (Req 9, AC 6)
            logger.error("Unexpected error in GetDashboardDetailsTool: %s", str(e))
            yield self.create_text_message(json.dumps(handle_unexpected_error(e)))

    def _extract_widgets(self, raw_widgets: list[dict]) -> list[dict]:
        """
        Extract widget information from raw dashboard response.

        For each widget:
        - Include widget ID and type
        - If widget has visualization.query.id → query_id = that id, visualization_type = visualization.type
        - If widget has no visualization (e.g., textbox) → query_id = null, visualization_type = null

        Args:
            raw_widgets: List of widget dicts from Redash API response.

        Returns:
            List of standardized widget dicts with id, type, query_id, visualization_type.
        """
        widgets = []
        for widget in raw_widgets:
            widget_info: dict[str, Any] = {
                "id": widget.get("id"),
                "type": widget.get("type"),
                "query_id": None,
                "visualization_type": None,
            }

            # Check if widget has a visualization with a query
            visualization = widget.get("visualization")
            if visualization and isinstance(visualization, dict):
                query = visualization.get("query")
                if query and isinstance(query, dict):
                    widget_info["query_id"] = query.get("id")
                widget_info["visualization_type"] = visualization.get("type")

            widgets.append(widget_info)
        return widgets

    def _fetch_widget_results(self, client: RedashClient, widgets: list[dict]) -> list[dict]:
        """
        Fetch cached query results for widgets that have associated queries.

        For widgets with a query_id: fetch GET /api/queries/{id}/results and include results.
        For widgets without a query_id: indicate results are not available.

        Args:
            client: RedashClient instance for API calls.
            widgets: List of widget dicts with query_id information.

        Returns:
            Updated widgets list with results or unavailability indicators.
        """
        formatter = ResponseFormatter()
        enriched_widgets = []

        for widget in widgets:
            enriched_widget = dict(widget)
            query_id = widget.get("query_id")

            if query_id is not None:
                # Fetch cached results for this widget's query
                try:
                    response = client.request("GET", f"/api/queries/{query_id}/results")
                    query_result = response.get("query_result")
                    if query_result and query_result.get("data"):
                        formatted_results = formatter.format_results(response)
                        enriched_widget["results"] = formatted_results
                    else:
                        enriched_widget["results_available"] = False
                        enriched_widget["results_message"] = "No cached results available for this query."
                except PluginError:
                    enriched_widget["results_available"] = False
                    enriched_widget["results_message"] = "Unable to retrieve results for this query."
            else:
                # Widget has no associated query (e.g., textbox)
                enriched_widget["results_available"] = False
                enriched_widget["results_message"] = "This widget has no associated query."

            enriched_widgets.append(enriched_widget)

        return enriched_widgets
