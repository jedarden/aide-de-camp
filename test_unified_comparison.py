"""
Comprehensive unit tests for unified classification comparison.

Tests cover all edge cases:
- None/empty inputs
- Missing keys in classifications
- Null values for any field
- Type mismatches between fields
- Nested None values in structured results
- Empty vs missing keys
- Enum values in intent_type
- Numeric tolerance for confidence
- Order-insensitive list comparison
"""


import pytest

from src.intent.unified_comparison import (
    _extract_classification_from_routed_intent,
    compare_classifications,
    compare_confidence_scores,
    compare_dicts,
    compare_intent_types,
    compare_lists,
    compare_structured_field,
    normalize_input_to_classifications,
    safe_get,
)


class TestNormalizeInput:
    """Test input normalization with various formats."""

    def test_normalize_none_input(self):
        """Test that None input returns empty list."""
        result = normalize_input_to_classifications(None)
        assert result == []

    def test_normalize_empty_dict(self):
        """Test that empty dict returns empty list."""
        result = normalize_input_to_classifications({})
        assert result == []

    def test_normalize_empty_list(self):
        """Test that empty list returns empty list."""
        result = normalize_input_to_classifications([])
        assert result == []

    def test_normalize_list_of_classifications(self):
        """Test normalizing a list of classification dicts."""
        input_data = [
            {"intent_type": "status", "confidence": 0.9},
            {"intent_type": "lookup", "confidence": 0.8},
        ]
        result = normalize_input_to_classifications(input_data)
        assert len(result) == 2
        assert result[0]["intent_type"] == "status"
        assert result[1]["intent_type"] == "lookup"

    def test_normalize_dict_with_classifications_key(self):
        """Test normalizing dict with 'classifications' key."""
        input_data = {
            "classifications": [
                {"intent_type": "status", "confidence": 0.9},
            ]
        }
        result = normalize_input_to_classifications(input_data)
        assert len(result) == 1
        assert result[0]["intent_type"] == "status"

    def test_normalize_routed_intent_structure(self):
        """Test normalizing RoutedIntent structure with nested classification."""
        input_data = {
            "classifications": [
                {
                    "classification": {
                        "intent_type": "status",
                        "confidence": 0.9,
                        "project_slug": "test-project",
                    }
                }
            ]
        }
        result = normalize_input_to_classifications(input_data)
        assert len(result) == 1
        assert result[0]["intent_type"] == "status"
        assert result[0]["confidence"] == 0.9
        assert result[0]["project_slug"] == "test-project"

    def test_normalize_mixed_structure(self):
        """Test normalizing mix of flat and nested classifications."""
        input_data = {
            "classifications": [
                {"intent_type": "status", "confidence": 0.9},
                {
                    "classification": {
                        "intent_type": "lookup",
                        "confidence": 0.8,
                    }
                },
            ]
        }
        result = normalize_input_to_classifications(input_data)
        assert len(result) == 2
        assert result[0]["intent_type"] == "status"
        assert result[1]["intent_type"] == "lookup"

    def test_normalize_unrecognized_format(self):
        """Test that unrecognized formats return empty list."""
        result = normalize_input_to_classifications({"random_key": "value"})
        assert result == []

    def test_normalize_single_classification_dict(self):
        """Test normalizing a single classification dict (not in list)."""
        input_data = {"intent_type": "status", "confidence": 0.9}
        result = normalize_input_to_classifications(input_data)
        assert len(result) == 1
        assert result[0]["intent_type"] == "status"


