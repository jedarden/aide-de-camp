"""
Comprehensive unit tests for unified classification comparison.

Tests the compare_classifications function to ensure it properly integrates
all comparison logic and handles all edge cases specified in bead adc-8ynoqj.

Acceptance criteria:
- Function compare_classifications(dispatch_result, test_result) -> ComparisonReport implemented
- Integrates all comparison functions from previous beads
- Returns ComparisonReport with: overall_match (bool), summary (str), detailed diffs (list[FieldDiff])
- Handles edge cases: missing keys, null values, type mismatches, nested structures
- Comprehensive unit tests covering all edge cases
- Returns True for overall_match only if ALL components match
"""

from enum import Enum

import pytest

from src.intent.unified_comparison import (
    compare_classifications,
    compare_confidence_scores,
    compare_intent_types,
    normalize_input_to_classifications,
    safe_get,
)
from src.validation.comparison import (
    FieldDiff,
)


class TestCompareClassificationsPerfectMatch:
    """Test perfect match scenarios."""

    def test_perfect_match_simple_classifications(self):
        """Verify perfect match with simple classification structures."""
        dispatch = {
            "classifications": [
                {
                    "intent_type": "status",
                    "project_slug": "adc",
                    "confidence": 0.9,
                }
            ]
        }
        test = {
            "classifications": [
                {
                    "intent_type": "status",
                    "project_slug": "adc",
                    "confidence": 0.9,
                }
            ]
        }
        report = compare_classifications(dispatch, test)
        assert report.overall_match is True
        assert report.total_comparisons == 1
        assert report.matching_count == 1
        assert report.partial_match_count == 0
        assert report.mismatch_count == 0
        assert "Perfect match" in report.summary

    def test_perfect_match_all_fields(self):
        """Verify perfect match with all classification fields."""
        dispatch = {
            "classifications": [
                {
                    "intent_type": "action",
                    "project_slug": "adc",
                    "confidence": 0.85,
                    "utterance_fragment": "check deployment",
                    "reasoning": "User wants to verify deployment status",
                    "urgency": "medium",
                    "lookup_kind": "deployment_status",
                    "structured_result": {"project": "adc", "status": "running"},
                }
            ]
        }
        test = {
            "classifications": [
                {
                    "intent_type": "action",
                    "project_slug": "adc",
                    "confidence": 0.85,
                    "utterance_fragment": "check deployment",
                    "reasoning": "User wants to verify deployment status",
                    "urgency": "medium",
                    "lookup_kind": "deployment_status",
                    "structured_result": {"project": "adc", "status": "running"},
                }
            ]
        }
        report = compare_classifications(dispatch, test)
        assert report.overall_match is True
        assert report.matching_count == 1

    def test_perfect_confidence_within_tolerance(self):
        """Verify perfect match when confidence is within tolerance."""
        dispatch = {"classifications": [{"intent_type": "status", "confidence": 0.9}]}
        test = {"classifications": [{"intent_type": "status", "confidence": 0.909}]}
        report = compare_classifications(dispatch, test)
        assert report.overall_match is True
        assert report.matching_count == 1

    def test_perfect_match_multiple_classifications(self):
        """Verify perfect match with multiple classifications."""
        dispatch = {
            "classifications": [
                {"intent_type": "status", "confidence": 0.9},
                {"intent_type": "action", "confidence": 0.8},
            ]
        }
        test = {
            "classifications": [
                {"intent_type": "status", "confidence": 0.9},
                {"intent_type": "action", "confidence": 0.8},
            ]
        }
        report = compare_classifications(dispatch, test)
        assert report.overall_match is True
        assert report.total_comparisons == 2
        assert report.matching_count == 2


