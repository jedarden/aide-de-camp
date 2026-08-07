"""
Classification comparison logic for validating endpoint equivalence.

This module provides utilities to compare classification results from
/test/intent-classify and /dispatch endpoints to ensure they produce
equivalent results.
"""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Union
from enum import Enum


class ComparisonMatchStatus(Enum):
    """Status of a single field comparison."""
    MATCH = "match"
    MISMATCH = "mismatch"
    MISSING_IN_TEST = "missing_in_test"
    MISSING_IN_DISPATCH = "missing_in_dispatch"
    TOLERANCE_MATCH = "tolerance_match"


@dataclass
class FieldDifference:
    """Details about a specific field difference."""
    field: str
    index: int  # Which classification in the list
    status: ComparisonMatchStatus
    test_value: Any
    dispatch_value: Any
    message: str


@dataclass
class ComparisonResult:
    """Result of comparing two classification results."""
    overall_match: bool
    test_count: int
    dispatch_count: int
    differences: List[FieldDifference]
    summary: str

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "overall_match": self.overall_match,
            "test_count": self.test_count,
            "dispatch_count": self.dispatch_count,
            "differences": [
                {
                    "field": diff.field,
                    "index": diff.index,
                    "status": diff.status.value,
                    "test_value": diff.test_value,
                    "dispatch_value": diff.dispatch_value,
                    "message": diff.message,
                }
                for diff in self.differences
            ],
            "summary": self.summary,
        }


def _safe_get(data: Dict[str, Any], field: str, default: Any = None) -> Any:
    """
    Safely get a field from a dict, returning default if missing or None.

    Args:
        data: Dictionary to extract from
        field: Field name to extract
        default: Default value if field is missing or None

    Returns:
        Field value or default
    """
    if data is None:
        return default
    value = data.get(field)
    return value if value is not None else default


def _compare_values(
    field: str,
    test_value: Any,
    dispatch_value: Any,
    index: int,
    tolerance: float = 0.0
) -> Optional[FieldDifference]:
    """
    Compare two values with tolerance for floating point.

    Args:
        field: Field name being compared
        test_value: Value from test endpoint
        dispatch_value: Value from dispatch endpoint
        index: Index of the classification being compared
        tolerance: Tolerance for floating point comparison

    Returns:
        FieldDifference if values don't match, None otherwise
    """
    # Handle None values
    if test_value is None and dispatch_value is None:
        return None
    if test_value is None:
        return FieldDifference(
            field=field,
            index=index,
            status=ComparisonMatchStatus.MISSING_IN_TEST,
            test_value=None,
            dispatch_value=dispatch_value,
            message=f"Field '{field}' is missing in test result but present in dispatch"
        )
    if dispatch_value is None:
        return FieldDifference(
            field=field,
            index=index,
            status=ComparisonMatchStatus.MISSING_IN_DISPATCH,
            test_value=test_value,
            dispatch_value=None,
            message=f"Field '{field}' is present in test result but missing in dispatch"
        )

    # Floating point comparison with tolerance
    if isinstance(test_value, float) and isinstance(dispatch_value, float):
        if abs(test_value - dispatch_value) <= tolerance:
            return None  # Match within tolerance
        return FieldDifference(
            field=field,
            index=index,
            status=ComparisonMatchStatus.MISMATCH,
            test_value=test_value,
            dispatch_value=dispatch_value,
            message=f"Field '{field}' mismatch: test={test_value}, dispatch={dispatch_value} (tolerance={tolerance})"
        )

    # Exact comparison for other types
    if test_value != dispatch_value:
        return FieldDifference(
            field=field,
            index=index,
            status=ComparisonMatchStatus.MISMATCH,
            test_value=test_value,
            dispatch_value=dispatch_value,
            message=f"Field '{field}' mismatch: test={test_value}, dispatch={dispatch_value}"
        )

    return None


