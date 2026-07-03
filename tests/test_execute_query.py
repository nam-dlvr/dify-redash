"""
Tests for the Execute Query Tool (tools/execute_query.py).

Covers:
- Task 7.1: YAML tool definition structure
- Task 7.2: ExecuteQueryTool class structure
- Task 7.3: Input validation - query_id positive integer, max_age non-negative integer
- Task 7.4: Parameter parsing - JSON string parsing, validation
- Task 7.5: API call to POST /api/queries/{id}/results
- Task 7.6: Execution timeout handling (QUERY_002)
- Task 7.7: ResponseFormatter integration for successful results
- Task 7.8: Error handling - query not found, execution error, invalid params
"""

import json
from unittest.mock import MagicMock, patch

import pytest
import yaml

from tools._dify_stubs import Tool, ToolRuntime
from tools.execute_query import ExecuteQueryTool, EXECUTION_TIMEOUT
from utils.error_handler import ErrorCode, PluginError


def _make_tool(credentials: dict | None = None) -> ExecuteQueryTool:
    """Create an ExecuteQueryTool instance with mock runtime credentials."""
    tool = ExecuteQueryTool()
    tool.runtime = ToolRuntime(credentials=credentials or {
        "redash_url": "https://redash.example.com",
        "api_key": "test-api-key-1234",
    })
    return tool


def _invoke_tool(tool: ExecuteQueryTool, params: dict) -> list[dict]:
    """Invoke the tool and collect all text messages as parsed JSON."""
    results = []
    for msg in tool._invoke(params):
        results.append(json.loads(msg.text))
    return results


class TestYamlDefinition:
    """Test YAML tool definition file (Task 7.1)."""

    def test_yaml_loads_correctly(self):
        with open("tools/execute_query.yaml") as f:
            data = yaml.safe_load(f)
        assert data is not None

    def test_yaml_has_identity(self):
        with open("tools/execute_query.yaml") as f:
            data = yaml.safe_load(f)
        assert data["identity"]["name"] == "execute_query"
        assert "label" in data["identity"]
        assert "en_US" in data["identity"]["label"]

    def test_yaml_has_description(self):
        with open("tools/execute_query.yaml") as f:
            data = yaml.safe_load(f)
        assert "human" in data["description"]
        assert "llm" in data["description"]

    def test_yaml_has_parameters(self):
        with open("tools/execute_query.yaml") as f:
            data = yaml.safe_load(f)
        params = data["parameters"]
        assert len(params) == 3

        param_names = [p["name"] for p in params]
        assert "query_id" in param_names
        assert "parameters" in param_names
        assert "max_age" in param_names

    def test_yaml_query_id_is_required_number(self):
        with open("tools/execute_query.yaml") as f:
            data = yaml.safe_load(f)
        query_id_param = next(p for p in data["parameters"] if p["name"] == "query_id")
        assert query_id_param["type"] == "number"
        assert query_id_param["required"] is True

    def test_yaml_parameters_is_optional_string(self):
        with open("tools/execute_query.yaml") as f:
            data = yaml.safe_load(f)
        params_param = next(p for p in data["parameters"] if p["name"] == "parameters")
        assert params_param["type"] == "string"
        assert params_param["required"] is False

    def test_yaml_max_age_is_optional_number(self):
        with open("tools/execute_query.yaml") as f:
            data = yaml.safe_load(f)
        max_age_param = next(p for p in data["parameters"] if p["name"] == "max_age")
        assert max_age_param["type"] == "number"
        assert max_age_param["required"] is False


class TestExecuteQueryToolClass:
    """Test ExecuteQueryTool class (Task 7.2)."""

    def test_extends_tool_base_class(self):
        tool = ExecuteQueryTool()
        assert isinstance(tool, Tool)

    def test_has_invoke_method(self):
        tool = ExecuteQueryTool()
        assert hasattr(tool, "_invoke")
        assert callable(tool._invoke)


