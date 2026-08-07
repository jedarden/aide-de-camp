"""
Unit tests for basic classification comparison function.

Tests the compare_classifications function's handling of fundamental
edge cases: None/empty inputs, intent type comparison, and confidence
comparison with configurable tolerance.

Acceptance criteria from bead adc-2qjc1d:
- ComparisonReport model defined with: overall_match: bool, summary: str, detailed_diffs: list[FieldDiff]
- compare_classifications() function created with correct signature
- Returns ComparisonReport with overall_match=False and summary explaining the issue when either input is None/empty
- Function passes basic type checking
- Unit tests for None/empty input cases

Acceptance criteria from bead adc-25atu4:
- Intent type comparison: exact string match, FieldDiff created on mismatch
- Confidence comparison: within tolerance (default ±0.1), FieldDiff with both values on mismatch
- Early return with overall_match=False when intent or confidence mismatch detected
- FieldDiff objects include field_name, expected_value, actual_value for both fields
- Unit tests covering: exact intent match, intent mismatch, confidence within tolerance,
  confidence outside tolerance, both intent and confidence mismatch
"""

import pytest

from src.validation.classification_comparison import (
    compare_classifications,
    ComparisonReport,
)
from src.validation.comparison import FieldDiff


class TestComparisonReportModel:
    """Test the ComparisonReport data model structure."""

    def test_comparison_report_has_required_fields(self):
        """Verify ComparisonReport has all required fields."""
        report = ComparisonReport(
            overall_match=True,
            summary="Test summary",
            detailed_diffs=[]
        )
        assert hasattr(report, 'overall_match')
        assert hasattr(report, 'summary')
        assert hasattr(report, 'detailed_diffs')
        assert report.overall_match is True
        assert report.summary == "Test summary"
        assert report.detailed_diffs == []

    def test_comparison_report_with_diffs(self):
        """Verify ComparisonReport can store field differences."""
        diffs = [
            FieldDiff("intent_type", "status", "action", False),
            FieldDiff("confidence", 0.9, 0.85, False),
        ]
        report = ComparisonReport(
            overall_match=False,
            summary="2 differences found",
            detailed_diffs=diffs
        )
        assert len(report.detailed_diffs) == 2
        assert report.detailed_diffs[0].field_name == "intent_type"
        assert report.detailed_diffs[1].field_name == "confidence"

    def test_comparison_report_default_empty_diffs(self):
        """Verify ComparisonReport defaults to empty diff list."""
        report = ComparisonReport(
            overall_match=True,
            summary="No differences"
        )
        assert report.detailed_diffs == []


class TestNoneInputHandling:
    """Test handling of None inputs."""

    def test_both_inputs_none(self):
        """Verify both inputs being None returns appropriate report."""
        report = compare_classifications(None, None)

        assert isinstance(report, ComparisonReport)
        assert report.overall_match is False
        assert "None" in report.summary
        assert len(report.detailed_diffs) == 1
        assert report.detailed_diffs[0].field_name == "input_validation"
        assert report.detailed_diffs[0].is_match is False

    def test_dispatch_none_test_valid(self):
        """Verify dispatch None and valid test returns appropriate report."""
        report = compare_classifications(
            None,
            {"classifications": [{"intent_type": "status"}]}
        )

        assert report.overall_match is False
        assert "None" in report.summary
        assert "dispatch_result=None" in report.summary
        assert len(report.detailed_diffs) == 1

    def test_dispatch_valid_test_none(self):
        """Verify valid dispatch and test None returns appropriate report."""
        report = compare_classifications(
            {"classifications": [{"intent_type": "status"}]},
            None
        )

        assert report.overall_match is False
        assert "None" in report.summary
        assert "test_result=None" in report.summary
        assert len(report.detailed_diffs) == 1


