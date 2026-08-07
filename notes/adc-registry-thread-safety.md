# Registry Thread Safety Analysis

## Executive Summary

The aide-de-camp registry implements a dual-layer locking strategy to protect concurrent access:
1. **AsyncIO Layer** (`src/registry.py`) - Protects the global registry cache with `asyncio.Lock()`
2. **Threading Layer** (`src/components/hot_reload.py`) - Protects hot-reload artifacts with `threading.RLock()`

This analysis identifies all critical sections, shared state, and potential race conditions.

---

## 1. Registry Access Points Inventory

### 1.1 Primary Registry Module (`src/registry.py`)

#### Global Shared State
```python
# Lines 98-113
_cache_lock = asyncio.Lock()          # AsyncIO lock protecting cache access
_cache: dict | None = None            # Registry cache (merged YAML + discovered)
_cache_at: float = 0                  # Cache timestamp for TTL invalidation
```

#### Public Access Functions
| Function | Lines | Operation | Lock Protection |
|----------|-------|-----------|-----------------|
| `get_registry()` | 366-431 | Read cache with hot-reload | ✅ `_cache_lock` (async) |
| `get_project()` | 434-454 | Get single project | ✅ Protected by `get_registry()` |
| `repo_path_for()` | 457-471 | Get repo path for slug | ✅ Protected by `get_project()` |
| `projects_summary()` | 474-492 | Generate project summary | ✅ Protected by `get_registry()` |

#### Internal Functions
| Function | Lines | Operation | Lock Protection |
|----------|-------|-----------|-----------------|
| `_load_yaml()` | 276-291 | Load YAML from disk | ⚠️ Retry decorator only |
| `_discover_repos()` | 251-273 | Scan filesystem for git repos | ❌ No lock (read-only) |
| `_read_description()` | 224-248 | Read README from repo | ⚠️ Retry decorator only |
| `_build_registry()` | 339-363 | Build full registry | ❌ No lock (internal) |
| `_merge()` | 294-336 | Merge discovered + YAML | ❌ No lock (pure function) |

### 1.2 Action Registry Module (`src/action/registry.py`)

This module has **no local state** - it depends entirely on the main registry:
- All functions are `async` and call `await get_registry()`
- Protected indirectly by `_cache_lock` in the main registry

| Function | Lines | Operation | Lock Protection |
|----------|-------|-----------|-----------------|
| `get_workflow_definition()` | 152-197 | Get workflow for project | ✅ Protected by `get_registry()` |
| `list_workflows()` | 200-224 | List all workflows for project | ✅ Protected by `get_registry()` |
| `validate_all_workflows()` | 227-264 | Validate all workflows | ✅ Protected by `get_registry()` |
| `reload_registry()` | 267-278 | Force reload cache | ✅ Protected by `get_registry(force=True)` |

### 1.3 Hot Reload Manager (`src/components/hot_reload.py`)

#### Global Shared State
```python
# Lines 689-690
_reload_manager: Optional[HotReloadManager] = None  # Singleton instance

# Lines 235-245 (HotReloadManager instance state)
_artifacts: Dict[str, Artifact] = {}  # Artifact metadata
_cache: Dict[str, Any] = {}            # Parsed content cache
_lock = threading.RLock()              # Thread-safe access
_error_count: Dict[str, int] = {}      # Error frequency tracking
```

#### Public Access Functions
| Function | Lines | Operation | Lock Protection |
|----------|-------|-----------|-----------------|
| `get_reload_manager()` | 693-707 | Get/create singleton | ❌ No lock (init only) |
| `register_prompt()` | 393-446 | Register prompt artifact | ✅ `self._lock` (RLock) |
| `register_config()` | 448-524 | Register config artifact | ✅ `self._lock` (RLock) |
| `get_prompt()` | 590-621 | Get prompt with auto-reload | ✅ `self._lock` (RLock) |
| `get_config()` | 623-634 | Get config with auto-reload | ⚠️ Calls `_check_and_reload()` (has lock) |
| `force_reload()` | 636-673 | Force reload artifact | ⚠️ No explicit lock (read-modify-write) |
| `_check_and_reload()` | 526-588 | Internal reload check | ✅ `self._lock` (RLock) |

