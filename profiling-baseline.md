# JSON Parsing Performance Baseline

**Date:** 2026-07-24
**Component:** Intent Router JSON Parsing
**Location:** `src/intent/router.py` line 236, `src/llm/response_parser.py`

## Summary

Current JSON parsing implementation uses an optimized `find()`/`rfind()` approach for fence removal and standard `json.loads()` for parsing. Baseline measurements show **extremely fast parsing** - average 2-4 microseconds per operation.

## Methodology

- **Sampling:** 50 iterations per test case for statistical significance
- **Measurement:** `time.perf_counter()` for high-precision timing
- **Test Cases:**
  1. Simple fenced JSON (single intent)
  2. Simple bare JSON (single intent, no fences)
  3. Complex fenced JSON (multiple intents)

## Baseline Results

### Simple Fenced JSON (Single Intent)

| Metric | Value |
|--------|-------|
| **Average Total Time** | **0.0028 ms (2.8 μs)** |
| Median | 0.0023 ms |
| 95th percentile | 0.0071 ms |
| Max | 0.0143 ms |
| Std Dev | 0.0019 ms |

**Breakdown:**
- Fence removal: 0.0006 ms (20.8%)
- JSON parsing: 0.0022 ms (79.2%)

### Simple Bare JSON (Single Intent, No Fences)

| Metric | Value |
|--------|-------|
| **Average Total Time** | **0.0021 ms (2.1 μs)** |
| Median | 0.0020 ms |
| 95th percentile | 0.0027 ms |
| Max | 0.0060 ms |
| Std Dev | 0.0006 ms |

**Breakdown:**
- Fence removal: 0.0002 ms (9.5%)
- JSON parsing: 0.0019 ms (90.5%)

### Complex Fenced JSON (Multiple Intents)

| Metric | Value |
|--------|-------|
| **Average Total Time** | **0.0036 ms (3.6 μs)** |
| Median | 0.0034 ms |
| 95th percentile | 0.0063 ms |
| Max | 0.0086 ms |
| Std Dev | 0.0010 ms |

**Breakdown:**
- Fence removal: 0.0005 ms (15.0%)
- JSON parsing: 0.0031 ms (85.0%)

## Comparison Table

| Test Case | Total (ms) | Fence (ms) | JSON (ms) | Fence % |
|-----------|------------|------------|-----------|---------|
| Simple bare JSON | 0.0020 | 0.0002 | 0.0018 | 9.5% |
| Simple fenced JSON | 0.0024 | 0.0005 | 0.0019 | 20.8% |
| Complex fenced JSON | 0.0035 | 0.0005 | 0.0030 | 15.0% |

## Identified Bottlenecks

### 1. JSON Parsing (85-90% of time)
- **Impact:** Primary bottleneck - 79-90% of total parse time
- **Cause:** Standard `json.loads()` is already highly optimized
- **Opportunity:** Minimal - CPython's json module is already C-accelerated

### 2. Fence Removal (9-21% of time)
- **Impact:** Secondary bottleneck - varies by response type
- **Cause:** String operations (strip, find, rfind, slice)
- **Opportunity:** Already optimized with `find()`/`rfind()` vs. `split()`/`rsplit()`
- **Current approach:** Position-based single-pass (10-15% faster than split-based)

### 3. Current Implementation Strengths
- **Optimized fence removal:** Uses `find()`/`rfind()` instead of `split()`/`rsplit()`
- **No regex overhead:** Avoids expensive regex patterns
- **Single-pass parsing:** Direct slice extraction without intermediate allocations
- **Early returns:** Empty/whitespace checks avoid unnecessary processing

## Before/After Measurement Strategy

For any optimization work, use the following strategy:

1. **Capture baseline:** Run `profile_json_parsing.py` before changes
2. **Implement optimization:** Modify parsing logic
3. **Rerun profiling:** Execute same test cases with new implementation
4. **Compare results:**
   - Average time improvement (%)
   - 95th percentile improvement
   - Code complexity change

## Key Findings

1. **Parsing is already very fast:** 2-4 μs average is negligible compared to LLM latency (hundreds of ms)
2. **JSON parsing dominates:** 85-90% of time is in `json.loads()`, not fence removal
3. **Fence removal is minor:** Even for fenced responses, fence removal is only 15-21% of total time
4. **Optimization headroom is limited:** Current implementation is already near-optimal for Python
5. **LLM latency dominates:** Total parse time (2-4 μs) is << 1% of typical LLM response time (200-500 ms)

## Recommendations

1. **Accept current performance:** 2-4 μs parsing time is not a bottleneck
2. **Focus elsewhere:** Optimize LLM call latency, not JSON parsing
3. **Profile only if needed:** Re-run profiling only if parsing becomes a measurable issue
4. **Avoid premature optimization:** Current implementation is already optimized

## Testing

To re-run this baseline:

```bash
cd /home/coding/aide-de-camp
.venv/bin/python profile_json_parsing.py
```

## Related Work

- Response parser implementation: `src/llm/response_parser.py`
- Intent router usage: `src/intent/router.py:236`
- Previous optimization work: `notes/adc-3e5gg.md` (fence removal optimization)
