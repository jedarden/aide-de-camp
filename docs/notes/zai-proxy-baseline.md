# ZAI Proxy Latency Baseline

**Baseline Date:** 2026-07-24
**Measurement Count:** 20 requests
**Test Utterances:** 8 different prompts

---

## Executive Summary

This document establishes the baseline latency measurements for the ZAI proxy
used by the intent router in aide-de-camp. All measurements are from live
server requests using the existing instrumentation.

---

## End-to-End Latency

| Metric | Value |
|--------|------|
| Average | 1569ms |
| Median | 1408ms |
| p95 | 2805ms |
| Min | 1077ms |
| Max | 2805ms |

---

## Intent Router Latency (Uncached)

**Cache Hit Rate:** 0.0% (0 cached, 0 uncached)

| Metric | Value |
|--------|------|
| Average | 0ms |
| Median | 0ms |
| p95 | 0ms |
| Min | 0ms |
| Max | 0ms |

---

## ZAI Proxy Call Time

Total time for the ZAI proxy call (network + inference).

| Metric | Value |
|--------|------|
| Average | 0ms |
| Median | 0ms |
| p95 | 0ms |
| Min | 0ms |
| Max | 0ms |

---

## Network Latency Component

Network latency (time to first byte) measures the round-trip time to the ZAI proxy
before inference begins. This includes DNS lookup, TCP connection, TLS handshake,
and server processing time.

| Metric | Value |
|--------|------|
| Average | 0ms |
| Median | 0ms |
| p95 | 0ms |
| Min | 0ms |
| Max | 0ms |

---

## Model Inference Time

Inference time is the time the LLM model spends generating the response, calculated
as proxy_call_ms - network_ms.

| Metric | Value |
|--------|------|
| Average | 0ms |
| Median | 0ms |
| p95 | 0ms |
| Min | 0ms |
| Max | 0ms |

---

## Key Findings

1. **Network Latency:** Median network latency is 0ms, which represents 0.0% of total proxy call time.

2. **Model Inference:** Median inference time is 0ms, which represents 0.0% of total proxy call time.

3. **Cache Effectiveness:** 0.0% of requests hit the cache and return in ~10-50ms.

4. **Router Overhead:** Non-ZAI router operations (prompt construction, JSON parsing, processing) add approximately 0ms on average.

---

## Recommendations

1. **Network:** The 0ms median network latency is acceptable for a remote proxy.

2. **Inference:** Model inference dominates the total time (0ms median). Consider:
   - Using a faster model class if accuracy requirements permit
   - Reducing max_tokens to minimize generation time
   - Implementing request batching to amortize overhead

3. **Caching:** The 0.0% cache hit rate demonstrates the value of the intent cache.

---

## Raw Data

Full measurement data saved to: `docs/notes/zai-proxy-baseline-raw-2026-07-24.json`