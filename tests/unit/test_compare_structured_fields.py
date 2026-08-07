"""
Unit tests for compare_structured_fields function.

Tests the structured field comparison logic used to validate
endpoint equivalence between /dispatch and /test/intent-classify.
"""

import pytest
from src.intent.comparison import compare_structured_fields


# Pytest fixtures for sample classification results
@pytest.fixture
def sample_dispatch_fields():
    """Sample dispatch endpoint fields for testing."""
    return {
        "project_slug": "aide-de-camp",
        "confidence": 0.9,
        "intent_type": "status",
    }


@pytest.fixture
def sample_test_fields():
    """Sample test endpoint fields for testing."""
    return {
        "project_slug": "aide-de-camp",
        "confidence": 0.9,
        "intent_type": "status",
    }


@pytest.fixture
def nested_dispatch_fields():
    """Sample nested dispatch fields."""
    return {
        "parameters": {
            "project": "adc",
            "urgency": "high",
        },
        "entities": ["project", "status"],
    }


@pytest.fixture
def nested_test_fields():
    """Sample nested test fields."""
    return {
        "parameters": {
            "project": "adc",
            "urgency": "high",
        },
        "entities": ["status", "project"],  # Different order
    }


class TestCompareStructuredFields:
    """Test suite for compare_structured_fields function."""

    def test_empty_dicts_both_inputs(self):
        """Test that empty dicts return empty result (all match)."""
        dispatch_fields = {}
        test_fields = {}

        result = compare_structured_fields(dispatch_fields, test_fields)

        assert result == {}, f"Expected empty dict, got {result}"

    def test_both_none_inputs(self):
        """Test that both None inputs return empty result."""
        result = compare_structured_fields(None, None)

        assert result == {}, f"Expected empty dict for None inputs, got {result}"

    def test_simple_match(self):
        """Test simple field match with identical values."""
        dispatch = {"project_slug": "aide-de-camp", "confidence": 0.9}
        test = {"project_slug": "aide-de-camp", "confidence": 0.9}

        result = compare_structured_fields(dispatch, test)

        assert result["project_slug"] is True
        assert result["confidence"] is True

    def test_simple_mismatch(self):
        """Test simple field mismatch with different values."""
        dispatch = {"project_slug": "aide-de-camp"}
        test = {"project_slug": "different-project"}

        result = compare_structured_fields(dispatch, test)

        assert result["project_slug"] is False

    def test_nested_dict_match(self, nested_dispatch_fields, nested_test_fields):
        """Test nested dictionary comparison."""
        result = compare_structured_fields(nested_dispatch_fields, nested_test_fields)

        # All nested fields should match
        assert result["parameters.project"] is True
        assert result["parameters.urgency"] is True

    def test_list_comparison_order_insensitive(self, nested_dispatch_fields, nested_test_fields):
        """Test that list comparison is order-insensitive by default."""
        result = compare_structured_fields(nested_dispatch_fields, nested_test_fields)

        # Entities list should match despite different order
        assert result["entities"] is True

    def test_float_tolerance(self):
        """Test that float comparison uses tolerance."""
        dispatch = {"confidence": 0.9}
        test = {"confidence": 0.899}  # Within 0.01 tolerance

        result = compare_structured_fields(dispatch, test)

        assert result["confidence"] is True

    def test_float_exceeds_tolerance(self):
        """Test that floats exceeding tolerance are marked as mismatch."""
        dispatch = {"confidence": 0.9}
        test = {"confidence": 0.85}  # Exceeds 0.01 tolerance

        result = compare_structured_fields(dispatch, test)

        assert result["confidence"] is False

    def test_missing_field_in_test(self):
        """Test detection of missing field in test result."""
        dispatch = {"project_slug": "adc", "confidence": 0.9}
        test = {"project_slug": "adc"}  # Missing confidence

        result = compare_structured_fields(dispatch, test)

        assert "confidence" in result
        assert result["confidence"] is False

    def test_missing_field_in_dispatch(self):
        """Test detection of missing field in dispatch result."""
        dispatch = {"project_slug": "adc"}  # Missing confidence
        test = {"project_slug": "adc", "confidence": 0.9}

        result = compare_structured_fields(dispatch, test)

        assert "confidence" in result
        assert result["confidence"] is False

    def test_completely_different_dicts(self):
        """Test comparison of completely different dictionaries with no overlapping keys."""
        dispatch = {"project_slug": "adc", "confidence": 0.9}
        test = {"intent_type": "status", "urgency": "high"}

        result = compare_structured_fields(dispatch, test)

        # All fields should be marked as mismatch
        assert len(result) == 4  # All 4 fields from both dicts
        assert all(value is False for value in result.values())

    def test_two_level_nested_dict_match(self):
        """Test nested dict comparison at 2 levels of depth."""
        dispatch = {
            "metadata": {
                "project": "adc",
                "version": "1.0.0"
            }
        }
        test = {
            "metadata": {
                "project": "adc",
                "version": "1.0.0"
            }
        }

        result = compare_structured_fields(dispatch, test)

        # Should return match results for nested fields using dot notation
        assert "metadata.project" in result
        assert "metadata.version" in result
        assert result["metadata.project"] is True
        assert result["metadata.version"] is True

    def test_two_level_nested_dict_mismatch(self):
        """Test nested dict comparison with mismatch at 2 levels."""
        dispatch = {
            "metadata": {
                "project": "adc",
                "version": "1.0.0"
            }
        }
        test = {
            "metadata": {
                "project": "different-project",
                "version": "1.0.0"
            }
        }

        result = compare_structured_fields(dispatch, test)

        # Should detect mismatch in nested field
        assert "metadata.project" in result
        assert "metadata.version" in result
        assert result["metadata.project"] is False
        assert result["metadata.version"] is True

    def test_three_level_nested_dict_match(self):
        """Test nested dict comparison at 3 levels of depth."""
        dispatch = {
            "metadata": {
                "config": {
                    "project": "adc",
                    "threshold": 0.9
                }
            }
        }
        test = {
            "metadata": {
                "config": {
                    "project": "adc",
                    "threshold": 0.9
                }
            }
        }

        result = compare_structured_fields(dispatch, test)

        # Should traverse 3 levels with dot notation
        assert "metadata.config.project" in result
        assert "metadata.config.threshold" in result
        assert result["metadata.config.project"] is True
        assert result["metadata.config.threshold"] is True

    def test_three_level_nested_dict_mismatch(self):
        """Test nested dict comparison with mismatch at 3 levels."""
        dispatch = {
            "metadata": {
                "config": {
                    "project": "adc",
                    "threshold": 0.9
                }
            }
        }
        test = {
            "metadata": {
                "config": {
                    "project": "adc",
                    "threshold": 0.5  # Different value
                }
            }
        }

        result = compare_structured_fields(dispatch, test)

        # Should detect mismatch at deepest level
        assert "metadata.config.project" in result
        assert "metadata.config.threshold" in result
        assert result["metadata.config.project"] is True
        assert result["metadata.config.threshold"] is False

    def test_mixed_flat_and_nested_dict(self):
        """Test comparison with mixed flat and nested fields."""
        dispatch = {
            "project_slug": "adc",  # Flat field
            "confidence": 0.9,     # Flat field
            "metadata": {          # Nested field
                "version": "1.0.0",
                "env": "production"
            }
        }
        test = {
            "project_slug": "adc",
            "confidence": 0.9,
            "metadata": {
                "version": "1.0.0",
                "env": "production"
            }
        }

        result = compare_structured_fields(dispatch, test)

        # Should have both flat and nested field results
        assert "project_slug" in result
        assert "confidence" in result
        assert "metadata.version" in result
        assert "metadata.env" in result
        assert result["project_slug"] is True
        assert result["confidence"] is True
        assert result["metadata.version"] is True
        assert result["metadata.env"] is True

    def test_mixed_flat_and_nested_with_partial_mismatch(self):
        """Test comparison with mixed flat/nested and some mismatches."""
        dispatch = {
            "project_slug": "adc",
            "confidence": 0.9,
            "metadata": {
                "version": "1.0.0",
                "env": "production"
            }
        }
        test = {
            "project_slug": "different-project",  # Mismatch
            "confidence": 0.9,
            "metadata": {
                "version": "2.0.0",  # Mismatch
                "env": "production"
            }
        }

        result = compare_structured_fields(dispatch, test)

        # Should detect mismatches at both flat and nested levels
        assert "project_slug" in result
        assert "confidence" in result
        assert "metadata.version" in result
        assert "metadata.env" in result
        assert result["project_slug"] is False
        assert result["confidence"] is True
        assert result["metadata.version"] is False
        assert result["metadata.env"] is True

    def test_nested_dict_with_missing_child_field(self):
        """Test nested dict comparison when child field is missing in one dict."""
        dispatch = {
            "metadata": {
                "project": "adc",
                "version": "1.0.0"
            }
        }
        test = {
            "metadata": {
                "project": "adc"
                # version is missing
            }
        }

        result = compare_structured_fields(dispatch, test)

        # Should detect missing nested field
        assert "metadata.project" in result
        assert "metadata.version" in result
        assert result["metadata.project"] is True
        assert result["metadata.version"] is False

    def test_deeply_nested_four_levels(self):
        """Test nested dict comparison at 4 levels to verify recursion depth."""
        dispatch = {
            "level1": {
                "level2": {
                    "level3": {
                        "level4": "deep_value",
                        "sibling": "other_value"
                    }
                }
            }
        }
        test = {
            "level1": {
                "level2": {
                    "level3": {
                        "level4": "deep_value",
                        "sibling": "other_value"
                    }
                }
            }
        }

        result = compare_structured_fields(dispatch, test)

        # Should traverse all 4 levels
        assert "level1.level2.level3.level4" in result
        assert "level1.level2.level3.sibling" in result
        assert result["level1.level2.level3.level4"] is True
        assert result["level1.level2.level3.sibling"] is True


