# Async Circuit Breaker Implementation (adc-2fpj)

## Status: ✅ COMPLETE

This bead implemented the async circuit breaker system for preventing infinite worker loops on unscoped tasks.

## What Was Implemented

### 1. bead_watch Table (Data Persistence)
- **Schema**: `bead_watch` table in session.db with all required columns:
  - `bead_ref` (PK) - references bead ID
  - `refusal_count` - number of REFUSED: comments seen
  - `last_refusal_reason` - most recent refusal reason
  - `last_refusal_at` - timestamp of most recent refusal
  - `comment_high_water` - latest comment index processed (-1 = none)
  - `sla_deadline` - Unix timestamp when SLA expires
  - `sla_flagged_at` - timestamp when SLA was flagged (NULL if not flagged)
  - `fenced_at` - timestamp when bead was fenced to status=blocked (NULL if not fenced)
  - `created_at` - when this watch row was created
- **Persistence**: All circuit breaker state lives in the database, surviving watcher restarts

### 2. Refusal Signal Detection
- **Worker convention**: Workers append `REFUSED: <reason>` comments via bf CLI
- **Watcher polling**: Each tick runs `bf show` on open tracked beads
- **Comment parsing**: `_parse_refusals_from_comments()` extracts REFUSED: comments past the high-water mark
- **State tracking**: `update_bead_watch_refusal()` persists refusal counts and reasons

### 3. Circuit Breaker Thresholds
- **Constants defined**:
  - `CIRCUIT_BREAKER_REFUSAL_THRESHOLD = 3` - fence after N refusals
  - `CIRCUIT_BREAKER_AGE_THRESHOLD_HOURS = 24.0` - fence after N hours without progress
- **Fencing logic**:
  - 3 refusals OR 24h age triggers fencing
  - Fence action: `bf update --status blocked <bead_ref>`
  - Intent status set to 'stuck'
  - Stuck card pushed with latest refusal reason

### 4. Terminal Failure Handling
- **Intent status enum extended**: 'stuck' and 'failed' added
- **Failure detection**: When beads close with 'failed' or 'refused' status
- **Reason surfacing**: Extract latest REFUSED comment reason
- **Result creation**: Failed cards include failure_reason in data
- **Status updates**: Intents marked as 'failed', 'cancelled', or 'resolved' based on bead status

### 5. SLA Tracking and Flagging
- **Default SLA per intent type** (`DEFAULT_SLA_HOURS`):
  - `task-profile`: 6h (async bead-backed tasks)
  - `status`, `action`, `lookup`: 30s (hot-path intents)
  - `brainstorm`: 30m
  - `reminder`: 24h
- **Deadline tracking**: `sla_deadline` computed at bead creation
- **Flagging**: `_check_and_flag_sla_beads()` flags beads past deadline
- **Visible aging**: Flagged beads show visual age indicator

### 6. Intent Status Migration
- **Database migration**: `_migrate_intents_status_enum()` handles enum extension
- **Backward compatibility**: Existing databases migrated on startup
- **Status values**: ('pending', 'dispatched', 'resolved', 'cancelled', 'stuck', 'failed')

## Test Coverage

All acceptance criteria met:
- ✅ 3 REFUSED comments trip the fence + stuck card
- ✅ 24h age trips the fence
- ✅ Counts survive a watcher restart
- ✅ Enum migration covered

**Test file**: `tests/test_circuit_breaker.py` - 24 tests passing:
- `TestRefusalParsing` - REFUSED: comment parsing (7 tests)
- `TestBeadWatchLifecycle` - bead_watch row lifecycle (5 tests)
- `TestSLATracking` - SLA deadline tracking and flagging (3 tests)
- `TestCircuitBreakerThresholds` - fencing thresholds (5 tests)
- `TestSLADefaults` - constants verification (2 tests)
- `TestCircuitBreakerIntegration` - end-to-end integration (2 tests)

## Key Files Modified

1. **`src/session/store.py`**
   - Added `bead_watch` table schema
   - Implemented circuit breaker CRUD methods
   - Added migration for intents.status enum extension
   - Defined SLA and circuit breaker constants

2. **`src/watcher/daemon.py`**
   - Implemented `_check_circuit_breaker()` - main circuit breaker tick
   - Implemented `_parse_refusals_from_comments()` - REFUSED: comment extraction
   - Implemented `_fence_needs_fencing_beads()` - fencing logic
   - Implemented `_check_and_flag_sla_beads()` - SLA tracking
   - Implemented `_fence_bead()` - single bead fencing with stuck card creation
   - Enhanced `_process_bead_event()` - terminal failure handling
   - Enhanced `_extract_result_from_bead()` - failure reason extraction

3. **`src/intent/router.py`**
   - Extended `IntentType` enum with `STUCK`
   - Implemented stuck card detection during intent routing
   - Implemented `_create_stuck_card_from_fence()` - stuck card creation

## Verification

Run the test suite:
```bash
.venv/bin/pytest tests/test_circuit_breaker.py -v
```

Expected: 24 passed

## Deployment Notes

- **Database migration**: Runs automatically on first startup after deployment
- **Backward compatibility**: Existing data migrated safely
- **Rollback safety**: Migration is additive (new columns, enum values)
- **No downtime**: Circuit breaker state persisted across restarts

## Related Beads

- `adc-2wzri` - Stuck card UI and failure handling
- `adc-5036z` - Stuck intent detection and escalate handler integration
- `adc-5i9kp` - Integration tests for stuck and failed card flows

## Conclusion

The async circuit breaker is fully implemented and tested. It prevents the July 2024 incident pattern (workers looped refusing an unscoped 'kubectl delete pod' bead with no breaker) by:

1. Tracking refusals persistently in the database
2. Fencing beads after 3 refusals or 24h age
3. Creating stuck cards with actionable reasons
4. Handling terminal failures with proper status tracking
5. Providing visible aging via SLA flagging

All code has been committed and pushed to the remote repository. Bead closed.
