# Atomic Write Utility — Usage Guide

Comprehensive guide for using the enhanced `atomic_write` utility with error handling, rollback support, and cleanup verification.

For the cross-codebase cleanup inventory, invariants, and verification checklist,
see [Cleanup Operations Reference](cleanup-operations-reference.md).

## Overview

The atomic write utility provides safe file operations that prevent data corruption by using temporary files and atomic renames. This ensures readers always see either the complete old content or the complete new content — never a partial write.

## Features

- **Atomic writes**: `os.replace()` guarantees atomic operations on same filesystem
- **Rollback support**: Context manager with automatic cleanup on errors
- **Backup creation**: Optional `.bak` backup of original files
- **Validation**: Optional pre-write validation function
- **Comprehensive logging**: All operations logged at appropriate levels
- **Cleanup verification**: Automatic detection and cleanup of orphaned temp files
- **Error handling**: Proper categorization of error types with cleanup on all paths

## Basic Usage

### Simple Atomic Write

```python
from src.utils.atomic_write import atomic_write

# Text mode (default)
atomic_write('/path/to/config.json', '{"key": "value"}')

# Binary mode
atomic_write('/path/to/data.bin', b'\x00\x01\x02\x03', mode='wb')

# With pathlib.Path
from pathlib import Path
atomic_write(Path('/path/to/file.txt'), 'content')
```

### With Backup Creation

```python
# Creates config.json.bak before overwriting
backup_path = atomic_write('/path/to/config.json', new_content, create_backup=True)

# backup_path is Path to backup file, or None if original didn't exist
if backup_path:
    print(f"Backup created at: {backup_path}")
```

### With Validation

```python
import json

def is_valid_json(content: str) -> bool:
    """Validate JSON content before writing."""
    try:
        json.loads(content)
        return True
    except json.JSONDecodeError:
        return False

# Only writes if validation passes
atomic_write('/path/to/config.json', content, validate_fn=is_valid_json)
```

## Rollback Context Manager

The `atomic_write_rollback` context manager provides automatic rollback on errors:

```python
from src.utils.atomic_write import atomic_write_rollback

try:
    with atomic_write_rollback('/path/to/data.txt') as temp_path:
        # Write to temp_path (it's a Path object)
        processed_data = process_raw_data(raw_data)
        temp_path.write_text(processed_data)
    # File is now atomically updated at target path
except ValueError as e:
    # Original file is preserved, temp file cleaned up automatically
    print(f"Processing failed: {e}")
```

### Binary Mode with Rollback

```python
with atomic_write_rollback('/path/to/image.png', mode='wb') as temp_path:
    # Process and write binary data
    temp_path.write_bytes(processed_image_data)
```

### Complex Processing with Rollback

```python
def update_config_with_validation(config_path: Path, updates: dict):
    """Update config file with validation and automatic rollback."""
    import json
    
    def validate_config(content: str) -> bool:
        """Ensure config is valid JSON and has required fields."""
        try:
            data = json.loads(content)
            return 'database' in data and 'api_key' in data
        except json.JSONDecodeError:
            return False
    
    # Read existing config
    current_data = json.loads(config_path.read_text())
    current_data.update(updates)
    new_content = json.dumps(current_data, indent=2)
    
    # Atomic write with validation and backup
    with atomic_write_rollback(config_path) as temp_path:
        temp_path.write_text(new_content)
        
        # Validate before completing
        if not validate_config(new_content):
            raise ValueError("Invalid config: missing required fields")
```

## Error Handling Patterns

### Handling Permission Errors

```python
from src.utils.atomic_write import atomic_write
import logging

try:
    atomic_write('/readonly/file.txt', 'content')
except PermissionError as e:
    logging.error(f"Permission denied: {e}")
    # Handle permission error (notify user, try alternative location, etc.)
except OSError as e:
    logging.error(f"Filesystem error: {e}")
    # Handle other filesystem errors (disk full, etc.)
```

### Handling Validation Failures

```python
def safe_write_with_validation(filepath: Path, content: str, validator):
    """Write with validation and proper error handling."""
    try:
        atomic_write(filepath, content, validate_fn=validator)
        return True
    except ValueError as e:
        print(f"Validation failed: {e}")
        return False
    except (PermissionError, OSError) as e:
        print(f"Write failed: {e}")
        return False
```

## Cleanup Operations

### Manual Cleanup of Orphaned Temp Files

```python
from src.utils.atomic_write import cleanup_orphaned_temp_files

# Clean up all .tmp files in a directory
cleaned_count = cleanup_orphaned_temp_files('/tmp', '*.tmp')
print(f"Cleaned up {cleaned_count} orphaned temp files")

# Clean up specific pattern
cleaned_count = cleanup_orphaned_temp_files('/var/cache', 'atomic_write_*.tmp')
```

### Startup Cleanup Pattern

```python
def cleanup_on_startup(directories: list[Path]):
    """Clean up orphaned temp files on application startup."""
    total_cleaned = 0
    for directory in directories:
        if directory.exists():
            count = cleanup_orphaned_temp_files(directory, '*.tmp')
            total_cleaned += count
            print(f"Cleaned {count} temp files from {directory}")
    return total_cleaned
```

## Best Practices

### 1. Always Use Atomic Writes for Critical Files

```python
# ❌ BAD: Not atomic
with open('config.json', 'w') as f:
    f.write(json.dumps(config))  # Can corrupt if process crashes

# ✅ GOOD: Atomic write
atomic_write('config.json', json.dumps(config))
```

### 2. Use Validation for Structured Data

