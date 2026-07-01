"""
Tests for the Response Formatter utility (utils/response_formatter.py).

Covers:
- Task 4.1: ResponseFormatter class creation
- Task 4.2: Column metadata extraction (name, type, display_order)
- Task 4.3: Date/timestamp conversion to ISO 8601 UTC
- Task 4.4: Null value preservation
- Task 4.5: Numeric precision preservation
- Task 4.6: Row truncation (50 rows max)
- Task 4.7: Size-based truncation (1 MB limit)
- Task 4.8: format_results() method with consistent structure
"""

import json
from decimal import Decimal

import pytest

from utils.response_formatter import ResponseFormatter


@pytest.fixture
def formatter():
    """Create a fresh ResponseFormatter instance."""
    return ResponseFormatter()


def _make_raw_results(columns, rows, retrieved_at="2024-01-20T12:00:00.000Z"):
    """Helper to build a raw Redash API result structure."""
    return {
        "query_result": {
            "data": {
                "columns": columns,
                "rows": rows,
            },
            "retrieved_at": retrieved_at,
        }
    }


# ─── Task 4.1: ResponseFormatter Class ─────────────────────────────────────────


class TestResponseFormatterClass:
    """Test ResponseFormatter class exists with correct constants (Task 4.1)."""

    def test_class_exists(self):
        formatter = ResponseFormatter()
        assert formatter is not None

    def test_max_rows_constant(self):
        assert ResponseFormatter.MAX_ROWS == 50

    def test_max_size_bytes_constant(self):
        assert ResponseFormatter.MAX_SIZE_BYTES == 1_048_576


# ─── Task 4.2: Column Metadata Extraction ──────────────────────────────────────


class TestColumnMetadataExtraction:
    """Test column metadata extraction with name, type, display_order (Task 4.2)."""

    def test_extracts_column_name_and_type(self, formatter):
        raw = _make_raw_results(
            columns=[
                {"name": "id", "type": "integer", "friendly_name": "Id"},
                {"name": "name", "type": "string", "friendly_name": "Name"},
            ],
            rows=[],
        )
        result = formatter.format_results(raw)
        assert result["columns"][0]["name"] == "id"
        assert result["columns"][0]["type"] == "integer"
        assert result["columns"][1]["name"] == "name"
        assert result["columns"][1]["type"] == "string"

    def test_assigns_display_order_by_position(self, formatter):
        raw = _make_raw_results(
            columns=[
                {"name": "a", "type": "string", "friendly_name": "A"},
                {"name": "b", "type": "integer", "friendly_name": "B"},
                {"name": "c", "type": "float", "friendly_name": "C"},
            ],
            rows=[],
        )
        result = formatter.format_results(raw)
        assert result["columns"][0]["display_order"] == 0
        assert result["columns"][1]["display_order"] == 1
        assert result["columns"][2]["display_order"] == 2

    def test_handles_empty_columns(self, formatter):
        raw = _make_raw_results(columns=[], rows=[])
        result = formatter.format_results(raw)
        assert result["columns"] == []

    def test_column_metadata_only_contains_name_type_display_order(self, formatter):
        raw = _make_raw_results(
            columns=[{"name": "id", "type": "integer", "friendly_name": "Id"}],
            rows=[],
        )
        result = formatter.format_results(raw)
        col = result["columns"][0]
        assert set(col.keys()) == {"name", "type", "display_order"}


# ─── Task 4.3: Date/Timestamp Conversion ───────────────────────────────────────


