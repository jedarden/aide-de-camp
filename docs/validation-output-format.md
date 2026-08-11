# Validation Output Format - Gap Metrics

## Overview

The `ValidationResult` class provides comprehensive validation results for deployment data files, including detailed gap metrics alongside schema validation results. The output format is designed to be both human-readable and machine-parsable.

## Output Structure

### Basic Schema Validation

```json
{
  "is_valid": bool,
  "file_path": str,
  "is_wellformed_json": bool,
  "has_required_fields": bool,
  "has_valid_types": bool,
  "has_complete_coverage": bool,
  "errors": List[str]
}
```

### Gap Metrics

```json
{
  "gap_detected": bool,
  "coverage_percentage": float,
  "expected_days": int,
  "actual_days": int,
  "gap_count": int,
  "gap_severity": str,
  "isolated_gap_count": int,
  "consecutive_gap_sequence_count": int,
  "gap_size_distribution": {
    "tiny": int,
    "small": int,
    "medium": int,
    "large": int,
    "extended": int
  },
  "gap_periods": List[str>
}
```

### Actionable Guidance

```json
{
  "actionable_guidance": List[str],
  "anomaly_messages": List[str],
  "deployment_intervals": Dict[str, Any]
}
```

### Metadata

```json
{
  "validated_at": str  // ISO 8601 timestamp
}
```

## Gap Metrics Detailed Reference

### gap_detected
- **Type**: `boolean`
- **Description**: Whether any gaps were detected in the deployment data
- **Values**: `true` if gaps exist, `false` if coverage is complete
- **Example**: `true`

### coverage_percentage
- **Type**: `float`
- **Description**: Percentage of days with deployment data coverage
- **Range**: 0.0 to 100.0
- **Example**: `83.33` (means 83.33% coverage)

### expected_days
- **Type**: `int`
- **Description**: Number of days expected in the analysis period
- **Example**: `30` (for a 30-day analysis)

### actual_days
- **Type**: `int`
- **Description**: Number of days with actual deployment data
- **Example**: `25` (25 days of data in a 30-day period)

### gap_count
- **Type**: `int`
- **Description**: Total number of gap periods detected
- **Example**: `5` (5 separate gap periods)

### gap_severity
- **Type**: `string`
- **Description**: Overall severity level of the gaps
- **Values**: `"none"`, `"low"`, `"medium"`, `"high"`, `"critical"`
- **Classification**:
  - `"none"`: No gaps detected
  - `"low"`: Minor gaps (<3 days total)
  - `"medium"`: Moderate gaps (3-7 days total)
  - `"high"`: Significant gaps (8-14 days total)
  - `"critical"`: Extended gaps (>14 days total)

### isolated_gap_count
- **Type**: `int`
- **Description**: Number of isolated (non-consecutive) gaps
- **Example**: `3` (3 separate single-day gaps)

### consecutive_gap_sequence_count
- **Type**: `int`
- **Description**: Number of consecutive gap sequences
- **Example**: `1` (1 sequence of 5 consecutive missing days)

### gap_size_distribution
- **Type**: `object`
- **Description**: Distribution of gaps by size classification
- **Structure**:
  ```json
  {
    "tiny": int,      // 1-day gaps
    "small": int,     // 2-3 day gaps
    "medium": int,    // 4-7 day gaps
    "large": int,     // 8-14 day gaps
    "extended": int   // >14 day gaps
  }
  ```
- **Example**:
  ```json
  {
    "tiny": 2,
    "small": 1,
    "medium": 1,
    "large": 0,
    "extended": 1
  }
  ```

### gap_periods
- **Type**: `array of strings`
- **Description**: List of individual gap period descriptions
- **Format**: `"YYYY-MM-DD to YYYY-MM-DD"`
- **Example**:
  ```json
  [
    "2026-07-01 to 2026-07-02",
    "2026-07-10 to 2026-07-15"
  ]
  ```

### actionable_guidance
- **Type**: `array of strings`
- **Description**: Actionable guidance for fixing detected gaps
- **Example**:
  ```json
  [
    "Add deployment data for missing days 2026-07-01 to 2026-07-02",
    "Extend data collection period to cover full 30-day window"
  ]
  ```

### anomaly_messages
- **Type**: `array of strings`
- **Description**: Anomaly detection messages highlighting unusual patterns
- **Example**:
  ```json
  [
    "Critical gap detected: 8 consecutive days without deployment data",
    "Coverage below 95% threshold"
  ]
  ```

