# ParseLLMError Handling Standardization

## Current State Analysis

### 1. Router Pattern (`src/intent/router.py`)

**Lines 252-309**

The router implements a **corrective retry pattern**:

```python
# Step 1: Parse using centralized parser
try:
    intents_data = parse_llm_response(response)
except ParseLLMError as e:
    # Convert to json.JSONDecodeError for compatibility with existing error handling
    raise json.JSONDecodeError(str(e), doc="", pos=0) from e

# Step 2: Handle JSON errors with corrective retry
except json.JSONDecodeError as e:
    logger.error(f"Failed to parse router response as JSON: {e}")
    
    # Implement one corrective retry on malformed JSON
    if retry_on_malformed and retry_count == 0:
        logger.info("Malformed JSON detected, attempting corrective retry...")
        retry_count += 1
        try:
            return await self.classify_utterance(
                utterance=utterance,
                session_id=session_id,
                retry_on_malformed=False,  # Prevent infinite retry
            )
        except json.JSONDecodeError as retry_e:
            raise RouterMalformedError(
                parse_error=str(e),
                raw_output=raw_response or "",
                retry_count=retry_count,
            ) from retry_e
    
    # No retry or retry failed - raise RouterMalformedError
    raise RouterMalformedError(
        parse_error=str(e),
        raw_output=raw_response or "",
        retry_count=retry_count,
    ) from e
```

**Key characteristics:**
- ✅ Uses centralized `parse_llm_response()`
- ⚠️ Converts `ParseLLMError` to `json.JSONDecodeError` (inconsistent type conversion)
- ✅ Implements corrective retry (one retry attempt)
- ✅ Raises domain-specific `RouterMalformedError`
- ✅ Includes debugging context (raw_output, retry_count)
- ❌ Inconsistent: doesn't preserve ParseLLMError.raw_response

### 2. Synthesize Pattern (`src/synthesize/strand.py`)

**Lines 144-198**

The synthesize strand implements a **fallback result pattern**:

```python
# Direct parsing without centralized parser
raw = strip_markdown_fences(response)
result_data = json.loads(raw)

# Extract fields...

# Error handling
except json.JSONDecodeError as e:
    logger.error(f"Failed to parse synthesize response as JSON: {e}")
    # Fallback: return minimal result
    return SynthesizeResult(
        intent_id=request.intent_id,
        data={"type": "error", "error": "Failed to parse synthesis response"},
        summary="An error occurred while processing the result.",
        urgency=Urgency.NORMAL,
    )
except Exception as e:
    logger.error(f"Synthesis failed for intent {request.intent_id}: {e}")
    raise
```

**Key characteristics:**
- ❌ Bypasses centralized `parse_llm_response()`
- ❌ Uses low-level `strip_markdown_fences()` + `json.loads()`
- ✅ Implements fallback result (graceful degradation)
- ✅ Logs error with context
- ❌ No domain-specific error type
- ❌ Loses ParseLLMError debugging context (raw_response)

## Inconsistencies Identified

| Aspect | Router | Synthesize | Impact |
|--------|--------|------------|--------|
| **Parser function** | `parse_llm_response()` | `strip_markdown_fences()` + `json.loads()` | Synthesize bypasses centralized parser |
| **Exception type** | `ParseLLMError` → `json.JSONDecodeError` → `RouterMalformedError` | `json.JSONDecodeError` only | Inconsistent error types |
| **Raw response preservation** | Stored manually in `raw_response` var | Lost | Debugging harder in synthesize |
| **Recovery strategy** | Corrective retry (1 attempt) | Fallback result | Both correct, but undocumented |
| **Domain error types** | `RouterMalformedError` | None | Router more structured |

## Standardized Pattern

### Decision: Preserve Both Recovery Strategies

Both approaches are correct for their contexts:

1. **Router → Corrective Retry**
   - Reasoning: Router is the **first step** in the pipeline
   - A malformed router response cascades to everything downstream
   - One retry is justified because it's cheap (same prompt, 2048 tokens)
   - If retry fails, degraded-state UX via clarification card

