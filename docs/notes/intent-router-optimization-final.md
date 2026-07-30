# Intent Router Optimization - Final Performance Report

**Date:** 2026-07-24
**Task:** adc-3d1fl - Verify latency improvements and add monitoring
**Baseline:** July 23, 2026 (docs/notes/latency-baseline-2026-07.md)

---

## Executive Summary

**Status: ❌ FAILED** - Latency targets are NOT met. Router performance has regressed significantly despite optimization attempts.

### Key Findings

- **Router latency p50: 2,767-3,613ms** (5.5-7.2x over the 500ms budget)
- **End-to-end latency p50: 2.8-3.6s** (near or exceeding the 3s target)
- **Performance regression:** Current p50 is 74-77% worse than July 23 baseline
- **Demo remains BLOCKED** per plan gate requirements

---

## Test Methodology

### Test Shapes
1. **Multi-intent status:** "Has the pbx web caught up, and what's the state of whisper stt?"
2. **Lookup logs:** "Pull up the recent logs for whisper stt"
3. **Brainstorm:** "Brainstorm improvements to the pbx web deployment pipeline"

### Test Execution
- **Runs per shape:** 30 (88 successful total)
- **Test date:** July 24, 2026
- **API endpoint:** http://localhost:8000/dispatch
- **Measurement:** Wall-clock dispatch time from HTTP POST to response

---

## Performance Results

### End-to-End Latency (Current vs Baseline)

| Shape | Current p50 | Baseline p50 | Change | Status |
|-------|-------------|--------------|--------|--------|
| Multi-intent | **3,613ms** | 2,074ms | **+74%** ❌ | 7.2x over budget |
| Lookup | **2,908ms** | 1,640ms | **+77%** ❌ | 5.8x over budget |
| Brainstorm | **2,767ms** | 1,587ms | **+74%** ❌ | 5.5x over budget |

| Shape | Current p95 | Baseline p95 | Change | Status |
|-------|-------------|--------------|--------|--------|
| Multi-intent | **8,130ms** | 4,301ms | **+89%** ❌ | 16x over budget |
| Lookup | **4,145ms** | 3,298ms | **+26%** ❌ | 8.3x over budget |
| Brainstorm | **7,500ms** | 2,527ms | **+197%** ❌ | 15x over budget |

### Stage-by-Stage Breakdown (from Health Monitoring)

Recent latency from last hour (via `/health` endpoint):

| Stage | p50 | p95 | Sample Count | Budget | Status |
|-------|-----|-----|--------------|--------|--------|
| Router | **3,054ms** | 7,467ms | 118 | ~500ms | ❌ 6x over |
| Fetch total | **35ms** | 84ms | 118 | ~1s | ✅ PASS |
| Synthesize total | N/A | N/A | 0 | ~1-2s | ⚠️ No data |

---

## Regression Analysis

### Current Performance vs July 23 Baseline

**ALL shapes show significant degradation:**
- Multi-intent: p50 increased from 2,074ms → 3,613ms (+74%)
- Lookup: p50 increased from 1,640ms → 2,908ms (+77%)
- Brainstorm: p50 increased from 1,587ms → 2,767ms (+74%)

**This is a critical regression** - the optimization attempts have made performance worse rather than better.

### Possible Causes for Regression

1. **ZAI Proxy degradation:** The proxy to apexalgo-iad may be experiencing increased latency
2. **LLM model changes:** If the model was switched from Haiku to Sonnet, this explains the 2x increase
3. **Network issues:** Hetzner infrastructure or Tailscale routing may have degraded
4. **Resource contention:** Server load or database contention may have increased

---

## Acceptance Criteria Status

| Criteria | Target | Actual | Status |
|----------|--------|-------|--------|
| Router p50 latency | < 700ms (40% over 500ms budget) | **2,767-3,613ms** | ❌ FAILED |
| Router p95 latency | < 1,500ms | **4,145-8,130ms** | ❌ FAILED |
| End-to-end p95 latency | < 3s | **4,145-8,130ms** | ❌ FAILED |
| Latency metrics via `/health` | Exposed | ✅ Implemented | ✅ PASS |
| Final performance report | Documented | ✅ This file | ✅ PASS |

---

## Monitoring Implementation

