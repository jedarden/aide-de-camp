#!/usr/bin/env python3
"""
Automated test repeat runner for flaky test detection.

This script runs the full test suite multiple times and tracks per-run results
to detect flaky tests that may pass sometimes but fail intermittently.

Usage:
    python scripts/run_tests_repeatedly.py [--count N] [--verbose] [--fail-fast]

Examples:
    # Run tests 10 times (default)
    python scripts/run_tests_repeatedly.py

    # Run tests 20 times with verbose output
    python scripts/run_tests_repeatedly.py --count 20 --verbose

    # Run tests 5 times, stopping on first failure
    python scripts/run_tests_repeatedly.py --count 5 --fail-fast
"""

import argparse
import json
import sys
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Set

import pytest
from pytest import TestReport


@dataclass
class TestResult:
    """Track the result of a single test execution."""
    test_name: str
    passed: bool
    duration: float
    error_message: str = ""

    def __hash__(self):
        return hash(self.test_name)


@dataclass
class RunSummary:
    """Summary of a single test run."""
    run_number: int
    start_time: datetime
    end_time: datetime
    duration: float
    total_tests: int
    passed: int
    failed: int
    skipped: int
    errors: int
    test_results: List[TestResult] = field(default_factory=list)

    @property
    def success_rate(self) -> float:
        """Calculate success rate as percentage."""
        if self.total_tests == 0:
            return 0.0
        return (self.passed / self.total_tests) * 100


@dataclass
class FlakyTestReport:
    """Report on flaky test behavior across runs."""
    test_name: str
    total_runs: int
    passed_runs: int
    failed_runs: int
    failure_rate: float
    failure_runs: List[int] = field(default_factory=list)

    @property
    def is_flaky(self) -> bool:
        """A test is flaky if it both passed and failed across runs."""
        return self.passed_runs > 0 and self.failed_runs > 0


