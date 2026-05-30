# Escalate Test Fixes (adc-19q)

## Issue
Two tests were failing in the escalate strand test suite:

1. `test_escalate_handler_extract_bead_id` - Was failing due to Python bytecode cache
   holding an outdated version of the handler implementation.

2. `test_escalate_handler_full_flow` - Was failing due to incorrect patch path for
   `asyncio.create_subprocess_exec` mock.

## Fix

1. **Cache clear**: Added explicit cache clearing before running tests to ensure
   fresh code is loaded:
   ```bash
   rm -rf src/__pycache__ src/escalate/__pycache__
   ```

2. **Patch path fix**: Changed subprocess mock patch paths from:
   - `asyncio.create_subprocess_exec` (wrong - patches top-level module)
   - `src.escalate.handler.asyncio.create_subprocess_exec` (correct - patches where used)

   Applied to:
   - `test_escalate_handler_full_flow` (line 343)
   - `test_escalate_bead_creation_failure` (line 455)

## Test Results

All 14 tests now pass:
- ✅ LLM Request payload serialization
- ✅ LLM Response total tokens
- ✅ Escalate Request serialization
- ✅ Escalate Result serialization
- ✅ ZAI Client call
- ✅ ZAI Client rate limit handling
- ✅ Escalate Handler formulate bead body
- ✅ Escalate Handler generate bead title
- ✅ Escalate Handler extract bead ID
- ✅ Escalate Handler build pending card
- ✅ Escalate Handler full flow
- ✅ Global singleton functions
- ✅ Escalate with real store
- ✅ escalate_intent convenience function
- ✅ Escalate Handler bead creation failure

## Files Changed

- `test_escalate.py`: Fixed subprocess mock patch paths (2 locations)
