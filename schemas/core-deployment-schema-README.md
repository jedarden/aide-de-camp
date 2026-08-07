# Core Deployment Data Schema

## Overview

This directory contains the core JSON schema for validating deployment data across services. The schema defines the essential fields and validation rules required for deployment entries, providing a foundation for service-specific schemas.

## Files

### core-deployment-schema.json
The primary JSON Schema (Draft 2020-12) definition that validates core deployment data structure.

**Key features:**
- **Draft 2020-12 compliance**: Uses the latest JSON Schema standard
- **Service-agnostic**: Designed to work across different services (whisper-stt, pbx-web, etc.)
- **ISO 8601 timestamps**: All timestamp fields use strict date-time format validation
- **Enum validation**: Status fields use allowed value enums for consistency
- **Pattern validation**: Container images and resource specifications use regex patterns

## Schema Structure

### Required Top-Level Fields

All deployment data files must contain these fields:
- `metadata` - Generation timestamp, time period, and service identification
- `deployment_info` - Core deployment information
- `current_status` - Current sync and health status
- `metrics` - Deployment metrics for the analysis period

### Optional Top-Level Fields

- `replica_history` - Historical ReplicaSet data
- `pod_health` - Pod health and runtime statistics
- `resources` - CPU and memory allocation/limits
- `storage` - PVC and volume information
- `summary` - Executive summary with health status

## Field Definitions

### Metadata Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `generated_at` | string (date-time) | Yes | Timestamp when deployment data was generated |
| `data_period_start` | string (date-time) | Yes | Start of the analysis period |
| `data_period_end` | string (date-time) | Yes | End of the analysis period |
| `service_name` | string | Yes | Name of the service |
| `namespace` | string | Yes | Kubernetes namespace |
| `cluster` | string | Yes | Kubernetes cluster identifier |
| `data_sources` | array of strings | No | Data sources used to compile deployment information |

### Deployment Info Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `deployment_name` | string | Yes | Kubernetes deployment name |
| `created_at` | string (date-time) | Yes | Initial deployment creation timestamp |
| `current_image` | string (pattern) | Yes | Current container image |
| `current_replicas` | integer (≥0) | Yes | Current number of desired replicas |
| `last_updated` | string (date-time) or null | No | Most recent deployment update timestamp |

### Current Status Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `sync_status` | enum (Synced, OutOfSync, Unknown) | Yes | ArgoCD sync status |
| `health_status` | enum (Healthy, Progressing, Degraded, Missing, Unknown) | Yes | Overall deployment health status |
| `ready_replicas` | integer (≥0) | Yes | Number of ready replicas |
| `available_replicas` | integer (≥0) | Yes | Number of available replicas |
| `updated_replicas` | integer (≥0) | Yes | Number of updated replicas |

### Metrics Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `total_deployments` | integer (≥0) | Yes | Total deployments in analysis period |
| `successful_deployments` | integer (≥0) | Yes | Number of successful deployments |
| `failed_deployments` | integer (≥0) | Yes | Number of failed deployments |
| `deployment_success_rate` | number (0.0-1.0) | Yes | Success rate as decimal |
| `last_deployment_timestamp` | string (date-time) or null | Yes | Last deployment timestamp |
| `days_since_last_deployment` | integer (≥0) | Yes | Days since last deployment |
| `rollbacks` | integer (≥0) | No | Number of rollback operations |
| `deployment_frequency_days` | number (≥0) | No | Average days between deployments |

## Data Types and Constraints

### Timestamps (ISO 8601)

All timestamp fields use ISO 8601 format with the `date-time` format validator:
- `generated_at`: "2026-08-06T12:03:32.329077Z"
- `data_period_start`: "2026-07-07T09:07:50Z"
- `data_period_end`: "2026-08-06T09:07:50Z"

Pattern: `^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})$`

### Container Images

Container image fields use pattern validation:
- Pattern: `^[a-z0-9-]+/[a-z0-9-]+:[\w.+]+$`
- Example: "ronaldraygun/whisper-stt:1.8.6"

### Resource Specifications

CPU and memory fields use pattern validation:

**CPU:**
- Pattern: `^[\d]+m?$|^[\d]+$`
- Examples: "1" (1 core), "500m" (500 millicores)

**Memory:**
- Pattern: `^[\d]+(Ei|Pi|Ti|Gi|Mi|Ki|E|P|T|G|M|K)?$`
- Examples: "4Gi" (4 gibibytes), "512Mi" (512 mebibytes)

### Enums and Status Values

**Sync Status:**
- `"Synced"` - Deployment is in sync with Git
- `"OutOfSync"` - Deployment is out of sync
- `"Unknown"` - Status cannot be determined

**Health Status:**
- `"Healthy"` - Deployment is healthy
- `"Progressing"` - Deployment is progressing
- `"Degraded"` - Deployment is degraded
- `"Missing"` - Deployment is missing
- `"Unknown"` - Health status cannot be determined

