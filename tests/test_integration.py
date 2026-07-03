"""
Integration tests for the Redash Extension for Dify plugin.

Covers:
- Task 12.1: Verify all YAML tool definitions load correctly and match expected parameter schemas
- Task 12.6: Verify error codes are unique string identifiers included in all error responses
- Task 12.7: Verify API Key masking (additional coverage - primary tests in test_redash_client.py)

Tasks 12.2-12.5 are verified by running existing test suites:
- test_provider.py (Task 12.2)
- test_execute_query.py, test_get_query_results.py, test_list_dashboards.py,
  test_get_dashboard_details.py, test_list_data_sources.py, test_list_queries.py (Task 12.3)
- test_response_formatter.py (Task 12.4)
- test_redash_client.py (Task 12.5)
"""

import os
from pathlib import Path

import yaml
import pytest

from utils.error_handler import ErrorCode, PluginError, format_error_response, handle_unexpected_error
from utils.redash_client import mask_api_key


# ─── Paths ─────────────────────────────────────────────────────────────────────

PROJECT_ROOT = Path(__file__).parent.parent


# ─── Task 12.1: YAML Tool Definitions ─────────────────────────────────────────


class TestYamlToolDefinitions:
    """Verify all YAML tool definitions load correctly and match expected schemas (Task 12.1)."""

    TOOL_YAML_FILES = [
        "tools/list_queries.yaml",
        "tools/execute_query.yaml",
        "tools/get_query_results.yaml",
        "tools/list_dashboards.yaml",
        "tools/get_dashboard_details.yaml",
        "tools/list_data_sources.yaml",
    ]

    PROVIDER_YAML = "provider/redash.yaml"
    MANIFEST_YAML = "manifest.yaml"

    def _load_yaml(self, relative_path: str) -> dict:
        """Load a YAML file from the project root."""
        path = PROJECT_ROOT / relative_path
        assert path.exists(), f"YAML file not found: {path}"
        with open(path, "r") as f:
            return yaml.safe_load(f)

    def test_all_tool_yaml_files_exist(self):
        """Verify all 6 tool YAML files exist."""
        for yaml_file in self.TOOL_YAML_FILES:
            path = PROJECT_ROOT / yaml_file
            assert path.exists(), f"Tool YAML file missing: {yaml_file}"

    def test_provider_yaml_exists(self):
        """Verify provider YAML file exists."""
        path = PROJECT_ROOT / self.PROVIDER_YAML
        assert path.exists(), f"Provider YAML file missing: {self.PROVIDER_YAML}"

    def test_manifest_yaml_exists(self):
        """Verify manifest YAML file exists."""
        path = PROJECT_ROOT / self.MANIFEST_YAML
        assert path.exists(), f"Manifest YAML file missing: {self.MANIFEST_YAML}"

    @pytest.mark.parametrize("yaml_file", TOOL_YAML_FILES)
    def test_tool_yaml_has_identity_section(self, yaml_file):
        """Each tool YAML must have an identity section with name, author, label."""
        data = self._load_yaml(yaml_file)
        assert "identity" in data, f"{yaml_file} missing 'identity' section"
        identity = data["identity"]
        assert "name" in identity, f"{yaml_file} identity missing 'name'"
        assert "author" in identity, f"{yaml_file} identity missing 'author'"
        assert "label" in identity, f"{yaml_file} identity missing 'label'"
        assert isinstance(identity["name"], str) and len(identity["name"]) > 0

    @pytest.mark.parametrize("yaml_file", TOOL_YAML_FILES)
    def test_tool_yaml_has_description_section(self, yaml_file):
        """Each tool YAML must have a description section with human and llm descriptions."""
        data = self._load_yaml(yaml_file)
        assert "description" in data, f"{yaml_file} missing 'description' section"
        desc = data["description"]
        assert "human" in desc, f"{yaml_file} description missing 'human'"
        assert "llm" in desc, f"{yaml_file} description missing 'llm'"

    @pytest.mark.parametrize("yaml_file", TOOL_YAML_FILES)
    def test_tool_yaml_has_parameters_section(self, yaml_file):
        """Each tool YAML must have a parameters section (may be empty list)."""
        data = self._load_yaml(yaml_file)
        assert "parameters" in data, f"{yaml_file} missing 'parameters' section"
        assert isinstance(data["parameters"], list), f"{yaml_file} 'parameters' must be a list"

    @pytest.mark.parametrize("yaml_file", TOOL_YAML_FILES)
    def test_tool_yaml_parameters_have_required_fields(self, yaml_file):
        """Each parameter must have name, type, required, and form fields."""
        data = self._load_yaml(yaml_file)
        for param in data["parameters"]:
            assert "name" in param, f"{yaml_file} parameter missing 'name'"
            assert "type" in param, f"{yaml_file} parameter '{param.get('name', '?')}' missing 'type'"
            assert "required" in param, f"{yaml_file} parameter '{param['name']}' missing 'required'"
            assert "form" in param, f"{yaml_file} parameter '{param['name']}' missing 'form'"
            assert isinstance(param["required"], bool), (
                f"{yaml_file} parameter '{param['name']}' 'required' must be boolean"
            )

    def test_list_queries_yaml_parameters(self):
        """Verify list_queries.yaml parameter types and required flags."""
        data = self._load_yaml("tools/list_queries.yaml")
        params = {p["name"]: p for p in data["parameters"]}
        assert "page_size" in params
        assert params["page_size"]["type"] == "number"
        assert params["page_size"]["required"] is False
        assert "search" in params
        assert params["search"]["type"] == "string"
        assert params["search"]["required"] is False

    def test_execute_query_yaml_parameters(self):
        """Verify execute_query.yaml parameter types and required flags."""
        data = self._load_yaml("tools/execute_query.yaml")
        params = {p["name"]: p for p in data["parameters"]}
        assert "query_id" in params
        assert params["query_id"]["type"] == "number"
        assert params["query_id"]["required"] is True
        assert "parameters" in params
        assert params["parameters"]["type"] == "string"
        assert params["parameters"]["required"] is False
        assert "max_age" in params
        assert params["max_age"]["type"] == "number"
        assert params["max_age"]["required"] is False

    def test_get_query_results_yaml_parameters(self):
        """Verify get_query_results.yaml parameter types and required flags."""
        data = self._load_yaml("tools/get_query_results.yaml")
        params = {p["name"]: p for p in data["parameters"]}
        assert "query_id" in params
        assert params["query_id"]["type"] == "number"
        assert params["query_id"]["required"] is False
        assert "job_id" in params
        assert params["job_id"]["type"] == "string"
        assert params["job_id"]["required"] is False

    def test_list_dashboards_yaml_parameters(self):
        """Verify list_dashboards.yaml parameter types and required flags."""
        data = self._load_yaml("tools/list_dashboards.yaml")
        params = {p["name"]: p for p in data["parameters"]}
        assert "page_size" in params
        assert params["page_size"]["type"] == "number"
        assert params["page_size"]["required"] is False
        assert "page" in params
        assert params["page"]["type"] == "number"
        assert params["page"]["required"] is False
        assert "search" in params
        assert params["search"]["type"] == "string"
        assert params["search"]["required"] is False

    def test_get_dashboard_details_yaml_parameters(self):
        """Verify get_dashboard_details.yaml parameter types and required flags."""
        data = self._load_yaml("tools/get_dashboard_details.yaml")
        params = {p["name"]: p for p in data["parameters"]}
        assert "dashboard_slug" in params
        assert params["dashboard_slug"]["type"] == "string"
        assert params["dashboard_slug"]["required"] is True
        assert "include_results" in params
        assert params["include_results"]["type"] == "boolean"
        assert params["include_results"]["required"] is False

    def test_list_data_sources_yaml_no_required_parameters(self):
        """Verify list_data_sources.yaml has no required parameters."""
        data = self._load_yaml("tools/list_data_sources.yaml")
        assert data["parameters"] == []

    def test_provider_yaml_has_identity_section(self):
        """Verify provider YAML has identity with name, author, label, description."""
        data = self._load_yaml(self.PROVIDER_YAML)
        assert "identity" in data
        identity = data["identity"]
        assert "name" in identity
        assert "author" in identity
        assert "label" in identity
        assert "description" in identity

    def test_provider_yaml_has_credentials(self):
        """Verify provider YAML defines required credentials."""
        data = self._load_yaml(self.PROVIDER_YAML)
        assert "credentials_for_provider" in data
        creds = data["credentials_for_provider"]
        assert "redash_url" in creds
        assert creds["redash_url"]["required"] is True
        assert "api_key" in creds
        assert creds["api_key"]["required"] is True
        assert creds["api_key"]["type"] == "secret-input"

    def test_provider_yaml_lists_all_tools(self):
        """Verify provider YAML references all 6 tool definition files."""
        data = self._load_yaml(self.PROVIDER_YAML)
        assert "tools" in data
        tools = data["tools"]
        assert len(tools) == 6
        expected_tools = {
            "tools/list_queries.yaml",
            "tools/execute_query.yaml",
            "tools/get_query_results.yaml",
            "tools/list_dashboards.yaml",
            "tools/get_dashboard_details.yaml",
            "tools/list_data_sources.yaml",
        }
        assert set(tools) == expected_tools

    def test_manifest_yaml_has_required_fields(self):
        """Verify manifest YAML has all required fields."""
        data = self._load_yaml(self.MANIFEST_YAML)
        assert "version" in data
        assert "type" in data
        assert "author" in data
        assert "name" in data
        assert "description" in data
        # Verify semver format
        version = data["version"]
        parts = version.split(".")
        assert len(parts) == 3, f"Version '{version}' not in MAJOR.MINOR.PATCH format"
        for part in parts:
            assert part.isdigit(), f"Version part '{part}' is not a digit"

    def test_manifest_yaml_declares_python_runner(self):
        """Verify manifest declares Python 3.12 runner."""
        data = self._load_yaml(self.MANIFEST_YAML)
        assert "meta" in data
        assert "runner" in data["meta"]
        runner = data["meta"]["runner"]
        assert runner["language"] == "python"
        assert runner["version"] == "3.12"

    def test_manifest_yaml_has_resource_limits(self):
        """Verify manifest declares resource limits."""
        data = self._load_yaml(self.MANIFEST_YAML)
        assert "resource" in data
        assert "memory" in data["resource"]
        assert isinstance(data["resource"]["memory"], int)

    def test_manifest_yaml_references_provider(self):
        """Verify manifest references the provider YAML."""
        data = self._load_yaml(self.MANIFEST_YAML)
        assert "plugins" in data
        assert "tools" in data["plugins"]
        assert "provider/redash.yaml" in data["plugins"]["tools"]


