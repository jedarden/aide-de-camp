# Registry Hot-Reload Behavior

## Overview

The registry module (`src/registry.py`) implements a **TTL-based cache invalidation** mechanism that enables hot-reload of `config/registry.yaml` without requiring a server restart. This is critical for self-modification workflows where agents may add new projects, aliases, or modify existing entries dynamically.

## Architecture

### Cache Mechanism

```python
_cache: dict | None = None          # Stores the merged registry (YAML + discovered projects)
_cache_at: float = 0                # Timestamp when cache was last built
CACHE_TTL = 300                     # 5 minutes
```

### Hot-Reload Flow

1. **First Call**: `get_registry()` builds the merged registry from disk
   - Reads `config/registry.yaml`
   - Scans `/home/coding` for git repos (auto-discovery)
   - Merges YAML entries with discovered entries (YAML takes precedence)
   - Validates the merged schema
   - Stores result in `_cache` with timestamp

2. **Subsequent Calls (within TTL)**: Returns cached registry
   - Check if cache is fresh (< CACHE_TTL seconds old)
   - Return `_cache` directly (no disk I/O, no YAML parsing)

3. **After TTL Expiry**: Automatic cache invalidation
   - Next call detects stale cache (> CACHE_TTL seconds old)
   - Rebuilds registry from disk
   - Updates `_cache` and `_cache_at`

4. **Manual Reload**: `get_registry(force=True)` bypasses cache
   - Forces immediate rebuild from disk
   - Used in tests and manual reload triggers
   - Takes effect instantly (no wait for TTL)

## Design Principles

### 1. YAML Precedence Rule

Once an entry exists in `registry.yaml` (written by the self-modification agent), it is **never overwritten** by auto-discovery. The `_merge()` function enforces this:

```python
# YAML enriches the discovered entry - YAML values take precedence
base = dict(merged[slug])
base.update({k: v for k, v in entry.items() if v is not None})
```

This protects agent-authored entries from being clobbered by automatic scanning.

### 2. Cache Invalidation

The cache is invalidated on:
- **Time-based**: Cache expires after `CACHE_TTL` (5 minutes)
- **Manual**: `get_registry(force=True)` forces immediate rebuild
- **Implicit**: Cache is `None` on first call or after module reload

### 3. Schema Validation

Every rebuild validates the registry schema before returning:
- Required fields: `description`, `aliases`, `intent_support`
- Optional fields: `cluster`, `namespace`, `repo_path`, `argocd_app`, `sla_hours`
- Type checking for all fields
- Alias validation (non-empty strings)
- Intent type validation (must be known intents)

## Usage Patterns

### Standard Usage (Automatic)

```python
from registry import get_registry

# First call: builds registry (expensive)
registry1 = get_registry()

# Subsequent calls within 5 minutes: returns cached registry (fast)
registry2 = get_registry()
```

### Manual Reload

```python
from registry import get_registry

# Force reload to pick up changes immediately
updated_registry = get_registry(force=True)
```

### Project Lookup

```python
from registry import get_project

# Get single project (respects cache TTL)
project = get_project("whisper-stt")

# Returns None if not found
if project:
    aliases = project.get("aliases", [])
    cluster = project.get("cluster")
```

## Self-Modification Integration

### Agent Workflow

1. **Modify Registry**: Agent writes to `config/registry.yaml`
   ```python
   # Agent adds new alias to project
   registry["projects"]["whisper-stt"]["aliases"].append("speech-service")
   REGISTRY_PATH.write_text(yaml.dump(registry))
   ```

2. **Dispatch Again**: Same utterance re-dispatched
   ```python
   # The deterministic router asks the shared loader for its current snapshot
   # on each routing call.  The normal call uses the five-minute TTL cache.
   registry = get_registry()

   # A self-modification workflow can request an immediate reload instead.
   registry = get_registry(force=True)  # Picks up the new alias now
   ```

3. **Routing**: Router recognizes new alias
   ```python
   # "check speech-service status" now routes to whisper-stt
   project = get_project("whisper-stt")
   assert "speech-service" in project["aliases"]
   ```

### Cache Coherence

