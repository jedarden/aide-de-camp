# Bead adc-5ktmz: Integrate cache into classify() flow

## Task Verification

This bead requested integration of the in-memory cache into the `classify_utterance()` flow in `src/intent/router.py`. Upon verification, **all acceptance criteria have already been implemented** in prior work (beads adc-3aa19, adc-2qhmb, and adc-4a3kd).

## Acceptance Criteria Status

✅ **All criteria met:**

1. **Modify `classify_utterance()` in src/intent/router.py**
   - Lines 419-437: Cache check on entry, immediate return on hit
   - Lines 565-566: Cache storage after successful classification

2. **On entry: generate cache key, check cache.get(key)**
   - Line 420: `cached_result = self._get_cached_classification(utterance, session_id)`
   - Uses `generate_cache_key()` method (lines 305-332)

3. **Cache hit: return cached intent_mapping immediately (skip ZAI proxy)**
   - Lines 421-437: Returns cached result with empty timing breakdown
   - No ZAI proxy call made on cache hit

4. **Cache miss: proceed to ZAI proxy, then cache.set(key, result)**
   - Lines 468-529: Full ZAI proxy call and response processing
   - Line 566: `self._cache_classification(utterance, session_id, classifications)`

5. **Cache stores the full intent_mapping dict**
   - Stores `list[IntentClassification]` including intent_type, confidence, reasoning, urgency, project_slug, etc.

6. **Cache miss path logs timing breakdown correctly**
   - Lines 533-547: Detailed timing logging for all stages
   - Lines 553-563: Complete timing_breakdown dict for storage

7. **Integration test: repeated utterance hits cache**
   - `tests/test_intent_classification.py::TestRouterCacheBehavior::test_cache_hit_skips_zai_call`
   - Test verified passing with `pytest` (no second ZAI call on cache hit)

## Implementation Summary

The cache integration uses:
- **IntentCache class**: In-memory TTL-based cache (300s default, 1000 entry max)
- **SHA256 cache keys**: Generated from `utterance + session_id`
- **Cache hit path**: Returns cached classifications with `total_ms=0`, `cached=True`
- **Cache miss path**: Full ZAI proxy call with detailed timing, then stores result
- **Statistics tracking**: Hits/misses logged every 50 operations

## Test Results

```bash
$ pytest tests/test_intent_classification.py::TestRouterCacheBehavior::test_cache_hit_skips_zai_call -xvs
============================= test session starts ==============================
tests/test_intent_classification.py::TestRouterCacheBehavior::test_cache_hit_skips_zai_call PASSED
============================== 1 passed in 0.06s ===============================
```

All cache integration functionality verified working correctly.

## Dependencies Satisfied

Depends on bead `adc-3aa19` (Implement in-memory cache store with TTL) - **completed**
