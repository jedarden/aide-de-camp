# First-Failure Detection Logic Design

**Bead:** adc-12bt
**Parent:** adc-4vhr
**Dependency:** adc-50ld (Thread-Safety Design)

## Overview

Design a mechanism to detect the **first failure** for async bead-backed tasks and trigger notifications **once per failure type**, suppressing redundant notifications for subsequent failures of the same type.

## Problem Statement

The async path creates NEEDLE beads for task-profile intents. These beads can fail in multiple ways:

1. **Refusal** - Bead comments contain `REFUSED:` indicating blocker
2. **SLA breach** - Bead exceeds its time budget without resolution
3. **Circuit breaker** - Bead hits refusal threshold (3 refusals or 24h age)

Without first-failure detection:
- The system would emit a notification on **every** BeadWatcher tick
- Users receive spam for the same underlying failure
- No way to distinguish "new problem" from "existing problem"

## Design Goals

1. **Notify once per failure type** - First time a bead hits a failure state, emit notification
2. **Suppress subsequent notifications** - Same bead, same failure type = silence
3. **Handle state transitions** - If bead recovers then fails again with NEW failure type, notify
4. **Thread-safe** - Multiple watcher ticks must race safely (depends on adc-50ld design)
5. **Config-aware** - If fetch config changes, reset suppression for affected sources

## Core Concepts

### Failure Type Taxonomy

Each failure maps to a distinct **failure type**:

| Failure Type | Trigger Condition | Notification Template |
|--------------|-------------------|----------------------|
| `refusal` | `bead_watch.last_refusal_reason IS NOT NULL` | "Bead {bead_ref} blocked: {reason}" |
| `sla_flag` | `bead_watch.sla_flagged_at IS NOT NULL` | "Bead {bead_ref} exceeded SLA" |
| `fenced` | `bead_watch.fenced_at IS NOT NULL` | "Bead {bead_ref} fenced (circuit breaker)" |
| `dispatch_failed` | `intent.status = 'failed'` | "Intent {intent_id} dispatch failed" |
| `fetch_terminal` | `fetch_result.terminal_failure = 'all_sources_failed'` | "All fetch sources failed for {project_slug}" |

### First-Failure State Tracking

**Key concept:** Track failure state **per bead** as a **bitfield** of emitted failure types.

```python
# bead_watch table schema (existing)
CREATE TABLE bead_watch (
    bead_ref           TEXT PRIMARY KEY,
    refusal_count      INTEGER NOT NULL DEFAULT 0,
    last_refusal_reason TEXT,
    last_refusal_at    INTEGER,
    comment_high_water INTEGER NOT NULL DEFAULT -1,
    sla_deadline       INTEGER NOT NULL,
    sla_flagged_at     INTEGER,
    fenced_at          INTEGER,
    created_at         INTEGER NOT NULL,
    -- NEW COLUMN for first-failure tracking:
    emitted_failures   INTEGER DEFAULT 0  -- Bitfield: 1=refusal, 2=sla, 4=fenced, 8=dispatch, 16=fetch
);
```

**Bitfield encoding:**

```python
FAILURE_BITREFUSAL = 1      # 0b00001
FAILURE_BIT_SLA = 2         # 0b00010
FAILURE_BIT_FENCED = 4      # 0b00100
FAILURE_BIT_DISPATCH = 8    # 0b01000
FAILURE_BIT_FETCH = 16      # 0b10000
```

**State diagram:**

```
initial: emitted_failures = 0
  |
  v
refusal detected → bit 0 set → emit "refusal" notification → emitted_failures = 1
  |
  v (subsequent ticks)
refusal still true → bit 0 already set → suppress notification
  |
  v
sla_flagged detected → bit 1 set → emit "sla" notification → emitted_failures = 3
  |
  v
bead closed → row deleted → state reset
```

## Detection Logic

### Check Points

Two check points ensure comprehensive coverage:

#### 1. Pre-Escalation Check (Before Bead Creation)

**Location:** `escalate/handler.py` - `escalate_intent()`

**Purpose:** Catch dispatch failures **before** bead is created

**Pseudo-code:**

```python
async def escalate_intent(request: EscalateRequest) -> str:
    """
    Escalate intent to NEEDLE bead, with pre-flight failure detection.
    """
    # Check if we've already notified about a dispatch failure for this intent
    store = get_store()
    intent = await store.get_intent(request.intent_id)

    # Check for existing failure notification (by intent_id, not bead_ref yet)
    # We use a separate table for intent-level failures because bead doesn't exist yet
    emitted = await store.get_emitted_intent_failures(request.intent_id)

    # If intent already failed and we notified, skip escalation
    # (This prevents retry spam on truly dead dispatches)
    if emitted & FAILURE_BIT_DISPATCH:
        logger.warning(f"Intent {request.intent_id} already marked as dispatch-failed, skipping escalation")
        return None

    # ... rest of escalation logic ...

    # If escalation fails (e.g., bf create fails):
    # 1. Mark intent as failed
    await store.update_intent_status(intent.id, "failed")
    # 2. Check if we should notify
    if not (emitted & FAILURE_BIT_DISPATCH):
        # 3. Emit notification (broadcast to fallback surface)
        await broadcast_first_failure(
            intent_id=intent.id,
            session_id=intent.session_id,
            failure_type="dispatch_failed",
            reason="Bead creation failed"
        )
        # 4. Mark as notified
        await store.mark_intent_failure_emitted(intent.id, FAILURE_BIT_DISPATCH)
```

