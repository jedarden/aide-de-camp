#!/usr/bin/env python3
"""
Unit tests for validate_completeness function.

Tests cover:
- Valid 30-day consecutive data
- Edge cases (29 days, 31 days)
- Date gaps
- Duplicate dates
- Invalid data types
- Missing/invalid timestamps
"""

import pytest
from datetime import datetime, timedelta
from src.validation.validate_completeness import validate_completeness, validate_completeness_with_details


class TestValidateCompleteness:
    """Test suite for validate_completeness function."""

    def test_valid_30_day_consecutive_data(self):
        """Test valid 30-day consecutive deployment data."""
        # Generate 30 consecutive days
        base_date = datetime(2026, 7, 7, 12, 0, 0)
        data = [
            {"timestamp": (base_date + timedelta(days=i)).isoformat() + "Z"}
            for i in range(30)
        ]

        is_valid, error = validate_completeness(data)
        assert is_valid is True
        assert error == ""

    def test_29_days_too_few(self):
        """Test 29 days of data (should fail)."""
        base_date = datetime(2026, 7, 7, 12, 0, 0)
        data = [
            {"timestamp": (base_date + timedelta(days=i)).isoformat() + "Z"}
            for i in range(29)  # Only 29 days
        ]

        is_valid, error = validate_completeness(data)
        assert is_valid is False
        assert "Expected 30 deployment entries, found 29" in error

    def test_31_days_too_many(self):
        """Test 31 days of data (should fail)."""
        base_date = datetime(2026, 7, 7, 12, 0, 0)
        data = [
            {"timestamp": (base_date + timedelta(days=i)).isoformat() + "Z"}
            for i in range(31)  # 31 days
        ]

        is_valid, error = validate_completeness(data)
        assert is_valid is False
        assert "Expected 30 deployment entries, found 31" in error

    def test_date_gap_in_middle(self):
        """Test data with a gap in the middle."""
        base_date = datetime(2026, 7, 7, 12, 0, 0)

        # Create data with a 2-day gap between day 10 and day 13
        data = []
        for i in range(11):  # Days 0-10
            data.append({"timestamp": (base_date + timedelta(days=i)).isoformat() + "Z"})
        for i in range(13, 32):  # Days 13-31 (skipping 11-12)
            data.append({"timestamp": (base_date + timedelta(days=i)).isoformat() + "Z"})

        is_valid, error = validate_completeness(data)
        assert is_valid is False
        assert "Date gap detected" in error

    def test_duplicate_date(self):
        """Test data with duplicate dates."""
        base_date = datetime(2026, 7, 7, 12, 0, 0)

        # Create 29 entries, then duplicate day 0 for the 30th entry
        data = [
            {"timestamp": (base_date + timedelta(days=i)).isoformat() + "Z"}
            for i in range(29)
        ]
        data.append({"timestamp": base_date.isoformat() + "Z"})  # Duplicate day 0

        is_valid, error = validate_completeness(data)
        assert is_valid is False
        assert "Duplicate date found" in error

    def test_data_not_list(self):
        """Test when data is not a list."""
        data = {"not": "a list"}

        is_valid, error = validate_completeness(data)
        assert is_valid is False
        assert "Data must be a list" in error

    def test_entry_not_dictionary(self):
        """Test when an entry is not a dictionary."""
        base_date = datetime(2026, 7, 7, 12, 0, 0)
        data = [
            {"timestamp": (base_date + timedelta(days=i)).isoformat() + "Z"}
            for i in range(29)
        ]
        data.append(["not", "a", "dict"])  # Invalid entry

        is_valid, error = validate_completeness(data)
        assert is_valid is False
        assert "Entry 29 is not a dictionary" in error

    def test_missing_timestamp_field(self):
        """Test entry without timestamp field."""
        base_date = datetime(2026, 7, 7, 12, 0, 0)
        data = [
            {"timestamp": (base_date + timedelta(days=i)).isoformat() + "Z"}
            for i in range(29)
        ]
        data.append({"revision": "123"})  # Missing timestamp

        is_valid, error = validate_completeness(data)
        assert is_valid is False
        assert "Entry 29 missing timestamp field" in error

    def test_empty_timestamp(self):
        """Test entry with empty timestamp."""
        base_date = datetime(2026, 7, 7, 12, 0, 0)
        data = [
            {"timestamp": (base_date + timedelta(days=i)).isoformat() + "Z"}
            for i in range(29)
        ]
        data.append({"timestamp": ""})  # Empty timestamp

        is_valid, error = validate_completeness(data)
        assert is_valid is False
        assert "Entry 29 has empty timestamp" in error

    def test_invalid_timestamp_format(self):
        """Test entry with invalid timestamp format."""
        base_date = datetime(2026, 7, 7, 12, 0, 0)
        data = [
            {"timestamp": (base_date + timedelta(days=i)).isoformat() + "Z"}
            for i in range(29)
        ]
        data.append({"timestamp": "not-a-valid-timestamp"})

        is_valid, error = validate_completeness(data)
        assert is_valid is False
        assert "Entry 29 has invalid timestamp" in error

    def test_timestamp_not_string(self):
        """Test entry with non-string timestamp."""
        base_date = datetime(2026, 7, 7, 12, 0, 0)
        data = [
            {"timestamp": (base_date + timedelta(days=i)).isoformat() + "Z"}
            for i in range(29)
        ]
        data.append({"timestamp": 12345})  # Numeric timestamp

        is_valid, error = validate_completeness(data)
        assert is_valid is False
        assert "Entry 29 timestamp must be a string" in error

    def test_supports_creationTimestamp_field(self):
        """Test that creationTimestamp field is also supported."""
        base_date = datetime(2026, 7, 7, 12, 0, 0)
        data = [
            {"creationTimestamp": (base_date + timedelta(days=i)).isoformat() + "Z"}
            for i in range(30)
        ]

        is_valid, error = validate_completeness(data)
        assert is_valid is True
        assert error == ""

    def test_unordered_entries_still_valid(self):
        """Test that entries can be in any order and still be valid."""
        base_date = datetime(2026, 7, 7, 12, 0, 0)

        # Create 30 entries but in reverse order
        data = [
            {"timestamp": (base_date + timedelta(days=i)).isoformat() + "Z"}
            for i in range(30)
        ]
        data.reverse()  # Put in reverse order

        is_valid, error = validate_completeness(data)
        assert is_valid is True
        assert error == ""

    def test_timestamp_with_timezone(self):
        """Test timestamps with timezone offsets."""
        base_date = datetime(2026, 7, 7, 12, 0, 0)
        data = [
            {"timestamp": (base_date + timedelta(days=i)).isoformat()}
            for i in range(30)
        ]

        is_valid, error = validate_completeness(data)
        assert is_valid is True
        assert error == ""


