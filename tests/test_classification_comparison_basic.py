"""
Unit tests for basic classification comparison function.

Tests the compare_classifications function's handling of fundamental
edge cases: None/empty inputs. More comprehensive tests will be added
as comparison logic is expanded.

Acceptance criteria from bead adc-2qjc1d:
- ComparisonReport model defined with: overall_match: bool, summary: str, detailed_diffs: list[FieldDiff]
- compare_classifications() function created with correct signature
- Returns ComparisonReport with overall_match=False and summary explaining the issue when either input is None/empty
- Function passes basic type checking
- Unit tests for None/empty input cases
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
        assert len(params) == 2  # Should only have these two parameters


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
        # For the foundational version, this should return a basic success report
        # Detailed comparison logic will be added in subsequent iterations
        report = compare_classifications(
            {"classifications": [{"intent_type": "status"}]},
            {"classifications": [{"intent_type": "status"}]}
        )

        assert isinstance(report, ComparisonReport)
        # Foundational version returns True for valid structure
        assert report.overall_match is True
        assert "validated" in report.summary.lower() or "ready" in report.summary.lower()
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