class TestListComparison:
    """Test suite for order-insensitive list comparison."""

    def test_list_of_strings_same_elements_different_order(self):
        """Test that lists of strings match regardless of order."""
        dispatch = {"tags": ["project", "status", "urgent"]}
        test = {"tags": ["urgent", "project", "status"]}

        result = compare_structured_fields(dispatch, test)

        assert result["tags"] is True

    def test_list_of_strings_different_elements(self):
        """Test that lists with different string elements don't match."""
        dispatch = {"tags": ["project", "status"]}
        test = {"tags": ["project", "different"]}

        result = compare_structured_fields(dispatch, test)

        assert result["tags"] is False

    def test_list_of_integers_same_elements_different_order(self):
        """Test that lists of integers match regardless of order."""
        dispatch = {"counts": [1, 2, 3, 4]}
        test = {"counts": [4, 3, 2, 1]}

        result = compare_structured_fields(dispatch, test)

        assert result["counts"] is True

    def test_list_of_floats_same_elements_different_order(self):
        """Test that lists of floats match regardless of order."""
        dispatch = {"scores": [0.1, 0.5, 0.9]}
        test = {"scores": [0.9, 0.1, 0.5]}

        result = compare_structured_fields(dispatch, test)

        assert result["scores"] is True

    def test_list_of_booleans_same_elements_different_order(self):
        """Test that lists of booleans match regardless of order."""
        dispatch = {"flags": [True, False, True]}
        test = {"flags": [True, True, False]}

        result = compare_structured_fields(dispatch, test)

        assert result["flags"] is True

    def test_list_of_strings_different_lengths(self):
        """Test that lists of different lengths don't match."""
        dispatch = {"tags": ["project", "status"]}
        test = {"tags": ["project", "status", "urgent"]}

        result = compare_structured_fields(dispatch, test)

        assert result["tags"] is False

    def test_list_of_integers_different_lengths(self):
        """Test that integer lists of different lengths don't match."""
        dispatch = {"counts": [1, 2, 3]}
        test = {"counts": [1, 2]}

        result = compare_structured_fields(dispatch, test)

        assert result["counts"] is False

    def test_list_of_dicts_same_elements_different_order(self):
        """Test that lists of dicts match by comparing dict fields, not identity."""
        dispatch = {
            "entities": [
                {"name": "project", "type": "resource"},
                {"name": "status", "type": "query"}
            ]
        }
        test = {
            "entities": [
                {"name": "status", "type": "query"},
                {"name": "project", "type": "resource"}
            ]
        }

        result = compare_structured_fields(dispatch, test)

        assert result["entities"] is True

    def test_list_of_dicts_different_nested_values(self):
        """Test that lists of dicts with different values don't match."""
        dispatch = {
            "entities": [
                {"name": "project", "type": "resource"},
                {"name": "status", "type": "query"}
            ]
        }
        test = {
            "entities": [
                {"name": "project", "type": "different"},
                {"name": "status", "type": "query"}
            ]
        }

        result = compare_structured_fields(dispatch, test)

        assert result["entities"] is False

    def test_list_of_dicts_different_keys(self):
        """Test that lists of dicts with different keys don't match."""
        dispatch = {
            "entities": [
                {"name": "project", "type": "resource"},
            ]
        }
        test = {
            "entities": [
                {"name": "project", "category": "resource"},
            ]
        }

        result = compare_structured_fields(dispatch, test)

        assert result["entities"] is False

    def test_list_of_dicts_different_lengths(self):
        """Test that lists of dicts with different lengths don't match."""
        dispatch = {
            "entities": [
                {"name": "project", "type": "resource"},
            ]
        }
        test = {
            "entities": [
                {"name": "project", "type": "resource"},
                {"name": "status", "type": "query"}
            ]
        }

        result = compare_structured_fields(dispatch, test)

        assert result["entities"] is False

    def test_nested_list_of_primitives(self):
        """Test nested lists containing primitive values."""
        dispatch = {
            "metadata": {
                "tags": ["alpha", "beta"]
            }
        }
        test = {
            "metadata": {
                "tags": ["beta", "alpha"]
            }
        }

        result = compare_structured_fields(dispatch, test)

        assert "metadata.tags" in result
        assert result["metadata.tags"] is True

    def test_nested_list_of_dicts(self):
        """Test nested lists containing dictionaries."""
        dispatch = {
            "metadata": {
                "entities": [
                    {"name": "project", "value": 1},
                    {"name": "status", "value": 2}
                ]
            }
        }
        test = {
            "metadata": {
                "entities": [
                    {"name": "status", "value": 2},
                    {"name": "project", "value": 1}
                ]
            }
        }

        result = compare_structured_fields(dispatch, test)

        assert "metadata.entities" in result
        assert result["metadata.entities"] is True

    def test_empty_lists_match(self):
        """Test that empty lists match."""
        dispatch = {"items": []}
        test = {"items": []}

        result = compare_structured_fields(dispatch, test)

        assert result["items"] is True

    def test_list_with_single_element_matches(self):
        """Test that single-element lists match."""
        dispatch = {"items": ["single"]}
        test = {"items": ["single"]}

        result = compare_structured_fields(dispatch, test)

        assert result["items"] is True

    def test_list_with_duplicates_matches(self):
        """Test that lists with duplicate elements match correctly."""
        dispatch = {"items": ["a", "b", "a"]}
        test = {"items": ["a", "a", "b"]}

        result = compare_structured_fields(dispatch, test)

        assert result["items"] is True

    def test_list_with_different_duplicate_counts_doesnt_match(self):
        """Test that lists with different duplicate counts don't match."""
        dispatch = {"items": ["a", "b", "a"]}
        test = {"items": ["a", "b", "b"]}

        result = compare_structured_fields(dispatch, test)

        assert result["items"] is False

    def test_mixed_type_list_matches(self):
        """Test that lists with mixed comparable types match."""
        dispatch = {"items": [1, "two", 3.0]}
        test = {"items": [3.0, 1, "two"]}

        result = compare_structured_fields(dispatch, test)

        assert result["items"] is True

    def test_mixed_type_list_different_elements_doesnt_match(self):
        """Test that mixed type lists with different elements don't match."""
        dispatch = {"items": [1, "two", 3.0]}
        test = {"items": [1, "different", 3.0]}

        result = compare_structured_fields(dispatch, test)

        assert result["items"] is False


