# adc-5xg08: DispatchRequest Model Verification

## Task
Create Pydantic dispatch request model in `src/test/router.py`.

## Status
**ALREADY COMPLETE** - Model verified existing at lines 442-456.

## Verification Results

### Acceptance Criteria Met
- ✅ Model exists in `src/test/router.py`
- ✅ Fields: `utterance` (str), `session_id` (str), `surface_id` (str)
- ✅ All fields are required (using `Field(...)`)
- ✅ Docstring present: `"Request model for dispatch endpoint."`

### Additional Features
- Field descriptions for all fields
- `utterance` field validator ensuring non-empty strings
- Integrated with `/dispatch` endpoint (lines 468-517)

### Implementation Details
```python
class DispatchRequest(BaseModel):
    """Request model for dispatch endpoint."""
    utterance: str = Field(..., description="The utterance text to dispatch")
    session_id: str = Field(..., description="Session ID for the dispatch")
    surface_id: str = Field(..., description="Surface ID for SSE targeting")

    @field_validator('utterance')
    @classmethod
    def utterance_must_be_non_empty(cls, v: str) -> str:
        """Validate that utterance is a non-empty string."""
        stripped = v.strip()
        if not stripped:
            raise ValueError('utterance must be a non-empty string')
        return stripped
```

The foundational data model for the test dispatch endpoint is fully implemented and production-ready.