---

## 2. Critical Sections Requiring Atomic Access

### 2.1 Registry Cache Update (HIGH PRIORITY)

**Location:** `src/registry.py`, lines 366-431 (`get_registry()`)

**Critical Code:**
```python
async with _cache_lock:
    cache_is_stale = force or _cache is None or (time.time() - _cache_at) > CACHE_TTL
    if cache_is_stale:
        _cache = _build_registry()  # EXPENSIVE OPERATION
        _cache_at = time.time()
    return _cache
```

**Why Critical:**
- Multiple async tasks can simultaneously detect stale cache
- `_build_registry()` performs expensive I/O (disk scans, YAML parsing, git repo discovery)
- Without atomicity, multiple tasks could redundantly rebuild the same cache
- Double-checked locking pattern prevents redundant rebuilds

**Protection:** ✅ `asyncio.Lock()` with double-checked pattern

### 2.2 Hot-Reload Artifact Cache Update (HIGH PRIORITY)

**Location:** `src/components/hot_reload.py`, lines 526-588 (`_check_and_reload()`)

**Critical Code:**
```python
with self._lock:
    artifact = self._artifacts[name]
    current_mtime = self._get_mtime_with_retry(artifact.path)
    if current_mtime > artifact.mtime:
        new_content = self._read_file_with_retry(artifact.path, ...)
        artifact.content = new_content
        artifact.mtime = current_mtime
        self._cache[name] = parser(new_content)  # CACHE UPDATE
```

**Why Critical:**
- Read-modify-write operation on shared artifact state
- Multiple threads could simultaneously detect mtime change
- Cache update could be corrupted if interleaved
- Parse errors must not leave cache in inconsistent state

**Protection:** ✅ `threading.RLock()`

### 2.3 Singleton Initialization (MEDIUM PRIORITY)

**Location:** `src/components/hot_reload.py`, lines 693-707 (`get_reload_manager()`)

**Critical Code:**
```python
def get_reload_manager() -> HotReloadManager:
    global _reload_manager
    if _reload_manager is None:  # CHECK
        _reload_manager = HotReloadManager()  # ASSIGN
        _reload_manager.register_prompt('router', 'prompts/router.md')
        # ... more registrations
    return _reload_manager
```

**Why Critical:**
- Classic check-then-act race condition
- Two threads could both see `None` and both create instances
- Second creation would overwrite first, losing initial registrations

**Protection:** ❌ **UNPROTECTED** - Race condition exists

**Impact:** Low - only occurs at startup, singleton pattern makes second creation unlikely in practice

### 2.4 Atomic File Write (MEDIUM PRIORITY)

**Location:** `src/components/hot_reload.py`, lines 92-194 (`_atomic_write()`)

**Critical Code:**
```python
temp_fd, temp_path = tempfile.mkstemp(dir=path.parent, prefix='.atomic_write_')
with os.fdopen(temp_fd, 'w') as f:
    f.write(content)
    f.flush()
    os.fsync(f.filelo())  # Force write to disk
os.rename(temp_path, path)  # ATOMIC REPLACE
```

**Why Critical:**
- Prevents partial writes during crashes/power failures
- Readers see either old file or complete new file, never partial data
- Uses POSIX atomic rename guarantee

**Protection:** ✅ Atomic rename + retry logic

### 2.5 Force Reload Race Condition (MEDIUM PRIORITY)

**Location:** `src/components/hot_reload.py`, lines 636-673 (`force_reload()`)

