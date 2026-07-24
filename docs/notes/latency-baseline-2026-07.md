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

## FINAL VERIFICATION STATUS

**Verification Date:** 2026-07-24  
**Bead:** adc-102n1  
**Verification Type:** Final baseline documentation and reporting  

### ✅ VERIFICATION COMPLETE — FAIL

All acceptance criteria for latency baseline documentation have been met:

- [x] Final results documented in latency-baseline-2026-07.md
- [x] Router p50/p95 compliance status: **❌ FAIL** (5.3× and 4.3× over budget respectively)
- [x] End-to-end p95 compliance status: **❌ FAIL** (2-2.5× over 3s budget)
- [x] Remaining gaps documented (ZAI proxy latency, LLM inference time)
- [x] Next steps documented (model changes, architectural alternatives)

**Overall Verdict:** The system does NOT meet the latency budget requirements established in plan.md. The demo gate remains blocked until either:
1. Router latency is reduced to meet 500ms p50 / 1,500ms p95 budgets, OR
2. The on-screen promise is revised from "<3s" to reflect actual measured performance

**Documentation Status:** ✅ Complete — This document represents the final verified baseline for July 2026.