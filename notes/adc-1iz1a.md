# JSON Well-Formedness and Completeness Validation

## Implementation Summary

This document summarizes the implementation of JSON well-formedness and 30-day completeness validation for bead adc-1iz1a.

## Acceptance Criteria Met

### ✅ 1. Validation checks file is well-formed JSON (parseable)

Implemented `validate_json_wellformedness()` and `validate_json_file_wellformedness()` functions:

- **Function**: `validate_json_wellformedness(data: Any) -> Tuple[bool, Optional[str]]`
  - Validates that Python objects can be serialized to JSON and deserialized back
  - Catches TypeError, ValueError for non-serializable objects (datetime, set, complex, etc.)
  
- **Function**: `validate_json_file_wellformedness(file_path: Path) -> Tuple[bool, Optional[str], Optional[Dict]]`
  - Loads and parses JSON files
  - Returns parsed data on success
  - Provides detailed error messages for JSON syntax errors

### ✅ 2. Validates exactly 30 days of data present (no gaps, no duplicates)

Implemented `validate_30day_completeness()` function:

- Extracts expected date range from metadata (supports both `metadata.time_period` and `report_metadata` formats)
- Generates expected dates for the range (inclusive)
- Extracts actual dates from deployment data (from `deployment_events_last_30_days` and `deployment_history_30_days.replicasets`)
- Checks for missing dates (gaps)
- Checks for extra dates (outside expected range)
- Validates duration is approximately 30 days (29-31 day tolerance)

### ✅ 3. Checks chronological sequence of dates

The chronological sequence check is integrated into `validate_30day_completeness()`:

- Sorts extracted dates
- Verifies consecutive dates have exactly 1 day difference
- Reports gaps with specific date ranges (e.g., "2026-07-01 → 2026-07-03 (gap of 2 days)")

### ✅ 4. Integrates with validation function from child adc-30zdd

Integration via `src/validation/__init__.py`:

```python
from src.validation.deployment_data import (
    validate_deployment_data,
    validate_deployment_data_simple,
    validate_deployment_record,
    validate_timestamp,
)

from src.validation.completeness import (
    validate_json_wellformedness,
    validate_json_file_wellformedness,
    validate_30day_completeness,
    validate_json_completeness,
    validate_json_file_completeness,
)
```

The `validate_json_completeness()` function combines both validations:
1. First checks JSON well-formedness
2. Then checks 30-day completeness

### ✅ 5. Unit tests cover completeness checks

Comprehensive test suite in `tests/unit/test_completeness_validation.py`:

**42 tests covering:**

- **JSON Well-Formedness (6 tests)**:
  - Valid JSON objects, arrays, primitives
  - Invalid JSON (datetime, set, complex)
  
- **JSON File Well-Formedness (3 tests)**:
  - Valid JSON files
  - Invalid JSON syntax
  - Nonexistent files
  
- **Date Parsing (3 tests)**:
  - ISO date strings
  - Timestamps
  - Invalid formats
  
- **Expected Date Generation (3 tests)**:
  - Single day, 3-day, 30-day ranges
  
- **Date Extraction (5 tests)**:
  - From deployment_events_last_30_days
  - From deployment_history_30_days.replicasets
  - Timestamp stripping
  - Empty data
  - Invalid date handling
  
- **30-Day Completeness (7 tests)**:
  - Complete 30-day data
  - Missing dates (gaps)
  - Duplicate dates
  - Incorrect date ranges
  - No metadata
  - Chronological sequence
  - Report metadata format
  
- **Combined Validation (3 tests)**:
  - Complete valid data
  - Invalid JSON structure
  - Incomplete data
  
- **File Validation (3 tests)**:
  - Valid complete files
  - Invalid JSON files
  - Incomplete JSON files
  
- **Real Data Integration (2 tests)**:
  - pbx-web deployment data
  - whisper-stt deployment data
  
- **Edge Cases (7 tests)**:
  - Empty data
  - No deployment events
  - Exactly 30 days
  - Too short (28 days)
  - Too long (32 days)
  - Leap year February
  - Malformed dates

**All 42 tests pass successfully.**