### Enhanced Health Endpoint

**Status:** ✅ **COMPLETED**

The `/health` endpoint now includes recent latency metrics:

```bash
curl http://localhost:8000/health
```

**Response structure:**
```json
{
  "status": "ok",
  "service": "adc-voice",
  "latency": {
    "router_ms": {"p50": 3054, "p95": 7467, "count": 118},
    "fetch_total_ms": {"p50": 35, "p95": 84, "count": 118},
    "synthesize_total_ms": {"p50": null, "p95": null, "count": 0},
    "window_seconds": 3600
  }
}
```

**Features:**
- Last hour rolling window (3600 seconds)
- p50 and p95 percentiles for router, fetch, and synthesize stages
- Sample count for data validity
- Graceful degradation if store unavailable

---

## Budget Compliance

### Plan Gate Status: ❌ **BLOCKED**

From `docs/plan/plan.md`:

> **Gate.** The demo cannot be scheduled until the Measured p50/p95 columns are filled from real runs. If measured p95 blows a stage's budget, either the stage gets fixed or the on-screen promise changes.

**Assessment:**
- ✅ Measured p50/p95 columns are filled
- ❌ **Measured p95 BLOWS budget** for all shapes
- ❌ **Measured p50 BLOWS budget** for all shapes
- ❌ The <3s promise **cannot be made**

### Budget vs Measured Comparison

| Stage | Budget | Measured p50 | Measured p95 | Status |
|-------|--------|--------------|--------------|---------|
| Router | ~500ms | **2,767-3,613ms** ❌ | **4,145-8,130ms** ❌ | FAIL |
| Fetch — first source | ~500ms | ~35ms ✅ | ~84ms ✅ | PASS |
| Fetch — window close | ~1s | ~35ms ✅ | ~84ms ✅ | PASS |
| Synthesize — total | ~1-2s | N/A | N/A | ⚠️ Not measured |
| **End-to-end** | **< 3s** | **2,767-3,613ms** ❌ | **4,145-8,130ms** ❌ | FAIL |

---

## Recommendations

### Immediate Actions Required

1. **Investigate regression root cause**
   - Check ZAI proxy logs for latency degradation
   - Verify LLM model being used (Haiku vs Sonnet)
   - Test with direct ZAI proxy endpoint bypass
   - Check for resource contention on Hetzner server

2. **Demo decision required**
   - Current performance **CANNOT support <3s promise**
   - Either defer demo until fixed, OR
   - Change on-screen promise to reflect 4-5s reality

### Architectural Next Steps

1. **Local LLM deployment** - The ZAI proxy network hop is the bottleneck
2. **Aggressive caching** - Cache router results for repeated utterances
3. **Model optimization** - Verify we're using the fastest model (Haiku)
4. **Infrastructure audit** - Check for network/CPU degradation on Hetzner

---

## Files Modified

### Monitoring Implementation
- `src/main.py` - Enhanced `/health` endpoint with latency metrics

### Test Results
- `/tmp/e2e-latency-test-results.json` - Raw test data (88 successful runs)
- `test_e2e_latency.py` - Test harness for reproducing measurements

---

## Conclusion

The intent router optimization efforts have **FAILED** to meet the latency budget. Performance has regressed significantly (74-77% worse p50) since the July 23 baseline, making the <3s end-to-end target impossible to achieve with current infrastructure.

**The demo remains BLOCKED** per the plan gate until either:
1. Latency is reduced to meet budget (unrealistic with current infrastructure), OR
2. The on-screen promise is revised to reflect actual 4-5s performance

**Primary blocker:** The ZAI proxy network hop to apexalgo-iad adds ~2-3s of latency that cannot be optimized away through prompt engineering or parameter tuning.

---

## Test Artifacts

**Test execution:** July 24, 2026 05:21-05:28 UTC
**Test harness:** `test_e2e_latency.py`
**Raw results:** `/tmp/e2e-latency-test-results.json`
**Baseline comparison:** `docs/notes/latency-baseline-2026-07.md`
**Optimization attempts:** `docs/notes/router-optimization-findings-2026-07.md`

---

**Related beads:**
- adc-2xf52: Baseline analysis
- adc-25sn9: Router optimization attempts
- adc-3d1fl: This verification task
