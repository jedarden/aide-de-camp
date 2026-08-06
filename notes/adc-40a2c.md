# Store-Level Assertions for E2E Testing (adc-40a2c)

## Summary
Added store-level assertions to verify backend state after E2E test completion.

## Implementation
Created `test_e2e_assertions.py` that verifies three key assertions:

1. **SSE Event Payload Structure**
   - Checks `intent_id` and `topic_id` are present and non-empty
   - Verifies `summary` field exists and is non-empty
   - Note: The 'data' field in SSE events contains rendered HTML, not structured data

2. **Intent Processing Status**
   - Checks intent thread ID in `dispatch_timings` table
   - The intent_id in SSE events is the intent thread ID (`routed_intent.intent_id`), not `intents.id`
   - Result existence proves successful resolution

3. **Result Row Existence**
   - Confirms result row exists with matching `intent_id` and `topic_id`
   - Validates `summary` and `data` fields in database
   - Verifies data is valid JSON

## Architecture Discovery
Discovered important architectural detail:
- SSE events carry intent **thread ID** (`routed_intent.intent_id`)
- Database `intents` table uses different `intents.id`
- `dispatch_timings` and `results` tables use intent thread ID
- Result existence is proof of successful intent resolution

## Testing
All assertions pass in E2E test:
```bash
.venv/bin/python test_e2e.py "what is the status of pbx-web"
✓ ALL STORE-LEVEL ASSERTIONS PASSED
✓ E2E TEST PASSED
```

## Files Changed
- `test_e2e_assertions.py` (new)
- Integrated with existing `test_e2e.py`

## Commit
feat(adc-40a2c): add store-level assertions for E2E testing
- Verify SSE event payload structure
- Check intent thread in dispatch_timings table  
- Confirm result row exists with valid data