- **Single Process**: Cache is in-memory, same process sees updated registry immediately after reload
- **Multiple Processes**: Each process has its own cache, TTL ensures eventual consistency
- **Long-lived Router**: The deterministic router refreshes its reference from
  `get_registry()` for each routing call, so it does not pin the snapshot that
  existed when the server started
- **Force Reload**: Agents use `force=True` to bypass cache and see changes immediately

## Testing

### Test Coverage

The test suite (`tests/test_registry_hot_reload.py`) covers:

1. **Basic Hot-Reload**: Alias modification is picked up by `get_registry(force=True)`
2. **Cache Invalidation**: Cache respects TTL and `force=True` bypass
3. **Dispatch Integration**: Routing recognizes new aliases without restart
4. **No-Restart Routing**: A reloaded alias can build a fetch context in the same process
5. **Idempotency**: `test_registry_hot_reload_idempotent()` runs the mutation twice in one session

### Running Tests

```bash
# Run all hot-reload tests
PYTHONPATH=. python tests/test_registry_hot_reload.py

# Run with pytest
pytest tests/test_registry_hot_reload.py -v

# Test specific function
pytest tests/test_registry_hot_reload.py::test_registry_hot_reload_idempotent -v
```

### Test Idempotency

All tests are designed to be **idempotent**:
- **Unique Artifacts**: UUID-based aliases prevent collisions between rapid runs
- **State Capture**: Original registry bytes and permission bits are captured before modification
- **Atomic Publication**: `atomic_write()` makes each replacement visible as a complete YAML file
- **Guaranteed Cleanup**: `finally` blocks restore the exact original file even on failure
- **Verification**: Tests verify file bytes, permissions, and the forced in-memory snapshot after cleanup

Example test structure:

```python
original_yaml = REGISTRY_PATH.read_bytes()  # Capture exact state
try:
    # Modify registry
    atomic_write(REGISTRY_PATH, modified_yaml)
    # Test hot-reload
    reloaded = get_registry(force=True)
    assert "test-alias" in reloaded["projects"]["test"]["aliases"]
finally:
    atomic_write(REGISTRY_PATH, original_yaml, mode="wb")  # Always restore
    get_registry(force=True)  # Clear cache
```

### Test Results

When tests pass, you should see:

```
Results: 5/5 tests passed

✓ All registry hot-reload tests PASSED

Conclusion:
- config/registry.yaml aliases can be modified ✓
- Changes are picked up via get_registry(force=True) ✓
- Original state is properly restored ✓
- Dispatch routing would recognize new aliases ✓
- Hot-reload works without server restart ✓
- Tests are idempotent (no side effects) ✓
- Atomic replacement and cleanup preserve file integrity ✓
```

## Edge Cases and Safety

### File Integrity

Tests verify file integrity before and after modifications:

```python
def _verify_file_integrity() -> bool:
    """Verify registry file is readable and valid YAML."""
    try:
        content = REGISTRY_PATH.read_text()
        yaml.safe_load(content)
        return True
    except (OSError, yaml.YAMLError):
        return False
```

### Backup Mechanism

Critical operations create timestamped backups:

```python
backup_path = REGISTRY_PATH.with_suffix(f".yaml.backup-{int(time.time())}")
shutil.copy2(REGISTRY_PATH, backup_path)
```

If a test crashes catastrophically, the backup can be used for manual recovery.

### Concurrent Access

The production registry lock serializes cache reads and force-rebuilds, while
`atomic_write()` serializes same-path writers and publishes complete files.
The real-file mutation tests also use a re-entrant module lock so their
backup/modify/reload/restore sections cannot race within one test process.
The suite does not merge independent concurrent writers; the CI entry point
runs these repository-file tests serially.

### Permission Errors

The idempotency test records and restores the registry's permission bits after
each atomic replacement. A checkout whose registry directory is not writable
fails with the underlying `PermissionError`; the test does not weaken
permissions or leave a backup behind as a workaround.

## Performance Considerations

### Cache Hit Path

- **No Disk I/O**: Returns cached dict directly
- **No YAML Parsing**: Cache stores pre-parsed dict
- **No Validation**: Schema already validated on build
- **Fast**: Essentially a dict lookup

