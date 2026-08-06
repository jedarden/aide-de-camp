# Component Library Adoption Investigation - Findings

## Task: Investigate low component-library adoption (2 components for 376 results)

## Executive Summary

The component library system is **fundamentally broken**. The hot-path renderer is not being invoked for the majority of results, causing 70.5% of results to fall through to generic topic card rendering instead of using component-library matching or the fallback card system.

## Data Analysis

### Database State (as of investigation)
- **Total results**: 376
- **Total components**: 2 (pod-status: 0 usage, status: 5 usage count)
- **Total component usage patterns**: 1 (status → comp-6ebcd2a2538b, match_score: 0.8, sample_count: 5)
- **Card cache entries**: 0 (should have 88+ if components were actually being used)

### Rendering Path Distribution

| Path | Count | Percentage | Description |
|------|-------|------------|-------------|
| **generic_topic** | 265 | 70.5% | ⚠️ ANOMALY: card_fallback=0 but NO matching pattern |
| **component_library** | 88 | 23.4% | ✅ Legitimate component matches |
| **fallback** | 23 | 6.1% | ✅ Explicit fallback card usage |

### Result Type Breakdown

| result_type | Total | component_library | fallback | generic_topic |
|-------------|-------|-------------------|----------|---------------|
| `default` | 158 | 0 | 0 | **158 (100%)** |
| `<NULL>` | 93 | 0 | 0 | **93 (100%)** |
| `status` | 88 | **88 (100%)** | 0 | 0 |
| `status:test-storage-verification` | 7 | 0 | 0 | **7 (100%)** |
| `status:aide-de-camp` | 6 | 0 | **6 (100%)** | 0 |
| `lookup:logs:general` | 5 | 0 | **5 (100%)** | 0 |

## The Core Anomaly

**265 results have `card_fallback=0` but NO matching `component_usage_patterns` entry.**

According to the intended design (src/render/hot_path.py):
1. Hot-path renderer is called for each result
2. It queries `component_usage_patterns` for a match
3. If match found (score >= 0.7): set `card_fallback=0`, cache card, record usage
4. If NO match found: set `card_fallback=1`, render fallback HTML

**The anomaly**: 265 results have `card_fallback=0` without matching patterns, meaning:
- They never went through the hot-path renderer, OR
- The hot-path renderer has a bug setting `card_fallback=0` by default, OR
- There's an alternative code path setting `card_fallback=0` without component matching

## Root Cause Analysis

### 1. Hot-Path Renderer Not Invoked

**Evidence**:
- 265 results with `card_fallback=0` but no patterns
- Empty card_cache (0 entries) despite 88 "component-rendered" results
- Component usage_count is only 5 despite 88 status results

**Conclusion**: The hot-path renderer (src/render/hot_path.py) is likely NOT being called for most results. Instead, results are getting `card_fallback=0` via a different code path and falling through to generic topic card rendering in canvas.js (lines 120-174).

### 2. UI-Regen Agent is Dead Code

**Evidence**:
- Only 2 components ever created (one with 0 usage)
- No components created for 265 generic-rendered results
- Component usage patterns not being learned/recorded

**Conclusion**: The UI-regen agent (src/agents/ui_regen.py) is effectively dead code on the hot path. It's supposed to:
- Find or create components for novel result shapes
- Generate purpose-built templates via LLM
- Iterate components based on feedback

But it's rarely/never being invoked, so the component library remains stagnant.

### 3. Result Type Derivation Issues

**Evidence**:
- 93 results with `result_type=''` (empty string, not NULL)
- 158 results with `result_type='default'`

**Conclusion**: The `derive_result_type()` function in hot_path.py may not be called consistently, or there's a bug where result_type is not being set correctly for many results.

## Why This Matters

The plan describes a two-tier rendering system:
1. **Hot path** (deterministic, no LLM): Match existing components via usage patterns
2. **Cold path** (LLM-driven): UI-regen agent generates new components for novel shapes

**Current reality**: Neither path is working for 70.5% of results. They fall through to generic topic card rendering, which:
- Provides no specialized visualization
- Cannot learn from usage patterns
- Cannot improve over time
- Defeats the purpose of the component library

## Recommendations

### Immediate Actions

1. **Add comprehensive logging** to trace the rendering flow:
   - Log hot-path renderer invocations (hot_path.py)
   - Log intent router render calls (intent/router.py)
   - Log canvas rendering decisions (canvas.js)

2. **Investigate the code flow**:
   - Find where `card_fallback=0` is set without component matching
   - Trace `derive_result_type()` calls to ensure result_type is set
   - Identify if there's an alternative code path bypassing the renderer

3. **Fix the hot-path renderer**:
   - Ensure it's actually called for ALL results
   - Fix any bugs where `card_fallback` is set incorrectly
   - Ensure card_cache and usage stats are written correctly

### Long-term Actions

1. **Revive UI-regen agent**:
   - Ensure it's invoked for novel result shapes
   - Enable component generation for the 265 generic-rendered results
   - Build component usage patterns from historical data

2. **Improve result type derivation**:
   - Fix the empty/default result_type issues
   - Ensure `derive_result_type()` is called consistently
   - Add validation to catch missing/invalid result_types

3. **Consider architectural changes**:
   - Should card_fallback default to 1 (requiring explicit component match)?
   - Should there be explicit "generic" rendering option?
   - Should the hot-path renderer be mandatory for all results?

## Conclusion

**The UI-regen agent is NOT dead code on the hot path—it's dead code because there's no hot path for 70.5% of results.**

The component library system needs fundamental fixes:
1. Ensure hot-path renderer is invoked for all results
2. Fix card_fallback setting logic
3. Revive UI-regen agent to generate components for novel shapes
4. Build proper usage patterns from historical data

Until these fixes are made, Phase 2's "component library: UI-regen agent generates first components from actual result shapes" should NOT be marked COMPLETE—the system is not working as designed.

## Files Created for Investigation

1. `investigate_component_adoption.py` - Database analysis script
2. `analyze_historical_rendering_paths.py` - Historical rendering path classifier
3. `add_render_logging.py` - (NOT APPLIED) Logging addition script
4. `notes/adc-5uds-findings.md` - This comprehensive findings document
