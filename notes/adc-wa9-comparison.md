# Fetch Implementation Comparison Report

**Bead:** adc-1dvh
**Date:** 2026-07-03
**Purpose:** Compare deleted fetch modules (`strand.py` + `executor.py`) against canonical stack (`commands.py` + `orchestrator.py`)

## Executive Summary

**Finding:** `strand.py` and `executor.py` were **NOT alternative implementations**—they were backward compatibility shims that wrapped the canonical implementation. Both were deleted in commit `34beb3c` (2026-07-03) as part of consolidating to a single fetch implementation.

- **`strand.py`** (13 lines): Minimal shim that only re-exported `KUBECTL_PROXIES`
- **`executor.py`** (217 lines): Adapter layer that wrapped the canonical API for legacy code

**No migration needed**—all capabilities already exist in the canonical stack.

---

## Overview of Files

The fetch implementation was consolidated in commit `34beb3c` ("refactor: consolidate dual fetch implementations (adc-wa9)").

### Deleted Modules

1. **`src/fetch/strand.py`** — 13-line compatibility shim
2. **`src/fetch/executor.py`** — 217-line backward compatibility adapter

### Canonical Implementation (Pre-Existing)

- **`src/fetch/commands.py`** — Command matrix, data structures, intent types
- **`src/fetch/orchestrator.py`** — `FetchStrand` + `FetchOrchestrator` with all source executors

## Deleted Module: `strand.py`

**Purpose:** Minimal backward compatibility shim

**Full Content (13 lines):**
```python
"""
Fetch strand - backward compatibility layer.

This module provides a compatibility shim for legacy imports.
The canonical fetch implementation is in orchestrator.py and commands.py.

DEPRECATED: Import from commands.py and orchestrator.py directly.
"""

# Re-export KUBECTL_PROXIES for backward compatibility
from .commands import KUBECTL_PROXIES

__all__ = ["KUBECTL_PROXIES"]
```

**Analysis:** This module provided NO functionality beyond re-exporting a constant from `commands.py`. It existed solely to allow legacy imports like `from .strand import KUBECTL_PROXIES` to continue working.

---

## Deleted Module: `executor.py`

**Purpose:** Backward compatibility adapter wrapping the canonical implementation

**Full Content (217 lines):**

### Key Components

1. **`FetchType` enum** (subset of `FetchSource`):
   ```python
   KUBECTL_STATUS = "kubectl_pods"
   POD_STATUS = "kubectl_pods"  # Alias
   ARGOCD_STATUS = "argocd_app"
   GIT_LOG = "git_log"
   BEAD_LIST = "bead_list"
   CI_STATUS = "ci_status"
   DEPLOYMENT_STATUS = "kubectl_deployments"
   ```
   - Mapped to canonical `FetchSource` via `_FETCH_TYPE_TO_SOURCE`
   - Mapped to `IntentType` via `_FETCH_TYPE_TO_INTENT`

2. **`FetchCommand` dataclass:**
   ```python
   fetch_type: FetchType
   project_slug: str
   args: list[str]
   timeout: int
   ```
   - `to_canonical()` method converted to `FetchRequest`
   - Auto-derived `intent_type` from `fetch_type`

3. **`FetchResult` dataclass:**
   ```python
   success: bool
   data: dict[str, Any]
   error: Optional[str] = None
   duration_ms: int = 0
   ```
   - `from_canonical()` factory converted from canonical `SourceResult`
   - Extracted source-specific fields (e.g., `pods` from `KUBECTL_PODS` result)

4. **`FetchExecutor` class:**
   - `execute()` method took `FetchCommand`
   - Converted to canonical `FetchRequest`
   - **Delegated to `FetchStrand.fetch()`** (from canonical `orchestrator.py`)
   - Converted result back to legacy `FetchResult`

5. **`get_fetch_executor()`:** Global instance getter

### Design Pattern

The `executor.py` module was a **pure adapter layer**. All actual execution was delegated to the canonical `FetchStrand` from `orchestrator.py`:

```python
async def execute(self, command: FetchCommand) -> FetchResult:
    canonical_request = command.to_canonical()
    result = await self._strand.fetch(canonical_request)  # Delegates to canonical
    return FetchResult.from_canonical(...)
```

No fetch logic was implemented in `executor.py`—it only translated between the old API and the canonical implementation.

