"""
Unit tests for structured field comparison with nested handling.

Tests the _compare_nested_structures helper and the extended compare_classifications
function to ensure proper handling of nested dicts, lists, None values, and type mismatches.

Acceptance criteria from bead adc-6995o4:
- Structured result comparison: recursive comparison of nested dicts/lists
- FieldDiff created for each differing field with full path (e.g., 'result.found_entities[0].name')
- Handles None values consistently (treat None and missing key the same)
- Handles type mismatches between expected/actual (e.g., str vs int)
- Accumulates all field diffs in detailed_diffs list
"""

from src.validation.comparison import (
    _compare_nested_structures,
    compare_classifications,
)


class TestCompareNestedStructures:
    """Test suite for _compare_nested_structures helper function."""

    def test_flat_structured_results_match(self):
        """Verify flat structured result with matching primitives."""
        expected = {"project": "adc", "status": "running", "count": 5}
        actual = {"project": "adc", "status": "running", "count": 5}

        diffs = []
        field_matches = {}
        result = _compare_nested_structures(
            expected, actual, "structured_result", diffs, field_matches
        )

        assert result is True
        assert field_matches["structured_result.project"] is True
        assert field_matches["structured_result.status"] is True
        assert field_matches["structured_result.count"] is True
        # No parent-level entry in field_matches
        assert "structured_result" not in field_matches
        assert len(diffs) == 3  # 3 leaf fields only
        assert all(d.is_match for d in diffs)

    def test_flat_structured_results_mismatch(self):
        """Verify flat structured result with mismatched primitives."""
        expected = {"project": "adc", "status": "running"}
        actual = {"project": "different", "status": "stopped"}

        diffs = []
        field_matches = {}
        result = _compare_nested_structures(
            expected, actual, "structured_result", diffs, field_matches
        )

        assert result is False
        assert field_matches["structured_result.project"] is False
        assert field_matches["structured_result.status"] is False
        # No parent-level entry in field_matches
        assert "structured_result" not in field_matches
        assert len(diffs) == 2
        assert not any(d.is_match for d in diffs)

    def test_nested_dict_match(self):
        """Verify nested dictionary comparison with all matches."""
        expected = {
            "parameters": {
                "project": "adc",
                "urgency": "high",
                "metadata": {
                    "tags": ["urgent", "review"],
                    "nested": {"key": "value"}
                }
            }
        }
        actual = {
            "parameters": {
                "project": "adc",
                "urgency": "high",
                "metadata": {
                    "tags": ["urgent", "review"],
                    "nested": {"key": "value"}
                }
            }
        }

        diffs = []
        field_matches = {}
        result = _compare_nested_structures(
            expected, actual, "structured_result", diffs, field_matches
        )

        assert result is True
        assert field_matches["structured_result.parameters.project"] is True
        assert field_matches["structured_result.parameters.urgency"] is True
        assert field_matches["structured_result.parameters.metadata.tags"] is True
        assert field_matches["structured_result.parameters.metadata.nested.key"] is True

    def test_nested_dict_mismatch(self):
        """Verify nested dictionary comparison with mismatches."""
        expected = {
            "parameters": {
                "project": "adc",
                "urgency": "high"
            }
        }
        actual = {
            "parameters": {
                "project": "different",
                "urgency": "low"
            }
        }

        diffs = []
        field_matches = {}
        result = _compare_nested_structures(
            expected, actual, "structured_result", diffs, field_matches
        )

        assert result is False
        assert field_matches["structured_result.parameters.project"] is False
        assert field_matches["structured_result.parameters.urgency"] is False
        # No parent-level entries in field_matches
        assert "structured_result.parameters" not in field_matches
        assert "structured_result" not in field_matches

    def test_list_element_match(self):
        """Verify list comparison with matching elements."""
        expected = {"entities": ["project", "status", "urgency"]}
        actual = {"entities": ["project", "status", "urgency"]}

        diffs = []
        field_matches = {}
        result = _compare_nested_structures(
            expected, actual, "structured_result", diffs, field_matches
        )

        assert result is True
        # List of primitives gets parent entry
        assert field_matches["structured_result.entities"] is True
        # No individual element entries for primitive lists
        assert "structured_result.entities[0]" not in field_matches

    def test_list_element_mismatch(self):
        """Verify list comparison with mismatched elements."""
        expected = {"entities": ["project", "status"]}
        actual = {"entities": ["project", "different"]}

        diffs = []
        field_matches = {}
        result = _compare_nested_structures(
            expected, actual, "structured_result", diffs, field_matches
        )

        assert result is False
        # For primitive lists, mismatch is detected at list level
        assert field_matches["structured_result.entities"] is False

    def test_list_length_mismatch(self):
        """Verify list comparison with different lengths."""
        expected = {"entities": ["project", "status"]}
        actual = {"entities": ["project", "status", "extra"]}

        diffs = []
        field_matches = {}
        result = _compare_nested_structures(
            expected, actual, "structured_result", diffs, field_matches
        )

        assert result is False
        # Find the diff for the list itself
        list_diff = next(d for d in diffs if d.field_name == "structured_result.entities")
        assert list_diff.is_match is False
        assert "list[2]" in str(list_diff.expected_value)
        assert "list[3]" in str(list_diff.actual_value)

    def test_missing_key_vs_none_value(self):
        """Verify that missing key and None value are treated consistently."""
        # Test case 1: Missing key in actual (treated as None)
        expected = {"project": "adc", "status": None}
        actual = {"project": "adc"}  # status is missing

        diffs = []
        field_matches = {}
        result = _compare_nested_structures(
            expected, actual, "structured_result", diffs, field_matches
        )

        assert result is True  # None vs missing should match
        assert field_matches["structured_result.status"] is True

        # Test case 2: Both None
        expected = {"project": "adc", "status": None}
        actual = {"project": "adc", "status": None}

        diffs = []
        field_matches = {}
        result = _compare_nested_structures(
            expected, actual, "structured_result", diffs, field_matches
        )

        assert result is True
        assert field_matches["structured_result.status"] is True

    def test_none_vs_value_mismatch(self):
        """Verify None vs actual value is treated as mismatch."""
        expected = {"project": None}
        actual = {"project": "adc"}

        diffs = []
        field_matches = {}
        result = _compare_nested_structures(
            expected, actual, "structured_result", diffs, field_matches
        )

        assert result is False
        assert field_matches["structured_result.project"] is False

        none_diff = next(d for d in diffs if d.field_name == "structured_result.project")
        assert none_diff.expected_value is None
        assert none_diff.actual_value == "adc"
        assert none_diff.is_match is False

    def test_type_mismatch_str_vs_int(self):
        """Verify type mismatch between string and int."""
        expected = {"count": "5"}
        actual = {"count": 5}

        diffs = []
        field_matches = {}
        result = _compare_nested_structures(
            expected, actual, "structured_result", diffs, field_matches
        )

        assert result is False
        assert field_matches["structured_result.count"] is False

        type_diff = next(d for d in diffs if d.field_name == "structured_result.count")
        assert type_diff.expected_value == "5"
        assert type_diff.actual_value == 5
        assert type_diff.is_match is False

    def test_type_mismatch_dict_vs_list(self):
        """Verify type mismatch between dict and list."""
        expected = {"data": {"key": "value"}}
        actual = {"data": ["item1", "item2"]}

        diffs = []
        field_matches = {}
        result = _compare_nested_structures(
            expected, actual, "structured_result", diffs, field_matches
        )

        assert result is False
        assert field_matches["structured_result.data"] is False

        type_diff = next(d for d in diffs if d.field_name == "structured_result.data")
        assert isinstance(type_diff.expected_value, dict)
        assert isinstance(type_diff.actual_value, list)
        assert type_diff.is_match is False

    def test_nested_missing_key(self):
        """Verify missing key in nested structure."""
        expected = {"parameters": {"project": "adc", "urgency": "high"}}
        actual = {"parameters": {"project": "adc"}}  # urgency missing

        diffs = []
        field_matches = {}
        result = _compare_nested_structures(
            expected, actual, "structured_result", diffs, field_matches
        )

        assert result is False
        assert field_matches["structured_result.parameters.urgency"] is False
        # No parent-level entry
        assert "structured_result.parameters" not in field_matches

    def test_deeply_nested_structure(self):
        """Verify deeply nested dictionary comparison."""
        expected = {
            "level1": {
                "level2": {
                    "level3": {
                        "level4": "deep_value"
                    }
                }
            }
        }
        actual = {
            "level1": {
                "level2": {
                    "level3": {
                        "level4": "deep_value"
                    }
                }
            }
        }

        diffs = []
        field_matches = {}
        result = _compare_nested_structures(
            expected, actual, "structured_result", diffs, field_matches
        )

        assert result is True
        assert field_matches["structured_result.level1.level2.level3.level4"] is True

    def test_partial_nested_mismatch(self):
        """Verify partial mismatch in nested structure."""
        expected = {
            "parameters": {
                "project": "adc",
                "urgency": "high",
                "metadata": {"tags": ["urgent"]}
            }
        }
        actual = {
            "parameters": {
                "project": "adc",  # Match
                "urgency": "low",  # Mismatch
                "metadata": {"tags": ["review"]}  # Mismatch
            }
        }

        diffs = []
        field_matches = {}
        result = _compare_nested_structures(
            expected, actual, "structured_result", diffs, field_matches
        )

        assert result is False
        assert field_matches["structured_result.parameters.project"] is True
        assert field_matches["structured_result.parameters.urgency"] is False
        assert field_matches["structured_result.parameters.metadata.tags"] is False
        # No parent-level entries
        assert "structured_result.parameters.metadata" not in field_matches
        assert "structured_result.parameters" not in field_matches

    def test_list_of_dicts_match(self):
        """Verify comparison of lists containing dictionaries."""
        expected = {
            "items": [
                {"id": 1, "name": "first"},
                {"id": 2, "name": "second"}
            ]
        }
        actual = {
            "items": [
                {"id": 1, "name": "first"},
                {"id": 2, "name": "second"}
            ]
        }

        diffs = []
        field_matches = {}
        result = _compare_nested_structures(
            expected, actual, "structured_result", diffs, field_matches
        )

        assert result is True
        assert field_matches["structured_result.items"] is True
        assert field_matches["structured_result.items[0].id"] is True
        assert field_matches["structured_result.items[1].name"] is True

    def test_list_of_dicts_mismatch(self):
        """Verify mismatch detection in lists of dictionaries."""
        expected = {
            "items": [
                {"id": 1, "name": "first"},
                {"id": 2, "name": "second"}
            ]
        }
        actual = {
            "items": [
                {"id": 1, "name": "first"},
                {"id": 2, "name": "different"}  # Mismatch
            ]
        }

        diffs = []
        field_matches = {}
        result = _compare_nested_structures(
            expected, actual, "structured_result", diffs, field_matches
        )

        assert result is False
        assert field_matches["structured_result.items[1].name"] is False

    def test_float_tolerance_match(self):
        """Verify float comparison with tolerance."""
        expected = {"confidence": 0.9}
        actual = {"confidence": 0.899}  # Within 0.01 tolerance

        diffs = []
        field_matches = {}
        result = _compare_nested_structures(
            expected, actual, "structured_result", diffs, field_matches,
            confidence_tolerance=0.01
        )

        assert result is True
        assert field_matches["structured_result.confidence"] is True

    def test_float_tolerance_exceeded(self):
        """Verify float comparison fails when tolerance exceeded."""
        expected = {"confidence": 0.9}
        actual = {"confidence": 0.85}  # Exceeds 0.01 tolerance

        diffs = []
        field_matches = {}
        result = _compare_nested_structures(
            expected, actual, "structured_result", diffs, field_matches,
            confidence_tolerance=0.01
        )

        assert result is False
        assert field_matches["structured_result.confidence"] is False

    def test_int_float_mix_match(self):
        """Verify int and float comparison works."""
        expected = {"count": 5}
        actual = {"count": 5.0}

        diffs = []
        field_matches = {}
        result = _compare_nested_structures(
            expected, actual, "structured_result", diffs, field_matches,
            confidence_tolerance=0.01
        )

        assert result is True
        assert field_matches["structured_result.count"] is True
        # Check that the diff was created
        count_diff = next(d for d in diffs if d.field_name == "structured_result.count")
        assert count_diff.is_match is True