class TestDateTimestampConversion:
    """Test date/timestamp conversion to ISO 8601 UTC (Task 4.3)."""

    def test_converts_datetime_column_to_iso8601(self, formatter):
        raw = _make_raw_results(
            columns=[{"name": "created_at", "type": "datetime", "friendly_name": "Created At"}],
            rows=[{"created_at": "2024-01-15T10:30:00"}],
        )
        result = formatter.format_results(raw)
        assert result["rows"][0]["created_at"] == "2024-01-15T10:30:00Z"

    def test_converts_date_column_to_iso8601(self, formatter):
        raw = _make_raw_results(
            columns=[{"name": "birth_date", "type": "date", "friendly_name": "Birth Date"}],
            rows=[{"birth_date": "2024-01-15"}],
        )
        result = formatter.format_results(raw)
        assert result["rows"][0]["birth_date"] == "2024-01-15T00:00:00Z"

    def test_converts_timestamp_column_to_iso8601(self, formatter):
        raw = _make_raw_results(
            columns=[{"name": "ts", "type": "timestamp", "friendly_name": "Timestamp"}],
            rows=[{"ts": "2024-01-15 10:30:00"}],
        )
        result = formatter.format_results(raw)
        assert result["rows"][0]["ts"] == "2024-01-15T10:30:00Z"

    def test_converts_datetime_with_microseconds(self, formatter):
        raw = _make_raw_results(
            columns=[{"name": "ts", "type": "datetime", "friendly_name": "Timestamp"}],
            rows=[{"ts": "2024-01-15T10:30:00.123456"}],
        )
        result = formatter.format_results(raw)
        assert result["rows"][0]["ts"] == "2024-01-15T10:30:00Z"

    def test_handles_already_utc_datetime(self, formatter):
        raw = _make_raw_results(
            columns=[{"name": "ts", "type": "datetime", "friendly_name": "Timestamp"}],
            rows=[{"ts": "2024-01-15T10:30:00Z"}],
        )
        result = formatter.format_results(raw)
        assert result["rows"][0]["ts"] == "2024-01-15T10:30:00Z"

    def test_preserves_null_in_date_column(self, formatter):
        raw = _make_raw_results(
            columns=[{"name": "ts", "type": "datetime", "friendly_name": "Timestamp"}],
            rows=[{"ts": None}],
        )
        result = formatter.format_results(raw)
        assert result["rows"][0]["ts"] is None

    def test_does_not_convert_non_date_columns(self, formatter):
        raw = _make_raw_results(
            columns=[
                {"name": "id", "type": "integer", "friendly_name": "Id"},
                {"name": "name", "type": "string", "friendly_name": "Name"},
            ],
            rows=[{"id": 1, "name": "2024-01-15T10:30:00"}],
        )
        result = formatter.format_results(raw)
        # The string value in the non-date column should NOT be converted
        assert result["rows"][0]["name"] == "2024-01-15T10:30:00"
        assert result["rows"][0]["id"] == 1


# ─── Task 4.4: Null Value Preservation ─────────────────────────────────────────


class TestNullValuePreservation:
    """Test null values are preserved explicitly (Task 4.4)."""

    def test_null_preserved_in_string_column(self, formatter):
        raw = _make_raw_results(
            columns=[{"name": "name", "type": "string", "friendly_name": "Name"}],
            rows=[{"name": None}],
        )
        result = formatter.format_results(raw)
        assert result["rows"][0]["name"] is None

    def test_null_preserved_in_integer_column(self, formatter):
        raw = _make_raw_results(
            columns=[{"name": "count", "type": "integer", "friendly_name": "Count"}],
            rows=[{"count": None}],
        )
        result = formatter.format_results(raw)
        assert result["rows"][0]["count"] is None

    def test_null_preserved_in_float_column(self, formatter):
        raw = _make_raw_results(
            columns=[{"name": "score", "type": "float", "friendly_name": "Score"}],
            rows=[{"score": None}],
        )
        result = formatter.format_results(raw)
        assert result["rows"][0]["score"] is None

    def test_null_serializes_to_json_null(self, formatter):
        raw = _make_raw_results(
            columns=[{"name": "val", "type": "string", "friendly_name": "Val"}],
            rows=[{"val": None}],
        )
        result = formatter.format_results(raw)
        serialized = json.dumps(result)
        assert '"val": null' in serialized


# ─── Task 4.5: Numeric Precision Preservation ──────────────────────────────────


class TestNumericPrecisionPreservation:
    """Test numeric precision is preserved without rounding or scientific notation (Task 4.5)."""

    def test_integer_preserved(self, formatter):
        raw = _make_raw_results(
            columns=[{"name": "id", "type": "integer", "friendly_name": "Id"}],
            rows=[{"id": 123456789}],
        )
        result = formatter.format_results(raw)
        assert result["rows"][0]["id"] == 123456789

    def test_float_preserved(self, formatter):
        raw = _make_raw_results(
            columns=[{"name": "price", "type": "float", "friendly_name": "Price"}],
            rows=[{"price": 19.99}],
        )
        result = formatter.format_results(raw)
        assert result["rows"][0]["price"] == 19.99

    def test_large_integer_preserved(self, formatter):
        raw = _make_raw_results(
            columns=[{"name": "big", "type": "integer", "friendly_name": "Big"}],
            rows=[{"big": 99999999999999}],
        )
        result = formatter.format_results(raw)
        assert result["rows"][0]["big"] == 99999999999999

    def test_decimal_converted_to_string(self, formatter):
        raw = _make_raw_results(
            columns=[{"name": "amount", "type": "float", "friendly_name": "Amount"}],
            rows=[{"amount": Decimal("123.456789012345")}],
        )
        result = formatter.format_results(raw)
        assert result["rows"][0]["amount"] == "123.456789012345"

    def test_float_not_converted_to_scientific_notation(self, formatter):
        raw = _make_raw_results(
            columns=[{"name": "val", "type": "float", "friendly_name": "Val"}],
            rows=[{"val": 0.000123}],
        )
        result = formatter.format_results(raw)
        serialized = json.dumps(result)
        # Should not contain scientific notation like 1.23e-04
        assert "e-" not in serialized
        assert result["rows"][0]["val"] == 0.000123


