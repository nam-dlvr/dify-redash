"""
Tests for the List Dashboards Tool (tools/list_dashboards.py).

Covers:
- Task 9.1: YAML tool definition structure
- Task 9.2: ListDashboardsTool class structure
- Task 9.3: Input validation - page_size 1-250 (default 25), page default 1, search 1-200 chars
- Task 9.4: API call to GET /api/dashboards with pagination and search parameters
- Task 9.5: Response mapping - extract dashboard ID, name, slug, created_at, updated_at
- Task 9.6: Handle empty results: return empty list with total_count: 0
- Task 9.7: Handle API errors: return structured error with HTTP status code
"""

import json
from unittest.mock import MagicMock, patch

import pytest
import yaml

from tools._dify_stubs import Tool, ToolRuntime
from tools.list_dashboards import (
    ListDashboardsTool,
    DEFAULT_PAGE_SIZE,
    DEFAULT_PAGE,
    MIN_PAGE_SIZE,
    MAX_PAGE_SIZE,
    MIN_SEARCH_LENGTH,
    MAX_SEARCH_LENGTH,
)
from utils.error_handler import ErrorCode, PluginError


def _make_tool(credentials: dict | None = None) -> ListDashboardsTool:
    """Create a ListDashboardsTool instance with mock runtime credentials."""
    tool = ListDashboardsTool()
    tool.runtime = ToolRuntime(credentials=credentials or {
        "redash_url": "https://redash.example.com",
        "api_key": "test-api-key-1234",
    })
    return tool


def _invoke_tool(tool: ListDashboardsTool, params: dict) -> list[dict]:
    """Invoke the tool and collect all text messages as parsed JSON."""
    results = []
    for msg in tool._invoke(params):
        results.append(json.loads(msg.text))
    return results


class TestYamlDefinition:
    """Test YAML tool definition file (Task 9.1)."""

    def test_yaml_loads_correctly(self):
        with open("tools/list_dashboards.yaml") as f:
            data = yaml.safe_load(f)
        assert data is not None

    def test_yaml_has_identity(self):
        with open("tools/list_dashboards.yaml") as f:
            data = yaml.safe_load(f)
        assert data["identity"]["name"] == "list_dashboards"
        assert "label" in data["identity"]
        assert "en_US" in data["identity"]["label"]

    def test_yaml_has_description(self):
        with open("tools/list_dashboards.yaml") as f:
            data = yaml.safe_load(f)
        assert "human" in data["description"]
        assert "llm" in data["description"]

    def test_yaml_has_parameters(self):
        with open("tools/list_dashboards.yaml") as f:
            data = yaml.safe_load(f)
        params = data["parameters"]
        assert len(params) == 3

        param_names = [p["name"] for p in params]
        assert "page_size" in param_names
        assert "page" in param_names
        assert "search" in param_names

    def test_yaml_page_size_is_optional_number(self):
        with open("tools/list_dashboards.yaml") as f:
            data = yaml.safe_load(f)
        page_size_param = next(p for p in data["parameters"] if p["name"] == "page_size")
        assert page_size_param["type"] == "number"
        assert page_size_param["required"] is False

    def test_yaml_page_is_optional_number(self):
        with open("tools/list_dashboards.yaml") as f:
            data = yaml.safe_load(f)
        page_param = next(p for p in data["parameters"] if p["name"] == "page")
        assert page_param["type"] == "number"
        assert page_param["required"] is False

    def test_yaml_search_is_optional_string(self):
        with open("tools/list_dashboards.yaml") as f:
            data = yaml.safe_load(f)
        search_param = next(p for p in data["parameters"] if p["name"] == "search")
        assert search_param["type"] == "string"
        assert search_param["required"] is False


class TestListDashboardsToolClass:
    """Test ListDashboardsTool class (Task 9.2)."""

    def test_extends_tool_base_class(self):
        tool = ListDashboardsTool()
        assert isinstance(tool, Tool)

    def test_has_invoke_method(self):
        tool = ListDashboardsTool()
        assert hasattr(tool, "_invoke")
        assert callable(tool._invoke)


