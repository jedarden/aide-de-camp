#!/usr/bin/env python3
"""
Comparison data structures for classification validation.

This module defines data structures for comparing classification results,
including individual field differences and comprehensive comparison reports.
These structures support intent classification validation by tracking matches
and mismatches between expected and actual classification results.

Usage:
    from src.validation.comparison import ComparisonResult, FieldDiff, ComparisonReport

    field_diff = FieldDiff(
        field_name="intent",
        expected_value="research",
        actual_value="research",
        is_match=True
    )

    result = ComparisonResult(
        intent_match=True,
        confidence_match=True,
        field_matches={"intent": True, "confidence": True},
        diffs=[field_diff]
    )
"""

import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple


@dataclass(frozen=True)
class FieldDiff:
    """
    Represents a difference between expected and actual values for a single field.

    A FieldDiff records whether a specific field in a classification result matches
    its expected value, including both the values for debugging and reporting.

    Attributes:
        field_name: Name of the field being compared (e.g., "intent", "confidence")
        expected_value: The expected value for this field
        actual_value: The actual value received (may be None if field was missing)
        is_match: True if values match according to comparison rules, False otherwise

    Matching Rules:
        - Exact match for non-None values
        - Structured comparison treats None and a missing nested key as equal
        - String comparison is case-sensitive
        - Numeric comparison uses exact equality

    Example:
        >>> diff = FieldDiff(
        ...     field_name="intent",
        ...     expected_value="research",
        ...     actual_value="personal",
        ...     is_match=False
        ... )
        >>> assert not diff.is_match
        >>> assert diff.field_name == "intent"
    """

    field_name: str
    expected_value: Any
    actual_value: Any
    is_match: bool

    def __post_init__(self) -> None:
        """Validate field names and ensure immutability."""
        if not isinstance(self.field_name, str):
            raise ValueError(f"field_name must be a string, got {type(self.field_name).__name__}")
        if not self.field_name.strip():
            raise ValueError("field_name cannot be empty")


@dataclass(frozen=True)
class ComparisonResult:
    """
    Result of comparing a classification against expected values.

    A ComparisonResult captures the outcome of comparing an actual classification
    result against an expected result, tracking both high-level match status and
    detailed field-by-field differences.

    Attributes:
        intent_match: True if the intent classification matches expected
        confidence_match: True if the confidence value matches expected
        field_matches: Dictionary mapping field names to match status (True/False)
        diffs: List of FieldDiff objects with detailed comparison information

    Matching Logic:
        - intent_match: True if intent field matches exactly
        - confidence_match: True if confidence values match (within tolerance for floats)
        - field_matches: Dict containing all field comparisons, including fields that matched
        - diffs: Complete list of field comparisons (both matches and diffs)

    Example:
        >>> result = ComparisonResult(
        ...     intent_match=True,
        ...     confidence_match=False,
        ...     field_matches={"intent": True, "confidence": False, "source": True},
        ...     diffs=[
        ...         FieldDiff("intent", "research", "research", True),
        ...         FieldDiff("confidence", 0.8, 0.75, False),
        ...     ]
        ... )
        >>> assert result.intent_match
        >>> assert not result.confidence_match
    """

    intent_match: bool
    confidence_match: bool
    field_matches: Dict[str, bool] = field(default_factory=dict)
    diffs: List[FieldDiff] = field(default_factory=list)

    def __post_init__(self) -> None:
        """Ensure diffs list is immutable and field_matches keys align with diffs."""
        # Convert lists to tuples for immutability
        if isinstance(self.diffs, list):
            object.__setattr__(self, 'diffs', tuple(self.diffs))
        if isinstance(self.field_matches, dict):
            object.__setattr__(self, 'field_matches', dict(self.field_matches))

        # Validate that field_matches keys correspond to diffs
        diff_fields = {d.field_name for d in self.diffs}
        match_fields = set(self.field_matches.keys())
        if diff_fields != match_fields:
            raise ValueError(
                f"field_matches keys {match_fields} must match diffs field_names {diff_fields}"
            )

    @property
    def detailed_diffs(self) -> Tuple[FieldDiff, ...]:
        """Expose the field comparisons under the report-oriented name."""
        return self.diffs


