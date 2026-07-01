"""
List Data Sources Tool for the Redash Extension for Dify plugin.

Retrieves all configured data sources from the Redash API. Returns a list
of data source objects with ID, name, type, and creation date.

Addresses: Requirement 11 (AC 1-6)
"""

import json
import logging
from typing import Any, Generator

try:
    from dify_plugin import Tool
    from dify_plugin.entities.tool import ToolInvokeMessage
except ImportError:
    from tools._dify_stubs import Tool, ToolInvokeMessage

from utils.error_handler import PluginError, format_error_response, handle_unexpected_error
from utils.redash_client import RedashClient


logger = logging.getLogger(__name__)

# Timeout configuration for data sources endpoint (seconds)
DATA_SOURCES_TIMEOUT = (30, 30)


class ListDataSourcesTool(Tool):
    """
    List all data sources from the connected Redash instance.

    No input parameters required.

    Returns:
    - JSON string with list of data source objects or structured error
    """

    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage.TextMessage, None, None]:
        """
        Invoke the List Data Sources tool.

        Steps:
        1. Create RedashClient with provider credentials
        2. Call GET /api/data_sources with 30-second timeout
        3. Map response to standardized output (id, name, type, created_at)
        4. Return results or structured error

        Args:
            tool_parameters: Dict (no parameters required for this tool).

        Yields:
            ToolInvokeMessage.TextMessage with JSON response.
        """
        try:
            # Step 1: Create RedashClient with credentials
            credentials = self.runtime.credentials
            base_url = credentials.get("redash_url", "")
            api_key = credentials.get("api_key", "")

            client = RedashClient(base_url=base_url, api_key=api_key)

            # Step 2: Call GET /api/data_sources with 30-second timeout
            response = client.request(
                "GET", "/api/data_sources", timeout=DATA_SOURCES_TIMEOUT
            )

            # Step 3: Map response to standardized output
            # Redash API returns a simple array of data source objects
            if not isinstance(response, list):
                response = []

            data_sources = []
            for ds in response:
                data_sources.append({
                    "id": ds.get("id"),
                    "name": ds.get("name"),
                    "type": ds.get("type"),
                    "created_at": ds.get("created_at"),
                })

            # Step 4: Return results (empty list if no data sources)
            yield self.create_text_message(json.dumps({"data_sources": data_sources}))

        except PluginError as e:
            # Return structured error for API failures
            logger.error("List data sources failed: %s (code: %s)", e.message, e.error_code.value)
            yield self.create_text_message(json.dumps(format_error_response(e)))

        except Exception as e:
            # Handle unexpected errors
            logger.error("Unexpected error in ListDataSourcesTool: %s", str(e))
            yield self.create_text_message(json.dumps(handle_unexpected_error(e)))