class TestCompareClassificationsIntentMismatch:
    """Test intent type mismatch scenarios."""

    def test_intent_type_mismatch(self):
        """Verify intent type mismatch is detected."""
        dispatch = {"classifications": [{"intent_type": "status", "confidence": 0.9}]}
        test = {"classifications": [{"intent_type": "action", "confidence": 0.9}]}
        report = compare_classifications(dispatch, test)
        assert report.overall_match is False
        assert report.mismatch_count == 1
        # Check that intent_type diff is present
        assert any(d.field_name == "intent_type" and not d.is_match for d in report.results[0].diffs)

    def test_intent_none_vs_value(self):
        """Verify None intent vs value is mismatch."""
        dispatch = {"classifications": [{"intent_type": None, "confidence": 0.9}]}
        test = {"classifications": [{"intent_type": "status", "confidence": 0.9}]}
        report = compare_classifications(dispatch, test)
        assert report.overall_match is False
        assert report.mismatch_count == 1

    def test_intent_both_none(self):
        """Verify both None intents is mismatch (None never matches)."""
        dispatch = {"classifications": [{"intent_type": None, "confidence": 0.9}]}
        test = {"classifications": [{"intent_type": None, "confidence": 0.9}]}
        report = compare_classifications(dispatch, test)
        assert report.overall_match is False
        # None never matches, so this should be a mismatch
        assert report.mismatch_count == 1

    def test_intent_case_sensitive_mismatch(self):
        """Verify case-sensitive intent comparison."""
        dispatch = {"classifications": [{"intent_type": "Status", "confidence": 0.9}]}
        test = {"classifications": [{"intent_type": "status", "confidence": 0.9}]}
        report = compare_classifications(dispatch, test)
        assert report.overall_match is False


class TestCompareClassificationsConfidenceMismatch:
    """Test confidence score mismatch scenarios."""

    def test_confidence_exceeds_tolerance(self):
        """Verify confidence exceeding tolerance is mismatch."""
        dispatch = {"classifications": [{"intent_type": "status", "confidence": 0.9}]}
        test = {"classifications": [{"intent_type": "status", "confidence": 0.85}]}
        report = compare_classifications(dispatch, test)
        assert report.overall_match is False
        assert report.mismatch_count == 1

    def test_confidence_none_vs_value(self):
        """Verify None confidence vs value is mismatch."""
        dispatch = {"classifications": [{"intent_type": "status", "confidence": None}]}
        test = {"classifications": [{"intent_type": "status", "confidence": 0.9}]}
        report = compare_classifications(dispatch, test)
        assert report.overall_match is False

    def test_confidence_both_none(self):
        """Verify both None confidences is mismatch."""
        dispatch = {"classifications": [{"intent_type": "status", "confidence": None}]}
        test = {"classifications": [{"intent_type": "status", "confidence": None}]}
        report = compare_classifications(dispatch, test)
        assert report.overall_match is False

    def test_confidence_custom_tolerance(self):
        """Verify custom tolerance parameter works."""
        dispatch = {"classifications": [{"intent_type": "status", "confidence": 0.9}]}
        test = {"classifications": [{"intent_type": "status", "confidence": 0.85}]}
        report = compare_classifications(dispatch, test, confidence_tolerance=0.1)
        assert report.overall_match is True


class TestCompareClassificationsStructuredFieldMismatch:
    """Test structured field mismatch scenarios."""

    def test_structured_result_mismatch(self):
        """Verify structured result mismatch is detected."""
        dispatch = {
            "classifications": [
                {"intent_type": "status", "structured_result": {"project": "adc"}}
            ]
        }
        test = {
            "classifications": [
                {"intent_type": "status", "structured_result": {"project": "different"}}
            ]
        }
        report = compare_classifications(dispatch, test)
        # Intent and confidence match, but structured_result doesn't
        # This is a partial match (not a full match, but intent/confidence match)
        assert report.overall_match is False
        assert report.partial_match_count == 1
        assert report.mismatch_count == 0

    def test_structured_result_none_vs_dict(self):
        """Verify structured result None vs dict is mismatch."""
        dispatch = {
            "classifications": [{"intent_type": "status", "structured_result": None}]
        }
        test = {
            "classifications": [
                {"intent_type": "status", "structured_result": {"project": "adc"}}
            ]
        }
        report = compare_classifications(dispatch, test)
        assert report.overall_match is False

    def test_structured_result_both_none(self):
        """Verify both None structured results match."""
        dispatch = {
            "classifications": [{"intent_type": "status", "structured_result": None}]
        }
        test = {
            "classifications": [{"intent_type": "status", "structured_result": None}]
        }
        report = compare_classifications(dispatch, test)
        # Both None should match
        assert report.matching_count == 1

    def test_structured_nested_dict_match(self):
        """Verify nested structured result match."""
        dispatch = {
            "classifications": [
                {
                    "intent_type": "status",
                    "structured_result": {"project": "adc", "metadata": {"tags": ["urgent"]}},
                }
            ]
        }
        test = {
            "classifications": [
                {
                    "intent_type": "status",
                    "structured_result": {"project": "adc", "metadata": {"tags": ["urgent"]}},
                }
            ]
        }
        report = compare_classifications(dispatch, test)
        assert report.overall_match is True

    def test_structured_list_order_insensitive_match(self):
        """Verify list comparison in structured result is order-insensitive."""
        dispatch = {
            "classifications": [
                {"intent_type": "status", "structured_result": {"tags": ["urgent", "review"]}}
            ]
        }
        test = {
            "classifications": [
                {"intent_type": "status", "structured_result": {"tags": ["review", "urgent"]}}
            ]
        }
        report = compare_classifications(dispatch, test)
        assert report.overall_match is True


