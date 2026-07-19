# adc-3g76 — Migrate context modules to canonical stack

## Task

Update `src/context/warmer.py` and `src/context/prefetch.py` to use
`src/fetch/commands.py` and `src/fetch/orchestrator.py` instead of the
deprecated `src/fetch/executor.py` and `src/fetch/strand.py`.

Acceptance criteria:
- No module imports `fetch.strand` or `fetch.executor`
- `test_phase3.py` passes

## Result: already complete on main

This migration was already performed in commit **`34beb3c`** (bead adc-wa9,
"refactor: consolidate dual fetch implementations"). That commit:

- Deleted `src/fetch/executor.py` (backward-compat layer)
- Deleted `src/fetch/strand.py` (legacy re-export module)
- Migrated `src/context/warmer.py` → `get_fetch_strand()` from orchestrator
- Migrated `src/context/prefetch.py` → `get_fetch_strand()` from orchestrator
- Migrated `src/monitoring/ambient.py` → same

So bead adc-3g76 re-states work already present on `main`. No code changes
were needed.

## Verification (2026-07-19)

1. **No deleted-module imports** — grep across `src/` and the test files for
   `fetch.strand` / `fetch.executor` import patterns returns nothing:
   ```
   grep -rn "from.*fetch\.strand\|from.*fetch\.executor" src/ test_phase3.py
   # (empty)
   ```
   The only remaining `strand` references are `get_fetch_strand` / `FetchStrand`
   (the canonical class/function in `fetch.orchestrator`) and the unrelated
   `synthesize.strand` module — neither is the deleted `fetch.strand`.

2. **Deleted files absent** — `src/fetch/executor.py` and `src/fetch/strand.py`
   do not exist. `src/fetch/__init__.py` docstring states "The legacy
   executor.py has been removed - all code now uses this stack."

3. **Canonical imports confirmed** — both files import from the canonical stack:
   - `warmer.py`: `from ..fetch.orchestrator import get_fetch_strand` +
     `from ..fetch.commands import FetchContext, FetchSource, IntentType`
   - `prefetch.py`: `from ..fetch.orchestrator import get_fetch_strand` +
     `from ..fetch.commands import FetchContext`

4. **Import smoke test** — both modules import cleanly; `get_fetch_strand`
   resolves to `src.fetch.orchestrator`.

5. **`test_phase3.py` passes** (run with `.venv/bin/python`): all 7 tests green
   (Conversation Tracker, Prefetcher, Diff Engine, Batching, Feedback Signals,
   Context Warmer, Ambient Monitor).

## Note on runtime

`test_phase3.py` must be run with the project venv (`.venv/bin/python`), not
the system `python3`, which lacks `aiosqlite`/`httpx`/`yaml`.