class TestExtractClassification:
    """Test extraction from RoutedIntent structures."""

    def test_extract_flat_classification(self):
        """Test extracting a flat classification (no nested structure)."""
        input_data = {"intent_type": "status", "confidence": 0.9}
        result = _extract_classification_from_routed_intent(input_data)
        assert result["intent_type"] == "status"
        assert result["confidence"] == 0.9

    def test_extract_nested_classification(self):
        """Test extracting nested classification from RoutedIntent."""
        input_data = {
            "classification": {
                "intent_type": "status",
                "confidence": 0.9,
                "project_slug": "test-project",
            }
        }
        result = _extract_classification_from_routed_intent(input_data)
        assert result["intent_type"] == "status"
        assert result["confidence"] == 0.9
        assert result["project_slug"] == "test-project"

    def test_extract_none_classification(self):
        """Test extracting when classification is None."""
        input_data = {"classification": None}
        result = _extract_classification_from_routed_intent(input_data)
        assert result["intent_type"] is None
        assert result["confidence"] is None
        assert result["project_slug"] is None

    def test_extract_enum_intent_type(self):
        """Test extracting enum intent_type."""
        from enum import Enum

        class TestIntent(Enum):
            STATUS = "status"

        input_data = {
            "classification": {
                "intent_type": TestIntent.STATUS,
                "confidence": 0.9,
            }
        }
        result = _extract_classification_from_routed_intent(input_data)
        assert result["intent_type"] == "status"

    def test_extract_dict_intent_type(self):
        """Test extracting dict intent_type with 'value' key."""
        input_data = {
            "classification": {
                "intent_type": {"value": "status"},
                "confidence": 0.9,
            }
        }
        result = _extract_classification_from_routed_intent(input_data)
        assert result["intent_type"] == "status"


class TestSafeGet:
    """Test safe_get function with edge cases."""

    def test_safe_get_none_data(self):
        """Test safe_get with None data."""
        result = safe_get(None, "field")
        assert result is None

    def test_safe_get_missing_field(self):
        """Test safe_get with missing field."""
        result = safe_get({"other": "value"}, "field")
        assert result is None

    def test_safe_get_none_field_value(self):
        """Test safe_get when field value is None."""
        result = safe_get({"field": None}, "field", default="default")
        assert result == "default"

    def test_safe_get_custom_default(self):
        """Test safe_get with custom default value."""
        result = safe_get(None, "field", default="custom_default")
        assert result == "custom_default"

    def test_safe_get_valid_field(self):
        """Test safe_get with valid field."""
        result = safe_get({"field": "value"}, "field")
        assert result == "value"

    def test_safe_get_non_dict_data(self):
        """Test safe_get with non-dict data."""
        result = safe_get("not_a_dict", "field")
        assert result is None


class TestCompareIntentTypes:
    """Test intent type comparison with edge cases."""

    def test_compare_matching_strings(self):
        """Test comparing matching string intent types."""
        result = compare_intent_types("status", "status")
        assert result is True

    def test_compare_mismatching_strings(self):
        """Test comparing mismatching string intent types."""
        result = compare_intent_types("status", "lookup")
        assert result is False

    def test_compare_none_values(self):
        """Test that None values never match."""
        assert compare_intent_types(None, "status") is False
        assert compare_intent_types("status", None) is False
        assert compare_intent_types(None, None) is False

    def test_compare_empty_strings(self):
        """Test that empty strings don't match."""
        assert compare_intent_types("", "status") is False
        assert compare_intent_types("status", "") is False
        assert compare_intent_types("", "") is False

    def test_compare_enum_values(self):
        """Test comparing enum intent types."""
        from enum import Enum

        class Intent(Enum):
            STATUS = "status"

        result = compare_intent_types(Intent.STATUS, "status")
        assert result is True

    def test_compare_dict_values(self):
        """Test comparing dict intent types with 'value' key."""
        result = compare_intent_types({"value": "status"}, "status")
        assert result is True

    def test_compare_type_mismatch(self):
        """Test that type mismatches return False."""
        assert compare_intent_types(123, "status") is False
        assert compare_intent_types("status", 123) is False

    def test_compare_case_sensitive(self):
        """Test that comparison is case-sensitive."""
        assert compare_intent_types("Status", "status") is False
        assert compare_intent_types("STATUS", "status") is False