class TestCompareClassificationsPartialMatch:
    """Test partial match scenarios (some fields match, not all)."""

    def test_partial_match_intent_confidence(self):
        """Verify partial match when only some fields match."""
        dispatch = {"classifications": [{"intent_type": "status", "confidence": 0.9}]}
        test = {"classifications": [{"intent_type": "status", "confidence": 0.85}]}
        report = compare_classifications(dispatch, test)
        # Confidence mismatch is treated as a mismatch (not partial match)
        # because intent or confidence mismatch = mismatch
        assert report.overall_match is False
        assert report.mismatch_count == 1
        assert report.partial_match_count == 0

    def test_partial_match_multiple_fields(self):
        """Verify partial match with multiple field matches."""
        dispatch = {
            "classifications": [
                {
                    "intent_type": "status",
                    "project_slug": "adc",
                    "confidence": 0.9,
                }
            ]
        }
        test = {
            "classifications": [
                {
                    "intent_type": "status",
                    "project_slug": "adc",
                    "confidence": 0.85,
                }
            ]
        }
        report = compare_classifications(dispatch, test)
        # Confidence mismatch is treated as a mismatch (not partial match)
        assert report.overall_match is False
        assert report.mismatch_count == 1
        assert report.partial_match_count == 0

    def test_partial_match_mixed_results(self):
        """Verify partial match with mixed results across classifications."""
        dispatch = {
            "classifications": [
                {"intent_type": "status", "confidence": 0.9},
                {"intent_type": "action", "confidence": 0.8},
            ]
        }
        test = {
            "classifications": [
                {"intent_type": "status", "confidence": 0.9},
                {"intent_type": "different", "confidence": 0.8},
            ]
        }
        report = compare_classifications(dispatch, test)
        assert report.overall_match is False
        assert report.total_comparisons == 2
        assert report.matching_count == 1
        # Intent mismatch is treated as a mismatch (not partial match)
        assert report.mismatch_count == 1
        assert report.partial_match_count == 0


class TestCompareClassificationsCountMismatch:
    """Test count mismatch scenarios."""

    def test_count_more_dispatch(self):
        """Verify count mismatch when dispatch has more classifications."""
        dispatch = {
            "classifications": [
                {"intent_type": "status", "confidence": 0.9},
                {"intent_type": "action", "confidence": 0.8},
            ]
        }
        test = {"classifications": [{"intent_type": "status", "confidence": 0.9}]}
        report = compare_classifications(dispatch, test)
        assert report.overall_match is False
        assert report.total_comparisons == 2
        assert "Count mismatch" in report.summary

    def test_count_more_test(self):
        """Verify count mismatch when test has more classifications."""
        dispatch = {"classifications": [{"intent_type": "status", "confidence": 0.9}]}
        test = {
            "classifications": [
                {"intent_type": "status", "confidence": 0.9},
                {"intent_type": "action", "confidence": 0.8},
            ]
        }
        report = compare_classifications(dispatch, test)
        assert report.overall_match is False
        assert report.total_comparisons == 2
        assert "Count mismatch" in report.summary

    def test_count_mismatch_with_content_mismatch(self):
        """Verify count mismatch combined with content mismatch."""
        dispatch = {
            "classifications": [
                {"intent_type": "status", "confidence": 0.9},
                {"intent_type": "action", "confidence": 0.8},
            ]
        }
        test = {
            "classifications": [
                {"intent_type": "different", "confidence": 0.9}
            ]
        }
        report = compare_classifications(dispatch, test)
        assert report.overall_match is False
        assert report.total_comparisons == 2
        # One content mismatch + one count mismatch
        assert report.mismatch_count >= 1


