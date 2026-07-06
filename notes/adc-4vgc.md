# Test Dispatch Endpoint Verification - adc-4vgc

## Task
Add test dispatch endpoint to API

## Discovery
The test dispatch endpoint already exists in the codebase at `src/test/dispatch.py` and was implemented in prior commits:
- `6697192 feat: add validation for test dispatch endpoint`
- `f870f39 feat: add test router module`  
- `2e8580f feat: mount test dispatch router at /api/v1 prefix`

## Acceptance Criteria Verification

All acceptance criteria are **MET**:

### 1. POST /api/v1/test/dispatch endpoint exists
✓ **VERIFIED**: Endpoint is accessible at `http://localhost:8000/api/v1/test/dispatch`
- Router mounted in `src/main.py` line 207: `app.include_router(test_router, prefix="/api/v1", tags=["test"])`

### 2. Accepts {utterance, session_id} in request body
✓ **VERIFIED**: Request model `TestDispatchRequest` accepts:
- `utterance: str` (required)
- `session_id: Optional[str]` (auto-generated if not provided)
- `surface_id: Optional[str]` (for SSE targeting)
- `wait_for_results: bool` (for synchronous testing)
- `timeout_seconds: int` (max wait time)

### 3. Bypasses Web Speech API transcription
✓ **VERIFIED**: Endpoint accepts plain text utterance directly, no audio transcription needed

### 4. Calls intent router directly with utterance text
✓ **VERIFIED**: Calls `router.route_utterance()` at line 87 in `dispatch.py`:
```python
routed_intents = await router.route_utterance(
    utterance=request.utterance,
    utterance_id=utterance_id,
    session_id=session_id,
)
```

### 5. Returns response matching existing /dispatch format
✓ **VERIFIED**: Returns `TestDispatchResponse` with:
- `status: str` ("dispatched" | "completed")
- `utterance_id: str`
- `session_id: str`
- `intent_count: int`
- `intent_ids: list[str]`
- `message: str`
- `results: Optional[list[dict]]` (when `wait_for_results=true`)

## Additional Features

The implementation includes **bonus features**:

1. **Pre-canned test utterances**: GET `/api/v1/test/utterances` returns 7 test scenarios
2. **Named dispatch**: POST `/api/v1/test/dispatch/{utterance_name}` for quick testing
3. **Test suite**: POST `/api/v1/test/run_suite` runs all pre-canned utterances
4. **Intent classification**: POST `/api/v1/test/classify` for LLM classification testing

## Test Results

Successfully dispatched test utterance:
```bash
curl -X POST http://localhost:8000/api/v1/test/dispatch \
  -H "Content-Type: application/json" \
  -d '{"utterance": "deploy the latest version of nap-api", "session_id": "test-session-123"}'
```

Response:
```json
{
  "status": "dispatched",
  "utterance_id": "b57ace6a-715a-4159-9b0a-d545d1a37871",
  "session_id": "test-session-123",
  "intent_count": 1,
  "intent_ids": ["..."],
  "message": "Test dispatch initiated for 1 intents"
}
```

## Conclusion

The bead's acceptance criteria are fully satisfied by the existing implementation. No code changes required.
