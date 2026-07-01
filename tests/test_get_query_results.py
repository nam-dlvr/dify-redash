"""
Tests for the Get Query Results Tool (tools/get_query_results.py).

Covers:
- Task 8.1: YAML tool definition structure
- Task 8.2: GetQueryResultsTool class structure
- Task 8.3: Input validation - query_id must be positive integer (VAL_001)
- Task 8.4: API call to GET /api/queries/{id}/results
- Task 8.5: ResponseFormatter integration with retrieval_timestamp in metadata
- Task 8.6: No cached results handling
- Task 8.7: Query not found (QUERY_001 error)
"""

import json
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
import yaml

from tools._dify_stubs import Tool, ToolRuntime
from tools.get_query_results import GetQueryResultsTool
from utils.error_handler import ErrorCode, PluginError


def _make_tool(credentials: dict | None = None) -> GetQueryResultsTool:
    """Create a GetQueryResultsTool instance with mock runtime credentials."""
    tool = GetQueryResultsTool()
    tool.runtime = ToolRuntime(credentials=credentials or {
        "redash_url": "https://redash.example.com",
        "api_key": "test-api-key-1234",
    })
    return tool


def _invoke_tool(tool: GetQueryResultsTool, params: dict) -> list[dict]:
    """Invoke the tool and collect all text messages as parsed JSON."""
    results = []
    for msg in tool._invoke(params):
        results.append(json.loads(msg.text))
    return results


class TestYamlDefinition:
    """Test YAML tool definition file (Task 8.1)."""

    def test_yaml_loads_correctly(self):
        with open("tools/get_query_results.yaml") as f:
            data = yaml.safe_load(f)
        assert data is not None

    def test_yaml_has_identity(self):
        with open("tools/get_query_results.yaml") as f:
            data = yaml.safe_load(f)
        assert data["identity"]["name"] == "get_query_results"
        assert "label" in data["identity"]
        assert "en_US" in data["identity"]["label"]

    def test_yaml_has_description(self):
        with open("tools/get_query_results.yaml") as f:
            data = yaml.safe_load(f)
        assert "human" in data["description"]
        assert "llm" in data["description"]

    def test_yaml_has_parameters(self):
        with open("tools/get_query_results.yaml") as f:
            data = yaml.safe_load(f)
        params = data["parameters"]
        assert len(params) == 1

        param_names = [p["name"] for p in params]
        assert "query_id" in param_names

    def test_yaml_query_id_is_required_number(self):
        with open("tools/get_query_results.yaml") as f:
            data = yaml.safe_load(f)
        query_id_param = next(p for p in data["parameters"] if p["name"] == "query_id")
        assert query_id_param["type"] == "number"
        assert query_id_param["required"] is True


class TestGetQueryResultsToolClass:
    """Test GetQueryResultsTool class (Task 8.2)."""

    def test_extends_tool_base_class(self):
        tool = GetQueryResultsTool()
        assert isinstance(tool, Tool)

    def test_has_invoke_method(self):
        tool = GetQueryResultsTool()
        assert hasattr(tool, "_invoke")
        assert callable(tool._invoke)


class TestInputValidation:
    """Test query_id validation (Task 8.3)."""

    def test_missing_query_id_returns_val_001(self):
        tool = _make_tool()
        results = _invoke_tool(tool, {})

        assert len(results) == 1
        assert results[0]["error"] is True
        assert results[0]["error_code"] == "VAL_001"

    def test_non_numeric_query_id_returns_val_001(self):
        tool = _make_tool()
        results = _invoke_tool(tool, {"query_id": "abc"})

        assert len(results) == 1
        assert results[0]["error"] is True
        assert results[0]["error_code"] == "VAL_001"

    def test_zero_query_id_returns_val_001(self):
        tool = _make_tool()
        results = _invoke_tool(tool, {"query_id": 0})

        assert len(results) == 1
        assert results[0]["error"] is True
        assert results[0]["error_code"] == "VAL_001"

    def test_negative_query_id_returns_val_001(self):
        tool = _make_tool()
        results = _invoke_tool(tool, {"query_id": -5})

        assert len(results) == 1
        assert results[0]["error"] is True
        assert results[0]["error_code"] == "VAL_001"

    def test_float_query_id_is_accepted_as_int(self):
        """Float values like 3.0 should be accepted (truncated to integer)."""
        tool = _make_tool()
        with patch("tools.get_query_results.RedashClient") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.request.return_value = {
                "query_result": {
                    "data": {"columns": [], "rows": []},
                    "retrieved_at": "2024-01-01T00:00:00Z",
                }
            }
            mock_client_cls.return_value = mock_client

            results = _invoke_tool(tool, {"query_id": 3.9})
            # Should be accepted (int(3.9) == 3, which is > 0)
            assert "error" not in results[0]

    @patch("tools.get_query_results.RedashClient")
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


class TestApiCall:
    """Test API call to GET /api/queries/{id}/results (Task 8.4)."""

    @patch("tools.get_query_results.RedashClient")
    def test_calls_get_with_correct_path(self, mock_client_cls):
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
        assert call_args[0][0] == "GET"
        assert call_args[0][1] == "/api/queries/42/results"

    @patch("tools.get_query_results.RedashClient")
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

    @patch("tools.get_query_results.RedashClient")
    def test_no_request_body_sent(self, mock_client_cls):
        """GET request should not include a request body."""
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

        call_args = mock_client.request.call_args
        # Should only have positional args (method, path), no json body
        assert "json" not in call_args[1] if call_args[1] else True


