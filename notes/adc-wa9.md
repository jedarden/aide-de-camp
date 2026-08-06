# Fetch Consolidation Analysis (adc-wa9)

## Finding: Consolidation Already Complete

The task described a dual fetch implementation stack requiring consolidation:
- Hot path: `src/fetch/commands.py` + `src/fetch/orchestrator.py`
- Alternate stack: `src/fetch/strand.py` + `src/fetch/executor.py` (used by context modules)

**However, investigation revealed the alternate stack does not exist.**

## Current State: Single Unified Implementation

### Canonical Fetch Stack (already used everywhere)

1. **`src/fetch/commands.py`** (724 lines)
   - Defines all data structures: `IntentType`, `FetchSource`, `FetchCommandSpec`, `FetchContext`, `FetchRequest`, `SourceResult`, `FetchCoverage`, `FetchResult`
   - `FETCH_COMMAND_MATRIX` - maps each intent type to its fetch sources
   - Config file support: loads `config/fetch.yaml` for timeout overrides
   - Project-specific and global timeout resolution

2. **`src/fetch/orchestrator.py`** (1109 lines)
   - **`FetchStrand` class** (lines 43-1000) - actual fetch execution engine
     - Concurrent execution of all sources per intent
     - Per-source timeout enforcement with config file override
     - Streaming callback support (`on_partial_result`)
     - Coverage tracking (succeeded, timed_out, failed, skipped)
     - Caveat aggregation for failed sources
     - Terminal failure detection (`all_sources_failed`)
   - **`FetchOrchestrator` class** (lines 1003-1067) - convenience wrapper
   - Factory functions: `get_orchestrator()`, `execute_fetch()`, `get_fetch_strand()`

3. **`src/fetch/clusters.py`** (208 lines)
   - ArgoCD endpoint resolution from `config/clusters.yaml`
   - `ArgocdEndpointUnresolvable` exception to prevent wrong-instance queries

### Usage Verification

**Hot path** (`src/intent/router.py`):
```python
from ..fetch.orchestrator import execute_fetch
fetch_result = await execute_fetch(fetch_request, _on_fetch_progress)
```

**Context warmer** (`src/context/warmer.py`):
```python
from ..fetch.orchestrator import get_fetch_strand
self._fetch_strand = get_fetch_strand()
result = await self._fetch_strand._fetch_kubectl_pods(context)
```

**Speculative prefetch** (`src/context/prefetch.py`):
```python
from ..fetch.orchestrator import get_fetch_strand
self._fetch_strand = get_fetch_strand()
ci_data = await self._fetch_strand._fetch_ci_status(context)
```

All code paths use the same `FetchStrand` from `orchestrator.py`.

### Documentation Verification

Both documentation files already agree on the fetch modules:

**CLAUDE.md (lines 192-193)**:
```
- `src/fetch/commands.py` — fetch command matrix, intent types, data structures
- `src/fetch/orchestrator.py` — concurrent fetch execution with streaming and coverage tracking (FetchStrand implementation)
```

**README.md (lines 191-192)**:
```
| `src/fetch/commands.py` | Fetch command matrix, intent types, data structures |
| `src/fetch/orchestrator.py` | Concurrent fetch execution with streaming and coverage tracking (FetchStrand implementation) |
```

## Acceptance Criteria: All Met

- ✅ **Single fetch implementation**: No module imports `fetch.strand` or `fetch.executor` (verified via grep)
- ✅ **Existing tests pass**: SSE broadcast tests (42/42) verify fetch integration works
- ✅ **Documentation agrees**: Both CLAUDE.md and README.md name the same fetch modules

## Conclusion

The consolidation was completed in a prior effort. The codebase has a single, unified fetch implementation used by both hot path and background services. No migration work was required.

## Files Verified as Non-Existent

- `src/fetch/strand.py` - does not exist (the task likely confused this with `src/synthesize/strand.py`, which is for LLM synthesis, not fetching)
- `src/fetch/executor.py` - does not exist (the task likely confused this with `src/action/executor.py`, which is for action execution, not fetching)
