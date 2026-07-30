# Latency Baseline — July 2026 (Final Verification)

**Baseline Date:** 2026-07-24  
**Server Version:** 0.22.0  
**Analysis Bead:** adc-1jrkq  
**Optimization Bead:** adc-1kp7n  
**Verification Type:** Final budget compliance check

---

## Executive Summary

**❌ DEMO GATE REMAINS BLOCKED** — Final verification confirms the system does **NOT** meet latency budget targets. Despite optimization work in adc-1kp7n, router latency remains 5.3× over the p50 budget (500ms) and 4.3× over the p95 budget (1,500ms).

**Critical Finding:** The plan.md gate status claiming "Demo unblocked" is **inconsistent with measured data**. The system continues to operate well outside acceptable latency ranges for demo purposes.

---

## Current Performance vs. Budget

### Router Latency (Primary Bottleneck)

| Metric | Budget | Measured | Status | Over Budget |
|--------|--------|----------|--------|-------------|
| p50 | 500ms | **2,642ms** | ❌ FAIL | 5.3× |
| p95 | 1,500ms | **6,437ms** | ❌ FAIL | 4.3× |

**Data Source:** Live server `/api/v1/timings/percentiles` endpoint (649 samples)

---

## Stage-by-Stage Analysis

### ✅ Fetch Stages — EXCELLENT

| Stage | Budget | Measured p50 | Measured p95 | Status |
|-------|--------|--------------|--------------|---------|
| Fetch — first source | ~500ms | **45ms** ✅ | **97ms** ✅ | PASS (10× headroom) |
| Fetch — window close | ~1s | **45ms** ✅ | **97ms** ✅ | PASS (20× headroom) |

**Analysis:** Fetch performance is excellent and comfortably meets budget with significant headroom.

---

### ❌ Intent Router — FAILS BUDGET

| Metric | Budget | Measured | Status | Analysis |
|--------|--------|----------|--------|----------|
| p50 | ~500ms | **2,651ms** | ❌ FAIL | 5.3× over budget |
| p95 | ~1,500ms | **6,441ms** | ❌ FAIL | 4.3× over budget |

**Root Cause:** ZAI proxy latency dominates router timing. Analysis shows:
- Proxy inference time: 1,449-1,875ms per call
- Network overhead: ~116ms per call
- Total router time dominated by external LLM inference

**Optimization Impact:** The adc-1kp7n optimizations (prompt simplification, max_tokens reduction, caching) did not achieve the target reduction.

---

### ❌ End-to-End — FAILS BUDGET

**Target:** < 3s from utterance to first partial card  
**Measured:** Router alone (2,651ms) + fetch (45ms) + synthesis (~3,000-5,000ms) = **5,700-7,700ms**

The end-to-end latency is **2-2.5×** over the 3s budget target.

---

## Cached Performance Analysis

**Positive Finding:** Aggressive intent caching delivers excellent cached performance:
- Cached responses: 7-50ms (p50: ~11-44ms)
- Cache hit rate: 100% on repeated utterances within 15min TTL

However, cached performance does not satisfy the budget requirements. The budget applies to **uncached** latency — the first request for a given utterance shape.

---

## Budget Compliance Summary

| Stage | Budget (ESTIMATE) | Measured p50 | Measured p95 | Status |
|-------|-------------------|--------------|--------------|---------|
| Intent Router | ~500ms | **2,651ms** ❌ | **6,441ms** ❌ | FAIL (5.3× over) |
| Fetch — first source | ~500ms | **45ms** ✅ | **97ms** ✅ | PASS |
| Fetch — window close | ~1s | **45ms** ✅ | **97ms** ✅ | PASS |
| Synthesize — total | ~1-2s | **~3,000-5,000ms** ❌ | **~4,700-7,900ms** ❌ | FAIL |
| **End-to-end** | **< 3s** | **~5,700-7,700ms** ❌ | **~8,800-10,400ms** ❌ | FAIL |

---

## Comparison Against adc-2xf52 Baseline

### Router Latency Changes

| Metric | adc-2xf52 Baseline | Current (Jul 24) | Change |
|--------|-------------------|------------------|---------|
| p50 | 1,587-2,074ms | **2,651ms** | +28-67% worse |
| p95 | 2,527-4,301ms | **6,441ms** | +50-155% worse |

