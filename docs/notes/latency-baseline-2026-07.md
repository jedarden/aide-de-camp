# Latency Baseline — July 2026

**Baseline Date:** 2026-07-23  
**Server Version:** 0.22.0  
**Analysis Bead:** adc-2xf52  
**Data Collection Bead:** adc-21k11  

---

## Executive Summary

Comprehensive latency baseline collected from 206 successful dispatch runs across three test shapes. All measured hot-path stages **significantly exceed** their budget estimates, with end-to-end latencies missing the <3s target by 2-3.5x at p50 and 3-4x at p95.

**Key Finding:** The demo **cannot proceed** until latency issues are addressed per the plan's explicit gate.

---

## Test Environment

### Server Configuration

- **Host:** Hetzner EX44 (deploy-stage-a bare metal)
- **Server Process:** uvicorn src.main:app (running since 12:07 UTC)
- **Version:** 0.22.0 (git commit: 86baa2a)
- **LLM Endpoint:** ZAI proxy at `https://zai-proxy-mcp-apexalgo-iad-ts.ardenone.com:8444/v1/messages`
- **Database:** SQLite session store at `/home/coding/aide-de-camp/data/session.db`
- **ZAI Proxy Status:** Reachable during all test runs

### Test Methodology

**Data Collection Period:** 2026-07-23 17:09-17:20 UTC  
**Total Runs:** 206 (35 runs × 3 shapes, plus multi-intent multiplier effects)

**Test Shapes:**

1. **Shape 1 - Multi-Intent Status** (`step1_multi_status`)
   - **Utterance:** "Has the pbx web caught up, and what's the state of whisper stt?"
   - **Intent Pattern:** 2 parallel status intents (pbx-web + whisper-stt)
   - **Runs:** 35 successful → 106 timing records (multi-intent multiplier)
   - **Complexity:** Router segments multiple intents; fetch executes in parallel

2. **Shape 2 - Lookup Logs** (`step2_lookup_logs`)
   - **Utterance:** "Pull up the recent logs for whisper stt"
   - **Intent Pattern:** Single lookup:logs intent
   - **Runs:** 35 successful → 64 timing records
   - **Complexity:** Targeted fetch matrix (logs-specific commands)

3. **Shape 3 - Brainstorm** (`step3_brainstorm`)
   - **Utterance:** "Brainstorm improvements to the pbx web deployment pipeline"
   - **Intent Pattern:** Single brainstorm intent
   - **Runs:** 35 successful → 35 timing records
   - **Complexity:** Synthesis-only (zero fetch time)

### Instrumentation Coverage

| Metric | Capture Rate | Notes |
|--------|--------------|-------|
| `router_ms` | 100% (206/206) | ✅ Fully captured |
| `fetch_first_source_ms` | 80.1% (165/206) | Partial coverage |
| `fetch_total_ms` | 92.2% (190/206) | ✅ Good coverage |
| `synthesize_first_token_ms` | 0% (0/206) | ❌ **Critical gap** |
| `synthesize_total_ms` | 92.2% (190/206) | ✅ Good coverage |
| `escalate_ms` | 44.2% (91/206) | Task-profile only |
| `stt_ms` | 0% (0/206) | Client-side (not reported) |
| `sse_emit_ms` | 0% (0/206) | ❌ Not instrumented |
| `first_render_ms` | 0% (0/206) | Client-side (not reported) |

**Instrumentation Gaps:**
- **Synthesize first token:** Critical timing shows `count: 0` — streaming token capture logic not working
- **STT timing:** Client-side Web Speech API timing not reported to server
- **SSE emit:** Server-side timing not captured
- **First render:** Client-side canvas render timing not reported

---

## Raw Data Summary

### Shape 1: Multi-Intent Status (106 records)

**Metadata:**
- Timestamp: 2026-07-23T17:09:41
- Target runs: 35 → Actual: 106 (multi-intent multiplier)
- Success rate: 100%

**Stage Timings:**

| Stage | Count | p50 | p95 | Min | Max | Mean |
|-------|-------|-----|-----|-----|-----|------|
| `router_ms` | 106 | 2,074ms | 4,301ms | 1,385ms | 5,284ms | 2,347ms |
| `fetch_first_source_ms` | 91 | 14ms | 21ms | 8ms | 32ms | 14ms |
| `fetch_total_ms` | 91 | 37ms | 179ms | 22ms | 200ms | 85ms |
| `synthesize_total_ms` | 91 | 3,108ms | 4,663ms | 2,136ms | 6,328ms | 3,367ms |
| `escalate_ms` | 91 | 3,992ms | 5,445ms | 2,789ms | 7,234ms | 4,245ms |

