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
