"""
Tests for the Get Dashboard Details Tool (tools/get_dashboard_details.py).

Covers:
- Task 10.1: YAML tool definition structure
- Task 10.2: GetDashboardDetailsTool class structure
- Task 10.3: Input validation - dashboard_slug must be non-empty, not whitespace-only
- Task 10.4: API call to GET /api/dashboards/{slug}
- Task 10.5: Response mapping - extract name, slug, dates, widgets with id, type, query_id, visualization_type
- Task 10.6: include_results logic - fetch cached results for query-associated widgets
- Task 10.7: Handle dashboard not found (DASH_001) and API errors
"""

import json
from unittest.mock import MagicMock, patch, call

import pytest
import yaml

from tools._dify_stubs import Tool, ToolRuntime
from tools.get_dashboard_details import GetDashboardDetailsTool
from utils.error_handler import ErrorCode, PluginError


def _make_tool(credentials: dict | None = None) -> GetDashboardDetailsTool:
    """Create a GetDashboardDetailsTool instance with mock runtime credentials."""
    tool = GetDashboardDetailsTool()
    tool.runtime = ToolRuntime(credentials=credentials or {
        "redash_url": "https://redash.example.com",
        "api_key": "test-api-key-1234",
    })
    return tool


def _invoke_tool(tool: GetDashboardDetailsTool, params: dict) -> list[dict]:
    """Invoke the tool and collect all text messages as parsed JSON."""
    results = []
    for msg in tool._invoke(params):
        results.append(json.loads(msg.text))
    return results


SAMPLE_DASHBOARD_RESPONSE = {
    "id": 1,
    "name": "My Dashboard",
    "slug": "my-dashboard",
    "created_at": "2024-01-01T00:00:00Z",
    "updated_at": "2024-06-01T00:00:00Z",
    "widgets": [
        {
            "id": 1,
            "type": "visualization",
            "visualization": {
                "id": 5,
                "type": "TABLE",
                "query": {
                    "id": 42,
                    "name": "Revenue Query",
                },
            },
        },
        {
            "id": 2,
            "type": "textbox",
            "text": "Some description",
        },
    ],
}


class TestYamlDefinition:
    """Test YAML tool definition file (Task 10.1)."""

    def test_yaml_loads_correctly(self):
        with open("tools/get_dashboard_details.yaml") as f:
            data = yaml.safe_load(f)
        assert data is not None

    def test_yaml_has_identity(self):
        with open("tools/get_dashboard_details.yaml") as f:
            data = yaml.safe_load(f)
        assert data["identity"]["name"] == "get_dashboard_details"
        assert "label" in data["identity"]
        assert "en_US" in data["identity"]["label"]

    def test_yaml_has_description(self):
        with open("tools/get_dashboard_details.yaml") as f:
            data = yaml.safe_load(f)
        assert "human" in data["description"]
        assert "llm" in data["description"]

    def test_yaml_has_parameters(self):
        with open("tools/get_dashboard_details.yaml") as f:
            data = yaml.safe_load(f)
        params = data["parameters"]
        assert len(params) == 2

        param_names = [p["name"] for p in params]
        assert "dashboard_slug" in param_names
        assert "include_results" in param_names

    def test_yaml_dashboard_slug_is_required_string(self):
        with open("tools/get_dashboard_details.yaml") as f:
            data = yaml.safe_load(f)
        slug_param = next(p for p in data["parameters"] if p["name"] == "dashboard_slug")
        assert slug_param["type"] == "string"
        assert slug_param["required"] is True

    def test_yaml_include_results_is_optional_boolean(self):
        with open("tools/get_dashboard_details.yaml") as f:
            data = yaml.safe_load(f)
        results_param = next(p for p in data["parameters"] if p["name"] == "include_results")
        assert results_param["type"] == "boolean"
        assert results_param["required"] is False


class TestGetDashboardDetailsToolClass:
    """Test GetDashboardDetailsTool class (Task 10.2)."""

    def test_extends_tool_base_class(self):
        tool = GetDashboardDetailsTool()
        assert isinstance(tool, Tool)

    def test_has_invoke_method(self):
        tool = GetDashboardDetailsTool()
        assert hasattr(tool, "_invoke")
        assert callable(tool._invoke)


