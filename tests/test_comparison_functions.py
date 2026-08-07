"""
Unit tests for intent type and confidence comparison functions.

Tests the compare_intent_type and compare_confidence functions to ensure:
- Exact match handling for intent types
- Tolerance-based comparison for confidence scores
- Proper None/null value handling
- Type mismatch handling
- Edge cases (case sensitivity, out-of-range values, etc.)

Acceptance criteria from bead adc-1m13ea:
- Function compare_intent_type(dispatch_intent, test_intent) -> bool implemented
- Function compare_confidence(dispatch_confidence, test_confidence, tolerance=0.01) -> bool implemented
- Handles None/null values gracefully (returns False if either is None)
- Confidence comparison uses tolerance for float comparison
- Unit tests cover: exact match, tolerance match, None values, type mismatches
"""

import pytest
from enum import Enum

from src.intent.comparison import compare_intent_type, compare_confidence, compare_structured_fields
from src.intent.router import IntentType


class TestCompareIntentType:
    """Test suite for compare_intent_type function."""

    def test_exact_match_strings(self):
        """Verify exact string match returns True."""
        assert compare_intent_type("status", "status") is True
        assert compare_intent_type("action", "action") is True
        assert compare_intent_type("brainstorm", "brainstorm") is True

    def test_exact_match_enums(self):
        """Verify exact Enum match returns True."""
        assert compare_intent_type(IntentType.STATUS, IntentType.STATUS) is True
        assert compare_intent_type(IntentType.ACTION, IntentType.ACTION) is True

    def test_exact_match_mixed_enum_and_string(self):
        """Verify Enum and string with same value match returns True."""
        assert compare_intent_type("status", IntentType.STATUS) is True
        assert compare_intent_type(IntentType.ACTION, "action") is True

    def test_case_sensitive_match(self):
        """Verify case-sensitive matching works correctly."""
        assert compare_intent_type("status", "status") is True
        assert compare_intent_type("Status", "status") is False
        assert compare_intent_type("STATUS", "status") is False
        assert compare_intent_type("STATUS", "STATUS") is True

    def test_mismatch_strings(self):
        """Verify string mismatch returns False."""
        assert compare_intent_type("status", "action") is False
        assert compare_intent_type("brainstorm", "lookup") is False

    def test_mismatch_enums(self):
        """Verify Enum mismatch returns False."""
        assert compare_intent_type(IntentType.STATUS, IntentType.ACTION) is False
        assert compare_intent_type(IntentType.BRAINSTORM, IntentType.LOOKUP) is False

    def test_none_dispatch_value(self):
        """Verify None in dispatch parameter returns False."""
        assert compare_intent_type(None, "status") is False
        assert compare_intent_type(None, IntentType.ACTION) is False
        assert compare_intent_type(None, None) is False

    def test_none_test_value(self):
        """Verify None in test parameter returns False."""
        assert compare_intent_type("status", None) is False
        assert compare_intent_type(IntentType.ACTION, None) is False

    def test_type_mismatch_non_string(self):
        """Verify non-string types return False."""
        assert compare_intent_type(123, "status") is False
        assert compare_intent_type("status", 123) is False
        assert compare_intent_type(123.45, "status") is False
        assert compare_intent_type([], "status") is False
        assert compare_intent_type({}, "status") is False
        assert compare_intent_type(True, "status") is False

    def test_empty_strings(self):
        """Verify empty string handling."""
        assert compare_intent_type("", "") is True
        assert compare_intent_type("", "status") is False
        assert compare_intent_type("status", "") is False