@dataclass
class ComparisonReport:
    """
    Comprehensive report of classification comparison results.

    A ComparisonReport aggregates multiple ComparisonResult objects and provides
    summary statistics and detailed breakdowns. This is the primary structure
    for reporting classification validation outcomes.

    Attributes:
        total_comparisons: Total number of classification comparisons performed
        matching_count: Number of comparisons where all fields matched
        partial_match_count: Number of comparisons with some matches but not all
        mismatch_count: Number of comparisons with no matches
        overall_match: True if ALL components match (no mismatches, no partials)
        results: List of individual ComparisonResult objects
        summary: Optional human-readable summary of the comparison results

    Summary Categories:
        - "full_match": All fields match (intent_match=True, confidence_match=True)
        - "partial_match": Some fields match but not all
        - "mismatch": No fields match (all comparisons failed)

    Example:
        >>> report = ComparisonReport(
        ...     total_comparisons=10,
        ...     matching_count=7,
        ...     partial_match_count=2,
        ...     mismatch_count=1,
        ...     overall_match=False,
        ...     results=[result1, result2, ...],
        ...     summary="7/10 classifications fully matched expected values"
        ... )
        >>> assert report.total_comparisons == 10
        >>> assert report.matching_count == 7
        >>> assert report.overall_match is False
    """

    total_comparisons: int
    matching_count: int
    partial_match_count: int
    mismatch_count: int
    results: List[ComparisonResult] = field(default_factory=list)
    summary: Optional[str] = None
    overall_match: bool = False

    def __post_init__(self) -> None:
        """Validate that counts match the results list and calculate overall_match."""
        if self.total_comparisons != len(self.results):
            raise ValueError(
                f"total_comparisons ({self.total_comparisons}) must equal "
                f"len(results) ({len(self.results)})"
            )

        counted = self.matching_count + self.partial_match_count + self.mismatch_count
        if counted != self.total_comparisons:
            raise ValueError(
                f"Sum of matching_count ({self.matching_count}), "
                f"partial_match_count ({self.partial_match_count}), and "
                f"mismatch_count ({self.mismatch_count}) must equal "
                f"total_comparisons ({self.total_comparisons})"
            )

        # Calculate overall_match if not explicitly set
        # overall_match is True only if ALL comparisons are full matches
        if self.total_comparisons > 0:
            object.__setattr__(self, 'overall_match', self.mismatch_count == 0 and self.partial_match_count == 0)
        else:
            object.__setattr__(self, 'overall_match', True)  # Empty results match

    def get_accuracy_rate(self) -> float:
        """
        Calculate the accuracy rate of classifications.

        Returns:
            Float between 0.0 and 1.0 representing the proportion of
            comparisons that fully matched expected values
        """
        if self.total_comparisons == 0:
            return 0.0
        return self.matching_count / self.total_comparisons

    @property
    def detailed_diffs(self) -> List[FieldDiff]:
        """Return all field comparisons as one report-level list.

        Individual ``ComparisonResult`` objects retain the classification
        boundaries, while callers that render a report generally need a flat
        list. Returning a new list keeps the report's result collection intact.
        """
        return [diff for result in self.results for diff in result.diffs]

    def get_partial_accuracy_rate(self) -> float:
        """
        Calculate the partial accuracy rate (including partial matches).

        Returns:
            Float between 0.0 and 1.0 representing the proportion of
            comparisons that either fully or partially matched
        """
        if self.total_comparisons == 0:
            return 0.0
        return (self.matching_count + self.partial_match_count) / self.total_comparisons


