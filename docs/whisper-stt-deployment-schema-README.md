# Whisper-STT Deployment Data Schema

## Overview

This directory contains the JSON schema and validation tools for whisper-stt deployment data files. The schema ensures deployment data meets structural, type, and 30-day completeness requirements for operational analysis.

## Files

### whisper-stt-deployment-data-schema.json
The primary JSON Schema (Draft 07) definition that validates whisper-stt deployment data structure. This schema matches the actual deployment data format produced by the persistence layer.

**Key validation areas:**
- **Metadata**: Generation timestamp, 30-day period boundaries, services, clusters, and data sources
- **Argo Workflows**: CI/CD build workflow execution data
- **ArgoCD**: Application deployment state and sync status
- **Cluster Deployments**: Kubernetes deployment metrics including replica history
- **Summary**: 30-day deployment statistics and coverage analysis
- **Pod Health**: Current pod status and aggregate health metrics
- **Resources**: CPU and memory allocation/limits
- **Storage**: PVC configuration and status
- **Error Incidents**: Critical, warning, and info level incidents
- **Notes**: Additional observations and context

### validate_deployment_data_schema.py
Python validation script that uses the JSON schema to validate deployment data files.

**Usage:**
```bash
# Validate a deployment data file
python3 validate_deployment_data_schema.py whisper-stt-deployments-30d.json

# Skip 30-day completeness check
python3 validate_deployment_data_schema.py --no-30-day-check whisper-stt-deployments-30d.json

# Use custom schema file
python3 validate_deployment_data_schema.py --schema custom-schema.json deployment.json
```

**Requirements:**
- jsonschema library (install with: `pip install jsonschema`)
- Falls back to basic structural validation if jsonschema is not available

## Schema Structure

### Required Top-Level Fields
All deployment data files must contain these fields:
- `metadata` - Generation and coverage information
- `argo_workflows` - CI/CD workflow data
- `argo_cd` - GitOps deployment state
- `cluster_deployments` - Kubernetes deployment metrics
- `summary` - 30-day period statistics
- `pod_health` - Current pod status and metrics

### Optional Top-Level Fields
- `resources` - CPU and memory specifications
- `storage` - PVC and volume information
- `error_incidents` - Error and failure tracking
- `notes` - Additional context

## 30-Day Completeness Validation

The schema includes a `thirtyDayCompleteness` definition that ensures:

1. **Time Period Coverage**: 
   - `metadata.data_period_start` and `metadata.data_period_end` define the analysis window
   - Period should span approximately 30 days (28-32 days allowed for flexibility)

2. **Deployment Metrics**:
   - `cluster_deployments.whisper-stt.deployments_last_30_days` must be present
   - `summary.total_deployments_last_30_days` provides overall deployment count
   - Metrics are non-negative integers

3. **Data Completeness**:
   - `summary.data_coverage` indicates percentage coverage (e.g., "100%")
   - `summary.gaps_detected` flags any data gaps
   - `summary.largest_gap_days` shows size of largest gap if any

## Data Types and Constraints

### Timestamps
All timestamps use ISO 8601 format:
- `generated_at`: "2026-08-06T12:03:32.329077Z"
- `data_period_start`: "2026-07-07T09:07:50Z"
- `created_at`: "2026-05-01T17:26:49Z"

### Counts and Metrics
- All deployment counts are integers (minimum: 0)
- Success rates are percentages (e.g., "85.7%")
- Age fields are in days (integer or float)

### Enums and Status Values
- **Sync Status**: "Synced", "OutOfSync", "Unknown"
- **Health Status**: "Healthy", "Progressing", "Degraded", "Missing", "Unknown"
- **Pod Status**: "Running", "Pending", "Failed", "Succeeded", "Unknown"
- **ReplicaSet Status**: "successful", "rolled_over", "scaled_down_or_failed", "failed"

## Validation Examples

### Valid Data Structure
```json
{
  "metadata": {
    "generated_at": "2026-08-06T12:03:32Z",
    "data_period_start": "2026-07-07T09:07:50Z",
    "data_period_end": "2026-08-06T09:07:50Z",
    "services": ["whisper-stt", "whisper-openai"],
    "clusters": ["ardenone-cluster"],
    "data_sources": ["kubernetes_replicasets", "argo_cd"]
  },
  "cluster_deployments": {
    "whisper-stt": {
      "namespace": "whisper-stt",
      "deployment_name": "whisper-stt",
      "deployments_last_30_days": 2,
      "successful_deployments": 2,
      "failed_deployments": 0,
      "deployment_versions": ["1.8.6"]
    }
  },
  "summary": {
    "total_deployments_last_30_days": 2,
    "whisper_stt_deployments": 1,
    "successful_deployments": 2,
    "failed_or_scaled_down": 0,
    "data_coverage": "100%",
    "gaps_detected": false,
    "largest_gap_days": 0
  },
  "pod_health": {
    "current_pods": [...],
    "pod_metrics": {...}
  }
}
```

### Common Validation Errors

1. **Missing Required Fields**
   ```
   ✗ Path: root | Error: 'metadata' is a required property
   ```
   Ensure all required top-level fields are present.

2. **Invalid Timestamp Format**
   ```
   ✗ Path: metadata.data_period_start | Error: does not match format 'date-time'
   ```
   Use ISO 8601 format: `YYYY-MM-DDTHH:MM:SSZ`

3. **Wrong Data Type**
   ```
   ✗ Path: cluster_deployments.whisper-stt.deployments_last_30_days | Error: expected integer, got string
   ```
   Ensure counts are integers, not strings.

4. **30-Day Completeness Issues**
   ```
   ⚠ No deployment events found in 30-day period.
   ```
   Verify data collection and deployment history.

## Integration with Persistence Layer

The schema is designed to work with the deployment persistence implementation:

```python
from src.persistence.deployment_persistence import load_deployment_data
from validate_deployment_data_schema import validate_file

# Load and validate
data = load_deployment_data("whisper-stt-deployments-30d.json")
result = validate_file("whisper-stt-deployments-30d.json")
```

## Extending the Schema

To add new fields or validation rules:

1. Add the field definition to the appropriate section in `whisper-stt-deployment-data-schema.json`
2. Update the validation script if new logic is needed
3. Add tests to ensure backward compatibility
4. Update this README with the new structure

## Maintenance

- **Schema Version**: Based on actual deployment data structure from `src/persistence/deployment_persistence.py`
- **Last Updated**: 2026-08-06
- **Compatibility**: Matches whisper-stt deployments-30d.json format

## Related Files

- `src/schemas/whisper_stt_deployment.py` - Pydantic models for deployment data
- `src/persistence/deployment_persistence.py` - Data persistence layer
- `whisper-stt-deployments-30d.json` - Example deployment data file
- `tests/unit/test_deployment_data_validation.py` - Unit tests for validation

## Troubleshooting

**Q: Validation fails with "jsonschema not installed"**
A: Install with `pip install jsonschema` or use basic structural validation (automatic fallback)

**Q: 30-day completeness validation fails**
A: Check that metadata.data_period_start and data_period_end are present and span ~30 days

**Q: Schema passes but data looks incomplete**
A: The schema validates structure, not content completeness. Use the 30-day completeness check for content validation.

**Q: How do I validate against a different time period?**
A: The schema validates any time period. Modify metadata.data_period_start and data_period_end accordingly.