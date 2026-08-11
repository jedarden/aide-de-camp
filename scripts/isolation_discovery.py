#!/usr/bin/env python3
"""
Focused isolation discovery script for detecting flaky tests.

This script runs a targeted subset of tests multiple times to identify:
- Connection leaks
- Database state isolation failures
- Race conditions
- Other flaky behavior

Usage:
    python scripts/isolation_discovery.py [--count N] [--verbose]
"""

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from collections import defaultdict


def get_core_tests():
    """Get the list of core tests that should be stable."""
    # Focus on core functionality tests that are likely to have isolation issues
    test_files = [
        "tests/test_git_retry.py",
        "tests/test_session_store.py",
        "tests/test_dispatch_validation.py",
        "tests/test_intent_router.py",
        "tests/test_fetch_orchestrator.py",
        "tests/test_sse_broadcaster.py",
        "tests/test_card_dismissal.py",
        "tests/test_ambient_monitoring.py",
    ]
    return test_files


def run_tests_once(test_files, verbose=False):
    """Run tests once and return results."""
    cmd = [".venv/bin/python", "-m", "pytest"] + test_files
    if verbose:
        cmd.extend(["-v", "--tb=short"])
    else:
        cmd.extend(["-q", "--tb=line"])

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=120  # 2 minute timeout per run
    )

    return result


def parse_test_results(output):
    """Parse pytest output to extract test results."""
    results = {
        "total": 0,
        "passed": 0,
        "failed": 0,
        "errors": 0,
        "skipped": 0,
        "test_details": []
    }

    lines = output.split('\n')
    for line in lines:
        # Parse summary line like "5 passed, 2 failed, 1 skipped in 10.5s"
        if 'passed' in line or 'failed' in line:
            parts = line.split()
            for i, part in enumerate(parts):
                if 'passed' in part and i > 0:
                    try:
                        results["passed"] = int(parts[i-1])
                    except (ValueError, IndexError):
                        pass
                elif 'failed' in part and i > 0:
                    try:
                        results["failed"] = int(parts[i-1])
                    except (ValueError, IndexError):
                        pass
                elif 'ERROR' in part:
                    results["errors"] += 1

    results["total"] = results["passed"] + results["failed"] + results["errors"]

    return results


def main():
    """Main entry point for isolation discovery."""
    parser = argparse.ArgumentParser(
        description="Run focused isolation discovery on core tests"
    )
    parser.add_argument(
        "--count", "-n",
        type=int,
        default=5,
        help="Number of times to run the test suite (default: 5)"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose output"
    )
    parser.add_argument(
        "--output", "-o",
        type=str,
        default="isolation_discovery_report.json",
        help="Output file for report (default: isolation_discovery_report.json)"
    )

    args = parser.parse_args()

    test_files = get_core_tests()

    print(f"🔍 Isolation Discovery - Running {len(test_files)} test files {args.count} times")
    print(f"📅 Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)

    all_runs = []
    test_failures = defaultdict(list)  # test_name -> [run_numbers]

    for run_num in range(1, args.count + 1):
        print(f"\n🔄 Run {run_num}/{args.count}")

        try:
            result = run_tests_once(test_files, args.verbose)
            test_results = parse_test_results(result.stdout)

            print(f"   Results: {test_results['passed']} passed, {test_results['failed']} failed, {test_results['errors']} errors")

            run_data = {
                "run_number": run_num,
                "timestamp": datetime.now().isoformat(),
                "exit_code": result.returncode,
                "results": test_results,
                "output": result.stdout if args.verbose else "",
                "errors": result.stderr if args.verbose else ""
            }
            all_runs.append(run_data)

            # Track failures
            if test_results['failed'] > 0 or test_results['errors'] > 0:
                # Parse output to find which specific tests failed
                for line in result.stdout.split('\n'):
                    if 'FAILED' in line or 'ERROR' in line:
                        # Extract test name
                        if '::' in line:
                            test_name = line.split('::')[1].split()[0]
                            test_failures[test_name].append(run_num)

        except subprocess.TimeoutExpired:
            print(f"   ⏱️  TIMEOUT after 120 seconds")
            run_data = {
                "run_number": run_num,
                "timestamp": datetime.now().isoformat(),
                "exit_code": -1,
                "results": {"total": 0, "passed": 0, "failed": 0, "errors": 1, "skipped": 0},
                "timeout": True
            }
            all_runs.append(run_data)
        except Exception as e:
            print(f"   ❌ Error: {e}")
            run_data = {
                "run_number": run_num,
                "timestamp": datetime.now().isoformat(),
                "exit_code": -1,
                "results": {"total": 0, "passed": 0, "failed": 0, "errors": 1, "skipped": 0},
                "error": str(e)
            }
            all_runs.append(run_data)

    # Analyze results
    print("\n" + "=" * 70)
    print("📊 ISOLATION DISCOVERY RESULTS")
    print("=" * 70)

    total_runs = len(all_runs)
    successful_runs = sum(1 for r in all_runs if r["results"]["failed"] == 0 and r["results"]["errors"] == 0)
    failed_runs = total_runs - successful_runs

    print(f"\n📈 Overall Results:")
    print(f"   Total runs: {total_runs}")
    print(f"   Successful runs: {successful_runs} ({successful_runs/total_runs*100:.1f}%)")
    print(f"   Failed runs: {failed_runs} ({failed_runs/total_runs*100:.1f}%)")

    # Analyze flaky tests
    always_failing = []
    sometimes_failing = []

    for test_name, failure_runs in test_failures.items():
        failure_rate = len(failure_runs) / total_runs
        if failure_rate == 1.0:
            always_failing.append(test_name)
        else:
            sometimes_failing.append({
                "test_name": test_name,
                "failure_runs": failure_runs,
                "failure_rate": failure_rate
            })

    print(f"\n🔍 Test Stability:")
    print(f"   Always failing: {len(always_failing)} tests")
    print(f"   Sometimes failing (flaky): {len(sometimes_failing)} tests")

    if always_failing:
        print(f"\n❌ ALWAYS FAILING TESTS:")
        for test in always_failing:
            print(f"   • {test}")

    if sometimes_failing:
        print(f"\n⚠️  FLAKY TESTS DETECTED:")
        for test_info in sorted(sometimes_failing, key=lambda x: x['failure_rate'], reverse=True):
            test_name = test_info['test_name']
            failure_runs = test_info['failure_runs']
            rate = test_info['failure_rate'] * 100
            print(f"   • {test_name}")
            print(f"     Failed in runs: {failure_runs} ({rate:.0f}% of runs)")

    # Save report
    report = {
        "metadata": {
            "timestamp": datetime.now().isoformat(),
            "total_runs": total_runs,
            "test_files": test_files
        },
        "summary": {
            "successful_runs": successful_runs,
            "failed_runs": failed_runs,
            "success_rate": successful_runs / total_runs * 100 if total_runs > 0 else 0
        },
        "runs": all_runs,
        "test_failures": dict(test_failures),
        "always_failing": always_failing,
        "flaky_tests": sometimes_failing
    }

    output_path = Path(args.output)
    output_path.write_text(json.dumps(report, indent=2))
    print(f"\n💾 Detailed report saved to: {args.output}")

    # Exit with error if any runs failed
    if failed_runs > 0:
        print(f"\n❌ {failed_runs} out of {total_runs} test runs failed")
        sys.exit(1)
    else:
        print(f"\n✅ All {total_runs} test runs passed successfully!")
        sys.exit(0)


if __name__ == "__main__":
    main()