# ADC-Q1H10: Router Prompt Hot-Reload Test Coverage

## Summary

The test file `tests/test_router_prompt_hotreload.py` already exists and comprehensively covers all requirements for prompts/router.md hot-reload test coverage.

## Existing Coverage

The test file contains 11 tests organized into 4 test classes:

### 1. TestRouterPromptReadPerCall (4 tests)
- ✅ Verifies `_load_router_prompt()` reads file content (not hardcoded)
- ✅ Confirms hot-reload detects disk changes
- ✅ Tests fallback behavior when file is missing
- ✅ Validates prompt differs from fallback constant

### 2. TestBuildSystemPrompt (2 tests)
- ✅ Confirms `_build_system_prompt()` includes router.md content
- ✅ Verifies system prompt reflects router.md edits

### 3. TestRouterMdReachesLLM (2 tests)
- ✅ Validates router.md content is sent to LLM
- ✅ **KEY TEST**: Confirms router.md edits reach LLM without server restart

### 4. TestRoutingBehaviorHotReload (3 tests)
- ✅ **KEY TEST**: Verifies routing behavior changes with prompt edits
- ✅ Tests hot-reload with cache invalidation
- ✅ Tests multiple rapid edits in sequence

## Key Integration Test: `test_routing_changes_with_prompt_edit_without_restart`

This test matches all acceptance criteria:

1. **Modifies prompts/router.md content** ✅
   - Writes status-biased router.md → action-biased router.md → back to status-biased

2. **Re-dispatches the same utterance** ✅
   - Uses "check the pods" for all three dispatches

3. **Verifies routing picks up the prompt change** ✅
   - First dispatch with status-biased → `intent_type="status"`
   - Second dispatch with action-biased → `intent_type="action"`
   - Third dispatch with status-biased → `intent_type="status"`

4. **Reverts the test edit** ✅
   - Final step reverts to original status-biased prompt
   - Confirms routing returns to original behavior

## Test Results

All 11 tests pass independently:

```bash
$ .venv/bin/python -m pytest tests/test_router_prompt_hotreload.py -v
============================== 11 passed in 9.13s ==============================
```

The key integration test passes independently:

```bash
$ .venv/bin/python -m pytest tests/test_router_prompt_hotreload.py::TestRoutingBehaviorHotReload::test_routing_changes_with_prompt_edit_without_restart -v
============================== 1 passed in 0.05s ==============================
```

## Conclusion

✅ **All acceptance criteria are met by existing test coverage**

The test file `tests/test_router_prompt_hotreload.py` provides comprehensive coverage of router prompt hot-reload functionality, including:
- Per-call prompt loading from disk
- Hot-reload detection of file changes  
- Prompt changes reaching the LLM without restart
- Actual routing behavior changes based on prompt edits
- Cache invalidation scenarios
- Multiple rapid edits in sequence

No additional test coverage is needed for this requirement.

## Related Files

- Test file: `tests/test_router_prompt_hotreload.py`
- Router implementation: `src/intent/router.py`
- Hot-reload infrastructure: `src/components/hot_reload.py`
- Router prompt: `prompts/router.md`
