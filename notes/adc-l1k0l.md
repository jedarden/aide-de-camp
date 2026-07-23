# Stages Exceeding Latency Budget Estimates

**Analysis Date:** 2026-07-23
**Data Source:** `data/parsed/stage_percentiles.json` (205 dispatches across 3 shapes)
**Budget Reference:** `docs/plan/plan.md` — Latency Budget & Instrumentation section

## Budget vs Actual Summary

### Critical Finding: Most stages significantly exceed budget estimates

The following stages consistently exceed their target budgets across all test shapes:

---

## 1. Intent Router

**Budget:** ~500ms

**Actual Performance:**
| Shape | p50 (ms) | p95 (ms) | p50 Overage | p95 Overage |
|-------|----------|----------|-------------|-------------|
| Shape 1 (Multi-intent status) | 2,074 | 4,187.5 | **4.1x (3,154ms over)** | **8.4x (3,687ms over)** |
| Shape 2 (Lookup logs) | 1,640 | 3,297.4 | **3.3x (1,140ms over)** | **6.6x (2,797ms over)** |
| Shape 3 (Brainstorm) | 1,587 | 2,487.1 | **3.2x (1,087ms over)** | **5.0x (1,987ms over)** |

**Magnitude:** Exceeds budget by **3.2x - 8.4x** across all shapes

---

## 2. Synthesize (First Token)

**Budget:** ~1,000ms (1s)

**Actual Performance:**
| Shape | p50 (ms) | p95 (ms) | p50 Overage | p95 Overage |
|-------|----------|----------|-------------|-------------|
| Shape 1 (Multi-intent status) | 3,108 | 4,592.5 | **3.1x (2,108ms over)** | **4.6x (3,592ms over)** |
| Shape 2 (Lookup logs) | 3,787.5 | 5,320.8 | **3.8x (2,787ms over)** | **5.3x (4,320ms over)** |
| Shape 3 (Brainstorm) | 3,984 | 6,666.7 | **4.0x (2,984ms over)** | **6.7x (5,666ms over)** |

**Magnitude:** Exceeds budget by **3.1x - 6.7x** across all shapes

---

## 3. Escalate (Bead Formulation + Validation + bf create)

**Budget:** ~2,000ms (2s)
*Note: This stage is off the first-card critical path*

**Actual Performance:**
| Shape | p50 (ms) | p95 (ms) | p50 Overage | p95 Overage |
|-------|----------|----------|-------------|-------------|
| Shape 1 (Multi-intent status) | 3,992 | 5,402.3 | **2.0x (1,992ms over)** | **2.7x (3,402ms over)** |
| Shape 2 (Lookup logs) | N/A | N/A | No escalate data | No escalate data |
| Shape 3 (Brainstorm) | N/A | N/A | No escalate data | No escalate data |

**Magnitude:** Exceeds budget by **2.0x - 2.7x** (Shape 1 only)

---

## 4. End-to-End (Utterance End → First Partial Card)

**Budget:** < 3,000ms (3s) — **This is the binding gate**

**Actual Performance:**
| Shape | p50 (ms) | p95 (ms) | p50 Overage | p95 Overage |
|-------|----------|----------|-------------|-------------|
| Shape 1 (Multi-intent status) | 5,553.5 | 8,031.5 | **1.9x (2,553ms over)** | **2.7x (5,031ms over)** |
| Shape 2 (Lookup logs) | 5,640.5 | 8,427.35 | **1.9x (2,640ms over)** | **2.8x (5,427ms over)** |
| Shape 3 (Brainstorm) | 5,937 | 8,784.2 | **2.0x (2,937ms over)** | **2.9x (5,784ms over)** |

**Magnitude:** Exceeds binding budget by **1.9x - 2.9x** — The system's central latency promise is not met

---

## Stages Within Budget

### Fetch Strands

**Budget:** ~500ms (first source), ~1,000ms (window close)

**Actual Performance:**
| Shape | p50 (ms) | p95 (ms) | Status |
|-------|----------|----------|--------|
| Shape 1 (Multi-intent status) | 37 | 178.5 | **WELL UNDER** (13x under budget at p50) |
| Shape 2 (Lookup logs) | 45 | 190.7 | **WELL UNDER** (11x under budget at p50) |
| Shape 3 (Brainstorm) | 0 | 0 | **WELL UNDER** (no fetch needed for brainstorm intent) |

### STT (Web Speech API)

**Budget:** ~300ms
**Status:** No client-reported timing data available in baseline measurements

### SSE Emit → First Card Render

**Budget:** ~100ms
**Status:** No data available (not captured in instrumentation)

---

## Summary of Exceeding Stages

| Stage | Budget | Worst p50 Overage | Worst p95 Overage | Severity |
|-------|--------|-------------------|-------------------|----------|
| **Intent Router** | ~500ms | 4.1x (3,154ms over) | 8.4x (3,687ms over) | 🔴 **CRITICAL** |
| **Synthesize** | ~1,000ms | 4.0x (2,984ms over) | 6.7x (5,666ms over) | 🔴 **CRITICAL** |
| **Escalate** | ~2,000ms | 2.0x (1,992ms over) | 2.7x (3,402ms over) | 🟡 **MODERATE** (off critical path) |
| **End-to-End** | <3,000ms | 2.0x (2,937ms over) | 2.9x (5,784ms over) | 🔴 **CRITICAL** — Promise broken |

---

## Implications

Per the plan's Gate requirement:

> **Gate.** The demo cannot be scheduled until the Measured p50/p95 columns are filled from real runs. If measured p95 blows a stage's budget, either the stage gets fixed or the on-screen promise changes — the recording must not showcase a number the system doesn't hit.

**Current State:** The measured p95 values blow the budgets for both individual stages (Intent Router, Synthesize) **and** the binding end-to-end gate. The < 3s promise is not being met.

**Required Actions:**
1. Fix Intent Router latency (primary contributor to e2e overage)
2. Fix Synthesize latency (secondary contributor)
3. Re-measure after fixes
4. Update the on-screen promise if fixes cannot bring performance within budget, OR delay demo until performance meets the stated promise