class TestCompareClassificationsStructuredResult:
    """Test suite for compare_classifications with structured_result."""

    def test_full_match_with_structured_result(self):
        """Verify full match including structured_result."""
        expected = {
            "intent_type": "status",
            "confidence": 0.9,
            "structured_result": {"project": "adc", "status": "running"}
        }
        actual = {
            "intent_type": "status",
            "confidence": 0.9,
            "structured_result": {"project": "adc", "status": "running"}
        }

        result = compare_classifications(expected, actual, early_return=False)

        assert result.intent_match is True
        assert result.confidence_match is True
        # Check leaf-level structured result fields
        assert "structured_result.project" in result.field_matches
        assert result.field_matches["structured_result.project"] is True
        assert result.field_matches["structured_result.status"] is True
        # Verify corresponding diffs exist
        structured_diffs = [d for d in result.diffs if d.field_name.startswith("structured_result")]
        assert len(structured_diffs) >= 2

    def test_structured_result_mismatch(self):
        """Verify structured_result mismatch is detected."""
        expected = {
            "intent_type": "status",
            "confidence": 0.9,
            "structured_result": {"project": "adc"}
        }
        actual = {
            "intent_type": "status",
            "confidence": 0.9,
            "structured_result": {"project": "different"}
        }

        result = compare_classifications(expected, actual, early_return=False)

        assert result.intent_match is True
        assert result.confidence_match is True
        assert result.field_matches["structured_result.project"] is False

    def test_structured_result_none_vs_dict(self):
        """Verify structured_result None vs dict is mismatch."""
        expected = {
            "intent_type": "status",
            "confidence": 0.9,
            "structured_result": None
        }
        actual = {
            "intent_type": "status",
            "confidence": 0.9,
            "structured_result": {"project": "adc"}
        }

        result = compare_classifications(expected, actual, early_return=False)

        assert result.intent_match is True
        assert result.confidence_match is True
        assert result.field_matches["structured_result"] is False

    def test_structured_result_both_none(self):
        """Verify structured_result both None is match."""
        expected = {
            "intent_type": "status",
            "confidence": 0.9,
            "structured_result": None
        }
        actual = {
            "intent_type": "status",
            "confidence": 0.9,
            "structured_result": None
        }

        result = compare_classifications(expected, actual, early_return=False)

        assert result.intent_match is True
        assert result.confidence_match is True
        # When both are None, a single diff is created
        assert result.field_matches["structured_result"] is True
        structured_diffs = [d for d in result.diffs if d.field_name == "structured_result"]
        assert len(structured_diffs) == 1
        assert structured_diffs[0].is_match is True

    def test_nested_structured_result_match(self):
        """Verify nested structured_result match."""
        expected = {
            "intent_type": "action",
            "confidence": 0.85,
            "structured_result": {
                "project": "adc",
                "metadata": {
                    "tags": ["urgent", "review"]
                }
            }
        }
        actual = {
            "intent_type": "action",
            "confidence": 0.85,
            "structured_result": {
                "project": "adc",
                "metadata": {
                    "tags": ["urgent", "review"]
                }
            }
        }

        result = compare_classifications(expected, actual, early_return=False)

        assert result.intent_match is True
        assert result.confidence_match is True
        # Check leaf-level fields
        assert result.field_matches["structured_result.project"] is True
        # List of primitives gets parent entry
        assert result.field_matches["structured_result.metadata.tags"] is True
        # Verify corresponding diffs exist
        structured_diffs = [d for d in result.diffs if d.field_name.startswith("structured_result")]
        assert len(structured_diffs) >= 2

    def test_nested_structured_result_mismatch(self):
        """Verify nested structured_result mismatch."""
        expected = {
            "intent_type": "action",
            "confidence": 0.85,
            "structured_result": {
                "project": "adc",
                "metadata": {"tags": ["urgent"]}
            }
        }
        actual = {
            "intent_type": "action",
            "confidence": 0.85,
            "structured_result": {
                "project": "adc",
                "metadata": {"tags": ["review"]}  # Different
            }
        }

        result = compare_classifications(expected, actual, early_return=False)

        assert result.intent_match is True
        assert result.confidence_match is True
        # List mismatch is detected at list level for primitive lists
        assert result.field_matches["structured_result.metadata.tags"] is False
        # Verify corresponding diff exists
        tags_diff = next((d for d in result.diffs if d.field_name == "structured_result.metadata.tags"), None)
        assert tags_diff is not None
        assert tags_diff.is_match is False

    def test_early_return_on_structured_result_mismatch(self):
        """Verify early return works with structured_result."""
        expected = {
            "intent_type": "status",
            "confidence": 0.9,
            "structured_result": {"project": "adc"}
        }
        actual = {
            "intent_type": "status",
            "confidence": 0.9,
            "structured_result": {"project": "different"}
        }

        result = compare_classifications(expected, actual, early_return=True)

        # Should return early after structured_result mismatch
        assert result.intent_match is True
        assert result.confidence_match is True
        assert result.field_matches["structured_result.project"] is False
        # Verify corresponding diff exists
        project_diff = next((d for d in result.diffs if d.field_name == "structured_result.project"), None)
        assert project_diff is not None
        assert project_diff.is_match is False

    def test_field_diff_full_path_creation(self):
        """Verify FieldDiff objects created with full paths."""
        expected = {
            "intent_type": "status",
            "confidence": 0.9,
            "structured_result": {
                "metadata": {
                    "tags": ["urgent", "review"]
                }
            }
        }
        actual = {
            "intent_type": "status",
            "confidence": 0.9,
            "structured_result": {
                "metadata": {
                    "tags": ["different", "review"]
                }
            }
        }

        result = compare_classifications(expected, actual, early_return=False)

        # For primitive lists, the diff is at the list level, not element level
        tags_diff = next(
            (d for d in result.diffs if d.field_name == "structured_result.metadata.tags"),
            None
        )
        assert tags_diff is not None
        assert tags_diff.expected_value == ["urgent", "review"]
        assert tags_diff.actual_value == ["different", "review"]
        assert tags_diff.is_match is False

    def test_all_field_diffs_accumulated(self):
        """Verify all field diffs are accumulated in detailed_diffs list."""
        expected = {
            "intent_type": "status",
            "confidence": 0.9,
            "structured_result": {
                "project": "adc",
                "count": 5,
                "metadata": {
                    "tags": ["urgent"]
                }
            }
        }
        actual = {
            "intent_type": "action",  # Mismatch
            "confidence": 0.8,  # Mismatch
            "structured_result": {
                "project": "different",  # Mismatch
                "count": 10,  # Mismatch
                "metadata": {
                    "tags": ["review"]  # Mismatch
                }
            }
        }

        result = compare_classifications(expected, actual, early_return=False)

        # Should have diffs for all mismatched fields
        assert len(result.diffs) >= 5  # intent, confidence, and structured_result fields

        # Check specific field diffs exist
        field_names = {d.field_name for d in result.diffs}
        assert "intent_type" in field_names
        assert "confidence" in field_names
        assert "structured_result.project" in field_names
        assert "structured_result.count" in field_names
        assert "structured_result.metadata.tags" in field_names  # List-level diff

    def test_missing_structured_result_in_expected(self):
        """Verify missing structured_result in expected is handled."""
        expected = {
            "intent_type": "status",
            "confidence": 0.9
        }
        actual = {
            "intent_type": "status",
            "confidence": 0.9,
            "structured_result": {"project": "adc"}
        }

        result = compare_classifications(expected, actual, early_return=False)

        assert result.intent_match is True
        assert result.confidence_match is True
        # Missing in expected means None vs actual dict → mismatch
        assert result.field_matches["structured_result"] is False

    def test_missing_structured_result_in_actual(self):
        """Verify missing structured_result in actual is handled."""
        expected = {
            "intent_type": "status",
            "confidence": 0.9,
            "structured_result": {"project": "adc"}
        }
        actual = {
            "intent_type": "status",
            "confidence": 0.9
        }

        result = compare_classifications(expected, actual, early_return=False)

        assert result.intent_match is True
        assert result.confidence_match is True
        # Missing in actual means expected dict vs None → mismatch
        assert result.field_matches["structured_result"] is False