## Canonical Implementation: `commands.py` + `orchestrator.py`

**Purpose:** Unified fetch framework with intent-based command matrix

### `commands.py`

**Purpose:** Command matrix defining what to fetch per intent type

**Key Components:**

1. **`IntentType` enum** (8 types):
   - `STATUS`, `ACTION`, `BRAINSTORM`, `LOOKUP`
   - `REMINDER`, `SELF_MODIFICATION`, `MONITORING_CONFIG`, `TASK_PROFILE`

2. **`FetchSource` enum** (17 sources):
   - Kubernetes: `KUBECTL_PODS`, `KUBECTL_DEPLOYMENTS`, `KUBECTL_WORKFLOWS`
   - ArgoCD: `ARGOCD_APP`
   - Git: `GIT_LOG`, `GIT_STATUS`
   - Beads: `BEAD_LIST`, `BEAD_DETAILS`
   - CI: `CI_STATUS`
   - Components: `COMPONENTS`
   - Operations: `LOGS`, `EVENTS`
   - State: `SESSION_STATE`, `TOPIC_CONTEXT`, `REMINDERS`
   - Filesystem: `FS_EXPLORE`, `FS_README`, `FS_HOME`

3. **`FetchCommandSpec` dataclass:**
   - `source`: FetchSource
   - `command_template`: str (e.g., `"kubectl --server={proxy} get pods -n {namespace} -o json"`)
   - `timeout_seconds`: int (default 5)
   - `required`: bool (default False)
   - `cacheable`: bool (default True)

4. **`FETCH_COMMAND_MATRIX`:**
   - Maps `IntentType` → `list[FetchCommandSpec]`
   - Defines which sources to query for each intent type
   - Configurable per-source timeouts
   - Marks required vs. optional sources

5. **`FetchContext` dataclass:**
   - Context variables for template expansion
   - Includes `ssh_target`, `host_alias` for remote execution
   - Template expansion via `expand_template()` method

6. **Result types:**
   - `SourceResult`: Single source result (status, data, error, duration_ms, cached)
   - `FetchCoverage`: Coverage report (succeeded, timed_out, failed, skipped)
   - `FetchResult`: Complete result with all sources and coverage

### `orchestrator.py`

**Purpose:** Concurrent fetch execution with streaming support

**Key Components:**

1. **`FetchStrand` class:**
   - `_source_executors`: Dict mapping `FetchSource` → async executor method
   - `fetch()` method:
     - Executes all sources concurrently via `asyncio.create_task()`
     - Enforces per-source timeouts via `asyncio.wait_for()`
     - Calls `on_partial_result` callback as each source completes
     - Tracks coverage (succeeded, timed_out, failed, skipped)
     - Generates caveats for failed sources
   - **17 source executor methods**: `_fetch_kubectl_pods`, `_fetch_git_log`, etc.
   - SSH remote execution support via `_make_cmd()` wrapper

2. **`FetchOrchestrator` class:**
   - Convenience wrapper around `FetchStrand`
   - Provides `execute_fetch()` method with same interface

3. **Global instances:**
   - `get_orchestrator()`: Returns singleton `FetchOrchestrator`
   - `get_fetch_strand()`: Returns singleton `FetchStrand`

**Capabilities:**
- ✅ Streaming callbacks via `on_partial_result(source, result)`
- ✅ Concurrent execution via asyncio
- ✅ Per-source timeouts
- ✅ Comprehensive coverage tracking
- ✅ Caveat generation for failed sources
- ✅ SSH remote execution for git/filesystem operations
- ✅ Async HTTP client (httpx) for Kubernetes API calls

## Capability Matrix