class TestInputValidation:
    """Test query_id and max_age validation (Task 7.3)."""

    def test_missing_query_id_returns_error(self):
        tool = _make_tool()
        results = _invoke_tool(tool, {})

        assert len(results) == 1
        assert results[0]["error"] is True
        assert results[0]["error_code"] == "VAL_001"

    def test_non_numeric_query_id_returns_error(self):
        tool = _make_tool()
        results = _invoke_tool(tool, {"query_id": "abc"})

        assert len(results) == 1
        assert results[0]["error"] is True
        assert results[0]["error_code"] == "VAL_001"

    def test_zero_query_id_returns_error(self):
        tool = _make_tool()
        results = _invoke_tool(tool, {"query_id": 0})

        assert len(results) == 1
        assert results[0]["error"] is True
        assert results[0]["error_code"] == "VAL_001"

    def test_negative_query_id_returns_error(self):
        tool = _make_tool()
        results = _invoke_tool(tool, {"query_id": -5})

        assert len(results) == 1
        assert results[0]["error"] is True
        assert results[0]["error_code"] == "VAL_001"

    def test_negative_max_age_returns_error(self):
        tool = _make_tool()
        results = _invoke_tool(tool, {"query_id": 1, "max_age": -1})

        assert len(results) == 1
        assert results[0]["error"] is True
        assert results[0]["error_code"] == "VAL_001"

    def test_non_numeric_max_age_returns_error(self):
        tool = _make_tool()
        results = _invoke_tool(tool, {"query_id": 1, "max_age": "abc"})

        assert len(results) == 1
        assert results[0]["error"] is True
        assert results[0]["error_code"] == "VAL_001"

    @patch("tools.execute_query.RedashClient")
    def test_zero_max_age_is_valid(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.request.return_value = {
            "query_result": {
                "data": {"columns": [], "rows": []},
                "retrieved_at": "2024-01-01T00:00:00Z",
            }
        }
        mock_client_cls.return_value = mock_client

        tool = _make_tool()
        results = _invoke_tool(tool, {"query_id": 1, "max_age": 0})

        assert "error" not in results[0]

    @patch("tools.execute_query.RedashClient")
    def test_positive_query_id_is_valid(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.request.return_value = {
            "query_result": {
                "data": {"columns": [], "rows": []},
                "retrieved_at": "2024-01-01T00:00:00Z",
            }
        }
        mock_client_cls.return_value = mock_client

        tool = _make_tool()
        results = _invoke_tool(tool, {"query_id": 42})

        assert "error" not in results[0]


class TestParameterParsing:
    """Test JSON parameter parsing (Task 7.4)."""

    def test_invalid_json_returns_query_004_error(self):
        tool = _make_tool()
        results = _invoke_tool(tool, {"query_id": 1, "parameters": "not valid json"})

        assert len(results) == 1
        assert results[0]["error"] is True
        assert results[0]["error_code"] == "QUERY_004"

    def test_non_object_json_returns_query_004_error(self):
        tool = _make_tool()
        results = _invoke_tool(tool, {"query_id": 1, "parameters": "[1, 2, 3]"})

        assert len(results) == 1
        assert results[0]["error"] is True
        assert results[0]["error_code"] == "QUERY_004"

    @patch("tools.execute_query.RedashClient")
    def test_valid_json_object_is_accepted(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.request.return_value = {
            "query_result": {
                "data": {"columns": [], "rows": []},
                "retrieved_at": "2024-01-01T00:00:00Z",
            }
        }
        mock_client_cls.return_value = mock_client

        tool = _make_tool()
        results = _invoke_tool(tool, {"query_id": 1, "parameters": '{"date": "2024-01-01"}'})

        assert "error" not in results[0]

    @patch("tools.execute_query.RedashClient")
    def test_empty_parameters_string_is_accepted(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.request.return_value = {
            "query_result": {
                "data": {"columns": [], "rows": []},
                "retrieved_at": "2024-01-01T00:00:00Z",
            }
        }
        mock_client_cls.return_value = mock_client

        tool = _make_tool()
        results = _invoke_tool(tool, {"query_id": 1, "parameters": ""})

        assert "error" not in results[0]

    @patch("tools.execute_query.RedashClient")
    def test_parameters_passed_in_request_body(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.request.return_value = {
            "query_result": {
                "data": {"columns": [], "rows": []},
                "retrieved_at": "2024-01-01T00:00:00Z",
            }
        }
        mock_client_cls.return_value = mock_client

        tool = _make_tool()
        _invoke_tool(tool, {"query_id": 5, "parameters": '{"limit": 100}'})

        call_kwargs = mock_client.request.call_args
        assert call_kwargs[1]["json"]["parameters"] == {"limit": 100}


class TestApiCall:
    """Test API call to POST /api/queries/{id}/results (Task 7.5)."""

    @patch("tools.execute_query.RedashClient")
    def test_calls_post_with_correct_path(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.request.return_value = {
            "query_result": {
                "data": {"columns": [], "rows": []},
                "retrieved_at": "2024-01-01T00:00:00Z",
            }
        }
        mock_client_cls.return_value = mock_client

        tool = _make_tool()
        _invoke_tool(tool, {"query_id": 42})

        mock_client.request.assert_called_once()
        call_args = mock_client.request.call_args
        assert call_args[0][0] == "POST"
        assert call_args[0][1] == "/api/queries/42/results"

    @patch("tools.execute_query.RedashClient")
    def test_includes_max_age_in_body(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.request.return_value = {
            "query_result": {
                "data": {"columns": [], "rows": []},
                "retrieved_at": "2024-01-01T00:00:00Z",
            }
        }
        mock_client_cls.return_value = mock_client

        tool = _make_tool()
        _invoke_tool(tool, {"query_id": 10, "max_age": 300})

        call_kwargs = mock_client.request.call_args
        assert call_kwargs[1]["json"]["max_age"] == 300

    @patch("tools.execute_query.RedashClient")
    def test_includes_parameters_and_max_age_in_body(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.request.return_value = {
            "query_result": {
                "data": {"columns": [], "rows": []},
                "retrieved_at": "2024-01-01T00:00:00Z",
            }
        }
        mock_client_cls.return_value = mock_client

        tool = _make_tool()
        _invoke_tool(tool, {"query_id": 10, "parameters": '{"x": 1}', "max_age": 60})

        call_kwargs = mock_client.request.call_args
        body = call_kwargs[1]["json"]
        assert body["parameters"] == {"x": 1}
        assert body["max_age"] == 60

    @patch("tools.execute_query.RedashClient")
    def test_empty_body_when_no_optional_params(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.request.return_value = {
            "query_result": {
                "data": {"columns": [], "rows": []},
                "retrieved_at": "2024-01-01T00:00:00Z",
            }
        }
        mock_client_cls.return_value = mock_client

        tool = _make_tool()
        _invoke_tool(tool, {"query_id": 10})

        call_kwargs = mock_client.request.call_args
        assert call_kwargs[1]["json"] == {}

    @patch("tools.execute_query.RedashClient")
    def test_uses_correct_timeout(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.request.return_value = {
            "query_result": {
                "data": {"columns": [], "rows": []},
                "retrieved_at": "2024-01-01T00:00:00Z",
            }
        }
        mock_client_cls.return_value = mock_client

        tool = _make_tool()
        _invoke_tool(tool, {"query_id": 10})

        call_kwargs = mock_client.request.call_args
        assert call_kwargs[1]["timeout"] == (30, EXECUTION_TIMEOUT)

    @patch("tools.execute_query.RedashClient")
    def test_uses_provided_credentials(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.request.return_value = {
            "query_result": {
                "data": {"columns": [], "rows": []},
                "retrieved_at": "2024-01-01T00:00:00Z",
            }
        }
        mock_client_cls.return_value = mock_client

        tool = _make_tool({
            "redash_url": "https://my-redash.com",
            "api_key": "my-key-5678",
        })
        _invoke_tool(tool, {"query_id": 1})

        mock_client_cls.assert_called_once_with(
            base_url="https://my-redash.com",
            api_key="my-key-5678",
        )


class TestTimeoutHandling:
    """Test execution timeout handling (Task 7.6)."""

    @patch("tools.execute_query.RedashClient")
    def test_timeout_returns_query_002(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.request.side_effect = PluginError(
            error_code=ErrorCode.CONN_TIMEOUT,
            message="Redash request timed out waiting for a response.",
            details={"host": "redash.example.com", "timeout_type": "read"},
        )
        mock_client_cls.return_value = mock_client

        tool = _make_tool()
        results = _invoke_tool(tool, {"query_id": 1})

        assert len(results) == 1
        assert results[0]["error"] is True
        assert results[0]["error_code"] == "QUERY_002"
        assert "120" in results[0]["message"] or "timeout" in results[0]["message"].lower()


class TestResponseFormatting:
    """Test ResponseFormatter integration (Task 7.7)."""

    @patch("tools.execute_query.RedashClient")
    def test_formats_results_with_columns_and_rows(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.request.return_value = {
            "query_result": {
                "data": {
                    "columns": [
                        {"name": "id", "type": "integer"},
                        {"name": "name", "type": "string"},
                    ],
                    "rows": [
                        {"id": 1, "name": "Alice"},
                        {"id": 2, "name": "Bob"},
                    ],
                },
                "retrieved_at": "2024-06-01T12:00:00Z",
            }
        }
        mock_client_cls.return_value = mock_client

        tool = _make_tool()
        results = _invoke_tool(tool, {"query_id": 1})

        assert len(results) == 1
        result = results[0]
        assert "columns" in result
        assert "rows" in result
        assert "metadata" in result
        assert len(result["columns"]) == 2
        assert len(result["rows"]) == 2
        assert result["metadata"]["total_row_count"] == 2
        assert result["metadata"]["returned_row_count"] == 2
        assert result["metadata"]["truncated"] is False

    @patch("tools.execute_query.RedashClient")
    def test_preserves_null_values(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.request.return_value = {
            "query_result": {
                "data": {
                    "columns": [
                        {"name": "id", "type": "integer"},
                        {"name": "value", "type": "string"},
                    ],
                    "rows": [
                        {"id": 1, "value": None},
                    ],
                },
                "retrieved_at": "2024-06-01T12:00:00Z",
            }
        }
        mock_client_cls.return_value = mock_client

        tool = _make_tool()
        results = _invoke_tool(tool, {"query_id": 1})

        result = results[0]
        assert result["rows"][0]["value"] is None


class TestErrorHandling:
    """Test error handling paths (Task 7.8)."""

    @patch("tools.execute_query.RedashClient")
    def test_query_not_found_returns_query_001(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.request.side_effect = PluginError(
            error_code=ErrorCode.SERVER_ERROR,
            message="Not found.",
            details={"http_status": 404},
        )
        mock_client_cls.return_value = mock_client

        tool = _make_tool()
        results = _invoke_tool(tool, {"query_id": 999})

        assert len(results) == 1
        assert results[0]["error"] is True
        assert results[0]["error_code"] == "QUERY_001"

    @patch("tools.execute_query.RedashClient")
    def test_execution_error_returns_query_003(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.request.return_value = {
            "query_result": {
                "data": {
                    "columns": [],
                    "rows": [],
                    "error": "Syntax error in SQL query at line 3",
                },
                "retrieved_at": "2024-06-01T12:00:00Z",
            }
        }
        mock_client_cls.return_value = mock_client

        tool = _make_tool()
        results = _invoke_tool(tool, {"query_id": 1})

        assert len(results) == 1
        assert results[0]["error"] is True
        assert results[0]["error_code"] == "QUERY_003"

    @patch("tools.execute_query.RedashClient")
    def test_job_response_returns_running_status(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.request.return_value = {
            "job": {
                "id": "abc-123",
                "status": 1,
            }
        }
        mock_client_cls.return_value = mock_client

        tool = _make_tool()
        results = _invoke_tool(tool, {"query_id": 1})

        assert len(results) == 1
        assert results[0]["status"] == "running"
        assert results[0]["job_id"] == "abc-123"
        assert results[0]["job_status"] == 1
        assert results[0]["query_id"] == 1
        assert "job_id" in results[0]["message"].lower() or "job" in results[0]["message"].lower()

    @patch("tools.execute_query.RedashClient")
    def test_auth_error_propagates(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.request.side_effect = PluginError(
            error_code=ErrorCode.AUTH_INVALID_CREDENTIALS,
            message="Authentication failed: invalid or expired API credentials.",
            details={"http_status": 401},
        )
        mock_client_cls.return_value = mock_client

        tool = _make_tool()
        results = _invoke_tool(tool, {"query_id": 1})

        assert len(results) == 1
        assert results[0]["error"] is True
        assert results[0]["error_code"] == "AUTH_001"

    @patch("tools.execute_query.RedashClient")
    def test_unexpected_error_returns_sanitized(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.request.side_effect = RuntimeError("Database connection pool exhausted")
        mock_client_cls.return_value = mock_client

        tool = _make_tool()
        results = _invoke_tool(tool, {"query_id": 1})

        assert len(results) == 1
        assert results[0]["error"] is True
        assert results[0]["error_code"] == "UNEXPECTED_001"
        # Should not contain internal details
        assert "RuntimeError" not in results[0]["message"]
        assert "Database connection pool" not in results[0]["message"]

    @patch("tools.execute_query.RedashClient")
    def test_server_error_propagates(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.request.side_effect = PluginError(
            error_code=ErrorCode.SERVER_ERROR,
            message="A Redash server-side error occurred.",
            details={"http_status": 500},
        )
        mock_client_cls.return_value = mock_client

        tool = _make_tool()
        results = _invoke_tool(tool, {"query_id": 1})

        assert len(results) == 1
        assert results[0]["error"] is True
        assert results[0]["error_code"] == "SERVER_001"
