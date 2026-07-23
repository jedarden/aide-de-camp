# Ambient Monitoring Tick Implementation

## Task: adc-g63t

**Status:** ✅ COMPLETE

## Summary

Implemented ambient monitoring tick functionality inside the watcher daemon (plan §10: Bead Watcher - Ambient monitoring tick).

## What Was Implemented

### 1. Core Infrastructure (in `src/watcher/daemon.py`)

- **`_ambient_monitoring_loop()`**: Independent asyncio task running on its own timer (separate from bead watch loop)
- **`_ambient_monitoring_tick()`**: Main tick handler that:
  1. Hot-reloads `config/monitoring.yaml` (mtime-checked cache)
  2. Evaluates each rule against watched topics
  3. Runs fetch-matrix sources via `src/monitoring/ambient.py`
  4. Diffs against `topic_context_cache`
  5. Writes results rows when rules fire
  6. Broadcasts via SSE per Surface Routing Rules

### 2. Configuration Hot-Reload

- **`_hot_reload_monitoring_config()`**: Mtime-checked cache for monitoring.yaml
- Loads `tick_interval_seconds` from config (default 300s = 5 minutes)
- Config reloads automatically on file modification
- Tick interval updates dynamically when config changes

### 3. State Detection & Diffing

- **`_get_topic_context_cache()`**: Reads previous state from SQLite
- **`_update_topic_context_cache()`**: Persists current state for next tick
- **`_detect_state_change()`**: Compares current vs cached state
  - Supports `notification_threshold: "any_change"` - any field triggers
  - Supports `notification_threshold: "state_change"` - only state fields (phase, status, health, etc.)
- **`_compute_state_diff()`**: Returns detailed diff of changed fields

### 4. Result Writing

- **`_write_monitoring_result()`**: Writes monitoring-originated results
  - `intent_id = NULL` (system-originated, no utterance)
  - `result_type = "monitoring:{project_slug}"`
  - `urgency` from monitoring config
  - Deterministic summary (no LLM) via `_generate_monitoring_summary()`
  - Creates result in `results` table

### 5. SSE Broadcast

- **`_broadcast_monitoring_result()`**: Routes result to active surfaces
  - Uses Surface Router to determine target surfaces
  - Broadcasts via SSE to canvas surfaces
  - Falls back to Telegram when no canvas active

### 6. Health Tracking

- **`health_snapshot()`**: Extended to include monitoring stats
  - `monitoring.last_tick_at`: Last successful tick time
  - `monitoring.tick_count`: Cumulative tick count
  - `monitoring.interval`: Current tick interval (hot-reloaded)
  - `monitoring.config_mtime`: Config file modification time

## Acceptance Criteria Verification

✅ **Rule fires on state change → result with intent_id NULL + SSE event**
- Test: `test_monitoring_tick_generates_result`
- Test: `test_full_monitoring_tick_integration`

✅ **No rule fire → no row created**
- Test: `test_no_result_when_rule_doesnt_fire`
- Baseline tick (first check) doesn't create result (establishes state only)

✅ **Interval hot-reload covered**
- Test: `test_monitoring_config_hot_reload`
- Config reloads when mtime changes
- Tick interval updates dynamically

## Configuration

`config/monitoring.yaml`:

```yaml
tick_interval_seconds: 300  # Default 5 minutes

monitoring:
  active_topics:
    - topic_id: options-pipeline-status
      project_slug: options-pipeline
      intent_type: status
      check_interval: 60
      urgency: normal
      filters:
        - "phase!=Running"
      notification_threshold: "any_change"
```

## Key Design Decisions

1. **Same Daemon, Own Timer**: Ambient monitoring runs in the same watcher daemon process but on a separate timer (independent asyncio task)

2. **Hot-Reload Pattern**: Mtime-checked cache like all other artifacts (router prompts, registry, etc.)

3. **NULL intent_id**: Monitoring-originated results have no intent thread behind them, distinguishing them from utterance-originated results

4. **Deterministic Summaries**: No LLM on the tick path - summaries are generated from templates based on what changed

5. **State Baseline Pattern**: First tick establishes baseline (no result), subsequent ticks notify on changes

## Files Modified

- `src/watcher/daemon.py`: Added ambient monitoring loop, tick handler, state detection, result writing
- `src/monitoring/ambient.py`: Already had fetch/state checking infrastructure
- `config/monitoring.yaml`: Configuration file (already existed)
- `tests/test_ambient_monitoring.py`: Comprehensive test suite (12 tests, all passing)

## Test Results

All 12 tests passing:
```
tests/test_ambient_monitoring.py::test_monitoring_config_hot_reload PASSED
tests/test_ambient_monitoring.py::test_topic_context_cache_lifecycle PASSED
tests/test_ambient_monitoring.py::test_state_change_detection_any_change PASSED
tests/test_ambient_monitoring.py::test_state_change_detection_state_change PASSED
tests/test_ambient_monitoring.py::test_monitoring_result_write_with_null_intent PASSED
tests/test_ambient_monitoring.py::test_no_result_when_rule_doesnt_fire PASSED
tests/test_ambient_monitoring.py::test_monitoring_tick_generates_result PASSED
tests/test_ambient_monitoring.py::test_health_snapshot_includes_monitoring_stats PASSED
tests/test_ambient_monitoring.py::test_deterministic_summary_generation PASSED
tests/test_ambient_monitoring.py::test_state_diff_computation PASSED
tests/test_ambient_monitoring.py::test_sse_broadcast_on_monitoring_result PASSED
tests/test_ambient_monitoring.py::test_full_monitoring_tick_integration PASSED
```

## Integration with Server

The watcher daemon (and thus ambient monitoring) is started automatically by FastAPI lifespan startup in `src/main.py`:

```python
@app.on_event("startup")
async def startup():
    # ... other startup ...
    global _bead_watcher
    _bead_watcher = await create_bead_watcher(store, router)
```

This means:
- Ambient monitoring starts automatically when the server starts
- No separate process or command to remember
- Health endpoint (`GET /health`) exposes monitoring tick liveness
- Crashes are handled by the supervisor with backoff retry

## Future Work

- Exception-based rules (`config/monitoring.yaml` `exceptions` section) - infrastructure exists but not yet wired
- Batching rules for low/normal urgency results
- Quiet hours filtering
- Multi-channel routing (canvas + telegram for critical)

## References

- Plan §10: Bead Watcher - Ambient monitoring tick
- Tests: `tests/test_ambient_monitoring.py`
- Implementation: `src/watcher/daemon.py` (lines 1202-1594)
