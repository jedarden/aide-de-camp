# whisper-stt Deployment Data Persistence Module

## Overview

This module provides robust data persistence functionality for whisper-stt deployment data, matching the pbx-web format structure. It handles JSON serialization, validation, backup creation, and error handling.

## Features

- ✅ **Schema Validation**: Ensures data matches required structure before writing
- ✅ **Automatic Backups**: Creates timestamped backups before overwriting existing files
- ✅ **Custom JSON Encoder**: Handles datetime objects, enums, and complex nested structures
- ✅ **Error Handling**: Comprehensive error handling for invalid data, file operations, and serialization issues
- ✅ **Flexible Formatting**: Supports both pretty-printed and compact JSON output
- ✅ **Data Verification**: Built-in verification tools to validate stored data

## Installation

The module is self-contained and requires only Python 3.7+ standard library dependencies:

```python
from persist_whisper_stt_deployment import (
    persist_deployment_data,
    load_deployment_data,
    validate_and_persist
)
```

## Quick Start

### Basic Usage

```python
# Persist deployment data with default settings
from persist_whisper_stt_deployment import persist_deployment_data

deployment_data = {
    "metadata": {
        "generated_at": "2026-08-06T12:00:00Z",
        "data_period_start": "2026-07-07T00:00:00Z",
        "data_period_end": "2026-08-06T12:00:00Z",
        "services": ["whisper-stt"],
        "clusters": ["ardenone-cluster"],
        "data_sources": ["kubernetes"]
    },
    "summary": {
        "total_deployments_last_30_days": 5,
        "whisper_stt_deployments": 5,
        "successful_deployments": 5,
        "failed_or_scaled_down": 0,
        "data_coverage": "100%",
        "gaps_detected": False,
        "largest_gap_days": 0
    }
}

# Persist with default file path (whisper-stt-deployments-30d.json)
success = persist_deployment_data(deployment_data)
```

### Custom File Path

```python
# Persist to custom location
success = persist_deployment_data(
    deployment_data,
    file_path="/custom/path/deployments.json",
    backup_enabled=True,
    pretty_print=True
)
```

### Load and Validate

```python
from persist_whisper_stt_deployment import load_deployment_data

# Load with automatic validation
data = load_deployment_data("whisper-stt-deployments-30d.json")

# Load without validation (faster for trusted data)
data = load_deployment_data("whisper-stt-deployments-30d.json", validate_on_load=False)
```

### Convenience Function

```python
from persist_whisper_stt_deployment import validate_and_persist

# One-step validation and persistence
success = validate_and_persist(deployment_data, "output.json")
```

## API Reference

### persist_deployment_data()

```python
def persist_deployment_data(
    data: Dict[str, Any],
    file_path: Union[str, Path] = "whisper-stt-deployments-30d.json",
    backup_enabled: bool = True,
    pretty_print: bool = True,
    validate_before_write: bool = True
) -> bool
```

**Parameters:**
- `data`: Deployment data dictionary matching the schema
- `file_path`: Target file path (default: `whisper-stt-deployments-30d.json`)
- `backup_enabled`: Whether to create backup of existing file (default: `True`)
- `pretty_print`: Whether to format JSON with indentation (default: `True`)
- `validate_before_write`: Whether to validate data structure (default: `True`)

**Returns:** `True` if persistence succeeded, `False` otherwise

**Raises:**
- `ValueError`: If data validation fails (when `validate_before_write=True`)
- `OSError`: If file operations fail
- `TypeError`: If data contains non-serializable types

### load_deployment_data()

```python
def load_deployment_data(
    file_path: Union[str, Path] = "whisper-stt-deployments-30d.json",
    validate_on_load: bool = True
) -> Optional[Dict[str, Any]]
```

**Parameters:**
- `file_path`: Path to JSON file (default: `whisper-stt-deployments-30d.json`)
- `validate_on_load`: Whether to validate data structure (default: `True`)

**Returns:** Deployment data dictionary, or `None` if loading failed

**Raises:**
- `FileNotFoundError`: If file does not exist
- `json.JSONDecodeError`: If file contains invalid JSON
- `ValueError`: If data validation fails (when `validate_on_load=True`)

### verify_json_file()

```python
def verify_json_file(file_path: Union[str, Path]) -> Dict[str, Any]
```

Verifies that a JSON file is valid and contains deployment data.

**Returns:**
```python
{
    "valid": bool,
    "readable": bool,
    "size_bytes": int,
    "error": Optional[str],
    "structure_ok": bool,
    "missing_keys": List[str]
}
```

## Data Schema

### Required Top-Level Structure

```python
{
    "metadata": {
        "generated_at": str,           # ISO 8601 timestamp
        "data_period_start": str,      # ISO 8601 timestamp
        "data_period_end": str,        # ISO 8601 timestamp
        "services": List[str],
        "clusters": List[str],
        "data_sources": List[str]
    },
    "summary": {
        "total_deployments_last_30_days": int,
        "whisper_stt_deployments": int,
        "successful_deployments": int,
        "failed_or_scaled_down": int,
        "data_coverage": str,
        "gaps_detected": bool,
        "largest_gap_days": int
    }
    # ... additional optional sections
}
```

### Optional Sections

- `argo_workflows`: Argo Workflow template and run data
- `argo_cd`: ArgoCD application management data
- `cluster_deployments`: Kubernetes deployment data
- `pod_health`: Pod health metrics
- `resources`: Resource limits and requests
- `storage`: PVC/storage information
- `error_incidents`: Error incident tracking
- `notes`: Array of informational notes

## Error Handling

### Validation Errors

```python
try:
    persist_deployment_data(invalid_data)
except ValueError as e:
    print(f"Validation failed: {e}")
    # Handles: missing required fields, invalid timestamps, etc.
```

