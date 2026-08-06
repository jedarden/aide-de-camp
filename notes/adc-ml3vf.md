# SSE Implementation Analysis: /dispatch Endpoint

## Overview

This document analyzes the existing Server-Sent Events (SSE) implementation in the `/dispatch` endpoint to document the pattern that needs to be replicated elsewhere.

## Files Analyzed

- `src/main.py` — Main FastAPI application with `/dispatch` endpoint
- `src/sse/broadcaster.py` — SSE broadcaster implementation

---

## 1. How `/dispatch` Uses `get_broadcaster()` and `SSEEvent`

### Broadcaster Initialization

The broadcaster is initialized **once at application startup** in the lifespan context manager:

```python
# src/main.py:117-120
_broadcaster = get_broadcaster()
await _broadcaster.start()
logger.info("SSE broadcaster started")
```

The `/dispatch` endpoint uses the **global `_broadcaster` instance** directly (not calling `get_broadcaster()` again):

```python
# src/main.py:720
if _broadcaster and surface_id:
    # Broadcast event...
```

### SSEEvent Structure

`SSEEvent` is a dataclass defined in `src/sse/broadcaster.py:65-81`:

```python
@dataclass
class SSEEvent:
    """An SSE event to broadcast.

    Attributes:
        event_type: The type of SSE event (e.g., 'result_created', 'topic_updated')
        data: The event payload data
        rendered_html: Optional rendered HTML for canvas injection (e.g., pre-rendered card)
        target_session_id: Optional filter to only send to connections for this session
        target_surface_id: Optional filter to only send to this specific surface
        exclude_surface_id: Optional filter to exclude this surface from receiving the event
    """
    event_type: str
    data: dict
    rendered_html: str | None = None
    target_session_id: str | None = None
    target_surface_id: str | None = None
    exclude_surface_id: str | None = None
```

---

## 2. Event Type: `result_created` Payload Structure

### Creation in `/dispatch` (src/main.py:724-742)

```python
sse_data = {
    "intent_id": intent_id,
    "topic_id": result.get("topic_id"),
    "summary": result.get("summary"),
    "urgency": result.get("urgency"),
}

# Optional component tracking
if result.get("component_id") is not None:
    sse_data["component_id"] = result["component_id"]

# Optional fallback flag (signals client to use fallback rendering)
if result.get("card_fallback") is not None:
    sse_data["card_fallback"] = result["card_fallback"]
```

### SSEEvent Object Creation (src/main.py:737-744)

```python
await _broadcaster.broadcast(
    SSEEvent(
        event_type="result_created",
        target_surface_id=surface_id,
        data=sse_data,
        rendered_html=result.get("rendered_html"),  # Optional pre-rendered HTML
    )
)
```

---

## 3. Surface ID Targeting Mechanism

### Targeting Filters in SSEBroadcaster.broadcast() (src/sse/broadcaster.py:165-189)

```python
async def broadcast(self, event: SSEEvent) -> int:
    """
    Broadcast an event to relevant connections.

    Returns the number of connections the event was sent to.
    """
    sent_count = 0

    for conn in list(self.connections.values()):
        # Filter by target
        if event.target_session_id and conn.session_id != event.target_session_id:
            continue
        if event.target_surface_id and conn.surface_id != event.target_surface_id:
            continue
        if event.exclude_surface_id and conn.surface_id == event.exclude_surface_id:
            continue

        # Queue the event
        try:
            conn.queue.put_nowait(event)
            sent_count += 1
        except asyncio.QueueFull:
            logger.warning(f"Queue full for connection {conn.connection_id}, dropping event")

    return sent_count
```

### Filter Behavior

- **`target_session_id`**: Only sends to connections for this session
- **`target_surface_id`**: Only sends to this specific surface (most selective)
- **`exclude_surface_id`**: Sends to all surfaces EXCEPT this one
- **No filters**: Broadcasts to all active connections

### Canvas Dispatch Contract (src/canvas/index.html)

