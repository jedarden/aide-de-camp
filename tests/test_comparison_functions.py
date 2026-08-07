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

from src.intent.comparison import compare_intent_type, compare_confidence
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
