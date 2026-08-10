"""
Unified classification comparison with comprehensive edge case handling.

This module provides the main compare_classifications function that integrates
all comparison logic and returns a standardized ComparisonReport. It handles:
- Intent type comparison
- Confidence score comparison with tolerance
- Structured field comparison (nested dicts, lists, primitives)
- Edge cases: missing keys, null values, type mismatches, nested structures

The function returns True for overall_match only if ALL components match.
"""

import math
from typing import Any, Dict, List, Optional, Tuple, Union

# Import comparison structures
from src.validation.comparison import (
    ComparisonReport,
    FieldDiff,
)
from src.validation.comparison import (
    ComparisonResult as ValidationComparisonResult,
)


def normalize_input_to_classifications(
    result: Optional[Union[List[Dict], Dict]], source: str = "unknown"
) -> List[Dict[str, Any]]:
    """
    Normalize various input formats to a list of classification dicts.

    Args:
        result: Input in various formats:
            - List of classification dicts
            - Dict with 'classifications' key
            - Dispatch dict with a 'results' key
            - Dict with nested 'classification' in RoutedIntent structure
            - None or an empty response
        source: Source name for error messages

    Returns:
        List of normalized classification dicts

    Edge cases handled:
        - None input
        - Empty dict/list
        - Missing 'classifications' key
        - RoutedIntent structure with nested classification
        - Enum values that need extraction
    """
    classifications, _is_valid, _reason = _normalize_input(result, source)
    return classifications


def _normalize_input(
    result: Any, source: str = "unknown"
) -> Tuple[List[Dict[str, Any]], bool, str]:
    """Normalize an endpoint response while retaining whether its shape is valid.

    The public normalizer intentionally returns only a list for backwards
    compatibility. The comparison function also needs to distinguish a valid
    empty response from an invalid response such as ``"not a dict"``; otherwise
    malformed values would compare equal to ``{}`` after both became ``[]``.
    """
    if result is None:
        return [], True, f"{source} result is empty"

    if isinstance(result, list):
        if not result:
            return [], True, f"{source} result contains no classifications"
        if not all(isinstance(item, dict) for item in result):
            return [], False, f"{source} result list contains a non-dict item"
        return _normalize_classification_items(result, source)

    if not isinstance(result, dict):
        return [], False, f"{source} result must be a dict, list, or None"

    # An empty dictionary is a valid empty endpoint response and is equivalent
    # to None/[] for comparison purposes.
    if not result:
        return [], True, f"{source} result is an empty dictionary"

    # /test/intent-classify returns ``classifications`` while /test/dispatch
    # returns ``results`` when it includes the completed classifications.
    envelope_key = None
    if "classifications" in result:
        envelope_key = "classifications"
    elif "results" in result:
        envelope_key = "results"

    if envelope_key is not None:
        items = result[envelope_key]
        if not isinstance(items, list):
            return [], False, (
                f"{source} result field '{envelope_key}' must be a list"
            )
        if not items:
            return [], True, f"{source} result contains no classifications"
        if not all(isinstance(item, dict) for item in items):
            return [], False, (
                f"{source} result field '{envelope_key}' contains a non-dict item"
            )
        return _normalize_classification_items(items, source)

    # A single flat classification or a single RoutedIntent is also accepted.
    if (
        "intent_type" in result
        or "project_slug" in result
        or "classification" in result
    ):
        return _normalize_classification_items([result], source)

    return [], False, f"{source} result has no classifications envelope"


def _normalize_classification_items(
    items: List[Dict[str, Any]], source: str
) -> Tuple[List[Dict[str, Any]], bool, str]:
    """Extract flat classification dictionaries from validated input items."""
    classifications: List[Dict[str, Any]] = []
    for item in items:
        if "classification" in item:
            classifications.append(_extract_classification_from_routed_intent(item))
        else:
            classifications.append(item)
    return classifications, True, f"{source} result normalized successfully"