class TestValidateCompletenessWithDetails:
    """Test suite for validate_completeness_with_details function."""

    def test_valid_data_with_details(self):
        """Test valid data returns detailed results."""
        base_date = datetime(2026, 7, 7, 12, 0, 0)
        data = [
            {"timestamp": (base_date + timedelta(days=i)).isoformat() + "Z"}
            for i in range(30)
        ]

        result = validate_completeness_with_details(data)
        assert result["is_valid"] is True
        assert result["error_message"] == ""
        assert result["entry_count"] == 30
        assert result["coverage_days"] == 30
        assert result["date_range"] is not None

    def test_invalid_data_with_details(self):
        """Test invalid data returns error details."""
        base_date = datetime(2026, 7, 7, 12, 0, 0)
        data = [
            {"timestamp": (base_date + timedelta(days=i)).isoformat() + "Z"}
            for i in range(29)  # Only 29 days
        ]

        result = validate_completeness_with_details(data)
        assert result["is_valid"] is False
        assert "Expected 30" in result["error_message"]
        assert result["entry_count"] == 29

    def test_date_range_calculation(self):
        """Test that date range is correctly calculated."""
        start_date = datetime(2026, 7, 7, 12, 0, 0)
        end_date = datetime(2026, 8, 5, 12, 0, 0)  # 30 days later

        data = [
            {"timestamp": (start_date + timedelta(days=i)).isoformat() + "Z"}
            for i in range(30)
        ]

        result = validate_completeness_with_details(data)
        assert result["date_range"][0] == "2026-07-07"
        assert result["date_range"][1] == "2026-08-05"