# ─── Task 4.6: Row Truncation ──────────────────────────────────────────────────


class TestRowTruncation:
    """Test row truncation at 50 rows maximum (Task 4.6)."""

    def test_no_truncation_for_50_rows(self, formatter):
        rows = [{"id": i} for i in range(50)]
        raw = _make_raw_results(
            columns=[{"name": "id", "type": "integer", "friendly_name": "Id"}],
            rows=rows,
        )
        result = formatter.format_results(raw)
        assert len(result["rows"]) == 50
        assert result["metadata"]["truncated"] is False
        assert result["metadata"]["total_row_count"] == 50
        assert result["metadata"]["returned_row_count"] == 50

    def test_truncates_to_50_rows(self, formatter):
        rows = [{"id": i} for i in range(100)]
        raw = _make_raw_results(
            columns=[{"name": "id", "type": "integer", "friendly_name": "Id"}],
            rows=rows,
        )
        result = formatter.format_results(raw)
        assert len(result["rows"]) == 50
        assert result["metadata"]["truncated"] is True
        assert result["metadata"]["total_row_count"] == 100
        assert result["metadata"]["returned_row_count"] == 50

    def test_preserves_first_50_rows(self, formatter):
        rows = [{"id": i} for i in range(75)]
        raw = _make_raw_results(
            columns=[{"name": "id", "type": "integer", "friendly_name": "Id"}],
            rows=rows,
        )
        result = formatter.format_results(raw)
        for i in range(50):
            assert result["rows"][i]["id"] == i

    def test_no_truncation_for_fewer_than_50_rows(self, formatter):
        rows = [{"id": i} for i in range(10)]
        raw = _make_raw_results(
            columns=[{"name": "id", "type": "integer", "friendly_name": "Id"}],
            rows=rows,
        )
        result = formatter.format_results(raw)
        assert len(result["rows"]) == 10
        assert result["metadata"]["truncated"] is False
        assert result["metadata"]["total_row_count"] == 10
        assert result["metadata"]["returned_row_count"] == 10


# ─── Task 4.7: Size-Based Truncation ───────────────────────────────────────────


class TestSizeBasedTruncation:
    """Test size-based truncation at 1 MB limit (Task 4.7)."""

    def test_no_size_truncation_within_limit(self, formatter):
        rows = [{"id": i, "name": f"row_{i}"} for i in range(10)]
        raw = _make_raw_results(
            columns=[
                {"name": "id", "type": "integer", "friendly_name": "Id"},
                {"name": "name", "type": "string", "friendly_name": "Name"},
            ],
            rows=rows,
        )
        result = formatter.format_results(raw)
        assert len(result["rows"]) == 10
        assert result["metadata"]["truncated"] is False

    def test_size_truncation_applied_when_exceeding_1mb(self, formatter):
        # Create rows with large string data that will exceed 1 MB
        large_value = "x" * 50000  # 50KB per row
        rows = [{"id": i, "data": large_value} for i in range(50)]
        raw = _make_raw_results(
            columns=[
                {"name": "id", "type": "integer", "friendly_name": "Id"},
                {"name": "data", "type": "string", "friendly_name": "Data"},
            ],
            rows=rows,
        )
        result = formatter.format_results(raw)
        # With 50 rows * ~50KB each = ~2.5MB, should be truncated
        assert len(result["rows"]) < 50
        assert result["metadata"]["truncated"] is True
        assert result["metadata"]["total_row_count"] == 50

    def test_size_truncation_result_within_1mb(self, formatter):
        # Create rows that exceed 1MB total
        large_value = "y" * 100000  # 100KB per row
        rows = [{"id": i, "data": large_value} for i in range(50)]
        raw = _make_raw_results(
            columns=[
                {"name": "id", "type": "integer", "friendly_name": "Id"},
                {"name": "data", "type": "string", "friendly_name": "Data"},
            ],
            rows=rows,
        )
        result = formatter.format_results(raw)
        # Verify the final result is within 1 MB
        serialized = json.dumps(result)
        assert len(serialized.encode("utf-8")) <= ResponseFormatter.MAX_SIZE_BYTES

    def test_size_truncation_sets_truncation_indicator(self, formatter):
        large_value = "z" * 50000
        rows = [{"id": i, "data": large_value} for i in range(50)]
        raw = _make_raw_results(
            columns=[
                {"name": "id", "type": "integer", "friendly_name": "Id"},
                {"name": "data", "type": "string", "friendly_name": "Data"},
            ],
            rows=rows,
        )
        result = formatter.format_results(raw)
        assert result["metadata"]["truncated"] is True
        assert result["metadata"]["returned_row_count"] < result["metadata"]["total_row_count"]