class TestEdgeCases:
    """Test suite for comprehensive edge case handling.

    This test class verifies that the comparison logic correctly handles
    boundary conditions and None/empty value semantics.
    """

    def test_none_vs_none_matches(self):
        """Test that None vs None results in a match for that field."""
        dispatch = {"field": None}
        test = {"field": None}

        result = compare_structured_fields(dispatch, test)

        assert result["field"] is True

    def test_none_vs_value_mismatches(self):
        """Test that None vs any non-None value results in mismatch."""
        dispatch = {"field": None}
        test = {"field": "value"}

        result = compare_structured_fields(dispatch, test)

        assert result["field"] is False

    def test_value_vs_none_mismatches(self):
        """Test that any non-None value vs None results in mismatch."""
        dispatch = {"field": "value"}
        test = {"field": None}

        result = compare_structured_fields(dispatch, test)

        assert result["field"] is False

    def test_none_vs_empty_dict_mismatches(self):
        """Test that None vs empty dict are semantically different (mismatch)."""
        dispatch = {"field": None}
        test = {"field": {}}

        result = compare_structured_fields(dispatch, test)

        assert result["field"] is False

    def test_empty_dict_vs_none_mismatches(self):
        """Test that empty dict vs None are semantically different (mismatch)."""
        dispatch = {"field": {}}
        test = {"field": None}

        result = compare_structured_fields(dispatch, test)

        assert result["field"] is False

    def test_none_vs_empty_list_mismatches(self):
        """Test that None vs empty list are semantically different (mismatch)."""
        dispatch = {"field": None}
        test = {"field": []}

        result = compare_structured_fields(dispatch, test)

        assert result["field"] is False

    def test_empty_list_vs_none_mismatches(self):
        """Test that empty list vs None are semantically different (mismatch)."""
        dispatch = {"field": []}
        test = {"field": None}

        result = compare_structured_fields(dispatch, test)

        assert result["field"] is False

    def test_empty_dict_vs_empty_dict_matches(self):
        """Test that empty dict vs empty dict results in match."""
        dispatch = {"field": {}}
        test = {"field": {}}

        result = compare_structured_fields(dispatch, test)

        assert result["field"] is True

    def test_empty_list_vs_empty_list_matches(self):
        """Test that empty list vs empty list results in match."""
        dispatch = {"field": []}
        test = {"field": []}

        result = compare_structured_fields(dispatch, test)

        assert result["field"] is True

    def test_missing_key_in_dispatch_mismatches(self):
        """Test that missing key in dispatch_fields results in mismatch."""
        dispatch = {"other_field": "value"}
        test = {"field": "value"}

        result = compare_structured_fields(dispatch, test)

        assert "field" in result
        assert result["field"] is False

    def test_missing_key_in_test_mismatches(self):
        """Test that missing key in test_fields results in mismatch."""
        dispatch = {"field": "value"}
        test = {"other_field": "value"}

        result = compare_structured_fields(dispatch, test)

        assert "field" in result
        assert result["field"] is False

    def test_nested_empty_dict_vs_none_mismatches(self):
        """Test that nested empty dict vs None results in mismatch."""
        dispatch = {"outer": {}}
        test = {"outer": None}

        result = compare_structured_fields(dispatch, test)

        assert result["outer"] is False

    def test_nested_empty_list_vs_none_mismatches(self):
        """Test that nested empty list vs None results in mismatch."""
        dispatch = {"outer": []}
        test = {"outer": None}

        result = compare_structured_fields(dispatch, test)

        assert result["outer"] is False

    def test_nested_none_vs_empty_dict_mismatches(self):
        """Test that nested None vs empty dict results in mismatch."""
        dispatch = {"outer": None}
        test = {"outer": {}}

        result = compare_structured_fields(dispatch, test)

        assert result["outer"] is False

    def test_nested_none_vs_empty_list_mismatches(self):
        """Test that nested None vs empty list results in mismatch."""
        dispatch = {"outer": None}
        test = {"outer": []}

        result = compare_structured_fields(dispatch, test)

        assert result["outer"] is False

    def test_multiple_fields_with_none_and_values(self):
        """Test multiple fields where some are None and some have values."""
        dispatch = {
            "field1": None,
            "field2": "value",
            "field3": None,
        }
        test = {
            "field1": None,
            "field2": "value",
            "field3": "different",
        }

        result = compare_structured_fields(dispatch, test)

        assert result["field1"] is True  # None vs None
        assert result["field2"] is True  # value vs value
        assert result["field3"] is False  # None vs value

    def test_mixed_empty_and_none_fields(self):
        """Test mix of empty dicts, empty lists, and None values."""
        dispatch = {
            "empty_dict": {},
            "empty_list": [],
            "none_field": None,
            "normal_field": "value",
        }
        test = {
            "empty_dict": {},
            "empty_list": [],
            "none_field": None,
            "normal_field": "value",
        }

        result = compare_structured_fields(dispatch, test)

        assert result["empty_dict"] is True
        assert result["empty_list"] is True
        assert result["none_field"] is True
        assert result["normal_field"] is True

    def test_empty_vs_populated_dict_mismatches(self):
        """Test that empty dict vs populated dict results in mismatch."""
        dispatch = {"field": {}}
        test = {"field": {"key": "value"}}

        result = compare_structured_fields(dispatch, test)

        # Empty vs populated dict should be marked as mismatch
        assert "field" in result or "field.key" in result
        # At least one field should show mismatch
        assert any(v is False for v in result.values())

    def test_empty_vs_populated_list_mismatches(self):
        """Test that empty list vs populated list results in mismatch."""
        dispatch = {"field": []}
        test = {"field": ["item"]}

        result = compare_structured_fields(dispatch, test)

        assert result["field"] is False

    def test_deeply_nested_with_none_at_leaf(self):
        """Test deeply nested structure with None at leaf level."""
        dispatch = {
            "level1": {
                "level2": {
                    "level3": None
                }
            }
        }
        test = {
            "level1": {
                "level2": {
                    "level3": None
                }
            }
        }

        result = compare_structured_fields(dispatch, test)

        # Should handle deep nesting with None values
        assert "level1.level2.level3" in result
        assert result["level1.level2.level3"] is True

    def test_deeply_nested_none_vs_value(self):
        """Test deeply nested structure with None vs value at leaf."""
        dispatch = {
            "level1": {
                "level2": {
                    "level3": None
                }
            }
        }
        test = {
            "level1": {
                "level2": {
                    "level3": "value"
                }
            }
        }

        result = compare_structured_fields(dispatch, test)

        assert "level1.level2.level3" in result
        assert result["level1.level2.level3"] is False

    def test_none_in_list_vs_none_in_list(self):
        """Test lists containing None values."""
        dispatch = {"items": [None, "value", None]}
        test = {"items": [None, "value", None]}

        result = compare_structured_fields(dispatch, test)

        # Lists with None values should match
        assert result["items"] is True

    def test_none_in_list_vs_value_in_list(self):
        """Test lists with different None/value patterns."""
        dispatch = {"items": [None, "value"]}
        test = {"items": ["different", "value"]}

        result = compare_structured_fields(dispatch, test)

        # Different patterns should mismatch
        assert result["items"] is False