The canvas sends `surface_id` with every dispatch POST:

```javascript
body: JSON.stringify({ 
    utterance, 
    session_id: sessionId, 
    surface_id: surfaceId 
})
```

---

## 4. Broadcast Timing in Request Flow

### When Broadcast Fires

The broadcast happens **after each intent completes processing** in the parallel execution flow:

```python
# src/main.py:687-766
# Create intent records and process in parallel
intent_tasks = []

for routed_intent in routed_intents:
    # Create intent record...
    intent_tasks.append((routed_intent.intent_id, task))

async def stream_results():
    """Process intents and stream results to SSE."""
    results = []

    for intent_id, task in intent_tasks:
        try:
            result = await task  # Wait for this intent to complete
            results.append(result)

            # Broadcast immediately after completion
            if _broadcaster and surface_id:
                emit_start = time.monotonic()
                # ... prepare SSE data ...
                await _broadcaster.broadcast(...)
                
                # Record SSE emit timing
                await store.record_dispatch_timings(
                    intent_id,
                    sse_emit_ms=int((time.monotonic() - emit_start) * 1000),
                )

# Start parallel processing in background
asyncio.create_task(stream_results())

# Return acknowledgment immediately
return {
    "utterance_id": utterance_id,
    "session_id": session_id,
    "intent_count": len(intent_ids),
    "intent_ids": intent_ids,
    "status": "dispatched",
    "message": f"Dispatched {len(intent_ids)} intents for parallel processing",
}
```

### Flow Summary

1. `/dispatch` receives request with `utterance`, `session_id`, `surface_id`
2. Router creates intents and spawns parallel tasks
3. **Returns acknowledgment immediately** (non-blocking)
4. Background `stream_results()` task:
   - Awaits each intent completion sequentially
   - **Broadcasts `result_created` immediately after each intent completes**
   - Records SSE emit timing for latency monitoring
5. Canvas receives SSE event and fetches updated topics via `GET /api/v1/sessions/{session_id}/topics`

---

## 5. Available Event Types (EventType class)

```python
# src/sse/broadcaster.py:299-357
class EventType:
    """SSE event types."""

    # Connection lifecycle
    CONNECTED = "connected"
    DISCONNECT = "disconnect"
    HEARTBEAT = "heartbeat"

    # Result events
    RESULT_CREATED = "result_created"
    RESULT_UPDATED = "result_updated"

    # Component events (Phase 2)
    COMPONENT_UPDATED = "component_updated"

    # Intent events
    INTENT_PENDING = "intent_pending"
    INTENT_DISPATCHED = "intent_dispatched"
    INTENT_RESOLVED = "intent_resolved"

    # Fetch progress events (per-source progress states)
    FETCH_PROGRESS = "fetch_progress"

    # Synthesis progress events (streaming synthesis)
    SYNTHESIS_PROGRESS = "synthesis_progress"

    # Topic events
    TOPIC_CREATED = "topic_created"
    TOPIC_UPDATED = "topic_updated"
    TOPIC_STALE = "topic_stale"

    # Workload events
    WORKLOAD_SUMMARY = "workload_summary"
    EXCEPTION_RAISED = "exception_raised"

    # Bead events
    BEAD_CLOSED = "bead_closed"
    BEAD_FAILED = "bead_failed"

    # Circuit breaker events
    TASK_STUCK = "task_stuck"
    TASK_FAILED = "task_failed"

    # Approval events (Generated-Bead Safety)
    APPROVAL_REQUIRED = "approval_required"
    APPROVAL_GRANTED = "approval_granted"
    APPROVAL_DENIED = "approval_denied"

    # Degraded-state error events
    ROUTER_UNAVAILABLE = "router_unavailable"
    ALL_SOURCES_FAILED = "all_sources_failed"
    DEGRADED_RAW_DATA = "degraded_raw_data"
    CLARIFICATION_CARD = "clarification_card"
    MALFORMED_RESPONSE = "malformed_response"

    # Unimplemented intent events (honesty guards)
    ACTION_DESIGN_ONLY = "action_design_only"
    REMINDER_UNAVAILABLE = "reminder_unavailable"
```

