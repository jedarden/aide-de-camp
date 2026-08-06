# First-Failure Detection Logic - Completion Summary

**Bead:** adc-12bt — "Design first-failure detection logic"
**Date:** 2026-08-06
**Status:** COMPLETE

## Task Completed

Design HOW to detect the first failure vs subsequent failures and trigger notification only once.

## What Was Done

Verified and updated the comprehensive first-failure detection logic design document at:
`notes/adc-12bt-first-failure-detection-logic.md`

The design document provides complete coverage of:

### 1. Detection Logic with Clear Pseudo-code and Flow (✓)
- **Flow diagram** (§5.1) showing the complete detection lifecycle from send attempt through notification
- **Pseudo-code** (§5.2) for `_handle_send_failure()` and `_record_failure_locked()` with clear logic
- Structural rules from thread-safety design properly integrated

### 2. How "First" Is Determined (✓)
- **Claim-and-set pattern** (§2): "First" = the failure that performs `_has_logged_first_failure` False→True transition
- **Atomic operation** under lock ensures exactly one winner
- **Monotonic flag**: Once True, stays True for process lifetime
- **Not timestamp-based**: "First" is about who claims, not when they fail

### 3. Why Subsequent Failures Are Ignored (✓)
- **Core invariant** (§6): "Notify once per process startup"
- **Monotonic flag construction**: Once set, all later failures observe True and are suppressed
- **Diagnostics preserved**: DEBUG logs, `_failure_count`, and `_last_failure_timestamp` still updated
- **No notification spam**: Only the first failure triggers the alert channel

### 4. Edge Cases Considered (✓)
- **Intermittent/flapping failures** (§7.1): Once-per-startup semantic, recovery-based reset extension point
- **Config changes** (§7.2): Current lifecycle is safe by accident; future hot-reload needs reset
- **Failure classification** (§7.3): 4xx vs 5xx vs transport - sharp edge identified
- **Self-failure recursion guard** (§7.4): Notification must use side channel
- **Reset re-arms detection** (§7.5): `reset_first_failure_state()` mechanism
- **Notification failure** (§7.6): Flag stays True even if notify fails
- **Concurrent first failures** (§7.7): Lock makes claim atomic

## Key Design Decisions

### When to Check: Reactive Only
- **Decision**: Evaluate detection predicate only after actual send failure
- **Rejected**: Pre-send proactive probes (TOCTOU issues, adds latency)
- **Rationale**: Only real send failures are authoritative; probes would fire false positives

### Detection Location: Inside Failure Handler
- **Entry point**: `_handle_send_failure()` reached from 3 failure branches
- **Critical section**: Under `asyncio.Lock` for thread-safety
- **Notification outside lock**: Decision made inside lock, I/O after release

### First-Failure Definition: Claim-Based
- **Not timestamp-based**: "First" is not about earliest failure time
- **Claim-and-set**: The coroutine that flips False→True is "the first"
- **Exactly one winner**: Lock serialization guarantees this

### Thread-Safety Integration
- **Depends on**: adc-50ld (thread-safety design) - **NOW CLOSED**
- **Pattern**: `asyncio.Lock` + await-free `_record_failure_locked()`
- **Performance**: ~50-100µs overhead (acceptable on failure path)

## Alignment with Thread-Safety Design

Verified that the detection logic properly consumes the thread-safety approach from adc-50ld:
- Uses `asyncio.Lock` for serialization
- Calls await-free `_record_failure_locked()` for atomicity
- Captures `was_first` decision inside lock, does I/O after release
- Performance implications acknowledged (~50-100µs per failure)

## Acceptance Criteria Met

| Criterion | Status | Section |
|---|---|---|
| Detection logic documented with clear pseudo-code or flow | ✓ | §5 (flow + pseudo-code) |
| Explains how "first" is determined | ✓ | §2 (claim-and-set) + §4 (win/lose) |
| Explains why subsequent failures are ignored | ✓ | §6 (three reasons) |
| Considers edge cases (intermittent failures, config changes) | ✓ | §7.1–§7.7 |
| Depends on adc-50ld completing thread-safety design | ✓ | adc-50ld is CLOSED |

## Next Steps

The detection logic design is complete. Downstream beads can now:
1. **adc-14la**: Synthesize this with data-structure, storage, and thread-safety designs
2. **Implementation bead**: Use this design to implement the detection mechanism

## Files Modified

- `notes/adc-12bt-first-failure-detection-logic.md` - Updated date to 2026-08-06 for thread-safety alignment

## References

- Detection logic: `notes/adc-12bt-first-failure-detection-logic.md`
- Thread-safety: `notes/adc-50ld-thread-safety-design.md` (updated 2026-08-06)
- Data structure: `notes/adc-65l3-first-failure-state-structure.md`
- Storage: `notes/adc-2duz-state-storage-design.md`
- Current code: `src/telegram/fallback.py`
