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


def compare_structured_fields(
    dispatch_fields: Dict[str, Any],
    test_fields: Dict[str, Any],
    order_sensitive_fields: Optional[List[str]] = None,
) -> Dict[str, bool]:
    """
    Compare structured result fields from classifications.

    This function performs deep comparison of structured fields including:
    - Nested dictionary comparison (recursive)
    - List/array comparison (order-insensitive by default)
    - Primitive type comparison (exact match for strings, tolerance for floats)

    Args:
        dispatch_fields: Fields from dispatch endpoint result
        test_fields: Fields from test endpoint result
        order_sensitive_fields: Optional list of field paths that require order-sensitive
            list comparison (e.g., ["parameters", "entities"]). Uses dot notation for
            nested fields like "metadata.steps" or "entities.tags".

    Returns:
        Dict mapping field paths to match status (True = match, False = mismatch).
        Uses dot notation for nested fields (e.g., "parameters.project_slug").

    Examples:
        >>> # Simple flat comparison
        >>> dispatch = {"project_slug": "aide-de-camp", "confidence": 0.9}
        >>> test = {"project_slug": "aide-de-camp", "confidence": 0.899}
        >>> result = compare_structured_fields(dispatch, test)
        >>> assert result["project_slug"] is True
        >>> assert result["confidence"] is True  # Within 0.01 tolerance

        >>> # Nested dict comparison
        >>> dispatch = {"parameters": {"project": "adc", "urgency": "high"}}
        >>> test = {"parameters": {"project": "adc", "urgency": "high"}}
        >>> result = compare_structured_fields(dispatch, test)
        >>> assert result["parameters.project"] is True
        >>> assert result["parameters.urgency"] is True

        >>> # List comparison (order-insensitive by default)
        >>> dispatch = {"entities": ["project", "status"]}
        >>> test = {"entities": ["status", "project"]}
        >>> result = compare_structured_fields(dispatch, test)
        >>> assert result["entities"] is True  # Order insensitive

        >>> # Order-sensitive list comparison
        >>> dispatch = {"steps": ["step1", "step2"]}
        >>> test = {"steps": ["step2", "step1"]}
        >>> result = compare_structured_fields(dispatch, test, order_sensitive_fields=["steps"])
        >>> assert result["steps"] is False  # Order sensitive
    """
    order_sensitive_fields = order_sensitive_fields or []
    results: Dict[str, bool] = {}

    def _get_all_keys(data: Dict[str, Any], prefix: str = "") -> List[str]:
        """Get all keys from a nested dict using dot notation."""
        keys = []
        for key, value in data.items():
            full_key = f"{prefix}.{key}" if prefix else key
            keys.append(full_key)
            if isinstance(value, dict):
                keys.extend(_get_all_keys(value, full_key))
        return keys

    def _get_value_by_path(data: Dict[str, Any], path: str) -> Any:
        """Get value from nested dict using dot-notation path."""
        keys = path.split(".")
        value = data
        for key in keys:
            if not isinstance(value, dict) or key not in value:
                return None
            value = value[key]
        return value

    def _compare_lists(
        list1: List[Any],
        list2: List[Any],
        field_path: str,
        order_sensitive: bool = False,
    ) -> bool:
        """
        Compare two lists with configurable order sensitivity.

        Args:
            list1: First list to compare
            list2: Second list to compare
            field_path: Full field path (for nested recursion)
            order_sensitive: If True, preserves order; if False, sorts before comparing

        Returns:
            True if lists match, False otherwise
        """
        if not isinstance(list1, list) or not isinstance(list2, list):
            return False

        if len(list1) != len(list2):
            return False

        if order_sensitive:
            # Order-sensitive comparison
            for i, (item1, item2) in enumerate(zip(list1, list2)):
                if isinstance(item1, dict) and isinstance(item2, dict):
                    # Recursively compare nested dicts in list items
                    nested_results = _compare_dicts(
                        item1,
                        item2,
                        prefix=field_path,
                    )
                    if not all(nested_results.values()):
                        return False
                elif item1 != item2:
                    return False
            return True
        else:
            # Order-insensitive comparison - sort if comparable
            try:
                # For primitives, use direct comparison after sorting
                sorted1 = sorted(list1)
                sorted2 = sorted(list2)
                return sorted1 == sorted2
            except TypeError:
                # For complex types (dicts, mixed types), use multiset comparison
                from collections import Counter

                # For dicts, compare by structure
                if all(isinstance(item, dict) for item in list1) and all(
                    isinstance(item, dict) for item in list2
                ):
                    # Compare each dict by its keys (order-insensitive)
                    matched_indices = set()
                    for item1 in list1:
                        found = False
                        for i, item2 in enumerate(list2):
                            if i in matched_indices:
                                continue
                            nested_results = _compare_dicts(item1, item2, prefix=field_path)
                            if nested_results and all(nested_results.values()):
                                matched_indices.add(i)
                                found = True
                                break
                        if not found:
                            return False
                    return True
                else:
                    # Fall back to Counter comparison (hashable items only)
                    try:
                        return Counter(list1) == Counter(list2)
                    except TypeError:
                        # Unhashable items - compare element by element (slow but correct)
                        list1_copy = list1.copy()
                        for item2 in list2:
                            if item2 in list1_copy:
                                list1_copy.remove(item2)
                            else:
                                return False
                        return len(list1_copy) == 0

    def _compare_dicts(
        dict1: Dict[str, Any],
        dict2: Dict[str, Any],
        prefix: str = "",
    ) -> Dict[str, bool]:
        """
        Recursively compare two dicts, returning field-level match results.

        Args:
            dict1: First dict to compare
            dict2: Second dict to compare
            prefix: Current field path prefix for nested keys

        Returns:
            Dict mapping field paths to match status
        """
        local_results: Dict[str, bool] = {}

        # Get all keys from both dicts
        all_keys = set(dict1.keys()) | set(dict2.keys())

        for key in all_keys:
            full_key = f"{prefix}.{key}" if prefix else key

            # Check for missing keys
            if key not in dict1:
                local_results[full_key] = False
                continue
            if key not in dict2:
                local_results[full_key] = False
                continue

            value1 = dict1[key]
            value2 = dict2[key]

            # Handle nested dicts
            if isinstance(value1, dict) and isinstance(value2, dict):
                nested_results = _compare_dicts(value1, value2, full_key)
                local_results.update(nested_results)
                # Parent field matches if all children match
                local_results[full_key] = all(nested_results.values())
            # Handle lists
            elif isinstance(value1, list) and isinstance(value2, list):
                order_sensitive = full_key in order_sensitive_fields or any(
                    full_key.startswith(f"{field}.") for field in order_sensitive_fields
                )
                local_results[full_key] = _compare_lists(
                    value1, value2, full_key, order_sensitive
                )
            # Handle None values
            elif value1 is None or value2 is None:
                local_results[full_key] = value1 is None and value2 is None
            # Handle float comparison with tolerance
            elif isinstance(value1, float) and isinstance(value2, float):
                import math

                local_results[full_key] = math.isclose(value1, value2, abs_tol=0.01)
            # Handle int/float mixed comparison
            elif isinstance(value1, (int, float)) and isinstance(value2, (int, float)):
                import math

                local_results[full_key] = math.isclose(
                    float(value1), float(value2), abs_tol=0.01
                )
            # Exact comparison for other types
            else:
                local_results[full_key] = value1 == value2

        return local_results

    # Handle edge cases
    if dispatch_fields is None and test_fields is None:
        return {}
    if dispatch_fields is None or test_fields is None:
        # One is None, treat all fields as mismatch
        all_keys = _get_all_keys(dispatch_fields or test_fields)
        return {key: False for key in all_keys}

    if not isinstance(dispatch_fields, dict) or not isinstance(test_fields, dict):
        return {"": False}

    # Perform comparison
    results.update(_compare_dicts(dispatch_fields, test_fields))

    return results


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