**End-to-End:** p50 ~5,219ms | p95 ~8,853ms (derived from stage composition)

---

### Shape 2: Lookup Logs (64 records)

**Metadata:**
- Timestamp: 2026-07-23T17:14:58
- Target runs: 35 → Actual: 64
- Success rate: 100%

**Stage Timings:**

| Stage | Count | p50 | p95 | Min | Max | Mean |
|-------|-------|-----|-----|-----|-----|------|
| `router_ms` | 64 | 1,640ms | 3,298ms | 1,312ms | 4,102ms | 2,012ms |
| `fetch_first_source_ms` | 58 | 0ms | 0ms | 0ms | 0ms | 0ms |
| `fetch_total_ms` | 58 | 0ms | 0ms | 0ms | 0ms | 0ms |
| `synthesize_total_ms` | 58 | 3,794ms | 5,364ms | 2,456ms | 7,123ms | 4,012ms |

**End-to-End:** p50 ~5,434ms | p95 ~8,662ms

---

### Shape 3: Brainstorm (35 records)

**Metadata:**
- Timestamp: 2026-07-23T17:20:11
- Target runs: 35 → Actual: 35
- Success rate: 100%

**Stage Timings:**

| Stage | Count | p50 | p95 | Min | Max | Mean |
|-------|-------|-----|-----|-----|-----|------|
| `router_ms` | 35 | 1,587ms | 2,527ms | 1,234ms | 3,456ms | 1,823ms |
| `synthesize_total_ms` | 35 | 3,984ms | 7,877ms | 2,678ms | 9,234ms | 4,567ms |

**End-to-End:** p50 ~5,571ms | p95 ~10,404ms

---

## Stage-by-Stage Analysis

### ❌ Intent Router — FAILS Budget (~500ms target)

**Measured Performance:**
- p50: 1,587-2,074ms (3.1-4.1x over budget)
- p95: 2,527-4,301ms (5-8.6x over budget)

**Analysis:**
- Router is consistently 3-4× slower than budget at p50
- Worst p95 reaches 4.3 seconds (Shape 1)
- Multi-intent segmentation (Shape 1) shows highest latency
- This is the **most variable stage** with high outlier sensitivity

**Potential Causes:**
- ZAI proxy latency (network hop to apexalgo-iad)
- Haiku model inference time
- Router prompt complexity (multi-intent segmentation)
- JSON parsing overhead

---

### ✅ Fetch Stages — PASS Budget (~500ms first-source / ~1s window)

**Measured Performance:**
- First source: p50 0-14ms | p95 0-21ms
- Window close: p50 0-37ms | p95 0-179ms

**Analysis:**
- Fetch **comfortably meets** budget with 10-50× headroom
- Local kubectl/git commands execute in milliseconds
- ArgoCD API calls via proxy are fast
- Only component meeting its budget

---

### ❌ Synthesize — FAILS Budget (~1-2s estimate)

**Measured Performance:**
- Total: p50 3,108-3,984ms | p95 4,663-7,877ms
- First token: *Not measured* (instrumentation gap)

**Analysis:**
- Synthesis is the **dominant latency contributor**
- Exceeds budget by 2-3× at p50
- Catastrophic p95: 4.7-7.9 seconds
- Brainstorm intent (Shape 3) shows worst variability (p95 7,877ms)

**Critical Gap:** First-token timing not captured — this is the binding gate for the <3s promise but shows `count: 0` across all shapes.

---

### ❌ Escalate — FAILS Budget (~2s target)

**Measured Performance:**
- p50: 3,992ms | p95: 5,445ms

**Analysis:**
- Exceeds budget by 2× at p50
- p95 reaches 5.4 seconds
- Only Shape 1 (task-profile intents requiring escalation)
- **Does not block demo** — task-profile ack card renders before escalate completes

---

### ❌ End-to-End — FAILS Budget (<3s target)

**Measured Performance:**
- p50: 5,219-5,571ms (1.7-1.9× over budget)
- p95: 8,853-10,404ms (3-4× over budget)

**Analysis:**
- **Core product promise fails completely**
- The <3s claim cannot be made in good faith
- Demo-blocking finding per plan's explicit gate

**E2E Composition (Shape 1, p50):**
```
Router:       2,074ms (39.7%)
Fetch Window:    37ms (0.7%)
Synthesize:   3,108ms (59.5%)
SSE Emit:        ?   (unmeasured)
────────────────────
Total:        ~5,219ms
```

---

## Budget vs. Measured Comparison

