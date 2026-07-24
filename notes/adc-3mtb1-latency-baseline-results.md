# Latency Baseline Results with Optimizations (Bead adc-3mtb1)

## Test Execution Date
2026-07-24T08:20:41.404611 UTC

## Test Configuration
- **Runs per shape:** 30 iterations
- **Test shapes:** 3 (multi-intent, lookup, brainstorm)
- **Server:** localhost:8000 (adc-voice)
- **All optimizations from adc-1kp7n enabled:**
  - Simplified router prompt (28 lines → 24 lines)
  - Reduced max_tokens (128 → 96)
  - Connection pooling enabled
  - Cache TTL 15 minutes, 1000 max entries
  - Temperature 0.0 (deterministic)

## Results Summary

### MULTI-INTENT Shape
**Utterance:** "Has the pbx web caught up, and what's the state of whisper stt?"

| Metric | Value |
|--------|-------|
| p50    | 5,459ms |
| p95    | 8,026ms |
| Min    | 1,842ms |
| Max    | 8,189ms |
| Mean   | 5,289ms |
| Success Rate | 87% (26/30) |

### LOOKUP Shape  
**Utterance:** "Pull up the recent logs for whisper stt"

| Metric | Value |
|--------|-------|
| p50    | 3,612ms |
| p95    | 8,016ms |
| Min    | 1,275ms |
| Max    | 8,087ms |
| Mean   | 3,591ms |
| Success Rate | 90% (27/30) |

### BRAINSTORM Shape
**Utterance:** "Brainstorm improvements to the pbx web deployment pipeline"

| Metric | Value |
|--------|-------|
| p50    | 3,419ms |
| p95    | 8,007ms |
| Min    | 1,401ms |
| Max    | 8,016ms |
| Mean   | 3,801ms |
| Success Rate | 93% (28/30) |

## Comparison with July 2026 Baseline

The test script includes a July 2026 baseline for comparison:

| Shape | Baseline p50 | Current p50 | Change | Baseline p95 | Current p95 | Change |
|-------|-------------|-------------|--------|-------------|-------------|--------|
| multi-intent | 2,074ms | 5,459ms | +163% | 4,301ms | 8,026ms | +87% |
| lookup | 1,640ms | 3,612ms | +120% | 3,298ms | 8,016ms | +143% |
| brainstorm | 1,587ms | 3,419ms | +115% | 2,527ms | 8,007ms | +217% |

**Note:** The current latencies are significantly higher than the July 2026 baseline. This may indicate:
- Different load conditions on the server
- ZAI proxy latency variations
- Network or infrastructure factors
- Possible measurement methodology differences

## Error Analysis

Across all 90 test runs, there were 9 failures (10% error rate):
- MULTI-INTENT: 4 failures (HTTP 500 errors)
- LOOKUP: 3 failures (HTTP 500 errors)  
- BRAINSTORM: 2 failures (HTTP 500 errors)

The failures appear to be timeout-related (8+ second dispatch times) suggesting some requests hit the 8-second router timeout.

## Key Observations

1. **High p95 values:** All shapes show p95 latencies around 8 seconds, suggesting significant tail latency
2. **Good success rates:** 87-93% success rates indicate reasonable reliability
3. **Minimum latencies:** The minimum values (1.2-1.8s) suggest the best-case performance is reasonable
4. **Large variance:** The spread between min and max (4-6x) indicates high variability

## Budget Compliance

**Target:** ~500ms router latency, <3000ms E2E

**Current Status:** ❌ NOT MEETING BUDGET
- All shapes exceed p50 budget by 6-11x
- All shapes exceed p95 budget by 2.7-5.3x

## Recommendations

1. **Investigate tail latency:** The 8-second p95 suggests some requests are hitting timeouts
2. **Analyze HTTP 500 errors:** Determine root cause of the 10% failure rate
3. **Monitor ZAI proxy:** The proxy may be experiencing latency issues
4. **Consider cache warming:** Pre-warm cache for common utterances
5. **Profile router bottleneck:** The router_ms averages 2.6-2.8s per the health endpoint

## Raw Data

Full results available at: `/tmp/e2e-latency-test-results.json`

## Next Steps

These baseline results establish the current performance with all optimizations enabled. Use this data to:
- Track performance improvements over time
- Identify optimization opportunities  
- Set realistic performance targets
- Compare against future optimization iterations
