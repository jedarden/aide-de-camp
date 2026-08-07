# Atomic File Operations Audit

**Date:** 2026-08-07
**Scope:** Audit all atomic file operations in aide-de-camp codebase
**Goal:** Verify all atomic file operations use centralized atomic_write utility

## Summary

✅ **PASSED:** All atomic file operations now use the centralized `atomic_write` utility from `src/utils/atomic_write.py`.

## Files Using atomic_write (Correct Implementation)

1. **src/memory/store.py** (line 203)
   - Uses `atomic_write(self.file_path, json.dumps(self._data, indent=2))`
   - Properly persists user memory with atomic overwrites

2. **src/persistence/deployment_persistence.py** (line 179)
   - Uses `atomic_write(filepath, json.dumps(data_dict, ...))`
   - Properly persists deployment data with atomic overwrites

3. **src/calculate_deployment_metrics.py** (line 178)
   - Uses `atomic_write(output_path, json.dumps(results, indent=2))`
   - Properly persists calculated metrics with atomic overwrites

4. **src/cli/config.py** (lines 78, 121) - FIXED
   - Now uses `atomic_write(self.config_file, ''.join(new_lines))`
   - Fixed from inline direct write pattern

## Legitimate Non-Atomic Patterns

These patterns are NOT violations and are appropriate for their use case:

1. **src/confirmations/confirmed_deletions.py** (lines 100-103)
   - Uses append mode (`open(..., "a")`) for JSONL log file
   - This is the correct pattern for append-only logs
   - Each line is a self-contained JSON record
   - Uses `flush()` and `fsync()` for durability
   - Not an atomic overwrite scenario

2. **src/cli/commands.py** (line 118)
   - Uses `sys.stdout.write()` for console output
   - Not a file persistence operation

## Grep Patterns for Future Violation Detection

Add these to CI/CD or pre-commit hooks to catch future violations:

```bash
# Pattern 1: Direct file writes that should use atomic_write
# This catches inline temp file + rename patterns
grep -rn 'mkstemp\|NamedTemporaryFile' --include="*.py" src/ | grep -v atomic_write.py

# Pattern 2: Direct file overwrites that should be atomic
# This catches open(..., 'w') patterns outside atomic_write.py
grep -rn 'open.*"w"\|open.*'"'w'" --include="*.py" src/ | grep -v atomic_write.py | grep -v test

# Pattern 3: Non-atomic file writes in config files
grep -rn 'writelines\|write_text\|write_bytes' --include="*.py" src/ | grep -v atomic_write.py | grep -v test | grep -v "\.pyc"
```

## Centralized Utility

**Location:** `src/utils/atomic_write.py`

**Functions:**
- `atomic_write(filepath, content, mode='w', ...)` - Atomic file write with comprehensive error handling
- `atomic_write_rollback(filepath, mode='w')` - Context manager for atomic write with automatic rollback

**Features:**
- Uses `os.replace()` for atomic operation (guaranteed atomic on same filesystem)
- Temp file creation in same directory as target (ensures same filesystem)
- Optional backup creation (`.bak` files)
- Optional validation function callback
- Retry logic with exponential backoff for transient failures
- Comprehensive error handling and logging
- Cleanup verification for orphaned temp files

## Migration Notes

When migrating inline atomic patterns to `atomic_write`:

**Before (inline pattern):**
```python
fd, temp_path = tempfile.mkstemp(dir=filepath.parent, prefix='.tmp')
try:
    os.write(fd, content.encode('utf-8'))
    os.fsync(fd)
    os.close(fd)
    os.replace(temp_path, filepath)
except:
    os.unlink(temp_path)
    raise
```

**After (using atomic_write):**
```python
atomic_write(filepath, content, mode='w')
```

## Registry Operations

No registry operations currently require atomic writes. All persistence operations use SQLite (via `aiosqlite`) or JSON files with `atomic_write`.

## Conclusion

All atomic file operations in the aide-de-camp codebase now use the centralized `atomic_write` utility. The one violation found (`src/cli/config.py`) has been fixed. A legitimate append-only log pattern in `src/confirmations/confirmed_deletions.py` was documented as appropriate for its use case.

## Recommendation

Add the grep patterns above to CI/CD or pre-commit hooks to prevent future violations from being introduced.