class TestCompareClassificationsEmptyInputs:
    """Test empty/None input scenarios."""

    def test_both_empty_no_classifications(self):
        """Verify both endpoints returning no classifications."""
        dispatch = {"classifications": []}
        test = {"classifications": []}
        report = compare_classifications(dispatch, test)
        assert report.total_comparisons == 0
        assert "no classifications" in report.summary

    def test_both_none_inputs(self):
        """Verify both None inputs handled gracefully."""
        dispatch = None
        test = None
        report = compare_classifications(dispatch, test)
        assert report.total_comparisons == 0

    def test_dispatch_none_test_not_empty(self):
        """Verify None dispatch vs non-empty test."""
        dispatch = None
        test = {"classifications": [{"intent_type": "status", "confidence": 0.9}]}
        report = compare_classifications(dispatch, test)
        assert report.overall_match is False
        assert "Count mismatch" in report.summary

    def test_dispatch_not_empty_test_none(self):
        """Verify None test vs non-empty dispatch."""
        dispatch = {"classifications": [{"intent_type": "status", "confidence": 0.9}]}
        test = None
        report = compare_classifications(dispatch, test)
        assert report.overall_match is False
        assert "Count mismatch" in report.summary

    def test_empty_dict_inputs(self):
        """Verify empty dict inputs handled gracefully."""
        dispatch = {}
        test = {}
        report = compare_classifications(dispatch, test)
        assert report.total_comparisons == 0


class TestCompareClassificationsMissingKeys:
    """Test missing key scenarios."""

    def test_missing_intent_type_both(self):
        """Verify missing intent_type in both classifications."""
        dispatch = {"classifications": [{"confidence": 0.9}]}
        test = {"classifications": [{"confidence": 0.9}]}
        report = compare_classifications(dispatch, test)
        # Missing keys in both should not count as mismatch
        assert report.matching_count == 1

    def test_missing_intent_type_dispatch_only(self):
        """Verify missing intent_type only in dispatch."""
        dispatch = {"classifications": [{"confidence": 0.9}]}
        test = {"classifications": [{"intent_type": "status", "confidence": 0.9}]}
        report = compare_classifications(dispatch, test)
        assert report.overall_match is False

    def test_missing_confidence_both(self):
        """Verify missing confidence in both classifications."""
        dispatch = {"classifications": [{"intent_type": "status"}]}
        test = {"classifications": [{"intent_type": "status"}]}
        report = compare_classifications(dispatch, test)
        # Missing keys in both should not count as mismatch
        assert report.matching_count == 1

    def test_missing_structured_result_both(self):
        """Verify missing structured_result in both classifications."""
        dispatch = {"classifications": [{"intent_type": "status", "confidence": 0.9}]}
        test = {"classifications": [{"intent_type": "status", "confidence": 0.9}]}
        report = compare_classifications(dispatch, test)
        assert report.matching_count == 1

    def test_multiple_missing_keys_both(self):
        """Verify multiple missing keys in both classifications."""
        dispatch = {"classifications": [{"intent_type": "status"}]}
        test = {"classifications": [{"intent_type": "status"}]}
        report = compare_classifications(dispatch, test)
        assert report.matching_count == 1


class TestCompareClassificationsTypeMismatches:
    """Test type mismatch scenarios."""

    def test_confidence_int_vs_float(self):
        """Verify int vs float confidence comparison works."""
        dispatch = {"classifications": [{"intent_type": "status", "confidence": 1}]}
        test = {"classifications": [{"intent_type": "status", "confidence": 1.0}]}
        report = compare_classifications(dispatch, test)
        assert report.overall_match is True

    def test_confidence_string_vs_numeric(self):
        """Verify string confidence vs numeric matches (string conversion)."""
        dispatch = {"classifications": [{"intent_type": "status", "confidence": "0.9"}]}
        test = {"classifications": [{"intent_type": "status", "confidence": 0.9}]}
        report = compare_classifications(dispatch, test)
        # compare_confidence_scores converts strings to floats, so they match
        assert report.overall_match is True

    def test_structured_dict_vs_list(self):
        """Verify dict vs list in structured_result is mismatch."""
        dispatch = {
            "classifications": [{"intent_type": "status", "structured_result": {"key": "value"}}]
        }
        test = {
            "classifications": [{"intent_type": "status", "structured_result": ["value"]}]
        }
        report = compare_classifications(dispatch, test)
        assert report.overall_match is False

    def test_intent_enum_vs_string(self):
        """Verify enum vs string intent comparison works."""
        class TestIntent(Enum):
            STATUS = "status"

        dispatch = {"classifications": [{"intent_type": TestIntent.STATUS, "confidence": 0.9}]}
        test = {"classifications": [{"intent_type": "status", "confidence": 0.9}]}
        report = compare_classifications(dispatch, test)
        assert report.overall_match is True


