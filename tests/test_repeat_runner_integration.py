"""
Repeat runner integration tests (bead adc-6b2c0p).

These tests verify that the repeat runner correctly executes test suites
multiple times and properly detects flaky tests and data leakage issues.

The integration tests verify:
1. Database state tests run successfully 10 times in a row
2. All tests pass with 100% consistency (no flaky tests)
3. No data leakage between iterations (verified by the underlying tests)
4. Repeat runner correctly generates reports
5. Repeat runner exits with correct codes

This ensures the test isolation guarantees hold up under repeated execution.
"""

import json
import sys
from pathlib import Path

import pytest


class TestRepeatRunnerIntegration:
    """Integration tests for the repeat runner with database state tests."""

    @pytest.mark.integration
    def test_database_state_tests_run_10_times_successfully(self):
        """Verify database state tests pass consistently when run 10 times.

        This integration test:
        1. Runs all tests in test_database_state_reset.py 10 times
        2. Verifies 100% success rate across all runs
        3. Confirms no flaky tests (all tests pass every time)
        4. Ensures no data leakage between iterations

        This validates the isolation guarantees provided by the test fixtures.
        """
        # Import here to avoid import errors if script is missing
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from scripts.run_tests_repeatedly import TestRepeatRunner

        # Create runner with 10 iterations
        runner = TestRepeatRunner(
            count=10,
            verbose=False,  # Don't clutter test output
            fail_fast=False,  # Run all 10 times even if one fails
            test_path=["tests/test_database_state_reset.py"]
        )

        # Run the tests
        all_success = runner.run_tests()

        # Verify all runs passed
        assert all_success, "Expected all 10 runs to pass, but some failed"

        # Verify we ran exactly 10 times
        assert len(runner.runs) == 10, f"Expected 10 runs, but got {len(runner.runs)}"

        # Verify 100% success rate across all runs
        for run in runner.runs:
            assert run.failed == 0, f"Run {run.run_number} had {run.failed} failed tests"
            assert run.errors == 0, f"Run {run.run_number} had {run.errors} errors"
            assert run.success_rate == 100.0, f"Run {run.run_number} had {run.success_rate}% success rate"

        # Verify no flaky tests
        flaky_reports = runner.generate_flaky_test_report()
        truly_flaky = [r for r in flaky_reports if r.is_flaky]
        assert len(truly_flaky) == 0, f"Found {len(truly_flaky)} flaky tests: {truly_flaky}"

        # Verify all tests are stable (pass every time)
        stable_tests = [r for r in flaky_reports if r.passed_runs == r.total_runs and r.total_runs > 0]
        assert len(stable_tests) > 0, "Expected at least some stable tests"

    @pytest.mark.integration
    def test_repeat_runner_generates_valid_report(self, tmp_path):
        """Verify repeat runner generates a valid JSON report.

        This test:
        1. Runs database state tests 3 times (reduced for speed)
        2. Generates a JSON report
        3. Verifies report structure and content
        """
        # Import here to avoid import errors if script is missing
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from scripts.run_tests_repeatedly import TestRepeatRunner

        # Create runner with 3 iterations (reduced for test speed)
        runner = TestRepeatRunner(
            count=3,
            verbose=False,
            fail_fast=False,
            test_path=["tests/test_database_state_reset.py"]
        )

        # Run the tests
        runner.run_tests()

        # Generate report to temp file
        report_file = tmp_path / "repeat_runner_report.json"
        runner.save_report(str(report_file))

        # Verify report file exists
        assert report_file.exists(), "Report file should be created"

        # Verify report is valid JSON
        with open(report_file) as f:
            report_data = json.load(f)

        # Verify report structure
        assert "metadata" in report_data, "Report should have metadata"
        assert "runs" in report_data, "Report should have runs"
        assert "flaky_tests" in report_data, "Report should have flaky_tests section"

        # Verify metadata
        assert report_data["metadata"]["total_runs"] == 3
        assert report_data["metadata"]["requested_runs"] == 3

        # Verify we have data for all 3 runs
        assert len(report_data["runs"]) == 3

        # Verify each run has required fields
        for run in report_data["runs"]:
            assert "run_number" in run
            assert "duration" in run
            assert "total_tests" in run
            assert "passed" in run
            assert "failed" in run
            assert "success_rate" in run

    @pytest.mark.integration
    def test_repeat_runner_detects_no_data_leakage(self):
        """Verify repeat runner confirms no data leakage across iterations.

        This test validates that the database isolation holds up by:
        1. Running tests 10 times
        2. Verifying each iteration has identical success rates
        3. Confirming no accumulation of failures (which would indicate leakage)

        Data leakage would manifest as:
        - Increasing failure rates across runs
        - Orphaned data causing cascading failures
        - Different test counts between runs
        """
        # Import here to avoid import errors if script is missing
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from scripts.run_tests_repeatedly import TestRepeatRunner

        runner = TestRepeatRunner(
            count=10,
            verbose=False,
            fail_fast=False,
            test_path=["tests/test_database_state_reset.py"]
        )

        # Run the tests
        runner.run_tests()

        # Extract test counts from each run
        test_counts = [run.total_tests for run in runner.runs]

        # All runs should execute the same number of tests
        # (Data leakage would cause tests to skip or fail differently)
        unique_counts = set(test_counts)
        assert len(unique_counts) <= 1, (
            f"Expected all runs to have the same test count, but found: {unique_counts}. "
            f"This suggests data leakage or state pollution between runs."
        )

        # All runs should have 100% success rate
        success_rates = [run.success_rate for run in runner.runs]
        expected_rates = [100.0] * 10
        assert success_rates == expected_rates, (
            f"Expected all runs to have 100% success rate, but got: {success_rates}. "
            f"This suggests tests are failing due to leaked state."
        )

    @pytest.mark.integration
    def test_repeat_runner_fail_fast_stops_on_failure(self):
        """Verify repeat runner's fail-fast feature works correctly.

        This test:
        1. Creates a temporary test file that always fails
        2. Runs it with fail_fast enabled
        3. Verifies execution stops on first failure
        """
        # Import here to avoid import errors if script is missing
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from scripts.run_tests_repeatedly import TestRepeatRunner

        # Create a temporary failing test
        failing_test_content = '''
import pytest

@pytest.mark.asyncio
async def test_always_fails():
    """This test always fails."""
    assert False, "Intentional failure for testing fail-fast"
'''
        tmp_test_file = Path(__file__).parent / "test_fail_fast_temp.py"
        tmp_test_file.write_text(failing_test_content)

        try:
            runner = TestRepeatRunner(
                count=5,  # Request 5 runs
                verbose=False,
                fail_fast=True,  # Enable fail-fast
                test_path=[str(tmp_test_file)]
            )

            # Run the tests
            all_success = runner.run_tests()

            # Should have failed
            assert not all_success, "Expected run to fail"

            # Should have stopped after first failure (only 1 run completed)
            assert len(runner.runs) == 1, (
                f"Expected fail-fast to stop after 1 run, but completed {len(runner.runs)} runs"
            )

        finally:
            # Clean up temporary test file
            if tmp_test_file.exists():
                tmp_test_file.unlink()

    @pytest.mark.integration
    def test_database_state_tests_complete_without_failures(self):
        """Verify database state test suite completes without any failures.

        This is the final integration test that confirms:
        1. All database state tests run successfully
        2. No timeouts or hangs occur
        3. Test suite completes in reasonable time
        4. All assertions pass (no silent failures)

        This is the acceptance criteria verification for bead adc-6b2c0p.
        """
        # Import here to avoid import errors if script is missing
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from scripts.run_tests_repeatedly import TestRepeatRunner

        runner = TestRepeatRunner(
            count=10,
            verbose=False,
            fail_fast=False,
            test_path=["tests/test_database_state_reset.py"]
        )

        # Run the tests and verify completion
        all_success = runner.run_tests()

        # Test suite must complete without failures
        assert all_success, "Test suite must complete without failures"

        # Verify all 10 runs completed
        assert len(runner.runs) == 10, "All 10 runs must complete"

        # Verify no errors or failures in any run
        total_failures = sum(run.failed + run.errors for run in runner.runs)
        assert total_failures == 0, f"Expected 0 total failures, but got {total_failures}"

        # Verify reasonable execution time (not hung)
        total_duration = sum(run.duration for run in runner.runs)
        assert total_duration < 300, (
            f"Test suite took {total_duration:.1f}s, which suggests a hang or slowdown. "
            f"Expected completion within 300 seconds for 10 runs."
        )

        # Verify we executed a reasonable number of tests per run
        # (The actual count depends on how many tests are in the file)
        avg_tests_per_run = sum(run.total_tests for run in runner.runs) / len(runner.runs)
        assert avg_tests_per_run >= 10, (
            f"Expected at least 10 tests per run, but got {avg_tests_per_run:.1f}. "
            f"This suggests tests are being skipped or not discovered."
        )
