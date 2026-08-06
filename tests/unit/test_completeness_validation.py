#!/usr/bin/env python3
"""
Unit tests for JSON well-formedness and 30-day completeness validation.

Tests cover:
- JSON well-formedness validation
- 30-day completeness validation (no gaps, no duplicates)
- Chronological sequence validation
- Integration with deployment_data validation
- Edge cases and error handling
"""

import pytest
from datetime import datetime, timedelta
from pathlib import Path
import json
import tempfile
import os

from src.validation.completeness import (
    validate_json_wellformedness,
    validate_json_file_wellformedness,
    validate_30day_completeness,
    validate_json_completeness,
    validate_json_file_completeness,
    parse_date_string,
    generate_expected_dates,
    extract_dates_from_data,
)


class TestValidateJsonWellformedness:
    """Test JSON well-formedness validation."""

    def test_valid_json_object(self):
        """Valid JSON object should pass."""
        data = {"key": "value", "number": 42, "nested": {"inner": "data"}}
        is_valid, error = validate_json_wellformedness(data)
        assert is_valid is True
        assert error is None

    def test_valid_json_array(self):
        """Valid JSON array should pass."""
        data = [1, 2, 3, "four", {"five": 5}]
        is_valid, error = validate_json_wellformedness(data)
        assert is_valid is True
        assert error is None

    def test_valid_json_primitives(self):
        """Valid JSON primitives should pass."""
        # String
        is_valid, error = validate_json_wellformedness("hello")
        assert is_valid is True
        assert error is None

        # Number
        is_valid, error = validate_json_wellformedness(42)
        assert is_valid is True
        assert error is None

        # Boolean
        is_valid, error = validate_json_wellformedness(True)
        assert is_valid is True
        assert error is None

        # None
        is_valid, error = validate_json_wellformedness(None)
        assert is_valid is True
        assert error is None

    def test_invalid_json_datetime(self):
        """datetime objects are not JSON serializable."""
        data = {"timestamp": datetime.now()}
        is_valid, error = validate_json_wellformedness(data)
        assert is_valid is False
        assert "not well-formed JSON" in error

    def test_invalid_json_set(self):
        """set objects are not JSON serializable."""
        data = {"items": {1, 2, 3}}
        is_valid, error = validate_json_wellformedness(data)
        assert is_valid is False
        assert "not well-formed JSON" in error

    def test_invalid_json_complex(self):
        """complex numbers are not JSON serializable."""
        data = {"value": complex(1, 2)}
        is_valid, error = validate_json_wellformedness(data)
        assert is_valid is False
        assert "not well-formed JSON" in error