class TestEmptyInputHandling:
    """Test handling of empty dict/list inputs."""

    def test_both_empty_dicts(self):
        """Verify both inputs being empty dicts returns appropriate report."""
        report = compare_classifications({}, {})

        assert isinstance(report, ComparisonReport)
        assert report.overall_match is False
        assert "empty" in report.summary.lower()
        assert "dispatch" in report.summary.lower()
        assert len(report.detailed_diffs) == 1
        assert report.detailed_diffs[0].field_name == "dispatch_result"

    def test_dispatch_empty_dict_test_valid(self):
        """Verify empty dispatch dict and valid test returns appropriate report."""
        report = compare_classifications(
            {},
            {"classifications": [{"intent_type": "status"}]}
        )

        assert report.overall_match is False
        assert "empty" in report.summary.lower()
        assert "dispatch" in report.summary.lower()
        assert len(report.detailed_diffs) == 1

    def test_dispatch_valid_test_empty_dict(self):
        """Verify valid dispatch and empty test dict returns appropriate report."""
        report = compare_classifications(
            {"classifications": [{"intent_type": "status"}]},
            {}
        )

        assert report.overall_match is False
        assert "empty" in report.summary.lower()
        assert "test" in report.summary.lower()
        assert len(report.detailed_diffs) == 1

    def test_both_empty_lists(self):
        """Verify both inputs being empty lists returns appropriate report."""
        report = compare_classifications([], [])

        assert isinstance(report, ComparisonReport)
        assert report.overall_match is False
        assert "empty" in report.summary.lower()
        assert "dispatch" in report.summary.lower()
        assert len(report.detailed_diffs) == 1

    def test_dispatch_empty_list_test_valid(self):
        """Verify empty dispatch list and valid test returns appropriate report."""
        report = compare_classifications(
            [],
            [{"intent_type": "status"}]
        )

        assert report.overall_match is False
        assert "empty" in report.summary.lower()
        assert "dispatch" in report.summary.lower()
        assert len(report.detailed_diffs) == 1

    def test_dispatch_valid_test_empty_list(self):
        """Verify valid dispatch and empty test list returns appropriate report."""
        report = compare_classifications(
            [{"intent_type": "status"}],
            []
        )

        assert report.overall_match is False
        assert "empty" in report.summary.lower()
        assert "test" in report.summary.lower()
        assert len(report.detailed_diffs) == 1


class TestEmptyClassificationsListHandling:
    """Test handling of empty 'classifications' lists in dicts."""

    def test_dispatch_empty_classifications_list(self):
        """Verify empty classifications list in dispatch returns appropriate report."""
        report = compare_classifications(
            {"classifications": []},
            {"classifications": [{"intent_type": "status"}]}
        )

        assert report.overall_match is False
        assert "empty" in report.summary.lower()
        assert "dispatch" in report.summary.lower()
        assert len(report.detailed_diffs) == 1
        assert report.detailed_diffs[0].field_name == "classifications"

    def test_test_empty_classifications_list(self):
        """Verify empty classifications list in test returns appropriate report."""
        report = compare_classifications(
            {"classifications": [{"intent_type": "status"}]},
            {"classifications": []}
        )

        assert report.overall_match is False
        assert "empty" in report.summary.lower()
        assert "test" in report.summary.lower()
        assert len(report.detailed_diffs) == 1

    def test_both_empty_classifications_lists(self):
        """Verify both having empty classifications lists returns appropriate report."""
        report = compare_classifications(
            {"classifications": []},
            {"classifications": []}
        )

        assert report.overall_match is False
        assert "empty" in report.summary.lower()
        assert len(report.detailed_diffs) == 1


class TestFunctionSignature:
    """Test function signature and type checking."""

    def test_function_accepts_none_and_dict(self):
        """Verify function accepts None and dict inputs without error."""
        # Should not raise any exceptions
        report = compare_classifications(None, {})
        assert isinstance(report, ComparisonReport)

        report = compare_classifications({}, None)
        assert isinstance(report, ComparisonReport)

    def test_function_accepts_lists(self):
        """Verify function accepts list inputs without error."""
        # Should not raise any exceptions
        report = compare_classifications([], [])
        assert isinstance(report, ComparisonReport)

    def test_function_returns_comparison_report(self):
        """Verify function always returns ComparisonReport instance."""
        # Various input combinations
        test_cases = [
            (None, None),
            (None, {}),
            ({}, None),
            ([], []),
            ({}, {"classifications": []}),
            ({"classifications": []}, {"classifications": []}),
        ]

        for dispatch, test in test_cases:
            report = compare_classifications(dispatch, test)
            assert isinstance(report, ComparisonReport), \
                f"Expected ComparisonReport for inputs ({dispatch}, {test}), got {type(report)}"

    def test_function_has_correct_signature(self):
        """Verify function has expected signature."""
        import inspect

        sig = inspect.signature(compare_classifications)
        params = list(sig.parameters.keys())

        assert 'dispatch_result' in params
        assert 'test_result' in params
        assert 'confidence_tolerance' in params
        assert len(params) == 3  # dispatch_result, test_result, confidence_tolerance


