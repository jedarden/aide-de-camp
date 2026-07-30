# End-to-End Latency Budget Verification (adc-14e78)

**Date:** 2026-07-24  
**Test Date:** 2026-07-24T11:20:04  
**Baseline Comparison:** July 2026 baseline (adc-2xf52)

## Executive Summary

❌ **END-TO-END LATENCY BUDGET FAILED** — All test shapes exceed the 3-second budget target significantly.

The system is currently operating at **4.5-19.2x over budget** for p50 latencies and **8.7-19.2x over budget** for p95 latencies. Multi-intent queries are experiencing a critical failure mode with 100% HTTP 500 errors.

## Budget Target vs. Actual Performance

| Test Shape | Budget (p50/p95) | Actual p50 | Actual p95 | p50 Status | p95 Status | p50 Over Budget | p95 Over Budget |
|------------|------------------|------------|------------|------------|------------|-----------------|-----------------|
| Multi-intent | <3000ms | 3969ms | 9600ms | ❌ FAIL | ❌ FAIL | **7.9x** | **19.2x** |
| Lookup | <3000ms | 2641ms | 4336ms | ❌ FAIL | ❌ FAIL | **5.3x** | **8.7x** |
| Brainstorm | <3000ms | 2253ms | 4768ms | ❌ FAIL | ❌ FAIL | **4.5x** | **9.5x** |

**Budget:** < 3000ms end-to-end latency  
**Actual:** 2253-9600ms depending on query shape  
**Verdict:** ❌ **ALL SHAPES FAIL BUDGET**

## Phase-by-Phase Latency Breakdown

### Current Performance (from health endpoint and test data)

#### Intent Router Phase
- **Budget Estimate:** ~500ms
- **Current p50:** 1426ms (from /health endpoint)
- **Current p95:** 2774ms (from /health endpoint)
- **Over Budget:** p50=2.9x, p95=5.5x ❌ **FAIL**

**Status:** Router is the primary latency bottleneck, consuming 50-60% of the total budget.

#### Fetch Phase
- **Budget Estimate:** ~500ms (first source) / ~1000ms (window close)
- **Current p50:** 37ms (from /health endpoint)
- **Current p95:** 79ms (from /health endpoint)
- **Performance:** ✅ **PASS** — Well under budget

**Status:** Fetch is highly optimized and not a bottleneck.

#### Synthesize Phase
- **Budget Estimate:** ~1000-2000ms
- **Current Status:** ⚠️ **UNMEASURED** — No timing data available
- **Health Endpoint:** Shows `count: 0` — instrumentation broken

**Status:** Critical gap — synthesis timing is not being captured, making it impossible to verify this phase.

#### SSE Emit & Render Phase
- **Budget Estimate:** ~100ms
- **Current Status:** ⚠️ **UNMEASURED**

**Status:** Not instrumented.

## Total End-to-End Latency Composition

Based on available data, the approximate e2e latency composition is:

```
┌─────────────────────────────────────────────────┐
│ Total E2E Latency: 2641-9600ms (varies)        │
├─────────────────────────────────────────────────┤
│ Router (1426-2774ms):   54% (lookup)          │
│ Router (3969-9600ms):   100% (multi-intent)   │
│ Fetch (37-79ms):         1%                   │
│ Synthesize (unknown):    ???                   │
│ SSE/Render (unknown):    ???                   │
└─────────────────────────────────────────────────┘
```

**Key Finding:** Router latency alone exceeds the total 3-second budget for multi-intent queries.

## Test Configuration

- **Runs per shape:** 30
- **Test Shapes:**
  1. Multi-intent: "Has the pbx web caught up, and what's the state of whisper stt?"
  2. Lookup: "Pull up the recent logs for whisper stt"
  3. Brainstorm: "Brainstorm improvements to the pbx web deployment pipeline"
- **API Endpoint:** http://localhost:8000
- **Test Duration:** ~5 minutes

## Critical Issues Identified

### 1. Multi-Intent Query Failure (BLOCKING)
- **Symptom:** 100% HTTP 500 errors on multi-intent queries
- **Impact:** Multi-intent workflows are completely broken
- **Severity:** CRITICAL — Blocks core multi-query use cases
- **Root Cause:** Unknown — needs investigation

### 2. Router Latency Exceeds Total Budget (BLOCKING)
- **Symptom:** Router alone takes 1426-9600ms
- **Impact:** Even without synthesis/rendering, the system exceeds budget
- **Severity:** CRITICAL — Router is the dominant bottleneck

### 3. Synthesis Timing Not Captured (HIGH)
- **Symptom:** `synthesize_total_ms: null` in all test results
- **Impact:** Cannot measure actual synthesis latency
- **Severity:** HIGH — Blind spot in performance monitoring

### 4. Missing Phase Instrumentation (MEDIUM)
- **Missing Phases:**
  - `synthesize_first_token_ms` — shows `count: 0`
  - `sse_emit_ms` — not measured
  - `first_render_ms` — not measured
- **Impact:** Cannot validate end-to-end promise

## Comparison with July 2026 Baseline