# ─── Task 12.6: Error Code Uniqueness and Inclusion ────────────────────────────


class TestErrorCodeUniqueness:
    """Verify error codes are unique string identifiers included in all error responses (Task 12.6)."""

    def test_all_error_codes_are_unique(self):
        """Each ErrorCode enum value must be a unique string."""
        values = [code.value for code in ErrorCode]
        assert len(values) == len(set(values)), "ErrorCode values are not unique"

    def test_all_error_codes_are_strings(self):
        """Each ErrorCode value must be a string."""
        for code in ErrorCode:
            assert isinstance(code.value, str), f"ErrorCode {code.name} is not a string"
            assert len(code.value) > 0, f"ErrorCode {code.name} is empty"

    def test_error_codes_follow_naming_convention(self):
        """Error codes should follow CATEGORY_NNN format."""
        import re
        pattern = re.compile(r"^[A-Z]+_\d{3}$")
        for code in ErrorCode:
            assert pattern.match(code.value), (
                f"ErrorCode {code.name} value '{code.value}' does not match CATEGORY_NNN format"
            )

    def test_expected_error_codes_exist(self):
        """Verify all expected error codes from the design doc are defined."""
        expected_codes = [
            "AUTH_001", "AUTH_002", "CONN_001", "CONN_002", "RATE_001",
            "QUERY_001", "QUERY_002", "QUERY_003", "QUERY_004",
            "DASH_001", "VAL_001", "SERVER_001", "UNEXPECTED_001",
        ]
        actual_values = [code.value for code in ErrorCode]
        for expected in expected_codes:
            assert expected in actual_values, f"Expected error code '{expected}' not found"

    def test_format_error_response_includes_error_code(self):
        """format_error_response always includes error_code field."""
        for code in ErrorCode:
            error = PluginError(
                error_code=code,
                message=f"Test message for {code.value}",
            )
            response = format_error_response(error)
            assert "error_code" in response, f"Response for {code.name} missing 'error_code'"
            assert response["error_code"] == code.value
            assert "error" in response
            assert response["error"] is True
            assert "message" in response

    def test_format_error_response_with_details(self):
        """format_error_response includes optional details when provided."""
        error = PluginError(
            error_code=ErrorCode.SERVER_ERROR,
            message="Server error",
            details={"http_status": 500},
        )
        response = format_error_response(error)
        assert "details" in response
        assert response["details"]["http_status"] == 500

    def test_format_error_response_without_details(self):
        """format_error_response works without details."""
        error = PluginError(
            error_code=ErrorCode.VALIDATION_ERROR,
            message="Validation failed",
        )
        response = format_error_response(error)
        assert "error_code" in response
        assert response["error_code"] == "VAL_001"
        assert "details" not in response

    def test_handle_unexpected_error_includes_error_code(self):
        """handle_unexpected_error returns response with error_code field."""
        result = handle_unexpected_error(RuntimeError("test"))
        assert "error_code" in result
        assert result["error_code"] == "UNEXPECTED_001"
        assert "error" in result
        assert result["error"] is True
        assert "message" in result
        # Should NOT contain stack trace info in the message
        assert "traceback" not in result["message"].lower()
        assert "file" not in result["message"].lower()

    def test_handle_unexpected_error_does_not_expose_internals(self):
        """handle_unexpected_error sanitizes sensitive info from response."""
        try:
            my_secret_var = "sensitive_data"
            raise ValueError(f"Error with secret: {my_secret_var}")
        except ValueError as e:
            result = handle_unexpected_error(e)

        # The response message should NOT contain the sensitive data
        assert "sensitive_data" not in result["message"]
        assert "my_secret_var" not in result["message"]


