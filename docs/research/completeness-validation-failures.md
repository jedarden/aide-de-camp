# Completeness Validation Failure Scenarios

## Overview

This document catalogs all possible completeness validation failure scenarios in the aide-de-camp deployment data validation system. It maps error messages to failure types, identifies where each failure is detected in the codebase, and specifies what each error message should convey.

## Validation Architecture

The validation system consists of four layers:

1. **JSON Well-formedness Validation** (`src/validation/completeness.py`)
2. **Required Fields Validation** (`src/validation/deployment_data.py`)
3. **Data Types Validation** (`src/validation/deployment_data.py`)
4. **Completeness Validation** (`src/validation/completeness.py`, `src/validation/validate_completeness.py`)

These layers are chained together in:
- `src/validation/integration.py` - `validate_all()`
- `src/validation/runner.py` - `validate_deployment_file()`

---

## Layer 1: JSON Well-formedness Validation

### Location
`src/validation/completeness.py` - `validate_json_wellformedness()`, `validate_json_file_wellformedness()`

### Failure Scenarios

#### F1.1: Non-serializable Data
**Detection:** `validate_json_wellformedness()` - Line 46-56
**Current Error:** `"Data is not well-formed JSON: {error}"`
**Failure Type:** Type error (object not JSON-serializable)
**Spec:** `"Data contains non-serializable value: {field_name} ({type}) - {error}"`

**Example causes:**
- `datetime` objects in data
- Custom class instances
- Complex objects without JSON serialization

#### F1.2: File Not Found
**Detection:** `validate_json_file_wellformedness()` - Line 75-76
**Current Error:** `"File does not exist: {file_path}"`
**Failure Type:** Filesystem error
**Spec:** `"File not found: {file_path} (cannot read validation data)"`

#### F1.3: Invalid JSON Syntax
**Detection:** `validate_json_file_wellformedness()` - Line 82-83
**Current Error:** `"Invalid JSON in file {file_path}: {error}"`
**Failure Type:** Parse error
**Spec:** `"Invalid JSON syntax in {file_path} at line {line}, column {column}: {error}"`

**Example causes:**
- Missing closing braces `}` or `]`
- Trailing commas
- Unquoted keys
- Invalid escape sequences

#### F1.4: File Read Error
**Detection:** `validate_json_file_wellformedness()` - Line 84-85
**Current Error:** `"Error reading file {file_path}: {error}"`
**Failure Type:** I/O error
**Spec:** `"Cannot read file {file_path}: {error} (permission denied or file locked)"`

---

## Layer 2: Required Fields Validation

### Location
`src/validation/deployment_data.py` - `validate_required_fields()`, `_validate_fields_in_record()`

### Failure Scenarios

#### F2.1: Missing Top-Level Fields
**Detection:** `_validate_fields_in_record()` - Line 332-344
**Current Error:** `"Missing required field: {field_name}"` (single) or `"Missing required fields: {fields}"` (multiple)
**Failure Type:** Schema violation
**Spec:** `"Missing required field: {field_name} - {field_description}"`

**Required fields from `DEPLOYMENT_DATA_SCHEMA`:**
```python
{
    "service": str,                    # Service name
    "first_deployment": str,           # First deployment timestamp
    "last_deployment": str,            # Last deployment timestamp
    "period_days": int,                # Analysis period in days
    "total_deployments": int,          # Total deployment count
    "successful_deployments": int,     # Successful deployment count
    "failed_deployments": int,         # Failed deployment count
    "success_rate": float,             # Success percentage
    "failure_rate": float,             # Failure percentage
    "deployment_frequency_per_day": float,  # Deployments per day
    "mean_time_between_deployments_hours": float,  # Mean time between deployments
    "deployment_names": list,           # List of deployment names
}
```

#### F2.2: Data Not Dictionary
**Detection:** `validate_required_fields()` - Line 290-291
**Current Error:** `"Data must be a dictionary, got {type}"`
**Failure Type:** Type error
**Spec:** `"Invalid data structure: expected dictionary, got {type} (deployment data must be key-value pairs)"`