2. **Synthesize → Fallback Result**
   - Reasoning: Synthesize runs **after expensive fetch operations**
   - Fetch data already obtained — should never be discarded
   - Fallback result allows displaying raw data in degraded-state UX
   - No retry needed (would re-run expensive fetch operations)

### Standard Structure

Both should follow this structure:

```python
# 1. PARSE: Use centralized parser
try:
    parsed_data = parse_llm_response(raw_response)
except ParseLLMError as e:
    # 2. CONTEXT: Preserve debugging information
    logger.error(f"Failed to parse LLM response: {e}")
    raw_output = e.raw_response or raw_response  # Prefer error's raw_response
    
    # 3. RECOVERY: Apply appropriate strategy
    # - Router: corrective retry
    # - Synthesize: fallback result
    
    # 4. ESCALATION: Raise domain-specific error or return fallback
```

### Implementation Guidance

#### For Router (retry pattern):

```python
try:
    intents_data = parse_llm_response(response)
except ParseLLMError as e:
    logger.error(f"Failed to parse router response: {e}")
    raw_output = e.raw_response or response  # Preserve for error reporting
    
    if retry_on_malformed and retry_count == 0:
        logger.info("Attempting corrective retry...")
        retry_count += 1
        try:
            return await self.classify_utterance(
                utterance=utterance,
                session_id=session_id,
                retry_on_malformed=False,
            )
        except ParseLLMError as retry_e:
            raise RouterMalformedError(
                parse_error=str(retry_e),
                raw_output=raw_output,
                retry_count=retry_count,
            ) from retry_e
    
    raise RouterMalformedError(
        parse_error=str(e),
        raw_output=raw_output,
        retry_count=retry_count,
    ) from e
```

#### For Synthesize (fallback pattern):

```python
try:
    raw = strip_markdown_fences(response)
    result_data = json.loads(raw)
except json.JSONDecodeError as e:
    logger.error(f"Failed to parse synthesize response as JSON: {e}")
    
    # Fallback: return minimal result with error context
    return SynthesizeResult(
        intent_id=request.intent_id,
        data={
            "type": "error",
            "error": "Failed to parse synthesis response",
            "parse_error": str(e),  # Preserve error details
        },
        summary="An error occurred while processing the result.",
        urgency=Urgency.NORMAL,
    )
```

## Migration Path

### Phase 1: Update Router (High Priority)

1. Remove ParseLLMError → json.JSONDecodeError conversion
2. Use ParseLLMError.raw_response directly
3. Simplify error chain

**Files:** `src/intent/router.py` (lines 252-309)

### Phase 2: Document Synthesize (Low Priority)

The synthesize strand works correctly as-is. Changes are optional:

1. Consider using `parse_llm_response()` for consistency
2. Document why fallback pattern is used (fetch data preservation)
3. Add inline comment explaining recovery strategy

**Files:** `src/synthesize/strand.py` (lines 144-198)

### Phase 3: Update response_parser.py Documentation

Add clear guidance on when to use each recovery strategy.

**Files:** `src/llm/response_parser.py`

## Benefits

1. **Consistency**: Standard structure across all LLM parsing points
2. **Debugging**: Preserved raw_response in all error paths
3. **Documentation**: Clear guidance on recovery strategy selection
4. **Maintainability**: Future LLM integrations follow established pattern
5. **Error Context**: Better error messages for degraded-state UX

## Testing Strategy

Test both recovery strategies:

1. **Router retry**: Mock malformed JSON → verify retry attempt → verify RouterMalformedError
2. **Synthesize fallback**: Mock malformed JSON → verify fallback SynthesizeResult returned
3. **ParseLLMError.raw_response**: Verify preserved in all error paths

## Related Beads

- adc-5mbc6: Original audit noting the need for standardization
- adc-636du: JSON parsing edge case tests
- adc-3e5gg: JSON parsing performance benchmark
