# Test Endpoint Intent Classification Verification

## Task: Wire test endpoint to existing intent router (adc-26ae)

### Implementation Status: ✅ COMPLETE

The `/api/v1/test/classify` endpoint in `src/test/router.py` is properly wired to the existing intent classification logic in `src/intent/router.py`.

### How It Works

1. **Test endpoint** (`src/test/router.py`, line 36): `/api/v1/test/classify`
   - Accepts: `{utterance, session_id}`
   - Calls `router.classify_utterance()` from intent router
   - Returns: Classified intents with full metadata

2. **Intent Router** (`src/intent/router.py`, line 166): `classify_utterance()`
   - Uses ZAI LLM with GLM-4.7 model
   - Segments utterance into distinct intent threads
   - Classifies each thread by intent type
   - Returns: List of `IntentClassification` objects

3. **Intent Types Supported**:
   - `status`: Query current state (pods, pipelines, deployments)
   - `action`: Execute commands (deploy, restart, create)
   - `brainstorm`: Explore options, design, architecture
   - `lookup`: Find specific information (logs, configs, docs)
   - `reminder`: Set or query reminders
   - `self-modification`: Instructions to improve the interface
   - `monitoring-config`: Configure ambient monitoring rules
   - `task-profile`: Durable async work items (escalates to NEEDLE beads)
   - `clarification`: Low-confidence routing requiring user input

### Test Results

**Test 1 - Status Query**:
```bash
curl -X POST http://localhost:8000/api/v1/test/classify \
  -H "Content-Type: application/json" \
  -d '{"utterance": "how are the pods running in aide-de-camp", "session_id": "test-session-123"}'
```
Result:
- intent_type: `status`
- confidence: `0.95`
- project_slug: `aide-de-camp`
- urgency: `normal`

**Test 2 - Task Profile Query**:
```bash
curl -X POST http://localhost:8000/api/v1/test/classify \
  -H "Content-Type: application/json" \
  -d '{"utterance": "create a new feature for the authentication system", "session_id": "test-session-456"}'
```
Result:
- intent_type: `task-profile`
- confidence: `0.85`
- project_slug: `null`
- urgency: `normal`

### Acceptance Criteria Met

- [x] Test endpoint calls `classify_utterance()` from intent router
- [x] Returns intent type (valid types: status, action, brainstorm, lookup, reminder, self-modification, monitoring-config, task-profile, clarification)
- [x] Returns confidence score (0.0-1.0)
- [x] Intent classification matches main dispatch for same input

### Key Points

1. **Same LLM Classification**: The test endpoint uses the exact same `classify_utterance()` method as the main `/dispatch` endpoint
2. **No Changes to Main Logic**: The main `/dispatch` endpoint remains unchanged
3. **Full Metadata**: Returns intent_type, confidence, reasoning, urgency, project_slug, and utterance_fragment
4. **Properly Integrated**: Router is included in main app at `/api/v1` prefix (see `src/main.py` line 207)

### Conclusion

The test endpoint is fully functional and meets all acceptance criteria. It provides a lightweight way to test intent classification without performing the full routing and processing pipeline.