### Cache Miss Path

- **Disk I/O**: Reads `config/registry.yaml`
- **YAML Parsing**: Parses YAML into dict
- **Git Discovery**: Scans `/home/coding` for git repos
- **Merge Operation**: Merges YAML and discovered entries
- **Schema Validation**: Validates entire registry
- **Slower**: But only happens once per TTL period

### Tuning

- **`CACHE_TTL`**: Adjust for your use case
  - Shorter TTL: Faster hot-reload, more frequent rebuilds
  - Longer TTL: Better performance, slower hot-reload
- **Default (300s)**: Good balance for self-modification workflows

## Troubleshooting

### Changes Not Picked Up

**Problem**: Modified `config/registry.yaml` but changes aren't visible.

**Solutions**:
1. Force reload: `get_registry(force=True)`
2. Wait for TTL expiry (5 minutes)
3. Check file permissions: Ensure server can read `config/registry.yaml`
4. Verify YAML syntax: `python -c "import yaml; yaml.safe_load(open('config/registry.yaml'))"`

### Cache Corruption

**Problem**: Cache returns unexpected or corrupted data.

**Solutions**:
1. Force rebuild: `get_registry(force=True)`
2. Restart server process (clears in-memory cache)
3. Verify YAML file integrity
4. Check for concurrent modifications

### Validation Errors

**Problem**: `RegistryValidationError` raised on reload.

**Solutions**:
1. Check schema requirements in `src/registry.py`
2. Verify required fields: `description`, `aliases`, `intent_support`
3. Check field types match schema
4. Validate intent types are known

### Test Failures

**Problem**: Hot-reload tests fail intermittently.

**Solutions**:
1. Check for leftover test aliases in `config/registry.yaml`
2. Verify file permissions allow read/write
3. Restore from backup if available: `config/registry.yaml.backup-*`
4. Run tests with increased verbosity: `-v` or `-vv`

## CI/CD Integration

The repository has no checked-in CI workflow. `scripts/run_hot_reload_tests.sh`
is the stable CI/local entry point and already includes
`tests/test_registry_hot_reload.py`; pytest discovery also includes it in the
normal `tests/` suite. The script keeps repository-file tests serial and the
external dispatch smoke test opt-in because it requires a running server.

## Future Enhancements

### Potential Improvements

1. **File Watching**: Use inotify to automatically reload on file changes
   ```python
   from watchdog.observers import Observer
   from watchdog.events import FileSystemEventHandler
   ```

2. **Selective Invalidation**: Cache individual projects instead of full registry
   ```python
   _project_cache: dict[str, dict] = {}
   ```

3. **Versioning**: Track registry version for cache coherence
   ```python
   _registry_version: int = 0
   ```

4. **Diff-Based Updates**: Apply only changed entries instead of full rebuild
   ```python
   def _apply_diff(old: dict, new: dict) -> dict:
       # Merge only changed keys
   ```

### Migration Path

Any changes to the hot-reload mechanism must:
1. Maintain backward compatibility with existing `config/registry.yaml`
2. Preserve YAML precedence rule
3. Keep TTL-based cache invalidation as fallback
4. Add tests for new behavior
5. Update this documentation

## Related Documentation

- **Self-Modification**: `docs/notes/self-modification-workflow.md`
- **Registry Schema**: `config/registry.yaml`
- **Testing**: `tests/test_registry_hot_reload.py`
- **Implementation**: `src/registry.py`

## Summary

The registry hot-reload mechanism provides:

- **No Server Restart**: Changes take effect immediately or within 5 minutes
- **Schema Validation**: Ensures registry integrity on every rebuild
- **YAML Precedence**: Protects agent-authored entries from auto-discovery
- **Cache Performance**: Fast cache hits, periodic cache misses for updates
- **Test Coverage**: Comprehensive tests for idempotency and edge cases
- **Production-Ready**: Handles concurrent access, file errors, and validation failures

This enables truly dynamic self-modification workflows where agents can evolve the system configuration without manual intervention or service interruption.