class TestFieldDiffPathFormats:
    """Test FieldDiff path formats for different structures."""

    def test_field_diff_path_flat(self):
        """Verify FieldDiff path for flat structure."""
        expected = {"structured_result": {"key": "value"}}
        actual = {"structured_result": {"key": "different"}}

        result = compare_classifications(expected, actual, early_return=False)

        key_diff = next(d for d in result.diffs if d.field_name == "structured_result.key")
        assert key_diff.field_name == "structured_result.key"
        assert key_diff.expected_value == "value"
        assert key_diff.actual_value == "different"
        assert key_diff.is_match is False

    def test_field_diff_path_nested(self):
        """Verify FieldDiff path for nested structure."""
        expected = {
            "structured_result": {
                "level1": {
                    "level2": "value"
                }
            }
        }
        actual = {
            "structured_result": {
                "level1": {
                    "level2": "different"
                }
            }
        }

        result = compare_classifications(expected, actual, early_return=False)

        nested_diff = next(d for d in result.diffs if "level2" in d.field_name)
        assert nested_diff.field_name == "structured_result.level1.level2"
        assert nested_diff.expected_value == "value"
        assert nested_diff.actual_value == "different"
        assert nested_diff.is_match is False

    def test_field_diff_path_list_indexed(self):
        """Verify FieldDiff path for list mismatches."""
        expected = {
            "structured_result": {
                "items": ["a", "b", "c"]
            }
        }
        actual = {
            "structured_result": {
                "items": ["a", "different", "c"]
            }
        }

        result = compare_classifications(expected, actual, early_return=False)

        # For primitive lists, diff is at list level
        list_diff = next(d for d in result.diffs if d.field_name == "structured_result.items")
        assert list_diff.field_name == "structured_result.items"
        assert list_diff.expected_value == ["a", "b", "c"]
        assert list_diff.actual_value == ["a", "different", "c"]
        assert list_diff.is_match is False
