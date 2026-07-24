# Intent Router Timing Instrumentation Verification

**Task:** adc-2ksq1 - Instrument and profile intent router latency
**Status:** ✅ Complete (commit 7c84727)

## What Was Implemented

### Per-Phase Timing Logs
The intent router (`src/intent/router.py`) now captures detailed timing for each phase:

1. **Cache Check** (`cache_check_ms`) - Time to check LRU cache for existing classification
2. **Prompt Construction** (`prompt_ms`) - Time to build system prompt and user message
3. **Proxy Call** (`proxy_ms`) - Total ZAI proxy round-trip time (network + inference)
4. **Proxy Network** (`timing_network_ms`) - Network RTT extracted from LLM client timing
5. **Proxy Inference** (`calculated_inference_ms`) - Model inference time (proxy_ms - network_ms)
6. **JSON Parse** (`parse_ms`) - Time to parse LLM JSON response via `parse_llm_response()`
7. **Process** (`process_ms`) - Time to convert parsed data into IntentClassification objects
8. **Total** (`total_ms`) - End-to-end classification time

### Structured DEBUG Logging
All timing data is logged at DEBUG level with structured format:
```
router_timing phase=prompt_construction duration_ms=1.23 phase=proxy_call duration_ms=2420.90 ...
```

This format is machine-parseable for analysis tools.

### Persistence
- Router timing breakdown is stored via `store.update_utterance_router_timing()`
- Per-intent dispatch timings stored in `dispatch_timings` table:
  - `router_ms` - Shared across all intents from same utterance
  - `fetch_total_ms`, `fetch_first_source_ms` - Fetch strand timings
  - `synthesize_total_ms` - Synthesize strand timing
  - `escalate_ms` - Escalate strand timing (task-profile only)

## Verification Results

### Server Health Check
```json
{
  "latency": {
    "router_ms": {
      "p50": 2642,
      "p95": 6437,
      "count": 650
    }
  }
}
```

### Test Dispatch Verification
- Sent test utterance: "check pbx-web status"
- Router classified 1 intent in 1442ms
- Timing data persisted to `dispatch_timings` table

### Database Verification
```sql
SELECT intent_id, router_ms, fetch_total_ms FROM dispatch_timings ORDER BY created_at DESC LIMIT 1;
-- 618a4815-4247-4a81-85d5-d5db31e2b09c | 1442 | 77
```

### Existing Latency Analysis
- `docs/notes/intent-router-latency-breakdown.md` shows detailed phase breakdown
- ZAI proxy call (model inference) accounts for 99.98% of router latency
- JSON parsing is negligible (~0.03ms)

## Acceptance Criteria Status

- ✅ Add per-phase timing logs to intent router module
- ✅ Log timing data at DEBUG level with structured format  
- ✅ Verify instrumentation is active by checking logs during a test dispatch

**All criteria met.** Task already complete as of commit 7c84727.
