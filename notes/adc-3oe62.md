# Task Already Completed: Bead Watch Table and Intents Status Enum

## Task: Add bead_watch table and intents status enum (adc-3oe62)

**Status**: ✅ **ALREADY COMPLETED**

## Verification

All acceptance criteria have been met:

### 1. ✅ Migration script adds table and enum values

**bead_watch table schema** (src/session/store.py, lines 202-221):
- `bead_ref` (PK, references beads.id)
- `refusal_count INTEGER DEFAULT 0`
- `last_refusal_reason TEXT`
- `last_refusal_at INTEGER`
- `comment_high_water INTEGER DEFAULT 0`
- `sla_deadline INTEGER`
- `sla_flagged_at INTEGER`
- `fenced_at INTEGER`
- Plus required indexes

**intents.status enum extension** (src/session/store.py, line 239):
- Added 'stuck' - bead fenced after threshold violations
- Added 'failed' - terminal failure with reason

**Migration logic** (src/session/store.py, lines 299-393):
- `_migrate_intents_status_enum()` - Handles enum migration for existing databases
- `_migrate_additive_columns()` - Idempotently adds new columns
- Table recreation when constraint changes are needed

### 2. ✅ Tests verify schema creation

**Test suite**: tests/test_circuit_breaker.py

**TestSchemaAndMigration class** (lines 502-641):
- `test_bead_watch_table_has_required_columns` ✅ PASSED
- `test_bead_watch_indexes_created` ✅ PASSED
- `test_intents_status_enum_includes_stuck_and_failed` ✅ PASSED
- `test_intents_status_can_be_set_to_stuck` ✅ PASSED
- `test_intents_status_can_be_set_to_failed` ✅ PASSED
- `test_intent_statuses_constant_matches_schema` ✅ PASSED

**TestBeadWatchLifecycle class** (lines 159-247):
- `test_create_bead_watch_defaults` ✅ PASSED
- `test_create_bead_watch_with_custom_sla` ✅ PASSED
- `test_update_refusal_increments_count` ✅ PASSED
- `test_fence_bead_sets_timestamp` ✅ PASSED
- `test_delete_bead_watch_removes_row` ✅ PASSED

### 3. ✅ Documentation updated

**docs/plan/plan.md** already contains:
- Line 85: bead_watch table usage for circuit breaker
- Line 87: SLA deadline tracking in bead_watch
- Line 367: Breaker state persistence in bead_watch
- Line 524: Data model reference
- References to 'stuck' and 'failed' statuses throughout

## Test Results

All schema and migration tests pass successfully:

```bash
$ .venv/bin/python -m pytest tests/test_circuit_breaker.py::TestSchemaAndMigration -xvs
======================== 6 passed in 0.17s =========================

$ .venv/bin/python -m pytest tests/test_circuit_breaker.py::TestBeadWatchLifecycle -xvs
======================== 5 passed in 0.12s =========================
```

## Implementation Status

The bead_watch table schema, intents status enum extension, migration scripts, tests, and documentation were already implemented in the codebase. No additional work was required.

**Bead**: adc-3oe62
**Date**: 2026-07-23