class TestCompareConfidence:
    """Test suite for compare_confidence function."""

    def test_exact_match_floats(self):
        """Verify exact float match returns True."""
        assert compare_confidence(0.9, 0.9) is True
        assert compare_confidence(0.5, 0.5) is True
        assert compare_confidence(1.0, 1.0) is True
        assert compare_confidence(0.0, 0.0) is True

    def test_exact_match_ints(self):
        """Verify exact int match returns True."""
        assert compare_confidence(1, 1) is True
        assert compare_confidence(0, 0) is True
        assert compare_confidence(5, 5) is True

    def test_mixed_int_and_float(self):
        """Verify int and float with same value match returns True."""
        assert compare_confidence(1, 1.0) is True
        assert compare_confidence(0.9, 0.9) is True
        assert compare_confidence(1.0, 1) is True

    def test_tolerance_match_within_default(self):
        """Verify values within default tolerance (0.01) match returns True."""
        assert compare_confidence(0.9, 0.909) is True  # Difference: 0.009
        assert compare_confidence(0.9, 0.895) is True  # Difference: 0.005
        assert compare_confidence(0.85, 0.859) is True  # Difference: 0.009

    def test_tolerance_match_exceeds_default(self):
        """Verify values exceeding default tolerance (0.01) match returns False."""
        assert compare_confidence(0.9, 0.92) is False  # Difference: 0.02
        assert compare_confidence(0.9, 0.85) is False  # Difference: 0.05
        assert compare_confidence(0.85, 0.86) is False  # Difference: 0.01 (exactly at boundary, but > due to float precision)

    def test_custom_tolerance_match(self):
        """Verify custom tolerance parameter works correctly."""
        assert compare_confidence(0.9, 0.95, tolerance=0.1) is True
        assert compare_confidence(0.8, 0.89, tolerance=0.1) is True
        assert compare_confidence(0.7, 0.71, tolerance=0.02) is True

    def test_custom_tolerance_exceeds(self):
        """Verify values exceeding custom tolerance return False."""
        assert compare_confidence(0.9, 0.95, tolerance=0.01) is False
        assert compare_confidence(0.8, 0.89, tolerance=0.05) is False

    def test_none_dispatch_value(self):
        """Verify None in dispatch parameter returns False."""
        assert compare_confidence(None, 0.9) is False
        assert compare_confidence(None, 0.5) is False
        assert compare_confidence(None, 1.0) is False
        assert compare_confidence(None, None) is False

    def test_none_test_value(self):
        """Verify None in test parameter returns False."""
        assert compare_confidence(0.9, None) is False
        assert compare_confidence(0.5, None) is False
        assert compare_confidence(1.0, None) is False

    def test_type_mismatch_non_numeric(self):
        """Verify non-numeric types return False."""
        assert compare_confidence("0.9", 0.9) is False
        assert compare_confidence(0.9, "0.9") is False
        assert compare_confidence([], 0.9) is False
        assert compare_confidence({}, 0.9) is False
        assert compare_confidence(True, 0.9) is False

    def test_out_of_range_values_still_compare(self):
        """Verify values outside [0,1] range are still compared."""
        assert compare_confidence(1.5, 1.5) is True
        assert compare_confidence(1.5, 1.501) is True  # Within default tolerance
        assert compare_confidence(-0.5, -0.5) is True
        assert compare_confidence(2.0, 2.0) is True

    def test_boundary_values(self):
        """Verify boundary value comparisons."""
        # Zero boundary
        assert compare_confidence(0.0, 0.0) is True
        assert compare_confidence(0.0, 0.005) is True
        assert compare_confidence(0.0, 0.015) is False

        # One boundary
        assert compare_confidence(1.0, 1.0) is True
        assert compare_confidence(1.0, 0.995) is True
        assert compare_confidence(1.0, 0.985) is False

    def test_negative_values(self):
        """Verify negative value comparisons work."""
        assert compare_confidence(-0.1, -0.1) is True
        assert compare_confidence(-0.5, -0.49, tolerance=0.02) is True
        assert compare_confidence(-1.0, -0.9) is False  # Default tolerance

    def test_very_small_differences(self):
        """Verify very small differences are handled correctly."""
        assert compare_confidence(0.123456, 0.123457, tolerance=0.00001) is True
        assert compare_confidence(0.123456, 0.123457, tolerance=0.000001) is False

    def test_zero_tolerance(self):
        """Verify zero tolerance requires exact match."""
        assert compare_confidence(0.9, 0.9, tolerance=0.0) is True
        assert compare_confidence(0.9, 0.900001, tolerance=0.0) is False
        assert compare_confidence(0.9, 0.91, tolerance=0.0) is False

    def test_large_tolerance(self):
        """Verify large tolerance allows wide differences."""
        assert compare_confidence(0.5, 0.9, tolerance=0.5) is True
        assert compare_confidence(0.1, 0.9, tolerance=1.0) is True
        assert compare_confidence(0.0, 10.0, tolerance=15.0) is True


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_intent_type_unicode(self):
        """Verify unicode string handling in intent types."""
        assert compare_intent_type("café", "café") is True
        assert compare_intent_type("café", "cafe") is False

    def test_confidence_very_large_numbers(self):
        """Verify very large number comparisons."""
        assert compare_confidence(1e10, 1e10) is True
        assert compare_confidence(1e10, 1e10 + 1, tolerance=2) is True

    def test_confidence_very_small_numbers(self):
        """Verify very small number comparisons."""
        assert compare_confidence(1e-10, 1e-10) is True
        assert compare_confidence(1e-10, 1e-10 + 1e-12, tolerance=1e-11) is True

    def test_intent_type_whitespace(self):
        """Verify whitespace handling in intent types."""
        assert compare_intent_type(" status ", "status") is False
        assert compare_intent_type(" status ", " status ") is True
        assert compare_intent_type("status ", "status") is False

    def test_combined_none_handling(self):
        """Verify both functions return False for None values."""
        assert compare_intent_type(None, None) is False
        assert compare_confidence(None, None) is False

    def test_special_float_values(self):
        """Verify special float value handling."""
        # NaN values (float('nan') != float('nan') is always True, so comparison fails)
        assert compare_confidence(float('nan'), float('nan')) is False

        # Infinity values
        assert compare_confidence(float('inf'), float('inf')) is True
        assert compare_confidence(float('inf'), float('inf') + 1) is True
        assert compare_confidence(float('-inf'), float('-inf')) is True


