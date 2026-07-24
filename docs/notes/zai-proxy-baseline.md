# ZAI Proxy Latency Baseline

**Baseline Date:** 2026-07-24 05:35:15
**Analysis Type:** Database record analysis
**Sample Count:** 88 uncached router calls

---

## Executive Summary

This document establishes the baseline latency measurements for the ZAI proxy
used by the intent router in aide-de-camp. Measurements are from actual router
timing breakdowns stored in the session database.

---

## Intent Router Total Time

Total router time includes prompt construction, ZAI proxy call, JSON parsing,
and intent processing.

| Metric | Value |
|--------|------|
| Count | 88 samples |
| Average | 2634ms |
| Median | 2317ms |
| p95 | 5636ms |
| p99 | 7808ms |
| Min | 1200ms |
| Max | 7808ms |

---

## ZAI Proxy Call Time

Total time for the ZAI proxy call (network + inference).

| Metric | Value |
|--------|------|
| Average | 2634ms |
| Median | 2317ms |
| p95 | 5636ms |
| p99 | 7808ms |
| Min | 1199ms |
| Max | 7808ms |

---

## Network Latency Component

Network latency (time to first byte) measures the round-trip time to the ZAI proxy
before inference begins. This includes DNS lookup, TCP connection, TLS handshake,
and server processing time.

| Metric | Value |
|--------|------|
| Average | 1186ms |
| Median | 122ms |
| p95 | 3935ms |
| p99 | 5705ms |
| Min | 114ms |
| Max | 5705ms |

---

## Model Inference Time

Inference time is the time the LLM model spends generating the response, calculated
as proxy_call_ms - network_ms.

| Metric | Value |
|--------|------|
| Average | 1449ms |
| Median | 1338ms |
| p95 | 4356ms |
| p99 | 7686ms |
| Min | 1ms |
| Max | 7686ms |

---

## Router Overhead Breakdown

Non-ZAI router operations: prompt construction, JSON parsing, and intent processing.

| Component | Median | p95 |
|-----------|--------|-----|
| Prompt Construction | 0.17ms | 0.23ms |
| JSON Parsing | 0.03ms | 0.04ms |
| Intent Processing | 0.02ms | 0.04ms |

---

## Cache Statistics

| Metric | Value |
|--------|------|
| Cached Requests | 12 |
| Uncached Requests | 88 |
| Cache Hit Rate | 12.0% |

---

## Key Findings

### Network vs. Inference Breakdown

The ZAI proxy call consists of two components:

1. **Network Latency:** Median 122ms, which represents
   5.2% of total proxy call time.

2. **Model Inference:** Median 1338ms, which represents
   57.8% of total proxy call time.

### Performance Analysis


✓ **Expected Inference Time:** The 1338ms median
inference time is consistent with LLM model processing expectations.

✓ **Cache Effectiveness:** 12.0% cache hit rate
   demonstrates the value of the intent cache for repeated queries.

✓ **Router Overhead:** Non-proxy operations (prompt construction + JSON parsing +
   processing) add only ~0.22ms
   median, which is negligible compared to proxy call time.

---

## Comparison with Budget

Based on the latency budget from plan.md:

| Metric | Budget | Measured | Status |
|--------|--------|----------|--------|
| Router p50 | ~500ms | 2317ms | ❌ FAIL | 4.6× |
| Router p95 | ~1500ms | 5636ms | ❌ FAIL | 3.8× |


### Recommendations

1. **Investigate Timing Measurement:** The unusually low inference time suggests
   the timing instrumentation may not be capturing the full model inference
   duration. Consider adding token-stream timing to measure true inference time.

2. **Consider Faster Model:** If actual router time is indeed 2317ms median,
   consider using a faster model class (Haiku) or optimizing the prompt to
   reduce processing time.

3. **Leverage Cache:** The 12.0% cache hit rate shows caching is effective.
   Consider expanding cache TTL or implementing smarter cache keys.

---

## Data Source

Analysis based on 88 router timing records from the
session database (`data/session.db`). Only uncached requests are included in
statistics.

---

**Generated:** 2026-07-24 05:35:15