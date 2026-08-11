#!/usr/bin/env python3
"""
Categorize failing tests by root cause.

Analyzes failure patterns and classifies them into:
- connection_leak: connection pool, too many open files, connection timeout
- database_state: no such table, constraint, schema, foreign key
- race_condition: timeout, deadlock, order, timing, async
- other: anything not matching above patterns
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Set


def load_failure_matrix(failure_file: Path) -> Dict:
    """Load the failure frequency matrix from JSON file."""
    with open(failure_file, 'r') as f:
        return json.load(f)


def categorize_failure(error_message: str, error_type: str) -> Set[str]:
    """
    Categorize a failure based on error message and type.

    Returns a set of matching categories (a failure can belong to multiple).
    Only categorizes based on ERROR PATTERNS, not test names.
    """
    categories = set()
    error_lower = error_message.lower()
    error_type_lower = error_type.lower()

    # Connection leak patterns - must appear in error message/type
    connection_leak_patterns = [
        "connection pool",
        "too many open files",
        "connection timeout",
    ]

    # Database state patterns - must appear in error message/type
    database_state_patterns = [
        "no such table",
        "constraint",
        "schema error",
        "foreign key",
        "integrityerror",
        "operationalerror",
    ]

    # Race condition patterns - must appear in error message/type
    race_condition_patterns = [
        "race",
        "deadlock",
        "lock timeout",
        "asyncio.gather",
        "concurrent.futures",
        "event loop",
        "coroutine",
    ]

    # Check patterns in both error message and error type (not test name)
    # Only use error_type and generic error patterns
    combined_text = f"{error_type_lower}"

    # Check connection leaks
    if any(pattern in combined_text for pattern in connection_leak_patterns):
        categories.add("connection_leak")

    # Check database state issues
    if any(pattern in combined_text for pattern in database_state_patterns):
        categories.add("database_state")

    # Check race conditions
    if any(pattern in combined_text for pattern in race_condition_patterns):
        categories.add("race_condition")

    # If no patterns matched, categorize as "other"
    if not categories:
        categories.add("other")

    return categories


def analyze_failures(failure_matrix: List[Dict]) -> Dict[str, List[Dict]]:
    """
    Analyze failures and categorize them by root cause.

    Returns a dictionary mapping categories to lists of test failures.
    """
    categorized = {
        "connection_leak": [],
        "database_state": [],
        "race_condition": [],
        "other": []
    }

    for failure in failure_matrix:
        test_name = failure.get("test_name", "unknown")
        error_type = failure.get("error_type", "Unknown")
        failure_count = failure.get("failure_count", 0)

        # Create error message based ONLY on error type (not test name)
        # This prevents false categorization based on test names
        error_message = error_type

        # Categorize the failure
        categories = categorize_failure(error_message, error_type)

        # Add test to each matching category
        for category in categories:
            categorized[category].append({
                "test_name": test_name,
                "error_type": error_type,
                "failure_count": failure_count,
                "failure_rate": failure.get("failure_rate", 100.0)
            })

    return categorized


def generate_report(categorized: Dict[str, List[Dict]], generated_at: str, source_file: str) -> Dict:
    """Generate a comprehensive categorization report."""
    
    # Remove duplicates (tests that appear in multiple categories)
    unique_tests_by_category = {}
    for category, tests in categorized.items():
        seen = set()
        unique_tests = []
        for test in tests:
            test_key = test["test_name"]
            if test_key not in seen:
                seen.add(test_key)
                unique_tests.append(test)
        unique_tests_by_category[category] = unique_tests

    # Count unique tests per category
    category_counts = {
        category: len(tests)
        for category, tests in unique_tests_by_category.items()
    }

    total_unique = sum(category_counts.values())

    return {
        "generated_at": datetime.now().isoformat(),
        "source_file": source_file,
        "classification_methodology": {
            "connection_leak": {
                "patterns": ["connection pool", "too many open files", "connection timeout"],
                "description": "Tests with connection pool exhaustion or too many open files",
                "note": "Patterns must appear in error message/type, not test name"
            },
            "database_state": {
                "patterns": ["no such table", "constraint", "schema error", "foreign key", "integrityerror", "operationalerror"],
                "description": "Tests with schema errors, constraint violations, or missing fixtures",
                "note": "Patterns must appear in error message/type, not test name"
            },
            "race_condition": {
                "patterns": ["race", "deadlock", "lock timeout", "asyncio.gather", "concurrent.futures", "event loop", "coroutine"],
                "description": "Tests with timing-dependent failures or order-dependent behavior",
                "note": "Patterns must appear in error message/type, not test name"
            },
            "other": {
                "patterns": ["anything not matching above patterns"],
                "description": "Tests with uncategorizable failures (e.g., syntax errors, import errors, pytest fixture issues)",
                "note": "Default category for all non-matching error patterns"
            }
        },
        "summary": {
            "total_unique_failures_categorized": total_unique,
            "unique_failures_by_category": category_counts,
            "categories_with_failures": [
                cat for cat, tests in unique_tests_by_category.items() if tests
            ]
        },
        "categorized_failures": unique_tests_by_category
    }


def main():
    """Main function to categorize failures."""
    # Find the most recent failure frequency file
    data_dir = Path("/home/coding/aide-de-camp/data")
    failure_files = sorted(data_dir.glob("failure_frequency_*.json"), reverse=True)

    if not failure_files:
        print("❌ No failure frequency files found in data directory")
        return

    source_file = str(failure_files[0])
    print(f"📊 Loading failure matrix from: {source_file}")

    # Load failure matrix
    failure_data = load_failure_matrix(Path(source_file))
    failure_matrix = failure_data.get("failure_matrix", [])

    print(f"📋 Analyzing {len(failure_matrix)} failing tests...")

    # Categorize failures
    categorized = analyze_failures(failure_matrix)

    # Generate report
    report = generate_report(
        categorized,
        failure_data.get("generated_at", "unknown"),
        source_file
    )

    # Save report
    output_file = data_dir / f"failure_categories_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(output_file, 'w') as f:
        json.dump(report, f, indent=2)

    print(f"✅ Categorization complete: {output_file}")
    print(f"\n📊 Summary:")
    print(f"   Total unique failures categorized: {report['summary']['total_unique_failures_categorized']}")
    print(f"   Categories with failures: {', '.join(report['summary']['categories_with_failures'])}")

    for category in report['summary']['categories_with_failures']:
        count = report['summary']['unique_failures_by_category'][category]
        print(f"   - {category}: {count} tests")


if __name__ == "__main__":
    main()
