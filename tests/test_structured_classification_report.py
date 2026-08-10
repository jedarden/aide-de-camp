"""Structured-result coverage for the endpoint comparison report."""

from src.validation.classification_comparison import compare_classifications


def _classification(structured_result):
    return {
        "classifications": [
            {
                "intent_type": "status",
                "confidence": 0.9,
                "structured_result": structured_result,
            }
        ]
    }


def test_matching_structured_result_has_no_report_diffs():
    result = compare_classifications(
        _classification({"project": "adc", "status": "running"}),
        _classification({"project": "adc", "status": "running"}),
    )

    assert result.overall_match is True
    assert result.detailed_diffs == []


def test_nested_structured_diffs_include_all_full_paths():
    expected = _classification(
        {
            "found_entities": [
                {"name": "pod", "metadata": {"status": "running"}},
                {"name": "service"},
            ]
        }
    )
    actual = _classification(
        {
            "found_entities": [
                {"name": "deployment", "metadata": {"status": "failed"}},
                {"name": "service"},
            ]
        }
    )

    result = compare_classifications(expected, actual)

    assert result.overall_match is False
    assert {
        diff.field_name for diff in result.detailed_diffs
    } == {
        "classification_0_structured_result.found_entities[0].name",
        "classification_0_structured_result.found_entities[0].metadata.status",
    }


def test_nested_missing_key_and_none_are_equivalent():
    result = compare_classifications(
        _classification({"metadata": {"status": None}}),
        _classification({"metadata": {}}),
    )

    assert result.overall_match is True
    assert result.detailed_diffs == []


def test_nested_type_mismatches_are_reported_at_their_field_paths():
    result = compare_classifications(
        _classification({"count": "5", "payload": {"key": "value"}}),
        _classification({"count": 5, "payload": ["value"]}),
    )

    assert result.overall_match is False
    assert {
        diff.field_name for diff in result.detailed_diffs
    } == {
        "classification_0_structured_result.count",
        "classification_0_structured_result.payload",
    }
