# Fetch-Window Policy Implementation Summary

**Task:** adc-3ib6 — Fetch-window policy: synthesize gates on window close, per-source timeouts, progress states

**Status:** ✅ COMPLETE — All acceptance criteria verified

## Implementation Verification

All 10 tests in `tests/test_fetch_window_policy.py` pass:

### Core Functionality Tests (4/4 passed)
1. ✅ `test_synthesis_waits_for_all_sources_to_complete` — Synthesis fires only after window close
2. ✅ `test_slow_source_times_out_does_not_block_window_close` — Timeout enforcement works correctly
3. ✅ `test_progress_events_fire_as_sources_complete` — Progress events stream during window
4. ✅ `test_timed_out_sources_included_in_caveats` — Timed-out sources appear in caveats only

### Timing Metrics Tests (2/2 passed)
5. ✅ `test_fetch_first_source_ms_recorded` — First source resolution timing captured
6. ✅ `test_fetch_total_ms_records_window_close` — Window close timing captured

### SSE Broadcast Tests (1/1 passed)
7. ✅ `test_progress_events_broadcast_via_sse` — FETCH_PROGRESS events broadcast correctly

### Synthesis Gating Tests (1/1 passed)
8. ✅ `test_synthesis_invoked_exactly_once_after_window_close` — One synthesis call per intent after window

### Streaming Synthesis Tests (2/2 passed)
9. ✅ `test_synthesis_streaming_emits_progress_events` — SYNTHESIS_PROGRESS events work
10. ✅ `test_zai_client_streaming_yields_chunks` — LLM streaming yields text chunks

## Architecture Components

### 1. Fetch Orchestrator (`src/fetch/orchestrator.py`)
- **Concurrent execution**: All fetch sources run in parallel via `asyncio.gather`
- **Window close detection**: Waits for ALL tasks to complete (success/timeout/error)
- **Per-source timeouts**: Enforced via `asyncio.wait_for` with configurable timeouts
- **Progress callbacks**: `on_partial_result` streams incremental results

### 2. Intent Router (`src/intent/router.py`)
- **Window-close gating**: Line 628 — `await execute_fetch()` completes before synthesis
- **Progress broadcasting**: Lines 609-626 — `_on_fetch_progress` broadcasts FETCH_PROGRESS events
- **Timing capture**: Lines 629-634 — Records `fetch_first_source_ms` and `fetch_total_ms`
- **Synthesis timing**: Line 753 — Records `synthesize_total_ms`

### 3. Per-Source Timeouts (`config/fetch.yaml`)
- Configurable timeouts in milliseconds for each source type
- Project-specific overrides supported
- Hot-reloaded on every fetch call

### 4. SSE Broadcaster (`src/sse/broadcaster.py`)
- `broadcast_fetch_progress()` — Emits '3/5 sources in' updates
- `broadcast_synthesis_progress()` — Emits text chunks for progressive card fill

### 5. Timing Instrumentation (`src/instrument/timings.py`)
- `DispatchTimings` class captures per-stage millisecond durations
- `fetch_first_source_ms` — Time to first source resolution
- `fetch_total_ms` — Window close time (all sources resolved or timed out)

## Key Behaviors Verified

### ✅ Synthesis Gates on Window Close
```python
# Line 628 in router.py — fetch completes before synthesis
fetch_result = await execute_fetch(fetch_request, _on_fetch_progress)
# ... window closes here ...

# Line 718 — synthesis happens AFTER window close
synthesize_result = await synthesize_intent(synthesize_request)
```

### ✅ Per-Source Progress States
- Progress callback fires as each source completes
- SSE event includes: completed/total counts, source name, status
- Canvas can render "3/5 sources in" progressively

### ✅ Timed-Out Sources in Caveats
- Timed-out sources go to `timed_out` bucket, not `failed`
- Caveats list includes "X source timed out"
- No re-synthesis triggered — synthesis fires once per window close

### ✅ Timing Metrics Persisted
- `dispatch_timings` table stores all captured timings
- `fetch_first_source_ms` — First progress state on pending card
- `fetch_total_ms` — Window close time (gates synthesis start)

## Files Modified/Created

### Core Implementation (already existed)
- `src/fetch/orchestrator.py` — Concurrent fetch execution with window-close detection
- `src/fetch/commands.py` — Per-source timeout configuration
- `src/intent/router.py` — Window-close gating, progress broadcasting, timing capture
- `src/sse/broadcaster.py` — FETCH_PROGRESS and SYNTHESIS_PROGRESS event broadcasting
- `src/instrument/timings.py` — DispatchTimings class for per-stage metrics

### Configuration (already existed)
- `config/fetch.yaml` — Per-source timeout definitions

### Tests (already existed)
- `tests/test_fetch_window_policy.py` — Comprehensive acceptance test suite (10 tests)

## Acceptance Criteria Status

| Criterion | Status | Evidence |
|-----------|--------|----------|
| Synthesis fires exactly once per thread on window close | ✅ PASS | Test #8 verifies one synthesis call after window close |
| Late/timed-out sources appear only as caveats | ✅ PASS | Test #4 verifies timed-out sources in caveats, no re-synthesis |
| Progress states stream to pending card | ✅ PASS | Test #3 verifies incremental progress events (3/5 sources in) |
| Per-source timeouts don't delay window close | ✅ PASS | Test #2 verifies slow source timeout doesn't block window |
| fetch_first_source_ms recorded | ✅ PASS | Test #5 verifies first source timing captured |
| fetch_total_ms records window close | ✅ PASS | Test #6 verifies window close timing captured |

## Implementation Notes

1. **No code changes required** — The implementation was already complete in the codebase
2. **Test coverage validates the design** — All 10 tests pass, confirming acceptance criteria
3. **Streaming synthesis support exists** — LLM client has `call_streaming()` for progressive card fill
4. **Configuration is flexible** — `config/fetch.yaml` allows project-specific timeout overrides

## Verification Steps Run

```bash
# Run all fetch-window policy tests
.venv/bin/python -m pytest tests/test_fetch_window_policy.py -v

# Result: 10 passed in 0.96s
```

All acceptance criteria verified. Implementation complete.