def detect_coverage_gaps(
    deployments: List[Dict[str, Any]],
    timestamp_field: str = "created_at",
    gap_threshold_days: int = 1
) -> List[Tuple[datetime, datetime]]:
    """
    Detect coverage gaps in a deployment sequence.

    This function identifies temporal gaps between deployments, which can indicate
    periods where no deployments occurred. Useful for validating deployment coverage
    and identifying potential data collection or deployment issues.

    Args:
        deployments: List of deployment dictionaries with timestamp fields
        timestamp_field: Name of the field containing ISO 8601 timestamp (default: "created_at")
        gap_threshold_days: Minimum number of days to consider a gap (default: 1)

    Returns:
        List of tuples (start_timestamp, end_timestamp) representing detected gaps.
        Returns empty list if no gaps are found or if input is invalid.

    Edge Cases Handled:
        - Empty deployment sequence: returns empty list
        - Single deployment: returns empty list (cannot detect gaps with one data point)
        - Unsorted timestamps: automatically sorts before gap detection
        - Invalid timestamps: skips deployments with missing/invalid timestamps
        - Missing timestamp_field: uses default field name

    Example:
        >>> deployments = [
        ...     {"name": "deploy-1", "created_at": "2026-08-01T00:00:00Z"},
        ...     {"name": "deploy-2", "created_at": "2026-08-05T00:00:00Z"},
        ...     {"name": "deploy-3", "created_at": "2026-08-06T00:00:00Z"},
        ... ]
        >>> gaps = detect_coverage_gaps(deployments, gap_threshold_days=2)
        >>> len(gaps)
        1
        >>> # Gap detected between 2026-08-01 and 2026-08-05 (4 days)
    """
    # Handle edge cases
    if not deployments:
        return []

    if len(deployments) < 2:
        return []

    gaps = []
    valid_timestamps = []

    # Extract and parse timestamps
    for deployment in deployments:
        if not isinstance(deployment, dict):
            continue

        timestamp_str = deployment.get(timestamp_field)
        if not timestamp_str:
            continue

        try:
            # Parse ISO 8601 timestamp
            timestamp = _parse_timestamp(timestamp_str)
            valid_timestamps.append(timestamp)
        except (ValueError, TypeError):
            # Skip invalid timestamps
            continue

    # Need at least 2 valid timestamps to detect gaps
    if len(valid_timestamps) < 2:
        return []

    # Sort timestamps to ensure chronological order
    valid_timestamps.sort()

    # Detect gaps between consecutive deployments
    for i in range(len(valid_timestamps) - 1):
        current_timestamp = valid_timestamps[i]
        next_timestamp = valid_timestamps[i + 1]

        # Calculate time difference
        time_diff = next_timestamp - current_timestamp

        # Check if gap exceeds threshold
        if time_diff.days >= gap_threshold_days:
            # Gap starts after current deployment and ends at next deployment
            gap_start = current_timestamp + timedelta(seconds=1)
            gap_end = next_timestamp - timedelta(seconds=1)
            gaps.append((gap_start, gap_end))

    return gaps


def _parse_timestamp(timestamp_str: str) -> datetime:
    """
    Parse ISO 8601 timestamp string to datetime object.

    Handles various ISO 8601 formats including:
    - 2026-08-01T00:00:00Z
    - 2026-08-01T00:00:00+00:00
    - 2026-08-01T00:00:00.123Z

    Args:
        timestamp_str: ISO 8601 timestamp string

    Returns:
        datetime object

    Raises:
        ValueError: If timestamp string is invalid or cannot be parsed
    """
    if not timestamp_str:
        raise ValueError("Timestamp string cannot be empty")

    # Handle Z suffix (UTC)
    ts = timestamp_str
    if ts.endswith('Z'):
        ts = ts[:-1] + '+00:00'

    # Parse using fromisoformat
    try:
        return datetime.fromisoformat(ts.replace('+00:00', ''))
    except ValueError as e:
        raise ValueError(f"Invalid ISO 8601 timestamp: {timestamp_str}") from e


def _record_field_comparison(
    expected: Any,
    actual: Any,
    field_path: str,
    diffs: List[FieldDiff],
    field_matches: Dict[str, bool],
    is_match: bool,
) -> bool:
    """Record one comparison and keep ``field_matches`` aligned with ``diffs``."""
    field_matches[field_path] = is_match
    diffs.append(FieldDiff(
        field_name=field_path,
        expected_value=expected,
        actual_value=actual,
        is_match=is_match,
    ))
    return is_match


def _atomic_values_match(expected: Any, actual: Any, confidence_tolerance: float) -> bool:
    """Compare non-container values, including the structured numeric tolerance."""
    # A missing mapping key is represented by None, so None and None match.
    if expected is None or actual is None:
        return expected is None and actual is None

    # bool is an int subclass, but must remain a distinct structured value.
    numeric_values = (
        isinstance(expected, (int, float)) and not isinstance(expected, bool),
        isinstance(actual, (int, float)) and not isinstance(actual, bool),
    )
    if any(numeric_values):
        if not all(numeric_values):
            return False
        return math.isclose(float(expected), float(actual), abs_tol=confidence_tolerance)

    # Do not let Python's permissive equality make unlike structured types match.
    if type(expected) is not type(actual):
        return False
    return expected == actual