class TestCompareClassificationsNestedNoneValues:
    """Test nested None value scenarios."""

    def test_nested_none_in_structured_result(self):
        """Verify nested None values in structured result handled correctly."""
        dispatch = {
            "classifications": [
                {"intent_type": "status", "structured_result": {"project": None, "urgency": None}}
            ]
        }
        test = {
            "classifications": [
                {"intent_type": "status", "structured_result": {"project": None, "urgency": None}}
            ]
        }
        report = compare_classifications(dispatch, test)
        # Both None should match
        assert report.matching_count == 1

    def test_nested_none_mismatch(self):
        """Verify nested None vs value is mismatch."""
        dispatch = {
            "classifications": [
                {"intent_type": "status", "structured_result": {"project": None}}
            ]
        }
        test = {
            "classifications": [
                {"intent_type": "status", "structured_result": {"project": "adc"}}
            ]
        }
        report = compare_classifications(dispatch, test)
        assert report.overall_match is False

    def test_deeply_nested_none(self):
        """Verify deeply nested None values handled correctly."""
        dispatch = {
            "classifications": [
                {
                    "intent_type": "status",
                    "structured_result": {"level1": {"level2": {"value": None}}},
                }
            ]
        }
        test = {
            "classifications": [
                {
                    "intent_type": "status",
                    "structured_result": {"level1": {"level2": {"value": None}}},
                }
            ]
        }
        report = compare_classifications(dispatch, test)
        assert report.matching_count == 1


class TestCompareClassificationsEmptyVsMissing:
    """Test empty vs missing key scenarios."""

    def test_empty_dict_vs_missing_key(self):
        """Verify empty dict vs missing key handled correctly."""
        dispatch = {"classifications": [{"intent_type": "status", "structured_result": {}}]}
        test = {"classifications": [{"intent_type": "status"}]}
        report = compare_classifications(dispatch, test)
        # Empty dict in dispatch but missing in test - should count as mismatch
        assert report.overall_match is False

    def test_empty_list_vs_missing_key(self):
        """Verify empty list vs missing key handled correctly."""
        dispatch = {"classifications": [{"intent_type": "status", "structured_result": {"tags": []}}]}
        test = {"classifications": [{"intent_type": "status", "structured_result": {}}]}
        report = compare_classifications(dispatch, test)
        assert report.overall_match is False

    def test_empty_string_vs_missing_key(self):
        """Verify empty string vs missing key handled correctly."""
        dispatch = {"classifications": [{"intent_type": "status", "utterance_fragment": ""}]}
        test = {"classifications": [{"intent_type": "status"}]}
        report = compare_classifications(dispatch, test)
        # Empty string vs missing - should count as mismatch
        assert report.overall_match is False


class TestCompareClassificationsRoutedIntentStructure:
    """Test RoutedIntent structure handling."""

    def test_routed_intent_nested_classification(self):
        """Verify RoutedIntent structure with nested classification is handled."""
        dispatch = {
            "classifications": [
                {
                    "classification": {
                        "intent_type": "status",
                        "project_slug": "adc",
                        "confidence": 0.9,
                    }
                }
            ]
        }
        test = {
            "classifications": [
                {"intent_type": "status", "project_slug": "adc", "confidence": 0.9}
            ]
        }
        report = compare_classifications(dispatch, test)
        assert report.overall_match is True

    def test_routed_intent_with_none_classification(self):
        """Verify RoutedIntent with None classification handled."""
        dispatch = {
            "classifications": [
                {"classification": None}
            ]
        }
        test = {
            "classifications": [
                {"intent_type": None, "project_slug": None, "confidence": None}
            ]
        }
        report = compare_classifications(dispatch, test)
        # Both should be None/missing - should count as match for missing fields
        assert report.total_comparisons == 1


class TestCompareClassificationsListInput:
    """Test list input format (without 'classifications' key)."""

    def test_list_input_format(self):
        """Verify direct list input format works."""
        dispatch = [{"intent_type": "status", "confidence": 0.9}]
        test = [{"intent_type": "status", "confidence": 0.9}]
        report = compare_classifications(dispatch, test)
        assert report.overall_match is True

    def test_list_input_format_mismatch(self):
        """Verify list input format with mismatch."""
        dispatch = [{"intent_type": "status", "confidence": 0.9}]
        test = [{"intent_type": "action", "confidence": 0.9}]
        report = compare_classifications(dispatch, test)
        assert report.overall_match is False

    def test_list_input_multiple_items(self):
        """Verify list input with multiple items."""
        dispatch = [
            {"intent_type": "status", "confidence": 0.9},
            {"intent_type": "action", "confidence": 0.8},
        ]
        test = [
            {"intent_type": "status", "confidence": 0.9},
            {"intent_type": "action", "confidence": 0.8},
        ]
        report = compare_classifications(dispatch, test)
        assert report.overall_match is True