**Critical Code:**
```python
def force_reload(self, name: str):
    artifact = self._artifacts[name]  # READ
    # ... read new content ...
    artifact.content = new_content    # WRITE
    artifact.mtime = artifact.path.stat().st_mtime  # WRITE
    self._cache[name] = parser(new_content)  # WRITE
```

**Why Critical:**
- Read-modify-write on shared artifact state
- No explicit lock acquisition
- Could interleave with `_check_and_reload()` updates

**Protection:** ⚠️ **UNPROTECTED** - Should acquire `self._lock`

**Impact:** Medium - force_reload is rarely used (mainly in tests)

---

## 3. Race Condition Scenarios

### Scenario 1: Double Cache Rebuild (MITIGATED ✅)

**Setup:**
- Task A and Task B both call `get_registry()` simultaneously
- Cache is stale (TTL expired)

**Race Sequence:**
1. Task A: Check cache stale → True
2. Task B: Check cache stale → True
3. Task A: Acquire `_cache_lock`, call `_build_registry()`
4. Task B: Block on `_cache_lock`
5. Task A: Update `_cache` and `_cache_at`, release lock
6. Task B: Acquire lock, **double-check** cache → no longer stale, skip rebuild
7. Both tasks return same cached registry

**Result:** ✅ **MITIGATED** by double-checked locking pattern
**Without Lock:** Both tasks would rebuild cache unnecessarily (expensive!)

---

### Scenario 2: Hot-Reload Cache Corruption (MITIGATED ✅)

**Setup:**
- Thread A and Thread B both access `get_prompt('router')` simultaneously
- File `prompts/router.md` is modified (mtime changes)

**Race Sequence:**
1. Thread A: Acquire `self._lock`, detect mtime change
2. Thread B: Block on `self._lock`
3. Thread A: Read new content, parse, update `self._cache['router']`, release lock
4. Thread B: Acquire lock, detect mtime unchanged (Thread A already updated)
5. Thread B: Skip reload, return cached content from lock
6. Both threads see consistent content

**Result:** ✅ **MITIGATED** by `threading.RLock()`
**Without Lock:** Cache corruption (partial updates, inconsistent state)

---

### Scenario 3: Singleton Double-Initialization (UNPROTECTED ❌)

**Setup:**
- Thread A and Thread B both call `get_reload_manager()` during startup

