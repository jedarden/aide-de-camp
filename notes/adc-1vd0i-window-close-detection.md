# Window Close Detection Implementation (adc-1vd0i)

## Overview

Implemented proper window close detection logic for the fetch orchestrator. The fetch window now closes deterministically when all sources have either completed successfully, timed out, or failed.

## Key Changes

### Before (Sequential Awaiting)

The old implementation used sequential awaiting in a for loop:

```python
for source, required, timeout, task in tasks:
    try:
        result = await asyncio.wait_for(task, timeout=timeout)
        # Process result...
    except asyncio.TimeoutError:
        # Handle timeout...
```

**Problem**: This waited for tasks sequentially, not concurrently. If Task A had a 5s timeout and Task B had a 1s timeout, but Task B completed in 0.5s, we wouldn't process Task B until Task A was done.

### After (Concurrent Awaiting)

The new implementation uses `asyncio.gather()` for true concurrent execution:

```python
# Wrap each task with timeout handling
async def execute_with_timeout(source, required, timeout, task):
    try:
        result = await asyncio.wait_for(task, timeout=timeout)
        return source, required, result
    except asyncio.TimeoutError:
        # Return timeout result
    except Exception as e:
        # Return error result

# Execute all wrapped tasks concurrently
wrapped_tasks = [
    execute_with_timeout(source, required, timeout, task)
    for source, required, timeout, task in tasks
]

# Wait for ALL tasks to complete (window close)
completed_results = await asyncio.gather(*wrapped_tasks)
```

**Benefits**:
- All tasks execute concurrently
- Window closes when ALL tasks reach terminal state
- Late sources don't block window close
- Deterministic and testable

## Window Close Detection

The window is **closed** when all fetch sources have reached a terminal state:
- ✅ Success (data returned successfully)
- ⏱️ Timeout (exceeded per-source timeout from config/fetch.yaml)
- ❌ Error (exception during execution)

## Per-Source Timeouts

Each source can have its own timeout configured in `config/fetch.yaml`:

```yaml
sources:
  kubectl_pods:
    timeout_ms: 5000  # 5 seconds
  logs:
    timeout_ms: 10000  # 10 seconds
```

Priority order:
1. Project-specific override (project_timeouts.{project}.{source})
2. Global source timeout (sources.{source}.timeout_ms)
3. Spec default (FetchCommandSpec.timeout_seconds)
4. No timeout (infinity)

## Test Fixes

The test `test_slow_source_times_out_does_not_block_window_close` was failing because:

1. The config file `config/fetch.yaml` was created AFTER the test was written (in bead adc-33xez)
2. The config file's timeout for `kubectl_pods` (5000ms) was overriding the test's spec timeout (0.1s)
3. The test needed to also mock `get_source_timeout_ms` to prevent config file overrides

**Fixed by**: Adding `patch('src.fetch.commands.get_source_timeout_ms', return_value=None)` to the test mocks.

## Acceptance Criteria - All Met

✅ Window closes only after all sources complete or timeout
   - Implemented via `asyncio.gather(*wrapped_tasks)` which waits for all tasks

✅ Sources exceeding timeout are marked timed_out
   - `execute_with_timeout()` catches `asyncio.TimeoutError` and returns timeout result

✅ Window close detection is deterministic and testable
   - `asyncio.gather()` provides deterministic completion detection
   - All tests pass

✅ Late sources don't block window close
   - Tasks are wrapped with individual timeouts
   - When a task times out, it returns immediately (doesn't block other tasks)

## Files Changed

- `src/fetch/orchestrator.py`: Replaced sequential awaiting with concurrent awaiting using `asyncio.gather()`
- `tests/test_fetch_window_policy.py`: Fixed tests to mock `get_source_timeout_ms` and prevent config overrides

## Performance Impact

**Improved**: Sources complete as soon as they finish (or timeout), not when the sequential loop reaches them. This enables true parallel processing and faster window close detection.
