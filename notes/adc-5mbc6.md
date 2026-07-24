# JSON Parsing Implementation Audit

## Overview

This audit documents the current JSON parsing implementation across the aide-de-camp codebase, focusing on LLM response handling and parsing architecture.

## Current Architecture

### Central Parser Module: `src/llm/response_parser.py`

The core JSON parsing utility is centralized in `response_parser.py`, which provides:

1. **`ParseLLMError(Exception)`** - Custom exception class that captures raw response for error reporting
2. **`strip_markdown_fences(raw: str) -> str`** - Strips markdown code fences (`` ```json...``` ```)
3. **`unwrap_zai_response(response_data: dict) -> dict`** - Extracts inner payload from ZAI proxy's "result" wrapper
4. **`extract_text_from_response(payload: dict) -> str`** - Extracts text from Anthropic content array structure
5. **`parse_llm_response(raw_text, ...)`** - Main entry point for parsing LLM text responses
6. **`parse_zai_proxy_response(response_dict, ...)`** - Full pipeline for ZAI proxy responses

**Performance optimizations already in place:**
- Precompiled regex pattern `_FENCE_PATTERN` (compiled once at module load)
- Early returns for empty/whitespace strings
- Single-strip operations (avoid redundant `.strip()` calls)
- Optimized for hot-path usage

## Usage Across Codebase

### 1. **Intent Router** (`src/intent/router.py`)

**Usage:**
- Imports: `ParseLLMError` from `response_parser`
- Does NOT directly use `parse_llm_response()` or `strip_markdown_fences()`
- Uses `client.call_and_parse()` from `escalate/llm.py` which handles parsing

**Flow:**
```
classify_utterance()
  → client.call_and_parse() [ZAI client]
    → call_simple() [gets raw text]
    → strip_markdown_fences()
    → json.loads()
  → Returns dict or raises ParseLLMError
```

**Error Handling:**
- Catches `ParseLLMError` and implements one corrective retry
- If retry fails, raises `RouterMalformedError` with parse error details
- Includes raw response snippet in error context

### 2. **Synthesize Strand** (`src/synthesize/strand.py`)

**Usage:**
- Imports: `ParseLLMError` from `response_parser`
- Uses: `client.call_and_parse()` from `escalate/llm.py`
- Direct JSON usage: `json.dumps()` for pretty-printing in `_build_user_message()`

**Flow:**
```
synthesize()
  → client.call_and_parse() [ZAI client]
    → call_simple() [gets raw text]
    → strip_markdown_fences()
    → json.loads()
  → Returns dict with {data, summary, urgency}
```

**Error Handling:**
- Catches `ParseLLMError` and returns fallback `SynthesizeResult`
- Falls back to minimal error result rather than failing completely
- Logs error and continues with degraded UX

### 3. **Escalate LLM Client** (`src/escalate/llm.py`)

**Usage:**
- Imports: `strip_markdown_fences`, `ParseLLMError` from `response_parser` (lazy import)
- Direct JSON parsing: `json.loads()` in multiple places
- Full ZAI response unwrapping in `call()` and `call_streaming()` methods

**Key Method: `call_and_parse()`**
```python
async def call_and_parse(system_prompt, user_message, ...) -> dict:
    raw_text = await self.call_simple(...)  # Gets raw text content
    text = strip_markdown_fences(raw_text)  # Strip fences
    return json.loads(text)  # Parse JSON
```

**Optimization Note:**
The comment in `call_and_parse()` says "Optimized: strip fences and parse JSON in one pass" but this is misleading - these are still two separate operations (`strip_markdown_fences()` then `json.loads()`), just in a single method call without intermediate text processing.

**Streaming Support:**
`call_streaming()` method handles SSE streaming and parses events incrementally:
```python
async for line in response.aiter_lines():
    if line.startswith("data: "):
        data_str = line[6:]
        if data_str == "[DONE]": break
        data = json.loads(data_str)
        # Handle ZAI proxy wrapping if "result" in data
```

## Data Flow Summary

```
LLM Response (ZAI proxy)
  ↓
{"result": {"content": [{"text": "```json\n{...}\n```"}]}}
  ↓
unwrap_zai_response() → {"content": [{"text": "```json\n{...}\n```"}]}
  ↓
extract_text_from_response() → "```json\n{...}\n```"
  ↓
strip_markdown_fences() → "{...}"
  ↓
json.loads() → {...} (final dict)
```

## Files Using JSON Parsing

### LLM Response Parsing (Hot Path)
1. **`src/llm/response_parser.py`** - Core parser implementation
2. **`src/escalate/llm.py`** - `call_and_parse()` method (primary consumer)
3. **`src/intent/router.py`** - Uses `call_and_parse()` via ZAI client
4. **`src/synthesize/strand.py`** - Uses `call_and_parse()` via ZAI client

### Other JSON Usage (Not LLM Response Parsing)
5. **`src/render/hot_path.py`** - Parses component data
6. **`src/realtime/session.py`** - Parses WebSocket arguments
7. **`src/context/warmer.py`** - Parses topic project_slugs
8. **`src/realtime/dispatch.py`** - Parses result data
9. **`src/fetch/orchestrator.py`** - Parses `br` CLI output
10. **`src/feedback/background_analysis.py`** - Parses signal data
11. **`src/session/store.py`** - Serializes/deserializes context data
12. **`src/memory/store.py`** - Parses memory facts

## What "Optimization" Means in This Context

Based on the codebase analysis, "optimization" refers to:

### 1. **Performance Optimizations (Already Implemented)**
- **Precompiled regex**: Fence-stripping pattern compiled once at module load
- **Early returns**: Skip processing for empty/whitespace inputs
- **Single-strip pattern**: Avoid redundant `.strip()` calls
- **Hot-path optimization**: Code paths used on every LLM call

### 2. **Potential Optimization Opportunities**

#### A. **Consolidate Duplicate Code**
Both `call_and_parse()` in `escalate/llm.py` and `parse_llm_response()` in `response_parser.py` perform similar operations:
- Strip markdown fences
- Parse JSON
- Handle errors with `ParseLLMError`

**Current duplication:**
```python
# In escalate/llm.py (call_and_parse)
text = strip_markdown_fences(raw_text)
return json.loads(text)

# In response_parser.py (parse_llm_response)
text = strip_markdown_fences(raw_text)
return json.loads(text)
```

#### B. **Eliminate Lazy Import**
`call_and_parse()` lazy-imports `strip_markdown_fences` and `ParseLLMError`:
```python
from ..llm.response_parser import strip_markdown_fences, ParseLLMError
```
This suggests module organization issue - could be moved to top-level imports.

#### C. **Consistent Error Handling**
- Router has corrective retry logic
- Synthesize has fallback result logic
- Both handle `ParseLLMError` differently
- Opportunity to standardize error handling patterns

#### D. **Type Safety**
- No type hints on many parsing functions
- Could add strict typing for better IDE support and catch bugs

#### E. **Documentation Inconsistencies**
The comment "Optimized: strip fences and parse JSON in one pass" in `call_and_parse()` is misleading - these are still sequential operations, not a true single-pass parse.

## Follow-up Bead Scope

Based on this audit, potential follow-up work includes:

### High Priority
1. **Consolidate duplicate parsing logic** - Remove duplication between `call_and_parse()` and `parse_llm_response()`
2. **Standardize error handling** - Create consistent retry/fallback patterns across router and synthesize
3. **Fix misleading documentation** - Correct the "one pass" comment in `call_and_parse()`

### Medium Priority
4. **Add type hints** - Improve type safety across parsing utilities
5. **Performance profiling** - Measure actual parsing latency to identify bottlenecks
6. **Consider streaming JSON** - For large responses, streaming parse could help

### Low Priority
7. **Module reorganization** - Move imports to top-level, eliminate lazy imports
8. **Testing coverage** - Add unit tests for edge cases in parsing

## Conclusion

The current JSON parsing implementation is **already optimized for performance** with precompiled patterns and early returns. The main issues are:

1. **Code duplication** between `escalate/llm.py` and `llm/response_parser.py`
2. **Inconsistent error handling** across different code paths
3. **Misleading documentation** about "one pass" parsing

Any optimization work should focus on **consolidation and consistency** rather than raw performance, as the hot paths are already efficient.
