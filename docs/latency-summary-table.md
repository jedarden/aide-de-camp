# Latency Baseline Summary Table

## Overview

This document summarizes the p50/p95 latencies for each pipeline stage across the three demo-step shapes, based on the baseline data collected on 2026-07-23.

## Budget vs. Measured Comparison

| Stage | Budget (ESTIMATE) | Measured p50 | Measured p95 | Status |
|-------|-------------------|--------------|--------------|---------|
| Intent Router | ~500ms | 1,587–2,074ms | 2,527–4,301ms | ❌ **FAIL (3-8x)** |
| Fetch — first source returns | ~500ms | 0–16ms | 0–21ms | ✅ **PASS** |
| Fetch — window closes | ~1,000ms | 0–51ms | 0–191ms | ✅ **PASS** |
| Synthesize — first token | ~1,000ms | *Not measured* | *Not measured* | ⚠️ **UNMEASURED** |
| Synthesize — total | ~1-2s | 3,108–3,984ms | 4,663–7,877ms | ❌ **FAIL (2-7x)** |
| SSE emit → first card render | ~100ms | *Not measured* | *Not measured* | ⚠️ **UNMEASURED** |
| Escalate | ~2,000ms | 3,992ms | 5,445ms | ❌ **FAIL (2x)** |
| **End-to-end** | **< 3,000ms** | **5,219–5,571ms** | **8,853–10,404ms** | ❌ **FAIL (3-4x)** |

**Gate Status:** ❌ DEMO BLOCKING — Per plan gate, demo cannot proceed until stages are fixed or on-screen promise is adjusted.

## Stage Latencies by Shape

| Stage | Shape 1 (p50) | Shape 1 (p95) | Shape 2 (p50) | Shape 2 (p95) | Shape 3 (p50) | Shape 3 (p95) |
|-------|---------------|---------------|---------------|---------------|---------------|---------------|
| **Intent Router** | 2,074 ms | 4,301 ms | 1,640 ms | 3,298 ms | 1,587 ms | 2,527 ms |
| **Fetch First Source** | 14 ms | 21 ms | 16 ms | 21 ms | — | — |
| **Fetch Total** | 37 ms | 179 ms | 51 ms | 191 ms | — | — |
| **Synthesize** | 3,108 ms | 4,663 ms | 3,794 ms | 5,364 ms | 3,984 ms | 7,877 ms |
| **Escalate** | 3,992 ms | 5,445 ms | — | — | — | — |
| **E2E (Router → Synthesize)** | 5,219 ms | 9,143 ms | 5,485 ms | 8,853 ms | 5,571 ms | 10,404 ms |

## Shape Descriptions

- **Shape 1 (Multi-intent status query)**: "Has the pbx web caught up, and what's the state of whisper stt?"
  - 106 timing records
  - Multi-fetch scenario (pbx-web + whisper-stt)
  - Includes escalate cases

- **Shape 2 (Lookup logs)**: "Pull up the recent logs for whisper stt."
  - 64 timing records
  - Single-fetch scenario (whisper-stt logs)

- **Shape 3 (Brainstorm)**: "Should pbx web keep using the static site generator, or is it time to move to a dynamic frontend? Give me the trade-offs."
  - 35 timing records
  - No fetch (synthesis-only)

## Key Findings

1. **Intent Router** is the most variable stage, with p95 latencies ranging from 2.5s (Shape 3) to 4.3s (Shape 1)
2. **Fetch stages** are consistently fast (p50 < 50ms) but show higher variability at p95 (up to 191ms for Shape 2)
3. **Synthesis** is the dominant latency contributor, ranging from 3.1s (Shape 1 p50) to 7.9s (Shape 3 p95)
4. **E2E latency** p50 is consistent (~5.2-5.6s) across shapes, but p95 varies significantly (8.9s to 10.4s)
5. **Shape 3 (no fetch)** shows the highest synthesis variability, likely due to the complex, open-ended nature of brainstorming queries

## Stages Exceeding Budgets

### Demo-Blocking Failures (Hot Path)

1. **Intent Router — FAILS Budget (~500ms estimate)**
   - p50: 1,587–2,074ms (3.1-4.1x over budget)
   - p95: 2,527–4,301ms (5-8.6x over budget)
   - Impact: Sequential stage; directly adds 2-4s to e2e latency
   - Severity: HIGH — Most variable stage

2. **Synthesize — FAILS Budget (~1-2s estimate)**
   - p50: 3,108–3,984ms (2-3x over budget)
   - p95: 4,663–7,877ms (4.7-7.9x over budget)
   - Impact: Dominant latency contributor; 2-4s per intent thread
   - Severity: CRITICAL — Largest latency contributor
   - Note: `synthesize_first_token_ms` instrumentation is broken (count: 0)

3. **End-to-End — FAILS Budget (< 3,000ms target)**
   - p50: 5,219–5,571ms (1.7-1.9x over budget)
   - p95: 8,853–10,404ms (3-3.5x over budget)
   - Impact: Core product promise (< 3s to first card) cannot be met
   - Severity: BLOCKING — Demo cannot proceed per plan gate

### Non-Blocking Failures (Off First-Card Path)

4. **Escalate — FAILS Budget (~2,000ms estimate)**
   - p50: 3,992ms (2x over budget)
   - p95: 5,445ms (2.7x over budget)
   - Impact: Task-profile bead creation; does not gate first card
   - Severity: MEDIUM — Not demo-blocking (ack card renders before escalate completes)

### Passing Stages

5. **Fetch Stages — PASS Budget (~500ms first source / ~1,000ms window close)**
   - Fetch first source: p50 0-16ms, p95 0-21ms (well under 500ms budget)
   - Fetch window: p50 0-51ms, p95 0-191ms (well under 1,000ms budget)
   - Only stages meeting their budgets

### Unmeasured Critical Timings

6. **STT final transcript — UNMEASURED (~300ms budget)**
   - Client-side timing; not reported to server
   - Missing from e2e calculation

7. **Synthesize first token — UNMEASURED (~1,000ms budget)**
   - Instrumentation shows `count: 0` — broken streaming token capture
   - **Critical gap** since this gates the e2e promise per plan's internal-consistency note

8. **SSE emit → first card render — UNMEASURED (~100ms budget)**
   - Not instrumented

## Recommended Actions

### Immediate (Demo-Blocking)
1. Fix synthesize_first_token_ms instrumentation — Critical for e2e gate validation
2. Investigate router latency — 3-4x over budget suggests fundamental issues
3. Optimize synthesis — 2-3x over budget is the dominant latency contributor

### Data Collection
4. Instrument SSE emit timing
5. Add client-side timing reports (STT, first render)

## Data Source

- Consolidated baseline data: `/home/coding/aide-de-camp/data/parsed/latency_baseline_consolidated.json`
- Parsed from raw baseline test runs on 2026-07-23
- Source bead: adc-21k11