class TestCompareClassificationsReportStructure:
    """Test ComparisonReport structure and fields."""

    def test_report_has_all_required_fields(self):
        """Verify report has all required fields."""
        dispatch = {"classifications": [{"intent_type": "status", "confidence": 0.9}]}
        test = {"classifications": [{"intent_type": "status", "confidence": 0.9}]}
        report = compare_classifications(dispatch, test)

        assert hasattr(report, "overall_match")
        assert hasattr(report, "summary")
        assert hasattr(report, "results")
        assert hasattr(report, "total_comparisons")
        assert hasattr(report, "matching_count")
        assert hasattr(report, "partial_match_count")
        assert hasattr(report, "mismatch_count")

    def test_report_summary_format(self):
        """Verify report summary format."""
        dispatch = {"classifications": [{"intent_type": "status", "confidence": 0.9}]}
        test = {"classifications": [{"intent_type": "status", "confidence": 0.85}]}
        report = compare_classifications(dispatch, test)

        assert report.summary is not None
        assert isinstance(report.summary, str)
        assert len(report.summary) > 0

    def test_report_results_structure(self):
        """Verify report results contain proper ComparisonResult objects."""
        dispatch = {"classifications": [{"intent_type": "status", "confidence": 0.9}]}
        test = {"classifications": [{"intent_type": "status", "confidence": 0.9}]}
        report = compare_classifications(dispatch, test)

        assert len(report.results) == 1
        result = report.results[0]
        assert hasattr(result, "intent_match")
        assert hasattr(result, "confidence_match")
        assert hasattr(result, "field_matches")
        assert hasattr(result, "diffs")

    def test_report_diffs_structure(self):
        """Verify report diffs contain proper FieldDiff objects."""
        dispatch = {"classifications": [{"intent_type": "status", "confidence": 0.9}]}
        test = {"classifications": [{"intent_type": "action", "confidence": 0.85}]}
        report = compare_classifications(dispatch, test)

        result = report.results[0]
        assert len(result.diffs) > 0

        for diff in result.diffs:
            assert isinstance(diff, FieldDiff)
            assert hasattr(diff, "field_name")
            assert hasattr(diff, "expected_value")
            assert hasattr(diff, "actual_value")
            assert hasattr(diff, "is_match")


class TestCompareClassificationsOverallMatch:
    """Test overall_match calculation logic."""

    def test_overall_match_true_only_if_all_match(self):
        """Verify overall_match is True only if ALL components match."""
        dispatch = {
            "classifications": [
                {"intent_type": "status", "confidence": 0.9},
                {"intent_type": "action", "confidence": 0.8},
            ]
        }
        test = {
            "classifications": [
                {"intent_type": "status", "confidence": 0.9},
                {"intent_type": "action", "confidence": 0.8},
            ]
        }
        report = compare_classifications(dispatch, test)
        assert report.overall_match is True

    def test_overall_match_false_if_any_mismatch(self):
        """Verify overall_match is False if any component mismatches."""
        dispatch = {
            "classifications": [
                {"intent_type": "status", "confidence": 0.9},
                {"intent_type": "action", "confidence": 0.8},
            ]
        }
        test = {
            "classifications": [
                {"intent_type": "status", "confidence": 0.9},
                {"intent_type": "different", "confidence": 0.8},
            ]
        }
        report = compare_classifications(dispatch, test)
        assert report.overall_match is False

    def test_overall_match_false_if_any_partial(self):
        """Verify overall_match is False if any component is partial match."""
        dispatch = {
            "classifications": [
                {"intent_type": "status", "confidence": 0.9},
                {"intent_type": "action", "confidence": 0.8},
            ]
        }
        test = {
            "classifications": [
                {"intent_type": "status", "confidence": 0.9},
                {"intent_type": "action", "confidence": 0.75},
            ]
        }
        report = compare_classifications(dispatch, test)
        assert report.overall_match is False

    def test_overall_match_false_on_count_mismatch(self):
        """Verify overall_match is False on count mismatch."""
        dispatch = {
            "classifications": [
                {"intent_type": "status", "confidence": 0.9},
                {"intent_type": "action", "confidence": 0.8},
            ]
        }
        test = {"classifications": [{"intent_type": "status", "confidence": 0.9}]}
        report = compare_classifications(dispatch, test)
        assert report.overall_match is False


