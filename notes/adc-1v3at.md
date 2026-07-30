# ZAI Proxy Network Timing Instrumentation

## Task Completion Status: ALREADY IMPLEMENTED

The ZAI proxy network timing instrumentation was already present in `src/intent/router.py` in the `classify_utterance()` method (lines 302-393).

## Implementation Details

### 1. Total Round-Trip Time Measurement (lines 304-313)
```python
proxy_start = time.perf_counter()
response_data = await client.call_simple(
    system_prompt=system_prompt,
    user_message=user_message,
    model=ModelClass.SONNET.value,
    max_tokens=128,
    temperature=0.0,
    return_timing=True,
)
proxy_ms = (time.perf_counter() - proxy_start) * 1000
```

### 2. Network Timing Breakdown Extraction (lines 316-319)
```python
timing_network_ms = response_data.get("timing_network_ms")
timing_inference_ms = response_data.get("timing_inference_ms")
```

The LLM client internally measures:
- **Network timing**: Pure HTTP request/response latency
- **Inference timing**: Model processing time on the server

### 3. Storage in Local Variable (lines 383-393)
```python
timing_breakdown = {
    "prompt_construction_ms": round(prompt_ms, 2),
    "proxy_call_ms": round(proxy_ms, 2),
    "proxy_network_ms": round(timing_network_ms, 2) if timing_network_ms is not None else None,
    "proxy_inference_ms": round(timing_inference_ms, 2) if timing_inference_ms is not None else None,
    "json_parse_ms": round(parse_ms, 2),
    "process_ms": round(process_ms, 2),
    "total_ms": round(total_ms, 2),
    "intents_count": len(classifications),
}
```

### 4. Detailed Logging (lines 365-378)
```python
logger.info(
    f"router_timing breakdown: "
    f"prompt_construction_ms={prompt_ms:.2f} "
    f"proxy_call_ms={proxy_ms:.2f} "
    f"proxy_network_ms={network_str} "
    f"proxy_inference_ms={inference_str} "
    f"json_parse_ms={parse_ms:.2f} "
    f"process_ms={process_ms:.2f} "
    f"total_ms={total_ms:.2f} "
    f"intents={len(classifications)}"
)
```

## Acceptance Criteria Verification

All acceptance criteria are met:

- ✅ **Timing measurement around the ZAI proxy HTTP call**: Implemented at lines 304-313
- ✅ **Measure total round-trip time**: `proxy_ms` captures complete request/response cycle
- ✅ **Store network timing in local variable**: `timing_breakdown` dict stores all metrics including network and inference breakdown

## Usage

The timing breakdown is:
1. Returned from `classify_utterance()` as the second tuple element
2. Stored in the database via `store.update_utterance_router_timing()` (line 491)
3. Logged for latency profiling and debugging

## Scaffolding Purpose

This timing infrastructure is foundational because:
- It separates network latency from model inference time
- It provides granular visibility into the 1,587-2,074ms router latency
- All subsequent timing optimizations can be measured against this baseline
- The breakdown helps identify if slowness is in network, model, or parsing

## Date Verified

2026-07-24 - Server running, instrumentation active and logging.
