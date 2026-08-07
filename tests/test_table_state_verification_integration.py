"""
Table state verification integration tests (bead adc-3i8g63).

This integration test combines the repeat runner with all three table state
verification tests to demonstrate that database isolation works reliably.

The test verifies:
1. All three table state checks (session, topic, utterance) run 10+ times sequentially
2. No residual data exists in any table after each iteration
3. Tests pass consistently without data leakage between runs
4. Isolation guarantees hold up under repeated execution

This brings together all previous table verification work into a comprehensive
integration test that proves database reset works reliably.
"""

import sys
from pathlib import Path

import pytest

# Import the repeat runner utility from adc-5tovwg
sys.path.insert(0, str(Path(__file__).parent.parent))
from scripts.run_tests_repeatedly import TestRepeatRunner, RunSummary, TestResult


class TestTableStateVerificationIntegration:
    """Integration tests for table state verification with repeat runner."""

    def test_all_three_table_state_checks_run_10_times_successfully(self):
        """Verify all three table state checks pass consistently when run 10 times.

        This integration test:
        1. Runs session, topic, and utterance table state tests 10 times
        2. Verifies 100% success rate across all runs
        3. Confirms no residual data in any table after each iteration
        4. Ensures no data leakage between iterations

        This validates the isolation guarantees for all three core tables.
        """
        # Create runner with 10 iterations
        runner = TestRepeatRunner(
            count=10,
            verbose=False,
            fail_fast=False,
            test_path=[]  # Empty, will use custom args
        )

        # Override execute method to run only the three table state tests
        def execute_table_tests(run_number: int):
            """Execute only the three table state verification tests."""
            from datetime import datetime

            start_time = datetime.now()

            # Construct pytest args to select only table state tests
            args = [
                "tests/test_database_state_reset.py",
                "-k", "table_state_reset",
                "-v",
                "--tb=line",
                "--color=yes",
            ]

            # Collect results
            test_results = []

            class TableTestCollector:
                def __init__(self, results):
                    self.results = results

                def pytest_runtest_logreport(self, report):
                    if report.when == "call":
                        test_name = report.nodeid.split("::")[-1]
                        passed = report.outcome == "passed"
                        duration = report.duration

                        self.results.append(TestResult(
                            test_name=test_name,
                            passed=passed,
                            duration=duration,
                            error_message=""
                        ))

            collector = TableTestCollector(test_results)
            exit_code = pytest.main(args, plugins=[collector])

            end_time = datetime.now()
            duration = (end_time - start_time).total_seconds()

            passed = sum(1 for r in test_results if r.passed)
            failed = len(test_results) - passed

            return RunSummary(
                run_number=run_number,
                start_time=start_time,
                end_time=end_time,
                duration=duration,
                total_tests=len(test_results),
                passed=passed,
                failed=failed,
                skipped=0,
                errors=0,
                test_results=test_results
            )

        runner._execute_run = execute_table_tests

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

        # Print iteration count in test output
        print(f"\n✅ All 3 table state checks passed across {len(runner.runs)} iterations")
        print(f"   - Session table state test: PASSED (10/10 runs)")
        print(f"   - Topic table state test: PASSED (10/10 runs)")
        print(f"   - Utterance table state test: PASSED (10/10 runs)")

    def test_table_state_verification_with_repeat_runner_k_filter(self):
        """Verify table state tests using pytest's -k filter for precise test selection.

        This test uses a more direct approach with pytest's main() function
        and the -k flag to select only the three table state verification tests.

        This test:
        1. Uses pytest.main() with -k filter to select specific tests
        2. Runs the selected tests 10 times sequentially
        3. Verifies no data leakage between iterations
        4. Confirms all three tables are clean after each run
        """
        # Create a custom runner that uses pytest.main() with -k filter
        runner = TestRepeatRunner(
            count=10,
            verbose=True,  # Show detailed output for verification
            fail_fast=False,
            test_path=[]  # Empty path, we'll construct custom args
        )

        # Override _execute_run to use pytest.main() with -k filter
        def execute_with_pytest_main(run_number: int):
            """Execute run using pytest.main() with -k filter."""
            from datetime import datetime

            start_time = datetime.now()

            # Use pytest.main() with -k filter to select only table state tests
            args = [
                "tests/test_database_state_reset.py",
                "-k", "table_state_reset",  # Select only the three table state tests
                "-v" if runner.verbose else "-q",
                "--tb=short",
                "--color=yes",
            ]

            # Collect test results
            test_results = []

            class ResultCollector:
                def __init__(self, results_list):
                    self.results = results_list

                def pytest_runtest_logreport(self, report):
                    """Collect results from each test."""
                    if report.when == "call":
                        test_name = report.nodeid
                        passed = report.outcome == "passed"
                        duration = report.duration
                        error_msg = str(report.longrepr) if not passed and hasattr(report, "longrepr") else ""

                        test_result = TestResult(
                            test_name=test_name,
                            passed=passed,
                            duration=duration,
                            error_message=error_msg
                        )
                        self.results.append(test_result)

            collector = ResultCollector(test_results)
            exit_code = pytest.main(args, plugins=[collector])

            end_time = datetime.now()
            duration = (end_time - start_time).total_seconds()

            # Count results
            passed = sum(1 for r in test_results if r.passed)
            failed = sum(1 for r in test_results if not r.passed and r.error_message)
            errors = sum(1 for r in test_results if not r.passed and not r.error_message)

            return RunSummary(
                run_number=run_number,
                start_time=start_time,
                end_time=end_time,
                duration=duration,
                total_tests=len(test_results),
                passed=passed,
                failed=failed,
                skipped=0,
                errors=errors,
                test_results=test_results
            )

        runner._execute_run = execute_with_pytest_main

        # Run the tests
        all_success = runner.run_tests()

        # Verify success
        assert all_success, "Expected all runs to pass"

        # Verify we ran exactly 10 times
        assert len(runner.runs) == 10, f"Expected 10 runs, but got {len(runner.runs)}"

        # Verify all runs had 100% success rate
        for run in runner.runs:
            assert run.success_rate == 100.0, (
                f"Run {run.run_number} had {run.success_rate}% success rate, expected 100%"
            )

        # Verify exactly 3 tests ran per run (session, topic, utterance)
        for run in runner.runs:
            assert run.total_tests == 3, (
                f"Run {run.run_number} executed {run.total_tests} tests, expected exactly 3 "
                f"(session, topic, utterance table state tests)"
            )

        print(f"\n📊 Table State Verification Summary:")
        print(f"   Iterations: {len(runner.runs)}")
        print(f"   Tests per iteration: {runner.runs[0].total_tests}")
        print(f"   Success rate: 100% across all iterations")
        print(f"   Data leakage: None detected")

    def test_comprehensive_table_state_isolation_verification(self):
        """Comprehensive integration test for table state isolation.

        This test performs a complete end-to-end verification:
        1. Runs all three table state tests 12 times (more than the minimum 10)
        2. Verifies database is clean after EACH iteration
        3. Includes detailed iteration count in output
        4. Demonstrates isolation is working reliably

        This is the acceptance criteria verification test for bead adc-3i8g63.
        """
        # Create runner with 12 iterations (exceeds the 10+ requirement)
        runner = TestRepeatRunner(
            count=12,  # 12 iterations to exceed the 10+ requirement
            verbose=True,  # Show detailed output
            fail_fast=False,
            test_path=[]  # Empty, will use custom args
        )

        # Override execute method to run only the three table state tests
        def execute_table_tests(run_number: int):
            """Execute only the three table state verification tests."""
            from datetime import datetime

            start_time = datetime.now()

            # Construct pytest args to select only table state tests
            args = [
                "tests/test_database_state_reset.py",
                "-k", "table_state_reset",
                "-v",
                "--tb=line",  # Compact traceback format
                "--color=yes",
            ]

            # Collect results
            test_results = []

            class TableTestCollector:
                def __init__(self, results):
                    self.results = results

                def pytest_runtest_logreport(self, report):
                    if report.when == "call":
                        test_name = report.nodeid.split("::")[-1]  # Get just test name
                        passed = report.outcome == "passed"
                        duration = report.duration

                        self.results.append(TestResult(
                            test_name=test_name,
                            passed=passed,
                            duration=duration,
                            error_message=""
                        ))

            collector = TableTestCollector(test_results)
            exit_code = pytest.main(args, plugins=[collector])

            end_time = datetime.now()
            duration = (end_time - start_time).total_seconds()

            passed = sum(1 for r in test_results if r.passed)
            failed = len(test_results) - passed

            return RunSummary(
                run_number=run_number,
                start_time=start_time,
                end_time=end_time,
                duration=duration,
                total_tests=len(test_results),
                passed=passed,
                failed=failed,
                skipped=0,
                errors=0,
                test_results=test_results
            )

        runner._execute_run = execute_table_tests

        # Run the tests
        all_success = runner.run_tests()

        # Verify all runs passed
        assert all_success, "All 12 iterations must pass"

        # Verify iteration count
        assert len(runner.runs) == 12, f"Expected 12 iterations, got {len(runner.runs)}"

        # Verify each iteration ran exactly 3 tests
        for i, run in enumerate(runner.runs, 1):
            assert run.total_tests == 3, (
                f"Iteration {i}: Expected 3 tests (session, topic, utterance), "
                f"but got {run.total_tests}"
            )
            assert run.passed == 3, (
                f"Iteration {i}: Expected all 3 tests to pass, "
                f"but only {run.passed} passed"
            )
            assert run.failed == 0, (
                f"Iteration {i}: Expected 0 failures, "
                f"but got {run.failed}"
            )

        # Verify no flaky tests
        flaky_reports = runner.generate_flaky_test_report()
        truly_flaky = [r for r in flaky_reports if r.is_flaky]
        assert len(truly_flaky) == 0, (
            f"Found {len(truly_flaky)} flaky tests - all tests must be stable"
        )

        # Verify all three tests are stable (passed every time)
        stable_tests = [r for r in flaky_reports if r.passed_runs == r.total_runs]
        assert len(stable_tests) == 3, (
            f"Expected exactly 3 stable tests (session, topic, utterance), "
            f"but found {len(stable_tests)}"
        )

        # Verify no data leakage (success rate is 100% for all runs)
        success_rates = [run.success_rate for run in runner.runs]
        expected_rates = [100.0] * 12
        assert success_rates == expected_rates, (
            f"Expected 100% success rate for all 12 iterations, "
            f"but got: {success_rates}"
        )

        # Print comprehensive summary with iteration count
        print(f"\n{'='*70}")
        print(f"📊 COMPREHENSIVE TABLE STATE ISOLATION VERIFICATION")
        print(f"{'='*70}")
        print(f"Iterations completed: {len(runner.runs)}")
        print(f"Tests per iteration: {runner.runs[0].total_tests}")
        print(f"Total test executions: {sum(run.total_tests for run in runner.runs)}")
        print(f"Success rate: 100.0% (all {len(runner.runs)} iterations)")
        print(f"Data leakage detected: NONE")
        print(f"Flaky tests detected: NONE")
        print(f"Stable tests: {len(stable_tests)} (session, topic, utterance)")
        print(f"{'='*70}")
        print(f"✅ ACCEPTANCE CRITERIA MET:")
        print(f"   ✓ All three table state checks ran {len(runner.runs)} times (exceeds 10+)")
        print(f"   ✓ No residual data in any table after each iteration")
        print(f"   ✓ Tests pass consistently without data leakage")
        print(f"   ✓ Iteration count included in output")
        print(f"{'='*70}")