class TestNormalizeInputToClassifications:
    """Test normalize_input_to_classifications helper function."""

    def test_normalize_none_returns_empty(self):
        """Verify normalizing None returns empty list."""
        result = normalize_input_to_classifications(None)
        assert result == []

    def test_normalize_empty_list_returns_empty(self):
        """Verify normalizing empty list returns empty list."""
        result = normalize_input_to_classifications([])
        assert result == []

    def test_normalize_empty_dict_returns_empty(self):
        """Verify normalizing empty dict returns empty list."""
        result = normalize_input_to_classifications({})
        assert result == []

    def test_normalize_list_of_classifications(self):
        """Verify normalizing list of classifications works."""
        input_data = [
            {"intent_type": "status", "confidence": 0.9},
            {"intent_type": "action", "confidence": 0.8},
        ]
        result = normalize_input_to_classifications(input_data)
        assert len(result) == 2
        assert result[0]["intent_type"] == "status"

    def test_normalize_dict_with_classifications_key(self):
        """Verify normalizing dict with 'classifications' key works."""
        input_data = {
            "classifications": [
                {"intent_type": "status", "confidence": 0.9}
            ]
        }
        result = normalize_input_to_classifications(input_data)
        assert len(result) == 1
        assert result[0]["intent_type"] == "status"

    def test_normalize_routed_intent_structure(self):
        """Verify normalizing RoutedIntent structure works."""
        input_data = {
            "classifications": [
                {"classification": {"intent_type": "status", "confidence": 0.9}}
            ]
        }
        result = normalize_input_to_classifications(input_data)
        assert len(result) == 1
        assert result[0]["intent_type"] == "status"


class TestFinalEdgeCasesAndDispatchIntegration:
    """Regression coverage for the final comparison edge cases."""

    def test_empty_dict_and_none_are_equivalent_empty_responses(self):
        report = compare_classifications({}, None)

        assert report.overall_match is True
        assert report.total_comparisons == 0
        assert report.summary == "Both endpoints returned no classifications"

    def test_empty_envelopes_are_equivalent_across_endpoint_shapes(self):
        report = compare_classifications(
            {"classifications": []},
            {"results": []},
        )

        assert report.overall_match is True
        assert report.total_comparisons == 0

    def test_empty_response_does_not_match_a_classification(self):
        report = compare_classifications(
            {},
            {"classifications": [{"intent_type": "status", "confidence": 0.9}]},
        )

        assert report.overall_match is False
        assert report.mismatch_count == 1
        assert "Count mismatch" in report.summary

    @pytest.mark.parametrize("invalid_result", ["not a response", 42, ["not a classification"]])
    def test_invalid_top_level_types_are_reported(self, invalid_result):
        report = compare_classifications(
            invalid_result,
            {"classifications": []},
        )

        assert report.overall_match is False
        assert report.mismatch_count == 1
        assert any(diff.field_name == "top_level_type" for diff in report.detailed_diffs)
        assert "Invalid comparison input" in report.summary

    def test_non_list_classifications_envelope_is_invalid(self):
        report = compare_classifications(
            {"classifications": {"intent_type": "status"}},
            {"classifications": []},
        )

        assert report.overall_match is False
        assert report.detailed_diffs[0].field_name == "top_level_type"

    def test_empty_structured_dict_does_not_match_none(self):
        dispatch = {
            "classifications": [{
                "intent_type": "status",
                "confidence": 0.9,
                "structured_result": {},
            }]
        }
        test = {
            "classifications": [{
                "intent_type": "status",
                "confidence": 0.9,
                "structured_result": None,
            }]
        }

        report = compare_classifications(dispatch, test)

        assert report.overall_match is False
        assert report.partial_match_count == 1
        assert report.results[0].field_matches["structured_result"] is False

    @pytest.mark.parametrize(
        ("dispatch_value", "test_value"),
        [
            ("lookup", "status"),
            (0.9, 0.8),
            ({"status": "running"}, {"status": "failed"}),
        ],
    )
    def test_each_core_or_structured_component_can_fail_overall_match(
        self, dispatch_value, test_value
    ):
        dispatch = {
            "classifications": [{
                "intent_type": "status",
                "confidence": 0.9,
                "structured_result": {"status": "running"},
            }]
        }
        test = {
            "classifications": [{
                "intent_type": "status",
                "confidence": 0.9,
                "structured_result": {"status": "running"},
            }]
        }
        if isinstance(dispatch_value, str):
            dispatch["classifications"][0]["intent_type"] = dispatch_value
        elif isinstance(dispatch_value, (int, float)):
            dispatch["classifications"][0]["confidence"] = dispatch_value
            test["classifications"][0]["confidence"] = test_value
        else:
            dispatch["classifications"][0]["structured_result"] = dispatch_value
            test["classifications"][0]["structured_result"] = test_value

        report = compare_classifications(dispatch, test)

        assert report.overall_match is False

    def test_full_dispatch_results_envelope_matches_test_classifications(self):
        dispatch_result = {
            "status": "completed",
            "utterance_id": "utt-123",
            "session_id": "session-123",
            "intent_count": 1,
            "intent_ids": ["intent-123"],
            "message": "Dispatch completed successfully",
            "results": [{
                "intent_id": "intent-123",
                "intent_type": "lookup",
                "project_slug": "aide-de-camp",
                "confidence": 0.94,
                "utterance_fragment": "show deployment status",
                "reasoning": "The user requested current deployment state.",
                "urgency": "normal",
                "lookup_kind": "status",
                "structured_result": {
                    "deployment": "api",
                    "status": "running",
                    "entities": ["api", "production"],
                },
            }],
        }
        test_result = {
            "classifications": [{
                "intent_type": "lookup",
                "project_slug": "aide-de-camp",
                "confidence": 0.945,
                "utterance_fragment": "show deployment status",
                "reasoning": "The user requested current deployment state.",
                "urgency": "normal",
                "lookup_kind": "status",
                "structured_result": {
                    "deployment": "api",
                    "status": "running",
                    "entities": ["production", "api"],
                },
            }]
        }

        report = compare_classifications(dispatch_result, test_result)

        assert report.overall_match is True
        assert report.total_comparisons == 1
        assert report.matching_count == 1
        assert report.partial_match_count == 0
        assert report.mismatch_count == 0