class TestFieldDiffIntegration:
    """Test that FieldDiff model is properly integrated."""

    def test_field_diff_structure(self):
        """Verify FieldDiff has required fields from existing model."""
        diff = FieldDiff(
            field_name="test_field",
            expected_value="expected",
            actual_value="actual",
            is_match=False
        )

        assert diff.field_name == "test_field"
        assert diff.expected_value == "expected"
        assert diff.actual_value == "actual"
        assert diff.is_match is False

    def test_field_diff_in_report(self):
        """Verify FieldDiff objects are properly stored in report."""
        diffs = [
            FieldDiff("field1", "val1", "val2", False),
            FieldDiff("field2", "val3", "val4", True),
        ]

        report = ComparisonReport(
            overall_match=False,
            summary="Test",
            detailed_diffs=diffs
        )

        assert len(report.detailed_diffs) == 2
        assert report.detailed_diffs[0].field_name == "field1"
        assert report.detailed_diffs[1].is_match is True


class TestBasicNonEmptyInputs:
    """Test basic behavior with non-empty inputs."""

    def test_non_empty_basic_valid_inputs(self):
        """Verify basic handling of non-empty valid inputs."""
        # Updated test: intent type match with missing confidence in both should pass
        report = compare_classifications(
            {"classifications": [{"intent_type": "status"}]},
            {"classifications": [{"intent_type": "status"}]}
        )

        assert isinstance(report, ComparisonReport)
        # Updated behavior: missing confidence in both results is OK
        assert report.overall_match is True
        assert "Perfect match" in report.summary
        assert report.detailed_diffs == []


class TestSummaryMessages:
    """Test that summary messages are informative."""

    def test_none_input_summary_is_informative(self):
        """Verify summary for None inputs explains the issue."""
        report = compare_classifications(None, None)

        summary = report.summary.lower()
        assert "none" in summary
        assert ("dispatch" in summary or "input" in summary)
        assert ("test" in summary or "input" in summary)

    def test_empty_input_summary_is_informative(self):
        """Verify summary for empty inputs explains the issue."""
        report = compare_classifications({}, {})

        summary = report.summary.lower()
        assert "empty" in summary
        assert "dictionary" in summary or "dict" in summary

    def test_empty_list_summary_is_informative(self):
        """Verify summary for empty lists explains the issue."""
        report = compare_classifications([], [])

        summary = report.summary.lower()
        assert "empty" in summary
        assert "list" in summary


class TestOverallMatchLogic:
    """Test overall_match logic for edge cases."""

    def test_overall_match_false_for_none_inputs(self):
        """Verify overall_match is False for None inputs."""
        test_cases = [
            (None, None),
            (None, {}),
            ({}, None),
            (None, []),
            ([], None),
        ]

        for dispatch, test in test_cases:
            report = compare_classifications(dispatch, test)
            assert report.overall_match is False, \
                f"Expected overall_match=False for ({dispatch}, {test})"

    def test_overall_match_false_for_empty_inputs(self):
        """Verify overall_match is False for empty inputs."""
        test_cases = [
            ({}, {}),
            ([], []),
            ({}, {"classifications": []}),
            ({"classifications": []}, {}),
            ({"classifications": []}, {"classifications": []}),
        ]

        for dispatch, test in test_cases:
            report = compare_classifications(dispatch, test)
            assert report.overall_match is False, \
                f"Expected overall_match=False for ({dispatch}, {test})"