class TestCompareConfidenceScores:
    """Test confidence score comparison with edge cases."""

    def test_compare_exact_match(self):
        """Test comparing exact confidence scores."""
        result = compare_confidence_scores(0.9, 0.9)
        assert result is True

    def test_compare_within_tolerance(self):
        """Test comparing scores within tolerance."""
        result = compare_confidence_scores(0.9, 0.91, tolerance=0.02)
        assert result is True

    def test_compare_outside_tolerance(self):
        """Test comparing scores outside tolerance."""
        result = compare_confidence_scores(0.9, 0.85)
        assert result is False

    def test_compare_none_values(self):
        """Test that None values never match."""
        assert compare_confidence_scores(None, 0.9) is False
        assert compare_confidence_scores(0.9, None) is False
        assert compare_confidence_scores(None, None) is False

    def test_compare_string_representation(self):
        """Test comparing string representations of numbers."""
        result = compare_confidence_scores("0.9", "0.9")
        assert result is True

    def test_compare_invalid_string(self):
        """Test that invalid strings return False."""
        assert compare_confidence_scores("not_a_number", 0.9) is False
        assert compare_confidence_scores(0.9, "not_a_number") is False

    def test_compare_int_vs_float(self):
        """Test comparing int vs float confidence."""
        result = compare_confidence_scores(1, 1.0)
        assert result is True

    def test_compare_nan_values(self):
        """Test that NaN values never match."""
        assert compare_confidence_scores(float('nan'), 0.9) is False
        assert compare_confidence_scores(0.9, float('nan')) is False
        assert compare_confidence_scores(float('nan'), float('nan')) is False

    def test_compare_infinity(self):
        """Test comparing infinity values."""
        result = compare_confidence_scores(float('inf'), float('inf'))
        assert result is True

        result = compare_confidence_scores(float('inf'), 0.9)
        assert result is False

    def test_compare_out_of_range(self):
        """Test comparing out-of-range values (still compared)."""
        # Values < 0 or > 1 are still compared
        result = compare_confidence_scores(1.5, 1.5)
        assert result is True

        result = compare_confidence_scores(-0.1, -0.1)
        assert result is True

    def test_compare_type_mismatch(self):
        """Test that type mismatches return False."""
        assert compare_confidence_scores("not_a_number", "also_not_a_number") is False


class TestCompareStructuredField:
    """Test structured field comparison with edge cases."""

    def test_compare_both_none(self):
        """Test that both None values match."""
        result = compare_structured_field(None, None)
        assert result is True

    def test_compare_one_none(self):
        """Test that one None doesn't match."""
        result = compare_structured_field(None, {"key": "value"})
        assert result is False

        result = compare_structured_field({"key": "value"}, None)
        assert result is False

    def test_compare_matching_primitives(self):
        """Test comparing matching primitive types."""
        assert compare_structured_field("string", "string") is True
        assert compare_structured_field(123, 123) is True
        assert compare_structured_field(True, True) is True

    def test_compare_mismatching_primitives(self):
        """Test comparing mismatching primitive types."""
        assert compare_structured_field("string1", "string2") is False
        assert compare_structured_field(123, 456) is False
        assert compare_structured_field(True, False) is False

    def test_compare_matching_floats_with_tolerance(self):
        """Test comparing floats within tolerance."""
        result = compare_structured_field(0.9, 0.91, tolerance=0.02)
        assert result is True

    def test_compare_mismatching_floats(self):
        """Test comparing floats outside tolerance."""
        result = compare_structured_field(0.9, 0.85)
        assert result is False

    def test_compare_matching_dicts(self):
        """Test comparing matching dicts."""
        result = compare_structured_field(
            {"key": "value", "number": 123},
            {"key": "value", "number": 123}
        )
        assert result is True

    def test_compare_mismatching_dicts(self):
        """Test comparing mismatching dicts."""
        result = compare_structured_field(
            {"key": "value1"},
            {"key": "value2"}
        )
        assert result is False

    def test_compare_nested_none_in_dicts(self):
        """Test dicts with nested None values."""
        result = compare_structured_field(
            {"key": None},
            {"key": None}
        )
        assert result is True

        result = compare_structured_field(
            {"key": None},
            {"key": "value"}
        )
        assert result is False

    def test_compare_different_key_sets(self):
        """Test dicts with different key sets."""
        result = compare_structured_field(
            {"key1": "value"},
            {"key2": "value"}
        )
        assert result is False

    def test_compare_matching_lists(self):
        """Test comparing matching lists (order-insensitive)."""
        result = compare_structured_field([1, 2, 3], [3, 2, 1])
        assert result is True

    def test_compare_mismatching_lists(self):
        """Test comparing mismatching lists."""
        result = compare_structured_field([1, 2, 3], [1, 2, 4])
        assert result is False

    def test_compare_different_length_lists(self):
        """Test lists with different lengths."""
        result = compare_structured_field([1, 2], [1, 2, 3])
        assert result is False

    def test_compare_empty_lists(self):
        """Test comparing empty lists."""
        result = compare_structured_field([], [])
        assert result is True

    def test_compare_type_mismatch(self):
        """Test comparing different types."""
        assert compare_structured_field({"key": "value"}, ["list"]) is False
        assert compare_structured_field("string", 123) is False