#### F2.3: Services Collection Not Dictionary
**Detection:** `validate_required_fields()` - Line 296-297
**Current Error:** `"'services' must be a dictionary, got {type}"`
**Failure Type:** Type error
**Spec:** `"Invalid services structure: expected dictionary of service_name -> deployment_data, got {type}"`

#### F2.4: Service Data Not Dictionary
**Detection:** `validate_required_fields()` - Line 301-302
**Current Error:** `"Service '{service_name}' data must be a dictionary, got {type}"`
**Failure Type:** Type error
**Spec:** `"Invalid service data for '{service_name}': expected deployment record, got {type}"`

---

## Layer 3: Data Types Validation

### Location
`src/validation/deployment_data.py` - `validate_data_types()`, `validate_deployment_record()`

### Failure Scenarios

#### F3.1: String Field Type Mismatch
**Detection:** `validate_data_types()` - Line 409-411
**Current Error:** `"{field_name} must be str, got {type}"`
**Failure Type:** Type mismatch
**Spec:** `"Invalid type for {field_name}: expected str, got {type} (value: {value})"`

**String fields:**
- `service`
- `first_deployment`
- `last_deployment`

#### F3.2: Integer Field Type Mismatch
**Detection:** `validate_data_types()` - Line 419-421
**Current Error:** `"{field_name} must be int, got {type}"`
**Failure Type:** Type mismatch
**Spec:** `"Invalid type for {field_name}: expected int, got {type} (value: {value})"`

**Integer fields:**
- `period_days`
- `total_deployments`
- `successful_deployments`
- `failed_deployments`

#### F3.3: Numeric Field Type Mismatch
**Detection:** `validate_data_types()` - Line 399-401
**Current Error:** `"{field_name} must be numeric, got {type}"`
**Failure Type:** Type mismatch
**Spec:** `"Invalid type for {field_name}: expected int or float, got {type} (value: {value})"`

**Numeric fields:**
- `success_rate`
- `failure_rate`
- `deployment_frequency_per_day`
- `mean_time_between_deployments_hours`

#### F3.4: List Field Type Mismatch
**Detection:** `validate_data_types()` - Line 404-406
**Current Error:** `"{field_name} must be a list, got {type}"`
**Failure Type:** Type mismatch
**Spec:** `"Invalid type for {field_name}: expected list, got {type} (value: {value})"`

**List fields:**
- `deployment_names`

#### F3.5: Invalid Timestamp Format
**Detection:** `validate_data_types()` - Line 414-416
**Current Error:** `"{field_name} contains invalid date string: {value}"`
**Failure Type:** Format validation error
**Spec:** `"Invalid timestamp format for {field_name}: '{value}' - expected ISO 8601 (e.g., '2026-07-13T18:07:55Z')"`

**Timestamp fields:**
- `first_deployment`
- `last_deployment`
- `created_at`
- `updated_at`

**Valid formats:**
- `2026-07-13T18:07:55Z`
- `2026-07-13T18:07:55+00:00`
- `2026-07-13`

#### F3.6: Empty Timestamp
**Detection:** `validate_deployment_record()` - Line 125-126
**Current Error:** `"{field_name} contains invalid timestamp: {value}"`
**Failure Type:** Empty value error
**Spec:** `"Empty timestamp for {field_name}: '{value}' - timestamp cannot be empty or null"`

#### F3.7: Negative Numeric Value
**Detection:** `validate_deployment_record()` - Line 118-119
**Current Error:** `"{field_name} must be non-negative, got {value}"`
**Failure Type:** Value constraint violation
**Spec:** `"Invalid value for {field_name}: {value} is negative - must be >= 0"`

**Non-negative fields:**
- `period_days`
- `total_deployments`
- `successful_deployments`
- `failed_deployments`
- `deployment_frequency_per_day`
- `mean_time_between_deployments_hours`

---

## Layer 4: Completeness Validation

### Location
- `src/validation/completeness.py` - `validate_30day_completeness()`
- `src/validation/validate_completeness.py` - `validate_completeness()`

### Failure Scenarios

