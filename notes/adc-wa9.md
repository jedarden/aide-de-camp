# Fetch Implementation Consolidation (adc-wa9)

## Problem

There were two parallel fetch-strand stacks:
1. **Hot path**: `src/fetch/commands.py` + `src/fetch/orchestrator.py` (used by `src/intent/router.py`)
2. **Alternate stack**: Non-existent `src/fetch/strand.py` + `src/fetch/executor.py` (imported by context modules)

The alternate stack files didn't exist, causing import errors in:
- `src/context/warmer.py`
- `src/context/prefetch.py`
- `src/escalate/commands.py`
- `src/monitoring/ambient.py`

## Solution

Created compatibility shims that bridge the old executor/strand API to the canonical orchestrator implementation:

### 1. Created `src/fetch/executor.py`
- **Purpose**: Backward compatibility layer for the old executor API
- **Key mappings**:
  - `FetchType` enum → `FetchSource` from commands.py
  - `FetchCommand` → `FetchRequest` from commands.py
  - `FetchResult` → `SourceResult` from commands.py
  - `get_fetch_executor()` → Returns adapter around `get_fetch_strand()`
- **DEPRECATED**: All code should migrate to using orchestrator/commands directly

### 2. Created `src/fetch/strand.py`
- **Purpose**: Re-export `KUBECTL_PROXIES` for backward compatibility
- **Re-exports**: `KUBECTL_PROXIES` from commands.py
- **DEPRECATED**: Import `KUBECTL_PROXIES` directly from commands.py

### 3. Added `KUBECTL_PROXIES` to `commands.py`
- Maps cluster names to their kubectl-proxy endpoints
- Used by escalate/commands.py for cluster access

## Architecture

**Canonical implementation** (existing):
- `src/fetch/commands.py` - Fetch command matrix, intent types, data structures
- `src/fetch/orchestrator.py` - Concurrent fetch execution with FetchStrand

**Compatibility shims** (newly created):
- `src/fetch/executor.py` - Maps old executor API to canonical implementation
- `src/fetch/strand.py` - Re-exports KUBECTL_PROXIES

## Verification

✅ All imports work correctly:
- `src/context/warmer.py` - imports from executor.py (shim)
- `src/context/prefetch.py` - imports from executor.py (shim)
- `src/escalate/commands.py` - imports KUBECTL_PROXIES from strand.py (shim)
- `src/monitoring/ambient.py` - imports from executor.py (shim)

✅ All tests pass (test_phase3.py: 7 passed)

✅ Documentation is correct:
- `CLAUDE.md` already identifies orchestrator.py and commands.py as canonical
- `README.md` already identifies orchestrator.py and commands.py as canonical

## Acceptance Criteria Met

- ✅ Single fetch implementation (orchestrator+commands)
- ✅ Compatibility shims allow existing imports to work
- ✅ No module imports fetch.strand or fetch.executor as primary implementation
- ✅ Existing tests still pass
- ✅ CLAUDE.md and README.md agree on fetch module names

## Next Steps (Future Migration)

The compatibility shims are marked DEPRECATED. Future work should:
1. Update `src/context/warmer.py` to use `get_orchestrator()` directly
2. Update `src/context/prefetch.py` to use `get_orchestrator()` directly
3. Update `src/escalate/commands.py` to import `KUBECTL_PROXIES` from commands.py
4. Update `src/monitoring/ambient.py` to use `get_orchestrator()` directly
5. Delete the compatibility shims once all imports are migrated

---

## Re-dispatch Verification (2026-07-20) — FINAL STATE

The "Next Steps" above have **all been completed**. The bead was re-dispatched on
2026-07-20 with a stale task description (it described the pre-consolidation world
where `strand.py`/`executor.py` existed). On re-dispatch I verified that the
consolidation already holds at HEAD. No source changes were required or made this
session — this section records the verification.

### Commit history of this consolidation
- `edd1fad` — the real consolidation: deleted the 833-line `strand.py` +
  488-line `executor.py`, folded their logic into `orchestrator.py` (+808 lines),
  updated `CLAUDE.md`.
- `bc75017` — a later agent re-introduced `strand.py` (13-line shim) +
  `executor.py` (217-line adapter) as backward-compat shims (+ this notes file,
  + `KUBECTL_PROXIES` in `commands.py`).
- `34beb3c` — deleted those shims again and migrated the consumers
  (`prefetch.py`, `warmer.py`, `ambient.py`) off them, onto `..fetch.orchestrator`
  directly.

### Verified acceptance criteria at HEAD
- ✅ **Single fetch implementation.** Neither `src/fetch/strand.py` nor
  `src/fetch/executor.py` exists. `grep -rn "fetch\.strand\|fetch\.executor"`
  across `src/`, `test/`, root `test_*.py`, `docs/`, `CLAUDE.md`, `README.md`
  returns zero hits (only `.beads/traces/*` log files mention them, which is
  expected historical agent output).
- ✅ **Consumers migrated.** `src/context/warmer.py`, `src/context/prefetch.py`,
  and `src/monitoring/ambient.py` all import `get_fetch_strand` from
  `..fetch.orchestrator` and call the `_fetch_*` source methods directly.
  All six methods consumers call (`_fetch_kubectl_pods`,
  `_fetch_kubectl_deployments`, `_fetch_argocd_app`, `_fetch_git_log`,
  `_fetch_bead_list`, `_fetch_ci_status`) exist on `orchestrator.FetchStrand`.
- ✅ **Tests.** `test_phase3.py` (covers context warmer/prefetch) passes 7/7.
  Full suite: 130 passed, 5 failed — but the 5 failures are in
  `tests/test_exceptions_routing.py` (`SurfaceRouter` missing
  `_get_no_canvas_timeout`, in `src/surface/router.py`), a different subsystem
  untouched by any of the three consolidation commits. They are pre-existing at
  HEAD and out of scope for this bead.
- ✅ **Docs agree.** `CLAUDE.md` (lines 82–83) and `README.md` (lines 187–188)
  both name exactly `src/fetch/commands.py` and `src/fetch/orchestrator.py`.
  Neither document mentions `strand.py` or `executor.py`.

### Conclusion
The dual-implementation consolidation is complete at HEAD. The blocking
dependency `adc-56ko` (doc update) is closed. Bead `adc-wa9` is ready to close.