class TestCompareDicts:
    """Test dictionary comparison with edge cases."""

    def test_compare_identical_dicts(self):
        """Test comparing identical dicts."""
        result = compare_dicts({"key": "value"}, {"key": "value"})
        assert result is True

    def test_compare_different_keys(self):
        """Test dicts with different keys."""
        result = compare_dicts({"key1": "value"}, {"key2": "value"})
        assert result is False

    def test_compare_different_values(self):
        """Test dicts with different values."""
        result = compare_dicts({"key": "value1"}, {"key": "value2"})
        assert result is False

    def test_compare_nested_dicts(self):
        """Test comparing nested dicts."""
        result = compare_dicts(
            {"outer": {"inner": "value"}},
            {"outer": {"inner": "value"}}
        )
        assert result is True

    def test_compare_nested_none_values(self):
        """Test nested dicts with None values."""
        result = compare_dicts(
            {"outer": None},
            {"outer": None}
        )
        assert result is True

        result = compare_dicts(
            {"outer": {"inner": None}},
            {"outer": {"inner": None}}
        )
        assert result is True

    def test_compare_mixed_nested_types(self):
        """Test dicts with mixed nested types."""
        result = compare_dicts(
            {"list": [1, 2], "dict": {"key": "value"}},
            {"list": [1, 2], "dict": {"key": "value"}}
        )
        assert result is True


class TestCompareLists:
    """Test list comparison with edge cases."""

    def test_compare_identical_lists(self):
        """Test comparing identical lists."""
        result = compare_lists([1, 2, 3], [1, 2, 3])
        assert result is True

    def test_compare_order_insensitive(self):
        """Test that list comparison is order-insensitive."""
        result = compare_lists([1, 2, 3], [3, 2, 1])
        assert result is True

    def test_compare_different_lengths(self):
        """Test lists with different lengths."""
        result = compare_lists([1, 2], [1, 2, 3])
        assert result is False

    def test_compare_different_values(self):
        """Test lists with different values."""
        result = compare_lists([1, 2, 3], [1, 2, 4])
        assert result is False

    def test_compare_empty_lists(self):
        """Test comparing empty lists."""
        result = compare_lists([], [])
        assert result is True

    def test_compare_nested_dicts(self):
        """Test lists containing dicts."""
        result = compare_lists(
            [{"key": "value"}],
            [{"key": "value"}]
        )
        assert result is True

    def test_compare_mismatched_nested_dicts(self):
        """Test lists with mismatched nested dicts."""
        result = compare_lists(
            [{"key": "value1"}],
            [{"key": "value2"}]
        )
        assert result is False

    def test_compare_nested_lists(self):
        """Test lists containing nested lists."""
        result = compare_lists([[1, 2], [3, 4]], [[3, 4], [1, 2]])
        assert result is True


