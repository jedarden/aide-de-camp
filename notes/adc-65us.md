# Test Dispatch Endpoint Implementation (adc-65us)

## Summary

Verified and enhanced the test dispatch endpoint at `/api/v1/test/dispatch` that accepts raw utterance text directly, bypassing the Web Speech API.

## What Was Done

### 1. Added Validation
Added Pydantic field validator to ensure utterance text is non-empty:
- Validates against empty strings (`""`)
- Validates against whitespace-only strings (`"   "`)
- Validates against missing utterance field
- Returns 400 error with descriptive message for invalid input

### 2. Endpoint Behavior
The endpoint:
- Accepts JSON body with `{utterance: str, session_id: str}` plus optional fields
- Returns same response format as main `/dispatch` endpoint
- No audio processing or transcription involved
- Proper error responses (400 for validation errors, 404 for invalid paths)

## Testing Results

All tests passed:
- ✓ Empty utterance → 400 error with validation message
- ✓ Missing utterance → 400 error with field required message
- ✓ Whitespace-only utterance → 400 error with validation message
- ✓ Valid utterance → 200 with dispatch response
- ✓ Invalid path → 404 error

## Response Format

Both `/dispatch` and `/api/v1/test/dispatch` return the same core structure:
```json
{
  "utterance_id": "...",
  "session_id": "...",
  "intent_count": 1,
  "intent_ids": ["..."],
  "status": "dispatched",
  "message": "..."
}
```

## Files Modified

- `src/test/dispatch.py`: Added `utterance_must_be_non_empty` field validator to `TestDispatchRequest` model

## Acceptance Criteria Met

- [x] Endpoint exists at /api/v1/test/dispatch
- [x] Accepts and validates utterance text
- [x] Returns valid JSON response structure
- [x] 404/400 errors return proper error responses

## Example Usage

```bash
# Valid request
curl -X POST http://localhost:8000/api/v1/test/dispatch \
  -H "Content-Type: application/json" \
  -d '{"utterance": "how are the pods doing", "session_id": "test-session"}'

# Invalid request (empty utterance)
curl -X POST http://localhost:8000/api/v1/test/dispatch \
  -H "Content-Type: application/json" \
  -d '{"utterance": "", "session_id": "test-session"}'
# Returns: 400 {"detail": [{"type": "value_error", "msg": "utterance must be a non-empty string"}]}
```
