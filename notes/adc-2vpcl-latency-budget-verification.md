# Latency Budget Verification Report (Bead adc-2vpcl)

**Date:** 2026-07-24
**Purpose:** Verify latency budget targets from optimization work

## Budget Targets

- **p50 latency:** < 500ms (primary budget target)
- **p95 latency:** < 1,500ms (3× budget, acceptable for tail)

## Verification Results

### Summary
❌ **BUDGET VIOLATIONS DETECTED** - All test shapes significantly exceed both p50 and p95 targets.

### Detailed Results by Shape

#### MULTI-INTENT Shape
**Utterance:** "Has the pbx web caught up, and what's the state of whisper stt?"

| Metric | Measured | Target | Status | Violation |
|--------|----------|--------|--------|-----------|
| p50    | 5,459ms  | 500ms  | ❌ FAIL | 10.9× over budget |
| p95    | 8,026ms  | 1,500ms | ❌ FAIL | 5.4× over budget |

#### LOOKUP Shape  
**Utterance:** "Pull up the recent logs for whisper stt"

| Metric | Measured | Target | Status | Violation |
|--------|----------|--------|--------|-----------|
| p50    | 3,612ms  | 500ms  | ❌ FAIL | 7.2× over budget |
| p95    | 8,016ms  | 1,500ms | ❌ FAIL | 5.3× over budget |

#### BRAINSTORM Shape
**Utterance:** "Brainstorm improvements to the pbx web deployment pipeline"

| Metric | Measured | Target | Status | Violation |
|--------|----------|--------|--------|-----------|
| p50    | 3,419ms  | 500ms  | ❌ FAIL | 6.8× over budget |
| p95    | 8,007ms  | 1,500ms | ❌ FAIL | 5.3× over budget |

## Violations Summary

### Critical Issues

1. **p50 Budget Violations (All Shapes)**
   - Multi-intent: 5,459ms (10.9× over 500ms target)
   - Lookup: 3,612ms (7.2× over 500ms target)
   - Brainstorm: 3,419ms (6.8× over 500ms target)

2. **p95 Budget Violations (All Shapes)**
   - All shapes: ~8,000ms (5.3-5.4× over 1,500ms target)
   - Suggests systemic timeout issues (8-second router timeout)

### Outliers and Anomalies

1. **High Tail Latency**
   - p95 values cluster around 8 seconds across all shapes
   - Indicates requests hitting router timeout limits
   - 10% failure rate (9/90 runs) with HTTP 500 errors

2. **Large Variance**
   - Min latencies: 1,275-1,842ms (2.6-3.7× over p50 target)
   - Max latencies: 8,087-8,189ms (approaching timeout)
   - 4-6× spread between min and max values

3. **Performance Degradation**
   - Compared to July 2026 baseline: 115-163% increase in p50
   - Compared to July 2026 baseline: 87-217% increase in p95
   - Suggests infrastructure or load regression

## Root Cause Analysis

### Primary Suspects

1. **ZAI Proxy Latency**
   - Router times (2,074-2,648ms p50) dominate the dispatch latency
   - Proxy may be experiencing load or network issues
   - 8-second p95 suggests proxy-side timeouts

2. **Router Timeout Configuration**
   - Current 8-second timeout may be too permissive
   - p95 clustering at timeout ceiling suggests requests are being killed
   - No evidence of optimizations (caching, pooling) taking effect

3. **Missing Optimization Impact**
   - All adc-1kp7n optimizations were enabled during testing
   - Results suggest optimizations are not providing expected benefits
   - Cache hit rates, connection pooling effectiveness not measured

## Acceptance Criteria Status

| Criteria | Target | Measured | Status |
|----------|--------|----------|--------|
| p50 latency < 500ms | 500ms | 3,419-5,459ms | ❌ FAIL (All shapes) |
| p95 latency < 1,500ms | 1,500ms | 8,007-8,026ms | ❌ FAIL (All shapes) |
| Identify violations | Document | ✅ Complete | ✅ PASS |
| Identify outliers | Document | ✅ Complete | ✅ PASS |

## Recommendations

### Immediate Actions

1. **Investigate ZAI Proxy Health**
   - Check proxy logs for latency spikes
   - Verify network connectivity between adc and proxy
   - Test proxy directly (bypass adc) to isolate issue

2. **Cache Effectiveness Analysis**
   - Measure cache hit rates during baseline test
   - Verify cache entries are being created and retrieved
   - Check if cache TTL (15min) is appropriate for workload

3. **Reduce Router Timeout**
   - Lower timeout from 8s to 3-4s to improve tail latency
   - Implement fallback behavior for timeout scenarios
   - Consider retry logic for failed requests

### Long-term Improvements

1. **Performance Monitoring**
   - Add continuous latency monitoring
   - Alert when p50 exceeds 1s or p95 exceeds 3s
   - Track optimization impact over time

2. **Load Testing**
   - Test under various concurrency levels
   - Identify breaking points and bottlenecks
   - Validate optimization effectiveness under load

3. **Infrastructure Review**
   - Evaluate if current hardware/VM resources are adequate
   - Consider scaling options (vertical/horizontal)
   - Review network topology between adc and ZAI proxy

## Conclusion

The measured latencies **do not meet** the defined budget targets. All shapes show 6.8-10.9× p50 budget violations and 5.3-5.4× p95 budget violations. The system requires significant performance investigation and optimization before it can meet the 500ms p50 / 1,500ms p95 targets.

The consistent clustering of p95 values around 8 seconds suggests requests are hitting timeout limits, and the performance degradation compared to the July 2026 baseline indicates a regression that needs immediate attention.

## Data Source

Results based on latency baseline data from bead adc-3mtb1 (2026-07-24):
- `data/latency-baseline-shape1-20260723_170941.json`
- `data/latency-baseline-shape2-20260723_171458.json` 
- `data/latency-baseline-shape3-20260723_172011.json`
- `notes/adc-3mtb1-latency-baseline-results.md`