class TestIntentTypeComparison:
    """Test intent type comparison logic."""

    def test_exact_intent_match_returns_true(self):
        """Verify exact intent type match returns overall_match=True."""
        dispatch = {"classifications": [{"intent_type": "status", "confidence": 0.9}]}
        test = {"classifications": [{"intent_type": "status", "confidence": 0.9}]}

        report = compare_classifications(dispatch, test)

        assert report.overall_match is True
        assert "Perfect match" in report.summary
        assert len(report.detailed_diffs) == 0

    def test_intent_mismatch_creates_field_diff(self):
        """Verify intent type mismatch creates FieldDiff and returns False."""
        dispatch = {"classifications": [{"intent_type": "status", "confidence": 0.9}]}
        test = {"classifications": [{"intent_type": "action", "confidence": 0.9}]}

        report = compare_classifications(dispatch, test)

        assert report.overall_match is False
        assert "Intent type mismatch" in report.summary
        assert len(report.detailed_diffs) == 1

        diff = report.detailed_diffs[0]
        assert diff.field_name == "classification_0_intent_type"
        assert diff.expected_value == "status"
        assert diff.actual_value == "action"
        assert diff.is_match is False

    def test_intent_none_in_dispatch_creates_field_diff(self):
        """Verify None intent in dispatch creates FieldDiff and returns False."""
        dispatch = {"classifications": [{"intent_type": None, "confidence": 0.9}]}
        test = {"classifications": [{"intent_type": "status", "confidence": 0.9}]}

        report = compare_classifications(dispatch, test)

        assert report.overall_match is False
        assert "Intent type mismatch" in report.summary
        assert len(report.detailed_diffs) == 1

        diff = report.detailed_diffs[0]
        assert diff.field_name == "classification_0_intent_type"
        assert diff.expected_value is None
        assert diff.actual_value == "status"
        assert diff.is_match is False

    def test_intent_none_in_test_creates_field_diff(self):
        """Verify None intent in test creates FieldDiff and returns False."""
        dispatch = {"classifications": [{"intent_type": "status", "confidence": 0.9}]}
        test = {"classifications": [{"intent_type": None, "confidence": 0.9}]}

        report = compare_classifications(dispatch, test)

        assert report.overall_match is False
        assert "Intent type mismatch" in report.summary
        assert len(report.detailed_diffs) == 1

        diff = report.detailed_diffs[0]
        assert diff.field_name == "classification_0_intent_type"
        assert diff.expected_value == "status"
        assert diff.actual_value is None
        assert diff.is_match is False

    def test_intent_none_in_both_creates_field_diff(self):
        """Verify None intent in both creates FieldDiff and returns False."""
        dispatch = {"classifications": [{"intent_type": None, "confidence": 0.9}]}
        test = {"classifications": [{"intent_type": None, "confidence": 0.9}]}

        report = compare_classifications(dispatch, test)

        assert report.overall_match is False
        assert "Intent type mismatch" in report.summary
        assert "None values never match" in report.summary
        assert len(report.detailed_diffs) == 1

        diff = report.detailed_diffs[0]
        assert diff.field_name == "classification_0_intent_type"
        assert diff.expected_value is None
        assert diff.actual_value is None
        assert diff.is_match is False