| Stage | Budget (ESTIMATE) | Measured p50 | Measured p95 | Status |
|-------|-------------------|--------------|--------------|---------|
| STT final transcript | ~300ms | *Not measured* | *Not measured* | ⚠️ Unmeasured |
| Intent Router | ~500ms | **1,587-2,074ms** ❌ | **2,527-4,301ms** ❌ | FAIL |
| Fetch — first source | ~500ms | **0-14ms** ✅ | **0-21ms** ✅ | PASS |
| Fetch — window close | ~1s | **0-37ms** ✅ | **0-179ms** ✅ | PASS |
| Synthesize — first token | ~1s | *Not measured* | *Not measured* | ⚠️ Unmeasured |
| Synthesize — total | ~1-2s | **3,108-3,984ms** ❌ | **4,663-7,877ms** ❌ | FAIL |
| SSE emit → first render | ~100ms | *Not measured* | *Not measured* | ⚠️ Unmeasured |
| Escalate | ~2s | **3,992ms** ❌ | **5,445ms** ❌ | FAIL |
| **End-to-end** | **< 3s** | **5,219-5,571ms** ❌ | **8,853-10,404ms** ❌ | FAIL |

---

## Observations & Anomalies

### 1. Synthesize First Token Not Captured
**Issue:** `synthesize_first_token_ms` shows `count: 0` across all 206 records.

**Impact:** Cannot validate the ~1s first-token budget — this is the binding gate per the plan's internal-consistency note.

**Diagnosis:** Streaming token timing logic in the server is not functioning. The instrumentation requirement specifies this metric should be captured, but the implementation appears broken.

---

### 2. Multi-Intent Router Latency
**Observation:** Shape 1 (multi-intent) shows significantly worse router performance:
- p50: 2,074ms vs 1,587-1,640ms (single-intent shapes)
- p95: 4,301ms vs 2,527-3,298ms

**Analysis:** Multi-intent segmentation adds complexity:
- Router must parse and split multiple project references
- JSON output structure is larger
- Prompt complexity increases with intent count

---

### 3. Zero Fetch Time for Shape 2
**Observation:** Shape 2 (lookup:logs) shows `fetch_first_source_ms` and `fetch_total_ms` as exactly 0ms for all runs.

**Analysis:** This suggests the fetch matrix for `lookup:logs` may be:
- Empty (no commands defined)
- Failing silently (all sources timeout)
- Cached with zero propagation delay

**Requires Investigation:** Verify `prompts/fetch/lookup-logs.md` has defined commands.

---

### 4. Brainstorm Synthesis Variability
**Observation:** Shape 3 (brainstorm) shows worst synthesis variability:
- p95: 7,877ms (vs 4,663-5,364ms for other shapes)
- Max: 9,234ms

**Analysis:** Brainstorm prompts likely generate longer, more complex responses:
- More tokens generated → higher latency
- More creative task → less predictable inference time
- May need separate budget allocation

---

### 5. ZAI Proxy Reachability
**Observation:** All three shapes report `zai_proxy_reachable: true`.

**Note:** No proxy-related failures occurred during baseline collection. Latency issues are not due to proxy unavailability.

---

## Compliance with Plan Gate

**Gate Status:** ❌ **FAIL** — Demo cannot proceed

From the plan:
> **Gate.** The demo cannot be scheduled until the Measured p50/p95 columns are filled from real runs (rehearsal timing logs count). If measured p95 blows a stage's budget, either the stage gets fixed or the on-screen promise changes — the recording must not showcase a number the system doesn't hit.

**Assessment:**
- ✅ Measured p50/p95 columns are filled
- ❌ Measured p95 **blows budget** for router, synthesize, escalate, and e2e
- ❌ The <3s promise **cannot be showcased**

**Conclusion:** Per the plan's explicit gate, the demo **cannot be scheduled** until either:
1. Router and Synthesis latencies are reduced to meet budgets, OR
2. The on-screen promise is changed (not recommended — undermines product value)

---

## Next Steps

### Immediate (Demo-Blocking)
1. **Fix synthesize_first_token_ms instrumentation** — Critical for validating e2e gate
2. **Investigate router latency** — 3-4× over budget suggests fundamental issues
3. **Optimize synthesis** — 2-3× over budget is the dominant latency contributor

### Data Collection
4. **Instrument SSE emit timing** — Add server-side capture
5. **Add client-side timing reports** — STT and first render from canvas

### Architecture
6. **Re-evaluate budget targets** — Estimates were 3-4× too low. Either fix stages or adjust promise.

---

## Data Files

**Raw JSON Data:**
- `/home/coding/aide-de-camp/data/latency-baseline-shape1-20260723_170941.json` (106 records)
- `/home/coding/aide-de-camp/data/latency-baseline-shape2-20260723_171458.json` (64 records)
- `/home/coding/aide-de-camp/data/latency-baseline-shape3-20260723_172011.json` (35 records)

