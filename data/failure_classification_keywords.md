# Failure Classification Pattern Keywords

This document documents the pattern keywords used for test failure categorization in the aide-de-camp project.

## Classification Methodology

The failure categorization system analyzes test error messages and error types to assign them to one of four categories:
- `connection_leak`: Connection pool exhaustion or file descriptor issues
- `database_state`: Database schema, constraint, or integrity issues  
- `race_condition`: Timing-dependent failures or concurrency issues
- `other`: Any failure not matching the above patterns

## Pattern Keywords by Category

### 1. Connection Leaks (`connection_leak`)

**Patterns:**
- `connection pool`
- `too many open files`
- `connection timeout`

**Description:** Tests with connection pool exhaustion or too many open files.

**Examples:**
- `"pool connection exhausted"` → connection_leak
- `"too many open files"` → connection_leak
- `"connection timeout after 30s"` → connection_leak

**Note:** Patterns must appear in the error message or error type, not in test names.

---

### 2. Database State Issues (`database_state`)

**Patterns:**
- `no such table`
- `constraint`
- `schema error`
- `foreign key`
- `integrityerror`
- `operationalerror`

**Description:** Tests with schema errors, constraint violations, or missing fixtures.

**Examples:**
- `"no such table: sessions"` → database_state
- `"foreign key constraint failed"` → database_state
- `"sqlite3.IntegrityError: UNIQUE constraint failed"` → database_state
- `"psycopg2.operationalerror: schema does not exist"` → database_state

**Note:** Patterns must appear in the error message or error type, not in test names.

---

### 3. Race Conditions (`race_condition`)

**Patterns:**
- `race`
- `deadlock`
- `lock timeout`
- `asyncio.gather`
- `concurrent.futures`
- `event loop`
- `coroutine`

**Description:** Tests with timing-dependent failures or order-dependent behavior.

**Examples:**
- `"race condition detected"` → race_condition
- `"database deadlock detected"` → race_condition
- `"asyncio.gather: coroutine raised exception"` → race_condition
- `"event loop is closed"` → race_condition

**Note:** Patterns must appear in the error message or error type, not in test names. Test names containing "timing" do NOT indicate race conditions.

---

### 4. Other (`other`)

**Patterns:**
- Anything not matching the above patterns

**Description:** Tests with uncategorizable failures (e.g., syntax errors, import errors, pytest fixture issues).

**Examples:**
- `"ModuleNotFoundError: No module named 'playwright'"` → other
- `"IndentationError: unexpected indent"` → other
- `"ValueError: class fixtures not supported"` → other
- `"ImportError: cannot import name 'foo'"` → other
- `"SyntaxError: invalid syntax"` → other
- `"Failed: Marks cannot be applied to fixtures"` → other

**Note:** This is the default category for all non-matching error patterns.

---

## Important Implementation Notes

### False Positive Prevention

The categorization system was designed to prevent false positives by:

1. **Not analyzing test names**: Only error messages and error types are analyzed. Test names like `test_client_timings_api.py` do NOT indicate race conditions.

2. **Specific pattern matching**: The `race_condition` category requires specific concurrency-related keywords like `deadlock`, `asyncio.gather`, or `event loop`. Generic terms like "timeout" in import contexts are excluded.

3. **Error-type classification**: Classification is based on actual runtime error patterns, not test subject matter.

### Current Dataset Analysis

As of 2026-08-07, the failure frequency analysis of 33 failing tests showed:
- **connection_leak**: 0 tests (no connection pool exhaustion detected)
- **database_state**: 0 tests (no schema or constraint issues detected)
- **race_condition**: 0 tests (no concurrency issues detected)
- **other**: 33 tests (all failures due to code structure and import issues)

The "other" category failures consist of:
- ModuleNotFoundError (1 test): Missing dependency
- Failed (4 tests): Pytest fixture decorator misuse
- IndentationError (8 tests): Python syntax errors
- ValueError (12 tests): Pytest class fixtures not supported
- ImportError (4 tests): Import statement issues
- SyntaxError (4 tests): Invalid Python syntax

---

## Usage

The classification is performed by the script:
```bash
.venv/bin/python categorize_failures_root_cause.py
```

This script:
1. Loads the latest failure frequency matrix from `data/failure_frequency_*.json`
2. Analyzes each failure's error type and patterns
3. Outputs a categorized JSON report to `data/failure_categories_YYYYMMDD_HHMMSS.json`

---

## Source

Generated as part of bead adc-4n5mbx: "Categorize failure types by root cause"
Generated at: 2026-08-07T09:22:00.326601
Input data: `data/failure_frequency_20260807_091617.json`