## Usage Examples

### Python API - Enhanced Result with Gap Metrics

```python
from src.validation.runner import validate_deployment_file

# Get comprehensive result with gap metrics
result = validate_deployment_file("deployment.json", return_type="result")

print(f"Coverage: {result.coverage_percentage}%")
print(f"Gap severity: {result.gap_severity}")
print(f"Gap count: {result.gap_count}")
print(f"Isolated gaps: {result.isolated_gap_count}")
print(f"Consecutive sequences: {result.consecutive_gap_sequence_count}")
print(f"Size distribution: {result.gap_size_distribution}")

# Get full dict output for JSON serialization
output_dict = result.to_dict()
```

### Python API - Legacy Format (Backward Compatible)

```python
from src.validation.runner import validate_deployment_file

# Get legacy format (backward compatible)
is_valid, errors = validate_deployment_file("deployment.json")

if not is_valid:
    for error in errors:
        print(f"ERROR: {error}")
```

### Output Example

```json
{
  "is_valid": false,
  "file_path": "/path/to/deployment.json",
  "is_wellformed_json": true,
  "has_required_fields": true,
  "has_valid_types": true,
  "has_complete_coverage": false,
  "errors": [
    "Completeness validation failed: Expected 30 deployment entries, found 25"
  ],
  "gap_detected": true,
  "coverage_percentage": 83.33,
  "expected_days": 30,
  "actual_days": 25,
  "gap_count": 5,
  "gap_severity": "medium",
  "isolated_gap_count": 3,
  "consecutive_gap_sequence_count": 1,
  "gap_size_distribution": {
    "tiny": 2,
    "small": 1,
    "medium": 1,
    "large": 0,
    "extended": 1
  },
  "gap_periods": [
    "2026-07-01 to 2026-07-02",
    "2026-07-05 to 2026-07-07",
    "2026-07-10 to 2026-07-15"
  ],
  "actionable_guidance": [
    "Add deployment data for missing days: 2026-07-01, 2026-07-02",
    "Fill gap in deployment coverage: 2026-07-05 to 2026-07-07",
    "Critical coverage gap: 2026-07-10 to 2026-07-15 (6 consecutive days)"
  ],
  "anomaly_messages": [
    "Medium severity gap detected: total coverage 83.33% below 95% threshold"
  ],
  "deployment_intervals": {
    "first_deployment": "2026-07-01T00:00:00Z",
    "last_deployment": "2026-07-25T00:00:00Z",
    "interval_days": 24
  },
  "validated_at": "2026-08-11T10:30:00Z"
}
```

## Backward Compatibility

The validation output maintains backward compatibility with existing consumers:

1. **Legacy tuple format**: `validate_deployment_file(file_path, return_type="legacy")` returns `(is_valid: bool, errors: List[str])`
2. **Default behavior**: When `return_type` is not specified, the function returns the legacy format
3. **Enhanced format**: Use `return_type="result"` to get the comprehensive `ValidationResult` object

## Integration Guide

### For Existing Code

No changes needed - the default behavior remains the same:

```python
# This continues to work as before
is_valid, errors = validate_deployment_file("deployment.json")
```

### For New Code

Use the enhanced format to access gap metrics:

```python
# Get comprehensive result
result = validate_deployment_file("deployment.json", return_type="result")

# Access gap metrics
if result.gap_detected:
    print(f"Coverage: {result.coverage_percentage}%")
    print(f"Severity: {result.gap_severity}")
    print(f"Gaps: {result.gap_count}")
```

### For JSON API Endpoints

Serialize the result to JSON:

```python
from fastapi import FastAPI
from src.validation.runner import validate_deployment_file

app = FastAPI()

@app.post("/validate")
async def validate_deployment(file_path: str):
    result = validate_deployment_file(file_path, return_type="result")
    return result.to_dict()  # Returns JSON-serializable dict
```

## Testing

Comprehensive tests verify the gap metrics output:

```bash
# Run gap metrics tests
pytest tests/test_validation_result_gap_metrics.py -v

# Run all validation tests
pytest tests/test_gap_validation_integration.py -v
```

## Related Documentation

- **Gap Detection Algorithm**: See `src/utilities/gap_calculator.py`
- **Validation Runner**: See `src/validation/runner.py`
- **Gap Integration**: See `src/validation/gap_integration.py`
- **Schema Reference**: See `schemas/core-deployment-schema-30day-completeness.json`
