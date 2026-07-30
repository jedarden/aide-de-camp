# adc-5k9c1: Result Type Derivation Function

## Task Status: COMPLETE

The `derive_result_type()` function was already implemented in `src/session/store.py` (lines 258-281).

## Implementation Details

The function handles all three derivation branches as specified:

1. **Intent-derived**: `{intent_type}:{project_slug}` - for intent threads
2. **Lookup threads**: `lookup:{lookup_kind}:{project_slug}` - for lookup intents with kind
3. **Monitoring**: `monitoring:{project_slug}` - for monitoring-originated results

## Graceful None/Empty Handling

- Missing `project_slug` → defaults to `"general"`
- Missing `intent_type` → defaults to `"status"`
- Missing `lookup_kind` → falls back to standard intent-derived format

## Current Usage

The function is imported and used in:
- `src/intent/router.py` - for hot-path fetch/synthesize results
- `src/escalate/handler.py` - for escalation results
- `src/watcher/daemon.py` - for monitoring results
- `src/render/` - exported for component selection

## Verification

All manual tests pass:
```python
derive_result_type('status', 'my-project')       # → 'status:my-project'
derive_result_type('lookup', 'my-project', 'logs') # → 'lookup:logs:my-project'
derive_result_type('monitoring', 'my-project')    # → 'monitoring:my-project'
derive_result_type('status', None)                # → 'status:general'
derive_result_type(None, 'my-project')             # → 'status:my-project'
```

## Acceptance Criteria Met

- ✅ Function exists and is importable
- ✅ Handles all three derivation branches correctly
- ✅ Returns deterministic values given same inputs
- ✅ Handles None/empty cases gracefully
