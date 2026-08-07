# /dispatch Validation - curl Command Reference

This document contains example curl commands for testing the `/dispatch` endpoint validation.

## Endpoint
```
POST http://localhost:8000/dispatch
Content-Type: application/json
```

## Required Fields
- `utterance`: Non-empty string (whitespace is stripped)
- `session_id`: Non-empty string (whitespace is stripped)
- `surface_id`: Non-empty string (whitespace is stripped)

## Optional Fields
- `utterance_id`: Custom utterance ID (auto-generated if not provided)

## Test Cases

### 1. Valid Request (Returns 200)
```bash
curl -s -X POST "http://localhost:8000/dispatch" \
  -H "Content-Type: application/json" \
  -d '{
    "utterance": "Test validation",
    "session_id": "test-session-123",
    "surface_id": "test-surface-456"
  }' | jq .
```

**Expected Response:**
```json
{
  "utterance_id": "<uuid>",
  "session_id": "test-session-123",
  "intent_count": 1,
  "intent_ids": ["<uuid>"],
  "status": "dispatched",
  "message": "Dispatched 1 intents for parallel processing"
}
```

### 2. Missing Required Field - utterance (Returns 400)
```bash
curl -s -X POST "http://localhost:8000/dispatch" \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "test-session-123",
    "surface_id": "test-surface-456"
  }' | jq .
```

**Expected Response:**
```json
{
  "error": "Validation failed",
  "detail": "Request contains invalid or missing fields",
  "errors": [
    {
      "field": "body -> utterance",
      "message": "Field required",
      "type": "missing"
    }
  ],
  "status": 400
}
```

### 3. Missing Required Field - session_id (Returns 400)
```bash
curl -s -X POST "http://localhost:8000/dispatch" \
  -H "Content-Type: application/json" \
  -d '{
    "utterance": "Test validation",
    "surface_id": "test-surface-456"
  }' | jq .
```

### 4. Missing Required Field - surface_id (Returns 400)
```bash
curl -s -X POST "http://localhost:8000/dispatch" \
  -H "Content-Type: application/json" \
  -d '{
    "utterance": "Test validation",
    "session_id": "test-session-123"
  }' | jq .
```

### 5. Empty String - utterance (Returns 400)
```bash
curl -s -X POST "http://localhost:8000/dispatch" \
  -H "Content-Type: application/json" \
  -d '{
    "utterance": "",
    "session_id": "test-session-123",
    "surface_id": "test-surface-456"
  }' | jq .
```

**Expected Response:**
```json
{
  "error": "Validation failed",
  "detail": "Request contains invalid or missing fields",
  "errors": [
    {
      "field": "body -> utterance",
      "message": "String should have at least 1 character",
      "type": "string_too_short"
    }
  ],
  "status": 400
}
```

### 6. Empty String - session_id (Returns 400)
```bash
curl -s -X POST "http://localhost:8000/dispatch" \
  -H "Content-Type: application/json" \
  -d '{
    "utterance": "Test validation",
    "session_id": "",
    "surface_id": "test-surface-456"
  }' | jq .
```

### 7. Empty String - surface_id (Returns 400)
```bash
curl -s -X POST "http://localhost:8000/dispatch" \
  -H "Content-Type: application/json" \
  -d '{
    "utterance": "Test validation",
    "session_id": "test-session-123",
    "surface_id": ""
  }' | jq .
```

### 8. Whitespace-Only String - utterance (Returns 400)
```bash
curl -s -X POST "http://localhost:8000/dispatch" \
  -H "Content-Type: application/json" \
  -d '{
    "utterance": "   ",
    "session_id": "test-session-123",
    "surface_id": "test-surface-456"
  }' | jq .
```

**Expected Response:**
```json
{
  "error": "Validation failed",
  "detail": "Request contains invalid or missing fields",
  "errors": [
    {
      "field": "body -> utterance",
      "message": "Value error, utterance must be a non-empty string",
      "type": "value_error"
    }
  ],
  "status": 400
}
```

### 9. Valid Request with Custom utterance_id (Returns 200 or 500)
```bash
curl -s -X POST "http://localhost:8000/dispatch" \
  -H "Content-Type: application/json" \
  -d '{
    "utterance": "Test with utterance_id",
    "session_id": "test-session-123",
    "surface_id": "test-surface-456",
    "utterance_id": "custom-utterance-789"
  }' | jq .
```

**Note:** If the custom `utterance_id` already exists in the database, this will return a 500 error due to UNIQUE constraint violation. Use a unique ID each time.

### 10. Malformed JSON (Returns 400)
```bash
curl -s -X POST "http://localhost:8000/dispatch" \
  -H "Content-Type: application/json" \
  -d '{
    "utterance": "Test validation",
    "session_id": "test-session-123",
  ' | jq .
```

**Expected Response:**
```json
{
  "error": "Validation failed",
  "detail": "Request contains invalid or missing fields",
  "errors": [
    {
      "field": "body -> <position>",
      "message": "JSON decode error",
      "type": "json_invalid"
    }
  ],
  "status": 400
}
```

## Validation Error Response Format

All validation errors follow this structure:
```json
{
  "error": "Validation failed",
  "detail": "Request contains invalid or missing fields",
  "errors": [
    {
      "field": "<field_path>",
      "message": "<error_message>",
      "type": "<error_type>"
    }
  ],
  "status": 400
}
```

## Error Types

- `missing`: Required field not provided
- `string_too_short`: Empty string provided
- `value_error`: Custom validator failed (e.g., whitespace-only string)
- `json_invalid`: Malformed JSON syntax

## Running All Tests

A comprehensive test script is available at `/tmp/test_dispatch.sh` (created during validation testing). Run with:
```bash
/tmp/test_dispatch.sh
```

## Findings from Manual Testing (2026-08-07)

✅ All validation tests passed:
- Missing required fields return 400 with clear error messages
- Empty strings return 400 with appropriate error types
- Whitespace-only strings are stripped and return 400
- Malformed JSON returns 400 with JSON decode error
- Valid requests return 200 with intent_ids

⚠️  Issue discovered:
- Custom `utterance_id` validation passes correctly, but database insertion fails with UNIQUE constraint violation if the ID already exists. This is a data integrity issue, not a validation issue.

## Validation Implementation

The validation is implemented using Pydantic models in `/home/coding/aide-de-camp/src/api/models.py`:
- `DispatchRequest` model defines required fields and validators
- Field validators strip whitespace and check for non-empty strings
- FastAPI exception handler in `/home/coding/aide-de-camp/src/main.py` returns structured 400 responses
