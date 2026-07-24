# Intent Router Latency Instrumentation - Implementation Summary

**Bead:** adc-5dnbe  
**Status:** ✅ COMPLETE  
**Implementation Date:** 2026-07-24  
**Related Commits:** ed5c043, cbee1f1, f0ca92f

## Overview

The intent router latency instrumentation has been successfully implemented across all investigation areas identified in the task. The implementation provides detailed visibility into WHERE the 1,587-2,074ms latency is spent during intent classification.

## Acceptance Criteria Verification

All acceptance criteria have been met:

### ✅ 1. ZAI Proxy Call Timing
- **Location:** `src/intent/router.py:303-314`
- **Implementation:** 
  ```python
  proxy_start = time.perf_counter()
  response_data = await client.call_simple(
      system_prompt=system_prompt,
      user_message=user_message,
      model=ModelClass.SONNET.value,
      max_tokens=128,
      temperature=0.0,
      return_timing=True,  # Requests timing breakdown from LLM client
  )
  proxy_ms = (time.perf_counter() - proxy_start) * 1000
  ```
- **Measures:** Total round-trip time (network + inference)

### ✅ 2. Model Inference Time (proxy response time - network time)
- **Location:** `src/intent/router.py:316-329`
- **Implementation:**
  ```python
  timing_network_ms = response_data.get("timing_network_ms")
  timing_inference_ms = response_data.get("timing_inference_ms")
  calculated_inference_ms = proxy_ms - timing_network_ms
  ```
- **Measures:** Pure model inference time by subtracting network RTT from total proxy time

### ✅ 3. Prompt Construction/Template Timing
- **Location:** `src/intent/router.py:290-301`
- **Implementation:**
  ```python
  prompt_start = time.perf_counter()
  user_message = f"Classify this utterance:\n\n{utterance}"
  system_prompt = self._build_system_prompt()
  prompt_ms = (time.perf_counter() - prompt_start) * 1000
  ```
- **Measures:** Time to build system prompt and user message template

### ✅ 4. JSON Parsing/Structure Extraction Timing
- **Location:** `src/intent/router.py:331-342`
- **Implementation:**
  ```python
  parse_start = time.perf_counter()
  intents_data = parse_llm_response(response, strip_fences=True, expect_json=True)
  parse_ms = (time.perf_counter() - parse_start) * 1000
  ```
- **Measures:** Time to parse LLM response and extract structured JSON

### ✅ 5. Per-Component Logging on Each classify() Call
- **Location:** `src/intent/router.py:371-385`
- **Implementation:**
  ```python
  logger.info(
      f"router_timing breakdown: "
      f"prompt_construction_ms={prompt_ms:.2f} "
      f"proxy_call_ms={proxy_ms:.2f} "
      f"proxy_network_ms={network_str} "
      f"proxy_inference_ms={calculated_inference_str} "
      f"json_parse_ms={parse_ms:.2f} "
      f"process_ms={process_ms:.2f} "
      f"total_ms={total_ms:.2f} "
      f"intents={len(classifications)}"
  )
  ```
- **Logs:** All timing components for every classification

### ✅ 6. Storage in Session Utterance Records
- **Location:** `src/intent/router.py:498` and `src/session/store.py:902-926`
- **Implementation:**
  ```python
  timing_breakdown = {
      "prompt_construction_ms": round(prompt_ms, 2),
      "proxy_call_ms": round(proxy_ms, 2),
      "proxy_network_ms": round(timing_network_ms, 2) if timing_network_ms is not None else None,
      "proxy_inference_ms": round(calculated_inference_ms, 2) if calculated_inference_ms is not None else None,
      "json_parse_ms": round(parse_ms, 2),
      "process_ms": round(process_ms, 2),
      "total_ms": round(total_ms, 2),
      "intents_count": len(classifications),
  }
  await store.update_utterance_router_timing(utterance_id, timing_breakdown)
  ```
- **Schema:** `utterances.router_timing_breakdown` (TEXT JSON field)

## Implementation Architecture

The timing instrumentation is built into the `classify_utterance()` method with the following flow:

1. **Cache Check** (lines 261-275): Returns empty timing breakdown for cached results
2. **Prompt Construction** (lines 290-301): Times system prompt and user message building
3. **Proxy Call** (lines 303-314): Times total ZAI proxy round-trip with `return_timing=True`
4. **Network vs Inference Separation** (lines 316-329): Extracts network latency and calculates pure inference time
5. **JSON Parsing** (lines 331-342): Times response parsing and structure extraction
6. **Classification Processing** (lines 344-367): Times intent object creation
7. **Total Calculation** (line 369): Computes overall latency
8. **Logging** (lines 371-385): Emits detailed breakdown to logs
9. **Storage** (lines 389-405, 498): Persists breakdown to database

## Key Files

- **`src/intent/router.py`**: Main timing instrumentation implementation (lines 235-505)
- **`src/session/store.py`**: Database schema and storage method (`update_utterance_router_timing`)
- **`src/escalate/llm.py`**: ZAI client with timing support (`return_timing=True` parameter)
- **`src/llm/response_parser.py`**: Optimized JSON parsing (7-179x faster than regex)

## Database Schema

```sql
CREATE TABLE utterances (
    id          TEXT PRIMARY KEY,
    session_id  TEXT NOT NULL,
    raw_text    TEXT NOT NULL,
    created_at  INTEGER NOT NULL,
    router_timing_breakdown TEXT,  -- JSON: detailed timing breakdown
    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
);
```

## Usage Example

To retrieve timing breakdown data:

```python
store = await get_store()
utterance = await store.get_utterance(utterance_id)
timing = json.loads(utterance["router_timing_breakdown"])

# Access individual components
prompt_time = timing["prompt_construction_ms"]
proxy_time = timing["proxy_call_ms"]
network_time = timing["proxy_network_ms"]
inference_time = timing["proxy_inference_ms"]
parse_time = timing["json_parse_ms"]
process_time = timing["process_ms"]
total_time = timing["total_ms"]
```

## Performance Insights

The instrumentation enables precise identification of latency bottlenecks:

- **Network latency**: `proxy_network_ms` - Time to first byte from ZAI proxy
- **Model inference**: `proxy_inference_ms` - Pure LLM processing time
- **Prompt overhead**: `prompt_construction_ms` - Client-side template rendering
- **Parse overhead**: `json_parse_ms` - Response parsing time
- **Process overhead**: `process_ms` - Intent object creation time

This data directly informs optimization priorities for subsequent beads.

## Related Beads

- adc-25sn9: Intent router optimization (caching, timeout tuning, max_tokens reduction)
- adc-3d1fl: Latency monitoring and performance reporting
- adc-1v3at: ZAI proxy network timing verification

## Conclusion

The intent router latency instrumentation is fully implemented and operational. All six acceptance criteria are met, with comprehensive timing breakdown collection, logging, and storage. The implementation is production-ready and provides the data needed to identify optimization targets.