class TestResponseFormatting:
    """Test ResponseFormatter integration with timestamps (Task 8.5)."""

    @patch("tools.get_query_results.RedashClient")
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

    @patch("tools.get_query_results.RedashClient")
    def test_includes_query_execution_timestamp(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.request.return_value = {
            "query_result": {
                "data": {
                    "columns": [{"name": "id", "type": "integer"}],
                    "rows": [{"id": 1}],
                },
                "retrieved_at": "2024-06-01T12:00:00Z",
            }
        }
        mock_client_cls.return_value = mock_client

        tool = _make_tool()
        results = _invoke_tool(tool, {"query_id": 1})

        result = results[0]
        assert "query_execution_timestamp" in result["metadata"]
        assert result["metadata"]["query_execution_timestamp"] == "2024-06-01T12:00:00Z"

    @patch("tools.get_query_results.RedashClient")
    def test_includes_retrieval_timestamp_in_iso_8601(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.request.return_value = {
            "query_result": {
                "data": {
                    "columns": [{"name": "id", "type": "integer"}],
                    "rows": [{"id": 1}],
                },
                "retrieved_at": "2024-06-01T12:00:00Z",
            }
        }
        mock_client_cls.return_value = mock_client

        tool = _make_tool()
        results = _invoke_tool(tool, {"query_id": 1})

        result = results[0]
        assert "retrieval_timestamp" in result["metadata"]
        # Verify it's a valid ISO 8601 timestamp ending with Z
        retrieval_ts = result["metadata"]["retrieval_timestamp"]
        assert retrieval_ts.endswith("Z")
        # Verify it can be parsed as a datetime
        parsed = datetime.strptime(retrieval_ts, "%Y-%m-%dT%H:%M:%SZ")
        assert parsed is not None

    @patch("tools.get_query_results.RedashClient")
    def test_retrieval_timestamp_is_current_utc(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.request.return_value = {
            "query_result": {
                "data": {
                    "columns": [{"name": "id", "type": "integer"}],
                    "rows": [{"id": 1}],
                },
                "retrieved_at": "2024-01-01T00:00:00Z",
            }
        }
        mock_client_cls.return_value = mock_client

        # Truncate 'before' to seconds to match the format used in the tool
        before = datetime.now(timezone.utc).replace(microsecond=0)
        tool = _make_tool()
        results = _invoke_tool(tool, {"query_id": 1})
        after = datetime.now(timezone.utc).replace(microsecond=0)

        result = results[0]
        retrieval_ts = datetime.strptime(
            result["metadata"]["retrieval_timestamp"], "%Y-%m-%dT%H:%M:%SZ"
        ).replace(tzinfo=timezone.utc)

        # The retrieval timestamp should be between before and after (all truncated to seconds)
        assert before <= retrieval_ts <= after


class TestNoCachedResults:
    """Test no cached results handling (Task 8.6)."""

    @patch("tools.get_query_results.RedashClient")
    def test_no_query_result_key_returns_message(self, mock_client_cls):
        mock_client = MagicMock()
        # Response with no query_result
        mock_client.request.return_value = {}
        mock_client_cls.return_value = mock_client

        tool = _make_tool()
        results = _invoke_tool(tool, {"query_id": 7})

        assert len(results) == 1
        result = results[0]
        assert "message" in result
        assert "7" in result["message"]
        assert "no cached results" in result["message"].lower() or "No cached results" in result["message"]
        assert result["query_id"] == 7

    @patch("tools.get_query_results.RedashClient")
    def test_null_query_result_returns_message(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.request.return_value = {"query_result": None}
        mock_client_cls.return_value = mock_client

        tool = _make_tool()
        results = _invoke_tool(tool, {"query_id": 15})

        assert len(results) == 1
        result = results[0]
        assert "message" in result
        assert "15" in result["message"]
        assert result["query_id"] == 15

    @patch("tools.get_query_results.RedashClient")
    def test_no_data_in_query_result_returns_message(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.request.return_value = {"query_result": {"retrieved_at": "2024-01-01T00:00:00Z"}}
        mock_client_cls.return_value = mock_client

        tool = _make_tool()
        results = _invoke_tool(tool, {"query_id": 20})

        assert len(results) == 1
        result = results[0]
        assert "message" in result
        assert result["query_id"] == 20

    @patch("tools.get_query_results.RedashClient")
    def test_null_data_in_query_result_returns_message(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.request.return_value = {
            "query_result": {"data": None, "retrieved_at": "2024-01-01T00:00:00Z"}
        }
        mock_client_cls.return_value = mock_client

        tool = _make_tool()
        results = _invoke_tool(tool, {"query_id": 25})

        assert len(results) == 1
        result = results[0]
        assert "message" in result
        assert result["query_id"] == 25


class TestQueryNotFound:
    """Test query not found error handling (Task 8.7)."""

    @patch("tools.get_query_results.RedashClient")
    def test_404_returns_query_001(self, mock_client_cls):
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
        assert "999" in results[0]["message"]

    @patch("tools.get_query_results.RedashClient")
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

    @patch("tools.get_query_results.RedashClient")
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

    @patch("tools.get_query_results.RedashClient")
    def test_unexpected_error_returns_sanitized(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.request.side_effect = RuntimeError("Something went wrong")
        mock_client_cls.return_value = mock_client

        tool = _make_tool()
        results = _invoke_tool(tool, {"query_id": 1})

        assert len(results) == 1
        assert results[0]["error"] is True
        assert results[0]["error_code"] == "UNEXPECTED_001"
        assert "RuntimeError" not in results[0]["message"]
        assert "Something went wrong" not in results[0]["message"]
