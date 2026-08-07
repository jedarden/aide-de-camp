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

from dataclasses import dataclass, field
from typing import Any, Optional, Dict, List


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
        - None values never match (missing field is always a diff)
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
        ...     results=[result1, result2, ...],
        ...     summary="7/10 classifications fully matched expected values"
        ... )
        >>> assert report.total_comparisons == 10
        >>> assert report.matching_count == 7
    """

    total_comparisons: int
    matching_count: int
    partial_match_count: int
    mismatch_count: int
    results: List[ComparisonResult] = field(default_factory=list)
    summary: Optional[str] = None

    def __post_init__(self) -> None:
        """Validate that counts match the results list."""
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


__all__ = [
    "FieldDiff",
    "ComparisonResult",
    "ComparisonReport",
]
