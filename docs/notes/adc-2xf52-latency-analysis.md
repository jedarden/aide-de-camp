# Latency Budget Analysis — adc-2xf52

**Analysis Date:** 2026-07-23  
**Source Bead:** adc-21k11 (latency baseline data collection)  
**Data Files:**
- `/home/coding/aide-de-camp/data/latency-baseline-shape1-20260723_170941.json`
- `/home/coding/aide-de-camp/data/latency-baseline-shape2-20260723_171458.json`
- `/home/coding/aide-de-camp/data/latency-baseline-shape3-20260723_172011.json`

---

## Executive Summary

All measured stages **significantly exceed** their budget estimates. The end-to-end latency target of <3 seconds is missed by a wide margin across all shapes, with p50 latencies ranging from 5.2-5.6 seconds (2.3-2.6x over budget) and p95 latencies reaching 8.9-10.4 seconds (3-4x over budget).

**Critical Finding:** No stage meets its budget. The system cannot proceed to demo scheduling without addressing these latency issues, as the gate in the plan states: *"The demo cannot be scheduled until the Measured p50/p95 columns are filled from real runs."*

---

## Budget vs. Measured Comparison

| Stage | Budget (ESTIMATE) | Measured p50 (All Shapes) | Measured p95 (All Shapes) | Status |
|-------|-------------------|---------------------------|---------------------------|---------|
| STT final transcript | ~300ms | *Not measured* | *Not measured* | ⚠️ Unmeasured |
| Intent Router | ~500ms | **1,587–2,074ms** | **2,527–4,301ms** | ❌ **FAIL** |
| Fetch — first source returns | ~500ms | **0–16ms** | **0–21ms** | ✅ **PASS** |
| Fetch — window closes | ~1,000ms | **0–51ms** | **0–191ms** | ✅ **PASS** |
| Synthesize — first token | ~1,000ms | *Not measured* | *Not measured* | ⚠️ Unmeasured |
| Synthesize — total | ~1-2s (estimate) | **3,108–3,984ms** | **4,663–7,877ms** | ❌ **FAIL** |
| SSE emit → first card render | ~100ms | *Not measured* | *Not measured* | ⚠️ Unmeasured |
| Escalate | ~2,000ms | **3,992ms** | **5,445ms** | ❌ **FAIL** |
| **End-to-end** | **< 3,000ms** | **5,219–5,571ms** | **8,853–10,404ms** | ❌ **FAIL** |

---

## Stage-by-Stage Analysis

### ❌ Intent Router — FAILS Budget
**Budget:** ~500ms  
**Measured:** p50 1,587–2,074ms (3.1-4.1x over) | p95 2,527–4,301ms (5-8.6x over)

**Analysis:**
- The router is consistently **3-4x slower** than budget at p50
- At p95, latency reaches **4.3 seconds** — nearly half the entire e2e budget
- Shape 1 (multi-intent) shows the worst router performance (p95 4,301ms)
- This is the **most variable stage**, with high outlier sensitivity

**Evidence:**
```json
// Shape 1 (Multi-intent status)
"router_ms": {
  "p50": 2074,  // 4.1x over budget
  "p95": 4301   // 8.6x over budget
}

// Shape 2 (Lookup logs)
"router_ms": {
  "p50": 1640,  // 3.3x over budget
  "p95": 3298   // 6.6x over budget
}

// Shape 3 (Brainstorm)
"router_ms": {
  "p50": 1587,  // 3.2x over budget
  "p95": 2527   // 5.1x over budget
}
```

---

### ✅ Fetch Stages — PASS Budget
**Budget:** ~500ms (first source) | ~1,000ms (window close)  
**Measured:** p50 0–51ms | p95 0–191ms

**Analysis:**
- Fetch stages **comfortably meet** their budgets
- p50 latencies are negligible (0-51ms vs 500-1000ms budget)
- p95 latencies remain well under budget (191ms vs 1000ms)
- Shape 3 (brainstorm) has zero fetch time (synthesis-only)
- This is the **only component meeting its budget**

---

