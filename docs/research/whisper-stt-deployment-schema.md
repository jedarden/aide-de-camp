# Whisper-STT Deployment Data Schema

## Overview

This schema defines the structure for whisper-stt deployment data, designed to match the pbx-web deployment data format for consistency and cross-service comparability.

## Schema Structure

### Top-Level Dataset Structure

```json
{
  "metadata": { ... },
  "summaries": { 
    "whisper-stt": { ... }
  },
  "deployment_records": [ ... ]
}
```

## Field Definitions

### 1. Metadata Section

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| `generated_at` | string (ISO 8601) | Timestamp when dataset was generated | `"2026-08-06T10:30:00.000000+00:00"` |
| `source_files` | array of strings | List of source data files | `["whisper-stt-deployments-30d.json"]` |
| `total_records` | integer | Total number of deployment records | `4` |

### 2. Service Summary Section

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| `service` | string | Service identifier | `"whisper-stt"` |
| `total_deployments` | integer | Total number of deployment resources | `2` |
| `total_replicasets` | integer | Total number of replicaset resources | `4` |
| `successful_updates` | integer | Count of successful deployment updates | `3` |
| `failed_rollouts` | integer | Count of failed rollout attempts | `0` |
| `rollback_events` | integer | Count of rollback events | `0` |
| `last_deployment_update` | string (ISO 8601) | Timestamp of last deployment activity | `"2026-07-12T16:54:57+00:00"` |
| `overall_health` | enum | Overall service health assessment | `"healthy"` |
| `deployment_stability` | enum | Deployment stability assessment | `"high"` |
| `uptime_percentage` | string (percentage) | Service uptime percentage | `"100%"` |
| `zero_downtime_deployment` | boolean | Whether deployments cause downtime | `true` |
| `successful_deployment_rate` | string (percentage) | Percentage of successful deployments | `"100%"` |
| `total_pods` | integer | Total pod count across deployments | `2` |
| `running_pods` | integer | Currently running pod count | `2` |
| `total_restarts` | integer | Total container restart count | `0` |
| `crashloops` | integer | Count of pods in crash loop back-off | `0` |
| `oomkills` | integer | Count of OOM killed pods | `0` |
| `total_incidents` | integer | Total incident count | `0` |
| `critical_incidents` | integer | Critical incident count | `0` |
| `warning_incidents` | integer | Warning incident count | `0` |
| `log_errors` | integer | Total log error count | `0` |

### 3. Deployment Record Section

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| `service` | string | Service identifier | `"whisper-stt"` |
| `deployment_name` | string | Kubernetes Deployment resource name | `"whisper-stt"` |
| `replicaset_name` | string | Kubernetes ReplicaSet resource name | `"whisper-stt-5dbff75cbd"` |
| `timestamp` | string (ISO 8601) | Deployment creation timestamp | `"2026-07-08T03:09:35+00:00"` |
| `status` | enum | Deployment status | `"success"` |
| `failure_type` | enum or null | Specific failure type if status='failed' | `null` |
| `revision` | string | Deployment revision number | `"29"` |
| `replicas` | integer | Total replica count | `0` |
| `ready_replicas` | integer | Number of ready replicas | `0` |
| `available_replicas` | integer | Number of available replicas | `0` |
| `image` | string or null | Container image tag | `"ronaldraygun/whisper-stt:1.8.2"` |
| `cluster` | string | Cluster identifier | `"ardenone-cluster"` |
| `namespace` | string | Kubernetes namespace | `"whisper-stt"` |

## Enum Definitions

### Health Status Enum (`overall_health`)
- `healthy` - Service is operating normally
- `degraded` - Service has issues but is partially functional
- `unhealthy` - Service is not functioning properly
- `unknown` - Health status cannot be determined

### Stability Level Enum (`deployment_stability`)
- `high` - Consistent successful deployments
- `medium` - Some deployment issues but generally stable
- `low` - Frequent deployment problems
- `unknown` - Stability cannot be determined

### Deployment Status Enum (`status`)
- `success` - Deployment completed successfully
- `failed` - Deployment failed
- `pending` - Deployment is in progress
- `rollback` - Deployment was rolled back

### Failure Type Enum (`failure_type`)
- `image_pull_error` - Container image could not be pulled
- `crash_loop_back_off` - Container is repeatedly crashing
- `oom_killed` - Container was terminated due to memory exhaustion
- `probe_failure` - Health check probes are failing
- `pvc_mount_failed` - Persistent volume claim could not be mounted
- `resource_limit_exceeded` - Resource limits were exceeded
- `unknown` - Unknown failure type

