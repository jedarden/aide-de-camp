# Implementation Summary: Gate Synthesis on Window Close

## Task Requirements
Ensure synthesis fires exactly once when window closes and record timing metrics.

## Acceptance Criteria Met

### 1. Synthesis Invoked Exactly Once ✅
**Implementation**: The orchestrator uses `asyncio.gather(*wrapped_tasks)` (src/fetch/orchestrator.py:164) which waits for ALL sources to complete before returning. The router calls synthesis only after fetch completes (src/intent/router.py:718), ensuring exactly one synthesis per intent.

**Test**: Added `TestSynthesisGating::test_synthesis_invoked_exactly_once_after_window_close` which mocks synthesis and tracks call counts, verifying synthesis is called exactly once and only after window close.

### 2. No Re-synthesis When Late Sources Arrive ✅
**Implementation**: Since synthesis is called once after `execute_fetch` returns, and `execute_fetch` waits for ALL sources (success/timeout/error), late/timed-out sources are included in the fetch result but do not trigger re-synthesis.

**Test**: Existing test `test_timed_out_sources_included_in_caveats` verifies timed-out sources appear only in caveats.

### 3. fetch_first_source_ms Recorded ✅
**Implementation**: Router tracks first source completion via progress callback (src/intent/router.py:612-613) and records timing (lines 630-634):
```python
if first_source_at[0] is not None:
    timings.record(
        "fetch_first_source_ms",
        timings.elapsed_ms(fetch_start, first_source_at[0]),
    )
```

**Test**: Existing test `test_fetch_first_source_ms_recorded` verifies this metric is captured.

### 4. fetch_total_ms (Window Close) Recorded ✅
**Implementation**: Router records total duration from fetch result (src/intent/router.py:629):
```python
timings.record("fetch_total_ms", fetch_result.total_duration_ms)
```

**Test**: Existing test `test_fetch_total_ms_records_window_close` verifies this metric matches window close time.

### 5. Timed-out Sources in fetch_coverage Caveats ✅
**Implementation**: Orchestrator adds timed-out sources to caveats (src/fetch/orchestrator.py:179-181):
```python
elif result.status == "timeout":
    timed_out.append(source)
    caveats.append(f"{source.value} timed out")
```

**Test**: Existing test `test_timed_out_sources_included_in_caveats` verifies timed-out sources appear in caveats.

### 6. Test Verifies No Re-synthesis ✅
**Implementation**: New test `TestSynthesisGating::test_synthesis_invoked_exactly_once_after_window_close` specifically mocks the synthesis function and tracks call count to verify exactly one invocation.

## Test Results
All fetch window policy tests pass (10/10):
```
tests/test_fetch_window_policy.py::TestFetchWindowPolicy::test_synthesis_waits_for_all_sources_to_complete PASSED
tests/test_fetch_window_policy.py::TestFetchWindowPolicy::test_slow_source_times_out_does_not_block_window_close PASSED
tests/test_fetch_window_policy.py::TestFetchWindowPolicy::test_progress_events_fire_as_sources_complete PASSED
tests/test_fetch_window_policy.py::TestFetchWindowPolicy::test_timed_out_sources_included_in_caveats PASSED
tests/test_fetch_window_policy.py::TestFetchWindowTimingMetrics::test_fetch_first_source_ms_recorded PASSED
tests/test_fetch_window_policy.py::TestFetchWindowTimingMetrics::test_fetch_total_ms_records_window_close PASSED
tests/test_fetch_window_policy.py::TestFetchProgressSSEBroadcast::test_progress_events_broadcast_via_sse PASSED
tests/test_fetch_window_policy.py::TestSynthesisGating::test_synthesis_invoked_exactly_once_after_window_close PASSED ✅ NEW
tests/test_fetch_window_policy.py::TestStreamingSynthesis::test_synthesis_streaming_emits_progress_events PASSED
tests/test_fetch_window_policy.py::TestStreamingSynthesis::test_zai_client_streaming_yields_chunks PASSED
```

## Implementation Details

### Window Close Detection
- Location: `src/fetch/orchestrator.py:162-164`
- Mechanism: `await asyncio.gather(*wrapped_tasks)`
- Behavior: Waits for ALL tasks to reach terminal state (success/timeout/error)
- This IS the window close detection - no additional logic needed

### Synthesis Gating
- Location: `src/intent/router.py:718`
- Mechanism: Synthesis called AFTER `execute_fetch` returns
- Since fetch waits for window close, synthesis is automatically gated

### Timing Recording
- Location: `src/intent/router.py:604-634`
- `fetch_start = timings.clock()` at window open
- `first_source_at[0] = timings.clock()` on first progress callback
- `timings.record("fetch_total_ms", fetch_result.total_duration_ms)` at window close
- `timings.record("fetch_first_source_ms", timings.elapsed_ms(fetch_start, first_source_at[0]))`

### Caveats for Timed-out Sources
- Location: `src/fetch/orchestrator.py:179-181`
- Timed-out sources added to both `timed_out` list and `caveats` list
- These appear in synthesized result's `caveats` field

## Conclusion
All acceptance criteria are met by the existing implementation. The only addition needed was a test to explicitly verify synthesis is invoked exactly once, which has been added.
