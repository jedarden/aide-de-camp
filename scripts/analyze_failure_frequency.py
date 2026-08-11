#!/usr/bin/env python3
"""
Analyze test failure consistency patterns across multiple runs.
Parses the repeat run log file and creates a failure frequency matrix.
"""

import re
import json
from datetime import datetime
from collections import defaultdict
from pathlib import Path


def parse_log_file(log_path: str) -> dict:
    """
    Parse the repeat run log file and extract failure information.

    Returns:
        dict with structure:
        {
            "total_runs": int,
            "failures": {
                "test_file.py": {
                    "runs_failed": list[int],  # Which runs (1-indexed) this test failed in
                    "failure_count": int,
                    "error_type": str,  # e.g., "ImportError", "IndentationError", etc.
                }
            }
        }
    """
    with open(log_path, 'r') as f:
        content = f.read()

    # Split by run markers
    runs = re.split(r'🔄 Run (\d+)/5', content)

    # First element is header before any run, rest are run data
    total_runs = 5
    failures = defaultdict(lambda: {"runs_failed": [], "failure_count": 0, "error_type": ""})

    # Process each run (odd indices are the run numbers, even indices are content)
    for i in range(1, len(runs), 2):
        if i + 1 >= len(runs):
            break
        run_number = int(runs[i])
        run_content = runs[i + 1]

        # Find all ERROR collecting lines in this run
        error_matches = re.findall(
            r'ERROR collecting (tests/[^\s]+\.py)',
            run_content
        )

        # Extract error type for each test
        error_type_matches = re.findall(
            r'ERROR collecting (tests/[^\s]+\.py).*?\n.*?\n.*?E\s+(\S+):',
            run_content,
            re.DOTALL
        )

        error_types = {}
        for test_file, error_type in error_type_matches:
            error_types[test_file] = error_type

        for test_file in error_matches:
            failures[test_file]["runs_failed"].append(run_number)
            failures[test_file]["failure_count"] += 1
            if test_file in error_types:
                failures[test_file]["error_type"] = error_types[test_file]

    return {
        "total_runs": total_runs,
        "failures": dict(failures)
    }


def create_failure_matrix(parsed_data: dict) -> list:
    """
    Create a failure frequency matrix from parsed log data.

    Returns:
        list of dicts with columns: test_name, failure_count, total_runs, failure_rate, classification
    """
    total_runs = parsed_data["total_runs"]
    failures = parsed_data["failures"]

    matrix = []
    for test_name, data in failures.items():
        failure_count = data["failure_count"]
        failure_rate = (failure_count / total_runs) * 100

        # Classify failure
        if failure_rate == 100:
            classification = "consistent"
        elif 20 <= failure_rate <= 80:
            classification = "intermittent"
        elif failure_rate == 0:
            classification = "pass"
        else:
            classification = "rare"

        matrix.append({
            "test_name": test_name,
            "failure_count": failure_count,
            "total_runs": total_runs,
            "failure_rate": round(failure_rate, 1),
            "classification": classification,
            "error_type": data["error_type"],
            "runs_failed": data["runs_failed"]
        })

    # Sort by failure_count descending, then by test_name
    matrix.sort(key=lambda x: (-x["failure_count"], x["test_name"]))

    return matrix


def generate_summary(matrix: list) -> dict:
    """
    Generate summary statistics from the failure matrix.
    """
    total_tests = len(matrix)
    consistent_failures = [t for t in matrix if t["classification"] == "consistent"]
    intermittent_failures = [t for t in matrix if t["classification"] == "intermittent"]
    rare_failures = [t for t in matrix if t["classification"] == "rare"]

    # Count by error type
    error_type_counts = defaultdict(int)
    for test in matrix:
        error_type_counts[test["error_type"]] += 1

    return {
        "total_tests_with_failures": total_tests,
        "consistent_failures_count": len(consistent_failures),
        "intermittent_failures_count": len(intermittent_failures),
        "rare_failures_count": len(rare_failures),
        "error_type_distribution": dict(error_type_counts),
        "consistent_failure_tests": [t["test_name"] for t in consistent_failures],
        "intermittent_failure_tests": [t["test_name"] for t in intermittent_failures]
    }


def main():
    log_path = "/home/coding/aide-de-camp/data/repeat_run_20260807_091110.log"

    print("Parsing log file...")
    parsed_data = parse_log_file(log_path)

    print("Creating failure frequency matrix...")
    matrix = create_failure_matrix(parsed_data)

    print("Generating summary...")
    summary = generate_summary(matrix)

    # Prepare output
    output = {
        "generated_at": datetime.now().isoformat(),
        "log_file": log_path,
        "total_runs": parsed_data["total_runs"],
        "summary": summary,
        "failure_matrix": matrix
    }

    # Save to file
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = f"/home/coding/aide-de-camp/data/failure_frequency_{timestamp}.json"

    with open(output_path, 'w') as f:
        json.dump(output, f, indent=2)

    print(f"\n✅ Analysis complete!")
    print(f"📊 Output saved to: {output_path}")
    print(f"\n📈 Summary:")
    print(f"  Total runs analyzed: {parsed_data['total_runs']}")
    print(f"  Tests with failures: {summary['total_tests_with_failures']}")
    print(f"  Consistent failures (100%): {summary['consistent_failures_count']}")
    print(f"  Intermittent failures (20-80%): {summary['intermittent_failures_count']}")
    print(f"  Rare failures (<20%): {summary['rare_failures_count']}")

    print(f"\n🔍 Error type distribution:")
    for error_type, count in sorted(summary['error_type_distribution'].items(), key=lambda x: -x[1]):
        print(f"  {error_type}: {count}")

    print(f"\n🚨 Consistent failure tests (fail in ALL runs):")
    for test_name in summary['consistent_failure_tests']:
        print(f"  - {test_name}")

    print(f"\n⚠️  Intermittent failure tests:")
    for test_name in summary['intermittent_failure_tests']:
        print(f"  - {test_name}")

    return output_path


if __name__ == "__main__":
    main()
