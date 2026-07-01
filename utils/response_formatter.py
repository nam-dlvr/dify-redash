"""
Response formatting utilities for Redash query results.

Transforms raw Redash API query result responses into a standardized structure
with column metadata, row data, and result metadata. Handles date conversion,
null preservation, numeric precision, row truncation, and size-based truncation.

Addresses: Requirement 8 (AC 1-6)
"""

import json
import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

logger = logging.getLogger(__name__)

# Date/timestamp column types from Redash that should be converted to ISO 8601
_DATE_COLUMN_TYPES = {"datetime", "date", "timestamp"}


class _DecimalEncoder(json.JSONEncoder):
    """Custom JSON encoder that converts Decimal values to string representation."""

    def default(self, obj: Any) -> Any:
        if isinstance(obj, Decimal):
            return str(obj)
        return super().default(obj)


class ResponseFormatter:
    """
    Formats Redash query results into a standardized structure.

    Output structure (Req 8, AC 2):
    {
        "columns": [
            {"name": str, "type": str, "display_order": int}
        ],
        "rows": [...],
        "metadata": {
            "total_row_count": int,
            "returned_row_count": int,
            "truncated": bool,
            "query_execution_timestamp": str (ISO 8601)
        }
    }
    """

    MAX_ROWS = 50  # Req 8, AC 1
    MAX_SIZE_BYTES = 1_048_576  # 1 MB limit (Req 8, AC 5)

    def format_results(self, raw_results: dict) -> dict:
        """
        Transform Redash query results into standardized format.

        Processing steps:
        1. Extract column metadata with display order (Req 8, AC 2)
        2. Convert date/timestamp columns to ISO 8601 UTC (Req 8, AC 3)
        3. Preserve null values explicitly (Req 8, AC 4)
        4. Preserve numeric precision without rounding (Req 8, AC 6)
        5. Truncate to MAX_ROWS if needed (Req 8, AC 1)
        6. Check JSON-serialized size, further truncate if > 1MB (Req 8, AC 5)
        7. Set truncation indicators in metadata

        Args:
            raw_results: Raw Redash API response dict, expected to have the
                structure: {"query_result": {"data": {"columns": [...], "rows": [...]},
                "retrieved_at": "..."}}

        Returns:
            Standardized result dict with columns, rows, and metadata.
        """
        # Extract data from the Redash response structure
        query_result = raw_results.get("query_result", {})
        data = query_result.get("data", {})
        raw_columns = data.get("columns", [])
        raw_rows = data.get("rows", [])

        # Extract the query execution timestamp
        retrieved_at = query_result.get("retrieved_at", "")
        query_execution_timestamp = self._normalize_timestamp(retrieved_at)

        # Step 1: Extract column metadata (Req 8, AC 2)
        columns = self._extract_column_metadata(raw_columns)

        # Identify date columns for conversion
        date_column_names = self._identify_date_columns(raw_columns)

        # Steps 2-4: Process rows (date conversion, null preservation, numeric precision)
        rows = self._process_rows(raw_rows, date_column_names)

        # Track total rows before any truncation
        total_row_count = len(rows)
        truncated = False

        # Step 5: Row-count truncation (Req 8, AC 1)
        if len(rows) > self.MAX_ROWS:
            rows = rows[: self.MAX_ROWS]
            truncated = True

        # Step 6: Size-based truncation (Req 8, AC 5)
        rows, size_truncated = self._apply_size_truncation(columns, rows, total_row_count, query_execution_timestamp)
        if size_truncated:
            truncated = True

        # Step 7: Build final result with metadata
        result = {
            "columns": columns,
            "rows": rows,
            "metadata": {
                "total_row_count": total_row_count,
                "returned_row_count": len(rows),
                "truncated": truncated,
                "query_execution_timestamp": query_execution_timestamp,
            },
        }

        return result

    def _extract_column_metadata(self, raw_columns: list[dict]) -> list[dict]:
        """
        Extract column metadata with display order from raw Redash columns.

        Args:
            raw_columns: List of column dicts from Redash API, each with
                "name", "type", and optionally "friendly_name".

        Returns:
            List of standardized column metadata dicts with name, type,
            and display_order (0-indexed based on position).
        """
        columns = []
        for index, col in enumerate(raw_columns):
            columns.append(
                {
                    "name": col.get("name", ""),
                    "type": col.get("type", ""),
                    "display_order": index,
                }
            )
        return columns

    def _identify_date_columns(self, raw_columns: list[dict]) -> set[str]:
        """
        Identify column names that have date/timestamp types.

        Args:
            raw_columns: List of column dicts from Redash API.

        Returns:
            Set of column names with date/timestamp types.
        """
        date_columns = set()
        for col in raw_columns:
            col_type = col.get("type", "").lower()
            if col_type in _DATE_COLUMN_TYPES:
                date_columns.add(col.get("name", ""))
        return date_columns

    def _process_rows(self, raw_rows: list[dict], date_column_names: set[str]) -> list[dict]:
        """
        Process rows: convert dates, preserve nulls, preserve numeric precision.

        Args:
            raw_rows: List of row dicts from Redash API.
            date_column_names: Set of column names that are date/timestamp type.

        Returns:
            List of processed row dicts.
        """
        processed_rows = []
        for row in raw_rows:
            processed_row = {}
            for key, value in row.items():
                # Null preservation (Req 8, AC 4) - keep None as-is
                if value is None:
                    processed_row[key] = None
                # Date/timestamp conversion (Req 8, AC 3)
                elif key in date_column_names:
                    processed_row[key] = self._convert_to_iso8601_utc(value)
                # Numeric precision preservation (Req 8, AC 6)
                elif isinstance(value, Decimal):
                    # Convert Decimal to string to preserve exact precision
                    processed_row[key] = str(value)
                else:
                    # Preserve as-is (integers, floats, strings, etc.)
                    processed_row[key] = value
            processed_rows.append(processed_row)
        return processed_rows

    def _convert_to_iso8601_utc(self, value: Any) -> str | None:
        """
        Convert a date/timestamp value to ISO 8601 format with UTC timezone designator.

        Handles various date string formats and returns ISO 8601 with 'Z' suffix.
        If conversion fails, returns the original value as a string.

        Args:
            value: The date/timestamp value to convert (typically a string).

        Returns:
            ISO 8601 formatted string with UTC timezone, or original string if
            parsing fails. Returns None if value is None.
        """
        if value is None:
            return None

        if not isinstance(value, str):
            value = str(value)

        if not value.strip():
            return value

        # Try common date/datetime formats
        formats = [
            "%Y-%m-%dT%H:%M:%S.%fZ",  # ISO with microseconds and Z
            "%Y-%m-%dT%H:%M:%SZ",  # ISO with Z
            "%Y-%m-%dT%H:%M:%S.%f",  # ISO with microseconds, no TZ
            "%Y-%m-%dT%H:%M:%S",  # ISO without TZ
            "%Y-%m-%d %H:%M:%S.%f",  # Space-separated with microseconds
            "%Y-%m-%d %H:%M:%S",  # Space-separated
            "%Y-%m-%d",  # Date only
        ]

        for fmt in formats:
            try:
                dt = datetime.strptime(value, fmt)
                # If no timezone info, assume UTC
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                else:
                    dt = dt.astimezone(timezone.utc)
                # Return ISO 8601 with UTC timezone designator
                return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
            except ValueError:
                continue

        # If we can't parse, return the original value
        logger.warning("Could not parse date value: %s", value)
        return value

    def _normalize_timestamp(self, timestamp: str) -> str:
        """
        Normalize a timestamp string to ISO 8601 UTC format.

        Args:
            timestamp: Timestamp string from Redash API (e.g., "2024-01-20T12:00:00.000Z").

        Returns:
            Normalized ISO 8601 string with UTC timezone designator,
            or empty string if input is empty.
        """
        if not timestamp:
            return ""

        converted = self._convert_to_iso8601_utc(timestamp)
        return converted if converted is not None else ""

    def _apply_size_truncation(
        self,
        columns: list[dict],
        rows: list[dict],
        total_row_count: int,
        query_execution_timestamp: str,
    ) -> tuple[list[dict], bool]:
        """
        Check JSON-serialized size and truncate rows if exceeding 1 MB limit.

        Uses binary search to find the maximum number of rows that fit within
        the size limit.

        Args:
            columns: Column metadata list.
            rows: Current rows (already row-count truncated).
            total_row_count: Total number of rows before any truncation.
            query_execution_timestamp: The execution timestamp for metadata.

        Returns:
            Tuple of (possibly truncated rows, whether size truncation was applied).
        """
        # Build the full result to check size
        result = {
            "columns": columns,
            "rows": rows,
            "metadata": {
                "total_row_count": total_row_count,
                "returned_row_count": len(rows),
                "truncated": True,  # Use True for size calculation (worst case)
                "query_execution_timestamp": query_execution_timestamp,
            },
        }

        serialized = json.dumps(result, cls=_DecimalEncoder)
        if len(serialized.encode("utf-8")) <= self.MAX_SIZE_BYTES:
            return rows, False

        # Binary search for the maximum number of rows that fit
        low = 0
        high = len(rows)

        while low < high:
            mid = (low + high + 1) // 2
            test_result = {
                "columns": columns,
                "rows": rows[:mid],
                "metadata": {
                    "total_row_count": total_row_count,
                    "returned_row_count": mid,
                    "truncated": True,
                    "query_execution_timestamp": query_execution_timestamp,
                },
            }
            test_serialized = json.dumps(test_result, cls=_DecimalEncoder)
            if len(test_serialized.encode("utf-8")) <= self.MAX_SIZE_BYTES:
                low = mid
            else:
                high = mid - 1

        truncated_rows = rows[:low]
        logger.info(
            "Size-based truncation applied: %d rows -> %d rows to fit within %d bytes",
            len(rows),
            len(truncated_rows),
            self.MAX_SIZE_BYTES,
        )
        return truncated_rows, True
