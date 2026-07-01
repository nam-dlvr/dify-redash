"""
Tests for the List Queries Tool (tools/list_queries.py).

Covers:
- Task 6.1: YAML tool definition structure
- Task 6.2: ListQueriesTool class structure
- Task 6.3: Input validation - page_size between 1-250, default 25
- Task 6.4: API call to GET /api/queries with pagination and search parameters
- Task 6.5: Response mapping - extract query ID, name, description, data_source_id, created_at, updated_at
- Task 6.6: Case-insensitive substring filtering for search term against query name
- Task 6.7: Handle empty results, invalid page_size, and API errors
"""

import json
from unittest.mock import MagicMock, patch

import pytest
import yaml

from tools._dify_stubs import Tool, ToolRuntime
from tools.list_queries import ListQueriesTool, DEFAULT_PAGE_SIZE, MIN_PAGE_SIZE, MAX_PAGE_SIZE
from utils.error_handler import ErrorCode, PluginError


def _make_tool(credentials: dict | None = None) -> ListQueriesTool:
    """Create a ListQueriesTool instance with mock runtime credentials."""
    tool = ListQueriesTool()
    tool.runtime = ToolRuntime(credentials=credentials or {
        "redash_url": "https://redash.example.com",
        "api_key": "test-api-key-1234",
    })
    return tool


def _invoke_tool(tool: ListQueriesTool, params: dict) -> list[dict]:
    """Invoke the tool and collect all text messages as parsed JSON."""
    results = []
    for msg in tool._invoke(params):
        results.append(json.loads(msg.text))
    return results


class TestYamlDefinition:
    """Test YAML tool definition file (Task 6.1)."""

    def test_yaml_loads_correctly(self):
        with open("tools/list_queries.yaml") as f:
            data = yaml.safe_load(f)
        assert data is not None

    def test_yaml_has_identity(self):
        with open("tools/list_queries.yaml") as f:
            data = yaml.safe_load(f)
        assert data["identity"]["name"] == "list_queries"
        assert "label" in data["identity"]
        assert "en_US" in data["identity"]["label"]

    def test_yaml_has_description(self):
        with open("tools/list_queries.yaml") as f:
            data = yaml.safe_load(f)
        assert "human" in data["description"]
        assert "llm" in data["description"]

    def test_yaml_has_parameters(self):
        with open("tools/list_queries.yaml") as f:
            data = yaml.safe_load(f)
        params = data["parameters"]
        assert len(params) == 2

        param_names = [p["name"] for p in params]
        assert "page_size" in param_names
        assert "search" in param_names

    def test_yaml_page_size_is_optional_number(self):
        with open("tools/list_queries.yaml") as f:
            data = yaml.safe_load(f)
        page_size_param = next(p for p in data["parameters"] if p["name"] == "page_size")
        assert page_size_param["type"] == "number"
        assert page_size_param["required"] is False

    def test_yaml_search_is_optional_string(self):
        with open("tools/list_queries.yaml") as f:
            data = yaml.safe_load(f)
        search_param = next(p for p in data["parameters"] if p["name"] == "search")
        assert search_param["type"] == "string"
        assert search_param["required"] is False


class TestListQueriesToolClass:
    """Test ListQueriesTool class (Task 6.2)."""

    def test_extends_tool_base_class(self):
        tool = ListQueriesTool()
        assert isinstance(tool, Tool)

    def test_has_invoke_method(self):
        tool = ListQueriesTool()
        assert hasattr(tool, "_invoke")
        assert callable(tool._invoke)


