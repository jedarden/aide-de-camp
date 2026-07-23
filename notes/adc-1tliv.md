# adc-1tliv: Wire result_type derivation into result write path

## Task Completed

Successfully integrated `derive_result_type()` into all result write paths.

## Changes Made

### Files Modified

1. **src/intent/router.py**
   - Added import: `from ..render.hot_path import derive_result_type`
   - Updated `_fetch_and_synthesize()` method (line 485-500): Call `derive_result_type()` and pass to `create_result()`
   - Updated `_create_stuck_card_from_fence()` method (line 690-703): Derive result_type from original intent classification

2. **src/escalate/handler.py**
   - Added import: `from ..render.hot_path import derive_result_type`
   - Updated `handle_terminal_failure()` function (line 966-980): Fetch intent for result_type derivation, call `derive_result_type()`, pass to `create_result()`

3. **src/monitoring/ambient.py**
   - Added import: `from ..render.hot_path import derive_result_type`
   - Updated `push_monitoring_result()` method (line 391-403): Call `derive_result_type(intent_type="monitoring", project_slug=rule.project_slug)`

4. **src/watcher/daemon.py**
   - Added import: `from ..render.hot_path import derive_result_type`
   - Updated `_create_stuck_card()` method (line 687-706): Fetch intent, derive result_type, pass to `create_result()`
   - Updated `_process_bead_event()` method (line 1015-1031): Derive result_type from intent data
   - Updated `_write_monitoring_result()` method (line 1466-1478): Call `derive_result_type(intent_type="monitoring", project_slug=project_slug)`

## All Result Write Paths Covered

Every `create_result()` call now includes a derived `result_type`:

1. ✅ Normal intent synthesis (router.py)
2. ✅ Stuck card from fence detection (router.py)
3. ✅ Terminal failure handling (escalate/handler.py)
4. ✅ Monitoring-originated results (monitoring/ambient.py)
5. ✅ Circuit breaker stuck cards (watcher/daemon.py)
6. ✅ Bead close event results (watcher/daemon.py)
7. ✅ Ambient monitoring tick results (watcher/daemon.py)

## Result Type Format

- General intents: `"{intent_type}:{project_slug}"`
- Lookup intents: `"lookup:{lookup_kind}:{project_slug}"`
- Monitoring intents: `"monitoring:{project_slug}"`
- Fallback: Uses `"general"` for project_slug and `"status"` for intent_type when None

## Acceptance Criteria Met

- ✅ Every result INSERT includes a derived result_type
- ✅ No write path bypasses result_type derivation
- ✅ One result_type per intent thread (not per fetch source)
- ✅ Deterministic derivation based on intent classification data