class TestInputValidation:
    """Test input parameter validation (Task 9.3)."""

    @patch("tools.list_dashboards.RedashClient")
    def test_default_page_size_is_25(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.request.return_value = {"results": [], "count": 0}
        mock_client_cls.return_value = mock_client

        tool = _make_tool()
        _invoke_tool(tool, {})

        mock_client.request.assert_called_once()
        call_kwargs = mock_client.request.call_args
        assert call_kwargs[1]["params"]["page_size"] == DEFAULT_PAGE_SIZE

    @patch("tools.list_dashboards.RedashClient")
    def test_default_page_is_1(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.request.return_value = {"results": [], "count": 0}
        mock_client_cls.return_value = mock_client

        tool = _make_tool()
        _invoke_tool(tool, {})

        call_kwargs = mock_client.request.call_args
        assert call_kwargs[1]["params"]["page"] == DEFAULT_PAGE

    @patch("tools.list_dashboards.RedashClient")
    def test_valid_page_size_is_used(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.request.return_value = {"results": [], "count": 0}
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

    @patch("tools.list_dashboards.RedashClient")
    def test_page_size_at_minimum_boundary(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.request.return_value = {"results": [], "count": 0}
        mock_client_cls.return_value = mock_client

        tool = _make_tool()
        _invoke_tool(tool, {"page_size": 1})

        call_kwargs = mock_client.request.call_args
        assert call_kwargs[1]["params"]["page_size"] == 1

    @patch("tools.list_dashboards.RedashClient")
    def test_page_size_at_maximum_boundary(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.request.return_value = {"results": [], "count": 0}
        mock_client_cls.return_value = mock_client

        tool = _make_tool()
        _invoke_tool(tool, {"page_size": 250})

        call_kwargs = mock_client.request.call_args
        assert call_kwargs[1]["params"]["page_size"] == 250

    def test_page_below_1_returns_error(self):
        tool = _make_tool()
        results = _invoke_tool(tool, {"page": 0})

        assert len(results) == 1
        assert results[0]["error"] is True
        assert results[0]["error_code"] == "VAL_001"

    def test_page_non_numeric_returns_error(self):
        tool = _make_tool()
        results = _invoke_tool(tool, {"page": "abc"})

        assert len(results) == 1
        assert results[0]["error"] is True
        assert results[0]["error_code"] == "VAL_001"

    @patch("tools.list_dashboards.RedashClient")
    def test_valid_page_number_is_used(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.request.return_value = {"results": [], "count": 0}
        mock_client_cls.return_value = mock_client

        tool = _make_tool()
        _invoke_tool(tool, {"page": 3})

        call_kwargs = mock_client.request.call_args
        assert call_kwargs[1]["params"]["page"] == 3

    def test_search_too_long_returns_error(self):
        tool = _make_tool()
        results = _invoke_tool(tool, {"search": "x" * 201})

        assert len(results) == 1
        assert results[0]["error"] is True
        assert results[0]["error_code"] == "VAL_001"

    def test_search_empty_string_returns_error(self):
        tool = _make_tool()
        results = _invoke_tool(tool, {"search": ""})

        assert len(results) == 1
        assert results[0]["error"] is True
        assert results[0]["error_code"] == "VAL_001"


class TestApiCall:
    """Test API call with pagination and search (Task 9.4)."""

    @patch("tools.list_dashboards.RedashClient")
    def test_calls_get_api_dashboards(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.request.return_value = {"results": [], "count": 0}
        mock_client_cls.return_value = mock_client

        tool = _make_tool()
        _invoke_tool(tool, {})

        mock_client.request.assert_called_once_with(
            "GET", "/api/dashboards", params={"page_size": 25, "page": 1}
        )

    @patch("tools.list_dashboards.RedashClient")
    def test_passes_search_as_q_param(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.request.return_value = {"results": [], "count": 0}
        mock_client_cls.return_value = mock_client

        tool = _make_tool()
        _invoke_tool(tool, {"search": "sales"})

        mock_client.request.assert_called_once_with(
            "GET", "/api/dashboards", params={"page_size": 25, "page": 1, "q": "sales"}
        )

    @patch("tools.list_dashboards.RedashClient")
    def test_passes_custom_page_size_and_page(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.request.return_value = {"results": [], "count": 0}
        mock_client_cls.return_value = mock_client

        tool = _make_tool()
        _invoke_tool(tool, {"page_size": 10, "page": 2})

        mock_client.request.assert_called_once_with(
            "GET", "/api/dashboards", params={"page_size": 10, "page": 2}
        )

    @patch("tools.list_dashboards.RedashClient")
    def test_uses_provided_credentials(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.request.return_value = {"results": [], "count": 0}
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
    """Test response field extraction (Task 9.5)."""

    @patch("tools.list_dashboards.RedashClient")
    def test_extracts_required_fields(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.request.return_value = {
            "count": 1,
            "results": [
                {
                    "id": 7,
                    "name": "Sales Dashboard",
                    "slug": "sales-dashboard",
                    "created_at": "2024-01-15T10:00:00Z",
                    "updated_at": "2024-06-20T14:30:00Z",
                    "user": {"name": "Admin"},
                    "is_archived": False,
                    "tags": ["sales"],
                }
            ],
        }
        mock_client_cls.return_value = mock_client

        tool = _make_tool()
        results = _invoke_tool(tool, {})

        assert len(results) == 1
        dashboards = results[0]["dashboards"]
        assert len(dashboards) == 1

        dashboard = dashboards[0]
        assert dashboard["id"] == 7
        assert dashboard["name"] == "Sales Dashboard"
        assert dashboard["slug"] == "sales-dashboard"
        assert dashboard["created_at"] == "2024-01-15T10:00:00Z"
        assert dashboard["updated_at"] == "2024-06-20T14:30:00Z"

        # Should NOT include extra fields
        assert "user" not in dashboard
        assert "is_archived" not in dashboard
        assert "tags" not in dashboard

    @patch("tools.list_dashboards.RedashClient")
    def test_maps_multiple_dashboards(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.request.return_value = {
            "count": 2,
            "results": [
                {"id": 1, "name": "D1", "slug": "d1", "created_at": "2024-01-01", "updated_at": "2024-02-01"},
                {"id": 2, "name": "D2", "slug": "d2", "created_at": "2024-03-01", "updated_at": "2024-04-01"},
            ],
        }
        mock_client_cls.return_value = mock_client

        tool = _make_tool()
        results = _invoke_tool(tool, {})

        dashboards = results[0]["dashboards"]
        assert len(dashboards) == 2
        assert dashboards[0]["id"] == 1
        assert dashboards[1]["id"] == 2

    @patch("tools.list_dashboards.RedashClient")
    def test_includes_total_count(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.request.return_value = {
            "count": 50,
            "results": [
                {"id": 1, "name": "D1", "slug": "d1", "created_at": "2024-01-01", "updated_at": "2024-02-01"},
            ],
        }
        mock_client_cls.return_value = mock_client

        tool = _make_tool()
        results = _invoke_tool(tool, {})

        assert results[0]["total_count"] == 50


class TestEmptyResults:
    """Test empty results handling (Task 9.6)."""

    @patch("tools.list_dashboards.RedashClient")
    def test_empty_results_returns_empty_list_with_zero_count(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.request.return_value = {"results": [], "count": 0}
        mock_client_cls.return_value = mock_client

        tool = _make_tool()
        results = _invoke_tool(tool, {})

        assert results[0]["dashboards"] == []
        assert results[0]["total_count"] == 0


class TestErrorHandling:
    """Test error handling paths (Task 9.7)."""

    @patch("tools.list_dashboards.RedashClient")
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

    @patch("tools.list_dashboards.RedashClient")
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

    @patch("tools.list_dashboards.RedashClient")
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

    @patch("tools.list_dashboards.RedashClient")
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

    @patch("tools.list_dashboards.RedashClient")
    def test_rate_limit_error_returns_structured_error(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.request.side_effect = PluginError(
            error_code=ErrorCode.RATE_LIMIT_EXCEEDED,
            message="Redash API rate limit exceeded. Please try again later.",
            details={"attempts": 3},
        )
        mock_client_cls.return_value = mock_client

        tool = _make_tool()
        results = _invoke_tool(tool, {})

        assert results[0]["error"] is True
        assert results[0]["error_code"] == "RATE_001"