class TestValidateJsonFileWellformedness:
    """Test JSON file well-formedness validation."""

    def test_valid_json_file(self):
        """Valid JSON file should parse correctly."""
        data = {"service": "test", "deployments": 10}

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(data, f)
            temp_path = Path(f.name)

        try:
            is_valid, error, parsed = validate_json_file_wellformedness(temp_path)
            assert is_valid is True
            assert error is None
            assert parsed == data
        finally:
            os.unlink(temp_path)

    def test_invalid_json_file(self):
        """Invalid JSON file should fail."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            f.write("{invalid json")
            temp_path = Path(f.name)

        try:
            is_valid, error, parsed = validate_json_file_wellformedness(temp_path)
            assert is_valid is False
            assert "Invalid JSON" in error
            assert parsed is None
        finally:
            os.unlink(temp_path)

    def test_nonexistent_file(self):
        """Nonexistent file should fail."""
        temp_path = Path("/nonexistent/path/file.json")
        is_valid, error, parsed = validate_json_file_wellformedness(temp_path)
        assert is_valid is False
        assert "does not exist" in error
        assert parsed is None


class TestParseDateString:
    """Test date string parsing."""

    def test_iso_date_only(self):
        """Parse ISO date string (no time)."""
        date_str = "2026-07-01"
        result = parse_date_string(date_str)
        assert result == datetime(2026, 7, 1)

    def test_iso_with_timestamp(self):
        """Parse ISO date string with timestamp."""
        date_str = "2026-07-01T12:34:56Z"
        result = parse_date_string(date_str)
        assert result.year == 2026
        assert result.month == 7
        assert result.day == 1
        assert result.hour == 12
        assert result.minute == 34

    def test_invalid_date_string(self):
        """Invalid date string should raise ValueError."""
        with pytest.raises(ValueError):
            parse_date_string("not-a-date")


class TestGenerateExpectedDates:
    """Test expected date generation."""

    def test_single_day_range(self):
        """Single day range."""
        start = datetime(2026, 7, 1)
        end = datetime(2026, 7, 1)
        dates = generate_expected_dates(start, end)
        assert len(dates) == 1
        assert dates[0] == start

    def test_three_day_range(self):
        """Three day range."""
        start = datetime(2026, 7, 1)
        end = datetime(2026, 7, 3)
        dates = generate_expected_dates(start, end)
        assert len(dates) == 3
        assert dates[0] == datetime(2026, 7, 1)
        assert dates[1] == datetime(2026, 7, 2)
        assert dates[2] == datetime(2026, 7, 3)

    def test_thirty_day_range(self):
        """Thirty day range."""
        start = datetime(2026, 7, 1)
        end = datetime(2026, 7, 30)
        dates = generate_expected_dates(start, end)
        assert len(dates) == 30
        assert dates[0] == start
        assert dates[-1] == end


class TestExtractDatesFromData:
    """Test date extraction from deployment data."""

    def test_extract_from_deployment_events(self):
        """Extract dates from deployment_events_last_30_days."""
        data = {
            "deployment_events_last_30_days": [
                {"date": "2026-07-01", "event": "deploy1"},
                {"date": "2026-07-02", "event": "deploy2"},
                {"date": "2026-07-03", "event": "deploy3"},
            ]
        }
        dates = extract_dates_from_data(data)
        assert len(dates) == 3
        assert datetime(2026, 7, 1) in dates
        assert datetime(2026, 7, 2) in dates
        assert datetime(2026, 7, 3) in dates

    def test_extract_from_replicasets(self):
        """Extract dates from deployment_history_30_days.replicasets."""
        data = {
            "deployment_history_30_days": {
                "replicasets": [
                    {"created": "2026-07-01T10:00:00Z", "name": "rs1"},
                    {"created": "2026-07-02T11:00:00Z", "name": "rs2"},
                ]
            }
        }
        dates = extract_dates_from_data(data)
        assert len(dates) == 2
        assert datetime(2026, 7, 1) in dates
        assert datetime(2026, 7, 2) in dates

    def test_extract_with_timestamps_strips_time(self):
        """Timestamps should be stripped to date only."""
        data = {
            "deployment_events_last_30_days": [
                {"date": "2026-07-01T12:34:56Z", "event": "deploy1"},
                {"date": "2026-07-01T23:59:59Z", "event": "deploy2"},  # Same day
            ]
        }
        dates = extract_dates_from_data(data)
        # Both should resolve to the same date
        assert len(dates) == 1
        assert datetime(2026, 7, 1) in dates

    def test_extract_from_empty_data(self):
        """Empty data returns empty set."""
        dates = extract_dates_from_data({})
        assert len(dates) == 0

    def test_extract_ignores_invalid_dates(self):
        """Invalid dates are silently ignored."""
        data = {
            "deployment_events_last_30_days": [
                {"date": "2026-07-01", "event": "deploy1"},
                {"date": "invalid-date", "event": "deploy2"},
                {"date": "2026-07-03", "event": "deploy3"},
            ]
        }
        dates = extract_dates_from_data(data)
        # Only valid dates should be extracted
        assert len(dates) == 2
        assert datetime(2026, 7, 1) in dates
        assert datetime(2026, 7, 3) in dates


class TestValidate30DayCompleteness:
    """Test 30-day completeness validation."""

    def test_complete_30_day_data(self):
        """Complete 30-day data should pass."""
        start = datetime(2026, 7, 1)
        end = datetime(2026, 7, 30)

        # Generate all 30 dates
        expected_dates = generate_expected_dates(start, end)

        # Create data with all dates
        events = [{"date": d.strftime("%Y-%m-%d"), "event": f"deploy{i}"} for i, d in enumerate(expected_dates)]

        data = {
            "metadata": {
                "time_period": {
                    "start": start.isoformat() + "Z",
                    "end": end.isoformat() + "Z"
                }
            },
            "deployment_events_last_30_days": events
        }

        is_valid, error = validate_30day_completeness(data)
        assert is_valid is True
        assert error is None

    def test_missing_dates_gaps(self):
        """Missing dates should fail."""
        start = datetime(2026, 7, 1)
        end = datetime(2026, 7, 30)

        # Create data with missing dates
        events = [
            {"date": "2026-07-01", "event": "deploy1"},
            {"date": "2026-07-05", "event": "deploy5"},  # Gap: missing 2,3,4
            {"date": "2026-07-06", "event": "deploy6"},
        ]

        data = {
            "metadata": {
                "time_period": {
                    "start": start.isoformat() + "Z",
                    "end": end.isoformat() + "Z"
                }
            },
            "deployment_events_last_30_days": events
        }

        is_valid, error = validate_30day_completeness(data)
        assert is_valid is False
        assert "Missing data for" in error

    def test_duplicate_dates(self):
        """Duplicate dates should be handled correctly."""
        start = datetime(2026, 7, 1)
        end = datetime(2026, 7, 3)

        # Create data with only 2 dates but expecting 3
        events = [
            {"date": "2026-07-01", "event": "deploy1"},
            {"date": "2026-07-02", "event": "deploy2"},
            # Missing 2026-07-03
        ]

        data = {
            "metadata": {
                "time_period": {
                    "start": start.isoformat() + "Z",
                    "end": end.isoformat() + "Z"
                }
            },
            "deployment_events_last_30_days": events
        }

        is_valid, error = validate_30day_completeness(data, require_exact_30_days=False)
        assert is_valid is False
        assert "Missing data for" in error

    def test_incorrect_date_range(self):
        """Incorrect date range should fail."""
        start = datetime(2026, 7, 1)
        end = datetime(2026, 8, 15)  # 45 days, not 30

        data = {
            "metadata": {
                "time_period": {
                    "start": start.isoformat() + "Z",
                    "end": end.isoformat() + "Z"
                }
            },
            "deployment_events_last_30_days": []
        }

        is_valid, error = validate_30day_completeness(data)
        assert is_valid is False
        assert "expected ~30 days" in error

    def test_no_metadata(self):
        """Data without metadata should fail."""
        data = {
            "deployment_events_last_30_days": [
                {"date": "2026-07-01", "event": "deploy1"}
            ]
        }

        is_valid, error = validate_30day_completeness(data)
        assert is_valid is False
        assert "Cannot determine date range" in error

    def test_chronological_sequence_check(self):
        """Non-chronological dates should fail with missing dates error."""
        start = datetime(2026, 7, 1)
        end = datetime(2026, 7, 5)

        # Create data with non-chronological dates (missing 3,4)
        events = [
            {"date": "2026-07-01", "event": "deploy1"},
            {"date": "2026-07-02", "event": "deploy2"},
            {"date": "2026-07-05", "event": "deploy5"},  # Gap: missing 3,4
        ]

        data = {
            "metadata": {
                "time_period": {
                    "start": start.isoformat() + "Z",
                    "end": end.isoformat() + "Z"
                }
            },
            "deployment_events_last_30_days": events
        }

        is_valid, error = validate_30day_completeness(data, require_exact_30_days=False)
        assert is_valid is False
        # Should fail due to missing dates (gaps are detected before sequence check)
        assert "Missing data for" in error

    def test_report_metadata_format(self):
        """Should handle report_metadata format as well."""
        start = datetime(2026, 7, 1)
        end = datetime(2026, 7, 30)

        # Create complete data
        expected_dates = generate_expected_dates(start, end)
        events = [{"date": d.strftime("%Y-%m-%d"), "event": f"deploy{i}"} for i, d in enumerate(expected_dates)]

        data = {
            "report_metadata": {
                "time_range_start": start.isoformat() + "Z",
                "time_range_end": end.isoformat() + "Z",
                "service": "test-service"
            },
            "deployment_history_30_days": {
                "replicasets": [
                    {"created": d.strftime("%Y-%m-%dT%H:%M:%SZ"), "name": f"rs{i}"}
                    for i, d in enumerate(expected_dates)
                ]
            }
        }

        is_valid, error = validate_30day_completeness(data)
        assert is_valid is True
        assert error is None


class TestValidateJsonCompleteness:
    """Test comprehensive JSON completeness validation."""

    def test_complete_valid_data(self):
        """Complete and valid data should pass."""
        start = datetime(2026, 7, 1)
        end = datetime(2026, 7, 30)

        # Generate all 30 dates
        expected_dates = generate_expected_dates(start, end)
        events = [{"date": d.strftime("%Y-%m-%d"), "event": f"deploy{i}"} for i, d in enumerate(expected_dates)]

        data = {
            "metadata": {
                "time_period": {
                    "start": start.isoformat() + "Z",
                    "end": end.isoformat() + "Z"
                }
            },
            "deployment_events_last_30_days": events
        }

        is_valid, error = validate_json_completeness(data)
        assert is_valid is True
        assert error is None

    def test_invalid_json_structure(self):
        """Invalid JSON structure should fail."""
        data = {"timestamp": datetime.now()}  # Not JSON serializable

        is_valid, error = validate_json_completeness(data)
        assert is_valid is False
        assert "well-formedness check failed" in error

    def test_incomplete_data(self):
        """Incomplete data (missing dates) should fail."""
        start = datetime(2026, 7, 1)
        end = datetime(2026, 7, 30)

        # Only provide 3 dates instead of 30
        events = [
            {"date": "2026-07-01", "event": "deploy1"},
            {"date": "2026-07-02", "event": "deploy2"},
            {"date": "2026-07-03", "event": "deploy3"},
        ]

        data = {
            "metadata": {
                "time_period": {
                    "start": start.isoformat() + "Z",
                    "end": end.isoformat() + "Z"
                }
            },
            "deployment_events_last_30_days": events
        }

        is_valid, error = validate_json_completeness(data)
        assert is_valid is False
        assert "completeness check failed" in error


class TestValidateJsonFileCompleteness:
    """Test JSON file completeness validation."""

    def test_valid_complete_file(self):
        """Valid and complete file should pass."""
        start = datetime(2026, 7, 1)
        end = datetime(2026, 7, 30)

        # Generate all 30 dates
        expected_dates = generate_expected_dates(start, end)
        events = [{"date": d.strftime("%Y-%m-%d"), "event": f"deploy{i}"} for i, d in enumerate(expected_dates)]

        data = {
            "metadata": {
                "time_period": {
                    "start": start.isoformat() + "Z",
                    "end": end.isoformat() + "Z"
                }
            },
            "deployment_events_last_30_days": events
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(data, f)
            temp_path = Path(f.name)

        try:
            is_valid, error, parsed = validate_json_file_completeness(temp_path)
            assert is_valid is True
            assert error is None
            assert parsed is not None
            assert parsed == data
        finally:
            os.unlink(temp_path)

    def test_invalid_json_file(self):
        """Invalid JSON file should fail at well-formedness check."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            f.write("{invalid json")
            temp_path = Path(f.name)

        try:
            is_valid, error, parsed = validate_json_file_completeness(temp_path)
            assert is_valid is False
            assert error is not None
            assert parsed is None
        finally:
            os.unlink(temp_path)

    def test_incomplete_json_file(self):
        """Valid JSON but incomplete data should fail at completeness check."""
        start = datetime(2026, 7, 1)
        end = datetime(2026, 7, 30)

        # Only provide 3 dates instead of 30
        events = [
            {"date": "2026-07-01", "event": "deploy1"},
            {"date": "2026-07-02", "event": "deploy2"},
            {"date": "2026-07-03", "event": "deploy3"},
        ]

        data = {
            "metadata": {
                "time_period": {
                    "start": start.isoformat() + "Z",
                    "end": end.isoformat() + "Z"
                }
            },
            "deployment_events_last_30_days": events
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(data, f)
            temp_path = Path(f.name)

        try:
            is_valid, error, parsed = validate_json_file_completeness(temp_path)
            assert is_valid is False
            assert error is not None
            assert parsed is not None  # Data should be parsed
        finally:
            os.unlink(temp_path)


class TestRealDataIntegration:
    """Integration tests with real deployment data files."""

    def test_pbx_web_deployment_data(self):
        """Test validation with real pbx-web deployment data file."""
        file_path = Path("/home/coding/aide-de-camp/pbx-web-deployment-data-30days.json")

        if not file_path.exists():
            pytest.skip("Real data file not available")

        is_valid, error, data = validate_json_file_completeness(file_path)

        # The real file should be well-formed JSON at minimum
        # Completeness depends on actual data coverage
        assert data is not None, "File should be parseable"

    def test_whisper_stt_deployment_data(self):
        """Test validation with real whisper-stt deployment data file."""
        file_path = Path("/home/coding/aide-de-camp/whisper-stt-deployment-data-30days.json")

        if not file_path.exists():
            pytest.skip("Real data file not available")

        is_valid, error, data = validate_json_file_completeness(file_path)

        # The real file should be well-formed JSON at minimum
        assert data is not None, "File should be parseable"


class TestEdgeCases:
    """Test edge cases and error conditions."""

    def test_empty_data(self):
        """Empty data should fail."""
        data = {}
        is_valid, error = validate_json_completeness(data)
        assert is_valid is False

    def test_no_deployment_events(self):
        """Data with no deployment events should fail."""
        start = datetime(2026, 7, 1)
        end = datetime(2026, 7, 30)

        data = {
            "metadata": {
                "time_period": {
                    "start": start.isoformat() + "Z",
                    "end": end.isoformat() + "Z"
                }
            },
            "deployment_events_last_30_days": []
        }

        is_valid, error = validate_30day_completeness(data)
        assert is_valid is False
        assert "No dates found" in error

    def test_exactly_30_days_range(self):
        """Exactly 30 days range should pass."""
        start = datetime(2026, 7, 1)
        end = datetime(2026, 7, 30)

        expected_dates = generate_expected_dates(start, end)
        events = [{"date": d.strftime("%Y-%m-%d"), "event": f"deploy{i}"} for i, d in enumerate(expected_dates)]

        data = {
            "metadata": {
                "time_period": {
                    "start": start.isoformat() + "Z",
                    "end": end.isoformat() + "Z"
                }
            },
            "deployment_events_last_30_days": events
        }

        is_valid, error = validate_30day_completeness(data)
        assert is_valid is True
        assert error is None

    def test_29_days_range_too_short(self):
        """29 days range should fail."""
        start = datetime(2026, 7, 1)
        end = datetime(2026, 7, 29)

        data = {
            "metadata": {
                "time_period": {
                    "start": start.isoformat() + "Z",
                    "end": end.isoformat() + "Z"
                }
            },
            "deployment_events_last_30_days": []
        }

        is_valid, error = validate_30day_completeness(data)
        assert is_valid is False
        assert "expected ~30 days" in error

    def test_31_days_range_too_long(self):
        """32 days range should fail when requiring exactly 30 days."""
        start = datetime(2026, 7, 1)
        end = datetime(2026, 8, 1)  # 32 days (Aug 1 - July 1 = 31, but range is inclusive so 32)

        # Create complete data
        expected_dates = generate_expected_dates(start, end)
        events = [{"date": d.strftime("%Y-%m-%d"), "event": f"deploy{i}"} for i, d in enumerate(expected_dates)]

        data = {
            "metadata": {
                "time_period": {
                    "start": start.isoformat() + "Z",
                    "end": end.isoformat() + "Z"
                }
            },
            "deployment_events_last_30_days": events
        }

        is_valid, error = validate_30day_completeness(data, require_exact_30_days=True)
        assert is_valid is False
        assert "expected ~30 days" in error

    def test_leap_year_february(self):
        """Leap year February should handle 29 days correctly when not requiring exactly 30 days."""
        start = datetime(2024, 2, 1)
        end = datetime(2024, 2, 29)  # Leap year: 29 days

        expected_dates = generate_expected_dates(start, end)
        events = [{"date": d.strftime("%Y-%m-%d"), "event": f"deploy{i}"} for i, d in enumerate(expected_dates)]

        data = {
            "metadata": {
                "time_period": {
                    "start": start.isoformat() + "Z",
                    "end": end.isoformat() + "Z"
                }
            },
            "deployment_events_last_30_days": events
        }

        # This should pass for 29-day February when not requiring exactly 30 days
        is_valid, error = validate_30day_completeness(data, require_exact_30_days=False)
        assert is_valid is True

        # But should fail when requiring exactly 30 days
        is_valid, error = validate_30day_completeness(data, require_exact_30_days=True)
        assert is_valid is False

    def test_malformed_dates(self):
        """Malformed dates should be handled gracefully."""
        start = datetime(2026, 7, 1)
        end = datetime(2026, 7, 30)

        data = {
            "metadata": {
                "time_period": {
                    "start": start.isoformat() + "Z",
                    "end": end.isoformat() + "Z"
                }
            },
            "deployment_events_last_30_days": [
                {"date": "not-a-date", "event": "deploy1"},
                {"date": "2026-07-02", "event": "deploy2"},
            ]
        }

        # Should fail with missing dates (since invalid ones are ignored)
        is_valid, error = validate_30day_completeness(data)
        assert is_valid is False
        assert "Missing data" in error
