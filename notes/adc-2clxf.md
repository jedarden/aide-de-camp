# POST /dispatch Route Implementation

## Task: adc-2clxf
Add basic POST /dispatch route to test router

## Status: ✅ COMPLETE

## Implementation Details

The POST /dispatch route was already implemented in `src/test/router.py` (lines 468-517).

### Models

**DispatchRequest** (lines 442-456):
```python
class DispatchRequest(BaseModel):
    utterance: str = Field(..., description="The utterance text to dispatch")
    session_id: str = Field(..., description="Session ID for the dispatch")
    surface_id: str = Field(..., description="Surface ID for SSE targeting")
    
    @field_validator('utterance')
    @classmethod
    def utterance_must_be_non_empty(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError('utterance must be a non-empty string')
        return stripped
```

**DispatchResponse** (lines 458-466):
```python
class DispatchResponse(BaseModel):
    status: str
    message: str
    utterance: str
    session_id: str
    surface_id: str
    timestamp: int
```

### Route Handler

**POST /dispatch** (lines 468-517):
- Accepts JSON body with utterance, session_id, and surface_id
- Validates input (non-empty utterance)
- Returns 200 OK with structured dummy response
- Includes current timestamp
- Mounted at `/api/v1/dispatch`

### Example Usage

```bash
curl -X POST http://localhost:8000/api/v1/dispatch \
  -H "Content-Type: application/json" \
  -d '{
    "utterance": "test utterance",
    "session_id": "test-session",
    "surface_id": "test-surface"
  }'
```

**Response:**
```json
{
  "status": "received",
  "message": "Dispatch request received successfully",
  "utterance": "test utterance",
  "session_id": "test-session",
  "surface_id": "test-surface",
  "timestamp": 1722638400
}
```

## Verification

Route is registered and functional (verified 2026-08-06):
- ✓ DispatchRequest model exists
- ✓ DispatchResponse model exists
- ✓ /dispatch route registered with router
- ✓ Returns 200 OK with dummy response

## Next Steps

Per the task context: "The actual logic will be added in subsequent beads."

The route structure is complete and ready for integration with the intent router and dispatch pipeline in future work.