class TestSafeGet:
    """Test safe_get helper function."""

    def test_safe_get_with_none_data(self):
        """Verify safe_get with None data returns default."""
        result = safe_get(None, "field", "default")
        assert result == "default"

    def test_safe_get_with_missing_field(self):
        """Verify safe_get with missing field returns default."""
        result = safe_get({"other": "value"}, "field", "default")
        assert result == "default"

    def test_safe_get_with_none_value(self):
        """Verify safe_get with None value returns default."""
        result = safe_get({"field": None}, "field", "default")
        assert result == "default"

    def test_safe_get_with_valid_value(self):
        """Verify safe_get with valid value returns value."""
        result = safe_get({"field": "value"}, "field", "default")
        assert result == "value"


class TestCompareIntentTypes:
    """Test compare_intent_types function edge cases."""

    def test_compare_intent_types_both_none(self):
        """Verify both None returns False."""
        assert compare_intent_types(None, None) is False

    def test_compare_intent_types_empty_strings(self):
        """Verify empty strings return False."""
        assert compare_intent_types("", "") is False
        assert compare_intent_types("", "status") is False

    def test_compare_intent_types_enum_extraction(self):
        """Verify enum value extraction works."""
        class TestIntent(Enum):
            STATUS = "status"

        assert compare_intent_types(TestIntent.STATUS, "status") is True
        assert compare_intent_types("status", TestIntent.STATUS) is True


class TestCompareConfidenceScores:
    """Test compare_confidence_scores function edge cases."""

    def test_compare_confidence_both_none(self):
        """Verify both None returns False."""
        assert compare_confidence_scores(None, None) is False

    def test_compare_confidence_string_conversion(self):
        """Verify string to float conversion works."""
        assert compare_confidence_scores("0.9", "0.9") is True

    def test_compare_confidence_invalid_string(self):
        """Verify invalid string returns False."""
        assert compare_confidence_scores("invalid", 0.9) is False

    def test_compare_confidence_nan(self):
        """Verify NaN handling returns False."""
        assert compare_confidence_scores(float('nan'), 0.9) is False

    def test_compare_confidence_infinity(self):
        """Verify infinity handling."""
        assert compare_confidence_scores(float('inf'), float('inf')) is True
        assert compare_confidence_scores(float('inf'), 1.0) is False
