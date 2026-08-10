#!/usr/bin/env python3
"""
Core classification comparison function.

This module provides the foundational compare_classifications function
that performs basic comparison of classification results with proper
edge case handling for None/empty inputs, intent type comparison, and
confidence comparison with configurable tolerance.

Usage:
    from src.validation.classification_comparison import compare_classifications

    dispatch_result = {"classifications": [...]}
    test_result = {"classifications": [...]}
    report = compare_classifications(dispatch_result, test_result)
    if report.overall_match:
        print("All classifications matched!")
"""

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Union

# Import the FieldDiff model from the comparison module
from src.validation.comparison import FieldDiff, _compare_nested_structures


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
    test_result: Optional[Union[Dict, List]],
    confidence_tolerance: float = 0.1
) -> ComparisonReport:
    """
    Compare classification results from dispatch and test endpoints.

    This function performs comprehensive comparison of classification results,
    including intent type comparison, confidence comparison with configurable
    tolerance, and edge case handling for None/empty inputs.

    Args:
        dispatch_result: Classification results from dispatch endpoint.
            Can be a dict with 'classifications' key, a list of classification
            dicts, or None/empty.
        test_result: Classification results from test endpoint.
            Can be a dict with 'classifications' key, a list of classification
            dicts, or None/empty.
        confidence_tolerance: Tolerance for confidence score comparison (default: 0.1).

    Returns:
        ComparisonReport with overall_match status, summary, and detailed diffs.

    Edge Cases Handled:
        - None inputs: Returns report with overall_match=False and explanatory summary
        - Empty dict/list inputs: Returns report with overall_match=False and explanatory summary
        - Missing 'classifications' key: Treated as empty input
        - Early return on intent/confidence mismatch: Stops comparison when critical fields differ

    Comparison Priority:
        1. Intent type comparison (exact string match)
        2. Confidence comparison (within tolerance)
        - If either mismatches, function returns early with overall_match=False

    Example:
        >>> # Both inputs are None
        >>> report = compare_classifications(None, None)
        >>> assert report.overall_match is False
        >>> assert "None" in report.summary

        >>> # One input is empty
        >>> report = compare_classifications({}, {"classifications": []})
        >>> assert report.overall_match is False
        >>> assert "empty" in report.summary.lower()

        >>> # Intent type mismatch
        >>> dispatch = {"classifications": [{"intent_type": "status", "confidence": 0.9}]}
        >>> test = {"classifications": [{"intent_type": "action", "confidence": 0.9}]}
        >>> report = compare_classifications(dispatch, test)
        >>> assert report.overall_match is False
        >>> assert any(d.field_name == "intent_type" for d in report.detailed_diffs)
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

    # Extract classifications from inputs
    dispatch_classifications = []
    test_classifications = []

    # Handle dict inputs with 'classifications' key
    if isinstance(dispatch_result, dict) and "classifications" in dispatch_result:
        dispatch_classifications = dispatch_result["classifications"]
        if not dispatch_classifications:
            return ComparisonReport(
                overall_match=False,
                summary="Dispatch classifications list is empty. No classifications to compare.",
                detailed_diffs=[
                    FieldDiff(
                        field_name="classifications",
                        expected_value="non-empty list",
                        actual_value="empty list in dispatch",
                        is_match=False
                    )
                ]
            )
    elif isinstance(dispatch_result, list):
        dispatch_classifications = dispatch_result

    if isinstance(test_result, dict) and "classifications" in test_result:
        test_classifications = test_result["classifications"]
        if not test_classifications:
            return ComparisonReport(
                overall_match=False,
                summary="Test classifications list is empty. No classifications to compare.",
                detailed_diffs=[
                    FieldDiff(
                        field_name="classifications",
                        expected_value="non-empty list",
                        actual_value="empty list in test",
                        is_match=False
                    )
                ]
            )
    elif isinstance(test_result, list):
        test_classifications = test_result

    # If we couldn't extract classifications from either input
    if not dispatch_classifications and not test_classifications:
        return ComparisonReport(
            overall_match=False,
            summary="Could not extract classifications from either input. "
                   "Inputs must be dict with 'classifications' key or list of classification dicts.",
            detailed_diffs=[
                FieldDiff(
                    field_name="input_format",
                    expected_value="dict with 'classifications' key or list",
                    actual_value=f"dispatch_type={type(dispatch_result).__name__}, test_type={type(test_result).__name__}",
                    is_match=False
                )
            ]
        )

    # Compare count of classifications
    if len(dispatch_classifications) != len(test_classifications):
        return ComparisonReport(
            overall_match=False,
            summary=f"Classification count mismatch: dispatch has {len(dispatch_classifications)}, "
                   f"test has {len(test_classifications)}",
            detailed_diffs=[
                FieldDiff(
                    field_name="classification_count",
                    expected_value=len(dispatch_classifications),
                    actual_value=len(test_classifications),
                    is_match=False
                )
            ]
        )

    # Compare each classification pair
    detailed_diffs = []

    for i, (dispatch_cls, test_cls) in enumerate(zip(dispatch_classifications, test_classifications)):
        # Ensure both are dicts
        if not isinstance(dispatch_cls, dict) or not isinstance(test_cls, dict):
            detailed_diffs.append(
                FieldDiff(
                    field_name=f"classification_{i}_type",
                    expected_value="dict",
                    actual_value=f"dispatch={type(dispatch_cls).__name__}, test={type(test_cls).__name__}",
                    is_match=False
                )
            )
            continue

        # Extract intent_type values
        dispatch_intent = dispatch_cls.get("intent_type")
        test_intent = test_cls.get("intent_type")

        # Handle Enum values (extract string value if needed)
        if hasattr(dispatch_intent, 'value'):
            dispatch_intent = dispatch_intent.value
        if hasattr(test_intent, 'value'):
            test_intent = test_intent.value

        # Compare intent_type (exact string match)
        # Handle None values - they never match
        if dispatch_intent is None or test_intent is None:
            detailed_diffs.append(
                FieldDiff(
                    field_name=f"classification_{i}_intent_type",
                    expected_value=dispatch_intent,
                    actual_value=test_intent,
                    is_match=False
                )
            )
            # Early return on intent type mismatch (including None)
            return ComparisonReport(
                overall_match=False,
                summary=f"Intent type mismatch at classification {i}: "
                       f"dispatch={dispatch_intent}, test={test_intent}. "
                       f"None values never match.",
                detailed_diffs=detailed_diffs
            )
        elif dispatch_intent != test_intent:
            # Intent type strings don't match
            detailed_diffs.append(
                FieldDiff(
                    field_name=f"classification_{i}_intent_type",
                    expected_value=dispatch_intent,
                    actual_value=test_intent,
                    is_match=False
                )
            )
            # Early return on intent type mismatch
            return ComparisonReport(
                overall_match=False,
                summary=f"Intent type mismatch at classification {i}: "
                       f"dispatch={dispatch_intent}, test={test_intent}",
                detailed_diffs=detailed_diffs
            )

        # Extract confidence values
        dispatch_conf = dispatch_cls.get("confidence")
        test_conf = test_cls.get("confidence")

        # Compare confidence with tolerance
        # If both are None, skip confidence comparison (missing in both is OK)
        if dispatch_conf is None and test_conf is None:
            # Missing confidence on both sides is equivalent; continue with
            # structured_result comparison for this classification.
            pass
        elif dispatch_conf is None or test_conf is None:
            # One is None but not the other - this is a mismatch
            detailed_diffs.append(
                FieldDiff(
                    field_name=f"classification_{i}_confidence",
                    expected_value=dispatch_conf,
                    actual_value=test_conf,
                    is_match=False
                )
            )
            # Early return on confidence mismatch (including None)
            return ComparisonReport(
                overall_match=False,
                summary=f"Confidence mismatch at classification {i}: "
                       f"dispatch={dispatch_conf}, test={test_conf}. "
                       f"None values never match.",
                detailed_diffs=detailed_diffs
            )

        else:
            # Ensure both are numeric.
            if not isinstance(dispatch_conf, (int, float)) or not isinstance(test_conf, (int, float)):
                detailed_diffs.append(
                    FieldDiff(
                        field_name=f"classification_{i}_confidence",
                        expected_value=f"numeric (got {type(dispatch_conf).__name__})",
                        actual_value=f"numeric (got {type(test_conf).__name__})",
                        is_match=False
                    )
                )
                # Early return on confidence type mismatch
                return ComparisonReport(
                    overall_match=False,
                    summary=f"Confidence type mismatch at classification {i}: "
                           f"dispatch={type(dispatch_conf).__name__}, test={type(test_conf).__name__}",
                    detailed_diffs=detailed_diffs
                )

            # Convert to float for comparison.
            dispatch_conf_float = float(dispatch_conf)
            test_conf_float = float(test_conf)

            # Check if confidence values are within tolerance.
            if not math.isclose(dispatch_conf_float, test_conf_float, abs_tol=confidence_tolerance):
                detailed_diffs.append(
                    FieldDiff(
                        field_name=f"classification_{i}_confidence",
                        expected_value=dispatch_conf_float,
                        actual_value=test_conf_float,
                        is_match=False
                    )
                )
                # Early return on confidence mismatch
                return ComparisonReport(
                    overall_match=False,
                    summary=f"Confidence mismatch at classification {i}: "
                           f"dispatch={dispatch_conf_float}, test={test_conf_float} "
                           f"(tolerance={confidence_tolerance})",
                    detailed_diffs=detailed_diffs
                )

        # Compare structured_result recursively. A missing structured_result
        # and an explicit None are equivalent; only run the recursive walk when
        # at least one side contains an actual value.
        dispatch_structured = dispatch_cls.get("structured_result")
        test_structured = test_cls.get("structured_result")
        if dispatch_structured is not None or test_structured is not None:
            structured_diffs: List[FieldDiff] = []
            structured_matches: Dict[str, bool] = {}
            structured_match = _compare_nested_structures(
                dispatch_structured,
                test_structured,
                f"classification_{i}_structured_result",
                structured_diffs,
                structured_matches,
            )

            # The report is intentionally a difference report, so retain only
            # mismatching FieldDiff objects while preserving every mismatching
            # nested leaf path.
            if not structured_match:
                mismatching_diffs = [diff for diff in structured_diffs if not diff.is_match]
                nested_mismatch_paths = {
                    diff.field_name
                    for diff in mismatching_diffs
                    if "[" in diff.field_name
                }
                detailed_diffs.extend(
                    diff
                    for diff in mismatching_diffs
                    if not any(
                        path.startswith(f"{diff.field_name}[")
                        for path in nested_mismatch_paths
                    )
                )
                return ComparisonReport(
                    overall_match=False,
                    summary=f"Structured result mismatch at classification {i}",
                    detailed_diffs=detailed_diffs,
                )

    # All classifications matched
    return ComparisonReport(
        overall_match=True,
        summary=f"Perfect match: All {len(dispatch_classifications)} classifications matched. "
               f"Intent types and confidence scores (where present, ±{confidence_tolerance}) are identical.",
        detailed_diffs=[]
    )


__all__ = [
    "compare_classifications",
    "ComparisonReport",
]