def _extract_classification_from_routed_intent(
    routed_intent: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Extract classification data from a RoutedIntent structure.

    Args:
        routed_intent: RoutedIntent dict with nested classification

    Returns:
        Flattened classification dict

    Edge cases handled:
        - Missing 'classification' key
        - Enum values for intent_type
        - None values in nested fields
    """
    if "classification" not in routed_intent:
        # Not a RoutedIntent, return as-is
        return routed_intent

    classification = routed_intent["classification"]

    # Handle None classification
    if classification is None:
        return {
            "intent_type": None,
            "project_slug": None,
            "confidence": None,
            "utterance_fragment": None,
            "reasoning": None,
            "urgency": None,
            "lookup_kind": None,
        }

    # A malformed nested value should be reported as a classification mismatch,
    # not raise an AttributeError or silently disappear from the comparison.
    if not isinstance(classification, dict):
        return {
            "intent_type": None,
            "project_slug": None,
            "confidence": None,
            "utterance_fragment": None,
            "reasoning": None,
            "urgency": None,
            "lookup_kind": None,
            "structured_result": None,
        }

    # Handle intent_type as enum or dict or string
    intent_type = classification.get("intent_type")
    if isinstance(intent_type, dict):
        intent_type = intent_type.get("value")
    elif hasattr(intent_type, 'value'):
        # Enum
        intent_type = intent_type.value
    elif intent_type is None:
        intent_type = None

    return {
        "intent_type": intent_type,
        "project_slug": classification.get("project_slug"),
        "confidence": classification.get("confidence"),
        "utterance_fragment": classification.get("utterance_fragment"),
        "reasoning": classification.get("reasoning"),
        "urgency": classification.get("urgency"),
        "lookup_kind": classification.get("lookup_kind"),
        "structured_result": classification.get("structured_result"),
    }


def safe_get(data: Dict[str, Any], field: str, default: Any = None) -> Any:
    """
    Safely get a field from a dict with extensive edge case handling.

    Args:
        data: Dictionary to extract from (can be None)
        field: Field name to extract
        default: Default value if field is missing or None

    Returns:
        Field value or default

    Edge cases handled:
        - data is None
        - field is missing
        - field value is None
        - nested None values
        - Type mismatches
    """
    if data is None:
        return default

    if not isinstance(data, dict):
        # Not a dict, can't extract
        return default

    value = data.get(field)

    # Return default if value is None
    if value is None:
        return default

    return value


def compare_intent_types(dispatch_intent: Any, test_intent: Any) -> bool:
    """
    Compare intent type values with comprehensive edge case handling.

    Args:
        dispatch_intent: Intent type from dispatch (string, Enum, dict, or None)
        test_intent: Intent type from test (string, Enum, dict, or None)

    Returns:
        True if both intent types match exactly, False otherwise

    Edge cases handled:
        - None values (never match)
        - Enum values (extract value)
        - Dict values with 'value' key
        - Type mismatches (string vs int vs None)
        - Empty strings
    """
    # Handle None values - None never matches
    if dispatch_intent is None or test_intent is None:
        return False

    # Handle empty strings - treat as missing
    if isinstance(dispatch_intent, str) and not dispatch_intent.strip():
        return False
    if isinstance(test_intent, str) and not test_intent.strip():
        return False

    # Handle Enum values
    if hasattr(dispatch_intent, 'value'):
        dispatch_intent = dispatch_intent.value
    if hasattr(test_intent, 'value'):
        test_intent = test_intent.value

    # Handle dict with 'value' key
    if isinstance(dispatch_intent, dict):
        dispatch_intent = dispatch_intent.get("value")
    if isinstance(test_intent, dict):
        test_intent = test_intent.get("value")

    # Re-check for None after extraction
    if dispatch_intent is None or test_intent is None:
        return False

    # Ensure both are strings
    if not isinstance(dispatch_intent, str) or not isinstance(test_intent, str):
        return False

    # Case-sensitive string comparison
    return dispatch_intent == test_intent


def compare_confidence_scores(
    dispatch_confidence: Any,
    test_confidence: Any,
    tolerance: float = 0.01
) -> bool:
    """
    Compare confidence scores with tolerance and edge case handling.

    Args:
        dispatch_confidence: Confidence from dispatch (float, int, string, or None)
        test_confidence: Confidence from test (float, int, string, or None)
        tolerance: Maximum allowed difference (default: 0.01)

    Returns:
        True if scores match within tolerance, False otherwise

    Edge cases handled:
        - None values (never match)
        - String representations of numbers
        - Integer vs float comparison
        - Out-of-range values (< 0 or > 1)
        - Infinity values
        - NaN values
    """
    # Handle None values
    if dispatch_confidence is None or test_confidence is None:
        return False

    # Handle string representations
    if isinstance(dispatch_confidence, str):
        try:
            dispatch_confidence = float(dispatch_confidence)
        except (ValueError, TypeError):
            return False
    if isinstance(test_confidence, str):
        try:
            test_confidence = float(test_confidence)
        except (ValueError, TypeError):
            return False

    # Ensure both are numeric
    if not isinstance(dispatch_confidence, (int, float)):
        return False
    if not isinstance(test_confidence, (int, float)):
        return False

    # Convert to float
    dispatch_float = float(dispatch_confidence)
    test_float = float(test_confidence)

    # Handle NaN
    if math.isnan(dispatch_float) or math.isnan(test_float):
        return False  # NaN never matches

    # Handle infinity
    if math.isinf(dispatch_float) or math.isinf(test_float):
        # Only match if both are the same infinity
        return dispatch_float == test_float

    # Handle out-of-range values (< 0 or > 1)
    # Still compare them, but could log a warning
    if dispatch_float < 0.0 or dispatch_float > 1.0:
        pass  # Out of range, but still compare
    if test_float < 0.0 or test_float > 1.0:
        pass  # Out of range, but still compare

    # Compare with tolerance
    return math.isclose(dispatch_float, test_float, abs_tol=tolerance)


def compare_structured_field(
    dispatch_field: Any,
    test_field: Any,
    field_name: str = "field",
    tolerance: float = 0.01
) -> bool:
    """
    Compare structured field values with comprehensive type handling.

    Args:
        dispatch_field: Field value from dispatch result
        test_field: Field value from test result
        field_name: Name of the field (for error reporting)
        tolerance: Tolerance for numeric comparison

    Returns:
        True if fields match, False otherwise

    Edge cases handled:
        - None values
        - Type mismatches (dict vs list vs primitive)
        - Nested None values in dicts/lists
        - Float comparison with tolerance
        - List order (order-insensitive by default)
        - Empty dicts/lists
        - String comparison (case-sensitive)
    """
    # Both None - match
    if dispatch_field is None and test_field is None:
        return True

    # One None, one not - mismatch
    if dispatch_field is None or test_field is None:
        return False

    # Same type - compare appropriately
    if type(dispatch_field) is type(test_field):
        if isinstance(dispatch_field, dict):
            return compare_dicts(dispatch_field, test_field, tolerance)
        elif isinstance(dispatch_field, list):
            return compare_lists(dispatch_field, test_field, tolerance)
        elif isinstance(dispatch_field, (int, float)):
            return math.isclose(dispatch_field, test_field, abs_tol=tolerance)
        else:
            # String, bool, etc. - exact comparison
            return dispatch_field == test_field

    # Different types - try to be flexible
    # Numeric comparison (int vs float)
    if isinstance(dispatch_field, (int, float)) and isinstance(test_field, (int, float)):
        return math.isclose(float(dispatch_field), float(test_field), abs_tol=tolerance)

    # All other type mismatches - fail
    return False


def compare_dicts(dict1: Dict, dict2: Dict, tolerance: float = 0.01) -> bool:
    """
    Compare two dictionaries recursively.

    Args:
        dict1: First dictionary
        dict2: Second dictionary
        tolerance: Tolerance for numeric comparison

    Returns:
        True if dicts match, False otherwise

    Edge cases handled:
        - Different key sets
        - Nested None values
        - Nested dicts
        - Nested lists
        - Mixed types
    """
    if not isinstance(dict1, dict) or not isinstance(dict2, dict):
        return False

    keys1 = set(dict1.keys())
    keys2 = set(dict2.keys())

    # Different key sets
    if keys1 != keys2:
        return False

    # Compare each key
    for key in keys1:
        val1 = dict1[key]
        val2 = dict2[key]

        # Both None - continue
        if val1 is None and val2 is None:
            continue

        # One None - mismatch
        if val1 is None or val2 is None:
            return False

        # Same type comparison
        if type(val1) is type(val2):
            if isinstance(val1, dict):
                if not compare_dicts(val1, val2, tolerance):
                    return False
            elif isinstance(val1, list):
                if not compare_lists(val1, val2, tolerance):
                    return False
            elif isinstance(val1, (int, float)):
                if not math.isclose(val1, val2, abs_tol=tolerance):
                    return False
            else:
                if val1 != val2:
                    return False
        else:
            # Type mismatch
            return False

    return True


def compare_lists(list1: List, list2: List, tolerance: float = 0.01) -> bool:
    """
    Compare two lists (order-insensitive).

    Args:
        list1: First list
        list2: Second list
        tolerance: Tolerance for numeric comparison

    Returns:
        True if lists match, False otherwise

    Edge cases handled:
        - Different lengths
        - Nested dicts (compare by structure)
        - Nested lists (recursive)
        - Primitive comparison with tolerance
        - Empty lists
    """
    if not isinstance(list1, list) or not isinstance(list2, list):
        return False

    if len(list1) != len(list2):
        return False

    # Order-insensitive comparison
    # For primitives, use sorted comparison
    # For complex types, use multiset comparison

    # Try to sort and compare
    try:
        return sorted(list1) == sorted(list2)
    except TypeError:
        # Can't sort (complex types) - use element-by-element matching
        list1_copy = list1.copy()
        for item2 in list2:
            found = False
            for i, item1 in enumerate(list1_copy):
                if type(item1) is type(item2):
                    if isinstance(item1, dict):
                        if compare_dicts(item1, item2, tolerance):
                            list1_copy.pop(i)
                            found = True
                            break
                    elif isinstance(item1, list):
                        if compare_lists(item1, item2, tolerance):
                            list1_copy.pop(i)
                            found = True
                            break
                    elif isinstance(item1, (int, float)):
                        if math.isclose(item1, item2, abs_tol=tolerance):
                            list1_copy.pop(i)
                            found = True
                            break
                    else:
                        if item1 == item2:
                            list1_copy.pop(i)
                            found = True
                            break
            if not found:
                return False

        return len(list1_copy) == 0


def compare_classifications(
    dispatch_result: Optional[Union[List[Dict], Dict]],
    test_result: Optional[Union[List[Dict], Dict]],
    confidence_tolerance: float = 0.01,
) -> ComparisonReport:
    """
    Unified classification comparison with comprehensive edge case handling.

    This is the main comparison function that integrates all comparison logic:
    - Intent type comparison
    - Confidence score comparison with tolerance
    - Structured field comparison (nested dicts, lists, primitives)
    - Edge case handling (missing keys, null values, type mismatches)

    Args:
        dispatch_result: Classifications from /dispatch endpoint
            - Can be a list of classification dicts
            - Can be a dict with 'classifications' key
            - Can be a dispatch response dict with 'results' key
            - Can contain RoutedIntent structures with nested 'classification'
        test_result: Classifications from /test/intent-classify endpoint
            - Can be a list of classification dicts
            - Can be a dict with 'classifications' key
            - None and empty responses represent zero classifications
        confidence_tolerance: Tolerance for confidence comparison (default: 0.01)

    Returns:
        ComparisonReport with:
        - overall_match: True only if ALL components match
        - summary: Human-readable summary
        - detailed diffs: List[FieldDiff] for each field comparison

    Edge cases handled:
        - None/empty inputs
        - Missing keys in classifications
        - Null values for any field
        - Type mismatches between fields
        - Nested None values in structured results
        - Empty vs missing keys (treated consistently)
        - Enum values in intent_type
        - Numeric tolerance for confidence
        - Order-insensitive list comparison
        - Invalid top-level types produce a mismatch report instead of being
          treated as an empty response

    Examples:
        >>> # Perfect match
        >>> dispatch = {"classifications": [
        ...     {"intent_type": "status", "project_slug": "adc", "confidence": 0.9}
        ... ]}
        >>> test = {"classifications": [
        ...     {"intent_type": "status", "project_slug": "adc", "confidence": 0.9}
        ... ]}
        >>> report = compare_classifications(dispatch, test)
        >>> assert report.overall_match is True

        >>> # Confidence mismatch
        >>> dispatch = {"classifications": [
        ...     {"intent_type": "status", "confidence": 0.9}
        ... ]}
        >>> test = {"classifications": [
        ...     {"intent_type": "status", "confidence": 0.8}
        ... ]}
        >>> report = compare_classifications(dispatch, test)
        >>> assert not report.overall_match
    """
    # Normalize inputs to lists of classifications. Keep the validity bit so a
    # malformed top-level value (for example, a string) cannot be mistaken for
    # a valid empty response after normalization.
    dispatch_classifications, dispatch_valid, dispatch_reason = _normalize_input(
        dispatch_result, "dispatch"
    )
    test_classifications, test_valid, test_reason = _normalize_input(
        test_result, "test"
    )

    if not dispatch_valid or not test_valid:
        invalid_sources = []
        if not dispatch_valid:
            invalid_sources.append(f"dispatch: {dispatch_reason}")
        if not test_valid:
            invalid_sources.append(f"test: {test_reason}")
        reason = "; ".join(invalid_sources)
        invalid_result = ValidationComparisonResult(
            intent_match=False,
            confidence_match=False,
            field_matches={"top_level_type": False},
            diffs=[
                FieldDiff(
                    field_name="top_level_type",
                    expected_value="dict, list, or None containing classifications",
                    actual_value=reason,
                    is_match=False,
                )
            ],
        )
        return ComparisonReport(
            total_comparisons=1,
            matching_count=0,
            partial_match_count=0,
            mismatch_count=1,
            results=[invalid_result],
            summary=f"✗ Invalid comparison input: {reason}",
        )

    # Track results for each classification
    all_results: List[ValidationComparisonResult] = []

    # Check count mismatch
    dispatch_count = len(dispatch_classifications)
    test_count = len(test_classifications)

    # Compare up to the minimum count
    min_count = min(dispatch_count, test_count)
    max_count = max(dispatch_count, test_count)

    # Compare each classification pair
    for i in range(min_count):
        dispatch_cls = dispatch_classifications[i]
        test_cls = test_classifications[i]

        # Compare individual fields
        result = _compare_single_classification(
            dispatch_cls, test_cls, i, confidence_tolerance
        )
        all_results.append(result)

    # Handle count mismatch
    if dispatch_count != test_count:
        # Add results for the extra classifications
        for i in range(min_count, max_count):
            if i < dispatch_count:
                # Extra dispatch classification
                result = ValidationComparisonResult(
                    intent_match=False,
                    confidence_match=False,
                    field_matches={
                        "count_mismatch": False,
                    },
                    diffs=[
                        FieldDiff(
                            field_name="count_mismatch",
                            expected_value=f"test classification {i}",
                            actual_value=f"dispatch classification {i}",
                            is_match=False,
                        )
                    ],
                )
            else:
                # Extra test classification
                result = ValidationComparisonResult(
                    intent_match=False,
                    confidence_match=False,
                    field_matches={
                        "count_mismatch": False,
                    },
                    diffs=[
                        FieldDiff(
                            field_name="count_mismatch",
                            expected_value=f"test classification {i}",
                            actual_value=f"dispatch classification {i}",
                            is_match=False,
                        )
                    ],
                )
            all_results.append(result)

    # Calculate summary statistics
    # Full match: ALL fields match (including intent, confidence, and all other fields)
    matching_count = sum(1 for r in all_results if all(r.field_matches.values()))

    # A core-field failure is a mismatch even when the other core field (or an
    # optional field) matches. A partial match is reserved for classifications
    # whose intent and confidence both match but whose structured/optional data
    # does not. This keeps the report useful to callers that gate on either core
    # comparison independently.
    mismatch_count = sum(1 for r in all_results if (
        "count_mismatch" in r.field_matches
        or not (r.intent_match and r.confidence_match)
    ))

    partial_match_count = sum(1 for r in all_results if (
        "count_mismatch" not in r.field_matches
        and r.intent_match
        and r.confidence_match
        and not all(r.field_matches.values())
    ))

    # Build summary
    if dispatch_count == 0 and test_count == 0:
        summary = "Both endpoints returned no classifications"
    elif matching_count == max_count and dispatch_count == test_count and mismatch_count == 0:
        summary = f"✓ Perfect match: {matching_count} classifications identical"
    else:
        if dispatch_count != test_count:
            summary = (
                f"✗ Count mismatch: test={test_count}, dispatch={dispatch_count}. "
                f"{matching_count} full matches, {partial_match_count} partial matches, {mismatch_count} mismatches"
            )
        else:
            summary = (
                f"✗ {mismatch_count} mismatch(es): {matching_count} full matches, "
                f"{partial_match_count} partial matches out of {len(all_results)} total"
            )

    return ComparisonReport(
        total_comparisons=len(all_results),
        matching_count=matching_count,
        partial_match_count=partial_match_count,
        mismatch_count=mismatch_count,
        results=all_results,
        summary=summary,
    )


def _compare_single_classification(
    dispatch_cls: Dict[str, Any],
    test_cls: Dict[str, Any],
    index: int,
    confidence_tolerance: float = 0.01,
) -> ValidationComparisonResult:
    """
    Compare a single classification pair and return detailed result.

    Args:
        dispatch_cls: Classification from dispatch
        test_cls: Classification from test
        index: Index of the classification being compared
        confidence_tolerance: Tolerance for confidence comparison

    Returns:
        ValidationComparisonResult with detailed field comparisons
    """
    diffs: List[FieldDiff] = []
    field_matches: Dict[str, bool] = {}

    # Extract field values with explicit checking for field presence
    dispatch_intent = dispatch_cls.get("intent_type") if "intent_type" in dispatch_cls else None
    test_intent = test_cls.get("intent_type") if "intent_type" in test_cls else None

    dispatch_confidence = dispatch_cls.get("confidence") if "confidence" in dispatch_cls else None
    test_confidence = test_cls.get("confidence") if "confidence" in test_cls else None

    dispatch_project = dispatch_cls.get("project_slug") if "project_slug" in dispatch_cls else None
    test_project = test_cls.get("project_slug") if "project_slug" in test_cls else None

    dispatch_fragment = dispatch_cls.get("utterance_fragment") if "utterance_fragment" in dispatch_cls else None
    test_fragment = test_cls.get("utterance_fragment") if "utterance_fragment" in test_cls else None

    dispatch_reasoning = dispatch_cls.get("reasoning") if "reasoning" in dispatch_cls else None
    test_reasoning = test_cls.get("reasoning") if "reasoning" in test_cls else None

    dispatch_urgency = dispatch_cls.get("urgency") if "urgency" in dispatch_cls else None
    test_urgency = test_cls.get("urgency") if "urgency" in test_cls else None

    dispatch_lookup = dispatch_cls.get("lookup_kind") if "lookup_kind" in dispatch_cls else None
    test_lookup = test_cls.get("lookup_kind") if "lookup_kind" in test_cls else None

    dispatch_structured = dispatch_cls.get("structured_result") if "structured_result" in dispatch_cls else None
    test_structured = test_cls.get("structured_result") if "structured_result" in test_cls else None

    # Helper function to compare fields
    def compare_field(
        field_name: str,
        dispatch_val: Any,
        test_val: Any,
        compare_func=None,
        nulls_match: bool = True,
    ) -> bool:
        """
        Compare a field, handling missing and explicit null fields consistently.

        Rules:
        - If field is in both results: compare values
        - If field is in neither result: match (both missing)
        - Missing and explicit ``None`` are equivalent for optional fields
        - A missing optional field and a concrete value are a mismatch

        Required fields still use their comparator when present, so an explicit
        ``None`` intent or confidence never matches a concrete value (or another
        explicit ``None``). Both fields being absent is retained as a compatible
        legacy case for partially populated classification fixtures.
        """
        dispatch_has = field_name in dispatch_cls
        test_has = field_name in test_cls

        # Both absent is a consistent missing-value comparison. This is
        # important for fixtures that intentionally omit optional fields and is
        # also how the existing comparison API treats incomplete core fixtures.
        if not dispatch_has and not test_has:
            return True

        # Missing and explicit None represent the same absent optional value.
        # Required core fields opt out so explicit None remains a failed core
        # comparison, even when both sides contain it.
        if nulls_match and (not dispatch_has or dispatch_val is None) and (
            not test_has or test_val is None
        ):
            return True

        # Both have a concrete value - compare it using the field's rules.
        if dispatch_has and test_has:
            if compare_func:
                return compare_func(dispatch_val, test_val)
            return dispatch_val == test_val

        # One side has a concrete value while the other side is missing.
        return False

    # Compare intent_type
    intent_match = compare_field(
        "intent_type",
        dispatch_intent,
        test_intent,
        compare_intent_types,
        nulls_match=False,
    )
    field_matches["intent_type"] = intent_match
    diffs.append(FieldDiff(
        field_name="intent_type",
        expected_value=test_intent,
        actual_value=dispatch_intent,
        is_match=intent_match,
    ))

    # Compare confidence
    confidence_match = compare_field(
        "confidence", dispatch_confidence, test_confidence,
        lambda d, t: compare_confidence_scores(d, t, confidence_tolerance),
        nulls_match=False,
    )
    field_matches["confidence"] = confidence_match
    diffs.append(FieldDiff(
        field_name="confidence",
        expected_value=test_confidence,
        actual_value=dispatch_confidence,
        is_match=confidence_match,
    ))

    # ``project_slug`` is dispatch metadata and older RoutedIntent payloads may
    # omit it from the test endpoint. If it is present on only one side, treat
    # that omission like an absent optional value; when both endpoints provide
    # it, compare the concrete values normally.
    project_has_dispatch = "project_slug" in dispatch_cls
    project_has_test = "project_slug" in test_cls
    if project_has_dispatch and project_has_test:
        project_match = compare_field(
            "project_slug", dispatch_project, test_project
        )
    else:
        project_match = True
    field_matches["project_slug"] = project_match
    diffs.append(FieldDiff(
        field_name="project_slug",
        expected_value=test_project,
        actual_value=dispatch_project,
        is_match=project_match,
    ))

    # Compare utterance_fragment
    fragment_match = compare_field("utterance_fragment", dispatch_fragment, test_fragment)
    field_matches["utterance_fragment"] = fragment_match
    diffs.append(FieldDiff(
        field_name="utterance_fragment",
        expected_value=test_fragment,
        actual_value=dispatch_fragment,
        is_match=fragment_match,
    ))

    # Compare reasoning
    reasoning_match = compare_field("reasoning", dispatch_reasoning, test_reasoning)
    field_matches["reasoning"] = reasoning_match
    diffs.append(FieldDiff(
        field_name="reasoning",
        expected_value=test_reasoning,
        actual_value=dispatch_reasoning,
        is_match=reasoning_match,
    ))

    # Compare urgency
    urgency_match = compare_field("urgency", dispatch_urgency, test_urgency)
    field_matches["urgency"] = urgency_match
    diffs.append(FieldDiff(
        field_name="urgency",
        expected_value=test_urgency,
        actual_value=dispatch_urgency,
        is_match=urgency_match,
    ))

    # Compare lookup_kind
    lookup_match = compare_field("lookup_kind", dispatch_lookup, test_lookup)
    field_matches["lookup_kind"] = lookup_match
    diffs.append(FieldDiff(
        field_name="lookup_kind",
        expected_value=test_lookup,
        actual_value=dispatch_lookup,
        is_match=lookup_match,
    ))

    # Compare structured_result
    structured_match = compare_field(
        "structured_result", dispatch_structured, test_structured,
        lambda d, t: compare_structured_field(d, t, "structured_result", confidence_tolerance)
    )
    field_matches["structured_result"] = structured_match
    diffs.append(FieldDiff(
        field_name="structured_result",
        expected_value=test_structured,
        actual_value=dispatch_structured,
        is_match=structured_match,
    ))

    return ValidationComparisonResult(
        intent_match=intent_match,
        confidence_match=confidence_match,
        field_matches=field_matches,
        diffs=diffs,
    )