#### 2. Post-Fetch Check (After Fetch Execution)

**Location:** `intent/router.py` - `process_intent()` after `execute_fetch()`

**Purpose:** Detect terminal fetch failures and notify

**Pseudo-code:**

```python
async def process_intent(intent: RoutedIntent, context: FetchContext) -> None:
    """
    Process intent through fetch + synthesize strands with failure detection.
    """
    # Execute fetch
    fetch_result = await execute_fetch(
        request=FetchRequest(
            intent_type=intent.intent_type,
            context=context,
            intent_id=intent.intent_id,
            session_id=intent.session_id,
        )
    )

    # Check for terminal failure (all sources failed)
    if fetch_result.terminal_failure == "all_sources_failed":
        # Get or create bead watch row (even for hot-path intents, we track fetch failures)
        store = get_store()
        bead_watch = await store.get_bead_watch_by_intent(intent.intent_id)

        # Check if we've already notified about fetch failure for this bead
        emitted = bead_watch.get("emitted_failures", 0) if bead_watch else 0

        if not (emitted & FAILURE_BIT_FETCH):
            # First time seeing this failure → emit notification
            await broadcast_first_failure(
                intent_id=intent.intent_id,
                session_id=intent.session_id,
                failure_type="fetch_terminal",
                reason=f"All {fetch_result.coverage.total_sources} fetch sources failed",
                context={
                    "timed_out": fetch_result.coverage.timed_out,
                    "failed": fetch_result.coverage.failed,
                }
            )

            # Update emitted_failures bitfield
            await store.update_bead_watch_emitted_failures(
                bead_ref=intent.bead_ref or f"intent:{intent.intent_id}",
                failure_bit=FAILURE_BIT_FETCH
            )
```

#### 3. BeadWatcher Tick Check (During Background Polling)

**Location:** New `bead/watcher.py` - `BeadWatcher.tick()`

**Purpose:** Detect refusal, SLA, and fencing failures

**Pseudo-code:**

```python
class BeadWatcher:
    """
    Watches open NEEDLE beads for failure conditions.
    """

    async def tick(self) -> None:
        """
        Single tick: check all watched beads for failures, notify on first detection.
        """
        store = get_store()
        watched_beads = await store.get_open_watched_beads()

        for bead in watched_beads:
            bead_ref = bead["bead_ref"]
            emitted_failures = bead.get("emitted_failures", 0)

            # Check 1: Refusal detection
            if bead.get("last_refusal_reason") and not (emitted_failures & FAILURE_BIT_REFUSAL):
                await self._handle_refusal(bead, emitted_failures)

            # Check 2: SLA breach detection
            elif bead.get("sla_flagged_at") and not (emitted_failures & FAILURE_BIT_SLA):
                await self._handle_sla_breach(bead, emitted_failures)

            # Check 3: Fencing detection (circuit breaker)
            elif bead.get("fenced_at") and not (emitted_failures & FAILURE_BIT_FENCED):
                await self._handle_fencing(bead, emitted_failures)

    async def _handle_refusal(self, bead: dict, emitted_failures: int) -> None:
        """Handle first refusal detection."""
        bead_ref = bead["bead_ref"]
        intent = await store.get_intent_by_bead_ref(bead_ref)

        # Emit notification to fallback surface (Telegram)
        await broadcast_first_failure(
            intent_id=intent["id"] if intent else None,
            session_id=intent["session_id"] if intent else None,
            failure_type="refusal",
            reason=bead["last_refusal_reason"],
            context={
                "bead_ref": bead_ref,
                "refusal_count": bead["refusal_count"],
            }
        )

        # Mark as notified
        await store.update_bead_watch_emitted_failures(
            bead_ref=bead_ref,
            failure_bit=FAILURE_BIT_REFUSAL
        )

    async def _handle_sla_breach(self, bead: dict, emitted_failures: int) -> None:
        """Handle first SLA breach detection."""
        # Similar pattern to _handle_refusal
        await store.update_bead_watch_emitted_failures(
            bead_ref=bead["bead_ref"],
            failure_bit=FAILURE_BIT_SLA
        )

    async def _handle_fencing(self, bead: dict, emitted_failures: int) -> None:
        """Handle first fencing detection."""
        # Similar pattern to _handle_refusal
        await store.update_bead_watch_emitted_failures(
            bead_ref=bead["bead_ref"],
            failure_bit=FAILURE_BIT_FENCED
        )
```

## Thread-Safety Considerations

**Dependency:** adc-50ld (Thread-Safety Design)

The detection logic relies on the thread-safety patterns designed in adc-50ld:

1. **SQLite write locking** - `aiosqlite` with WAL mode allows concurrent reads, serialized writes
2. **Compare-and-swap pattern** - Update emitted_failures only if bit not set:

```sql
-- Atomic test-and-set for failure bit
UPDATE bead_watch
SET emitted_failures = emitted_failures | ?
WHERE bead_ref = ? AND (emitted_failures & ?) = 0;
```

If `rowcount == 0`, another tick already set the bit → skip notification.

3. **Intent-level lock** - For pre-escalation checks, use intent_id as lock key:

```python
async def check_and_notify_dispatch_failure(intent_id: str) -> bool:
    """Check if dispatch failure already notified, emit if not. Returns True if notified."""
    async with _intent_locks.setdefault(intent_id, asyncio.Lock()):
        # Double-checked locking pattern
        emitted = await store.get_emitted_intent_failures(intent_id)
        if emitted & FAILURE_BIT_DISPATCH:
            return False  # Already notified by another coroutine

        # Emit notification
        await broadcast_first_failure(...)
        await store.mark_intent_failure_emitted(intent_id, FAILURE_BIT_DISPATCH)
        return True
```

## Edge Cases

### 1. Intermittent Failures

**Scenario:** Bead is refused, user resolves the blocker, bead gets refused again later.

**Handling:** Emitted failures persist **per bead watch row**. If bead is closed and reopened, state resets.

**Flow:**
```
1. Bead refused → emitted_failures = 1 → notify
2. User resolves → refusal cleared → emitted_failures stays 1 (no reset)
3. Bead refused again → bit already set → suppress
```

**Rationale:** "First failure" means "first time we saw this failure type for this bead watch instance". If the same bead keeps failing with the same reason, the user already knows about it from the first notification.

### 2. Config Changes

**Scenario:** `config/fetch.yaml` changes, timeout adjusted, previously-failing source now succeeds.

**Handling:** Emitted failures are **not** tied to config version. If a source starts working again, we don't auto-reset because the user may have already taken action based on the first notification.

**Optional enhancement:** Add a config_version column to bead_watch and auto-reset on config change (future work).

### 3. Bead Resolution Changes

**Scenario:** Bead is reassigned to different intent, or bead_ref changes.

**Handling:** `bead_ref` is the primary key. If bead_ref changes:
1. Old row deleted (or manual update)
2. New row created with `emitted_failures = 0`
3. New failures trigger fresh notifications

**User action:** Manual `bf update --bead-ref <new-id>` creates new watch row.

### 4. Multiple Failure Types

**Scenario:** Bead hits refusal, then SLA breach, then fencing.

**Handling:** Each failure type is a separate bit:

```
emitted_failures = 0
  → refusal detected → bit 0 set → emitted_failures = 1 → notify refusal
  → SLA breached → bit 1 set → emitted_failures = 3 → notify SLA
  → fenced → bit 2 set → emitted_failures = 7 → notify fencing
```

**Result:** User receives **three distinct notifications**, one per failure type.

## Notification Payload

**Structure:** `SSEEvent` with `event_type="first_failure"`

```python
{
    "event_type": "first_failure",
    "data": {
        "failure_type": "refusal" | "sla_flag" | "fenced" | "dispatch_failed" | "fetch_terminal",
        "bead_ref": str,
        "intent_id": str,
        "session_id": str,
        "reason": str,
        "context": {
            # Failure-specific metadata
            "refusal_count": int,
            "sla_deadline": int,
            "timed_out_sources": list[str],
            "failed_sources": list[str],
        },
        "notified_at": int,  # Unix timestamp
    }
}
```

**Broadcast targets:**
1. **Session surfaces** - All active surfaces for the session
2. **Fallback surface** - Telegram (always, for critical failures)

## Implementation Checklist

- [ ] Add `emitted_failures INTEGER DEFAULT 0` column to `bead_watch` table migration
- [ ] Add `intent_failures` table for pre-bead dispatch failure tracking
- [ ] Implement `broadcast_first_failure()` in `src/sse/broadcaster.py`
- [ ] Implement pre-escalation check in `src/escalate/handler.py`
- [ ] Implement post-fetch check in `src/intent/router.py`
- [ ] Implement BeadWatcher checks in new `src/bead/watcher.py`
- [ ] Add thread-safety locks from adc-50ld design
- [ ] Write tests for first-failure detection edge cases
- [ ] Add logging for first-failure events (INFO level)

## Why This Works

1. **Bitfield state** enables efficient per-type tracking without separate columns
2. **Atomic test-and-set** prevents duplicate notifications under concurrency
3. **Separate check points** cover all failure entry points
4. **Persistent state** survives watcher restarts
5. **Graceful degradation** - if state is lost, worst case is duplicate notification (not silent failure)

## Open Questions

1. **State reset on bead close:** Should we auto-delete bead_watch row when bead closes, or keep for audit trail?
   - **Recommendation:** Delete on close to avoid stale state accumulation

2. **Notification dedupe window:** Should we add a time-based dedupe window (e.g., "same failure type within 1 hour")?
   - **Recommendation:** No - bitfield is simpler and sufficient

3. **Fetch failure granularity:** Should we track per-source failures, or only "all sources failed"?
   - **Recommendation:** Only terminal failure for now; per-source tracking is future enhancement
