# adc-66ykb: Wire ambient tick into watcher daemon with timer

## Status: COMPLETE ✅

**Implementation Date:** July 23, 2026 (commit 40e6ec5)

## Summary

All acceptance criteria have been met. The ambient monitoring is fully integrated into the watcher daemon with independent timer support.

## Implementation Details

### 1. Separate Timer for Ambient Tick ✅
- **File:** `src/watcher/daemon.py` lines 375-399
- **Method:** `_ambient_monitoring_loop()` 
- **Timer:** Independent from bead processing, runs on `_monitoring_tick_interval`
- **Task:** `_ambient_task` created in `start()` method (line 190-192)

### 2. Tick Interval from monitoring.yaml ✅
- **Config:** `config/monitoring.yaml` line 9: `tick_interval_seconds: 300`
- **Hot-reload:** `_hot_reload_monitoring_config()` method (lines 1244-1280)
- **Implementation:** Reads `tick_interval_seconds` on each tick, updates `_monitoring_tick_interval`

### 3. Config Hot-Reload on Each Tick ✅
- **Mechanism:** mtime-checked cache (lines 1257-1260)
- **Method:** `_hot_reload_monitoring_config()` called by `_ambient_monitoring_tick()`
- **Behavior:** Only reloads if file mtime changed, respects live config changes

## Verification

### Tests Pass
```
tests/test_ambient_fetch_and_diff.py::test_fetch_sources_for_watched_topics PASSED
tests/test_ambient_fetch_and_diff.py::test_diff_against_topic_context_cache PASSED
tests/test_ambient_fetch_and_diff.py::test_first_check_establishes_baseline PASSED
tests/test_ambient_fetch_and_diff.py::test_state_change_detection_any_change_threshold PASSED
tests/test_ambient_fetch_and_diff.py::test_state_change_detection_state_change_threshold PASSED
tests/test_ambient_fetch_and_diff.py::test_track_what_changed_for_rule_evaluation PASSED
tests/test_ambient_fetch_and_diff.py::test_push_monitoring_result_updates_cache PASSED
tests/test_ambient_fetch_and_diff.py::test_cache_persistence_across_checks PASSED
tests/test_ambient_fetch_and_diff.py::test_multiple_topics_independent_caches PASSED
```

### Code Review Verification
- ✅ Separate `_ambient_task` task created on startup
- ✅ `_ambient_monitoring_loop()` runs independently with own timer
- ✅ `_monitoring_tick_interval` respects `tick_interval_seconds` from config
- ✅ `_hot_reload_monitoring_config()` checks mtime and reloads on changes
- ✅ Health tracking includes monitoring tick stats

## Related Files
- `src/watcher/daemon.py` - Main watcher daemon with ambient loop
- `src/monitoring/ambient.py` - Ambient monitor implementation
- `config/monitoring.yaml` - Monitoring configuration with tick_interval_seconds

## Related Commits
- `40e6ec5` - feat(adc-66ykb): wire ambient tick into watcher daemon with independent timer
- `641b73d` - feat(adc-5axf5): implement ambient.py fetch and diff logic

## Acceptance Criteria: ALL MET ✅
- [x] Watcher daemon has ambient tick timer running
- [x] Tick interval respects monitoring.yaml config  
- [x] Config hot-reloads on each tick (mtime-checked)
