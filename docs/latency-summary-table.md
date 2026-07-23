# Latency Baseline Summary Table

## Overview

This document summarizes the p50/p95 latencies for each pipeline stage across the three demo-step shapes, based on the baseline data collected on 2026-07-23.

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

## Data Source

- Consolidated baseline data: `/home/coding/aide-de-camp/data/parsed/latency_baseline_consolidated.json`
- Parsed from raw baseline test runs on 2026-07-23
- Source bead: adc-21k11