class TestConfidenceComparison:
    """Test confidence comparison logic with configurable tolerance."""

    def test_exact_confidence_match_returns_true(self):
        """Verify exact confidence match returns overall_match=True."""
        dispatch = {"classifications": [{"intent_type": "status", "confidence": 0.9}]}
        test = {"classifications": [{"intent_type": "status", "confidence": 0.9}]}

        report = compare_classifications(dispatch, test)

        assert report.overall_match is True
        assert "Perfect match" in report.summary
        assert len(report.detailed_diffs) == 0

    def test_confidence_within_default_tolerance(self):
        """Verify confidence within default tolerance (±0.1) returns True."""
        dispatch = {"classifications": [{"intent_type": "status", "confidence": 0.9}]}
        test = {"classifications": [{"intent_type": "status", "confidence": 0.85}]}  # 0.05 difference

        report = compare_classifications(dispatch, test)

        assert report.overall_match is True
        assert "Perfect match" in report.summary
        assert len(report.detailed_diffs) == 0

    def test_confidence_at_tolerance_boundary(self):
        """Verify confidence at exactly tolerance boundary returns True."""
        dispatch = {"classifications": [{"intent_type": "status", "confidence": 0.9}]}
        test = {"classifications": [{"intent_type": "status", "confidence": 0.8}]}  # Exactly 0.1 difference

        report = compare_classifications(dispatch, test)

        assert report.overall_match is True
        assert len(report.detailed_diffs) == 0

    def test_confidence_exceeds_tolerance(self):
        """Verify confidence exceeding tolerance creates FieldDiff and returns False."""
        dispatch = {"classifications": [{"intent_type": "status", "confidence": 0.9}]}
        test = {"classifications": [{"intent_type": "status", "confidence": 0.75}]}  # 0.15 difference

        report = compare_classifications(dispatch, test)

        assert report.overall_match is False
        assert "Confidence mismatch" in report.summary
        assert len(report.detailed_diffs) == 1

        diff = report.detailed_diffs[0]
        assert diff.field_name == "classification_0_confidence"
        assert diff.expected_value == 0.9
        assert diff.actual_value == 0.75
        assert diff.is_match is False

    def test_confidence_custom_tolerance(self):
        """Verify custom tolerance parameter works correctly."""
        dispatch = {"classifications": [{"intent_type": "status", "confidence": 0.9}]}
        test = {"classifications": [{"intent_type": "status", "confidence": 0.75}]}  # 0.15 difference

        # Should fail with default tolerance (0.1)
        report_default = compare_classifications(dispatch, test)
        assert report_default.overall_match is False

        # Should pass with custom tolerance (0.2)
        report_custom = compare_classifications(dispatch, test, confidence_tolerance=0.2)
        assert report_custom.overall_match is True
        assert "Perfect match" in report_custom.summary

    def test_confidence_none_in_dispatch_creates_field_diff(self):
        """Verify None confidence in dispatch creates FieldDiff and returns False."""
        dispatch = {"classifications": [{"intent_type": "status", "confidence": None}]}
        test = {"classifications": [{"intent_type": "status", "confidence": 0.9}]}

        report = compare_classifications(dispatch, test)

        assert report.overall_match is False
        assert "Confidence mismatch" in report.summary
        assert "None values never match" in report.summary
        assert len(report.detailed_diffs) == 1

        diff = report.detailed_diffs[0]
        assert diff.field_name == "classification_0_confidence"
        assert diff.expected_value is None
        assert diff.actual_value == 0.9
        assert diff.is_match is False

    def test_confidence_none_in_test_creates_field_diff(self):
        """Verify None confidence in test creates FieldDiff and returns False."""
        dispatch = {"classifications": [{"intent_type": "status", "confidence": 0.9}]}
        test = {"classifications": [{"intent_type": "status", "confidence": None}]}

        report = compare_classifications(dispatch, test)

        assert report.overall_match is False
        assert "Confidence mismatch" in report.summary
        assert len(report.detailed_diffs) == 1

        diff = report.detailed_diffs[0]
        assert diff.field_name == "classification_0_confidence"
        assert diff.expected_value == 0.9
        assert diff.actual_value is None
        assert diff.is_match is False

    def test_confidence_type_mismatch(self):
        """Verify non-numeric confidence types create FieldDiff and return False."""
        dispatch = {"classifications": [{"intent_type": "status", "confidence": "high"}]}
        test = {"classifications": [{"intent_type": "status", "confidence": 0.9}]}

        report = compare_classifications(dispatch, test)

        assert report.overall_match is False
        assert "Confidence type mismatch" in report.summary
        assert len(report.detailed_diffs) == 1

        diff = report.detailed_diffs[0]
        assert diff.field_name == "classification_0_confidence"
        assert "numeric" in str(diff.expected_value)
        assert "numeric" in str(diff.actual_value)
        assert diff.is_match is False


