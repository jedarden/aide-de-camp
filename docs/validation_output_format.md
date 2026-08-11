# Validation Output Format

This document describes the output format for the deployment data validation runner.

## Overview

The validation runner (`src/validation/runner.py`) provides comprehensive validation of deployment data files, including:
- JSON well-formedness
- Required fields validation
- Data type validation
- Completeness validation (30-day coverage, gap detection)

## ValidationResult Schema

The `ValidationResult` dataclass contains the following fields:

### Basic Validation Status

| Field | Type | Description |
|-------|------|-------------|
| `is_valid` | `bool` | Overall validation status (all checks must pass) |
| `file_path` | `str` | Path to the validated file |
| `validated_at` | `str` | ISO 8601 timestamp of validation |

### Individual Validation Checks

| Field | Type | Description |
|-------|------|-------------|
| `is_wellformed_json` | `bool` | File exists and is parseable JSON |
| `has_required_fields` | `bool` | All required fields are present |
| `has_valid_types` | `bool` | All data types match the schema |
| `has_complete_coverage` | `bool` | 30-day coverage with no significant gaps |

### Error Messages (Legacy)

| Field | Type | Description |
|-------|------|-------------|
| `errors` | `List[str]` | Human-readable error messages (backward compatibility) |

### Gap Metrics

| Field | Type | Description |
|-------|------|-------------|
| `gap_detected` | `bool` | Whether gaps were detected |
| `coverage_percentage` | `float` | Percentage of days with deployment data (0-100) |
| `expected_days` | `int` | Expected number of days in analysis period |
| `actual_days` | `int` | Actual number of days with deployment data |
| `gap_count` | `int` | Total number of gap days detected |
| `gap_severity` | `str` | Overall severity level: `none`, `low`, `medium`, `high`, `critical` |

### Gap Type Breakdown

| Field | Type | Description |
|-------|------|-------------|
| `isolated_gap_count` | `int` | Number of isolated (non-consecutive) gap days |
| `consecutive_gap_sequence_count` | `int` | Number of unique consecutive gap sequences |

### Gap Size Distribution

| Field | Type | Description |
|-------|------|-------------|
| `gap_size_distribution` | `Dict[str, int]` | Breakdown of gaps by size classification: |
| | `tiny` | 1-day gaps |
| | `small` | 2-3 day gaps |
| | `medium` | 4-7 day gaps |
| | `large` | 8-14 day gaps |
| | `extended` | >14 day gaps |

### Detailed Gap Information

| Field | Type | Description |
|-------|------|-------------|
| `gap_periods` | `List[str]` | String representations of gap periods (e.g., "2026-07-15 to 2026-07-17") |
| `actionable_guidance` | `List[str]` | Actionable remediation steps |
| `anomaly_messages` | `List[str]` | Detected anomalies with explanations |

### Deployment Interval Statistics

| Field | Type | Description |
|-------|------|-------------|
| `deployment_intervals` | `Dict[str, Any]` | Statistics about deployment intervals: |
| | `first_deployment` | Date of first deployment |
| | `last_deployment` | Date of last deployment |
| | `total_deployments` | Total number of deployments |
| | `average_interval_days` | Average days between deployments |
| | `longest_interval_days` | Longest gap between deployments |
| | `shortest_interval_days` | Shortest gap between deployments |

## Example Output

### Successful Validation

```json
{
  "is_valid": true,
  "file_path": "deployment-validation-results.json",
  "is_wellformed_json": true,
  "has_required_fields": true,
  "has_valid_types": true,
  "has_complete_coverage": true,
  "errors": [],
  "gap_detected": false,
  "coverage_percentage": 100.0,
  "expected_days": 30,
  "actual_days": 30,
  "gap_count": 0,
  "gap_severity": "none",
  "isolated_gap_count": 0,
  "consecutive_gap_sequence_count": 0,
  "gap_size_distribution": {
    "tiny": 0,
    "small": 0,
    "medium": 0,
    "large": 0,
    "extended": 0
  },
  "gap_periods": [],
  "actionable_guidance": [],
  "anomaly_messages": [],
  "deployment_intervals": {
    "first_deployment": "2026-07-01",
    "last_deployment": "2026-07-30",
    "total_deployments": 30,
    "average_interval_days": 1.0,
    "longest_interval_days": 1,
    "shortest_interval_days": 1
  },
  "validated_at": "2026-08-11T12:00:00Z"
}
```

### Validation with Gaps