class TestInputValidation:
    """Test input parameter validation (Task 10.3)."""

    def test_missing_dashboard_slug_returns_error(self):
        tool = _make_tool()
        results = _invoke_tool(tool, {})

        assert len(results) == 1
        assert results[0]["error"] is True
        assert results[0]["error_code"] == "VAL_001"
        assert "dashboard slug" in results[0]["message"].lower()

    def test_empty_string_dashboard_slug_returns_error(self):
        tool = _make_tool()
        results = _invoke_tool(tool, {"dashboard_slug": ""})

        assert len(results) == 1
        assert results[0]["error"] is True
        assert results[0]["error_code"] == "VAL_001"

    def test_whitespace_only_dashboard_slug_returns_error(self):
        tool = _make_tool()
        results = _invoke_tool(tool, {"dashboard_slug": "   "})

        assert len(results) == 1
        assert results[0]["error"] is True
        assert results[0]["error_code"] == "VAL_001"

    def test_none_dashboard_slug_returns_error(self):
        tool = _make_tool()
        results = _invoke_tool(tool, {"dashboard_slug": None})

        assert len(results) == 1
        assert results[0]["error"] is True
        assert results[0]["error_code"] == "VAL_001"

    @patch("tools.get_dashboard_details.RedashClient")
    def test_valid_slug_passes_validation(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.request.return_value = SAMPLE_DASHBOARD_RESPONSE
        mock_client_cls.return_value = mock_client

        tool = _make_tool()
        results = _invoke_tool(tool, {"dashboard_slug": "my-dashboard"})

        assert len(results) == 1
        assert "error" not in results[0]

    @patch("tools.get_dashboard_details.RedashClient")
    def test_slug_with_leading_trailing_whitespace_is_trimmed(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.request.return_value = SAMPLE_DASHBOARD_RESPONSE
        mock_client_cls.return_value = mock_client

        tool = _make_tool()
        _invoke_tool(tool, {"dashboard_slug": "  my-dashboard  "})

        mock_client.request.assert_called_once_with("GET", "/api/dashboards/my-dashboard")


class TestApiCall:
    """Test API call to GET /api/dashboards/{slug} (Task 10.4)."""

    @patch("tools.get_dashboard_details.RedashClient")
    def test_calls_get_api_dashboards_with_slug(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.request.return_value = SAMPLE_DASHBOARD_RESPONSE
        mock_client_cls.return_value = mock_client

        tool = _make_tool()
        _invoke_tool(tool, {"dashboard_slug": "my-dashboard"})

        mock_client.request.assert_called_once_with("GET", "/api/dashboards/my-dashboard")

    @patch("tools.get_dashboard_details.RedashClient")
    def test_uses_provided_credentials(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.request.return_value = SAMPLE_DASHBOARD_RESPONSE
        mock_client_cls.return_value = mock_client

        tool = _make_tool({
            "redash_url": "https://my-redash.com",
            "api_key": "my-key-5678",
        })
        _invoke_tool(tool, {"dashboard_slug": "test-dash"})

        mock_client_cls.assert_called_once_with(
            base_url="https://my-redash.com",
            api_key="my-key-5678",
        )


class TestResponseMapping:
    """Test response field extraction (Task 10.5)."""

    @patch("tools.get_dashboard_details.RedashClient")
    def test_extracts_dashboard_metadata(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.request.return_value = SAMPLE_DASHBOARD_RESPONSE
        mock_client_cls.return_value = mock_client

        tool = _make_tool()
        results = _invoke_tool(tool, {"dashboard_slug": "my-dashboard"})

        assert len(results) == 1
        result = results[0]
        assert result["name"] == "My Dashboard"
        assert result["slug"] == "my-dashboard"
        assert result["created_at"] == "2024-01-01T00:00:00Z"
        assert result["updated_at"] == "2024-06-01T00:00:00Z"

    @patch("tools.get_dashboard_details.RedashClient")
    def test_extracts_visualization_widget(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.request.return_value = SAMPLE_DASHBOARD_RESPONSE
        mock_client_cls.return_value = mock_client

        tool = _make_tool()
        results = _invoke_tool(tool, {"dashboard_slug": "my-dashboard"})

        widgets = results[0]["widgets"]
        vis_widget = widgets[0]
        assert vis_widget["id"] == 1
        assert vis_widget["type"] == "visualization"
        assert vis_widget["query_id"] == 42
        assert vis_widget["visualization_type"] == "TABLE"

    @patch("tools.get_dashboard_details.RedashClient")
    def test_extracts_textbox_widget_with_null_fields(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.request.return_value = SAMPLE_DASHBOARD_RESPONSE
        mock_client_cls.return_value = mock_client

        tool = _make_tool()
        results = _invoke_tool(tool, {"dashboard_slug": "my-dashboard"})

        widgets = results[0]["widgets"]
        text_widget = widgets[1]
        assert text_widget["id"] == 2
        assert text_widget["type"] == "textbox"
        assert text_widget["query_id"] is None
        assert text_widget["visualization_type"] is None

    @patch("tools.get_dashboard_details.RedashClient")
    def test_handles_widget_with_visualization_but_no_query(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.request.return_value = {
            "id": 1,
            "name": "Test",
            "slug": "test",
            "created_at": "2024-01-01T00:00:00Z",
            "updated_at": "2024-01-01T00:00:00Z",
            "widgets": [
                {
                    "id": 3,
                    "type": "visualization",
                    "visualization": {
                        "id": 10,
                        "type": "CHART",
                    },
                },
            ],
        }
        mock_client_cls.return_value = mock_client

        tool = _make_tool()
        results = _invoke_tool(tool, {"dashboard_slug": "test"})

        widget = results[0]["widgets"][0]
        assert widget["id"] == 3
        assert widget["query_id"] is None
        assert widget["visualization_type"] == "CHART"

    @patch("tools.get_dashboard_details.RedashClient")
    def test_handles_empty_widgets_list(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.request.return_value = {
            "id": 1,
            "name": "Empty Dashboard",
            "slug": "empty",
            "created_at": "2024-01-01T00:00:00Z",
            "updated_at": "2024-01-01T00:00:00Z",
            "widgets": [],
        }
        mock_client_cls.return_value = mock_client

        tool = _make_tool()
        results = _invoke_tool(tool, {"dashboard_slug": "empty"})

        assert results[0]["widgets"] == []


class TestIncludeResults:
    """Test include_results logic (Task 10.6)."""

    @patch("tools.get_dashboard_details.RedashClient")
    def test_include_results_false_does_not_fetch_results(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.request.return_value = SAMPLE_DASHBOARD_RESPONSE
        mock_client_cls.return_value = mock_client

        tool = _make_tool()
        _invoke_tool(tool, {"dashboard_slug": "my-dashboard", "include_results": False})

        # Should only call once for the dashboard itself
        mock_client.request.assert_called_once_with("GET", "/api/dashboards/my-dashboard")

    @patch("tools.get_dashboard_details.RedashClient")
    def test_include_results_true_fetches_cached_results_for_query_widgets(self, mock_client_cls):
        mock_client = MagicMock()

        cached_result_response = {
            "query_result": {
                "data": {
                    "columns": [{"name": "revenue", "type": "float"}],
                    "rows": [{"revenue": 1000.50}],
                },
                "retrieved_at": "2024-06-01T12:00:00Z",
            },
        }

        mock_client.request.side_effect = [
            SAMPLE_DASHBOARD_RESPONSE,      # GET /api/dashboards/{slug}
            cached_result_response,          # GET /api/queries/42/results
        ]
        mock_client_cls.return_value = mock_client

        tool = _make_tool()
        results = _invoke_tool(tool, {"dashboard_slug": "my-dashboard", "include_results": True})

        # Verify API calls
        calls = mock_client.request.call_args_list
        assert len(calls) == 2
        assert calls[0] == call("GET", "/api/dashboards/my-dashboard")
        assert calls[1] == call("GET", "/api/queries/42/results")

        # First widget (with query) should have results
        widget_with_query = results[0]["widgets"][0]
        assert "results" in widget_with_query
        assert "columns" in widget_with_query["results"]
        assert "rows" in widget_with_query["results"]

    @patch("tools.get_dashboard_details.RedashClient")
    def test_include_results_true_indicates_unavailability_for_textbox_widgets(self, mock_client_cls):
        mock_client = MagicMock()

        cached_result_response = {
            "query_result": {
                "data": {
                    "columns": [{"name": "revenue", "type": "float"}],
                    "rows": [{"revenue": 1000.50}],
                },
                "retrieved_at": "2024-06-01T12:00:00Z",
            },
        }

        mock_client.request.side_effect = [
            SAMPLE_DASHBOARD_RESPONSE,
            cached_result_response,
        ]
        mock_client_cls.return_value = mock_client

        tool = _make_tool()
        results = _invoke_tool(tool, {"dashboard_slug": "my-dashboard", "include_results": True})

        # Second widget (textbox, no query) should indicate unavailability
        textbox_widget = results[0]["widgets"][1]
        assert textbox_widget["results_available"] is False
        assert "results_message" in textbox_widget

    @patch("tools.get_dashboard_details.RedashClient")
    def test_include_results_true_handles_query_results_fetch_failure(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.request.side_effect = [
            SAMPLE_DASHBOARD_RESPONSE,
            PluginError(
                error_code=ErrorCode.SERVER_ERROR,
                message="A Redash server-side error occurred.",
                details={"http_status": 500},
            ),
        ]
        mock_client_cls.return_value = mock_client

        tool = _make_tool()
        results = _invoke_tool(tool, {"dashboard_slug": "my-dashboard", "include_results": True})

        # Widget with failed result fetch should indicate unavailability
        widget = results[0]["widgets"][0]
        assert widget["results_available"] is False
        assert "results_message" in widget

    @patch("tools.get_dashboard_details.RedashClient")
    def test_include_results_true_handles_no_cached_results(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.request.side_effect = [
            SAMPLE_DASHBOARD_RESPONSE,
            {"query_result": None},  # No cached results
        ]
        mock_client_cls.return_value = mock_client

        tool = _make_tool()
        results = _invoke_tool(tool, {"dashboard_slug": "my-dashboard", "include_results": True})

        widget = results[0]["widgets"][0]
        assert widget["results_available"] is False

    @patch("tools.get_dashboard_details.RedashClient")
    def test_include_results_string_true_is_handled(self, mock_client_cls):
        mock_client = MagicMock()

        cached_result_response = {
            "query_result": {
                "data": {
                    "columns": [{"name": "id", "type": "integer"}],
                    "rows": [{"id": 1}],
                },
                "retrieved_at": "2024-06-01T12:00:00Z",
            },
        }

        mock_client.request.side_effect = [
            SAMPLE_DASHBOARD_RESPONSE,
            cached_result_response,
        ]
        mock_client_cls.return_value = mock_client

        tool = _make_tool()
        results = _invoke_tool(tool, {"dashboard_slug": "my-dashboard", "include_results": "true"})

        # Should fetch results since "true" string is parsed as true
        calls = mock_client.request.call_args_list
        assert len(calls) == 2


class TestErrorHandling:
    """Test error handling (Task 10.7)."""

    @patch("tools.get_dashboard_details.RedashClient")
    def test_dashboard_not_found_returns_dash_001(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.request.side_effect = PluginError(
            error_code=ErrorCode.SERVER_ERROR,
            message="Not found",
            details={"http_status": 404},
        )
        mock_client_cls.return_value = mock_client

        tool = _make_tool()
        results = _invoke_tool(tool, {"dashboard_slug": "nonexistent"})

        assert len(results) == 1
        assert results[0]["error"] is True
        assert results[0]["error_code"] == "DASH_001"
        assert "nonexistent" in results[0]["message"]

    @patch("tools.get_dashboard_details.RedashClient")
    def test_api_auth_error_returns_structured_error(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.request.side_effect = PluginError(
            error_code=ErrorCode.AUTH_INVALID_CREDENTIALS,
            message="Authentication failed: invalid or expired API credentials.",
            details={"http_status": 401},
        )
        mock_client_cls.return_value = mock_client

        tool = _make_tool()
        results = _invoke_tool(tool, {"dashboard_slug": "my-dashboard"})

        assert results[0]["error"] is True
        assert results[0]["error_code"] == "AUTH_001"

    @patch("tools.get_dashboard_details.RedashClient")
    def test_api_server_error_returns_structured_error(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.request.side_effect = PluginError(
            error_code=ErrorCode.SERVER_ERROR,
            message="A Redash server-side error occurred.",
            details={"http_status": 500},
        )
        mock_client_cls.return_value = mock_client

        tool = _make_tool()
        results = _invoke_tool(tool, {"dashboard_slug": "my-dashboard"})

        assert results[0]["error"] is True
        assert results[0]["error_code"] == "SERVER_001"

    @patch("tools.get_dashboard_details.RedashClient")
    def test_connection_error_returns_structured_error(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.request.side_effect = PluginError(
            error_code=ErrorCode.CONN_UNREACHABLE,
            message="Unable to connect to the Redash instance.",
            details={"host": "redash.example.com", "error_type": "ConnectionError"},
        )
        mock_client_cls.return_value = mock_client

        tool = _make_tool()
        results = _invoke_tool(tool, {"dashboard_slug": "my-dashboard"})

        assert results[0]["error"] is True
        assert results[0]["error_code"] == "CONN_001"

    @patch("tools.get_dashboard_details.RedashClient")
    def test_unexpected_error_returns_sanitized_error(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.request.side_effect = RuntimeError("Something unexpected happened")
        mock_client_cls.return_value = mock_client

        tool = _make_tool()
        results = _invoke_tool(tool, {"dashboard_slug": "my-dashboard"})

        assert results[0]["error"] is True
        assert results[0]["error_code"] == "UNEXPECTED_001"
        assert "RuntimeError" not in results[0]["message"]
        assert "Something unexpected happened" not in results[0]["message"]

    @patch("tools.get_dashboard_details.RedashClient")
    def test_rate_limit_error_returns_structured_error(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.request.side_effect = PluginError(
            error_code=ErrorCode.RATE_LIMIT_EXCEEDED,
            message="Redash API rate limit exceeded. Please try again later.",
            details={"attempts": 3},
        )
        mock_client_cls.return_value = mock_client

        tool = _make_tool()
        results = _invoke_tool(tool, {"dashboard_slug": "my-dashboard"})

        assert results[0]["error"] is True
        assert results[0]["error_code"] == "RATE_001"