```python
def validate_json(content: str) -> bool:
    try:
        json.loads(content)
        return True
    except json.JSONDecodeError:
        return False

atomic_write('data.json', json_content, validate_fn=validate_json)
```

### 3. Create Backups for Important Configurations

```python
# Always backup critical config files before updates
atomic_write('production_config.json', new_config, create_backup=True)
```

### 4. Use Context Manager for Complex Operations

```python
# ✅ GOOD: Context manager with automatic rollback
with atomic_write_rollback('data.csv') as temp:
    temp.write_text(process_csv_data(raw_data))
```

### 5. Handle Errors Appropriately

```python
try:
    atomic_write(filepath, content)
except PermissionError:
    # Handle permission issues
    notify_user(f"Cannot write to {filepath}")
except OSError as e:
    # Handle filesystem errors
    if "No space left" in str(e):
        notify_user("Disk is full")
    else:
        notify_user(f"Filesystem error: {e}")
```

### 6. Use Logging for Debugging

The utility includes comprehensive logging. Configure log level:

```python
import logging
logging.basicConfig(level=logging.INFO)

# All atomic_write operations now log:
# - INFO: Successful operations
# - WARNING: Validation failures, cleanup issues
# - ERROR: Write failures, permission errors
```

## Error Scenarios Covered

### 1. Permission Denied
```python
# Directory is read-only
atomic_write('/readonly/file.txt', 'content')
# Raises: PermissionError with detailed message
# Logs: ERROR with permission details
```

### 2. Disk Full
```python
# Disk has no space left
atomic_write('/full_disk/file.txt', large_content)
# Raises: OSError with ENOSPC
# Logs: ERROR with disk full message
# Cleanup: Temp file is removed
```

### 3. Validation Failure
```python
def validator(content): return False

atomic_write('file.txt', 'content', validate_fn=validator)
# Raises: ValueError with validation failure message
# Logs: WARNING about validation failure
# Result: Original file unchanged
```

### 4. Invalid Content Type
```python
# Wrong content type for mode
atomic_write('file.txt', b'bytes', mode='w')
# Raises: TypeError with mode mismatch details
# Logs: ERROR about type validation
```

### 5. Concurrent Access
```python
# Multiple processes writing same file
# Only one wins, but all writes are atomic
# No partial writes or corruption possible
```

## Testing

The utility includes 32 comprehensive tests covering:
- Basic atomic operations
- Backup creation and preservation
- Validation scenarios
- Rollback context manager behavior
- Error scenarios (disk full, permission denied, etc.)
- Orphaned temp file cleanup
- Logging verification
- Edge cases (empty content, Unicode, binary mode)

Run tests:
```bash
pytest tests/test_atomic_write.py -v
```

## Performance Considerations

1. **Temp file overhead**: Creating temp files has minimal overhead (~1-2ms for small files)
2. **fsync overhead**: `fsync()` adds durability but may slow down writes by 10-20%
3. **Large files**: For very large files (>1GB), consider chunked writes with custom implementation
4. **Network filesystems**: Atomic operations work on same filesystem only

## Migration from Non-Atomic Writes

### Before (Non-Atomic)
```python
with open('config.json', 'w') as f:
    f.write(json.dumps(config))
```

### After (Atomic)
```python
atomic_write('config.json', json.dumps(config))
```

### With Additional Safety
```python
atomic_write(
    'config.json', 
    json.dumps(config),
    create_backup=True,
    validate_fn=lambda c: json.loads(c) is not None
)
```

## Troubleshooting

### Problem: "No orphaned temp files" warning
**Solution**: Normal — verification is extra safety, warnings are informational

### Problem: Validation fails unexpectedly
**Solution**: Check validator function returns bool, not truthy/falsy values

### Problem: Backup file not created
**Solution**: Only created if original file exists and `create_backup=True`

### Problem: Permission errors on NFS mounts
**Solution**: Ensure write permissions on directory, not just file

## Thread Safety

The utility is thread-safe for concurrent writes to different files. For concurrent writes to the same file, only one write will succeed (atomic behavior), but no data corruption occurs.

## Logging Examples

```python
# Enable DEBUG logging for detailed operation tracking
import logging
logging.basicConfig(level=logging.DEBUG)

# Logs include:
# - Operation ID for tracking
# - File paths and temp file locations
# - Success/failure status
# - Cleanup operations
# - Error details with stack traces
```

## Advanced Usage

### Custom Error Handling
```python
from src.utils.atomic_write import AtomicWriteError, AtomicWriteRollbackError

try:
    with atomic_write_rollback('critical.dat') as temp:
        temp.write_bytes(process_data())
except AtomicWriteRollbackError as e:
    # Rollback itself failed
    emergency_cleanup()
except AtomicWriteError as e:
    # General atomic write error
    handle_write_error(e)
```

### Batch Operations
```python
def atomic_write_batch(files: dict[Path, str]):
    """Write multiple files atomically with collective error handling."""
    failures = []
    
    for filepath, content in files.items():
        try:
            atomic_write(filepath, content, create_backup=True)
        except Exception as e:
            failures.append((filepath, str(e)))
    
    if failures:
        print(f"Failed to write {len(failures)} files:")
        for path, error in failures:
            print(f"  {path}: {error}")
        return False
    return True
```

## Summary

The enhanced atomic write utility provides:
- ✅ Safe, atomic file operations
- ✅ Automatic rollback on errors
- ✅ Backup creation for critical files
- ✅ Content validation before write
- ✅ Comprehensive error handling and logging
- ✅ Temp file cleanup verification
- ✅ Support for text and binary modes
- ✅ Extensive test coverage (32 tests)

Use it for any file write operation where data integrity matters — configuration files, databases, cache files, logs, etc.