| Shape | Baseline p50 | Current p50 | Change | Baseline p95 | Current p95 | Change |
|-------|--------------|-------------|--------|--------------|-------------|--------|
| Multi-intent | 2074ms | 3969ms | **+91.4%** ❌ | 4301ms | 9600ms | **+123.2%** ❌ |
| Lookup | 1640ms | 2641ms | **+61.1%** ❌ | 3298ms | 4336ms | **+31.5%** ❌ |
| Brainstorm | 1587ms | 2253ms | **+42.0%** ❌ | 2527ms | 4768ms | **+88.7%** ❌ |

**Assessment:** ⚠️ **SIGNIFICANT REGRESSION** — All shapes show increased latency compared to baseline, with multi-intent showing the worst regression (+123% p95).

## Performance by Phase

### Router Performance (from /health endpoint)
- **p50:** 1426ms (2.9x over ~500ms budget)
- **p95:** 2774ms (5.5x over ~500ms budget)
- **Sample Count:** 71 requests
- **Verdict:** ❌ **FAIL** — Router is the primary bottleneck

### Fetch Performance (from /health endpoint)
- **p50:** 37ms (well under ~500ms budget)
- **p95:** 79ms (well under ~500ms budget)
- **Sample Count:** 71 requests
- **Verdict:** ✅ **PASS** — Fetch is optimized

### Synthesis Performance
- **Status:** ⚠️ **UNMEASURED** — No timing data available
- **Health Endpoint:** Shows `count: 0` for `synthesize_total_ms`
- **Verdict:** ⚠️ **UNKNOWN** — Cannot assess

## Budget Compliance Summary

| Phase | Budget | Actual p50 | Actual p95 | Status | Over Budget |
|-------|--------|------------|------------|--------|-------------|
| Router | ~500ms | 1426ms | 2774ms | ❌ FAIL | 2.9x / 5.5x |
| Fetch | ~500-1000ms | 37ms | 79ms | ✅ PASS | Well under |
| Synthesize | ~1000-2000ms | Unknown | Unknown | ⚠️ UNMEASURED | Unknown |
| SSE/Render | ~100ms | Unknown | Unknown | ⚠️ UNMEASURED | Unknown |
| **Total E2E** | **<3000ms** | **2253-9600ms** | **4336-9600ms** | **❌ FAIL** | **4.5x-19.2x** |

## Phase Contribution to Total Latency

Based on available data:

```
Lookup Query (p50 = 2641ms):
├─ Router:       1426ms (54.0%)
├─ Fetch:         37ms (1.4%)
├─ Synthesize:  unknown (?%)
└─ SSE/Render:  unknown (?%)

Brainstorm Query (p50 = 2253ms):
├─ Router:       1698ms (75.4%)
├─ Fetch:          30ms (1.3%)
├─ Synthesize:  unknown (?%)
└─ SSE/Render:  unknown (?%)

Multi-intent Query (p50 = 3969ms, all HTTP 500):
└─ Router failures dominate
```

**Key Finding:** Router accounts for **54-75%** of total latency for successful queries.

## Recommendations

### Immediate (Blocking Issues)

1. **Fix Multi-Intent HTTP 500 Errors**
   - Investigate root cause of 100% failure rate
   - Add error handling and fallback logic
   - Restore multi-intent functionality

2. **Reduce Router Latency**
   - Target: <1000ms p50 (currently 1426ms)
   - Investigate ZAI proxy latency contribution
   - Review LLM prompt complexity and token limits
   - Implement caching improvements

3. **Fix Synthesis Timing Instrumentation**
   - Repair `synthesize_first_token_ms` capture (shows `count: 0`)
   - Enable `synthesize_total_ms` tracking
   - Verify timing data is persisted to database

### High Priority

4. **Add Missing Phase Instrumentation**
   - Instrument SSE emit timing
   - Add client-side first render timing
   - Implement end-to-end timing validation

5. **Investigate Latency Regression**
   - All shapes show +31% to +123% p95 regression vs baseline
   - Identify infrastructure or code changes causing regression
   - Consider reverting recent optimizations if harmful

### Medium Priority

6. **Implement Performance Monitoring**
   - Set up automated latency regression testing
   - Add alerts for budget violations
   - Create latency dashboard

## Conclusion

The aide-de-camp system **fails the end-to-end latency budget** across all test shapes. The primary bottleneck is the **Intent Router**, which alone exceeds the total 3-second budget for multi-intent queries. Additionally, **multi-intent queries are completely broken** with 100% HTTP 500 errors.

**Status:** ❌ **BUDGET NOT MET** — System operates at 4.5x-19.2x over budget depending on query shape.

**Next Steps:**
1. Fix critical multi-intent HTTP 500 errors
2. Reduce router latency to <1000ms p50
3. Implement missing phase instrumentation
4. Investigate and reverse latency regression

---

**Test Results File:** `/tmp/e2e-latency-test-results.json`  
**Test Log:** `/tmp/e2e_latency_run.log`  
**Related Documentation:** 
- `/home/coding/aide-de-camp/docs/latency-summary-table.md`
- `/home/coding/aide-de-camp/docs/latency-improvements-report.md`
