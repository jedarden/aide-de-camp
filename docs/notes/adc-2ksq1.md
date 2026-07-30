# Intent Router Latency Instrumentation (adc-2ksq1)

## Overview

Added detailed timing instrumentation to understand exactly where time is spent in the intent router pipeline. All timing logs use structured key-value format at DEBUG level for production-safe profiling.

## Changes Made

### 1. Intent Router (`src/intent/router.py`)

**Added timing phases:**
- `cache_check` - Time to check cache for existing classification
- `prompt_construction` - Time to build system and user prompts
- `proxy_call` - Total time for LLM API call (network + inference)
- `proxy_network` - Network latency to proxy
- `proxy_inference` - Model inference time (proxy_call - proxy_network)
- `json_parse` - Time to parse LLM JSON response
- `process` - Time to process classifications into objects
- `total` - End-to-end classification time

**Log format (DEBUG):**
```
router_timing phase=prompt_construction duration_ms=1.23 phase=proxy_call duration_ms=2500.45 ...
```

**Summary log (INFO):**
```
Classified N intents from utterance (2576ms total)
```

### 2. Fetch Orchestrator (`src/fetch/orchestrator.py`)

**Added timing phases:**
- `setup` - Time to resolve fetch commands and required sources
- `source_complete` - Per-source completion time (logged per source)
- `coverage` - Time to build coverage report
- `total` - End-to-end fetch time

**Log format (DEBUG):**
```
fetch_timing phase=setup duration_ms=2.34 intent_id=abc12345 sources_count=7
fetch_timing phase=source_complete source=kubectl_pods status=success duration_ms=45 ...
fetch_timing phase=coverage duration_ms=0.12 phase=total duration_ms=1234 ...
```

**Summary log (INFO):**
```
Fetch complete for intent abc12345: 5/7 succeeded, 1 timed out, 1 failed (1234ms)
```

### 3. Synthesize Strand (`src/synthesize/strand.py`)

**Added timing phases:**
- `prompt_construction` - Time to load prompts and build messages
- `llm_call` - Time for LLM synthesis call
- `json_parse` - Time to parse synthesis response
- `result_process` - Time to build result objects
- `total` - End-to-end synthesis time

**Log format (DEBUG):**
```
synthesize_timing phase=prompt_construction duration_ms=1.23 intent_id=abc12345
synthesize_timing phase=llm_call duration_ms=850.67 intent_id=abc12345
synthesize_timing phase=json_parse duration_ms=0.45 intent_id=abc12345
synthesize_timing phase=result_process duration_ms=0.23 phase=total duration_ms=852.58 ...
```

**Summary log (INFO):**
```
Synthesis complete for intent abc12345: 3 data fields, urgency=normal (853ms)
```

## Verification

### Health Endpoint
The `/health` endpoint confirms timing data is being collected:
```json
{
  "latency": {
    "router_ms": {"p50": 2642, "p95": 6437, "count": 649},
    "fetch_total_ms": {"p50": 43, "p95": 97, "count": 620}
  }
}
```

### Log Levels
- **DEBUG**: Detailed per-phase timing (structured format)
- **INFO**: Summary timing with human-readable messages

### To Enable DEBUG Logging
Currently production runs at INFO level. To see detailed timing:

1. Edit `src/main.py`: Change `logging.basicConfig(level=logging.DEBUG)`
2. Or set environment variable: `LOG_LEVEL=DEBUG`

## Usage Examples

### View Router Timing
```bash
# Check recent router timing at DEBUG level
tail -f /tmp/adc.log | grep "router_timing"
```

### View Fetch Timing
```bash
# Check fetch orchestration timing
tail -f /tmp/adc.log | grep "fetch_timing"
```

### View Synthesis Timing
```bash
# Check synthesis timing
tail -f /tmp/adc.log | grep "synthesize_timing"
```

### Profile Specific Dispatch
```bash
# Filter by intent_id
tail -f /tmp/adc.log | grep "intent_id=abc12345"
```

## Design Notes

1. **Structured Format**: All timing logs use `phase=X duration_ms=Y` format for easy parsing
2. **Intent IDs**: First 8 characters of intent ID shown (for log brevity)
3. **Consistent Units**: All durations in milliseconds (ms) with 2 decimal places
4. **Non-Breaking**: Logging failures don't break dispatch flow
5. **Performance**: Timing measurements use `time.perf_counter()` for high precision

## Future Work

This instrumentation provides the foundation for latency optimization (parent bead adc-25sn9). Next steps:
1. Collect baseline metrics over 24-48 hours
2. Identify outliers (>p95) for investigation
3. Optimize slow phases identified by timing data
4. Add alerting on latency SLO breaches
