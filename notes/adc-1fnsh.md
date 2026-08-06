# Hot-Reload Verification Results (adc-1fnsh)

## Summary

Verified that prompts and configs are hot-reloaded on every invocation without requiring server restart.

## Test Results

All tests passed (3/3):

### 1. Router Prompt Hot-Reload ✓
- **File:** `prompts/router.md`
- **Mechanism:** `HotReloadManager.get_prompt('router')`
- **Behavior:** Changes detected within 1 second (CHECK_INTERVAL throttle)
- **Path:** Loaded via `src/intent/router.py:_load_router_prompt()`

### 2. Registry Config Hot-Reload ✓
- **File:** `config/registry.yaml`
- **Mechanism:** `HotReloadManager.get_config('registry')`
- **Behavior:** Changes detected within 1 second (CHECK_INTERVAL throttle)
- **Uses:** YAML parsing with automatic cache update on mtime change

### 3. YAML Registry Force Reload ✓
- **File:** `config/registry.yaml`
- **Mechanism:** `registry.py:get_registry(force=True)`
- **Behavior:** 5-minute TTL cache, can be force-reloaded
- **Uses:** Merged registry (YAML + auto-discovered repos)

## Implementation Details

### HotReloadManager (`src/components/hot_reload.py`)

```python
CHECK_INTERVAL = 1.0  # Seconds between mtime checks

def _check_and_reload(self, name: str) -> bool:
    # Checks mtime, reloads if changed
    # Throttled to 1 second intervals
```

**Usage patterns:**
- Router prompt: `reload_mgr.get_prompt('router')`
- Registry config: `reload_mgr.get_config('registry')`

### Registry Loading (`src/registry.py`)

```python
CACHE_TTL = 300  # 5 minutes

def get_registry(force: bool = False) -> dict:
    # Returns merged registry (YAML + discovered)
    # Auto-rebuilds after 5-minute TTL
    # Can force-reload with force=True
```

**Two registry consumers:**
1. **HotReloadManager** - Fast hot-reload (1-second check)
2. **registry.py module** - Cached with TTL (5-minute default)

## Conclusion

✅ **Hot-reload is working correctly for all tested artifacts.**

Both `prompts/router.md` and `config/registry.yaml` are read per-invocation through the HotReloadManager, with changes picked up within 1 second without server restart.

The YAML registry also supports a cached mode with 5-minute TTL for performance, which can be bypassed with `force=True` if immediate reload is needed.

## Test File

Created `tests/test_hot_reload_fast.py` for ongoing verification of hot-reload behavior.