# ─── Task 4.8: format_results() Method Structure ───────────────────────────────


class TestFormatResultsStructure:
    """Test format_results() returns consistent structure (Task 4.8)."""

    def test_returns_columns_rows_metadata(self, formatter):
        raw = _make_raw_results(
            columns=[{"name": "id", "type": "integer", "friendly_name": "Id"}],
            rows=[{"id": 1}],
        )
        result = formatter.format_results(raw)
        assert "columns" in result
        assert "rows" in result
        assert "metadata" in result

    def test_metadata_contains_required_fields(self, formatter):
        raw = _make_raw_results(
            columns=[{"name": "id", "type": "integer", "friendly_name": "Id"}],
            rows=[{"id": 1}],
        )
        result = formatter.format_results(raw)
        metadata = result["metadata"]
        assert "total_row_count" in metadata
        assert "returned_row_count" in metadata
        assert "truncated" in metadata
        assert "query_execution_timestamp" in metadata

    def test_query_execution_timestamp_in_iso8601(self, formatter):
        raw = _make_raw_results(
            columns=[{"name": "id", "type": "integer", "friendly_name": "Id"}],
            rows=[{"id": 1}],
            retrieved_at="2024-01-20T12:00:00.000Z",
        )
        result = formatter.format_results(raw)
        assert result["metadata"]["query_execution_timestamp"] == "2024-01-20T12:00:00Z"

    def test_handles_empty_results(self, formatter):
        raw = _make_raw_results(columns=[], rows=[])
        result = formatter.format_results(raw)
        assert result["columns"] == []
        assert result["rows"] == []
        assert result["metadata"]["total_row_count"] == 0
        assert result["metadata"]["returned_row_count"] == 0
        assert result["metadata"]["truncated"] is False

    def test_handles_missing_query_result_key(self, formatter):
        raw = {}
        result = formatter.format_results(raw)
        assert result["columns"] == []
        assert result["rows"] == []
        assert result["metadata"]["total_row_count"] == 0
        assert result["metadata"]["returned_row_count"] == 0

    def test_full_integration_with_multiple_types(self, formatter):
        raw = _make_raw_results(
            columns=[
                {"name": "id", "type": "integer", "friendly_name": "Id"},
                {"name": "name", "type": "string", "friendly_name": "Name"},
                {"name": "created_at", "type": "datetime", "friendly_name": "Created At"},
                {"name": "score", "type": "float", "friendly_name": "Score"},
            ],
            rows=[
                {"id": 1, "name": "Alice", "created_at": "2024-01-15T10:30:00", "score": 95.5},
                {"id": 2, "name": None, "created_at": "2024-01-16T11:45:00", "score": None},
            ],
            retrieved_at="2024-01-20T12:00:00.000Z",
        )
        result = formatter.format_results(raw)

        # Columns
        assert len(result["columns"]) == 4
        assert result["columns"][0] == {"name": "id", "type": "integer", "display_order": 0}
        assert result["columns"][3] == {"name": "score", "type": "float", "display_order": 3}

        # Rows
        assert result["rows"][0]["id"] == 1
        assert result["rows"][0]["name"] == "Alice"
        assert result["rows"][0]["created_at"] == "2024-01-15T10:30:00Z"
        assert result["rows"][0]["score"] == 95.5
        assert result["rows"][1]["name"] is None
        assert result["rows"][1]["score"] is None
        assert result["rows"][1]["created_at"] == "2024-01-16T11:45:00Z"

        # Metadata
        assert result["metadata"]["total_row_count"] == 2
        assert result["metadata"]["returned_row_count"] == 2
        assert result["metadata"]["truncated"] is False
        assert result["metadata"]["query_execution_timestamp"] == "2024-01-20T12:00:00Z"
