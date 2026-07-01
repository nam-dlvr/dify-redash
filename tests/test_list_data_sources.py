"""
Tests for the List Data Sources Tool (tools/list_data_sources.py).

Covers:
- Task 11.1: YAML tool definition structure
- Task 11.2: ListDataSourcesTool class structure
- Task 11.3: API call to GET /api/data_sources with 30-second timeout
- Task 11.4: Response mapping - extract data source ID, name, type, created_at
- Task 11.5: Handle empty list response - return empty collection with no error
- Task 11.6: Handle API errors and network/timeout failures
"""

import json
from unittest.mock import MagicMock, patch

import pytest
import yaml

from tools._dify_stubs import Tool, ToolRuntime
from tools.list_data_sources import ListDataSourcesTool, DATA_SOURCES_TIMEOUT
from utils.error_handler import ErrorCode, PluginError


def _make_tool(credentials: dict | None = None) -> ListDataSourcesTool:
    """Create a ListDataSourcesTool instance with mock runtime credentials."""
    tool = ListDataSourcesTool()
    tool.runtime = ToolRuntime(credentials=credentials or {
        "redash_url": "https://redash.example.com",
        "api_key": "test-api-key-1234",
    })
    return tool


def _invoke_tool(tool: ListDataSourcesTool, params: dict | None = None) -> list[dict]:
    """Invoke the tool and collect all text messages as parsed JSON."""
    results = []
    for msg in tool._invoke(params or {}):
        results.append(json.loads(msg.text))
    return results


class TestYamlDefinition:
    """Test YAML tool definition file (Task 11.1)."""

    def test_yaml_loads_correctly(self):
        with open("tools/list_data_sources.yaml") as f:
            data = yaml.safe_load(f)
        assert data is not None

    def test_yaml_has_identity(self):
        with open("tools/list_data_sources.yaml") as f:
            data = yaml.safe_load(f)
        assert data["identity"]["name"] == "list_data_sources"
        assert "label" in data["identity"]
        assert "en_US" in data["identity"]["label"]

    def test_yaml_has_description(self):
        with open("tools/list_data_sources.yaml") as f:
            data = yaml.safe_load(f)
        assert "human" in data["description"]
        assert "llm" in data["description"]

    def test_yaml_has_no_required_parameters(self):
        with open("tools/list_data_sources.yaml") as f:
            data = yaml.safe_load(f)
        assert data["parameters"] == []


class TestListDataSourcesToolClass:
    """Test ListDataSourcesTool class (Task 11.2)."""

    def test_extends_tool_base_class(self):
        tool = ListDataSourcesTool()
        assert isinstance(tool, Tool)

    def test_has_invoke_method(self):
        tool = ListDataSourcesTool()
        assert hasattr(tool, "_invoke")
        assert callable(tool._invoke)