def _extract_classification_from_routed_intent(
    routed_intent: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Extract classification data from a RoutedIntent structure.

    Args:
        routed_intent: RoutedIntent dict with nested classification

    Returns:
        Flattened classification dict
    """
    if "classification" in routed_intent:
        # Extract from RoutedIntent structure
        classification = routed_intent["classification"]

        # Handle intent_type as enum or string
        intent_type = classification.get("intent_type")
        if isinstance(intent_type, dict):
            intent_type = intent_type.get("value")
        elif isinstance(intent_type, Enum):
            intent_type = intent_type.value

        return {
            "intent_type": intent_type,
            "project_slug": classification.get("project_slug"),
            "confidence": classification.get("confidence"),
            "utterance_fragment": classification.get("utterance_fragment"),
            "reasoning": classification.get("reasoning"),
            "urgency": classification.get("urgency"),
            "lookup_kind": classification.get("lookup_kind"),
        }
    else:
        # Assume it's already a flat classification dict
        return routed_intent


def compare_classifications(
    dispatch_result: Union[List[Dict], Dict],
    test_result: Union[List[Dict], Dict],
    confidence_tolerance: float = 0.01,
) -> ComparisonResult:
    """
    Compare classification results from dispatch and test endpoints.

    This function validates that classification results from both endpoints
    are equivalent, comparing:
    - Intent types
    - Confidence scores (with tolerance)
    - Project slugs
    - Utterance fragments
    - Reasoning
    - Urgency levels
    - Lookup kinds (optional field for lookup intents)

    Args:
        dispatch_result: Classifications from /dispatch endpoint
            - Can be a list of RoutedIntent dicts (with nested classification)
            - Can be a list of classification dicts
            - Can be a dict with 'classifications' key
        test_result: Classifications from /test/intent-classify endpoint
            - Can be a list of classification dicts
            - Can be a dict with 'classifications' key
        confidence_tolerance: Tolerance for confidence score comparison (default: 0.01)

    Returns:
        ComparisonResult with detailed differences if any

    Examples:
        >>> # Compare results from both endpoints
        >>> dispatch_data = {
        ...     "classifications": [
        ...         {"intent_type": "status", "project_slug": "my-project", "confidence": 0.9}
        ...     ]
        ... }
        >>> test_data = {
        ...     "classifications": [
        ...         {"intent_type": "status", "project_slug": "my-project", "confidence": 0.9}
        ...     ]
        ... }
        >>> result = compare_classifications(dispatch_data, test_data)
        >>> assert result.overall_match is True

        >>> # Handle list inputs directly
        >>> dispatch_list = [{"intent_type": "status", ...}]
        >>> test_list = [{"intent_type": "status", ...}]
        >>> result = compare_classifications(dispatch_list, test_list)
    """
    differences: List[FieldDifference] = []

    # Normalize inputs to lists of classification dicts
    dispatch_classifications = []
    test_classifications = []

    # Extract dispatch classifications
    if isinstance(dispatch_result, dict) and "classifications" in dispatch_result:
        dispatch_intents = dispatch_result["classifications"]
        for intent in dispatch_intents:
            dispatch_classifications.append(
                _extract_classification_from_routed_intent(intent)
            )
    elif isinstance(dispatch_result, list):
        for intent in dispatch_result:
            dispatch_classifications.append(
                _extract_classification_from_routed_intent(intent)
            )
    else:
        # Invalid input format
        return ComparisonResult(
            overall_match=False,
            test_count=0,
            dispatch_count=0,
            differences=[],
            summary="Invalid dispatch_result format: expected dict or list"
        )

    # Extract test classifications
    if isinstance(test_result, dict) and "classifications" in test_result:
        test_classifications = test_result["classifications"]
    elif isinstance(test_result, list):
        test_classifications = test_result
    else:
        # Invalid input format
        return ComparisonResult(
            overall_match=False,
            test_count=0,
            dispatch_count=0,
            differences=[],
            summary="Invalid test_result format: expected dict or list"
        )

    # Check count match
    test_count = len(test_classifications)
    dispatch_count = len(dispatch_classifications)

    if test_count != dispatch_count:
        differences.append(FieldDifference(
            field="count",
            index=-1,  # Special index for count mismatch
            status=ComparisonMatchStatus.MISMATCH,
            test_value=test_count,
            dispatch_value=dispatch_count,
            message=f"Different number of classifications: test={test_count}, dispatch={dispatch_count}"
        ))

        # Still compare individual classifications up to the min count
        # to provide more detailed differences
        min_count = min(test_count, dispatch_count)
    else:
        min_count = test_count

    # Compare each classification pair
    for i in range(min_count):
        test_cls = test_classifications[i]
        dispatch_cls = dispatch_classifications[i]

        # Compare intent_type
        test_intent = _safe_get(test_cls, "intent_type")
        dispatch_intent = _safe_get(dispatch_cls, "intent_type")
        diff = _compare_values("intent_type", test_intent, dispatch_intent, i)
        if diff:
            differences.append(diff)

        # Compare project_slug
        test_project = _safe_get(test_cls, "project_slug")
        dispatch_project = _safe_get(dispatch_cls, "project_slug")
        diff = _compare_values("project_slug", test_project, dispatch_project, i)
        if diff:
            differences.append(diff)

        # Compare confidence with tolerance
        test_conf = _safe_get(test_cls, "confidence", 0.0)
        dispatch_conf = _safe_get(dispatch_cls, "confidence", 0.0)
        diff = _compare_values(
            "confidence",
            test_conf,
            dispatch_conf,
            i,
            tolerance=confidence_tolerance
        )
        if diff:
            differences.append(diff)

        # Compare utterance_fragment
        test_fragment = _safe_get(test_cls, "utterance_fragment")
        dispatch_fragment = _safe_get(dispatch_cls, "utterance_fragment")
        diff = _compare_values("utterance_fragment", test_fragment, dispatch_fragment, i)
        if diff:
            differences.append(diff)

        # Compare reasoning
        test_reasoning = _safe_get(test_cls, "reasoning")
        dispatch_reasoning = _safe_get(dispatch_cls, "reasoning")
        diff = _compare_values("reasoning", test_reasoning, dispatch_reasoning, i)
        if diff:
            differences.append(diff)

        # Compare urgency
        test_urgency = _safe_get(test_cls, "urgency")
        dispatch_urgency = _safe_get(dispatch_cls, "urgency")
        diff = _compare_values("urgency", test_urgency, dispatch_urgency, i)
        if diff:
            differences.append(diff)

        # Compare lookup_kind (optional field - may be None)
        test_lookup = _safe_get(test_cls, "lookup_kind")
        dispatch_lookup = _safe_get(dispatch_cls, "lookup_kind")
        diff = _compare_values("lookup_kind", test_lookup, dispatch_lookup, i)
        if diff:
            differences.append(diff)

    # Build summary
    overall_match = len(differences) == 0

    if overall_match:
        summary = f"✓ Perfect match: {test_count} classifications identical"
    elif differences[0].field == "count":
        summary = (
            f"✗ Count mismatch: test={test_count}, dispatch={dispatch_count}. "
            f"Compared {min_count} classifications, found {len(differences)} differences."
        )
    else:
        field_names = set(d.field for d in differences)
        summary = (
            f"✗ {len(differences)} difference(s) across {len(field_names)} field(s): "
            f"{', '.join(sorted(field_names))}"
        )

    return ComparisonResult(
        overall_match=overall_match,
        test_count=test_count,
        dispatch_count=dispatch_count,
        differences=differences,
        summary=summary,
    )