```json
{
  "is_valid": false,
  "file_path": "deployment-with-gaps.json",
  "is_wellformed_json": true,
  "has_required_fields": true,
  "has_valid_types": true,
  "has_complete_coverage": false,
  "errors": [
    "service-name: 86.7% coverage (26/30 days). 4 gap(s) detected."
  ],
  "gap_detected": true,
  "coverage_percentage": 86.67,
  "expected_days": 30,
  "actual_days": 26,
  "gap_count": 4,
  "gap_severity": "medium",
  "isolated_gap_count": 2,
  "consecutive_gap_sequence_count": 1,
  "gap_size_distribution": {
    "tiny": 2,
    "small": 0,
    "medium": 1,
    "large": 0,
    "extended": 0
  },
  "gap_periods": [
    "2026-07-05 to 2026-07-05",
    "2026-07-10 to 2026-07-12",
    "2026-07-15 to 2026-07-15",
    "2026-07-20 to 2026-07-20"
  ],
  "actionable_guidance": [
    "Increase coverage from 86.7% to 95.0% (shortfall: 8.3%). Add deployment data for 4 missing day(s).",
    "Address 1 consecutive gap sequence(s). Longest sequence: 3 days. Check for extended data collection failures or service downtime.",
    "Fill 2 isolated gap day(s). May indicate intermittent data collection issues or skipped deployments.",
    "Expected deployment interval: Days 1-30 of analysis period. Current: 26 day(s) with deployment data. Add deployment data for 4 missing day(s) in the 1-30 range."
  ],
  "anomaly_messages": [],
  "deployment_intervals": {
    "first_deployment": "2026-07-01",
    "last_deployment": "2026-07-30",
    "total_deployments": 26,
    "average_interval_days": 1.1,
    "longest_interval_days": 3,
    "shortest_interval_days": 1
  },
  "validated_at": "2026-08-11T12:00:00Z"
}
```

## Usage Examples

### Legacy Format (Backward Compatible)

```python
from src.validation.runner import validate_deployment_file

is_valid, errors = validate_deployment_file("deployment.json")
if not is_valid:
    for error in errors:
        print(f"ERROR: {error}")
```

### Enhanced Format with Gap Metrics

```python
from src.validation.runner import validate_deployment_file

result = validate_deployment_file("deployment.json", return_type="result")

# Access gap metrics
print(f"Coverage: {result.coverage_percentage}%")
print(f"Gap severity: {result.gap_severity}")
print(f"Isolated gaps: {result.isolated_gap_count}")
print(f"Consecutive sequences: {result.consecutive_gap_sequence_count}")
print(f"Gap size distribution: {result.gap_size_distribution}")

# Access detailed information
if result.gap_detected:
    for guidance in result.actionable_guidance:
        print(f"Guidance: {guidance}")
```

### JSON Serialization

```python
from src.validation.runner import validate_deployment_file
import json

result = validate_deployment_file("deployment.json", return_type="result")
output_dict = result.to_dict()

# Write to file
with open("validation_result.json", "w") as f:
    json.dump(output_dict, f, indent=2)
```

## Backward Compatibility

The validation runner maintains backward compatibility with existing code:

1. **Legacy tuple format**: `validate_deployment_file(file_path)` returns `(is_valid, errors)` by default
2. **Enhanced format**: `validate_deployment_file(file_path, return_type="result")` returns `ValidationResult`
3. **Error messages**: The `errors` field continues to provide human-readable messages
4. **Gap metrics**: New fields are optional and have sensible defaults

## Severity Levels

Gap severity is assessed based on coverage percentage and maximum gap size:

| Severity | Coverage | Max Gap Size | Description |
|----------|----------|--------------|-------------|
| `none` | ≥95% | 0 days | No gaps detected |
| `low` | ≥95% | ≤3 days | Minor gaps, acceptable |
| `medium` | <95% | >3 days | Moderate gaps, action recommended |
| `high` | <90% | >7 days | Significant gaps, action required |
| `critical` | <80% | >14 days | Severe gaps, immediate action required |

## Gap Size Classifications

| Classification | Size | Description |
|----------------|------|-------------|
| `tiny` | 1 day | Single-day gaps, usually acceptable |
| `small` | 2-3 days | Short gaps, may indicate intermittent issues |
| `medium` | 4-7 days | Moderate gaps, investigation recommended |
| `large` | 8-14 days | Significant gaps, action required |
| `extended` | >14 days | Severe gaps, immediate attention needed |

## Integration with Deployment Pipeline

The validation output is designed to integrate with deployment validation pipelines:

1. **CI/CD integration**: Use `is_valid` to gate deployments
2. **Monitoring**: Track `coverage_percentage` and `gap_severity` over time
3. **Alerting**: Alert on `gap_severity` of `high` or `critical`
4. **Trending**: Monitor `gap_size_distribution` for patterns

## Further Documentation

- Gap calculation: `src/utilities/gap_calculator.py`
- Gap validation: `src/validation/gap_integration.py`
- Schema definition: `src/validation/deployment_data.py`
- Test examples: `tests/unit/test_validation_runner.py`