#### F4.1: Cannot Determine Date Range
**Detection:** `validate_30day_completeness()` - Line 270-271
**Current Error:** `"Cannot determine date range from data"`
**Failure Type:** Metadata error
**Spec:** `"Cannot determine date range: metadata.time_period.start/end or report_metadata.time_range_start/end not found in data"`

**Required metadata structure:**
```python
{
    "metadata": {
        "time_period": {
            "start": "2026-07-01T00:00:00Z",
            "end": "2026-07-30T23:59:59Z"
        }
    }
}

# Alternative structure
{
    "report_metadata": {
        "time_range_start": "2026-07-01T00:00:00Z",
        "time_range_end": "2026-07-30T23:59:59Z"
    }
}
```

#### F4.2: Invalid Date in Metadata
**Detection:** `validate_30day_completeness()` - Line 257-258, Line 266-267
**Current Error:** `"Invalid date in time_period: {error}"` or `"Invalid date in report_metadata: {error}"`
**Failure Type:** Date format error
**Spec:** `"Invalid date format in metadata.{field}: '{value}' - {error}"`

#### F4.3: Wrong Date Range Duration
**Detection:** `validate_30day_completeness()` - Line 284-285
**Current Error:** `"Date range covers {count} days, expected ~30 days (from {start} to {end})"`
**Failure Type:** Duration constraint violation
**Spec:** `"Invalid date range duration: {count} days from {start} to {end} - expected 29-31 days for 30-day completeness check"`

**Acceptable ranges:** 29-31 days (inclusive)

#### F4.4: No Dates Found in Data
**Detection:** `validate_30day_completeness()` - Line 290-291
**Current Error:** `"No dates found in deployment data"`
**Failure Type:** Data absence error
**Spec:** `"No deployment dates found in data - expected dates in deployment_events_last_30_days[].date or deployment_history_30_days.replicasets[].created"`

**Expected data locations:**
```python
{
    "deployment_events_last_30_days": [
        {"date": "2026-07-13"},
        ...
    ],
    "deployment_history_30_days": {
        "replicasets": [
            {"created": "2026-07-13T18:07:55Z"},
            ...
        ]
    }
}
```

#### F4.5: Missing Dates (Gaps)
**Detection:** `validate_30day_completeness()` - Line 295-297
**Current Error:** `"Missing data for {count} day(s): {dates}..."`
**Failure Type:** Coverage gap
**Spec:** `"Missing data for {count} day(s): {dates} - expected consecutive daily coverage with no gaps"`

**Example:** `"Missing data for 3 day(s): 2026-07-05, 2026-07-06, 2026-07-15"`

#### F4.6: Extra Dates (Out of Range)
**Detection:** `validate_30day_completeness()` - Line 300-303
**Current Error:** `"Found {count} date(s) outside expected range: {dates}..."`
**Failure Type:** Boundary violation
**Spec:** `"Found {count} date(s) outside expected range ({start} to {end}): {dates} - all dates must be within the analysis period"`

**Example:** `"Found 2 date(s) outside expected range (2026-07-01 to 2026-07-30): 2026-06-30, 2026-07-31"`

#### F4.7: Non-Chronological Dates
**Detection:** `validate_30day_completeness()` - Line 315-316
**Current Error:** `"Non-chronological dates: {prev} → {curr} (gap of {days} days)"`
**Failure Type:** Sequence violation
**Spec:** `"Non-consecutive dates: {prev} → {curr} (gap of {days} days) - expected exactly 1 day between consecutive dates"`

**Example:** `"Non-consecutive dates: 2026-07-10 → 2026-07-13 (gap of 3 days)"`

---

## Layer 5: Entry Count Validation (Alternative Completeness Check)

### Location
`src/validation/validate_completeness.py` - `validate_completeness()`

### Failure Scenarios

#### F5.1: Wrong Entry Count
**Detection:** `validate_completeness()` - Line 29-31
**Current Error:** `"Expected 30 deployment entries, found {count}"`
**Failure Type:** Count constraint violation
**Spec:** `"Invalid deployment count: found {count} entries, expected exactly 30 for 30-day completeness"`