class TestInputValidation:
    """Test page_size validation (Task 6.3)."""

    @patch("tools.list_queries.RedashClient")
    def test_default_page_size_is_25(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.request.return_value = {"results": []}
        mock_client_cls.return_value = mock_client

        tool = _make_tool()
        _invoke_tool(tool, {})

        mock_client.request.assert_called_once()
        call_kwargs = mock_client.request.call_args
        assert call_kwargs[1]["params"]["page_size"] == DEFAULT_PAGE_SIZE

    @patch("tools.list_queries.RedashClient")
    def test_valid_page_size_is_used(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.request.return_value = {"results": []}
        mock_client_cls.return_value = mock_client

        tool = _make_tool()
        _invoke_tool(tool, {"page_size": 50})

        call_kwargs = mock_client.request.call_args
        assert call_kwargs[1]["params"]["page_size"] == 50

    def test_page_size_below_minimum_returns_error(self):
        tool = _make_tool()
        results = _invoke_tool(tool, {"page_size": 0})

        assert len(results) == 1
        assert results[0]["error"] is True
        assert results[0]["error_code"] == "VAL_001"

    def test_page_size_above_maximum_returns_error(self):
        tool = _make_tool()
        results = _invoke_tool(tool, {"page_size": 251})

        assert len(results) == 1
        assert results[0]["error"] is True
        assert results[0]["error_code"] == "VAL_001"

    def test_page_size_non_numeric_returns_error(self):
        tool = _make_tool()
        results = _invoke_tool(tool, {"page_size": "abc"})

        assert len(results) == 1
        assert results[0]["error"] is True
        assert results[0]["error_code"] == "VAL_001"

    @patch("tools.list_queries.RedashClient")
    def test_page_size_at_minimum_boundary(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.request.return_value = {"results": []}
        mock_client_cls.return_value = mock_client

        tool = _make_tool()
        _invoke_tool(tool, {"page_size": 1})

        call_kwargs = mock_client.request.call_args
        assert call_kwargs[1]["params"]["page_size"] == 1

    @patch("tools.list_queries.RedashClient")
    def test_page_size_at_maximum_boundary(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.request.return_value = {"results": []}
        mock_client_cls.return_value = mock_client

        tool = _make_tool()
        _invoke_tool(tool, {"page_size": 250})

        call_kwargs = mock_client.request.call_args
        assert call_kwargs[1]["params"]["page_size"] == 250


class TestApiCall:
    """Test API call with pagination and search (Task 6.4)."""

    @patch("tools.list_queries.RedashClient")
    def test_calls_get_api_queries(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.request.return_value = {"results": []}
        mock_client_cls.return_value = mock_client

        tool = _make_tool()
        _invoke_tool(tool, {})

        mock_client.request.assert_called_once_with(
            "GET", "/api/queries", params={"page_size": 25}
        )

    @patch("tools.list_queries.RedashClient")
    def test_passes_search_as_q_param(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.request.return_value = {"results": []}
        mock_client_cls.return_value = mock_client

        tool = _make_tool()
        _invoke_tool(tool, {"search": "revenue"})

        mock_client.request.assert_called_once_with(
            "GET", "/api/queries", params={"page_size": 25, "q": "revenue"}
        )

    @patch("tools.list_queries.RedashClient")
    def test_uses_provided_credentials(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.request.return_value = {"results": []}
        mock_client_cls.return_value = mock_client

        tool = _make_tool({
            "redash_url": "https://my-redash.com",
            "api_key": "my-key-5678",
        })
        _invoke_tool(tool, {})

        mock_client_cls.assert_called_once_with(
            base_url="https://my-redash.com",
            api_key="my-key-5678",
        )


class TestResponseMapping:
    """Test response field extraction (Task 6.5)."""

    @patch("tools.list_queries.RedashClient")
    def test_extracts_required_fields(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.request.return_value = {
            "results": [
                {
                    "id": 42,
                    "name": "Revenue Report",
                    "description": "Monthly revenue",
                    "data_source_id": 1,
                    "created_at": "2024-01-15T10:00:00Z",
                    "updated_at": "2024-06-20T14:30:00Z",
                    "schedule": {"interval": 3600},
                    "user": {"name": "Admin"},
                    "is_archived": False,
                }
            ]
        }
        mock_client_cls.return_value = mock_client

        tool = _make_tool()
        results = _invoke_tool(tool, {})

        assert len(results) == 1
        queries = results[0]["queries"]
        assert len(queries) == 1

        query = queries[0]
        assert query["id"] == 42
        assert query["name"] == "Revenue Report"
        assert query["description"] == "Monthly revenue"
        assert query["data_source_id"] == 1
        assert query["created_at"] == "2024-01-15T10:00:00Z"
        assert query["updated_at"] == "2024-06-20T14:30:00Z"

        # Should NOT include extra fields
        assert "schedule" not in query
        assert "user" not in query
        assert "is_archived" not in query

    @patch("tools.list_queries.RedashClient")
    def test_maps_multiple_queries(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.request.return_value = {
            "results": [
                {"id": 1, "name": "Q1", "description": "D1", "data_source_id": 1, "created_at": "2024-01-01", "updated_at": "2024-02-01"},
                {"id": 2, "name": "Q2", "description": "D2", "data_source_id": 2, "created_at": "2024-03-01", "updated_at": "2024-04-01"},
            ]
        }
        mock_client_cls.return_value = mock_client

        tool = _make_tool()
        results = _invoke_tool(tool, {})

        queries = results[0]["queries"]
        assert len(queries) == 2
        assert queries[0]["id"] == 1
        assert queries[1]["id"] == 2


class TestSearchFiltering:
    """Test case-insensitive substring filtering (Task 6.6)."""

    @patch("tools.list_queries.RedashClient")
    def test_filters_by_name_case_insensitive(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.request.return_value = {
            "results": [
                {"id": 1, "name": "Revenue Report", "description": "", "data_source_id": 1, "created_at": "", "updated_at": ""},
                {"id": 2, "name": "User Signup Count", "description": "", "data_source_id": 1, "created_at": "", "updated_at": ""},
                {"id": 3, "name": "REVENUE Analysis", "description": "", "data_source_id": 2, "created_at": "", "updated_at": ""},
            ]
        }
        mock_client_cls.return_value = mock_client

        tool = _make_tool()
        results = _invoke_tool(tool, {"search": "revenue"})

        queries = results[0]["queries"]
        assert len(queries) == 2
        assert queries[0]["name"] == "Revenue Report"
        assert queries[1]["name"] == "REVENUE Analysis"

    @patch("tools.list_queries.RedashClient")
    def test_substring_match(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.request.return_value = {
            "results": [
                {"id": 1, "name": "Monthly Revenue", "description": "", "data_source_id": 1, "created_at": "", "updated_at": ""},
                {"id": 2, "name": "Daily Users", "description": "", "data_source_id": 1, "created_at": "", "updated_at": ""},
            ]
        }
        mock_client_cls.return_value = mock_client

        tool = _make_tool()
        results = _invoke_tool(tool, {"search": "evenu"})

        queries = results[0]["queries"]
        assert len(queries) == 1
        assert queries[0]["name"] == "Monthly Revenue"

    @patch("tools.list_queries.RedashClient")
    def test_no_matches_returns_empty_list(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.request.return_value = {
            "results": [
                {"id": 1, "name": "Revenue Report", "description": "", "data_source_id": 1, "created_at": "", "updated_at": ""},
            ]
        }
        mock_client_cls.return_value = mock_client

        tool = _make_tool()
        results = _invoke_tool(tool, {"search": "nonexistent"})

        queries = results[0]["queries"]
        assert len(queries) == 0


class TestErrorHandling:
    """Test error handling paths (Task 6.7)."""

    @patch("tools.list_queries.RedashClient")
    def test_empty_results_returns_empty_list(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.request.return_value = {"results": []}
        mock_client_cls.return_value = mock_client

        tool = _make_tool()
        results = _invoke_tool(tool, {})

        assert results[0]["queries"] == []

    def test_invalid_page_size_returns_validation_error(self):
        tool = _make_tool()
        results = _invoke_tool(tool, {"page_size": -5})

        assert results[0]["error"] is True
        assert results[0]["error_code"] == "VAL_001"
        assert "page_size" in results[0]["message"].lower()

    @patch("tools.list_queries.RedashClient")
    def test_api_auth_error_returns_structured_error(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.request.side_effect = PluginError(
            error_code=ErrorCode.AUTH_INVALID_CREDENTIALS,
            message="Authentication failed: invalid or expired API credentials.",
            details={"http_status": 401},
        )
        mock_client_cls.return_value = mock_client

        tool = _make_tool()
        results = _invoke_tool(tool, {})

        assert results[0]["error"] is True
        assert results[0]["error_code"] == "AUTH_001"

    @patch("tools.list_queries.RedashClient")
    def test_api_server_error_returns_structured_error(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.request.side_effect = PluginError(
            error_code=ErrorCode.SERVER_ERROR,
            message="A Redash server-side error occurred.",
            details={"http_status": 500},
        )
        mock_client_cls.return_value = mock_client

        tool = _make_tool()
        results = _invoke_tool(tool, {})

        assert results[0]["error"] is True
        assert results[0]["error_code"] == "SERVER_001"
        assert results[0]["details"]["http_status"] == 500

    @patch("tools.list_queries.RedashClient")
    def test_connection_error_returns_structured_error(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.request.side_effect = PluginError(
            error_code=ErrorCode.CONN_UNREACHABLE,
            message="Unable to connect to the Redash instance.",
            details={"host": "redash.example.com", "error_type": "ConnectionError"},
        )
        mock_client_cls.return_value = mock_client

        tool = _make_tool()
        results = _invoke_tool(tool, {})

        assert results[0]["error"] is True
        assert results[0]["error_code"] == "CONN_001"

    @patch("tools.list_queries.RedashClient")
    def test_unexpected_error_returns_sanitized_error(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.request.side_effect = RuntimeError("Something unexpected happened")
        mock_client_cls.return_value = mock_client

        tool = _make_tool()
        results = _invoke_tool(tool, {})

        assert results[0]["error"] is True
        assert results[0]["error_code"] == "UNEXPECTED_001"
        # Should not contain internal details
        assert "RuntimeError" not in results[0]["message"]
        assert "Something unexpected happened" not in results[0]["message"]
