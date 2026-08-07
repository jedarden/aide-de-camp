# Implementation Summary: File Permission and Registry Error Handling

## Task: adc-12z0i

Implemented comprehensive error handling for file permission issues and malformed registry files in the hot-reload system.

## Changes Made

### 1. Custom Exception Classes (src/components/hot_reload.py)

Added four new exception classes that inherit from `HotReloadError`:

- **`PermissionDeniedError`**: Raised when file permission is denied. Includes file path, operation context, and actionable guidance (check permissions with `ls -la`).
- **`RegistryNotFoundError`**: Raised when registry file doesn't exist. Includes file path and guidance to verify file location.
- **`RegistryParseError`**: Raised when registry parsing fails. Includes file path, parse error details (line/column when available), content preview, and validation guidance.
- **`EmptyRegistryError`**: Raised when registry file is empty. Includes file path and guidance to ensure valid content.

### 2. Enhanced Error Handling

Updated key methods to use custom exceptions with enhanced error messages:

- **`_read_file_with_retry()`**: Now raises `PermissionDeniedError` and `RegistryNotFoundError` instead of generic exceptions. Added detection of empty registry files with WARNING level logging.
- **`_get_mtime_with_retry()`**: Enhanced to raise `PermissionDeniedError` and `RegistryNotFoundError` with clear guidance.
- **`register_prompt()`**: Updated to use custom exceptions for permission and not found errors.
- **`register_config()`**: Enhanced to detect empty files before parsing and use `RegistryParseError` for parse failures.
- **`force_reload()`**: Added error handling for permission and parse errors during forced reloads.

### 3. JSON Parsing Support

Added JSON parsing capability alongside existing YAML support:

- **`_parse_json()`**: New static method that parses JSON with detailed error messages including line and column numbers.
- Updated `_parsers` dictionary to include `.json` extension support.

### 4. Enhanced Logging

All errors are now logged at appropriate levels:

- **WARNING level**: Transient errors during retry attempts
- **ERROR level**: Final failures after all retries exhausted
- Error messages include file paths and actionable guidance

### 5. Comprehensive Test Suite

Created `tests/test_permission_and_registry_errors.py` with 7 tests:

1. **test_permission_error_on_readonly_file**: Verifies `PermissionDeniedError` is raised with file path and actionable guidance
2. **test_missing_registry_file_error**: Verifies `RegistryNotFoundError` is raised correctly
3. **test_malformed_yaml_parse_error**: Verifies `RegistryParseError` for YAML with line/column details
4. **test_malformed_json_parse_error**: Verifies `RegistryParseError` for JSON with line/column details
5. **test_empty_registry_error**: Verifies `EmptyRegistryError` for empty files
6. **test_permission_denied_on_force_reload**: Verifies permission errors during force reload
7. **test_error_logging_levels**: Verifies appropriate logging levels (WARNING/ERROR)

All 7 tests pass successfully.

## Acceptance Criteria Met

✅ Hot-reload catches PermissionError and provides clear error message
✅ Malformed JSON/YAML in registry raises specific error with file path and parse details
✅ Missing registry files handled gracefully with clear error
✅ All permission/registry errors logged at appropriate level (WARNING/ERROR)
✅ At least 3 new tests covering these scenarios (7 tests implemented)
✅ Error messages include file paths and actionable guidance

## Edge Cases Covered

1. ✅ Readonly files that cannot be written → `PermissionDeniedError`
2. ✅ Permission denied when accessing registry → `PermissionDeniedError`
3. ✅ Missing registry files → `RegistryNotFoundError`
4. ✅ Malformed YAML in registry files → `RegistryParseError` with line/column
5. ✅ Malformed JSON in registry files → `RegistryParseError` with line/column
6. ✅ Empty registry data → `EmptyRegistryError`

## Files Modified

- `src/components/hot_reload.py` - Core implementation
- `tests/test_permission_and_registry_errors.py` - New test file

## Backward Compatibility

All changes are backward compatible. Existing code that catches generic `PermissionError`, `FileNotFoundError`, or `ValueError` will continue to work, as the custom exceptions inherit from standard exceptions where appropriate.
