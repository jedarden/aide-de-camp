# 30-Day Completeness Validation Guide

## Overview

The 30-day completeness validation schema extends the core deployment data schema to ensure deployment data covers a continuous 30-day period without significant gaps. This validation is critical for:

- **Reliability analysis**: Ensures sufficient data for statistical analysis
- **Trend detection**: Provides adequate temporal coverage for pattern identification
- **Compliance monitoring**: Meets minimum data retention requirements
- **Operational confidence**: Validates deployment pipeline stability

## Validation Components

### 1. JSON Schema Structure Validation

The schema file `core-deployment-schema-30day-completeness.json` validates the structural requirements of deployment data including:

- Required top-level fields (metadata, deployment_info, current_status, metrics, completeness)
- Metadata requirements (data_period_start, data_period_end, service_name)
- Completeness section requirements
- Field types and formats
- Value constraints (minimums, patterns, enums)

### 2. Programmatic Completeness Validation

The validator script `validate_30day_completeness_combined.py` performs business logic validation:

- **Period coverage**: Validates `data_period_end - data_period_start >= 30 days`
- **Gap detection**: Identifies gaps > 3 days (warning) and > 7 days (critical)
- **Deployment activity**: Ensures minimum deployment days threshold is met
- **Completeness threshold**: Validates coverage percentage meets requirements (default 95%)

## Completeness Section Requirements

The `completeness` object is required and must contain the following fields:

### Required Fields

| Field | Type | Description | Validation |
|-------|------|-------------|------------|
| `period_coverage_days` | integer | Number of days covered | Must be >= 30 |
| `data_coverage_percent` | string | Coverage percentage | Pattern: `^\d+%$`, should be >= 95% |
| `gaps_detected` | boolean | Whether gaps exist | Should be `false` for completeness |
| `gap_details` | array | List of gaps detected | Empty if no gaps, otherwise detailed gap info |
| `meets_completeness_threshold` | boolean | Threshold compliance | Should be `true` for completeness |
| `minimum_deployment_days` | integer | Minimum deployment days required | Default: 1 |
| `actual_deployment_days` | integer | Actual deployment days | Should meet minimum |
| `deployment_days_threshold_met` | boolean | Deployment days compliance | Should be `true` for completeness |

### Optional Fields

| Field | Type | Description | Default |
|-------|------|-------------|---------|
| `completeness_threshold_percent` | string | Minimum threshold | "95%" |
| `gap_details[].severity` | string | Gap severity level | "critical", "warning", "info" |

## Gap Severity Classification

Gaps are classified by duration:

| Severity | Duration Range | Description |
|----------|---------------|-------------|
| **Critical** | > 7 days | Significant data loss, affects analysis validity |
| **Warning** | 3-7 days | Notable gap, may affect some analyses |
| **Info** | < 3 days | Minor gap, acceptable for most analyses |

## Validation Workflow

### Step 1: JSON Schema Validation

```bash
python validate_30day_completeness_combined.py deployment-data.json
```

This validates:
- All required fields present
- Correct data types and formats
- Value constraints (minimums, patterns)
- Completeness section structure

### Step 2: Completeness Validation

The combined validator automatically performs completeness checks:

```python
from schemas.validate_30day_completeness_combined import CompletenessValidator

validator = CompletenessValidator(
    min_coverage_percent=95.0,
    min_deployment_days=1,
    critical_gap_threshold=7,
    warning_gap_threshold=3
)

is_valid, errors = validator.validate(deployment_data)
```

### Step 3: Error Analysis

Errors are grouped by category:

- **JSON Schema Validation**: Structural issues
- **Period Coverage**: Time period too short
- **Data Gaps**: Gaps in deployment timeline
- **Deployment Activity**: Insufficient deployment activity
- **Completeness Threshold**: Coverage below threshold
- **Timestamp Format**: Invalid timestamp formats

## Error Messages and Resolution

### Period Coverage Errors