## Schema Constraints

### Required Fields

**DeploymentRecord:**
- service, deployment_name, replicaset_name, timestamp, status, revision, replicas, ready_replicas, available_replicas, cluster, namespace

**ServiceSummary:**
- service, total_deployments, total_replicasets, successful_updates, failed_rollouts, rollback_events, last_deployment_update, overall_health, deployment_stability, uptime_percentage, zero_downtime_deployment, successful_deployment_rate, total_pods, running_pods, total_restarts, crashloops, oomkills, total_incidents, critical_incidents, warning_incidents, log_errors

**DeploymentMetadata:**
- generated_at, source_files, total_records

### Nullable Fields
- `failure_type` (null if deployment was successful)
- `image` (null if image information is not available)

### Format Requirements
- **Timestamps:** ISO 8601 format (e.g., `"2026-07-08T03:09:35+00:00"`)
- **Percentages:** String with % suffix (e.g., `"100%"`, `"99.9%"`)
- **Revisions:** String representation of integer (e.g., `"29"`, `"30"`)

## Example Data

```json
{
  "metadata": {
    "generated_at": "2026-08-06T10:30:00.000000+00:00",
    "source_files": ["whisper-stt-deployments-30d.json"],
    "total_records": 4
  },
  "summaries": {
    "whisper-stt": {
      "service": "whisper-stt",
      "total_deployments": 2,
      "total_replicasets": 4,
      "successful_updates": 3,
      "failed_rollouts": 0,
      "rollback_events": 0,
      "last_deployment_update": "2026-07-12T16:54:57+00:00",
      "overall_health": "healthy",
      "deployment_stability": "high",
      "uptime_percentage": "100%",
      "zero_downtime_deployment": true,
      "successful_deployment_rate": "100%",
      "total_pods": 2,
      "running_pods": 2,
      "total_restarts": 0,
      "crashloops": 0,
      "oomkills": 0,
      "total_incidents": 0,
      "critical_incidents": 0,
      "warning_incidents": 0,
      "log_errors": 0
    }
  },
  "deployment_records": [
    {
      "service": "whisper-stt",
      "deployment_name": "whisper-stt",
      "replicaset_name": "whisper-stt-5dbff75cbd",
      "timestamp": "2026-07-08T03:09:35+00:00",
      "status": "success",
      "failure_type": null,
      "revision": "29",
      "replicas": 0,
      "ready_replicas": 0,
      "available_replicas": 0,
      "image": "ronaldraygun/whisper-stt:1.8.2",
      "cluster": "ardenone-cluster",
      "namespace": "whisper-stt"
    }
  ]
}
```

## Compatibility with pbx-web Format

This schema is designed to match the pbx-web deployment data structure exactly:

✅ **Same top-level structure:** metadata, summaries, deployment_records
✅ **Same field names and types across all sections**
✅ **Same enum values for health, stability, and status**
✅ **Same format requirements (timestamps, percentages, revisions)**
✅ **Same nullable field conventions**

This allows direct comparison and analysis between pbx-web and whisper-stt deployment data using identical schemas.

## Implementation Notes

### Python Implementation
A complete Python implementation with dataclasses and validation is available in `whisper-stt-deployment-schema.py`:

- Type-safe dataclass definitions for all schema components
- Enum definitions for all constrained fields
- Schema validation function with detailed error reporting
- Example data generator

### Usage Example
```python
from whisper_stt_deployment_schema import example_whisper_stt_dataset, validate_schema

# Generate example data
data = example_whisper_stt_dataset()

# Validate schema
is_valid, errors = validate_schema(data)
if not is_valid:
    for error in errors:
        print(f"Validation error: {error}")
```

## Schema Validation

The schema includes comprehensive validation rules:

1. **Required field checking** - Ensures all required fields are present
2. **Type validation** - Verifies field types match schema definitions
3. **Format validation** - Checks timestamps, percentages, and other formatted fields
4. **Enum validation** - Ensures enum fields contain valid values
5. **Nullable field handling** - Correctly processes fields that can be null

## Next Steps

With this schema defined:
1. ✅ Schema is ready for implementation
2. 🔄 Collect whisper-stt deployment data following this schema
3. 🔄 Store data in JSON format matching this structure
4. 🔄 Use schema validation to ensure data quality
5. 🔄 Perform comparative analysis with pbx-web deployment data

---

**Schema Version:** 1.0  
**Last Updated:** 2026-08-06  
**Compatibility:** Matches pbx-web deployment data schema exactly