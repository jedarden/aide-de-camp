# Router Prompt Hot-Reload Test Coverage Summary

## Task Requirements
Add test coverage for verifying hot-reload behavior of `prompts/router.md`.

## Acceptance Criteria
- ✅ Test exists that modifies router prompts
- ✅ Test verifies prompt change is reflected in next dispatch
- ✅ Test reverts modifications after verification
- ✅ Test passes when run independently

## Existing Coverage

The file `tests/test_router_prompt_hotreload.py` already contains comprehensive test coverage with **11 passing tests** organized into 4 test classes:

### 1. TestRouterPromptReadPerCall (4 tests)
Tests that the router prompt is read from disk on each call, not hardcoded:

- `test_load_router_prompt_reads_file_content` - Verifies `_load_router_prompt()` returns on-disk content
- `test_router_prompt_not_hardcoded_fallback` - Proves the loaded prompt differs from the fallback constant
- `test_router_prompt_hot_reload_detects_disk_change` - Core regression test for adc-3a3d: edits to `prompts/router.md` are detected without server restart
- `test_router_prompt_falls_back_when_file_missing` - Graceful fallback when file is missing

### 2. TestBuildSystemPrompt (2 tests)
Tests that the system prompt construction uses router.md:

- `test_build_includes_router_md_content` - Verifies `_build_system_prompt()` includes router.md content
- `test_build_reflects_router_md_edit` - Verifies prompt edits are reflected in system prompt

### 3. TestRouterMdReachesLLM (2 tests)
Tests that the router prompt actually reaches the LLM:

- `test_router_md_content_sent_to_llm` - Verifies router.md content is sent to ZAI client
- `test_router_md_edit_reaches_llm_without_restart` - Verifies edits reach LLM without server restart

### 4. TestRoutingBehaviorHotReload (3 tests)
**Integration tests** that verify routing BEHAVIOR changes with prompt edits:

- `test_routing_changes_with_prompt_edit_without_restart` - **The core acceptance test**:
  1. Dispatch utterance with status-biased prompt → gets "status" classification
  2. Edit `prompts/router.md` to action-biased prompt
  3. Re-dispatch SAME utterance → gets "action" classification
  4. Revert to status-biased prompt
  5. Third dispatch → gets "status" classification again

- `test_hot_reload_with_cache_invalidation` - Verifies hot-reload works with router cache active
- `test_multiple_prompt_edits_in_sequence` - Tests iterative prompt edits (simulating self-modification agent)

## Test Results

All 11 tests pass independently:
```
============================== 11 passed in 9.11s ==============================
```

## Key Test: `test_routing_changes_with_prompt_edit_without_restart`

This test **exactly matches** the task requirements:

1. ✅ **Modifies prompts/router.md content** - Writes `ROUTER_MD_ACTION_BIASED` to temp file
2. ✅ **Re-dispatches the same utterance** - Classifies "check the pods" 3 times
3. ✅ **Verifies routing picks up the prompt change** - Asserts classification changes from "status" → "action" → "status"
4. ✅ **Reverts the test edit** - Restores original prompt content

## Conclusion

**Task Status: COMPLETE**

Comprehensive test coverage for `prompts/router.md` hot-reload already exists in `tests/test_router_prompt_hotreload.py`. All acceptance criteria are met:

- ✅ Tests modify router prompts
- ✅ Tests verify prompt changes affect routing behavior
- ✅ Tests revert modifications after verification
- ✅ All tests pass independently

No additional test coverage is needed. The existing tests lock down the core fix for bead adc-3a3d: the router reads `prompts/router.md` on each `classify_utterance()` call, so edits take effect without server restart.