**Analysis:** Router latency has **degraded** compared to the baseline. The optimizations either had no effect or made performance worse.

---

## Demo Gate Status

**Gate Status:** ❌ **DEMO REMAINS BLOCKED**

From the plan.md gate:
> "The demo cannot be scheduled until the Measured p50/p95 columns are filled from real runs. If measured p95 blows a stage's budget, either the stage gets fixed or the on-screen promise changes."

**Assessment:**
- ✅ Measured p50/p95 columns are filled
- ❌ Measured p50 **blows budget** (2,651ms vs 500ms target)
- ❌ Measured p95 **blows budget** (6,441ms vs 1,500ms target)
- ❌ End-to-end latency exceeds 3s promise by 2-2.5×

**Conclusion:** The gate criteria are **NOT met**. The demo cannot proceed until either:
1. Router latency is reduced to meet the 500ms p50 / 1,500ms p95 budgets, OR
2. The on-screen promise is changed from "<3s" to reflect actual performance

---

## Recommended Actions

### Immediate (Demo-Blocking)

1. **Correct Plan Documentation:** Update plan.md gate status to reflect actual measured performance
2. **Address Root Cause:** ZAI proxy/LLM inference is the dominant bottleneck (1,449-1,875ms per call)
3. **Consider Alternatives:**
   - Switch to faster LLM model
   - Implement local inference
   - Change LLM provider
   - Architectural changes to reduce LLM dependency

### Performance Optimization

1. **Profile ZAI Proxy:** Investigate why inference time is consistently 1.4-1.9s
2. **Evaluate Model Options:** Test if different model classes (faster inference) meet accuracy requirements
3. **Reduce LLM Calls:** Consider if router functionality can be achieved with deterministic code + caching

---

## Data Sources

**Live Performance:** `curl http://localhost:8000/api/v1/timings/percentiles`  
**Baseline Comparison:** `docs/notes/latency-baseline-2026-07.md` (adc-2xf52 analysis)  
**Optimization Details:** `docs/latency-improvements-report.md` (adc-emkv3)

**Sample Count:** 611 router timing measurements  
**Test Environment:** Hetzner EX44, uvicorn src.main:app, ZAI proxy connectivity confirmed

---

## Conclusion

The latency optimization work (adc-1kp7n) did not achieve the budget targets. The system continues to operate well outside acceptable latency ranges for demo purposes.

**Status:** ❌ **BUDGET COMPLIANCE FAILED** — Demo gate remains blocked per plan.md criteria.

The previous plan.md update claiming "Demo unblocked" appears to be based on incomplete analysis or incorrect data interpretation. The measured performance clearly shows the system does not meet the latency budget requirements.

---

## FINAL VERIFICATION STATUS — END-TO-END TEST RESULTS

**Verification Date:** 2026-07-24  
**Bead:** adc-3fqf1  
**Verification Type:** End-to-end latency budget compliance verification  

### ❌ VERIFICATION COMPLETE — FAIL

All acceptance criteria for latency baseline verification have been tested:

- [x] Full end-to-end latency baseline measurement completed (90 runs across 3 shapes)
- [x] Router p50/p95 compliance status: **❌ FAIL** (4.5-7.9× over 500ms budget)
- [x] Router p95 compliance status: **❌ FAIL** (7.7-11.3× over 1,500ms budget)
- [x] End-to-end p95 compliance status: **❌ FAIL** (1.9-2.3× over 3s budget)
- [x] Remaining gaps documented (ZAI proxy latency, LLM inference time)
- [x] Next steps documented (model changes, architectural alternatives)

---

## Final End-to-End Test Results

**Test Methodology:** 30 runs per shape × 3 shapes = 90 total dispatch measurements
**Test Date:** 2026-07-24
**Server Version:** 0.22.0

### Performance by Intent Shape

| Shape | p50 (ms) | p95 (ms) | p50 vs Budget | p95 vs Budget | Status |
|-------|----------|----------|---------------|---------------|---------|
| Multi-intent | **3,929** | **5,667** | ❌ 7.9× over | ❌ 11.3× over | FAIL |
| Lookup | **2,227** | **3,862** | ❌ 4.5× over | ❌ 7.7× over | FAIL |
| Brainstorm | **2,497** | **4,171** | ❌ 5.0× over | ❌ 8.3× over | FAIL |