class TestRealWorldScenarios:
    """Test real-world usage scenarios."""

    def test_typical_intent_comparison(self):
        """Verify typical intent type comparison scenarios."""
        # Valid matches
        assert compare_intent_type("status", "status") is True
        assert compare_intent_type("action", "action") is True
        assert compare_intent_type("lookup", "lookup") is True

        # Invalid matches
        assert compare_intent_type("status", "Status") is False
        assert compare_intent_type("action", "lookup") is False

    def test_typical_confidence_comparison(self):
        """Verify typical confidence comparison scenarios."""
        # Exact matches (common case)
        assert compare_confidence(0.9, 0.9) is True
        assert compare_confidence(0.85, 0.85) is True

        # Near matches within tolerance
        assert compare_confidence(0.9, 0.909) is True  # Small floating point diff
        assert compare_confidence(0.75, 0.749) is True

        # Clear mismatches
        assert compare_confidence(0.9, 0.85) is False
        assert compare_confidence(0.95, 0.8) is False

    def test_enum_vs_string_intent_types(self):
        """Verify mixed Enum and string comparisons work."""
        # Both should match since they represent the same value
        assert compare_intent_type("status", IntentType.STATUS) is True
        assert compare_intent_type(IntentType.STATUS, "status") is True
        assert compare_intent_type("action", IntentType.ACTION) is True

    def test_missing_data_scenarios(self):
        """Verify scenarios representing missing/invalid data."""
        # Missing intent type
        assert compare_intent_type(None, "status") is False
        assert compare_intent_type("status", None) is False

        # Missing confidence score
        assert compare_confidence(None, 0.9) is False
        assert compare_confidence(0.9, None) is False

        # Invalid types
        assert compare_intent_type("", "status") is False
        assert compare_confidence("high", 0.9) is False