**Analysis Bead:** adc-2xf52  
**Parent Plan:** `/home/coding/aide-de-camp/docs/plan/plan.md` → "Latency Budget & Instrumentation"

**Total Runs:** 206 timing records across all shapes  
**Success Rate:** 100% (all runs completed successfully)

---

## Post-Optimization Verification — 2026-07-24

**Verification Date:** 2026-07-24  
**Analysis Bead:** adc-1jrkq  
**Optimization Bead:** adc-1kp7n  
**Server Version:** 0.22.0 (post-optimization commits 828d3fb, 4dca81f)

### Executive Summary

**❌ DEMO GATE REMAINS BLOCKED** — The intent router optimizations implemented in adc-1kp7n did not achieve the latency budget targets. Performance has actually **degraded** compared to the July 2026 baseline, with p50 latencies 39-84% worse across all test shapes.

### Critical Findings

1. **Performance Degradation:** All three test shapes show worse latencies after optimization
2. **Budget Target Miss:** Router latency still 5-6× over the 500ms budget (measured p50: 2,808ms)
3. **Synthesis Failures:** HTTP 500 errors (8 failures in multi-intent, 1 in brainstorm) due to missing import
4. **Cache Working:** Intent cache functional (100% hit rate on repeated utterances), but not enough to compensate for slow base latency

### Detailed Comparison

| Shape | Metric | Baseline (Jul 2026) | Post-Opt (Jul 24) | Change | Status |
|-------|--------|-------------------|------------------|---------|---------|
| Multi-intent | p50 | 2,074ms | 2,887ms | +39% worse | ❌ Degraded |
| Multi-intent | p95 | 4,301ms | 8,025ms | +87% worse | ❌ Degraded |
| Lookup | p50 | 1,640ms | 3,022ms | +84% worse | ❌ Degraded |
| Lookup | p95 | 3,298ms | 4,293ms | +30% worse | ❌ Degraded |
| Brainstorm | p50 | 1,587ms | 2,478ms | +56% worse | ❌ Degraded |
| Brainstorm | p95 | 2,527ms | 4,284ms | +70% worse | ❌ Degraded |

### Test Methodology

**Data Collection Period:** 2026-07-24 03:43-03:49 UTC  
**Total Runs:** 90 (30 runs × 3 shapes)  
**Success Rate:** 90% (81/90 successful, 9 failures due to synthesis errors)

**Instrumentation:** Automated test script `test_e2e_latency.py` measuring:
- Full dispatch latency (HTTP POST /dispatch → response)
- Router timing via `/api/v1/timings/percentiles` endpoint

### Root Cause Analysis

1. **Missing Import Bug:** `src/synthesize/strand.py` missing `ParseLLMError` import from `..llm.response_parser`, causing synthesis failures and HTTP 500 errors

2. **Insufficient Optimization:** The prompt simplification and max_tokens reduction (96→80) in adc-1kp7n did not significantly reduce inference time

3. **ZAI Proxy Latency:** Router timing breakdown shows:
   - `proxy_inference_ms`: 1,449-1,875ms (dominant contributor)
   - `proxy_network_ms`: ~116ms (consistent overhead)
   - Total router time: 1,566-1,992ms per call

### Compliance with Budget Targets

| Stage | Budget | Measured p50 | Measured p95 | Status |
|-------|--------|--------------|--------------|---------|
| Intent Router | ~500ms | **2,808ms** ❌ | **5,558ms** ❌ | FAIL (5.6× over) |
| End-to-end | <3s | **2.5-8+ seconds** ❌ | **4.3-8+ seconds** ❌ | FAIL |

**Gate Status:** ❌ **DEMO REMAINS BLOCKED**

Per the plan's explicit gate: "The demo cannot be scheduled until the Measured p50/p95 columns are filled from real runs... If measured p95 blows a stage's budget, either the stage gets fixed or the on-screen promise changes."

### Recommended Actions

1. **Fix Critical Bug:** Add missing `ParseLLMError` import to `src/synthesize/strand.py` (adc-1jrkq-5)
2. **Re-evaluate Approach:** Current optimization strategies insufficient for 500ms target
3. **Consider Alternatives:**
   - Switch to faster model (current GLM-4.7 inference 1.4-1.9s)
   - Implement request batching/streaming
   - Cache more aggressively (currently 5min TTL)
   - Architectural changes (local inference, different LLM provider)

---

**Raw Test Data:** `/tmp/e2e-latency-test-results.json` (2026-07-24 03:49:02 UTC)
