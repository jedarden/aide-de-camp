# Memory Extraction Wiring Verification (adc-28wqn)

**Date:** 2026-08-06
**Status:** ✅ VERIFIED COMPLETE
**Result:** No bugs found - wiring is correct

## Call Path Trace

### 1. Memory Handler Creation
**File:** `src/main.py:359`
```python
memory_handler = create_memory_handler(session_id=session_id, api_key=api_key)
if memory_handler:
    logger.info(f"Memory extraction enabled for session: {session_id}")
```
✓ Memory handler created in `/voice` endpoint

### 2. Callback Registration
**File:** `src/main.py:372`
```python
voice = VoiceSession(
    websocket=websocket,
    model=DEFAULT_MODEL,
    api_key=api_key,
    session_id=session_id,
    system_message=voice_prompt,
    voice=DEFAULT_VOICE,
    logger=logger,
    on_turn_done=memory_handler.on_turn_done if memory_handler else None,
    on_surface_switch=on_surface_switch,
)
```
✓ Callback passed to VoiceSession constructor

### 3. Callback Storage
**File:** `src/realtime/session.py:66,76`
```python
def __init__(
    self,
    websocket: WebSocket,
    model: str,
    api_key: str,
    session_id: str,
    system_message: str,
    voice: str = "alloy",
    logger: Optional[Logger] = None,
    on_turn_done: Optional[Callable] = None,
    on_surface_switch: Optional[Callable] = None,
):
    # ...
    self.on_turn_done = on_turn_done  # async (user_text, assistant_text) -> None
    self.on_surface_switch = on_surface_switch  # async (surface_type) -> None
```
✓ Callback stored as instance variable

### 4. Event Handler - THE CRITICAL WIRING
**File:** `src/realtime/session.py:339-345`
```python
elif msg_type == "adc.turn_done":
    if self.on_turn_done:
        user_text = data.get("user_text", "")
        assistant_text = data.get("assistant_text", "")
        asyncio.create_task(
            self.on_turn_done(user_text, assistant_text)
        )
    # Update user activity tracking
    self._user_last_spoke = time.time()
```
✓ **on_turn_done IS INVOKED** when `adc.turn_done` event received
✓ Wrapped in `asyncio.create_task()` for non-blocking async execution

### 5. Handler Implementation
**File:** `src/memory/extraction.py:42`
```python
async def on_turn_done(self, user_text: str, assistant_text: str) -> None:
    """
    Callback handler for conversation turn completion.

    Extracts salient facts from the conversation turn and persists them.

    Args:
        user_text: What the user said this turn
        assistant_text: What the assistant responded
    """
    if not self.api_key:
        return

    if not user_text.strip():
        return

    try:
        await self.memory_store.extract_and_save(
            user_text=user_text,
            assistant_text=assistant_text,
            api_key=self.api_key,
        )
        logger.debug(f"Memory extraction completed for session {self.session_id}")
    except Exception as e:
        # Never crash the session over memory extraction
        logger.warning(f"Memory extraction failed: {e}")
```
✓ Handler extracts and persists salient facts via MemoryStore

## Complete Flow

1. **Client → Server:** Browser sends `adc.turn_done` event with `{user_text, assistant_text}`
2. **VoiceSession.run():** Receives event in websocket loop (session.py:339)
3. **Task Creation:** `asyncio.create_task(self.on_turn_done(...))` (session.py:343)
4. **Memory Handler:** `memory_handler.on_turn_done()` executes asynchronously (extraction.py:42)
5. **Persistence:** `memory_store.extract_and_save()` extracts facts and saves to SQLite (extraction.py:59)

## Key Design Decision: Non-blocking Async

The use of `asyncio.create_task()` ensures memory extraction doesn't block the websocket loop. If extraction fails or takes time, the session stays responsive. Errors are caught and logged without crashing the session.

## Verification Result

**Status:** ✅ PASS - All wiring verified and correct
**Files checked:** `src/main.py`, `src/realtime/session.py`, `src/memory/extraction.py`
**Line citations:**
- Memory handler creation: `src/main.py:359`
- Callback registration: `src/main.py:372`
- Callback storage: `src/realtime/session.py:76`
- **Callback invocation: `src/realtime/session.py:339-345`** ← THE KEY WIRING
- Handler implementation: `src/memory/extraction.py:42`
