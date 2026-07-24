# ZAI Proxy Optimization Results

**Report Date:** 2026-07-24
**Optimizations Deployed:** HTTP/2 support, Connection Pooling
**Analysis Type:** Post-optimization validation
**Sample Count:** 445 good router calls (out of 574 total)

---

## Executive Summary

The ZAI proxy latency optimizations (HTTP/2 support and connection pooling) were deployed on 2026-07-24. Post-optimization measurements show **latency increased by 32%** rather than the targeted 20-30% reduction. The median router time increased from 2317ms to 3060ms.

---

## Deployment Timeline

| Time (UTC) | Event |
|------------|-------|
| 05:02:45 | Intent router timing instrumentation verified (adc-2ksq1) |
| 05:35:15 | **Baseline established** - 88 samples, median 2317ms (adc-2woc6) |
| 05:49:02 | HTTP/2 support implemented |
| 06:03:56 | Connection pooling implemented |
| 08:02:49 | Post-optimization data collection begins |

---

## Comparison: Baseline vs Post-Optimization

### Intent Router Total Time

| Metric | Baseline | Post-Opt | Change |
|--------|----------|----------|--------|
| Count | 88 samples | 445 samples | +405 samples |
| Median | 2317ms | 3060ms | **+32%** ❌ |
| Average | 2634ms | 3321ms | **+26%** ❌ |
| p95 | 5636ms | 6437ms | +14% |
| p99 | 7808ms | 7937ms | +2% |

### ZAI Proxy Call Time

| Metric | Baseline | Post-Opt | Change |
|--------|----------|----------|--------|
| Median | 2317ms | 3060ms | **+32%** ❌ |
| Average | 2634ms | 3321ms | **+26%** ❌ |
| p95 | 5636ms | 6437ms | +14% |

### Network Latency Component

| Metric | Baseline | Post-Opt | Change |
|--------|----------|----------|--------|
| Median | 122ms | 117ms | **-4%** ✅ |
| Average | 1186ms | 119ms | **-90%** ✅ |
| p95 | 3935ms | 125ms | **-97%** ✅ |

### Model Inference Time

| Metric | Baseline | Post-Opt | Change |
|--------|----------|----------|--------|
| Median | 1338ms | 2944ms | **+120%** ❌ |
| Average | 1449ms | 3201ms | **+121%** ❌ |
| p95 | 4356ms | 6320ms | +45% |

---

## Key Findings

### What Worked

1. **Network Latency Improved:** Median network latency decreased from 122ms to 117ms (-4%), and average network latency dropped from 1186ms to 119ms (-90%). The p95 network latency improved dramatically from 3935ms to 125ms (-97%), indicating the connection pooling and HTTP/2 successfully eliminated most network outliers.

2. **Consistent Network Performance:** Post-optimization network latencies are tightly clustered between 113-129ms, with a p95 of only 125ms. This is a significant improvement over the baseline's highly variable network times.

### What Didn't Work

1. **Overall Latency Increased:** Despite network improvements, total router latency increased by 32% (median: 2317ms → 3060ms). This is the opposite of the targeted 20-30% reduction.

2. **Inference Time Doubled:** Model inference time increased by 120% (median: 1338ms → 2944ms). This suggests either:
   - The model endpoint is under heavier load post-deployment
   - The model version changed
   - Different prompts or complexity
   - Measurement artifact (see below)

3. **Target Missed:** The goal of 20-30% latency reduction was not achieved. Instead, we saw a 32% increase.

---

## Data Quality Issues

The post-optimization dataset contained 574 total records, of which:

- **445 good records** (78%) - Valid timing measurements
- **129 broken records** (22%) - Corrupted timing data

Timing corruption started at 09:28:42, where network time ≈ call time (99.9%) and inference time dropped to ~2ms. These records were excluded from analysis.

---

## Possible Causes for Latency Increase

1. **Model Endpoint Load:** The ZAI proxy may be under heavier load during the post-optimization measurement period (08:02-09:28) compared to the baseline period (pre-05:35).

2. **Model Version Change:** The model endpoint may have been upgraded or changed between baseline and post-optimization measurements.

3. **Different Query Patterns:** The post-optimization period may have included more complex queries that require longer inference time.

4. **Upstream Issues:** The ZAI proxy itself may have been experiencing performance issues unrelated to HTTP/2 or connection pooling.

5. **Client-side Changes:** The optimization code may have introduced unintended side effects that increased overall latency despite network improvements.

---

## Router Overhead Breakdown (Post-Optimization)

Non-ZAI router operations: prompt construction, JSON parsing, and intent processing.

| Component | Median | p95 |
|-----------|--------|-----|
| Prompt Construction | 0.19ms | 0.22ms |
| JSON Parsing | 0.02ms | 0.04ms |
| Intent Processing | 0.02ms | 0.04ms |

Router overhead remains negligible (~0.23ms median), consistent with baseline.

---

## Recommendations

1. **Investigate Inference Increase:** The 120% increase in inference time is the primary concern. This needs investigation at the ZAI proxy level to determine if model load, version, or configuration changed.

2. **Separate Network from Model:** While network optimizations succeeded (dramatically reduced p95 network latency), the overall goal failed because model inference time dominates total latency. Future optimizations should focus on model-side improvements.

3. **Cache Expansion:** Consider expanding the intent cache or implementing smarter cache keys to reduce overall call volume. The baseline showed a 12% cache hit rate; post-optimization cache statistics were not analyzed.

4. **Timing Instrumentation Fix:** The timing corruption at 09:28:42 indicates a bug in the measurement code. This should be fixed before future measurements.

5. **Consider Faster Model:** Given that inference now accounts for 96% of total latency (2944ms / 3060ms), consider using a faster model class (e.g., Haiku) or optimizing prompts to reduce processing time.

---

## Conclusion

The HTTP/2 and connection pooling optimizations **successfully improved network latency** (median -4%, average -90%, p95 -97%), but **overall latency increased by 32%** due to a 120% increase in model inference time. The network improvements were overshadowed by degradation in model-side performance.

**Status:** Target not achieved ❌
**Goal:** 20-30% latency reduction
**Actual:** 32% latency increase

---

## Data Source

Baseline: 88 router timing records collected before 05:35:15 on 2026-07-24.
Post-optimization: 445 good router timing records collected 08:02-09:28 on 2026-07-24, from `data/session.db`.

---

**Generated:** 2026-07-24