class TestApiCall:
    """Test API call with 30-second timeout (Task 11.3)."""

    @patch("tools.list_data_sources.RedashClient")
    def test_calls_get_api_data_sources(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.request.return_value = []
        mock_client_cls.return_value = mock_client

        tool = _make_tool()
        _invoke_tool(tool)

        mock_client.request.assert_called_once_with(
            "GET", "/api/data_sources", timeout=DATA_SOURCES_TIMEOUT
        )

    @patch("tools.list_data_sources.RedashClient")
    def test_uses_30_second_timeout(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.request.return_value = []
        mock_client_cls.return_value = mock_client

        tool = _make_tool()
        _invoke_tool(tool)

        call_kwargs = mock_client.request.call_args
        assert call_kwargs[1]["timeout"] == (30, 30)

    @patch("tools.list_data_sources.RedashClient")
    def test_uses_provided_credentials(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.request.return_value = []
        mock_client_cls.return_value = mock_client

        tool = _make_tool({
            "redash_url": "https://my-redash.com",
            "api_key": "my-key-5678",
        })
        _invoke_tool(tool)

        mock_client_cls.assert_called_once_with(
            base_url="https://my-redash.com",
            api_key="my-key-5678",
        )


class TestResponseMapping:
    """Test response field extraction (Task 11.4)."""

    @patch("tools.list_data_sources.RedashClient")
    def test_extracts_required_fields(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.request.return_value = [
            {
                "id": 1,
                "name": "PostgreSQL",
                "type": "pg",
                "created_at": "2024-01-01T00:00:00Z",
                "syntax": "sql",
                "paused": 0,
                "pause_reason": None,
            }
        ]
        mock_client_cls.return_value = mock_client

        tool = _make_tool()
        results = _invoke_tool(tool)

        assert len(results) == 1
        data_sources = results[0]["data_sources"]
        assert len(data_sources) == 1

        ds = data_sources[0]
        assert ds["id"] == 1
        assert ds["name"] == "PostgreSQL"
        assert ds["type"] == "pg"
        assert ds["created_at"] == "2024-01-01T00:00:00Z"

        # Should NOT include extra fields
        assert "syntax" not in ds
        assert "paused" not in ds
        assert "pause_reason" not in ds

    @patch("tools.list_data_sources.RedashClient")
    def test_maps_multiple_data_sources(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.request.return_value = [
            {"id": 1, "name": "PostgreSQL", "type": "pg", "created_at": "2024-01-01T00:00:00Z"},
            {"id": 2, "name": "MySQL", "type": "mysql", "created_at": "2024-02-01T00:00:00Z"},
            {"id": 3, "name": "BigQuery", "type": "bigquery", "created_at": "2024-03-01T00:00:00Z"},
        ]
        mock_client_cls.return_value = mock_client

        tool = _make_tool()
        results = _invoke_tool(tool)

        data_sources = results[0]["data_sources"]
        assert len(data_sources) == 3
        assert data_sources[0]["id"] == 1
        assert data_sources[0]["name"] == "PostgreSQL"
        assert data_sources[1]["id"] == 2
        assert data_sources[1]["name"] == "MySQL"
        assert data_sources[2]["id"] == 3
        assert data_sources[2]["name"] == "BigQuery"

    @patch("tools.list_data_sources.RedashClient")
    def test_created_at_is_iso_8601(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.request.return_value = [
            {"id": 1, "name": "PG", "type": "pg", "created_at": "2024-01-15T10:30:00Z"},
        ]
        mock_client_cls.return_value = mock_client

        tool = _make_tool()
        results = _invoke_tool(tool)

        ds = results[0]["data_sources"][0]
        assert ds["created_at"] == "2024-01-15T10:30:00Z"


class TestEmptyResponse:
    """Test empty list handling (Task 11.5)."""

    @patch("tools.list_data_sources.RedashClient")
    def test_empty_array_returns_empty_collection(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.request.return_value = []
        mock_client_cls.return_value = mock_client

        tool = _make_tool()
        results = _invoke_tool(tool)

        assert len(results) == 1
        assert results[0]["data_sources"] == []
        assert "error" not in results[0]

    @patch("tools.list_data_sources.RedashClient")
    def test_non_list_response_returns_empty_collection(self, mock_client_cls):
        """If API returns unexpected format, treat as empty."""
        mock_client = MagicMock()
        mock_client.request.return_value = {}
        mock_client_cls.return_value = mock_client

        tool = _make_tool()
        results = _invoke_tool(tool)

        assert results[0]["data_sources"] == []
        assert "error" not in results[0]


class TestErrorHandling:
    """Test error handling paths (Task 11.6)."""

    @patch("tools.list_data_sources.RedashClient")
    def test_api_auth_error_returns_structured_error(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.request.side_effect = PluginError(
            error_code=ErrorCode.AUTH_INVALID_CREDENTIALS,
            message="Authentication failed: invalid or expired API credentials.",
            details={"http_status": 401},
        )
        mock_client_cls.return_value = mock_client

        tool = _make_tool()
        results = _invoke_tool(tool)

        assert results[0]["error"] is True
        assert results[0]["error_code"] == "AUTH_001"

    @patch("tools.list_data_sources.RedashClient")
    def test_api_server_error_returns_structured_error(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.request.side_effect = PluginError(
            error_code=ErrorCode.SERVER_ERROR,
            message="A Redash server-side error occurred.",
            details={"http_status": 500},
        )
        mock_client_cls.return_value = mock_client

        tool = _make_tool()
        results = _invoke_tool(tool)

        assert results[0]["error"] is True
        assert results[0]["error_code"] == "SERVER_001"
        assert results[0]["details"]["http_status"] == 500

    @patch("tools.list_data_sources.RedashClient")
    def test_connection_error_returns_structured_error(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.request.side_effect = PluginError(
            error_code=ErrorCode.CONN_UNREACHABLE,
            message="Unable to connect to the Redash instance.",
            details={"host": "redash.example.com", "error_type": "ConnectionError"},
        )
        mock_client_cls.return_value = mock_client

        tool = _make_tool()
        results = _invoke_tool(tool)

        assert results[0]["error"] is True
        assert results[0]["error_code"] == "CONN_001"

    @patch("tools.list_data_sources.RedashClient")
    def test_timeout_error_returns_structured_error(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.request.side_effect = PluginError(
            error_code=ErrorCode.CONN_TIMEOUT,
            message="Connection to Redash timed out.",
            details={"host": "redash.example.com", "timeout_type": "connection"},
        )
        mock_client_cls.return_value = mock_client

        tool = _make_tool()
        results = _invoke_tool(tool)

        assert results[0]["error"] is True
        assert results[0]["error_code"] == "CONN_002"

    @patch("tools.list_data_sources.RedashClient")
    def test_unexpected_error_returns_sanitized_error(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.request.side_effect = RuntimeError("Something unexpected happened")
        mock_client_cls.return_value = mock_client

        tool = _make_tool()
        results = _invoke_tool(tool)

        assert results[0]["error"] is True
        assert results[0]["error_code"] == "UNEXPECTED_001"
        # Should not contain internal details
        assert "RuntimeError" not in results[0]["message"]
        assert "Something unexpected happened" not in results[0]["message"]

    @patch("tools.list_data_sources.RedashClient")
    def test_permission_error_returns_structured_error(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.request.side_effect = PluginError(
            error_code=ErrorCode.AUTH_INSUFFICIENT_PERMISSIONS,
            message="Insufficient permissions for the requested resource.",
            details={"http_status": 403},
        )
        mock_client_cls.return_value = mock_client

        tool = _make_tool()
        results = _invoke_tool(tool)

        assert results[0]["error"] is True
        assert results[0]["error_code"] == "AUTH_002"