class TestCompareClassifications:
    """Test the main compare_classifications function with edge cases."""

    def test_perfect_match_single_classification(self):
        """Test perfect match with single classification."""
        dispatch = {"classifications": [{"intent_type": "status", "confidence": 0.9}]}
        test = {"classifications": [{"intent_type": "status", "confidence": 0.9}]}

        result = compare_classifications(dispatch, test)

        assert result.overall_match is True
        assert result.matching_count == 1
        assert result.mismatch_count == 0
        assert "Perfect match" in result.summary

    def test_perfect_match_multiple_classifications(self):
        """Test perfect match with multiple classifications."""
        dispatch = {
            "classifications": [
                {"intent_type": "status", "confidence": 0.9},
                {"intent_type": "lookup", "confidence": 0.8},
            ]
        }
        test = {
            "classifications": [
                {"intent_type": "status", "confidence": 0.9},
                {"intent_type": "lookup", "confidence": 0.8},
            ]
        }

        result = compare_classifications(dispatch, test)

        assert result.overall_match is True
        assert result.matching_count == 2
        assert result.mismatch_count == 0

    def test_intent_type_mismatch(self):
        """Test mismatch in intent type."""
        dispatch = {"classifications": [{"intent_type": "status", "confidence": 0.9}]}
        test = {"classifications": [{"intent_type": "lookup", "confidence": 0.9}]}

        result = compare_classifications(dispatch, test)

        assert result.overall_match is False
        assert result.mismatch_count == 1
        assert result.matching_count == 0

    def test_confidence_mismatch(self):
        """Test mismatch in confidence score."""
        dispatch = {"classifications": [{"intent_type": "status", "confidence": 0.9}]}
        test = {"classifications": [{"intent_type": "status", "confidence": 0.8}]}

        result = compare_classifications(dispatch, test)

        assert result.overall_match is False
        assert result.mismatch_count == 1

    def test_confidence_within_tolerance(self):
        """Test confidence within tolerance matches."""
        dispatch = {"classifications": [{"intent_type": "status", "confidence": 0.9}]}
        test = {"classifications": [{"intent_type": "status", "confidence": 0.905}]}

        result = compare_classifications(dispatch, test, confidence_tolerance=0.01)

        assert result.overall_match is True
        assert result.matching_count == 1

    def test_count_mismatch_more_dispatch(self):
        """Test count mismatch - dispatch has more classifications."""
        dispatch = {
            "classifications": [
                {"intent_type": "status", "confidence": 0.9},
                {"intent_type": "lookup", "confidence": 0.8},
            ]
        }
        test = {"classifications": [{"intent_type": "status", "confidence": 0.9}]}

        result = compare_classifications(dispatch, test)

        assert result.overall_match is False
        assert "Count mismatch" in result.summary

    def test_count_mismatch_more_test(self):
        """Test count mismatch - test has more classifications."""
        dispatch = {"classifications": [{"intent_type": "status", "confidence": 0.9}]}
        test = {
            "classifications": [
                {"intent_type": "status", "confidence": 0.9},
                {"intent_type": "lookup", "confidence": 0.8},
            ]
        }

        result = compare_classifications(dispatch, test)

        assert result.overall_match is False
        assert "Count mismatch" in result.summary

    def test_both_empty_results(self):
        """Test both endpoints returning no classifications."""
        dispatch = {"classifications": []}
        test = {"classifications": []}

        result = compare_classifications(dispatch, test)

        assert result.overall_match is True
        assert result.total_comparisons == 0

    def test_none_inputs(self):
        """Test None inputs."""
        result = compare_classifications(None, None)

        assert result.overall_match is True
        assert result.total_comparisons == 0

    def test_missing_intent_type_field(self):
        """Test classification missing intent_type field."""
        dispatch = {"classifications": [{"confidence": 0.9}]}
        test = {"classifications": [{"intent_type": "status", "confidence": 0.9}]}

        result = compare_classifications(dispatch, test)

        assert result.overall_match is False

    def test_none_intent_type_value(self):
        """Test classification with None intent_type value."""
        dispatch = {"classifications": [{"intent_type": None, "confidence": 0.9}]}
        test = {"classifications": [{"intent_type": "status", "confidence": 0.9}]}

        result = compare_classifications(dispatch, test)

        assert result.overall_match is False

    def test_none_confidence_value(self):
        """Test classification with None confidence value."""
        dispatch = {"classifications": [{"intent_type": "status", "confidence": None}]}
        test = {"classifications": [{"intent_type": "status", "confidence": 0.9}]}

        result = compare_classifications(dispatch, test)

        assert result.overall_match is False

    def test_routed_intent_structure(self):
        """Test comparing RoutedIntent structures."""
        dispatch = {
            "classifications": [
                {
                    "classification": {
                        "intent_type": "status",
                        "confidence": 0.9,
                        "project_slug": "test-project",
                    }
                }
            ]
        }
        test = {"classifications": [{"intent_type": "status", "confidence": 0.9}]}

        result = compare_classifications(dispatch, test)

        assert result.overall_match is True

    def test_list_input_format(self):
        """Test list input format (not wrapped in dict)."""
        dispatch = [{"intent_type": "status", "confidence": 0.9}]
        test = [{"intent_type": "status", "confidence": 0.9}]

        result = compare_classifications(dispatch, test)

        assert result.overall_match is True

    def test_structured_result_comparison(self):
        """Test comparison of structured_result field."""
        dispatch = {
            "classifications": [
                {
                    "intent_type": "status",
                    "confidence": 0.9,
                    "structured_result": {"project": "adc", "urgency": "high"},
                }
            ]
        }
        test = {
            "classifications": [
                {
                    "intent_type": "status",
                    "confidence": 0.9,
                    "structured_result": {"project": "adc", "urgency": "high"},
                }
            ]
        }

        result = compare_classifications(dispatch, test)

        assert result.overall_match is True

    def test_nested_structured_result_with_none(self):
        """Test structured_result with nested None values."""
        dispatch = {
            "classifications": [
                {
                    "intent_type": "status",
                    "confidence": 0.9,
                    "structured_result": {"project": None, "urgency": "high"},
                }
            ]
        }
        test = {
            "classifications": [
                {
                    "intent_type": "status",
                    "confidence": 0.9,
                    "structured_result": {"project": None, "urgency": "high"},
                }
            ]
        }

        result = compare_classifications(dispatch, test)

        assert result.overall_match is True

    def test_partial_match(self):
        """Test partial match (some fields match, others don't)."""
        dispatch = {
            "classifications": [
                {
                    "intent_type": "status",
                    "confidence": 0.9,
                    "project_slug": "adc",
                }
            ]
        }
        test = {
            "classifications": [
                {
                    "intent_type": "status",
                    "confidence": 0.85,  # Outside tolerance
                    "project_slug": "adc",
                }
            ]
        }

        result = compare_classifications(dispatch, test, confidence_tolerance=0.01)

        assert result.overall_match is False
        # A confidence failure is a core mismatch even when optional metadata
        # such as project_slug still matches.
        assert result.mismatch_count == 1
        assert result.partial_match_count == 0

    def test_all_fields_mismatch(self):
        """Test all fields mismatching."""
        dispatch = {
            "classifications": [
                {"intent_type": "status", "confidence": 0.9, "project_slug": "adc"}
            ]
        }
        test = {
            "classifications": [
                {"intent_type": "lookup", "confidence": 0.8, "project_slug": "other"}
            ]
        }

        result = compare_classifications(dispatch, test)

        assert result.overall_match is False
        assert result.mismatch_count == 1

    def test_order_insensitive_list_comparison(self):
        """Test that list fields are compared order-insensitively."""
        dispatch = {
            "classifications": [
                {
                    "intent_type": "status",
                    "confidence": 0.9,
                    "structured_result": {"entities": ["pod", "status"]},
                }
            ]
        }
        test = {
            "classifications": [
                {
                    "intent_type": "status",
                    "confidence": 0.9,
                    "structured_result": {"entities": ["status", "pod"]},
                }
            ]
        }

        result = compare_classifications(dispatch, test)

        assert result.overall_match is True


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
