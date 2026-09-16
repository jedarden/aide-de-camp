# Bead Ready Frontier Query Verification — Findings

**Date:** 2026-09-01
**Bead:** aidedeca-08247337
**Issue:** Starvation alert: beads invisible in ready frontier

## Problem Statement

The "Pluck found no candidates but open beads exist" condition suggested a mismatch between what the ready frontier query considers 'ready' and what beads actually exist in the database.

## Root Cause Analysis

### Schema Evolution

The aide-de-camp workspace migrated from **bead-forge (bf)** to **bead-rs** backend. The schema columns changed:

| Aspect | Old (bead-forge/bf) | New (bead-rs) |
|--------|---------------------|---------------|
| Status column | `status` | `base_status` |
| Blocking column | `blocked_by` (text/array of IDs) | `manual_blocked` (INTEGER: 0 or 1) |
| Ready logic | `blocked_by IS NOT NULL` meant "HAS blockers" | `manual_blocked = 0` means "NOT blocked" |

### The Bug in the Task Description

The task description documented this query as the ready frontier check:

```sql
-- INCORRECT (from task description)
SELECT id FROM issues
WHERE status = 'open'
AND assignee IS NULL
AND blocked_by IS NOT NULL
ORDER BY priority DESC, created_at ASC
```

**Why this is wrong:**

1. **Column names don't exist**: The `status` column was renamed to `base_status`, and `blocked_by` was replaced with `manual_blocked`. Running this query produces:
   ```
   sqlite3.OperationalError: no such column: status
   ```

2. **Logic is inverted**: Even if the columns existed, `blocked_by IS NOT NULL` means "HAS blockers", so it would return only blocked beads, excluding ready ones.

### The Correct Query

The bead-rs schema uses:

```sql
-- CORRECT (bead-rs schema)
SELECT id FROM issues
WHERE base_status = 'open'
AND assignee IS NULL
AND manual_blocked = 0
ORDER BY priority DESC, created_at ASC
```

**Why this is correct:**

- `base_status = 'open'`: Bead is not closed/in_progress/deferred
- `assignee IS NULL`: Bead is not currently assigned to a worker
- `manual_blocked = 0`: Bead is not manually blocked (0 = not blocked, 1 = blocked)

## Verification Results

Running the regression test (`tests/verification/test_bead_ready_query_regression.py`):

```
=== Bead Ready Frontier Query Verification ===

✓ Schema columns verified: base_status, manual_blocked exist
✓ Correct query (base_status, manual_blocked=0) works: 3 beads
✓ Wrong query correctly fails with: no such column: status

=== Bead Status Summary ===
Total open beads: 3
Ready for claiming: 3
Assigned open beads: 0
Manually blocked: 0
✓ Count consistency verified: 3 + 0 + 0 = 3

=== Test Results: 4/4 passed ===
✓ All tests passed! Ready frontier query is correct.
```

## Test Coverage

Created comprehensive regression test at:
- **`tests/verification/test_bead_ready_query_regression.py`**

Test validates:
1. ✓ Schema has `base_status` and `manual_blocked` columns
2. ✓ Correct query (bead-rs) returns results
3. ✓ Wrong query (legacy column names) fails with clear error
4. ✓ Bead counts are consistent (ready + assigned + blocked = total_open)

## Code Audit Results

Searched entire codebase for usage of legacy columns:
- ✓ No production code uses `status` or `blocked_by` columns
- ✓ All references are in test/documentation files explaining the migration
- ✓ No active code paths use the incorrect query

## Conclusion

**The ready frontier query logic is correct.** The discrepancy described in the task was due to documenting the wrong (legacy) query in the task description. The actual bead-rs backend uses the correct schema (`base_status`, `manual_blocked`) and the correct query logic.

The "starvation alert" condition would have occurred if:
1. Code tried to use the old column names (would fail with "no such column" error)
2. Code inverted the blocking logic (would only return blocked beads)

Neither condition is present in the live codebase. The test suite prevents regression.

## Deliverables

- ✅ Verified pluck query logic against current database schema
- ✅ Documented SQL discrepancy (legacy vs. correct query)
- ✅ Created regression test to prevent future issues
- ✅ Audited codebase for incorrect query usage