class TestCompareStructuredFields:
    """Test suite for compare_structured_fields function."""

    def test_empty_dicts(self):
        """Verify comparison of empty dictionaries."""
        result = compare_structured_fields({}, {})
        assert result == {}

    def test_flat_primitive_fields_match(self):
        """Verify flat primitive field comparison with exact matches."""
        dispatch = {"project_slug": "aide-de-camp", "confidence": 0.9, "urgency": "high"}
        test = {"project_slug": "aide-de-camp", "confidence": 0.9, "urgency": "high"}
        result = compare_structured_fields(dispatch, test)
        assert result == {
            "project_slug": True,
            "confidence": True,
            "urgency": True,
        }

    def test_flat_primitive_fields_mismatch(self):
        """Verify flat primitive field comparison with mismatches."""
        dispatch = {"project_slug": "aide-de-camp", "confidence": 0.9}
        test = {"project_slug": "different-project", "confidence": 0.8}
        result = compare_structured_fields(dispatch, test)
        assert result == {
            "project_slug": False,
            "confidence": False,
        }

    def test_nested_dict_comparison_match(self):
        """Verify nested dictionary comparison with matches."""
        dispatch = {
            "parameters": {
                "project": "adc",
                "urgency": "high",
                "nested": {"key": "value"}
            }
        }
        test = {
            "parameters": {
                "project": "adc",
                "urgency": "high",
                "nested": {"key": "value"}
            }
        }
        result = compare_structured_fields(dispatch, test)
        # All fields should match including nested ones
        assert result["parameters.project"] is True
        assert result["parameters.urgency"] is True
        assert result["parameters.nested.key"] is True
        assert result["parameters"] is True  # Parent matches if all children match

    def test_nested_dict_comparison_mismatch(self):
        """Verify nested dictionary comparison with mismatches."""
        dispatch = {
            "parameters": {
                "project": "adc",
                "urgency": "high",
            }
        }
        test = {
            "parameters": {
                "project": "different",
                "urgency": "low",
            }
        }
        result = compare_structured_fields(dispatch, test)
        assert result["parameters.project"] is False
        assert result["parameters.urgency"] is False
        assert result["parameters"] is False  # Parent fails if any child fails

    def test_list_comparison_order_insensitive_match(self):
        """Verify list comparison is order-insensitive by default."""
        dispatch = {"entities": ["project", "status", "urgency"]}
        test = {"entities": ["status", "project", "urgency"]}  # Different order
        result = compare_structured_fields(dispatch, test)
        assert result["entities"] is True

    def test_list_comparison_order_insensitive_mismatch(self):
        """Verify list comparison detects actual differences."""
        dispatch = {"entities": ["project", "status"]}
        test = {"entities": ["project", "different"]}  # Different element
        result = compare_structured_fields(dispatch, test)
        assert result["entities"] is False

    def test_list_comparison_order_sensitive(self):
        """Verify order-sensitive list comparison when configured."""
        dispatch = {"steps": ["step1", "step2", "step3"]}
        test = {"steps": ["step3", "step1", "step2"]}  # Different order
        result = compare_structured_fields(
            dispatch, test, order_sensitive_fields=["steps"]
        )
        assert result["steps"] is False

    def test_list_comparison_order_sensitive_match(self):
        """Verify order-sensitive list comparison with same order."""
        dispatch = {"steps": ["step1", "step2", "step3"]}
        test = {"steps": ["step1", "step2", "step3"]}  # Same order
        result = compare_structured_fields(
            dispatch, test, order_sensitive_fields=["steps"]
        )
        assert result["steps"] is True

    def test_missing_key_in_dispatch(self):
        """Verify missing key in dispatch is treated as mismatch."""
        test = {"project_slug": "aide-de-camp", "confidence": 0.9}
        dispatch = {"project_slug": "aide-de-camp"}  # Missing confidence
        result = compare_structured_fields(dispatch, test)
        assert result["project_slug"] is True
        assert result["confidence"] is False

    def test_missing_key_in_test(self):
        """Verify missing key in test is treated as mismatch."""
        dispatch = {"project_slug": "aide-de-camp", "confidence": 0.9}
        test = {"project_slug": "aide-de-camp"}  # Missing confidence
        result = compare_structured_fields(dispatch, test)
        assert result["project_slug"] is True
        assert result["confidence"] is False

    def test_nested_none_values_match(self):
        """Verify nested None values match when both are None."""
        dispatch = {"parameters": {"project": None, "urgency": None}}
        test = {"parameters": {"project": None, "urgency": None}}
        result = compare_structured_fields(dispatch, test)
        assert result["parameters.project"] is True
        assert result["parameters.urgency"] is True
        assert result["parameters"] is True

    def test_nested_none_values_mismatch(self):
        """Verify nested None values mismatch when one is not None."""
        dispatch = {"parameters": {"project": None}}
        test = {"parameters": {"project": "adc"}}
        result = compare_structured_fields(dispatch, test)
        assert result["parameters.project"] is False
        assert result["parameters"] is False

    def test_empty_dict_vs_none_in_dispatch(self):
        """Verify empty dict vs None in dispatch is treated as mismatch."""
        dispatch = {"parameters": {}}
        test = {"parameters": None}
        result = compare_structured_fields(dispatch, test)
        assert result["parameters"] is False

    def test_empty_dict_vs_none_in_test(self):
        """Verify empty dict vs None in test is treated as mismatch."""
        dispatch = {"parameters": None}
        test = {"parameters": {}}
        result = compare_structured_fields(dispatch, test)
        assert result["parameters"] is False

    def test_empty_list_vs_missing(self):
        """Verify empty list vs missing key is treated as mismatch."""
        dispatch = {"entities": []}
        test = {}
        result = compare_structured_fields(dispatch, test)
        assert result["entities"] is False

    def test_float_tolerance(self):
        """Verify float comparison with tolerance."""
        dispatch = {"confidence": 0.9}
        test = {"confidence": 0.899}  # Within 0.01 tolerance
        result = compare_structured_fields(dispatch, test)
        assert result["confidence"] is True

    def test_float_tolerance_exceeded(self):
        """Verify float comparison fails when tolerance exceeded."""
        dispatch = {"confidence": 0.9}
        test = {"confidence": 0.85}  # Exceeds 0.01 tolerance
        result = compare_structured_fields(dispatch, test)
        assert result["confidence"] is False

    def test_int_float_mix(self):
        """Verify int and float comparison works."""
        dispatch = {"count": 5}
        test = {"count": 5.0}
        result = compare_structured_fields(dispatch, test)
        assert result["count"] is True

    def test_complex_nested_structure(self):
        """Verify complex nested structure comparison."""
        dispatch = {
            "parameters": {
                "project": "adc",
                "metadata": {
                    "tags": ["urgent", "review"],
                    "nested": {"key": "value"}
                }
            },
            "entities": ["project", "status"]
        }
        test = {
            "parameters": {
                "project": "adc",
                "metadata": {
                    "tags": ["review", "urgent"],  # Different order
                    "nested": {"key": "value"}
                }
            },
            "entities": ["status", "project"]  # Different order
        }
        result = compare_structured_fields(dispatch, test)
        # All should match despite different list orders
        assert result["parameters.project"] is True
        assert result["parameters.metadata.tags"] is True
        assert result["parameters.metadata.nested.key"] is True
        assert result["parameters.metadata"] is True
        assert result["parameters"] is True
        assert result["entities"] is True

    def test_nested_order_sensitive_field(self):
        """Verify order-sensitive comparison for nested field paths."""
        dispatch = {
            "metadata": {
                "steps": ["step1", "step2"]
            }
        }
        test = {
            "metadata": {
                "steps": ["step2", "step1"]
            }
        }
        result = compare_structured_fields(
            dispatch, test, order_sensitive_fields=["metadata.steps"]
        )
        assert result["metadata.steps"] is False

    def test_none_vs_none_both_none(self):
        """Verify both inputs being None returns empty dict."""
        result = compare_structured_fields(None, None)
        assert result == {}

    def test_dispatch_none_test_not_none(self):
        """Verify dispatch None and test non-None returns all False."""
        result = compare_structured_fields(None, {"field": "value"})
        assert result == {"field": False}

    def test_dispatch_not_none_test_none(self):
        """Verify dispatch non-None and test None returns all False."""
        result = compare_structured_fields({"field": "value"}, None)
        assert result == {"field": False}

    def test_list_of_dicts_comparison(self):
        """Verify comparison of lists containing dictionaries."""
        dispatch = {
            "items": [
                {"id": 1, "name": "first"},
                {"id": 2, "name": "second"}
            ]
        }
        test = {
            "items": [
                {"id": 2, "name": "second"},  # Different order
                {"id": 1, "name": "first"}
            ]
        }
        result = compare_structured_fields(dispatch, test)
        assert result["items"] is True  # Order-insensitive for dicts

    def test_list_of_dicts_order_sensitive(self):
        """Verify order-sensitive comparison of lists containing dictionaries."""
        dispatch = {
            "steps": [
                {"action": "load"},
                {"action": "process"}
            ]
        }
        test = {
            "steps": [
                {"action": "process"},  # Different order
                {"action": "load"}
            ]
        }
        result = compare_structured_fields(
            dispatch, test, order_sensitive_fields=["steps"]
        )
        assert result["steps"] is False

    def test_mixed_types_comparison(self):
        """Verify comparison handles mixed types correctly."""
        dispatch = {
            "string": "value",
            "number": 42,
            "float": 3.14,
            "boolean": True,
            "list": [1, 2, 3],
            "nested": {"key": "value"}
        }
        test = {
            "string": "value",
            "number": 42,
            "float": 3.14,
            "boolean": True,
            "list": [3, 2, 1],  # Different order
            "nested": {"key": "value"}
        }
        result = compare_structured_fields(dispatch, test)
        assert result["string"] is True
        assert result["number"] is True
        assert result["float"] is True
        assert result["boolean"] is True
        assert result["list"] is True  # Order-insensitive
        assert result["nested.key"] is True

    def test_deeply_nested_structure(self):
        """Verify deeply nested dictionary comparison."""
        dispatch = {
            "level1": {
                "level2": {
                    "level3": {
                        "level4": "deep_value"
                    }
                }
            }
        }
        test = {
            "level1": {
                "level2": {
                    "level3": {
                        "level4": "deep_value"
                    }
                }
            }
        }
        result = compare_structured_fields(dispatch, test)
        assert result["level1.level2.level3.level4"] is True
        assert result["level1.level2.level3"] is True
        assert result["level1.level2"] is True
        assert result["level1"] is True

    def test_partial_nested_mismatch(self):
        """Verify partial mismatch in nested structure."""
        dispatch = {
            "parameters": {
                "project": "adc",
                "urgency": "high",
                "metadata": {"tags": ["urgent"]}
            }
        }
        test = {
            "parameters": {
                "project": "adc",  # Match
                "urgency": "low",  # Mismatch
                "metadata": {"tags": ["review"]}  # Mismatch
            }
        }
        result = compare_structured_fields(dispatch, test)
        assert result["parameters.project"] is True
        assert result["parameters.urgency"] is False
        assert result["parameters.metadata.tags"] is False
        assert result["parameters.metadata"] is False
        assert result["parameters"] is False
