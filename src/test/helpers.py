"""
Test Helpers Module

Provides helper functions for testing aide-de-camp functionality.
"""
import json
from pathlib import Path
from typing import Any, Optional
from logging import getLogger

logger = getLogger(__name__)


def load_test_utterances() -> dict[str, Any]:
    """
    Load pre-canned test utterances from the fixtures file.

    Returns a dictionary containing:
    - metadata: Information about the utterance suite
    - utterances: Categorized utterances by type

    Returns:
        Dictionary with test utterances organized by type

    Raises:
        FileNotFoundError: If the utterances.json file doesn't exist
        json.JSONDecodeError: If the file contains invalid JSON

    Example:
        >>> utterances = load_test_utterances()
        >>> project_utterances = utterances['utterances']['project']
        >>> for utterance in project_utterances:
        ...     print(utterance['utterance'])
    """
    fixtures_path = Path(__file__).parent / "fixtures" / "utterances.json"

    if not fixtures_path.exists():
        raise FileNotFoundError(f"Test utterances file not found: {fixtures_path}")

    try:
        with open(fixtures_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        logger.info(f"Loaded {data.get('metadata', {}).get('total_utterances', 0)} test utterances from {fixtures_path}")
        return data

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse test utterances JSON: {e}")
        raise


def get_utterances_by_type(topic_type: str) -> list[dict[str, Any]]:
    """
    Get all utterances for a specific topic type.

    Args:
        topic_type: The topic type to filter by
                   ('project', 'research', 'personal', 'exception', 'compound', 'edge_cases')

    Returns:
        List of utterance dictionaries for the specified type

    Raises:
        ValueError: If the topic_type is not recognized

    Example:
        >>> project_utts = get_utterances_by_type('project')
        >>> print(len(project_utts))
        5
    """
    data = load_test_utterances()
    utterances = data.get('utterances', {})

    if topic_type not in utterances:
        available_types = ', '.join(utterances.keys())
        raise ValueError(
            f"Unknown topic type '{topic_type}'. "
            f"Available types: {available_types}"
        )

    return utterances[topic_type]


def get_utterance_by_name(name: str) -> Optional[dict[str, Any]]:
    """
    Find a specific utterance by its name across all types.

    Args:
        name: The name of the utterance to find

    Returns:
        The utterance dictionary if found, None otherwise

    Example:
        >>> utterance = get_utterance_by_name('project_status_pods')
        >>> print(utterance['utterance'])
        'how are the pods doing in options pipeline'
    """
    data = load_test_utterances()
    utterances = data.get('utterances', {})

    for topic_type, utterance_list in utterances.items():
        for utterance in utterance_list:
            if utterance.get('name') == name:
                return utterance

    return None


def get_all_utterances_flat() -> list[dict[str, Any]]:
    """
    Get all utterances as a flat list with type annotation.

    Returns:
        List of utterance dictionaries, each with a 'topic_type' field
        indicating which category they belong to

    Example:
        >>> all_utts = get_all_utterances_flat()
        >>> for utt in all_utts:
        ...     print(f"{utt['topic_type']}: {utt['name']}")
    """
    data = load_test_utterances()
    utterances = data.get('utterances', {})

    flat_list = []
    for topic_type, utterance_list in utterances.items():
        for utterance in utterance_list:
            # Add topic_type to each utterance
            utterance_with_type = utterance.copy()
            utterance_with_type['topic_type'] = topic_type
            flat_list.append(utterance_with_type)

    return flat_list


def get_utterance_count() -> dict[str, int]:
    """
    Get the count of utterances per type.

    Returns:
        Dictionary with topic types as keys and counts as values

    Example:
        >>> counts = get_utterance_count()
        >>> print(counts)
        {'project': 5, 'research': 5, 'personal': 5, 'exception': 5, 'compound': 5, 'edge_cases': 10}
    """
    data = load_test_utterances()
    utterances = data.get('utterances', {})

    counts = {}
    for topic_type, utterance_list in utterances.items():
        counts[topic_type] = len(utterance_list)

    return counts


def validate_utterance_suite() -> dict[str, Any]:
    """
    Validate the utterance suite for completeness and correctness.

    Checks:
    - All required topic types are present
    - Each type has minimum required utterances (3 per type)
    - Required fields are present in each utterance
    - No duplicate utterance names

    Returns:
        Dictionary with validation results:
        - valid: Boolean indicating overall validation status
        - errors: List of error messages
        - warnings: List of warning messages
        - summary: Summary statistics

    Example:
        >>> result = validate_utterance_suite()
        >>> if result['valid']:
        ...     print("All checks passed!")
    """
    result = {
        'valid': True,
        'errors': [],
        'warnings': [],
        'summary': {}
    }

    try:
        data = load_test_utterances()
        utterances = data.get('utterances', {})
        metadata = data.get('metadata', {})

        # Check metadata
        if 'version' not in metadata:
            result['warnings'].append("Missing version in metadata")

        # Required topic types
        required_types = {'project', 'research', 'personal', 'exception', 'compound', 'edge_cases'}
        present_types = set(utterances.keys())

        missing_types = required_types - present_types
        if missing_types:
            result['errors'].append(f"Missing required topic types: {missing_types}")
            result['valid'] = False

        # Check minimum utterances per type (3 required, but edge_cases can have more)
        for topic_type in required_types:
            if topic_type in utterances:
                utterance_count = len(utterances[topic_type])
                minimum_required = 3 if topic_type != 'edge_cases' else 5

                if utterance_count < minimum_required:
                    result['errors'].append(
                        f"Topic type '{topic_type}' has only {utterance_count} utterances, "
                        f"minimum {minimum_required} required"
                    )
                    result['valid'] = False

                result['summary'][topic_type] = utterance_count

        # Check for required fields in each utterance
        all_names = set()
        for topic_type, utterance_list in utterances.items():
            for i, utterance in enumerate(utterance_list):
                # Check required fields
                required_fields = ['name', 'utterance']
                missing_fields = [field for field in required_fields if field not in utterance]

                if missing_fields:
                    result['errors'].append(
                        f"Utterance {i+1} in '{topic_type}' missing fields: {missing_fields}"
                    )
                    result['valid'] = False

                # Check for duplicate names
                utterance_name = utterance.get('name')
                if utterance_name:
                    if utterance_name in all_names:
                        result['errors'].append(f"Duplicate utterance name: '{utterance_name}'")
                        result['valid'] = False
                    all_names.add(utterance_name)

        # Update summary
        result['summary']['total_utterances'] = sum(len(utterances[t]) for t in utterances)
        result['summary']['total_types'] = len(utterances)

    except FileNotFoundError as e:
        result['valid'] = False
        result['errors'].append(f"Test utterances file not found: {e}")
    except json.JSONDecodeError as e:
        result['valid'] = False
        result['errors'].append(f"Invalid JSON in utterances file: {e}")
    except Exception as e:
        result['valid'] = False
        result['errors'].append(f"Unexpected error during validation: {e}")

    return result


def get_sample_utterances(sample_size: int = 3) -> list[dict[str, Any]]:
    """
    Get a sample of utterances from each type for quick testing.

    Args:
        sample_size: Number of utterances to sample from each type (default: 3)

    Returns:
        List of utterance dictionaries with topic_type annotation

    Example:
        >>> samples = get_sample_utterances(2)
        >>> print(len(samples))
        12  # 2 from each of 6 types
    """
    all_utterances = get_all_utterances_flat()

    # Group by type
    from collections import defaultdict
    grouped = defaultdict(list)
    for utterance in all_utterances:
        topic_type = utterance.get('topic_type', 'unknown')
        grouped[topic_type].append(utterance)

    # Sample from each group
    samples = []
    for topic_type, utterance_list in grouped.items():
        samples.extend(utterance_list[:sample_size])

    return samples


def print_utterance_summary():
    """
    Print a formatted summary of the utterance suite to the console.

    Useful for debugging and documentation purposes.

    Example:
        >>> print_utterance_summary()
        Test Utterance Suite Summary
        =============================
        Total utterances: 35
        Topic types: 6

        Type          Count
        -----------   -----
        project          5
        research         5
        personal         5
        exception        5
        compound         5
        edge_cases      10
    """
    counts = get_utterance_count()
    total = sum(counts.values())

    print("Test Utterance Suite Summary")
    print("============================")
    print(f"Total utterances: {total}")
    print(f"Topic types: {len(counts)}")
    print()
    print(f"{'Type':<15} {'Count':>10}")
    print("-" * 27)

    for topic_type, count in sorted(counts.items()):
        print(f"{topic_type:<15} {count:>10}")

    print("-" * 27)
    print(f"{'TOTAL':<15} {total:>10}")


if __name__ == "__main__":
    # When run directly, validate and print summary
    print_utterance_summary()
    print()

    validation = validate_utterance_suite()
    if validation['valid']:
        print("✅ Validation passed")
    else:
        print("❌ Validation failed")
        for error in validation['errors']:
            print(f"  Error: {error}")

    if validation['warnings']:
        print("⚠️  Warnings:")
        for warning in validation['warnings']:
            print(f"  Warning: {warning}")