# ─── Task 12.7: API Key Masking (Additional Coverage) ──────────────────────────


class TestApiKeyMaskingIntegration:
    """Verify API Key masking across the system (Task 12.7)."""

    def test_mask_api_key_standard_length(self):
        """Standard API key shows only last 4 characters."""
        result = mask_api_key("abcdefghijklmnop1234")
        assert result == "****1234"
        # Verify original key is not present
        assert "abcdefghijklmnop" not in result

    def test_mask_api_key_minimum_revealed(self):
        """Keys longer than 4 chars show exactly last 4."""
        result = mask_api_key("12345")
        assert result == "****2345"

    def test_mask_api_key_short_key_fully_hidden(self):
        """Keys of 4 chars or fewer are fully masked."""
        assert mask_api_key("abcd") == "****"
        assert mask_api_key("abc") == "****"
        assert mask_api_key("ab") == "****"
        assert mask_api_key("a") == "****"
        assert mask_api_key("") == "****"

    def test_mask_api_key_never_reveals_more_than_4_chars(self):
        """Regardless of key length, never more than 4 chars visible."""
        for length in range(0, 100):
            key = "x" * length
            masked = mask_api_key(key)
            # The visible portion is at most 4 chars after the placeholder
            visible_part = masked.replace("****", "")
            assert len(visible_part) <= 4

    def test_redash_client_stores_masked_key(self):
        """RedashClient instance stores the masked key for use in logs."""
        from utils.redash_client import RedashClient
        client = RedashClient("https://redash.example.com", "my-super-secret-api-key-9999")
        assert client._masked_key == "****9999"
        # The full key should NOT be in the masked representation
        assert "my-super-secret-api-key" not in client._masked_key
