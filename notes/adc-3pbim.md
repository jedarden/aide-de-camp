# SSE Broadcast Verification - Test Endpoints

## Summary

Verified that test endpoints correctly broadcast SSE events to connected canvas surfaces using the existing broadcaster infrastructure.

## Test Endpoints Verified

### 1. `/api/v1/test/dispatch` (src/test/dispatch.py:458-491)

**Implementation**: `dispatch_test_utterance()` (lines 85-204)

**SSE Broadcast Pattern**:
```python
# Lines 164-191: Background streaming with SSE broadcast
async def stream_results():
    for intent_id, task in intent_tasks:
        result = await task
        if broadcaster and request.surface_id:
            await broadcaster.broadcast(
                SSEEvent(
                    event_type="result_created",
                    target_surface_id=request.surface_id,
                    data={
                        "intent_id": intent_id,
                        "topic_id": result.get("topic_id"),
                        "summary": result.get("summary"),
                        "urgency": result.get("urgency"),
                    }
                )
            )
```

**Verification**:
- ✅ Uses `event_type="result_created"` (line 177)
- ✅ Includes `target_surface_id=request.surface_id` (line 178)
- ✅ Uses existing `get_broadcaster()` (line 165)
- ✅ Uses `SSEEvent` dataclass (line 176)
- ✅ Broadcast timing matches `/dispatch`: processes intents in parallel, broadcasts after each result
- ✅ Non-blocking: uses `asyncio.create_task(stream_results())` (line 191)

### 2. `/api/v1/test/dispatch-synthetic` (src/test/dispatch.py:494-540)

**Implementation**: `generate_synthetic_result()` (lines 207-323)

**SSE Broadcast Pattern**:
```python
# Lines 291-305: Broadcast after result creation
if request.surface_id:
    broadcaster = get_broadcaster()
    await broadcaster.broadcast(
        SSEEvent(
            event_type="result_created",
            target_surface_id=request.surface_id,
            data={
                "intent_id": intent_id_created,
                "topic_id": topic_id_created,
                "summary": synthetic_summary,
                "urgency": urgency,
            }
        )
    )
```

**Verification**:
- ✅ Uses `event_type="result_created"` (line 296)
- ✅ Includes `target_surface_id=request.surface_id` (line 297)
- ✅ Uses existing `get_broadcaster()` (line 293)
- ✅ Uses `SSEEvent` dataclass (line 295)
- ✅ Broadcast timing: after result creation (line 281: `create_result()`, lines 291-305: broadcast)

### 3. `/test` (src/main.py:278-408)

**SSE Broadcast Pattern**:
```python
# Lines 371-393: Broadcast AFTER result creation
if surface_id and _broadcaster:
    await _broadcaster.broadcast(
        SSEEvent(
            event_type=EventType.RESULT_CREATED,
            target_surface_id=surface_id,
            data={
                "intent_id": intent_id,
                "topic_id": topic_id,
                "result_id": result_id,
                "summary": f"Test result for: {utterance[:100]}",
                "urgency": "normal",
            },
        )
    )
```

**Verification**:
- ✅ Uses `EventType.RESULT_CREATED` (line 378)
- ✅ Includes `target_surface_id=surface_id` (line 379)
- ✅ Uses existing `_broadcaster` (line 376)
- ✅ Uses `SSEEvent` dataclass (line 377)
- ✅ Broadcast timing matches `/dispatch`: result → persist → broadcast (line 371 comment confirms)

## Acceptance Criteria Met

All acceptance criteria from adc-3pbim are satisfied:

1. ✅ **SSE event with event_type="result_created" broadcast** - All three endpoints use `"result_created"` event type
2. ✅ **Event includes surface_id targeting if provided** - All endpoints use `target_surface_id` parameter
3. ✅ **Uses existing get_broadcaster() and SSEEvent** - All endpoints use the global broadcaster and SSEEvent dataclass
4. ✅ **Broadcast timing matches /dispatch pattern** - All endpoints broadcast after result creation, following the result → persist → broadcast pattern

## Broadcast Timing Comparison

### `/dispatch` Pattern (src/main.py:711-767)
```python
async def stream_results():
    for intent_id, task in intent_tasks:
        result = await task
        # Broadcast result_created so canvas reloads topics
        await _broadcaster.broadcast(
            SSEEvent(
                event_type="result_created",
                target_surface_id=surface_id,
                data=sse_data,
                rendered_html=result.get("rendered_html"),
            )
        )
```

### Test Pattern (src/test/dispatch.py:167-188)
```python
async def stream_results():
    for intent_id, task in intent_tasks:
        result = await task
        if broadcaster and request.surface_id:
            await broadcaster.broadcast(
                SSEEvent(
                    event_type="result_created",
                    target_surface_id=request.surface_id,
                    data={...},
                )
            )
```

**Conclusion**: Test endpoints follow the exact same broadcast pattern as `/dispatch`.

## Notes

- The `/api/v1/test/dispatch` endpoint includes a `wait_for_results` option for synchronous testing
- The `/api/v1/test/dispatch-synthetic` endpoint creates controlled synthetic results without LLM processing
- Both test endpoints properly integrate with the SSE broadcaster infrastructure
- Broadcast timing is consistent across all endpoints: result creation → persistence → SSE broadcast