### File Operation Errors

```python
try:
    persist_deployment_data(data, "/protected/path/file.json")
except OSError as e:
    print(f"File operation failed: {e}")
    # Handles: permission errors, disk full, etc.
```

### Serialization Errors

```python
try:
    persist_deployment_data(data)
except TypeError as e:
    print(f"Serialization failed: {e}")
    # Handles: non-serializable types, circular references, etc.
```

## Backup System

The module automatically creates timestamped backups before overwriting existing files:

- **Location**: `.backups/` directory
- **Format**: `{filename}_backup_{timestamp}{ext}`
- **Retention**: Keeps the 5 most recent backups per file
- **Example**: `whisper-stt-deployments-30d_backup_20260806_120432.json`

### Backup Management

```python
# Disable backup creation
persist_deployment_data(data, backup_enabled=False)
```

## Custom JSON Encoder

The `DeploymentDataEncoder` handles special types:

- **datetime**: Converted to ISO 8601 format with 'Z' suffix
- **Enum**: Uses the enum's value
- **Path**: Converted to string
- **dataclasses**: Serialized to dictionaries
- **Objects with `to_dict()`**: Uses the custom method

### Example with datetime objects

```python
from datetime import datetime
from persist_whisper_stt_deployment import persist_deployment_data

data = {
    "metadata": {
        "generated_at": datetime.now(),  # Automatically serialized
        "data_period_start": "2026-07-07T00:00:00Z",
        "data_period_end": "2026-08-06T12:00:00Z",
        "services": ["whisper-stt"],
        "clusters": ["ardenone-cluster"],
        "data_sources": ["kubernetes"]
    },
    "summary": {
        "total_deployments_last_30_days": 1,
        "whisper_stt_deployments": 1,
        "successful_deployments": 1,
        "failed_or_scaled_down": 0,
        "data_coverage": "100%",
        "gaps_detected": False,
        "largest_gap_days": 0
    }
}

success = persist_deployment_data(data)
```

## Testing

Run the comprehensive test suite:

```bash
python test_persistence_edge_cases.py
```

Test with real whisper-stt data:

```bash
python test_persistence_real_data.py
```

Run the built-in demo:

```bash
python persist_whisper_stt_deployment.py
```

## File Format Comparison

### Pretty Print (default)

```json
{
  "metadata": {
    "generated_at": "2026-08-06T12:00:00Z",
    "data_period_start": "2026-07-07T00:00:00Z",
    ...
  },
  "summary": {
    "total_deployments_last_30_days": 5,
    ...
  }
}
```

### Compact Format

```json
{"metadata":{"generated_at":"2026-08-06T12:00:00Z","data_period_start":"2026-07-07T00:00:00Z",...},"summary":{"total_deployments_last_30_days":5,...}}
```

## Best Practices

1. **Always validate**: Keep `validate_before_write=True` for production code
2. **Enable backups**: Use `backup_enabled=True` for important data files
3. **Use pretty print**: Set `pretty_print=True` for human-readable files ( Git versioning)
4. **Handle exceptions**: Always wrap persistence calls in try-except blocks
5. **Verify after write**: Use `verify_json_file()` after critical writes

### Example Production Usage

```python
from persist_whisper_stt_deployment import persist_deployment_data, verify_json_file

def save_deployment_data(data, output_path):
    """Save deployment data with proper error handling."""
    try:
        success = persist_deployment_data(
            data,
            file_path=output_path,
            backup_enabled=True,
            pretty_print=True,
            validate_before_write=True
        )

        if success:
            verification = verify_json_file(output_path)
            if verification['valid']:
                print(f"✓ Data successfully saved to {output_path}")
                return True
            else:
                print(f"✗ File verification failed: {verification['error']}")
                return False
        else:
            print("✗ Persistence failed")
            return False

    except ValueError as e:
        print(f"✗ Validation error: {e}")
        return False
    except OSError as e:
        print(f"✗ File operation error: {e}")
        return False
    except Exception as e:
        print(f"✗ Unexpected error: {e}")
        return False
```

## Integration with Schema Module

The persistence module is designed to work with the `whisper_stt_deployment_schema` module:

```python
from whisper_stt_deployment_schema import WhisperSTTDeploymentSchema, validate_deployment_data
from persist_whisper_stt_deployment import persist_deployment_data

# Validate using schema
validation_result = validate_deployment_data(data)
if validation_result["valid"]:
    # Persist validated data
    persist_deployment_data(data)
else:
    print(f"Validation errors: {validation_result['errors']}")
```

## Troubleshooting

### Common Issues

**Issue**: `'bool' object is not callable`
**Cause**: Parameter shadowing (fixed in current version)
**Solution**: Update to latest version

**Issue**: `Invalid timestamp format`
**Cause**: Timestamps not in ISO 8601 format
**Solution**: Use `datetime.now().isoformat() + 'Z'` format

**Issue**: `Missing required top-level key`
**Cause**: Data missing required fields
**Solution**: Ensure both `metadata` and `summary` sections are present

**Issue**: Backups not created
**Cause**: File doesn't exist yet or `backup_enabled=False`
**Solution**: Backups only created when overwriting existing files

## Version History

- **v1.0** (2026-08-06): Initial implementation
  - Schema validation
  - Automatic backups
  - Custom JSON encoder
  - Comprehensive error handling

## License

Part of the aide-de-camp project. See project LICENSE for details.

## Contributing

When adding new features:

1. Add comprehensive tests
2. Update this documentation
3. Ensure backward compatibility
4. Test with real deployment data

## Related Modules

- `whisper_stt_deployment_schema.py`: Schema definitions and validation
- `test_persistence_edge_cases.py`: Comprehensive test suite
- `test_persistence_real_data.py`: Real data conversion tests