**ReplicaSet Status:**
- `"successful"` - ReplicaSet deployed successfully
- `"rolled_over"` - ReplicaSet was rolled over
- `"scaled_down_or_failed"` - ReplicaSet scaled down or failed
- `"failed"` - ReplicaSet deployment failed

**Overall Health Status:**
- `"excellent"` - Service health is excellent
- `"good"` - Service health is good
- `"degraded"` - Service health is degraded
- `"poor"` - Service health is poor
- `"critical"` - Service health is critical

## Validation Examples

### Valid Data Structure

```json
{
  "metadata": {
    "generated_at": "2026-08-06T12:03:32Z",
    "data_period_start": "2026-07-07T09:07:50Z",
    "data_period_end": "2026-08-06T09:07:50Z",
    "service_name": "whisper-stt",
    "namespace": "whisper-stt",
    "cluster": "ardenone-cluster",
    "data_sources": ["kubernetes_replicasets", "argo_cd"]
  },
  "deployment_info": {
    "deployment_name": "whisper-stt",
    "created_at": "2026-05-01T17:26:49Z",
    "current_image": "ronaldraygun/whisper-stt:1.8.6",
    "current_replicas": 1,
    "last_updated": "2026-07-15T10:30:00Z"
  },
  "current_status": {
    "sync_status": "Synced",
    "health_status": "Healthy",
    "ready_replicas": 1,
    "available_replicas": 1,
    "updated_replicas": 1
  },
  "metrics": {
    "total_deployments": 2,
    "successful_deployments": 2,
    "failed_deployments": 0,
    "deployment_success_rate": 1.0,
    "last_deployment_timestamp": "2026-07-15T10:30:00Z",
    "days_since_last_deployment": 22,
    "rollbacks": 0,
    "deployment_frequency_days": 15.0
  },
  "summary": {
    "overall_health_status": "excellent",
    "data_coverage": "100%",
    "gaps_detected": false,
    "largest_gap_days": 0
  }
}
```

### Common Validation Errors

**1. Missing Required Field**
```
✗ Path: root | Error: 'metadata' is a required property
```
Ensure all required top-level fields are present.

**2. Invalid Timestamp Format**
```
✗ Path: metadata.data_period_start | Error: does not match format 'date-time'
```
Use ISO 8601 format: `YYYY-MM-DDTHH:MM:SSZ`

**3. Invalid Status Enum**
```
✗ Path: current_status.sync_status | Error: 'NotSynced' is not a valid enum value
```
Use only allowed enum values: `"Synced"`, `"OutOfSync"`, `"Unknown"`

**4. Invalid Image Pattern**
```
✗ Path: deployment_info.current_image | Error: does not match pattern
```
Use format: `registry/image:tag` (e.g., `"ronaldraygun/whisper-stt:1.8.6"`)

**5. Wrong Data Type**
```
✗ Path: metrics.total_deployments | Error: expected integer, got string
```
Ensure counts are integers, not strings (e.g., `2` not `"2"`)

## Schema Version

- **Schema Version**: 1.0
- **JSON Schema Draft**: 2020-12
- **Last Updated**: 2026-08-06
- **Compatibility**: Service-agnostic design

## Usage

### Python Validation

```python
import json
from jsonschema import validate, Draft202012Validator

# Load schema
with open('core-deployment-schema.json', 'r') as f:
    schema = json.load(f)

# Load data
with open('deployment-data.json', 'r') as f:
    data = json.load(f)

# Validate
validator = Draft202012Validator(schema)
errors = list(validator.iter_errors(data))

if errors:
    for error in errors:
        print(f"✗ Path: {'.'.join(str(p) for p in error.path)} | Error: {error.message}")
else:
    print("✓ Schema validation passed")
```

### CLI Validation with jq

```bash
# Quick schema structure check
jq 'has("metadata", "deployment_info", "current_status", "metrics")' deployment-data.json
```

## Extending the Schema

To create service-specific schemas:

1. **Import the core schema** using `$ref` or extend with additional properties
2. **Add service-specific fields** (e.g., model cache for whisper-stt)
3. **Refine validation rules** for specific requirements
4. **Maintain backward compatibility** with the core schema

Example extension pattern:
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "allOf": [
    {"$ref": "https://aide-de-camp.ardenone.com/schemas/core-deployment.json"},
    {
      "properties": {
        "whisper_stt_specific": {
          "type": "object",
          "properties": {
            "model_cache_status": {"type": "string"},
            "language_support": {"type": "array", "items": {"type": "string"}}
          }
        }
      }
    }
  ]
}
```

## Related Files

- `whisper-stt-deployment-data-schema.json` - Service-specific comprehensive schema
- `src/schemas/whisper_stt_deployment.py` - Pydantic models
- `whisper-stt-deployment-schema-README.md` - Service-specific schema documentation

## Maintenance

To update this schema:

1. Validate changes against JSON Schema Draft 2020-12 specification
2. Ensure backward compatibility with existing data
3. Update this README with new fields or validation rules
4. Test validation against sample deployment data files
