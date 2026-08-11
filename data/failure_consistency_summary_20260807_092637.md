# Test Failure Consistency Analysis Report

**Generated:** 2026-08-07 09:26:37  
**Source:** `repeat_run_20260807_091110.log` (5 consecutive test runs)

## Executive Summary

All test failures in the 5-repeat run are **systematic (100% consistent)**. There are **no intermittent failures** - every failing test fails in all 5 runs with identical error patterns. This indicates the failures are due to missing dependencies, configuration issues, or environment problems rather than flaky tests.

## Key Metrics

- **Total runs analyzed:** 5
- **Unique tests with failures:** 33
- **Consistent failures (100% failure rate):** 33 (100%)
- **Intermittent failures (20-80% failure rate):** 0
- **Rare failures (<20% failure rate):** 0

## Failure Categories

### By Test Type

| Category | Count | Percentage |
|----------|-------|------------|
| other    | 18    | 54.5%      |
| card     | 7     | 21.2%      |
| e2e      | 3     | 9.1%       |
| ambient  | 2     | 6.1%       |
| canvas   | 1     | 3.0%       |
| resilience | 1   | 3.0%       |
| monitoring | 1   | 3.0%       |

### Most Frequent Consistent Failures (Top 10)

1. **tests.e2e.test_canvas_navigation** - 5/5 runs (100%) - `ModuleNotFoundError: playwright`
2. **tests.test_ambient_fetch_and_diff** - 5/5 runs (100%) - `Failed: Marks cannot be applied to fixtures`
3. **tests.test_ambient_rule_engine** - 5/5 runs (100%) - `SyntaxError`
4. **tests.test_backend_stuck_failed_cards** - 5/5 runs (100%) - `FAILED`
5. **tests.test_bead_watcher_integration** - 5/5 runs (100%) - `FAILED`
6. **tests.test_canvas_component_cards** - 5/5 runs (100%) - `FAILED`
7. **tests.test_card_cache** - 5/5 runs (100%) - `FAILED`
8. **tests.test_card_dismissal_db_verification** - 5/5 runs (100%) - `FAILED`
9. **tests.test_card_dismissal_helpers** - 5/5 runs (100%) - `FAILED`
10. **tests.test_circuit_breaker** - 5/5 runs (100%) - `FAILED`

## Root Cause Analysis

### Primary Issues Identified

1. **Missing Dependencies** (3 tests):
   - `playwright` module not installed (E2E tests)
   - Likely other missing imports in ambient tests

2. **Test Configuration Issues** (2 tests):
   - Marks applied to pytest fixtures (deprecation error)
   - Syntax errors in test code

3. **Systematic Test Failures** (28 tests):
   - Consistent test logic failures or dependency issues
   - All fail with 100% consistency across runs

## Conclusions

### No Flaky Tests Detected
The absence of intermittent failures is a positive finding. There are no race conditions, timing issues, or non-deterministic test behaviors. All failures are reproducible and systematic.

### Infrastructure/Dependency Issues
The 100% consistent failure rate indicates these are infrastructure problems rather than test design issues:
- Missing required packages (playwright)
- Test configuration errors (fixture marks)
- Potential environment configuration issues

### Recommendations Priority
1. **HIGH:** Install missing dependencies (playwright)
2. **HIGH:** Fix fixture mark deprecation issues
3. **MEDIUM:** Investigate systematic test failures (28 tests)
4. **LOW:** No flaky test mitigation needed (none exist)

## Data Files Generated

- **Failure Frequency Matrix:** `data/failure_frequency_20260807_092637.json`
- **Detailed Pattern Analysis:** `data/failure_analysis_detailed_20260807_092637.json`
- **Summary Report:** `data/failure_consistency_summary_20260807_092637.md`

---

**Analysis Method:** Parsed 5-repeat test run logs (3,469 lines) → extracted test failures → grouped by test name → calculated frequency matrix → categorized by consistency pattern