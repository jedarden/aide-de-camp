# Synthesis Latency Optimization — adc-1btyk

## Problem
Synthesis latency exceeded budget by 2-3×:
- p50: 3,108-3,984ms (budget: ~1-2s)
- p95: 4,663-7,877ms (4.7-7.9× over budget)
- Accounts for ~60% of end-to-end latency
- Demo-blocker per plan gate

## Changes Implemented

### 1. Model Selection (Biggest Win)
**Changed**: `ModelClass.SONNET` → `ModelClass.HAIKU`
**Expected Impact**: 50-70% latency reduction
- Haiku is significantly faster than Sonnet
- Sufficient for synthesis tasks (data structuring, not creative generation)
- Lower cost per invocation

### 2. Token Limit Reduction
**Changed**: `max_tokens: 4096` → `max_tokens: 1024`
**Expected Impact**: 20-30% reduction in generation time
- Most synthesis outputs are < 1024 tokens
- Prevents unnecessary generation time
- Fail-fast if output exceeds expected size

### 3. Temperature Optimization
**Changed**: `temperature: 0.5` → `temperature: 0.3`
**Expected Impact**: 5-10% reduction in latency
- Lower temperature = more deterministic outputs
- Faster convergence on structured data
- Maintains consistency for synthesis

### 4. Prompt Optimization
**Changed**: Rewrote `prompts/synthesize.md`
**Expected Impact**: 10-15% reduction in input processing
- Reduced prompt length by ~40%
- Removed redundant examples
- Kept essential instructions only
- More concise = faster processing

## Expected Performance Improvement

**Conservative Estimate** (assuming multiplicative effects compound):
- Model switch: 50% reduction
- Token limit: 25% reduction on remaining
- Temperature: 7% reduction on remaining
- Prompt: 12% reduction on remaining

**Calculated**: 3,500ms × 0.5 × 0.75 × 0.93 × 0.88 ≈ **1,080ms p50**

**Optimistic Estimate** (if effects are additive):
- 3,500ms - 1,750ms (model) - 875ms (tokens) - 350ms (temp+prompt) ≈ **525ms p50**

**Realistic Expected Range**: 1,000-1,500ms p50

This would bring synthesis within or very close to the ~1-2s budget.

## Testing Required

1. Run latency baseline collection again with same test shapes
2. Compare p50/p95 synthesis times against adc-2xf52 baseline
3. Verify output quality is maintained with Haiku
4. Check if max_tokens=1024 is sufficient for all intents

## Follow-up Optimizations (if needed)

If still over budget after these changes:
1. Implement streaming for faster first-token time
2. Consider request batching for multi-intent dispatches
3. Add caching for repeated synthesis patterns
4. Explore even more aggressive prompt reduction

## Files Modified
- `src/synthesize/strand.py`: Model, max_tokens, temperature
- `prompts/synthesize.md: Complete rewrite for brevity

## Related Beads
- Baseline analysis: adc-2xf52
- Plan gate: docs/plan/plan.md → "Latency Budget & Instrumentation"