---

## 6. Helper Broadcast Functions

The broadcaster module provides several helper functions for common broadcast patterns:

### `broadcast_result()` (src/sse/broadcaster.py:359-384)

```python
async def broadcast_result(
    result: dict,
    session_id: str,
    target_surface_id: str | None = None,
    rendered_html: str | None = None,
) -> int:
    """Broadcast a result to relevant surfaces."""
    broadcaster = get_broadcaster()
    event = SSEEvent(
        event_type=EventType.RESULT_CREATED,
        data=result,
        rendered_html=rendered_html,
        target_session_id=session_id,
        target_surface_id=target_surface_id,
    )
    return await broadcaster.broadcast(event)
```

### Other Helper Functions

- `broadcast_intent_update()` — Intent status updates
- `broadcast_workload_summary()` — Workload summaries for reconnection
- `broadcast_fetch_progress()` — Per-source fetch progress (3/5 sources in)
- `broadcast_synthesis_progress()` — Streaming synthesis text chunks

---

## 7. SSE Connection Lifecycle

### Registration (src/main.py:1003-1023, /events endpoint)

```python
# Get or create session
session = await store.get_session(session_id)
if not session:
    session_id = await store.create_session()

# Register or update surface
if not surface_id:
    surface_id = await store.register_surface(session_id, "canvas")

# Create SSE connection
connection = broadcaster.register(
    surface_id=surface_id,
    session_id=session_id,
    surface_type="canvas",
)
```

### Event Streaming (src/sse/broadcaster.py:191-247)

The `event_generator()` yields SSE messages and handles:
- Initial `connected` event with connection info
- Keep-alive ping every 5 seconds (`: ping\n\n`)
- Event queuing per connection
- Cleanup on disconnect

### SSE Format (src/sse/broadcaster.py:249-251)

```python
def _format_sse(self, event_type: str, data: dict) -> str:
    """Format an event as SSE."""
    return f"event: {event_type}\ndata: {json.dumps(data)}\n\n"
```

---

## 8. Key Implementation Patterns

### Pattern 1: Broadcast After Async Work

```python
# Do async work
result = await some_async_operation()

# Broadcast result immediately
if _broadcaster and surface_id:
    await _broadcaster.broadcast(
        SSEEvent(
            event_type="result_created",
            target_surface_id=surface_id,
            data=result_dict,
        )
    )
```

### Pattern 2: Optional Pre-rendered HTML

```python
SSEEvent(
    event_type="result_created",
    data={"intent_id": "...", "topic_id": "..."},
    rendered_html=result.get("rendered_html"),  # Optional canvas injection
)
```

### Pattern 3: Surface-level Targeting

```python
# Broadcast to specific surface
SSEEvent(
    event_type="component_updated",
    target_surface_id=surface_id,  # Single surface
    data={...},
)

# Broadcast to entire session
SSEEvent(
    event_type="workload_summary",
    target_session_id=session_id,  # All surfaces in session
    data={...},
)

# Broadcast to all surfaces
SSEEvent(
    event_type="component_updated",
    # No targeting = all surfaces
    data={...},
)
```

---

## Summary

The `/dispatch` SSE implementation follows this pattern:

1. **Broadcaster**: Global singleton instance started at app startup
2. **Event**: `SSEEvent(event_type, data, rendered_html?, target_filters?)`
3. **Timing**: Broadcast immediately after each async operation completes
4. **Targeting**: Use `target_surface_id` for single-surface delivery
5. **Payload**: Include result identifiers (intent_id, topic_id) + optional rendered HTML
6. **Canvas**: Listens for `result_created`, then fetches topics via REST API

This pattern ensures real-time updates to connected canvases while maintaining clean separation between event delivery and data retrieval.