| Capability | Canonical (orchestrator.py) | Deleted (strand.py) | Deleted (executor.py) |
|------------|----------------------------|--------------------|----------------------|
| Concurrent fetch execution | ✅ Native | ❌ N/A (shim) | ❌ Delegated to canonical |
| Streaming callbacks | ✅ `on_partial_result` | ❌ N/A (shim) | ❌ No support |
| Per-source timeouts | ✅ `timeout_seconds` in spec | ❌ N/A (shim) | ❌ No support |
| Coverage tracking | ✅ `FetchCoverage` dataclass | ❌ N/A (shim) | ❌ No support |
| Caveat generation | ✅ Automatic | ❌ N/A (shim) | ❌ No support |
| SSH remote execution | ✅ `_make_cmd()` wrapper | ❌ N/A (shim) | ❌ No support |
| Kubernetes API (async) | ✅ Httpx async client | ❌ N/A (shim) | ❌ Delegated to canonical |
| Git operations | ✅ Local + SSH remote | ❌ N/A (shim) | ❌ Delegated to canonical |
| Filesystem operations | ✅ Local + SSH remote | ❌ N/A (shim) | ❌ Delegated to canonical |
| Intent-based routing | ✅ `FETCH_COMMAND_MATRIX` | ❌ N/A (shim) | ❌ No support |
| Source executors (17) | ✅ All implemented | ❌ N/A (shim) | ❌ Delegated to canonical |

---

## Consolidation Details

### Commit: `34beb3c` (2026-07-03)

**Title:** "refactor: consolidate dual fetch implementations (adc-wa9)"

**Changes:**
1. Deleted `src/fetch/executor.py` (217 lines)
2. Deleted `src/fetch/strand.py` (13 lines)
3. Updated `src/context/warmer.py` → use `get_fetch_strand()` from orchestrator
4. Updated `src/context/prefetch.py` → use `get_fetch_strand()` from orchestrator
5. Updated `src/monitoring/ambient.py` → use `get_fetch_strand()` from orchestrator

**Acceptance Criteria (from commit):**
- ✅ Single fetch implementation using orchestrator+commands
- ✅ No module imports fetch.strand or fetch.executor
- ✅ Existing tests still pass
- ✅ CLAUDE.md and README.md already agree on fetch module names

---

## Key Findings

### 1. `strand.py` Was a Minimal Shim

**Purpose:** Allow legacy imports of `KUBECTL_PROXIES` to continue working

**Impact:** Zero—no functionality lost, only a constant re-export

### 2. `executor.py` Was an Adapter Layer

**Purpose:** Translate old API (`FetchType`, `FetchCommand`) to new API (`FetchSource`, `FetchRequest`)

**Impact:** Zero—all execution delegated to canonical `FetchStrand.fetch()`

**Design Pattern:**
- `FetchType` enum → mapped to `FetchSource`
- `FetchCommand` → converted to `FetchRequest`
- `FetchResult` → converted from `SourceResult`
- `FetchExecutor.execute()` → delegated to `FetchStrand.fetch()`

### 3. All Capabilities Were Already in Canonical Stack

The canonical implementation (`commands.py` + `orchestrator.py`) already had:

- ✅ All 17 source executors
- ✅ Streaming callbacks via `on_partial_result`
- ✅ Coverage tracking (succeeded, timed_out, failed, skipped)
- ✅ Caveat generation for failed sources
- ✅ SSH remote execution support
- ✅ Per-source timeout enforcement
- ✅ Intent-based command matrix
- ✅ Required/optional source flags
- ✅ Cacheable flags (for future caching layer)

---

## Migration Status

**No migration required**—the deleted modules provided no capabilities beyond what exists in the canonical stack.

### What Was Deleted

1. **`strand.py`** (13 lines):
   - Re-exported `KUBECTL_PROXIES` constant
   - Existed solely for backward compatibility

2. **`executor.py`** (217 lines):
   - Adapter layer translating old API to new API
   - Delegated all execution to canonical `FetchStrand`
   - No independent fetch logic

### What Remains

1. **`commands.py`**:
   - Intent types, fetch sources, command matrix
   - Result types and context structures

2. **`orchestrator.py`**:
   - `FetchStrand` with all source executors
   - `FetchOrchestrator` convenience wrapper
   - Global instance management

---

## Acceptance Criteria

- ✅ Comparison report exists documenting all capabilities from deleted modules
- ✅ List of features that need migration: **NONE**—all capabilities already present in canonical stack

---

## Conclusion

**The canonical stack (`commands.py` + `orchestrator.py`) was already the complete implementation** before consolidation. The deleted `strand.py` and `executor.py` modules were compatibility shims that wrapped the canonical implementation:

- `strand.py` was a 13-line shim that only re-exported `KUBECTL_PROXIES`
- `executor.py` was a 217-line adapter that translated between old and new APIs

**No features require migration**—all functionality exists in the canonical implementation. The consolidation successfully removed the compatibility layer without losing any capabilities.
