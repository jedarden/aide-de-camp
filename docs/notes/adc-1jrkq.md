# Latency Budget Verification (adc-1jrkq)

**Bead:** adc-1jrkq
**Date:** 2026-07-24
**Task:** Verify latency budget compliance and document results
**Status:** ❌ BUDGET COMPLIANCE FAILED

## Acceptance Criteria Verification

| Criterion | Target | Measured | Status |
|-----------|--------|----------|--------|
| Router p50 latency | < 500ms | **2,642ms** | ❌ FAIL (5.3× over) |
| Router p95 latency | < 1,500ms | **6,437ms** | ❌ FAIL (4.3× over) |
| Baseline documented | docs/notes/latency-baseline-2026-07.md | Complete | ✅ PASS |
| Demo gate status | Based on measured performance | "DEMO BLOCKED" | ✅ PASS (correctly blocked) |

## Key Findings

1. **Router Latency Dominates Bottleneck:**
   - ZAI proxy inference time: ~1,449-1,875ms per call
   - Network overhead: ~116ms per call
   - Total router time: 2,642ms p50, 6,437ms p95

2. **Fetch Performance Excellent:**
   - p50: 43ms (10× headroom against 500ms budget)
   - p95: 97ms (15× headroom)

3. **Optimizations in adc-1kp7n Insufficient:**
   - Prompt simplification, max_tokens reduction, and caching did not achieve target reduction
   - Performance has actually degraded compared to adc-2xf52 baseline
   - Router latency increased by 28-67% for p50, 50-155% for p95

## Demo Gate Status

**Gate: DEMO BLOCKED** ❌

The plan.md gate criteria explicitly require:
> "The demo cannot be scheduled until the Measured p50/p95 columns are filled from real runs. If measured p95 blows a stage's budget, either the stage gets fixed or the on-screen promise changes."

Measured performance clearly blows the budget:
- p50: 2,642ms vs 500ms target
- p95: 6,437ms vs 1,500ms target
- End-to-end: ~5,700-7,700ms vs <3s promise

Per gate criteria, the demo cannot proceed until either:
1. Router latency is reduced to meet budget targets, OR
2. The on-screen promise is changed to reflect actual performance

## Documentation

- Full analysis: `docs/notes/latency-baseline-2026-07.md`
- Live server data: 649 samples from `/api/v1/timings/percentiles`
- Plan.md gate status: Updated to reflect DEMO BLOCKED based on measured performance

## Conclusion

The latency optimization work (adc-1kp7n) did not achieve the budget targets. The system operates well outside acceptable latency ranges for demo purposes. The gate status is correctly set to "DEMO BLOCKED" in plan.md, which aligns with the measured performance data.

**Next Steps (if unblocking demo):**
- Investigate ZAI proxy latency (why is inference consistently 1.4-1.9s?)
- Evaluate faster LLM model options
- Consider local inference or alternative LLM providers
- Or change on-screen promise from "<3s" to reflect actual performance