def compare_intent_type(dispatch_intent: Any, test_intent: Any) -> bool:
    """
    Compare intent type strings between two classification results.

    This function performs a direct string comparison of intent types.
    It handles None/null values gracefully and performs case-sensitive matching.

    Args:
        dispatch_intent: Intent type from dispatch endpoint (can be string, Enum, or None)
        test_intent: Intent type from test endpoint (can be string, Enum, or None)

    Returns:
        True if both intent types are non-None and match exactly, False otherwise

    Examples:
        >>> compare_intent_type("status", "status")
        True
        >>> compare_intent_type("status", "action")
        False
        >>> compare_intent_type(None, "status")
        False
        >>> compare_intent_type("status", None)
        False
        >>> compare_intent_type(None, None)
        False

    Note:
        None values never match — missing intent type is always a failure.
        This ensures that absent intent fields are detected as differences.
    """
    # Handle None values - return False if either is None
    if dispatch_intent is None or test_intent is None:
        return False

    # Handle Enum values (extract the string value)
    if hasattr(dispatch_intent, 'value'):
        dispatch_intent = dispatch_intent.value
    if hasattr(test_intent, 'value'):
        test_intent = test_intent.value

    # Ensure both are strings
    if not isinstance(dispatch_intent, str) or not isinstance(test_intent, str):
        return False

    # Case-sensitive string comparison
    return dispatch_intent == test_intent


def compare_confidence(
    dispatch_confidence: Any,
    test_confidence: Any,
    tolerance: float = 0.01
) -> bool:
    """
    Compare confidence scores with tolerance for floating-point arithmetic.

    This function compares two confidence scores, allowing for a small tolerance
    to handle floating-point precision issues. It handles None/null values
    gracefully and validates input types.

    Args:
        dispatch_confidence: Confidence score from dispatch endpoint (float or None)
        test_confidence: Confidence score from test endpoint (float or None)
        tolerance: Maximum allowed difference between scores (default: 0.01)

    Returns:
        True if both scores are non-None and within tolerance, False otherwise

    Examples:
        >>> compare_confidence(0.9, 0.9)
        True
        >>> compare_confidence(0.9, 0.91, tolerance=0.02)
        True
        >>> compare_confidence(0.9, 0.85)
        False
        >>> compare_confidence(None, 0.9)
        False
        >>> compare_confidence(0.9, None)
        False
        >>> compare_confidence(1.5, 1.6)  # Values outside [0,1] still compared
        True

    Note:
        None values never match — missing confidence scores are always a failure.
        Values outside the [0,1] range are still compared (no range validation).
        Use a larger tolerance for comparisons with lower-precision scores.
    """
    import math

    # Handle None values - return False if either is None
    if dispatch_confidence is None or test_confidence is None:
        return False

    # Ensure both are numeric (int or float)
    if not isinstance(dispatch_confidence, (int, float)) or not isinstance(test_confidence, (int, float)):
        return False

    # Convert to float for comparison
    dispatch_float = float(dispatch_confidence)
    test_float = float(test_confidence)

    # Handle infinity values - they match only if both are the same infinity
    if math.isinf(dispatch_float) or math.isinf(test_float):
        return dispatch_float == test_float

    # Compare with tolerance, accounting for floating-point precision
    # Use math.isclose for better floating-point comparison
    return math.isclose(dispatch_float, test_float, abs_tol=tolerance)


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
