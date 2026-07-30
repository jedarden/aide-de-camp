# Task adc-2aepu: Remove the direct .beads/ read path from the bead watcher

## Goal
Plan §10 (Bead Watcher): detection must be CLI-only. Delete the direct-read code
path from `src/watcher/daemon.py` — the `BEADS_JSONL` constant, the
`beads_jsonl` constructor param, `_read_terminal_events()` (which opened
`issues.jsonl` directly), and the in-memory `_processed_beads` ID set used for
dedup — leaving the rest of the watcher intact.

## Outcome
**No source changes required — the direct-read path was already removed.**

The removal was performed by the **parent bead adc-qw85** in commit
`15c228d` ("feat(watcher): CLI-only bead-close detection with close-timestamp
HWM"). That commit deleted exactly the symbols this bead targets, and landed
the CLI-only replacement (`_run_bf_list_closed`, `_poll_closed_beads`, the
`_close_highwater` mark). Its own commit message enumerates the removals:

- `BEADS_JSONL` constant + `TERMINAL_STATUSES` constant + `from pathlib import Path`
- `beads_jsonl` constructor param → `self._beads_jsonl`
- `_read_terminal_events()` (opened/read `.beads/issues.jsonl` directly)
- `_processed_beads` ID set (dedup-by-id re-delivered backlog on restart)

## Acceptance-criteria verification (all pass)

1. **No direct `.beads/` read in `src/watcher`:**
   `grep -rn '\.beads/' src/watcher` → no matches. No `Path`/`open` of beads
   files, no `issues.jsonl`/`beads.db`/`pathlib` references either.

2. **No test uses the removed symbols:**
   The only matches are (a) the allowed historical comment at
   `src/watcher/daemon.py:138` ("replaces the former in-memory
   `_processed_beads` ID set"), and (b) a guardrail test
   `test_no_beads_jsonl_attribute_or_param_remains` (`tests/test_bead_watcher.py`)
   that *asserts* the symbols are absent (`assert not hasattr(BeadWatcher,
   "BEADS_JSONL")`, etc.) — it guards the removal, it does not use them.

3. **Module imports cleanly; supervisor + /health plumbing unaffected:**
   `.venv/bin/python -c "from src.watcher.daemon import BeadWatcher, BeadEvent"`
   → `import OK`. Full watcher suite: **46 passed**.
   The lifespan supervisor (adc-4afi) and liveness stamping are untouched.

## Action taken
This bead is a no-op verification pass against already-completed work. Committed
this notes file (no `src/` diff) per the bead commit requirement.