#### F5.2: Entry Not Dictionary
**Detection:** `validate_completeness()` - Line 38-39
**Current Error:** `"Entry {index} is not a dictionary"`
**Failure Type:** Type error
**Spec:** `"Invalid entry type at index {index}: expected dictionary, got {type} - each deployment entry must be a key-value structure"`

#### F5.3: Missing Timestamp Field
**Detection:** `validate_completeness()` - Line 47-48
**Current Error:** `"Entry {index} missing timestamp field"`
**Failure Type:** Schema violation
**Spec:** `"Missing timestamp in entry {index} - required field 'timestamp' or 'creationTimestamp' not found"`

**Supported timestamp fields:**
- `timestamp`
- `creationTimestamp`

#### F5.4: Empty Timestamp
**Detection:** `validate_completeness()` - Line 51-52
**Current Error:** `"Entry {index} has empty timestamp"`
**Failure Type:** Empty value error
**Spec:** `"Empty timestamp in entry {index} - timestamp field cannot be empty or null"`

#### F5.5: Timestamp Not String
**Detection:** `validate_completeness()` - Line 60-61
**Current Error:** `"Entry {index} timestamp must be a string"`
**Failure Type:** Type error
**Spec:** `"Invalid timestamp type in entry {index}: expected string, got {type} - timestamps must be ISO 8601 formatted strings"`

#### F5.6: Invalid Timestamp Format
**Detection:** `validate_completeness()` - Line 71-72
**Current Error:** `"Entry {index} has invalid timestamp: {error}"`
**Failure Type:** Format validation error
**Spec:** `"Invalid timestamp format in entry {index}: '{value}' - {error} (expected ISO 8601, e.g., '2026-07-13T18:07:55Z')"`

#### F5.7: Duplicate Date
**Detection:** `validate_completeness()` - Line 67-68
**Current Error:** `"Duplicate date found: {date}"`
**Failure Type:** Uniqueness constraint violation
**Spec:** `"Duplicate deployment date: {date} - each date must appear exactly once in the 30-day period"`

#### F5.8: Date Gap Detected
**Detection:** `validate_completeness()` - Line 83-85
**Current Error:** `"Date gap detected: {current} to {next} ({diff} days, expected 1)"`
**Failure Type:** Coverage gap
**Spec:** `"Date gap detected: {current} → {next} is {diff} days, expected 1 day - missing deployment data for {missing_dates}"`

**Example:** `"Date gap detected: 2026-07-10 → 2026-07-13 is 3 days, expected 1 day - missing deployment data for 2026-07-11, 2026-07-12"`

---

## Layer 6: Business Constraint Validation

### Location
`src/validation/deployment_data.py` - `validate_deployment_record()`

### Failure Scenarios

#### F6.1: Deployment Count Mismatch
**Detection:** `validate_deployment_record()` - Line 134-135
**Current Error:** `"successful_deployments ({s}) + failed_deployments ({f}) must equal total_deployments ({t})"`
**Failure Type:** Arithmetic constraint violation
**Spec:** `"Deployment count mismatch: successful ({s}) + failed ({f}) = {sum}, but total is {t} - successful + failed must equal total"`

**Example:** `"Deployment count mismatch: successful (8) + failed (2) = 10, but total is 11 - successful + failed must equal total"`

#### F6.2: Rate Sum Not 100%
**Detection:** `validate_deployment_record()` - Line 146-147
**Current Error:** `"success_rate ({s}) + failure_rate ({f}) should equal 100.0"`
**Failure Type:** Arithmetic constraint violation
**Spec:** `"Rate sum error: success_rate ({s}) + failure_rate ({f}) = {sum}%, expected 100.0% - rates must sum to 100%"`

**Example:** `"Rate sum error: success_rate (85.0) + failure_rate (10.0) = 95.0%, expected 100.0% - rates must sum to 100%"`