**Budget Targets:**
- Router p50: ≤500ms
- Router p95: ≤1,500ms
- End-to-end: <3,000ms

---

## Degradation vs. July 2026 Baseline

Compared to the adc-2xf52 baseline measurements:

| Shape | Baseline p50 | Current p50 | Change | Baseline p95 | Current p95 | Change |
|-------|--------------|-------------|---------|--------------|-------------|---------|
| Multi-intent | 2,074ms | **3,929ms** | +89.5% ⬆️ | 4,301ms | **5,667ms** | +31.8% ⬆️ |
| Lookup | 1,640ms | **2,227ms** | +35.8% ⬆️ | 3,298ms | **3,862ms** | +17.1% ⬆️ |
| Brainstorm | 1,587ms | **2,497ms** | +57.4% ⬆️ | 2,527ms | **4,171ms** | +65.0% ⬆️ |

**Critical Finding:** Performance has **degraded 18-90%** across all shapes compared to the July baseline. The optimization work in adc-1kp7n either had no measurable effect or made performance worse.

---

## Compliance Summary

| Stage | Budget (p50/p95) | Measured p50 | Measured p95 | Status |
|-------|-----------------|--------------|--------------|---------|
| Intent Router | 500ms / 1,500ms | **2,227-3,929ms** ❌ | **3,862-5,667ms** ❌ | FAIL (4.5-7.9× / 7.7-11.3×) |
| End-to-end | <3,000ms | **2,227-3,929ms** ❌ | **3,862-5,667ms** ❌ | FAIL (1.3-2.3× over budget) |

**Overall Verdict:** The system does **NOT** meet the latency budget requirements established in plan.md. The demo gate remains blocked until either:
1. Router latency is reduced to meet 500ms p50 / 1,500ms p95 budgets, OR
2. The on-screen promise is revised from "<3s" to reflect actual measured performance (currently 4-6s)

---

## Remaining Gaps

### Primary Bottleneck: ZAI Proxy / LLM Inference

- **Root Cause:** External LLM inference via ZAI proxy dominates router timing
- **Measured Impact:** 1,449-1,875ms per LLM call (proxy inference time alone)
- **Network Overhead:** ~116ms per call
- **Cache Performance:** Excellent (7-50ms for cached intents) but budget requires uncached performance

### Why Optimizations Failed

The prompt simplification, max_tokens reduction, and caching optimizations attempted in adc-1kp7n did not address the fundamental bottleneck: **external LLM inference latency**. The router remains bound by ZAI proxy response times regardless of prompt size or token limits.

---

## Recommended Next Steps

### Immediate (Demo-Blocking)

1. **Correct Plan Documentation:** Update plan.md gate status to reflect actual measured performance
2. **Address Root Cause:** ZAI proxy/LLM inference is the dominant bottleneck (1.4-1.9s per call)
3. **Consider Alternatives:**
   - Switch to faster LLM model
   - Implement local inference
   - Change LLM provider
   - Architectural changes to reduce LLM dependency

### Performance Optimization Path

1. **Profile ZAI Proxy:** Investigate why inference time is consistently 1.4-1.9s
2. **Evaluate Model Options:** Test if different model classes (faster inference) meet accuracy requirements
3. **Reduce LLM Calls:** Consider if router functionality can be achieved with deterministic code + caching
4. **Consider Architectural Changes:** Move from LLM-based routing to deterministic routing where possible

---

## Test Data

**Full Results:** `/tmp/e2e-latency-test-results.json`
**Live Performance:** `curl http://localhost:8000/api/v1/timings/percentiles`
**Test Runs:** 90 total (30 per shape × 3 shapes)
**Test Shapes:**
1. Multi-intent: "Has the pbx web caught up, and what's the state of whisper stt?"
2. Lookup: "Pull up the recent logs for whisper stt"
3. Brainstorm: "Brainstorm improvements to the pbx web deployment pipeline"

**Documentation Status:** ✅ Complete — This document represents the final verified end-to-end baseline for July 2026 with all acceptance criteria tested and documented.