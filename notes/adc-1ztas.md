# Surface ID Targeting Implementation

## Task: adc-1ztas

### Changes Made

Fixed surface_id targeting in SSE broadcasts to properly support both targeted and global broadcasts.

### Problem

Previously, SSE broadcasts were wrapped in conditional checks like:
```python
if surface_id and _broadcaster:
    await _broadcaster.broadcast(...)
```

This meant broadcasts only happened when `surface_id` was provided, violating the acceptance criterion that "Broadcast without surface_id targets all surfaces."

### Solution

Modified three endpoints in `src/main.py`:

1. **POST /api/v1/test/dispatch** (line ~273)
2. **POST /test** (line ~449)
3. **POST /dispatch** (line ~797)

Changed from:
```python
if surface_id and _broadcaster:
    await _broadcaster.broadcast(
        SSEEvent(
            event_type="result_created",
            target_surface_id=surface_id,
            data=...,
        )
    )
```

To:
```python
if _broadcaster:
    event = SSEEvent(
        event_type="result_created",
        data=...,
    )
    # Set target_surface_id only if surface_id is provided
    if surface_id:
        event.target_surface_id = surface_id
    await _broadcaster.broadcast(event)
```

### Behavior

- **When surface_id is provided**: The event targets only that specific surface via `target_surface_id` filtering in `SSEBroadcaster.broadcast()`
- **When surface_id is NOT provided**: The event broadcasts to all connected surfaces (no filtering applied)

### Acceptance Criteria Met

✅ Endpoint surface_id parameter passed to SSEEvent
✅ SSEEvent sets target_surface_id if surface_id provided
✅ Broadcast without surface_id targets all surfaces
✅ Targeting logic follows existing /dispatch pattern

### Testing

Verified that:
- SSEEvent accepts conditional target_surface_id assignment
- Events with target_surface_id set target specific surfaces
- Events without target_surface_id broadcast to all surfaces
- Server imports and initializes correctly with changes