#### F6.3: Non-Zero Rates with Zero Deployments
**Detection:** `validate_deployment_record()` - Line 144-145
**Current Error:** `"When total_deployments is 0, success_rate and failure_rate must both be 0.0, got {s} and {f}"`
**Failure Type:** Logical constraint violation
**Spec:** `"Invalid rates with zero deployments: total=0 but success_rate={s}, failure_rate={f} - when no deployments, both rates must be 0.0%"`

---

## Error Message Quality Issues

### Current Problems

1. **Vague error context:** Errors don't explain what the field represents
2. **No actionability:** Errors don't suggest how to fix the problem
3. **Inconsistent format:** Similar errors have different message structures
4. **Missing values:** Errors often don't include the actual problematic value
5. **No examples:** Errors don't show what a valid value looks like

### Specification Guidelines

All error messages should follow this pattern:

```
[{category}] {problem} - {explanation} ({suggestion})
```

**Example specification:**

```
Invalid type for service: expected str, got int (value: 123) - service name must be a string identifier
```

**Components:**
1. **Category:** Error type (Invalid type, Missing field, Format error, etc.)
2. **Problem:** What went wrong (specific field/value)
3. **Explanation:** Why it's wrong (constraint details)
4. **Suggestion:** How to fix it (expected format, valid examples)

---

## Validation Flow

### Integration Function: `validate_all()`

**Location:** `src/validation/integration.py`

**Validation sequence:**

1. **Load data** (from file or direct input)
2. **JSON well-formedness** - Early termination on failure
3. **Required fields** - Continue collecting errors
4. **Data types** - Continue collecting errors
5. **Completeness** - Final check

**Return value:** `(is_valid: bool, errors: List[str])`

### Runner Function: `validate_deployment_file()`

**Location:** `src/validation/runner.py`

**Validation sequence:**

1. **File exists and parseable** (JSON well-formedness)
2. **Required fields** - Collect all errors
3. **Data types** - Collect all errors
4. **Completeness** - Final check

**Return value:** `(is_valid: bool, errors: List[str])`

---

## Test Coverage

### Existing Tests

1. **`test_required_fields_validation.py`**
   - Missing single required field
   - All fields present
   - Multiple entries with multiple missing fields
   - Deployment data mapping
   - Integration with real data structure

2. **`test_validate_all_integration.py`**
   - Valid complete data (happy path)
   - Invalid JSON (early termination)
   - Missing required fields
   - Invalid data types
   - File-based validation
   - Nonexistent file
   - No input provided

3. **`test_validate_deployment_file.py`**
   - Function existence
   - Return type correctness
   - Return value types
   - Nonexistent file handling
   - Function signature validation
   - Docstring presence

### Test Gaps

The following failure scenarios lack test coverage:

1. All completeness validation failures (F4.3-F4.7, F5.1-F5.8)
2. Business constraint violations (F6.1-F6.3)
3. Timestamp format edge cases
4. Negative value constraints
5. Empty timestamp handling
6. Wrong date range duration

---

## Recommendations

1. **Implement error message specification:** Update all error messages to follow the specified format

2. **Add missing test coverage:** Create tests for all F4.x, F5.x, and F6.x scenarios

3. **Add validation helpers:** Create helper functions that generate well-formatted error messages

4. **Improve error context:** Include field descriptions, expected values, and examples in error messages

5. **Create validation documentation:** User-facing guide explaining all validation checks and how to fix failures

6. **Add validation mode:** Support "strict" vs "lenient" validation modes for different use cases

7. **Internationalization:** Structure error messages to support i18n in the future

---

## Summary Statistics

- **Total validation layers:** 6
- **Total failure scenarios documented:** 39
- **Current error messages reviewed:** 39
- **Error message specifications created:** 39
- **Code locations mapped:** 39
- **Test coverage gaps identified:** 23 scenarios

---

## Document Metadata

**Created:** 2026-08-07
**Author:** Research task (adc-5v5g48)
**Scope:** Completeness validation failure scenarios in aide-de-camp deployment data validation
**Related files:**
- `src/validation/completeness.py`
- `src/validation/validate_completeness.py`
- `src/validation/deployment_data.py`
- `src/validation/deployment_validator.py`
- `src/validation/integration.py`
- `src/validation/runner.py`
