# Router Latency Compliance Analysis

**Task:** adc-1gqcg  
**Date:** 2026-07-24  
**Analysis Source:** Latency baseline measurements from 2026-07-24

## Budget Requirements

- **p50:** < 500ms
- **p95:** < 1500ms

## Current Performance vs Budget

### Most Recent Baseline (20260724_070617.json)
- **Sample Size:** 20 router timing records
- **p50:** 1408ms (281% of budget, **+908ms over**)
- **p95:** 2563ms (171% of budget, **+1063ms over**)
- **Min:** 1042ms (still 208% of budget)
- **Max:** 2563ms
- **Mean:** 1434.3ms
- **Median:** 1374.5ms

### Previous Baseline (20260724_065509.json)
- **Sample Size:** 142 router timing records
- **p50:** 1896ms (379% of budget, **+1396ms over**)
- **p95:** 4118ms (275% of budget, **+2618ms over**)
- **Min:** 1037ms
- **Max:** 11095ms
- **Mean:** 2293.7ms
- **Median:** 1877.5ms

## Compliance Status

### ❌ **NON-COMPLIANT** - Both Metrics Exceed Budget

| Metric | Budget | Current (Latest) | Status | Over Budget |
|--------|--------|------------------|---------|-------------|
| p50 | < 500ms | 1408ms | ❌ FAIL | +908ms (+181%) |
| p95 | < 1500ms | 2563ms | ❌ FAIL | +1063ms (+71%) |

## Key Findings

1. **Severe p50 Violation:** The median router latency (1408ms) is nearly 3x the budget target of 500ms.

2. **Severe p95 Violation:** The 95th percentile latency (2563ms) exceeds the budget by 71%.

3. **No Records Within Budget:** Even the minimum recorded router latency (1042ms) exceeds the p50 budget by 108%.

4. **High Variance:** The router shows significant variance (range: 1042ms-11095ms), indicating potential performance instability.

5. **Trend Direction:** The smaller dataset (20 records) shows slightly better performance than the larger dataset (142 records), but still far exceeds budget.

## Router Component Analysis

The baseline data does not break down router latency into sub-phases (e.g., LLM call time vs. JSON parsing vs. intent classification). The entire router operation includes:

- LLM intent classification call to ZAI proxy
- JSON response parsing (GLM-4.7 wraps responses in markdown fences)
- Intent type determination and command selection
- Fetch strategy setup

**Recommendation:** Future measurements should instrument router sub-phases to identify the specific bottleneck (LLM call vs. parsing vs. logic).

## Comparison to Other Pipeline Phases

For context, other pipeline phases in the latest baseline:
- **Fetch First Source:** p50: 62ms, p95: 81ms (✅ appears compliant)
- **Escalate:** p50: 9205ms (only applies to task-profile intents)

The router is the clear bottleneck in the pipeline, taking 22x longer than fetch operations.

## Conclusion

**Router latency is critically non-compliant with budget targets.** Both p50 and p95 metrics significantly exceed their budgets, with no recorded measurements falling within acceptable ranges. The router requires optimization before it can meet latency budget requirements.

### Recommended Actions

1. **Profile router sub-phases** to identify the specific bottleneck (LLM call vs. JSON parsing vs. logic)
2. **Investigate LLM response times** to ZAI proxy - network latency or model response time may be the root cause
3. **Optimize JSON parsing** - GLM-4.7 markdown fence stripping overhead should be measured
4. **Consider prompt optimization** - current intent classification prompt may be unnecessarily complex
5. **Evaluate router caching** - repeated utterances or common patterns might benefit from caching