class TestRepeatRunner:
    """Manages repeated test execution and flaky test detection."""

    def __init__(self, count: int = 10, verbose: bool = False, fail_fast: bool = False, test_path: List[str] = None):
        self.count = count
        self.verbose = verbose
        self.fail_fast = fail_fast
        self.test_path = test_path or ["tests/"]
        self.runs: List[RunSummary] = []
        self.all_test_results: Dict[str, List[TestResult]] = defaultdict(list)

    def run_tests(self) -> bool:
        """Run the test suite N times and track results."""
        print(f"🧪 Running test suite {self.count} time(s)")
        print(f"📅 Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 60)

        all_success = True

        for run_num in range(1, self.count + 1):
            print(f"\n🔄 Run {run_num}/{self.count}")

            run_summary = self._execute_run(run_num)
            self.runs.append(run_summary)

            # Store individual test results
            for test_result in run_summary.test_results:
                self.all_test_results[test_result.test_name].append(test_result)

            # Print run summary
            self._print_run_summary(run_summary)

            # Check if run failed
            if run_summary.failed > 0 or run_summary.errors > 0:
                all_success = False
                if self.fail_fast:
                    print(f"\n⚠️  Run {run_num} failed.Stopping due to --fail-fast")
                    break

        print("\n" + "=" * 60)
        print(f"🏁 Completed {len(self.runs)} run(s) at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

        return all_success

    def _execute_run(self, run_number: int) -> RunSummary:
        """Execute a single test run and collect results."""
        start_time = datetime.now()

        # Collect test results during execution
        test_results: List[TestResult] = []

        class ResultCollector:
            def __init__(self, results_list):
                self.results = results_list

            def pytest_runtest_logreport(self, report: TestReport):
                """Collect results from each test."""
                if report.when == "call":  # Only collect the call phase, not setup/teardown
                    # Extract test name from nodeid (e.g., "tests/test_foo.py::test_bar")
                    test_name = report.nodeid
                    passed = report.outcome == "passed"
                    duration = report.duration

                    error_msg = ""
                    if not passed and hasattr(report, "longrepr"):
                        error_msg = str(report.longrepr) if report.longrepr else ""

                    test_result = TestResult(
                        test_name=test_name,
                        passed=passed,
                        duration=duration,
                        error_message=error_msg
                    )
                    self.results.append(test_result)

        # Run pytest with our collector
        args = [
            *self.test_path,
            "-v" if self.verbose else "-q",
            "--tb=short",
            "--color=yes",
        ]

        collector = ResultCollector(test_results)

        # Use pytest.main to run tests
        exit_code = pytest.main(args, plugins=[collector])

        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()

        # Count results
        passed = sum(1 for r in test_results if r.passed)
        failed = sum(1 for r in test_results if not r.passed and r.error_message)
        errors = sum(1 for r in test_results if not r.passed and not r.error_message)
        skipped = 0  # Pytest doesn't report skipped in the call phase

        total = len(test_results)

        return RunSummary(
            run_number=run_number,
            start_time=start_time,
            end_time=end_time,
            duration=duration,
            total_tests=total,
            passed=passed,
            failed=failed,
            skipped=skipped,
            errors=errors,
            test_results=test_results
        )

    def _print_run_summary(self, run_summary: RunSummary):
        """Print summary of a single run."""
        status_emoji = "✅" if run_summary.failed == 0 else "❌"

        print(f"{status_emoji} Results: {run_summary.passed}/{run_summary.total_tests} passed "
              f"({run_summary.success_rate:.1f}%)")

        if run_summary.failed > 0:
            print(f"   Failed: {run_summary.failed}")

        if run_summary.errors > 0:
            print(f"   Errors: {run_summary.errors}")

        print(f"   Duration: {run_summary.duration:.2f}s")

        # Show failed tests if verbose
        if self.verbose and run_summary.failed > 0:
            print("\n   Failed tests:")
            for result in run_summary.test_results:
                if not result.passed:
                    print(f"     - {result.test_name}")
                    if result.error_message:
                        # Show first line of error
                        first_line = result.error_message.split('\n')[0]
                        print(f"       {first_line}")

    def generate_flaky_test_report(self) -> List[FlakyTestReport]:
        """Generate report on flaky tests across all runs."""
        flaky_reports = []

        for test_name, results in self.all_test_results.items():
            if not results:
                continue

            passed_runs = sum(1 for r in results if r.passed)
            failed_runs = sum(1 for r in results if not r.passed)

            # Find which runs had failures
            failure_runs = []
            for i, run in enumerate(self.runs, 1):
                test_result = next((r for r in run.test_results if r.test_name == test_name), None)
                if test_result and not test_result.passed:
                    failure_runs.append(i)

            total_runs = len(results)
            failure_rate = (failed_runs / total_runs * 100) if total_runs > 0 else 0

            report = FlakyTestReport(
                test_name=test_name,
                total_runs=total_runs,
                passed_runs=passed_runs,
                failed_runs=failed_runs,
                failure_rate=failure_rate,
                failure_runs=failure_runs
            )

            flaky_reports.append(report)

        # Sort by failure rate (highest first)
        flaky_reports.sort(key=lambda r: r.failure_rate, reverse=True)

        return flaky_reports

    def print_final_report(self):
        """Print comprehensive final report."""
        print("\n" + "=" * 60)
        print("📊 FINAL REPORT")
        print("=" * 60)

        # Overall statistics
        total_tests_run = sum(run.total_tests for run in self.runs)
        total_passed = sum(run.passed for run in self.runs)
        total_failed = sum(run.failed for run in self.runs)
        total_errors = sum(run.errors for run in self.runs)

        overall_success_rate = (total_passed / total_tests_run * 100) if total_tests_run > 0 else 0

        print(f"\n📈 Overall Statistics:")
        print(f"   Total runs: {len(self.runs)}")
        print(f"   Total test executions: {total_tests_run}")
        print(f"   Passed: {total_passed} ({overall_success_rate:.1f}%)")
        print(f"   Failed: {total_failed}")
        print(f"   Errors: {total_errors}")

        # Duration statistics
        durations = [run.duration for run in self.runs]
        avg_duration = sum(durations) / len(durations) if durations else 0
        print(f"\n⏱️  Duration Statistics:")
        print(f"   Total: {sum(durations):.2f}s")
        print(f"   Average: {avg_duration:.2f}s")
        print(f"   Min: {min(durations):.2f}s" if durations else "   Min: N/A")
        print(f"   Max: {max(durations):.2f}s" if durations else "   Max: N/A")

        # Flaky test analysis
        flaky_reports = self.generate_flaky_test_report()
        truly_flaky = [r for r in flaky_reports if r.is_flaky]
        always_failing = [r for r in flaky_reports if r.failed_runs == r.total_runs]

        print(f"\n🔍 Test Stability Analysis:")
        print(f"   Unique tests executed: {len(self.all_test_results)}")
        print(f"   Flaky tests (pass & fail): {len(truly_flaky)}")
        print(f"   Always failing: {len(always_failing)}")

        if truly_flaky:
            print(f"\n⚠️  FLAKY TESTS DETECTED ({len(truly_flaky)}):")
            print("   " + "-" * 56)
            for report in truly_flaky:
                print(f"   • {report.test_name}")
                print(f"     Passed: {report.passed_runs}/{report.total_runs} "
                      f"({report.passed_runs/report.total_runs*100:.0f}%)")
                print(f"     Failed: {report.failed_runs}/{report.total_runs} "
                      f"({report.failure_rate:.0f}%)")
                print(f"     Failed in runs: {', '.join(map(str, report.failure_runs))}")

        if always_failing:
            print(f"\n❌ ALWAYS FAILING TESTS ({len(always_failing)}):")
            print("   " + "-" * 56)
            for report in always_failing:
                print(f"   • {report.test_name}")
                print(f"     Failed in all {report.total_runs} runs")

        # Stable tests
        stable = [r for r in flaky_reports if r.passed_runs == r.total_runs and r.total_runs > 0]
        print(f"\n✅ STABLE TESTS: {len(stable)} tests passed consistently")

        # Print summary of failures per run
        print(f"\n📋 Failures by Run:")
        for run in self.runs:
            emoji = "✅" if run.failed == 0 else "❌"
            print(f"   Run {run.run_number}: {emoji} {run.failed} failed, {run.errors} errors "
                  f"({run.success_rate:.1f}% success)")

    def save_report(self, output_file: str = "test_repeat_report.json"):
        """Save detailed report to JSON file."""
        report_data = {
            "metadata": {
                "timestamp": datetime.now().isoformat(),
                "total_runs": len(self.runs),
                "requested_runs": self.count,
                "fail_fast": self.fail_fast
            },
            "runs": [
                {
                    "run_number": run.run_number,
                    "start_time": run.start_time.isoformat(),
                    "end_time": run.end_time.isoformat(),
                    "duration": run.duration,
                    "total_tests": run.total_tests,
                    "passed": run.passed,
                    "failed": run.failed,
                    "skipped": run.skipped,
                    "errors": run.errors,
                    "success_rate": run.success_rate,
                    "test_results": [
                        {
                            "test_name": result.test_name,
                            "passed": result.passed,
                            "duration": result.duration,
                            "error_message": result.error_message
                        }
                        for result in run.test_results
                    ]
                }
                for run in self.runs
            ],
            "flaky_tests": [
                {
                    "test_name": report.test_name,
                    "total_runs": report.total_runs,
                    "passed_runs": report.passed_runs,
                    "failed_runs": report.failed_runs,
                    "failure_rate": report.failure_rate,
                    "failure_runs": report.failure_runs,
                    "is_flaky": report.is_flaky
                }
                for report in self.generate_flaky_test_report()
            ]
        }

        output_path = Path(output_file)
        output_path.write_text(json.dumps(report_data, indent=2))
        print(f"\n💾 Detailed report saved to: {output_file}")


def main():
    """Main entry point for the test repeat runner."""
    parser = argparse.ArgumentParser(
        description="Run test suite multiple times to detect flaky tests",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    parser.add_argument(
        "--count", "-n",
        type=int,
        default=10,
        help="Number of times to run the test suite (default: 10)"
    )

    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose output including individual test names and errors"
    )

    parser.add_argument(
        "--fail-fast",
        action="store_true",
        help="Stop on first failed run"
    )

    parser.add_argument(
        "--output", "-o",
        type=str,
        default="test_repeat_report.json",
        help="Output file for detailed JSON report (default: test_repeat_report.json)"
    )

    parser.add_argument(
        "test_path",
        nargs="*",
        default=["tests/"],
        help="Path to test files or directories (default: tests/)"
    )

    args = parser.parse_args()

    # Validate count
    if args.count < 1:
        print("❌ Error: count must be at least 1", file=sys.stderr)
        sys.exit(1)

    # Run the tests
    runner = TestRepeatRunner(
        count=args.count,
        verbose=args.verbose,
        fail_fast=args.fail_fast,
        test_path=args.test_path
    )

    try:
        all_success = runner.run_tests()
        runner.print_final_report()
        runner.save_report(args.output)

        # Exit with error if any run failed
        if not all_success:
            print("\n❌ Some test runs failed. Exiting with error code 1.")
            sys.exit(1)
        else:
            print("\n✅ All test runs passed successfully!")
            sys.exit(0)

    except KeyboardInterrupt:
        print("\n\n⚠️  Test execution interrupted by user")
        if runner.runs:
            print(f"📊 Partial report from {len(runner.runs)} completed run(s):")
            runner.print_final_report()
            runner.save_report(args.output)
        sys.exit(130)  # Standard exit code for SIGINT
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()