### ❌ Synthesize — FAILS Budget
**Budget:** ~1-2s (estimate for total) | ~1s (first token gate)  
**Measured:** p50 3,108–3,984ms | p95 4,663–7,877ms

**Analysis:**
- Synthesis is the **dominant latency contributor**
- p50 exceeds budget by **2-3x** (3.1-4.0s vs 1-2s estimate)
- p95 is catastrophically over budget at **4.7-7.9 seconds**
- Shape 3 (brainstorm) shows worst synthesis variability (p95 7,877ms)
- First-token timing was **not measured** — critical gap since this gates the e2e promise

**Evidence:**
```json
// Shape 1 (Multi-intent status)
"synthesize_total_ms": {
  "p50": 3108,  // 2.1-3.1x over budget
  "p95": 4663   // 4.7-7.9x over budget
}

// Shape 2 (Lookup logs)
"synthesize_total_ms": {
  "p50": 3794,  // 2.5-3.8x over budget
  "p95": 5364   // 5.4x over budget
}

// Shape 3 (Brainstorm)
"synthesize_total_ms": {
  "p50": 3984,  // 2.7-4.0x over budget
  "p95": 7877   // 7.9x over budget (worst case)
}
```

**Critical Gap:** `synthesize_first_token_ms` shows `count: 0` across all shapes — this critical timing was not captured. The plan's e2e gate depends on first-token latency (~1s budget), but we only measured total synthesis time.

---

### ❌ Escalate — FAILS Budget
**Budget:** ~2,000ms  
**Measured:** p50 3,992ms | p95 5,445ms

**Analysis:**
- Escalate exceeds budget by **2x** at p50 (3,992ms vs 2,000ms)
- p95 reaches **5.4 seconds** — 2.7x over budget
- Only measured in Shape 1 (multi-intent cases requiring escalation)
- Note: Escalate does not gate the <3s first-card promise (task-profile ack card renders before escalate completes), so this failure does not block the demo

**Evidence:**
```json
// Shape 1 (Multi-intent status with escalate cases)
"escalate_ms": {
  "count": 91,
  "p50": 3992,  // 2.0x over budget
  "p95": 5445   // 2.7x over budget
}
```

---

### ❌ End-to-End — FAILS Budget
**Budget:** < 3,000ms  
**Measured:** p50 5,219–5,571ms | p95 8,853–10,404ms

**Analysis:**
- **The core product promise fails completely**
- p50 exceeds budget by **1.7-1.9x** (5.2-5.6s vs 3s)
- p95 exceeds budget by **3-3.5x** (8.9-10.4s vs 3s)
- The <3s promise cannot be made in good faith with these measurements
- This is a **demo-blocking finding** per the plan's gate

**E2E Composition (Approximate, Shape 1 p50):**
- Router: 2,074ms
- Fetch Window: 37ms
- Synthesize: 3,108ms
- **Total:** ~5,219ms (without SSE emit, which was not measured)

**The missing measurements:**
- STT latency (client-side, not measured)
- Synthesize first token (not measured)
- SSE emit (not measured)
- First render (client-side, not measured)

---

## Unmeasured Critical Timings

The following stages specified in the plan's instrumentation requirement were **not captured**:

1. **STT final transcript (Web Speech API)** — Client-side timing, not reported to server
2. **Synthesize first token** — Server was configured to capture this (`synthesize_first_token_ms`), but shows `count: 0` — the streaming token timing logic is not working
3. **SSE emit → first card render** — Not instrumented
4. **First render (client-side)** — Client-side timing, not reported to server

**Impact:** The e2e gate cannot be properly validated without these measurements. In particular, `synthesize_first_token_ms` is the binding gate for the <3s promise per the plan's internal-consistency note.

---

## Stages Exceeding Budget — Ranked by Severity

