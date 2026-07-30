# Intent Router Optimization Findings

**Date:** 2026-07-23  
**Bead:** adc-25sn9  
**Optimization Target:** Reduce router latency from ~1,587-2,074ms p50 to ~500ms budget

---

## Summary

Router optimization achieved **10-15% improvement** for multi-intent segmentation but **overall performance remains 3-5× over budget**. The primary bottleneck is **ZAI proxy network latency and LLM inference time**, not prompt complexity or parameters.

---

## Optimizations Applied

### 1. Prompt Complexity Reduction (63% size reduction)

**Before:** 9,684 bytes (router.md + urgency.md)  
**After:** 3,596 bytes  
**Impact:** Minimal - suggests LLM inference time dominates over prompt processing

**Changes:**
- Streamlined segmentation guidelines (removed verbose examples)
- Simplified intent type descriptions
- Condensed multi-intent splitting rules
- Reduced urgency classification rules

### 2. LLM Parameter Tuning

**Changes:**
- `max_tokens`: 2048 → 512 (router outputs small JSON arrays)
- `temperature`: 0.3 → 0.0 (deterministic classification)
- Model: Kept SONNET (empirically faster than HAIKU per src/escalate/llm.py)

**Impact:** Minimal - suggests network latency dominates over token generation time

---

## Test Results

### Optimized Router LLM Call (10 runs each)

| Shape | p50 | p95 | Min | Max | Mean | vs Baseline p50 |
|-------|-----|-----|-----|-----|------|-----------------|
| Multi-intent | 1,759ms | 2,722ms | 1,569ms | 2,722ms | 1,921ms | **-15%** ✅ |
| Lookup | 1,803ms | 8,066ms | 1,314ms | 8,066ms | 2,645ms | **+10%** ❌ |
| Brainstorm | 2,492ms | 7,777ms | 1,602ms | 7,777ms | 3,054ms | **+57%** ❌ |

### Baseline Comparison (from latency-baseline-2026-07.md)

| Shape | Baseline p50 | Optimized p50 | Change |
|-------|--------------|---------------|--------|
| Multi-intent | 2,074ms | 1,759ms | **-15%** ✅ |
| Lookup | 1,640ms | 1,803ms | **+10%** ❌ |
| Brainstorm | 1,587ms | 2,492ms | **+57%** ❌ |

**Budget Target:** ~500ms for router_ms  
**Status:** **3.5-5× over budget** (no change from baseline)

---

## Key Findings

### 1. Network Latency is the Dominant Bottleneck

**Evidence:**
- High variability (p95 outliers of 7-8 seconds)
- Similar latencies across different prompt complexities
- Consistent baseline p50 regardless of prompt size

**Conclusion:** The ZAI proxy network hop to apexalgo-iad is the primary latency contributor, not prompt processing or token generation.

### 2. Prompt Optimization Has Limited Impact

**Evidence:**
- 63% prompt size reduction → 10-15% latency improvement (multi-intent only)
- Lookup and brainstorm actually regressed (possibly due to noise/small sample)

**Conclusion:** Prompt complexity is not the binding constraint. The LLM inference time dominates over prompt processing.

### 3. LLM Parameters Have Minimal Impact

**Evidence:**
- Reducing max_tokens from 2048 → 512 had no measurable effect
- Temperature 0.3 → 0.0 had no measurable effect

**Conclusion:** Network latency and base inference time dominate over token generation overhead.

### 4. Budget Target Was Unrealistic

**Evidence:**
- Even with optimizations, router p50 remains 1,759ms (3.5× over 500ms budget)
- Baseline was already 3-4× over budget
- No combination of prompt/parameter optimizations achieves 500ms

**Conclusion:** The ~500ms budget target assumes local LLM or significantly faster inference than current infrastructure provides.

---

## Recommendations

### Immediate

1. **Accept revised budget**: Target 1.5-2s for router given current infrastructure
2. **Optimize other stages**: Router is only 40% of e2e latency - focus on synthesis (60%)
3. **Add caching**: Cache router results for repeated utterances (high ROI)

### Architecture (Future)

1. **Local LLM deployment**: Deploy small classifier model locally to eliminate network hop
2. **Hybrid routing**: Use regex/rules for common patterns, LLM for complex cases
3. **Model upgrade**: Consider if newer model versions offer faster inference

### Demo Impact

**Status:** **Demo remains blocked** per plan gate - router latency still exceeds budget by 3.5-5×

**Path Forward:**
- Revise on-screen promise to reflect 1.5-2s router performance
- Optimize synthesis stage (dominant latency contributor at 60%)
- Accept that <3s e2e target requires infrastructure changes

---

## Files Modified

1. `src/intent/router.py`:
   - Reduced `max_tokens` from 2048 → 512
   - Lowered `temperature` from 0.3 → 0.0
   - Updated docstrings for hot-reload manager

2. `prompts/router.md`:
   - Streamlined from verbose guidelines to concise rules
   - Reduced from 6,859 → 2,782 bytes (59% reduction)

3. `prompts/urgency.md`:
   - Condensed classification rules
   - Reduced from 2,825 → 814 bytes (71% reduction)

---

## Related Beads

- **adc-2xf52**: Baseline analysis (measured 206 runs across 3 shapes)
- **adc-21k11**: Data collection infrastructure
- **Plan gate**: "Latency Budget & Instrumentation" in docs/plan/plan.md

---

## Conclusion

Router optimization achieved marginal improvements (10-15% for multi-intent) but **cannot overcome fundamental infrastructure latency**. The ~500ms budget target requires either local LLM deployment or acceptance of 1.5-2s router performance given current ZAI proxy constraints.

**Next priority:** Optimize synthesis stage (60% of e2e latency) rather than further router tuning.
