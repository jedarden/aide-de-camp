# Ambient Monitoring Fetch and Diff Logic - Completion Verification

**Task:** Implement ambient monitoring fetch and diff logic
**Bead ID:** adc-1zm60
**Date:** 2026-07-23

## Acceptance Criteria Status: ✓ COMPLETE

All acceptance criteria have been verified and met:

### 1. ✓ `src/monitoring/ambient.py` exists with fetch-matrix integration
- **File:** `/home/coding/aide-de-camp/src/monitoring/ambient.py`
- **Lines:** 658 lines of implementation
- **Fetch-matrix integration:** Uses `execute_fetch()` from `src/fetch/orchestrator.py` with full command matrix support
- **Imports:**
  ```python
  from ..fetch.orchestrator import get_fetch_strand, execute_fetch, FetchRequest
  from ..fetch.commands import FetchContext, FetchSource, IntentType
  ```

### 2. ✓ Module can fetch sources for topics marked as 'watched'
- **Method:** `check_topic_state()` (lines 165-222)
- **Fetch integration:** Uses `execute_fetch()` with `FetchRequest` containing:
  - `intent_type` mapped from monitoring intent types to fetch IntentTypes
  - `FetchContext` with project_slug, namespace, repo_path, deployment, etc.
  - Full fetch command matrix support via orchestrator
- **Data extraction:** Returns state data with successful source results from all available sources

### 3. ✓ Diff logic compares fetched data against topic_context_cache
- **Methods:**
  - `_get_topic_context_cache()` (lines 291-296): Reads cached context from database
  - `_update_topic_context_cache()` (lines 298-309): Stores context in database with TTL
  - `detect_state_change()` (lines 311-361): Compares current state against cached state
  - `_compute_diff()` (lines 456-470): Computes field-level diffs between previous and current state

### 4. ✓ State changes are detected and flagged
- **Detection logic:** `detect_state_change()` returns `(has_change, changes_dict)` where:
  - `has_change`: Boolean flag indicating if state changed
  - `changes_dict["changed_fields"]`: List of field names that changed
  - `changes_dict["diff"]`: Full diff with `{"from": ..., "to": ...}` per changed field
  - `changes_dict["is_first"]`: True if this is the first check (baseline establishment)
- **Notification thresholds:**
  - `any_change`: Triggers on any field change
  - `state_change`: Triggers only on significant state fields (phase, status, health, ready, sync_status)

### 5. ✓ Test covers fetch, cache read, and diff generation
- **Test file:** `/home/coding/aide-de-camp/tests/test_ambient_fetch_and_diff.py`
- **Test count:** 10 comprehensive tests, all passing
- **Coverage:**
  - `test_fetch_sources_for_watched_topics`: Fetch-matrix integration
  - `test_diff_against_topic_context_cache`: Diff logic against cache
  - `test_first_check_establishes_baseline`: Baseline establishment behavior
  - `test_state_change_detection_any_change_threshold`: Any-change threshold
  - `test_state_change_detection_state_change_threshold`: State-change threshold
  - `test_track_what_changed_for_rule_evaluation`: Diff tracking
  - `test_push_monitoring_result_updates_cache`: Cache updates on result push
  - `test_cache_persistence_across_checks`: Cache persistence
  - `test_multiple_topics_independent_caches`: Independent topic caches
  - `test_sse_broadcast_on_monitoring_result_creation`: SSE event broadcasting

## Test Results

All 10 tests pass successfully:
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
tests/test_ambient_fetch_and_diff.py::test_sse_broadcast_on_monitoring_result_creation PASSED
============================== 10 passed in 0.38s ==============================
```

## Implementation Details

### Key Components

1. **AmbientMonitor class** (lines 80-646):
   - Manages monitoring rules and config
   - Runs per-topic monitor tasks with configurable intervals
   - Hot-reload support for config changes

2. **Check cycle flow**:
   ```
   monitor_topic() → check_topic_state() → detect_state_change() → push_monitoring_result()
   ```

3. **Fetch integration**:
   - Uses `execute_fetch()` from orchestrator with full command matrix
   - Maps monitoring intent types to fetch IntentTypes
   - Extracts successful data from multiple sources
   - Supports filters for state evaluation

4. **Diff and caching**:
   - First check establishes baseline (no notification)
   - Subsequent checks diff against cached baseline
   - Configurable notification thresholds
   - Cache updated after each check

5. **Result broadcasting**:
   - Creates result with `intent_id=NULL` (system-originated)
   - Derives result_type via hot-path selector
   - Broadcasts SSE event to canvas surfaces
   - Updates topic context cache after result creation

## Git History

The implementation was completed in previous commits:
- `c4cbb52`: feat: implement monitoring config hot-reload with tick interval
- `014f9cd`: feat(adc-6g8f0): implement SSE event broadcasting for monitoring results

## Conclusion

The ambient monitoring fetch and diff logic is fully implemented and tested. All acceptance criteria are met. The module integrates with the fetch-matrix, uses topic_context_cache for diff comparisons, detects and flags state changes, and has comprehensive test coverage.