**Error**: `Analysis period is only X days. Minimum required: 30 days.`

**Resolution**: Extend the data collection period to cover at least 30 days. Update `metadata.data_period_start` and `metadata.data_period_end`.

### Gap Errors

**Error**: `Gap of X days detected at start/end of period.`

**Resolution**:
- Extend data collection to fill the gap
- If gap is unavoidable, document the reason in the completeness section
- Consider whether the gap affects your analysis requirements

**Error**: `Gap of X days between replicas (Y to Z days ago).`

**Resolution**:
- Verify if ReplicaSet data is missing from the collection
- Check if replicas were scaled to 0 during the gap
- Document infrastructure maintenance windows if applicable

### Deployment Activity Errors

**Error**: `No deployments recorded in the analysis period.`

**Resolution**:
- Verify deployment data collection is working
- Check if the deployment pipeline is active
- Ensure metrics are being calculated correctly

### Completeness Threshold Errors

**Error**: `Data coverage (X%) is below minimum threshold (95%).`

**Resolution**:
- Investigate missing data in the uncovered period
- Consider lowering the threshold if appropriate for your use case
- Document data limitations in analysis reports

## Usage Examples

### Example 1: Valid 30-Day Complete Data

```json
{
  "metadata": {
    "data_period_start": "2026-07-07T09:07:50Z",
    "data_period_end": "2026-08-06T09:07:50Z",
    "service_name": "whisper-stt"
  },
  "metrics": {
    "analysis_period_days": 30,
    "total_deployments": 5
  },
  "replica_history": [
    {"created_at": "2026-07-07T10:00:00Z", "status": "successful"},
    {"created_at": "2026-07-15T14:30:00Z", "status": "successful"},
    {"created_at": "2026-07-22T09:15:00Z", "status": "successful"},
    {"created_at": "2026-07-29T16:45:00Z", "status": "successful"},
    {"created_at": "2026-08-05T11:20:00Z", "status": "successful"}
  ],
  "completeness": {
    "period_coverage_days": 30,
    "data_coverage_percent": "100%",
    "gaps_detected": false,
    "gap_details": [],
    "meets_completeness_threshold": true,
    "minimum_deployment_days": 1,
    "actual_deployment_days": 5,
    "deployment_days_threshold_met": true
  }
}
```

### Example 2: Data with Gaps

```json
{
  "completeness": {
    "period_coverage_days": 30,
    "data_coverage_percent": "87%",
    "gaps_detected": true,
    "gap_details": [
      {
        "gap_start_days_ago": 20,
        "gap_end_days_ago": 15,
        "gap_duration_days": 5,
        "severity": "warning",
        "missing_data_types": ["replicasets", "argo_cd_status"]
      },
      {
        "gap_start_days_ago": 8,
        "gap_end_days_ago": 1,
        "gap_duration_days": 7,
        "severity": "critical",
        "missing_data_types": ["replicasets", "pod_health", "metrics"]
      }
    ],
    "meets_completeness_threshold": false,
    "minimum_deployment_days": 1,
    "actual_deployment_days": 3,
    "deployment_days_threshold_met": true
  }
}
```

## Integration with Analysis Pipelines

### Pre-analysis Validation

Before performing any analysis, validate completeness:

```python
from pathlib import Path
from schemas.validate_30day_completeness_combined import CompletenessValidator

def validate_and_load(data_path: Path) -> dict:
    """Validate and load deployment data."""
    with open(data_path) as f:
        data = json.load(f)

    validator = CompletenessValidator()
    is_valid, errors = validator.validate(data)

    if not is_valid:
        print("Validation failed:")
        for error in errors:
            print(f"  {error}")
        raise ValueError("Data validation failed")

    return data
```

### Conditional Analysis

Adjust analysis based on completeness:

```python
def analyze_deployment_patterns(data: dict) -> dict:
    """Analyze patterns with completeness-aware adjustments."""

    completeness = data.get("completeness", {})
    coverage = float(completeness.get("data_coverage_percent", "0%").rstrip("%"))

    if coverage < 100:
        # Log warnings about incomplete data
        print(f"Warning: Only {coverage}% coverage. Some patterns may be affected.")

        # Adjust confidence intervals
        confidence_adjustment = coverage / 100.0
    else:
        confidence_adjustment = 1.0

    # Perform analysis with adjusted confidence
    results = perform_analysis(data)
    results["confidence_factor"] = confidence_adjustment
    results["completeness_note"] = f"Based on {coverage}% data coverage"

    return results
```

## Best Practices

### 1. Data Collection

- **Automate collection**: Use automated scripts to collect deployment data daily
- **Validate early**: Run completeness validation during collection, not just before analysis
- **Monitor gaps**: Set up alerts when gaps are detected

### 2. Threshold Management

- **Set appropriate thresholds**: 95% is default, but adjust based on your needs
- **Document exceptions**: When completeness thresholds aren't met, document why
- **Trend monitoring**: Track completeness metrics over time

### 3. Gap Handling

- **Investigate gaps**: Always understand why gaps occurred
- **Document reasons**: Record maintenance windows, infrastructure issues, etc.
- **Assess impact**: Evaluate whether gaps affect your specific analysis

### 4. Analysis Reporting

- **Always report completeness**: Include completeness metrics in analysis reports
- **Qualify conclusions**: Add caveats when completeness is below 100%
- **Provide context**: Explain gaps and their potential impact

## Troubleshooting

### Common Issues

**Issue**: Schema validation passes, but completeness validation fails

**Cause**: JSON Schema validates structure but not business logic (period length, gap calculations)

**Resolution**: Use the combined validator which checks both structure and completeness

**Issue**: False gap detection during maintenance windows

**Cause**: Planned infrastructure downtime creates gaps in deployment data

**Resolution**: Document maintenance in `gap_details[].missing_data_types` or adjust gap thresholds for known maintenance periods

**Issue**: Coverage percentage doesn't match manual calculation

**Cause**: Coverage calculation may use different methodology

**Resolution**: Verify the calculation method used in your data pipeline and document it

## Validation Tools

### Command Line

```bash
# Validate a deployment data file
python schemas/validate_30day_completeness_combined.py deployment-data.json

# Validate with custom schema
python schemas/validate_30day_completeness_combined.py deployment-data.json custom-schema.json
```

### Python API

```python
from schemas.validate_30day_completeness_combined import CompletenessValidator

# Create validator with custom thresholds
validator = CompletenessValidator(
    min_coverage_percent=90.0,  # Lower threshold
    min_deployment_days=5,        # Require more deployment activity
    critical_gap_threshold=10,    # More lenient gap detection
    warning_gap_threshold=5
)

# Validate data
is_valid, errors = validator.validate(deployment_data)

# Process errors
for error in errors:
    print(f"{error.category}: {error.message}")
```

## Related Documentation

- [Core Deployment Schema README](core-deployment-schema-README.md) - Base schema documentation
- [JSON Schema Specification](https://json-schema.org/draft/2020-12/spec.html) - JSON Schema standard
- [ISO 8601 Format](https://en.wikipedia.org/wiki/ISO_8601) - Timestamp format reference

## Maintenance and Updates

### Version History

- **v1.0** (2026-08-06): Initial 30-day completeness validation schema

### Future Enhancements

Planned improvements:

- Support for sliding window validation (e.g., any 30-day period within 90 days)
- Gap pattern detection (recurring gaps at same time)
- Quality scoring based on completeness, gap severity, and deployment activity
- Integration with monitoring/alerting systems

## Support

For questions or issues with 30-day completeness validation:

1. Check this guide for common scenarios
2. Review the validation error messages carefully
3. Examine the `completeness` section in your data for detailed gap information
4. Verify your data collection pipeline is working correctly