def _compare_nested_structures(
    expected: Any,
    actual: Any,
    field_path: str,
    diffs: List[FieldDiff],
    field_matches: Dict[str, bool],
    confidence_tolerance: float = 0.01,
) -> bool:
    """Recursively compare dictionaries, lists, and scalar structured values.

    Mapping keys are compared as a union, with a missing key represented by
    ``None``. This deliberately makes a missing key equivalent to an explicit
    ``None`` value. Dictionary children and lists containing nested containers
    receive full paths such as ``result.found_entities[0].name``. Lists of
    scalar values are represented by one field-level comparison at the list
    path, which keeps the result useful for unordered/atomic array fields.
    """
    # None and missing mapping keys are intentionally equivalent.
    if expected is None or actual is None:
        return _record_field_comparison(
            expected,
            actual,
            field_path,
            diffs,
            field_matches,
            expected is None and actual is None,
        )

    # Containers need to be handled before the general type check so that
    # nested values can produce leaf-level paths.
    if isinstance(expected, dict) or isinstance(actual, dict):
        if not isinstance(expected, dict) or not isinstance(actual, dict):
            return _record_field_comparison(
                expected, actual, field_path, diffs, field_matches, False
            )

        all_match = True
        # Sort by a stable string representation for deterministic reports while
        # still allowing non-string JSON-like keys in callers' dictionaries.
        all_keys = sorted(set(expected) | set(actual), key=str)
        for key in all_keys:
            nested_path = f"{field_path}.{key}" if field_path else str(key)
            nested_match = _compare_nested_structures(
                expected.get(key),
                actual.get(key),
                nested_path,
                diffs,
                field_matches,
                confidence_tolerance,
            )
            all_match = nested_match and all_match
        return all_match

    if isinstance(expected, list) or isinstance(actual, list):
        if not isinstance(expected, list) or not isinstance(actual, list):
            return _record_field_comparison(
                expected, actual, field_path, diffs, field_matches, False
            )

        if len(expected) != len(actual):
            # Keep the length mismatch at the list field; it is one structural
            # difference and avoids inventing paths for absent list elements.
            return _record_field_comparison(
                f"list[{len(expected)}]",
                f"list[{len(actual)}]",
                field_path,
                diffs,
                field_matches,
                False,
            )

        contains_nested_values = any(
            isinstance(item, (dict, list)) for item in (*expected, *actual)
        )
        if not contains_nested_values:
            return _record_field_comparison(
                expected,
                actual,
                field_path,
                diffs,
                field_matches,
                all(
                    _atomic_values_match(exp_item, act_item, confidence_tolerance)
                    for exp_item, act_item in zip(expected, actual)
                ),
            )

        all_match = True
        for index, (expected_item, actual_item) in enumerate(zip(expected, actual)):
            item_match = _compare_nested_structures(
                expected_item,
                actual_item,
                f"{field_path}[{index}]",
                diffs,
                field_matches,
                confidence_tolerance,
            )
            all_match = item_match and all_match

        # Keep an aggregate list result as well as indexed nested fields. This
        # makes callers able to ask for either the list field or its leaf paths.
        return _record_field_comparison(
            expected,
            actual,
            field_path,
            diffs,
            field_matches,
            all_match,
        )

    return _record_field_comparison(
        expected,
        actual,
        field_path,
        diffs,
        field_matches,
        _atomic_values_match(expected, actual, confidence_tolerance),
    )


