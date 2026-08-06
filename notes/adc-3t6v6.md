# Memory Extraction Integration Test (adc-3t6v6)

## Summary

Integration-level test for memory extraction after voice turn completion.

## Implementation

Created comprehensive integration test suite in `tests/test_voice_memory_extraction_integration.py`:

### Test Coverage

1. **`test_voice_turn_creates_memory_file_with_facts`**
   - Validates full voice turn → memory file creation flow
   - Asserts file exists at `data/memory/session_<sha256(session_id)[:16]>.json`
   - Validates JSON structure and fact persistence
   - Checks metadata fields (text, category, confidence, timestamps)

2. **`test_voice_turn_persists_facts_across_handler_instances`**
   - Simulates multiple voice turns across different handler instances
   - Validates facts persist and accumulate correctly
   - Tests real-world scenario of multiple conversation turns

3. **`test_voice_turn_with_no_facts_does_not_create_file`**
   - Validates behavior when no facts are extracted
   - Confirms empty files are NOT created (correct behavior)
   - Validates graceful handling of empty API responses

4. **`test_voice_turn_deduplication_in_memory_file`**
   - Tests duplicate detection across voice turns
   - Validates deduplication logic prevents duplicate facts
   - Ensures only unique facts are persisted

5. **`test_integration_requires_api_key`**
   - Documents API key requirement
   - Validates graceful degradation without key

6. **`test_integration_test_documentation`**
   - Documentation test for requirements and acceptance criteria

## Dependencies

- Requires voice bead adc-4iq infrastructure
- Requires OPENAI_API_KEY for extraction to work
- Unit tests (test_memory_store.py) must pass
- Extraction tests (test_memory_extraction.py) must pass

## Acceptance Criteria Met

✅ Session memory file exists at correct path: `data/memory/session_<sha256(session_id)[:16]>.json`
✅ File is non-empty when facts are extracted
✅ Facts from turn are persisted with correct structure
✅ Facts persist across handler instances
✅ Deduplication works correctly
✅ Test requires API key (documented)

## Test Results

All 6 tests pass:
```
tests/test_voice_memory_extraction_integration.py::test_voice_turn_creates_memory_file_with_facts PASSED [ 16%]
tests/test_voice_memory_extraction_integration.py::test_voice_turn_persists_facts_across_handler_instances PASSED [ 33%]
tests/test_voice_memory_extraction_integration.py::test_voice_turn_with_no_facts_does_not_create_file PASSED [ 50%]
tests/test_voice_memory_extraction_integration.py::test_voice_turn_deduplication_in_memory_file PASSED [ 66%]
tests/test_voice_memory_extraction_integration.py::test_integration_requires_api_key PASSED [ 83%]
tests/test_voice_memory_extraction_integration.py::test_integration_test_documentation PASSED [100%]
```

## Technical Details

### File Naming Convention
- Uses SHA256 hash of session_id (first 16 characters)
- Format: `session_{hash}.json`
- Example: `session_05a6bfae1122b9dc.json`

### JSON Structure
```json
{
  "session_id": "test-session-e6a74ae5",
  "facts": [
    {
      "text": "User's dog is named Rex",
      "category": "personal",
      "confidence": 0.95,
      "created_at": "2026-08-06T11:30:37.781516+00:00",
      "last_referenced": "2026-08-06T11:30:37.781516+00:00"
    }
  ],
  "updated_at": "2026-08-06T11:30:37.781566+00:00"
}
```

### Fact Categories
- `preference`: User likes/dislikes
- `personal`: Personal details
- `correction`: User correcting assistant
- `context`: Other contextual information

## Implementation Notes

- Tests use mocked OpenAI API responses to avoid real API calls
- Temporary directories used for isolation
- Integration validates full flow from handler → extraction → persistence
- Tests are fast (~0.04s total) and hermetic

## Running the Tests

```bash
# Run integration tests only
.venv/bin/python -m pytest tests/test_voice_memory_extraction_integration.py -v

# Run all memory-related tests
.venv/bin/python -m pytest tests/test_memory_*.py -v

# Run with coverage
.venv/bin/python -m pytest tests/test_voice_memory_extraction_integration.py --cov=src.memory
```

## Dependencies on Other Beads

This test (adc-3t6v6) depends on:
- **adc-4iq**: Voice bead infrastructure (only meaningful if it ran with OPENAI_API_KEY)
- **Unit tests**: test_memory_store.py (must pass first)
- **Extraction tests**: test_memory_extraction.py (must pass first)
- **Wiring verification**: Memory extraction wired correctly in main.py

## Conclusion

The integration test successfully validates the full memory extraction flow after voice turn completion, ensuring that:
1. Memory files are created at the correct paths
2. Facts are persisted with proper structure
3. The system handles edge cases gracefully
4. Requirements are met and documented
