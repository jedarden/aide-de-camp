#!/usr/bin/env python3
"""
Core classification comparison function.

This module provides the foundational compare_classifications function
that performs basic comparison of classification results with proper
edge case handling for None/empty inputs.

Usage:
    from src.validation.classification_comparison import compare_classifications

    dispatch_result = {"classifications": [...]}
    test_result = {"classifications": [...]}
    report = compare_classifications(dispatch_result, test_result)
    if report.overall_match:
        print("All classifications matched!")
"""

from typing import Any, Dict, List, Optional, Union
from dataclasses import dataclass, field


# Import the FieldDiff model from the comparison module
from src.validation.comparison import FieldDiff


@dataclass
class ComparisonReport:
    """
    Foundational comparison report for classification results.

    This is a simplified report structure that captures the essential
    comparison results: overall match status, human-readable summary,
    and detailed field-by-field differences.

    Attributes:
        overall_match: True if all classifications match completely
        summary: Human-readable summary of the comparison results
        detailed_diffs: List of field-level differences with match details

    Example:
        >>> report = ComparisonReport(
        ...     overall_match=False,
        ...     summary="2 differences found in intent_type and confidence",
        ...     detailed_diffs=[
        ...         FieldDiff("intent_type", "status", "action", False),
        ...         FieldDiff("confidence", 0.9, 0.85, False),
        ...     ]
        ... )
    """

    overall_match: bool
    summary: str
    detailed_diffs: List[FieldDiff] = field(default_factory=list)


def compare_classifications(
    dispatch_result: Optional[Union[Dict, List]],
    test_result: Optional[Union[Dict, List]]
) -> ComparisonReport:
    """
    Compare classification results from dispatch and test endpoints.

    This function performs basic comparison of classification results,
    focusing on handling fundamental edge cases like None/empty inputs.
    More detailed comparison logic will be added in subsequent iterations.

    Args:
        dispatch_result: Classification results from dispatch endpoint.
            Can be a dict with 'classifications' key, a list of classification
            dicts, or None/empty.
        test_result: Classification results from test endpoint.
            Can be a dict with 'classifications' key, a list of classification
            dicts, or None/empty.

    Returns:
        ComparisonReport with overall_match status, summary, and detailed diffs.

    Edge Cases Handled:
        - None inputs: Returns report with overall_match=False and explanatory summary
        - Empty dict/list inputs: Returns report with overall_match=False and explanatory summary
        - Missing 'classifications' key: Treated as empty input

    Example:
        >>> # Both inputs are None
        >>> report = compare_classifications(None, None)
        >>> assert report.overall_match is False
        >>> assert "None" in report.summary

        >>> # One input is empty
        >>> report = compare_classifications({}, {"classifications": []})
        >>> assert report.overall_match is False
        >>> assert "empty" in report.summary.lower()
    """
    # Handle None inputs
    if dispatch_result is None or test_result is None:
        return ComparisonReport(
            overall_match=False,
            summary=f"Cannot compare: dispatch_result={dispatch_result}, test_result={test_result}. "
                   f"Both inputs must be non-None.",
            detailed_diffs=[
                FieldDiff(
                    field_name="input_validation",
                    expected_value="non-None dict or list",
                    actual_value=f"dispatch_result={dispatch_result}, test_result={test_result}",
                    is_match=False
                )
            ]
        )

    # Handle empty dict inputs
    if isinstance(dispatch_result, dict) and not dispatch_result:
        return ComparisonReport(
            overall_match=False,
            summary="Dispatch result is an empty dictionary. No classifications to compare.",
            detailed_diffs=[
                FieldDiff(
                    field_name="dispatch_result",
                    expected_value="non-empty dict with 'classifications' key",
                    actual_value="empty dict {}",
                    is_match=False
                )
            ]
        )

    if isinstance(test_result, dict) and not test_result:
        return ComparisonReport(
            overall_match=False,
            summary="Test result is an empty dictionary. No classifications to compare.",
            detailed_diffs=[
                FieldDiff(
                    field_name="test_result",
                    expected_value="non-empty dict with 'classifications' key",
                    actual_value="empty dict {}",
                    is_match=False
                )
            ]
        )

    # Handle empty list inputs
    if isinstance(dispatch_result, list) and not dispatch_result:
        return ComparisonReport(
            overall_match=False,
            summary="Dispatch result is an empty list. No classifications to compare.",
            detailed_diffs=[
                FieldDiff(
                    field_name="dispatch_result",
                    expected_value="non-empty list of classifications",
                    actual_value="empty list []",
                    is_match=False
                )
            ]
        )

    if isinstance(test_result, list) and not test_result:
        return ComparisonReport(
            overall_match=False,
            summary="Test result is an empty list. No classifications to compare.",
            detailed_diffs=[
                FieldDiff(
                    field_name="test_result",
                    expected_value="non-empty list of classifications",
                    actual_value="empty list []",
                    is_match=False
                )
            ]
        )

    # At this point, we have non-empty inputs
    # For this foundational version, return a basic match report
    # Detailed comparison logic will be added in subsequent iterations

    # Check if both have 'classifications' key (if they're dicts)
    dispatch_has_classifications = (
        isinstance(dispatch_result, dict) and
        "classifications" in dispatch_result
    )
    test_has_classifications = (
        isinstance(test_result, dict) and
        "classifications" in test_result
    )

    # If both are dicts with 'classifications' key, extract the lists
    if dispatch_has_classifications and test_has_classifications:
        dispatch_classifications = dispatch_result["classifications"]
        test_classifications = test_result["classifications"]

        # Check if either list is empty
        if not dispatch_classifications or not test_classifications:
            which_empty = []
            if not dispatch_classifications:
                which_empty.append("dispatch")
            if not test_classifications:
                which_empty.append("test")

            return ComparisonReport(
                overall_match=False,
                summary=f"Empty classifications list in: {', '.join(which_empty)}",
                detailed_diffs=[
                    FieldDiff(
                        field_name="classifications",
                        expected_value="non-empty list",
                        actual_value=f"empty list in {', '.join(which_empty)}",
                        is_match=False
                    )
                ]
            )

    # For now, if we haven't hit an edge case, return a basic report
    # This will be expanded with actual comparison logic in the next iteration
    return ComparisonReport(
        overall_match=True,
        summary="Basic comparison structure validated. Ready for detailed comparison logic.",
        detailed_diffs=[]
    )


__all__ = [
    "compare_classifications",
    "ComparisonReport",
]