class TestEarlyReturnLogic:
    """Test early return behavior on intent/confidence mismatch."""

    def test_early_return_on_intent_mismatch(self):
        """Verify function returns immediately when intent type mismatches."""
        # Add extra fields after intent to test early return
        dispatch = {"classifications": [{"intent_type": "status", "confidence": 0.9}]}
        test = {"classifications": [{"intent_type": "action", "confidence": 0.9}]}

        report = compare_classifications(dispatch, test)

        # Should return immediately with only intent diff, not confidence diff
        assert report.overall_match is False
        assert "Intent type mismatch" in report.summary
        assert len(report.detailed_diffs) == 1
        assert report.detailed_diffs[0].field_name == "classification_0_intent_type"

    def test_early_return_on_confidence_mismatch(self):
        """Verify function returns immediately when confidence mismatches."""
        dispatch = {"classifications": [{"intent_type": "status", "confidence": 0.9}]}
        test = {"classifications": [{"intent_type": "status", "confidence": 0.7}]}

        report = compare_classifications(dispatch, test)

        # Should return immediately with confidence diff
        assert report.overall_match is False
        assert "Confidence mismatch" in report.summary
        assert len(report.detailed_diffs) == 1
        assert report.detailed_diffs[0].field_name == "classification_0_confidence"

    def test_no_early_return_on_match(self):
        """Verify function continues when all fields match."""
        dispatch = {"classifications": [{"intent_type": "status", "confidence": 0.9}]}
        test = {"classifications": [{"intent_type": "status", "confidence": 0.9}]}

        report = compare_classifications(dispatch, test)

        # Should complete with no diffs
        assert report.overall_match is True
        assert len(report.detailed_diffs) == 0


class TestFieldDiffStructure:
    """Test FieldDiff object structure for intent and confidence comparisons."""

    def test_intent_field_diff_structure(self):
        """Verify FieldDiff has correct structure for intent mismatch."""
        dispatch = {"classifications": [{"intent_type": "status", "confidence": 0.9}]}
        test = {"classifications": [{"intent_type": "action", "confidence": 0.9}]}

        report = compare_classifications(dispatch, test)
        diff = report.detailed_diffs[0]

        assert hasattr(diff, 'field_name')
        assert hasattr(diff, 'expected_value')
        assert hasattr(diff, 'actual_value')
        assert hasattr(diff, 'is_match')

        assert diff.field_name == "classification_0_intent_type"
        assert diff.expected_value == "status"
        assert diff.actual_value == "action"
        assert diff.is_match is False

    def test_confidence_field_diff_structure(self):
        """Verify FieldDiff has correct structure for confidence mismatch."""
        dispatch = {"classifications": [{"intent_type": "status", "confidence": 0.9}]}
        test = {"classifications": [{"intent_type": "status", "confidence": 0.7}]}

        report = compare_classifications(dispatch, test)
        diff = report.detailed_diffs[0]

        assert diff.field_name == "classification_0_confidence"
        assert diff.expected_value == 0.9
        assert diff.actual_value == 0.7
        assert diff.is_match is False


class TestMultipleClassifications:
    """Test behavior with multiple classifications in results."""

    def test_multiple_classifications_all_match(self):
        """Verify multiple classifications all match correctly."""
        dispatch = {"classifications": [
            {"intent_type": "status", "confidence": 0.9},
            {"intent_type": "action", "confidence": 0.8}
        ]}
        test = {"classifications": [
            {"intent_type": "status", "confidence": 0.9},
            {"intent_type": "action", "confidence": 0.8}
        ]}

        report = compare_classifications(dispatch, test)

        assert report.overall_match is True
        assert "2 classifications matched" in report.summary
        assert len(report.detailed_diffs) == 0

    def test_multiple_classifications_first_mismatch(self):
        """Verify early return on first classification mismatch."""
        dispatch = {"classifications": [
            {"intent_type": "status", "confidence": 0.9},
            {"intent_type": "action", "confidence": 0.8}
        ]}
        test = {"classifications": [
            {"intent_type": "wrong", "confidence": 0.9},
            {"intent_type": "action", "confidence": 0.8}
        ]}

        report = compare_classifications(dispatch, test)

        # Should return immediately after first classification
        assert report.overall_match is False
        assert len(report.detailed_diffs) == 1
        assert report.detailed_diffs[0].field_name == "classification_0_intent_type"

    def test_multiple_classifications_second_mismatch(self):
        """Verify detection of mismatch in second classification."""
        dispatch = {"classifications": [
            {"intent_type": "status", "confidence": 0.9},
            {"intent_type": "action", "confidence": 0.8}
        ]}
        test = {"classifications": [
            {"intent_type": "status", "confidence": 0.9},
            {"intent_type": "wrong", "confidence": 0.8}
        ]}

        report = compare_classifications(dispatch, test)

        # First matches, second mismatches
        assert report.overall_match is False
        assert len(report.detailed_diffs) == 1
        assert report.detailed_diffs[0].field_name == "classification_1_intent_type"