## File Structure

```
src/validation/
├── __init__.py                 # Exports all validation functions
├── deployment_data.py          # Field presence and type validation (adc-30zdd)
└── completeness.py             # JSON well-formedness and 30-day completeness (adc-1iz1a)

tests/unit/
└── test_completeness_validation.py  # 42 comprehensive tests
```

## Usage Examples

### Validate JSON well-formedness

```python
from src.validation.completeness import validate_json_wellformedness

data = {"service": "pbx-web", "deployments": 10}
is_valid, error = validate_json_wellformedness(data)
# Returns: (True, None)
```

### Validate 30-day completeness

```python
from src.validation.completeness import validate_30day_completeness
from datetime import datetime

data = {
    "metadata": {
        "time_period": {
            "start": "2026-07-01T00:00:00Z",
            "end": "2026-07-30T23:59:59Z"
        }
    },
    "deployment_events_last_30_days": [...]
}

is_valid, error = validate_30day_completeness(data)
# Returns: (True, None) if data covers all 30 days
# Returns: (False, "Missing data for 5 day(s): ...") if gaps exist
```

### Validate both (comprehensive)

```python
from src.validation.completeness import validate_json_completeness

is_valid, error = validate_json_completeness(data)
# Returns: (True, None) if well-formed AND complete
# Returns: (False, "JSON well-formedness check failed: ...") if invalid JSON
# Returns: (False, "30-day completeness check failed: ...") if incomplete
```

### Validate from file

```python
from pathlib import Path
from src.validation.completeness import validate_json_file_completeness

file_path = Path("pbx-web-deployment-data-30days.json")
is_valid, error, data = validate_json_file_completeness(file_path)
# Returns: (True, None, parsed_data) on success
```

## Integration with adc-30zdd

The completeness validation builds on the field presence and type validation from adc-30zdd:

```python
from src.validation import (
    # From adc-30zdd
    validate_deployment_data,
    validate_timestamp,
    
    # From adc-1iz1a
    validate_json_completeness,
    validate_30day_completeness,
)

# Full validation pipeline
data = load_json_file("deployment-data.json")

# 1. Check field presence and types (adc-30zdd)
is_valid_structure, structure_error = validate_deployment_data(data)

# 2. Check JSON well-formedness and 30-day completeness (adc-1iz1a)
is_valid_complete, complete_error = validate_json_completeness(data)
```

## Implementation Details

### Date Parsing

Supports multiple date formats:
- ISO 8601 dates: `2026-07-01`
- ISO 8601 with time: `2026-07-01T12:00:00Z`
- Handles timezone normalization (Z → +00:00)

### Date Extraction

Looks for dates in:
- `deployment_events_last_30_days[].date`
- `deployment_history_30_days.replicasets[].created`
- Strips time component from timestamps (uses date only for completeness)

### Completeness Algorithm

1. Extract date range from metadata (or use provided parameters)
2. Normalize to date-only (no time)
3. Generate expected dates for range (inclusive)
4. Extract actual dates from deployment data
5. Compute set differences:
   - `missing = expected - actual`
   - `extra = actual - expected`
6. Verify chronological order by checking consecutive differences

### Error Messages

Provides detailed, actionable error messages:
- `"Missing data for 5 day(s): 2026-07-02, 2026-07-03, ..."`
- `"Found 2 date(s) outside expected range: 2026-06-30, 2026-07-31"`
- `"Non-chronological dates: 2026-07-01 → 2026-07-03 (gap of 2 days)"`
- `"Date range covers 45 days, expected ~30 days"`

## Testing

Run tests with:

```bash
.venv/bin/python -m pytest tests/unit/test_completeness_validation.py -v
```

All 42 tests pass in 0.04 seconds.

## Conclusion

The implementation fully satisfies all acceptance criteria for bead adc-1iz1a:

✅ JSON well-formedness validation
✅ 30-day completeness validation (no gaps, no duplicates)
✅ Chronological sequence checking
✅ Integration with adc-30zdd validation
✅ Comprehensive unit test coverage (42 tests)

The validation functions are production-ready and integrated into the aide-de-camp validation framework.
