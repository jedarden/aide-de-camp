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
