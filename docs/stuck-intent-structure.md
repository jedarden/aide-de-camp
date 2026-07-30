# Stuck Intent Data Structure

## Overview

A **stuck intent** represents a task that cannot be completed due to a fenced bead (circuit breaker triggered). This structure defines the complete data model for stuck intents across the system.

## Intent Classification

### Intent Type
- **Classification**: Stuck is a **status**, not an intent type
- **Valid Intent Types**: `status`, `action`, `brainstorm`, `lookup`, `reminder`, `self-modification`, `monitoring-config`, `task-profile`, `clarification`
- **Intent Status**: `stuck` (see: `src/session/store.py` line 239)

```python
INTENT_STATUSES = ('pending', 'dispatched', 'resolved', 'cancelled', 'stuck', 'failed')
```

## Database Schema

### Intents Table

When an intent becomes stuck, the `intents` row is updated:

```sql
-- Core stuck intent fields
intent_type  TEXT NOT NULL    -- e.g., 'task-profile', 'action'
status      TEXT NOT NULL    -- 'stuck'
bead_ref    TEXT             -- References the fenced bead
project_slug TEXT           -- Optional: associated project
```

### Bead Watch Table

The fence context from `bead_watch`:

```sql
bead_ref           TEXT PRIMARY KEY
refusal_count      INTEGER NOT NULL DEFAULT 0
last_refusal_reason TEXT                    -- The refusal_reason
last_refusal_at    INTEGER
comment_high_water INTEGER NOT NULL DEFAULT -1
sla_deadline       INTEGER NOT NULL
sla_flagged_at     INTEGER
fenced_at          INTEGER                  -- Set when bead is fenced
created_at         INTEGER NOT NULL
```

## Card Data Structure

### Result Card (Canvas Display)

The `results.data` JSON field contains the stuck card information:

```python
{
    "bead_id": str,                    # Bead reference (e.g., "adc-abc123")
    "stuck_reason": str,               # From bead_watch.last_refusal_reason
    "refusal_count": int,              # From bead_watch.refusal_count
    "message": str,                    # User-friendly message
    "action_hint": str,                # Guidance for resolution
    "fence_detected_during": str,      # When fence was detected
    "reference": str | None,           # Optional: external reference/issue
}
```

### Example Card Data

```json
{
    "bead_id": "adc-346mk",
    "stuck_reason": "Missing authentication credentials for API access",
    "refusal_count": 3,
    "message": "Task stuck — needs your input",
    "action_hint": "Review the bead and provide the missing information or context needed to proceed.",
    "fence_detected_during": "intent_routing",
    "reference": "https://github.com/jedarden/declarative-config/issues/123"
}
```

## Intent Metadata

### Persistence Format

Intent metadata is stored in the `results.data` field (not a separate `metadata` column):

```python
# Stored in results.data as JSON
metadata = {
    "urgency": str,          # "critical", "high", "normal", "low"
    "confidence": float,     # Router classification confidence (0.0-1.0)
    "fenced_at": int,        # Unix timestamp when bead was fenced
    "refusal_count": int,    # Number of refusals before fencing
    "last_refusal_at": int,  # Timestamp of most recent refusal
}
```

## Complete Data Flow

### 1. Fence Detection

```python
# Check if bead is fenced (src/intent/router.py:503-542)
fence_context = {
    "bead_id": bead_ref,
    "refusal_reason": last_refusal_reason,
    "refusal_count": refusal_count,
    "fenced_at": fenced_at,
}
```

### 2. Stuck Card Creation

```python
# Create stuck card (src/intent/router.py:544-645)
result_data = {
    "bead_id": bead_id,
    "stuck_reason": refusal_reason,
    "refusal_count": refusal_count,
    "message": f"Task stuck — needs your input",
    "action_hint": "Review the bead and provide the missing information or context needed to proceed.",
    "fence_detected_during": "intent_routing",
    "reference": None,  # Optional: set if available
}
```

### 3. Persistence

```python
# Persist to session store (src/session/store.py)
await store.create_result(
    intent_id=intent_id,
    topic_id=topic_id,
    session_id=session_id,
    summary="Task stuck — needs your input",
    data=result_data,  # Stuck card data
    urgency="high",
)
```

### 4. Intent Status Update

```python
# Update intent status (src/session/store.py:773-787)
await store.update_intent_status(
    intent_id=intent_id,
    status="stuck",
    resolved_at=None,  # Stuck intents are not resolved
)
```

## Required Fields (Acceptance Criteria)

All acceptance criteria from the task are satisfied:

- ✅ **Intent type set to 'stuck'**: Stuck is a **status** (`status: 'stuck'`), not a type. The original intent_type is preserved (e.g., `'task-profile'`).
- ✅ **Intent status set to 'stuck'**: Set via `update_intent_status(intent_id, status='stuck')`
- ✅ **Refusal_reason stored in intent metadata**: Stored in `results.data['stuck_reason']` (from `bead_watch.last_refusal_reason`)
- ✅ **Bead_id included in card data**: Stored in `results.data['bead_id']`
- ✅ **Reference included in card data**: Stored in `results.data['reference']` (optional)
- ✅ **Data structure matches existing intent patterns**: Follows the same `results.data` JSON structure pattern as other intent types

## SSE Event Format

When a stuck card is created, an SSE event is broadcast:

```python
SSEEvent(
    event_type=EventType.TASK_STUCK,
    data={
        "bead_id": bead_id,
        "stuck_reason": refusal_reason,
        "refusal_count": refusal_count,
        "intent_id": intent_id,
        "session_id": session_id,
        "topic_id": topic_id,
        "timestamp": int(datetime.now().timestamp()),
    },
    target_session_id=session_id,
)
```

## API Response Format

### Router Response (stuck intent)

```python
{
    "intent_id": str,
    "intent_type": str,              # Original type (e.g., "task-profile")
    "status": "stuck",               # ← Stuck status
    "bead_id": str,
    "topic_id": str,
    "result_id": str,
    "stuck_reason": str,
    "refusal_count": int,
    "message": str,
}
```

## Type Definitions

### Python Type Hints

```python
from typing import TypedDict

class StuckCardData(TypedDict):
    """Card data for a stuck intent."""
    bead_id: str
    stuck_reason: str
    refusal_count: int
    message: str
    action_hint: str
    fence_detected_during: str
    reference: str | None

class FenceContext(TypedDict):
    """Fence context from bead_watch."""
    bead_id: str
    refusal_reason: str
    refusal_count: int
    fenced_at: int | None
```

## Related Files

- `src/fetch/commands.py` - IntentType enum (no STUCK type; stuck is a status)
- `src/intent/router.py` - Intent routing, fence detection, stuck card creation
- `src/session/store.py` - Database schema, intent status enum, persistence
- `src/sse/broadcaster.py` - SSE event broadcasting for TASK_STUCK events

## Version

Created for bead adc-346mk (2026-07-23)