def compare_classifications(
    expected: Dict[str, Any],
    actual: Dict[str, Any],
    confidence_tolerance: float = 0.1,
    early_return: bool = True
) -> ComparisonResult:
    """
    Compare classification results for intent type, confidence, and structured result.

    Performs field-by-field comparison between expected and actual classification
    results, supporting both exact matching (intent_type), tolerance-based
    matching (confidence), and recursive nested structure comparison (structured_result).

    Args:
        expected: Expected classification result with 'intent_type', 'confidence', and optional 'structured_result' fields
        actual: Actual classification result to compare against expected
        confidence_tolerance: Tolerance for confidence comparison (default: ±0.1)
        early_return: If True, return early on first mismatch without checking remaining fields

    Returns:
        ComparisonResult containing match status and field differences

    Raises:
        ValueError: If expected or actual is not a dict, or if required fields are missing

    Example:
        >>> expected = {"intent_type": "research", "confidence": 0.8, "structured_result": {"project": "adc"}}
        >>> actual = {"intent_type": "research", "confidence": 0.85, "structured_result": {"project": "adc"}}
        >>> result = compare_classifications(expected, actual, confidence_tolerance=0.1)
        >>> assert result.intent_match
        >>> assert result.confidence_match
    """
    # Validate inputs
    if not isinstance(expected, dict) or not isinstance(actual, dict):
        raise ValueError(
            f"Both expected and actual must be dicts, got "
            f"{type(expected).__name__} and {type(actual).__name__}"
        )

    # Extract expected values
    expected_intent = expected.get("intent_type")
    expected_confidence = expected.get("confidence")
    expected_structured = expected.get("structured_result")

    # Extract actual values
    actual_intent = actual.get("intent_type")
    actual_confidence = actual.get("confidence")
    actual_structured = actual.get("structured_result")

    diffs = []
    field_matches = {}
    intent_match = False
    confidence_match = False

    # Compare intent_type (exact string match)
    # Convert enum to string if necessary
    expected_intent_str = str(expected_intent.value) if hasattr(expected_intent, 'value') else str(expected_intent)
    actual_intent_str = str(actual_intent.value) if hasattr(actual_intent, 'value') else str(actual_intent)

    intent_match = expected_intent_str == actual_intent_str
    field_matches["intent_type"] = intent_match

    intent_diff = FieldDiff(
        field_name="intent_type",
        expected_value=expected_intent_str,
        actual_value=actual_intent_str,
        is_match=intent_match
    )
    diffs.append(intent_diff)

    # Early return if intent doesn't match
    if not intent_match and early_return:
        return ComparisonResult(
            intent_match=False,
            confidence_match=False,
            field_matches=field_matches,
            diffs=diffs
        )

    # Compare confidence (within tolerance)
    try:
        expected_conf = float(expected_confidence) if expected_confidence is not None else None
        actual_conf = float(actual_confidence) if actual_confidence is not None else None

        if expected_conf is None or actual_conf is None:
            # One or both values are None - treat as mismatch
            confidence_match = False
        else:
            # Check if values are within tolerance
            confidence_diff = abs(expected_conf - actual_conf)
            confidence_match = confidence_diff <= confidence_tolerance

        field_matches["confidence"] = confidence_match

        confidence_diff_obj = FieldDiff(
            field_name="confidence",
            expected_value=expected_conf,
            actual_value=actual_conf,
            is_match=confidence_match
        )
        diffs.append(confidence_diff_obj)

        # Early return if confidence doesn't match
        if not confidence_match and early_return:
            return ComparisonResult(
                intent_match=intent_match,
                confidence_match=False,
                field_matches=field_matches,
                diffs=diffs
            )

    except (ValueError, TypeError):
        # Handle case where confidence values cannot be converted to float
        confidence_match = False
        field_matches["confidence"] = False

        confidence_diff_obj = FieldDiff(
            field_name="confidence",
            expected_value=expected_confidence,
            actual_value=actual_confidence,
            is_match=False
        )
        diffs.append(confidence_diff_obj)

        if early_return:
            return ComparisonResult(
                intent_match=intent_match,
                confidence_match=False,
                field_matches=field_matches,
                diffs=diffs
            )

    # Compare structured_result even when both values are None/missing. This
    # records the consistent None/missing match and keeps the result complete.
    structured_match = _compare_nested_structures(
        expected_structured,
        actual_structured,
        "structured_result",
        diffs,
        field_matches,
        confidence_tolerance=0.01,
    )

    # Early return if structured_result doesn't match
    if not structured_match and early_return:
        return ComparisonResult(
            intent_match=intent_match,
            confidence_match=confidence_match,
            field_matches=field_matches,
            diffs=diffs,
        )

    # Return final result with all comparisons
    return ComparisonResult(
        intent_match=intent_match,
        confidence_match=confidence_match,
        field_matches=field_matches,
        diffs=diffs
    )


__all__ = [
    "FieldDiff",
    "ComparisonResult",
    "ComparisonReport",
    "detect_coverage_gaps",
    "_parse_timestamp",
    "compare_classifications",
]
