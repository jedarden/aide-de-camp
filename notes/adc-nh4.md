# Bead adc-nh4: Urgency Hot-Reload Verification Summary

## Task
Wire `prompts/urgency.md` into urgency classification (currently dead artifact)

## Finding
**The work was already completed.** The bead description was outdated.

## Current Implementation

### Consumption Points (2 total)

1. **`src/intent/router.py`** (lines 191-199)
   - Loads urgency rules via `reload_mgr.get_prompt('urgency')`
   - Injects into router's system prompt via `URGENCY_RULES_PLACEHOLDER`
   - Used for initial intent classification

2. **`src/synthesize/strand.py`** (lines 95-120)
   - Loads urgency prompt via `reload_mgr.get_prompt('urgency')`
   - Combines with synthesize prompt: `f"{synthesize_prompt}\n\n## Urgency Classification Rules\n\n{urgency_prompt}"`
   - Used for refinement during synthesis

### Hot-Reload Registration
`src/components/hot_reload.py` (line 232):
```python
_reload_manager.register_prompt('urgency', 'prompts/urgency.md')
```

### Test Coverage
`tests/test_urgency_hotreload.py` provides comprehensive coverage:
- ✅ Urgency prompt loaded into LLM system prompt (router and synthesize)
- ✅ Hot-reload detects changes without server restart
- ✅ Urgency rules influence the urgency field of results
- ✅ All 8 tests pass

### Documentation Status
`prompts/urgency.md` header comment (line 3):
```
**Consumed by:** `src/intent/router.py` and `src/synthesize/strand.py` (loaded fresh on each invocation for hot-reload)
```
✅ Already accurate

## Why Escalate Doesn't Use Urgency Rules
The escalate handler (`src/escalate/handler.py`) does NOT perform urgency classification:
- It receives urgency as input from the router (line 487, 490, 594)
- It passes urgency through to the pending card (line 594)
- No LLM-based urgency decision is made during escalation

## Conclusion
No changes needed. The urgency hot-reload system is fully functional and well-tested.
