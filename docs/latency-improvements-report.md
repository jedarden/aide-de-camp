# Latency Improvements Report (adc-emkv3)

**Date:** 2026-07-24  
**Baseline Comparison:** adc-2xf52 (2026-07-23)  
**Optimization Work:** adc-1kp7n intent router optimizations (2026-07-24)

## Executive Summary

The intent router optimization work yielded **mixed results** with significant variations across different utterance shapes. While some shapes showed improvements in tail latency (p95), most shapes experienced regressions in median latency (p50).

**Key Finding:** The optimizations did not deliver consistent performance improvements across all use cases, suggesting the need for further investigation and refinement.

---

## Baseline vs. Optimized Results

### Intent Router Latency Comparison

| Shape | Metric | Baseline (ms) | Optimized (ms) | Change | % Change |
|-------|--------|---------------|----------------|--------|----------|
| **Multi-intent** | p50 | 2,074 | 2,194 | +120 | +5.8% |
| **Multi-intent** | p95 | 4,188 | 2,807 | **-1,380** | **-33.0%** |
| **Lookup** | p50 | 1,640 | 2,899 | +1,259 | +76.8% |
| **Lookup** | p95 | 3,297 | 2,919 | **-378** | **-11.5%** |
| **Brainstorm** | p50 | 1,587 | 2,899 | +1,312 | +82.7% |
| **Brainstorm** | p95 | 2,487 | 3,087 | +600 | +24.1% |

### Summary by Shape

#### Multi-intent Queries
- **p50:** INCREASED by 5.8% (2,074 → 2,194ms)
- **p95:** DECREASED by 33.0% (4,188 → 2,807ms) ✅
- **Assessment:** Trade-off between median and tail latency

#### Lookup Queries  
- **p50:** INCREASED by 76.8% (1,640 → 2,899ms) ❌
- **p95:** DECREASED by 11.5% (3,297 → 2,919ms) ✅
- **Assessment:** Significant median regression with modest tail improvement

#### Brainstorm Queries
- **p50:** INCREASED by 82.7% (1,587 → 2,899ms) ❌
- **p95:** INCREASED by 24.1% (2,487 → 3,087ms) ❌
- **Assessment:** Complete regression across all metrics

---

## Optimizations Implemented (adc-1kp7n)

The following optimizations were implemented and enabled during testing:

1. **Simplified router prompt** (28 lines → 24 lines)
2. **Reduced max_tokens** (128 → 96, 25% reduction)
3. **Enhanced caching strategy** (15min TTL, 1000 max entries)
4. **HTTP connection pooling** (keepalive enabled)
5. **Aggressive timeout** (8s router timeout)
6. **Temperature 0.0** (deterministic responses)

---

## Analysis

### Positive Outcomes

1. **Tail Latency Improvements:** Both multi-intent and lookup shapes showed p95 improvements, suggesting the optimizations may help with outlier cases.

2. **Consistency:** Reduced variance in multi-intent queries (p95 improvement of 33%) indicates more predictable performance for complex queries.

### Negative Outcomes

1. **Median Latency Regressions:** Significant p50 increases across lookup (76.8%) and brainstorm (82.7%) shapes indicate the optimizations hurt typical case performance.

2. **Brainstorm Performance:** Complete regression on brainstorm queries suggests the optimizations may be particularly unsuitable for synthesis-heavy workloads.

3. **Inconsistent Results:** The mixed performance across shapes suggests the optimizations may have different impacts depending on query complexity and type.

### Potential Root Causes

1. **Cache Effectiveness:** The expected 15-20% cache hit rate improvement may not have materialized, potentially due to insufficient conversation repetition in testing.

2. **Connection Pooling Overhead:** HTTP connection pooling may add latency for single-shot requests where connection reuse doesn't occur.

3. **Prompt Simplification:** Reducing prompt complexity may have increased inference time by requiring more model processing.

4. **max_tokens Reduction:** The 25% reduction in max_tokens may have forced more retries or refills for complex responses.

---

## Budget Compliance Status

**Target Budgets:**
- p50: < 500ms
- p95: < 1,500ms

**Current Status:** ❌ **FAILING** - All shapes exceed both p50 and p95 budgets significantly

| Shape | p50 Status | p95 Status |
|-------|------------|------------|
| Multi-intent | 4.4× over budget | 1.9× over budget |
| Lookup | 5.8× over budget | 1.9× over budget |
| Brainstorm | 5.8× over budget | 2.1× over budget |

---

## Recommendations

### Immediate Actions

1. **Investigate Cache Performance:** Measure actual cache hit rates during testing to verify the caching strategy is working as intended.

2. **Profile by Shape:** Analyze why different query shapes respond differently to the optimizations.

3. **Revert Select Optimizations:** Consider reverting optimizations that show clear negative impact (e.g., for brainstorm queries).

### Long-term Improvements

1. **Shape-Specific Tuning:** Apply different optimization strategies based on query type rather than a one-size-fits-all approach.

2. **Adaptive Caching:** Implement cache warming and smarter cache key generation for better hit rates.

3. **Infrastructure Investigation:** The consistent 2-3s latency suggests external factors (ZAI proxy, network) may be the primary bottleneck.

---

## Data Sources

**Baseline:** `/home/coding/aide-de-camp/data/parsed/stage_percentiles.json` (adc-2xf52)  
**Optimized:** `/tmp/e2e-latency-test-results.json` (adc-3mtb1, 2026-07-24T08:20:41)

**Test Configuration:**
- 30 runs per shape
- Server: localhost:8000 (adc-voice)
- All adc-1kp7n optimizations enabled

---

## Conclusion

The intent router optimization work delivered **mixed results** that do not clearly demonstrate improvement over baseline performance. While some tail latency metrics improved, the significant median latency regressions across most shapes suggest the optimizations require further refinement before they can be considered successful.

The system continues to operate **well outside latency budget targets**, indicating that additional optimization work is needed beyond the current implementation.

**Status:** ⚠️ **INCONCLUSIVE** - Further investigation and optimization iteration required
