# Bead Starvation Alert Investigation (adc-46cn)

## Problem

Open beads existed but Pluck found none — potential configuration error.

**Reported state:**
- Total beads: 96
- Open: 33  
- In-progress: 2
- Claimed by: claude-code-glm-4.7-juliet

## Root Cause Analysis

### 1. Database/JSONL Sync Issue

The primary issue was that the JSONL checkpoint (`.beads/issues.jsonl`) was **stale** and out of sync with the live database.

**Before fix:**
- Database: 98 beads (33 open)
- JSONL: Only 5 beads total (3 open, 2 blocked)

This meant any bead-worker reading from the JSONL checkpoint would see a dramatically reduced bead pool.

### 2. Label Filtering

Even with correct data, the effective "workable" bead pool is smaller than the total open count:

**Out of 33 open beads:**
- 27 beads have exclusion labels (`deferred`, `split-child`, `umbrella`)
- Only 6 beads are truly workable (no exclusion labels)

**Workable open beads:**
- adc-1sb
- adc-1ua  
- adc-3rt
- adc-4iq
- adc-5kp
- adc-zec

Bead-workers typically exclude beads with these labels:
- `deferred` — explicitly deferred from work
- `split-child` — child tasks of split operations
- `umbrella` — parent tasks that shouldn't be directly worked
- `failure-count:N` — failed beads with retry limiting

## Solution Applied

### 1. Flush Database to JSONL

```bash
br sync --flush-only
```

This synced the live database (98 beads) to the JSONL checkpoint, updating it from 5 beads to 98 beads.

### 2. Verify Database Integrity

```bash
sqlite3 .beads/beads.db "PRAGMA integrity_check;"
# Result: ok
```

The database was healthy, so the flush was safe.

## Prevention

### Regular Flushes

The JSONL checkpoint can become stale when:
- Beads are created/modified in the database but not flushed
- Workers read from stale JSONL instead of live database

**Solution:** Run `br sync --flush-only` periodically, especially after bulk operations.

### Before Running `br doctor --repair`

**IMPORTANT:** Always flush before repair:

```bash
br sync --flush-only                    # 1. Checkpoint db → JSONL
sqlite3 .beads/beads.db "PRAGMA integrity_check;"  # 2. True check
br doctor --repair                      # 3. Only now, if needed
```

Running `br doctor --repair` rebuilds the database FROM the JSONL, so any unflushed beads would be lost.

## Verification

After the fix:
- JSONL now contains 98 beads (matching database)
- Status distribution matches: 17 blocked, 29 closed, 15 completed, 3 in_progress, 33 open, 1 resolved
- 6 workable open beads available for worker pickup

## Outcome

The starvation alert was caused by the JSONL checkpoint being stale. The flush operation resolved it, and the bead-worker should now be able to find and claim the 6 workable open beads.

## Related

- Bead ID: adc-46cn  
- Applied: 2026-07-06
- Worker: claude-code-glm-4.7-juliet