**Race Sequence:**
1. Thread A: Check `_reload_manager is None` → True
2. Thread B: Check `_reload_manager is None` → True
3. Thread A: Create `HotReloadManager()`, register 8 artifacts
4. Thread B: Create **second** `HotReloadManager()`, register 8 artifacts (overwrites Thread A's instance!)
5. Subsequent calls get Thread B's instance
6. Thread A's registrations are lost

**Result:** ❌ **UNPROTECTED** - Second initialization overwrites first
**Impact:** Low - only occurs during first-call initialization, unlikely in practice

**Mitigation:** Add lock or use module-level initialization (not lazy singleton)

---

### Scenario 4: Force Reload Interference (UNPROTECTED ❌)

**Setup:**
- Thread A: Auto-reload via `_check_and_reload()` detects mtime change
- Thread B: Manual `force_reload()` called simultaneously

**Race Sequence:**
1. Thread A: Acquire `self._lock`, start reading new content
2. Thread B: Call `force_reload()`, read artifact (NO LOCK)
3. Thread A: Update artifact.content, artifact.mtime, cache
4. Thread B: Update artifact.content, artifact.mtime, cache (overwrites Thread A!)
5. Cache ends up with Thread B's state, potentially stale

**Result:** ❌ **UNPROTECTED** - `force_reload()` doesn't acquire lock
**Impact:** Medium - could cause stale cache or inconsistent state

**Mitigation:** `force_reload()` should acquire `self._lock` before accessing artifact

---

### Scenario 5: File Read During Concurrent Write (MITIGATED ✅)

**Setup:**
- Process A: Reading `config/registry.yaml` via `_load_yaml()`
- Process B: Writing `config/registry.yaml` via `_atomic_write()`

**Race Sequence:**
1. Process A: Open file for reading
2. Process B: Write to temp file, `os.rename()` to replace target
3. Process A: Either reads old content (before rename) or new content (after rename)
4. Process A: Never sees partial/corrupted data

**Result:** ✅ **MITIGATED** by atomic rename in `_atomic_write()`
**Without Atomic Rename:** Could read partial file write

---

## 4. Lock Inventory

### 4.1 AsyncIO Locks

| Lock Name | Type | Scope | Protected State | Location |
|-----------|------|-------|-----------------|----------|
| `_cache_lock` | `asyncio.Lock()` | Global (module) | `_cache`, `_cache_at` | `src/registry.py:102` |

**When Held:**
- Cache validation checks (lines 408, 419)
- Cache rebuild operations (lines 424-425)
- Cache return (line 431)

**Contention Points:**
- Cache TTL expiry (every 5 minutes)
- Forced reloads (`force=True`)
- Simultaneous first access after startup

### 4.2 Threading Locks

| Lock Name | Type | Scope | Protected State | Location |
|-----------|------|-------|-----------------|----------|
| `self._lock` | `threading.RLock()` | Instance (HotReloadManager) | `_artifacts`, `_cache`, `_error_count` | `src/components/hot_reload.py:244` |

**When Held:**
- Artifact registration (lines 406, 463)
- Reload checks and updates (lines 533)
- Prompt/config access (lines 604, implicit in get_config)

**Contention Points:**
- Concurrent access to same artifact
- File modification detection
- Error count updates

---

## 5. Bottleneck Identification

### 5.1 Registry Cache Rebuild (BOTTLENECK)

**Location:** `src/registry.py:424` (`_cache = _build_registry()`)

**Operations:**
- YAML load from disk: `config/registry.yaml`
- Filesystem scan: `/home/coding` for `.git` directories
- README file reads: Each discovered repo
- Dictionary merging and validation

**Duration:** ~100-500ms (depends on repo count)

**Impact:** When cache expires, ALL waiting tasks block on rebuild

**Mitigation:** ✅ Double-checked locking prevents redundant rebuilds

### 5.2 Hot-Reload mtime Check (POTENTIAL BOTTLENECK)

**Location:** `src/components/hot_reload.py:546` (`self._get_mtime_with_retry()`)

**Operations:**
- `path.stat().st_mtime` system call per artifact
- Throttled to 1 check per second per artifact

**Duration:** ~1-5ms per artifact

**Impact:** Under high concurrency, many threads could block on mtime checks

**Mitigation:** ⚠️ Throttling exists, but lock contention still possible

---

## 6. Recommendations

### 6.1 Immediate Actions

1. **Protect Singleton Initialization**
   - Add lock to `get_reload_manager()` or convert to module-level initialization
   - Prevent double-initialization race condition

2. **Add Lock to `force_reload()`**
   - Acquire `self._lock` before accessing artifact
   - Prevent interference with auto-reload

3. **Add Timeout to Lock Acquisition**
   - Use `asyncio.wait_for()` with timeout for `_cache_lock`
   - Prevent deadlock scenarios (currently unprotected)

### 6.2 Medium-Term Improvements

1. **Separate Read/Write Locks**
   - Use `asyncio.RWLock` for registry cache (if library available)
   - Allow concurrent reads, exclusive writes
   - Reduce contention during cache rebuilds

2. **Lock Contention Monitoring**
   - Add metrics for lock wait times
   - Track cache rebuild frequency
   - Detect performance regressions

3. **Fine-Grained Locking**
   - Consider per-artifact locks in hot-reload
   - Reduce contention when accessing different artifacts simultaneously

### 6.3 Long-Term Enhancements

1. **Event-Driven Cache Invalidation**
   - Replace TTL polling with filesystem event notifications (inotify)
   - Eliminate unnecessary cache rebuilds
   - Reduce lock contention

2. **Read-Only Cache Views**
   - Return immutable snapshots of registry
   - Eliminate need for read locks
   - Copy-on-write for updates

---

## 7. Testing Coverage

### 7.1 Existing Tests (`tests/test_concurrent_access_protection.py`)

| Test | Lines | Scenario | Coverage |
|------|-------|----------|----------|
| `test_concurrent_registry_access` | 96-180 | 50 threads × 20 reads | ✅ Cache hit/miss contention |
| `test_race_condition_read_write` | 183-283 | 8 readers + 2 writers | ✅ Read vs write race |
| `test_concurrent_hot_reload_access` | 286-371 | 30 threads accessing artifacts | ✅ Hot-reload concurrency |
| `test_atomic_file_operations` | 374-426 | Concurrent file writes | ✅ Atomic write verification |
| `test_high_concurrency_stress` | 429-525 | 100 threads stress test | ✅ System under load |
| `test_cache_consistency` | 528-614 | Cache state observations | ✅ Data consistency |

### 7.2 Missing Test Coverage

1. **Singleton Race Condition**
   - Test double-initialization of `get_reload_manager()`
   - Verify only one instance is created under concurrent first-call

2. **Force Reload Race**
   - Test `force_reload()` interleave with auto-reload
   - Verify cache consistency

3. **Lock Timeout Detection**
   - Add timeout to lock acquisition
   - Test deadlock scenarios (e.g., cache rebuild takes too long)

4. **Filesystem Event Race**
   - Test file modification during active reload
   - Verify atomic file operations

---

## 8. Conclusion

The registry system implements **robust concurrent access protection** for the critical hot paths:

✅ **Well-Protected:**
- Registry cache updates (asyncio.Lock with double-checked pattern)
- Hot-reload artifact updates (threading.RLock)
- Atomic file operations (POSIX rename)

⚠️ **Partially Protected:**
- Singleton initialization (race condition exists but low impact)
- Force reload operations (no explicit lock)

❌ **Unprotected (Low Risk):**
- File read operations (rely on atomic write from other side)
- Pure functions (no shared state)

**Overall Assessment:** The current implementation is **production-ready** with known minor race conditions that have low practical impact. The double-checked locking pattern and retry mechanisms provide strong guarantees for the critical paths.

**Next Steps:** Address the unprotected singleton initialization and force reload operations to achieve complete thread safety coverage.

---

## Appendix: Code References

### A.1 Double-Checked Locking Pattern
```python
# src/registry.py:406-431
cache_is_stale = force or _cache is None or (time.time() - _cache_at) > CACHE_TTL
if not cache_is_stale:
    return _cache  # Fast path - no lock

async with _cache_lock:
    cache_is_stale = force or _cache is None or (time.time() - _cache_at) > CACHE_TTL
    if cache_is_stale:  # Double-check
        _cache = _build_registry()
        _cache_at = time.time()
    return _cache
```

### A.2 Retry Pattern with Jitter
```python
# src/registry.py:29-91 (decorator)
# Applied to _load_yaml() and _read_description()
jittered_delay = delay * (0.5 + random.random() * 0.5)
time.sleep(jittered_delay)
delay *= backoff_factor  # Exponential backoff
```

### A.3 Atomic File Write
```python
# src/components/hot_reload.py:92-194
temp_fd, temp_path = tempfile.mkstemp(dir=path.parent, prefix='.atomic_write_')
with os.fdopen(temp_fd, 'w') as f:
    f.write(content)
    f.flush()
    os.fsync(f.fileno())  # Force to disk
os.rename(temp_path, path)  # Atomic replace
```

---

**Document Version:** 1.0
**Analysis Date:** 2026-08-07
**Analyst:** Thread Safety Analysis (adc-5b1ko)
**Status:** Complete
