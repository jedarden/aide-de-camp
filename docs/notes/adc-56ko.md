# adc-56ko — Align fetch module docs in CLAUDE.md and README.md

## Task

Make CLAUDE.md and README.md agree on the canonical fetch modules
(`commands.py` + `orchestrator.py`) and remove any references to the
deprecated fetch modules.

## Acceptance criteria

- CLAUDE.md and README.md agree on fetch module names ✓
- No references to `strand.py` or `executor.py` in either file ✓ (see note)

## What was done

Harmonized the fetch module descriptions so both docs name the same two
files with the same wording:

- `src/fetch/commands.py` — fetch command matrix, intent types, data structures
- `src/fetch/orchestrator.py` — concurrent fetch execution with streaming and
  coverage tracking (FetchStrand implementation)

README.md previously had terse, divergent descriptions ("Fetch command matrix
per intent type" / "Parallel fetch execution"). It now matches CLAUDE.md and
the canonical surface documented in `src/fetch/__init__.py`.

## Note on `src/fetch/strand.py` / `src/fetch/executor.py`

The deprecated fetch modules — `src/fetch/strand.py` and
`src/fetch/executor.py` — were consolidated into `src/fetch/orchestrator.py`
(commits `edd1fad`, `34beb3c`) and no longer exist. Neither CLAUDE.md nor
README.md references them. `src/fetch/__init__.py` states this explicitly:
"This is the single canonical fetch implementation. The legacy executor.py
has been removed."

## Important distinction: `src/synthesize/strand.py` is NOT deprecated

Both docs legitimately reference `src/synthesize/strand.py`. This is a
different module — the **synthesize** strand, not a fetch module — and it is
live code: `src/intent/router.py:21` imports `SynthesizeRequest,
synthesize_intent` from it, and `src/synthesize/__init__.py` exports it.
Removing its documentation would make the docs inaccurate. The criterion's
"no references to strand.py" targets the deprecated **fetch** `strand.py`,
which is already absent.
