# adc-1fhf0: Monitoring.yaml Config Implementation

## Task Summary
Add monitoring.yaml config with tick_interval_seconds and ensure artifact loader supports mtime-checked hot-reload per tick.

## Status: ✅ COMPLETE

All acceptance criteria already implemented:

### 1. config/monitoring.yaml exists with tick_interval_seconds: 300
- File exists at `config/monitoring.yaml`
- Contains `tick_interval_seconds: 300` (5 minutes)
- Properly documented with comments explaining hot-reload behavior

### 2. Artifact loader supports mtime-checked hot-reload
- Implemented in `src/watcher/daemon.py::BeadWatcher._hot_reload_monitoring_config()`
- Uses file mtime (modification time) to detect changes
- Only reloads when file has been modified
- Caches config between reloads in `_monitoring_config`
- Tracks mtime in `_monitoring_config_mtime`
- Updates `_monitoring_tick_interval` when config changes

### 3. Hot-reload is called per tick
- `_ambient_monitoring_tick()` calls `_hot_reload_monitoring_config()` as step 1
- Every monitoring tick checks for config changes
- New interval takes effect immediately on next tick

### 4. Tests verify hot-reload works
- `tests/test_ambient_monitoring.py::test_monitoring_config_hot_reload` ✅ PASSED
- All 12 ambient monitoring tests ✅ PASSED

## Implementation Details

**Config File:** `config/monitoring.yaml`
```yaml
tick_interval_seconds: 300  # 5 minutes
monitoring:
  active_topics: [...]
```

**Hot-reload Logic:** `src/watcher/daemon.py:1199-1235`
```python
async def _hot_reload_monitoring_config(self) -> None:
    # Check mtime
    current_mtime = config_path.stat().st_mtime
    if current_mtime <= self._monitoring_config_mtime:
        return  # No change, skip reload
    
    # Load YAML
    config = yaml.safe_load(f)
    
    # Update cached config and interval
    self._monitoring_config = config
    self._monitoring_config_mtime = current_mtime
    new_interval = config.get("tick_interval_seconds", 300)
    self._monitoring_tick_interval = float(new_interval)
```

**Tick Integration:** `src/watcher/daemon.py:1114-1115`
```python
# Step 1: Hot-reload monitoring config if changed
await self._hot_reload_monitoring_config()
```

## Verification
All tests pass:
```bash
.venv/bin/pytest tests/test_ambient_monitoring.py -xvs
# 12 passed in 0.73s
```

The task was already fully implemented. No code changes were needed.