| Rank | Stage | p50 Over-Budget | p95 Over-Budget | Critical to Demo? |
|------|-------|-----------------|-----------------|-------------------|
| 1 | **Synthesize** | 2-3x | 4.7-7.9x | ✅ Yes (gates first card) |
| 2 | **Intent Router** | 3-4x | 5-8.6x | ✅ Yes (sequential) |
| 3 | **Escalate** | 2x | 2.7x | ❌ No (off first-card path) |
| 4 | **Fetch** | ✅ Under budget | ✅ Under budget | ✅ Yes (but passing) |
| 5 | **STT** | ⚠️ Unmeasured | ⚠️ Unmeasured | ✅ Yes (sequential) |
| 6 | **SSE emit** | ⚠️ Unmeasured | ⚠️ Unmeasured | ✅ Yes (sequential) |

**Blocking Issues:** Synthesize and Intent Router failures are demo-blocking since they're on the sequential hot path and their budgets must sum inside the 3s e2e gate.

---

## Recommended Actions

### Immediate (Demo-Blocking)
1. **Fix synthesize_first_token_ms instrumentation** — This is critical for validating the e2e gate but currently shows `count: 0`
2. **Investigate router latency** — 3-4x over budget at p50 suggests fundamental issues (proxy latency, model choice, prompt complexity)
3. **Optimize synthesis** — 2-3x over budget at p50 is the dominant latency contributor; consider faster models or prompt optimization

### Data Collection
4. **Instrument SSE emit timing** — Add `sse_emit_ms` capture to validate the ~100ms budget
5. **Add client-side timing reports** — STT and first render timings should be reported from canvas to complete the e2e picture

### Architecture
6. **Re-evaluate budget targets** — The original estimates were ~500ms (router) and ~1-2s (synthesis). Measured reality is 3-4x higher. Either:
   - Fix the stages to meet budget, OR
   - Adjust the on-screen promise to match reality (but <3s is the product's central claim — changing it undermines the value prop)

---

## Compliance with Plan Gate

**Gate Status:** ❌ **FAIL** — Demo cannot proceed

From the plan:
> **Gate.** The demo cannot be scheduled until the Measured p50/p95 columns are filled from real runs (rehearsal timing logs count). If measured p95 blows a stage's budget, either the stage gets fixed or the on-screen promise changes — the recording must not showcase a number the system doesn't hit.

**Findings:**
- ✅ Measured p50/p95 columns are now filled from real runs
- ❌ Measured p95 **blows the budget** for router, synthesize, escalate, and e2e
- The <3s promise **cannot be showcased** in a recording

**Conclusion:** Per the plan's explicit gate, the demo **cannot be scheduled** until either:
1. Router and Synthesis latencies are reduced to meet their budgets, OR
2. The on-screen promise is changed to reflect measured reality (not recommended — undermines product value)

---

## Data Completeness

**Total Timing Records:** 206 (106 Shape 1 + 64 Shape 2 + 35 Shape 3)  
**Target Runs:** 35 per shape (all met)  
**Successful Runs:** 105/105 (100% success rate)

**Instrumentation Coverage:**
- ✅ Router: 100% captured (206/206 records)
- ✅ Fetch first source: 165/206 captured (80.1%)
- ✅ Fetch total: 190/206 captured (92.2%)
- ✅ Synthesize total: 190/206 captured (92.2%)
- ❌ Synthesize first token: 0/206 captured (0%) — **Critical gap**
- ⚠️ Escalate: 91/206 captured (44.2%) — Only for task-profile intents
- ❌ STT: 0/206 captured (0%) — Client-side
- ❌ SSE emit: 0/206 captured (0%)
- ❌ First render: 0/206 captured (0%) — Client-side

---

## Appendix: Raw Data References

- **Shape 1:** `/home/coding/aide-de-camp/data/latency-baseline-shape1-20260723_170941.json` (106 records)
- **Shape 2:** `/home/coding/aide-de-camp/data/latency-baseline-shape2-20260723_171458.json` (64 records)
- **Shape 3:** `/home/coding/aide-de-camp/data/latency-baseline-shape3-20260723_172011.json` (35 records)
- **Consolidated:** `/home/coding/aide-de-camp/data/parsed/latency_baseline_consolidated.json`

**Analysis Bead:** adc-2xf52  
**Parent Plan:** `/home/coding/aide-de-camp/docs/plan/plan.md` → "Latency Budget & Instrumentation"