class TestEnumHandling:
    """Test handling of Enum values in intent types."""

    def test_intent_enum_values_extracted(self):
        """Verify Enum values are extracted to strings for comparison."""
        from enum import Enum

        class MockIntent(Enum):
            STATUS = "status"
            ACTION = "action"

        dispatch = {"classifications": [{"intent_type": MockIntent.STATUS, "confidence": 0.9}]}
        test = {"classifications": [{"intent_type": "status", "confidence": 0.9}]}

        report = compare_classifications(dispatch, test)

        # Should extract Enum value "status" and match
        assert report.overall_match is True
        assert len(report.detailed_diffs) == 0

    def test_intent_enum_mismatch(self):
        """Verify Enum value mismatch is detected."""
        from enum import Enum

        class MockIntent(Enum):
            STATUS = "status"
            ACTION = "action"

        dispatch = {"classifications": [{"intent_type": MockIntent.STATUS, "confidence": 0.9}]}
        test = {"classifications": [{"intent_type": MockIntent.ACTION, "confidence": 0.9}]}

        report = compare_classifications(dispatch, test)

        # Should detect mismatch between "status" and "action"
        assert report.overall_match is False
        assert len(report.detailed_diffs) == 1
        assert report.detailed_diffs[0].expected_value == "status"
        assert report.detailed_diffs[0].actual_value == "action"


class TestCountMismatch:
    """Test handling of classification count mismatches."""

    def test_count_mismatch_returns_early(self):
        """Verify count mismatch is detected before field comparisons."""
        dispatch = {"classifications": [
            {"intent_type": "status", "confidence": 0.9}
        ]}
        test = {"classifications": [
            {"intent_type": "status", "confidence": 0.9},
            {"intent_type": "action", "confidence": 0.8}
        ]}

        report = compare_classifications(dispatch, test)

        assert report.overall_match is False
        assert "Classification count mismatch" in report.summary
        assert "dispatch has 1" in report.summary
        assert "test has 2" in report.summary
        assert len(report.detailed_diffs) == 1

        diff = report.detailed_diffs[0]
        assert diff.field_name == "classification_count"
        assert diff.expected_value == 1
        assert diff.actual_value == 2


class TestListInputFormat:
    """Test handling of list inputs (direct classification lists)."""

    def test_list_inputs_both_match(self):
        """Verify list inputs work correctly when both match."""
        dispatch = [{"intent_type": "status", "confidence": 0.9}]
        test = [{"intent_type": "status", "confidence": 0.9}]

        report = compare_classifications(dispatch, test)

        assert report.overall_match is True
        assert "Perfect match" in report.summary
        assert len(report.detailed_diffs) == 0

    def test_list_inputs_intent_mismatch(self):
        """Verify list inputs detect intent mismatch."""
        dispatch = [{"intent_type": "status", "confidence": 0.9}]
        test = [{"intent_type": "action", "confidence": 0.9}]

        report = compare_classifications(dispatch, test)

        assert report.overall_match is False
        assert "Intent type mismatch" in report.summary
        assert len(report.detailed_diffs) == 1

    def test_list_inputs_confidence_mismatch(self):
        """Verify list inputs detect confidence mismatch."""
        dispatch = [{"intent_type": "status", "confidence": 0.9}]
        test = [{"intent_type": "status", "confidence": 0.7}]

        report = compare_classifications(dispatch, test)

        assert report.overall_match is False
        assert "Confidence mismatch" in report.summary
        assert len(report.detailed_diffs) == 1
