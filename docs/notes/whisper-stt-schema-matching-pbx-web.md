# Whisper-STT Deployment Schema Design
## Matching pbx-web Data Structure

**Purpose:** Design whisper-stt deployment data schema to match pbx-web format for cross-service comparative analysis.

**Schema Version:** 2.0  
**Created:** 2026-08-06  
**Status:** Ready for Implementation

---

## Overview

The whisper-stt deployment data will be restructured to match the pbx-web schema format, enabling consistent comparative analysis across services. This design maintains all whisper-stt-specific data while adopting the pbx-web structure.

---

## Schema Structure Mapping

### 1. Metadata Section
**Corresponds to pbx-web: `metadata`**

```json
{
  "metadata": {
    "service": "whisper-stt",
    "namespace": "whisper-stt", 
    "cluster": "ardenone-cluster",
    "data_collected_at": "2026-08-06T12:37:36Z",
    "time_period": {
      "start": "2026-07-07T00:00:00Z",
      "end": "2026-08-06T12:37:36Z",
      "description": "Last 30 days"
    },
    "managed_by": "ArgoCD",
    "strategy": "Recreate"
  }
}
```

**Field Types:**
- `service`: string (Kubernetes name pattern, 1-63 chars)
- `namespace`: string (Kubernetes name pattern, 1-63 chars)
- `cluster`: string (DNS name pattern, 1-253 chars)
- `data_collected_at`: string (ISO 8601 timestamp with timezone)
- `time_period`: object (nested structure)
  - `start`: string (ISO 8601 timestamp)
  - `end`: string (ISO 8601 timestamp)
  - `description`: string (human-readable)
- `managed_by`: string (deployment management system)
- `strategy`: string (deployment strategy: "Recreate" or "RollingUpdate")

---

### 2. Current Status Section
**Corresponds to pbx-web: `current_status`**

```json
{
  "current_status": {
    "deployment_name": "whisper-stt",
    "current_revision": 32,
    "current_image": "ronaldraygun/whisper-stt:1.8.6",
    "generation": 353,
    "replicas": 1,
    "readyReplicas": 1,
    "updatedReplicas": 1,
    "availableReplicas": 1,
    "current_pod": "whisper-stt-847fd8d7b9-v2rs5",
    "pod_created_at": "2026-07-12T16:53:42Z",
    "conditions": [
      {
        "type": "Progressing",
        "status": "True",
        "reason": "NewReplicaSetAvailable",
        "message": "ReplicaSet \"whisper-stt-847fd8d7b9\" has successfully progressed.",
        "lastTransitionTime": "2026-07-12T16:54:57Z"
      },
      {
        "type": "Available",
        "status": "True",
        "reason": "MinimumReplicasAvailable",
        "message": "Deployment has minimum availability.",
        "lastTransitionTime": "2026-07-12T16:54:57Z"
      }
    ]
  }
}
```

**Field Types:**
- `deployment_name`: string (Kubernetes Deployment name)
- `current_revision`: number (deployment revision number)
- `current_image`: string (Docker image reference)
- `generation`: number (Kubernetes generation number)
- `replicas`: number (desired replica count)
- `readyReplicas`: number (ready replica count)
- `updatedReplicas`: number (updated replica count)
- `availableReplicas`: number (available replica count)
- `current_pod`: string (current pod name)
- `pod_created_at`: string (ISO 8601 timestamp)
- `conditions`: array of objects (deployment conditions)
  - Each condition: `type`, `status`, `reason`, `message`, `lastTransitionTime`

---

### 3. Deployment Events Section
**Corresponds to pbx-web: `deployment_events_last_30_days`**

```json
{
  "deployment_events_last_30_days": [
    {
      "date": "2026-07-12",
      "timestamp": "2026-07-12T16:54:57Z",
      "event_type": "deployment_rollout",
      "revision": 32,
      "replicaSet": "whisper-stt-847fd8d7b9",
      "image": "ronaldraygun/whisper-stt:1.8.6",
      "outcome": "success",
      "pod_name": "whisper-stt-847fd8d7b9-v2rs5",
      "pod_ready": true,
      "restart_count": 0,
      "notes": "Current active deployment"
    },
    {
      "date": "2026-07-08",
      "timestamp": "2026-07-08T03:26:44Z",
      "event_type": "deployment_rollout",
      "revision": 31,
      "replicaSet": "whisper-stt-6c497489fb",
      "image": "ronaldraygun/whisper-stt:1.8.6",
      "outcome": "success",
      "pod_name": "whisper-stt-6c497489fb-xxxxx",
      "pod_ready": true,
      "restart_count": 0,
      "notes": "Previous deployment"
    }
  ]
}
```

**Field Types:**
- `deployment_events_last_30_days`: array of deployment event objects
  - `date`: string (ISO 8601 date format)
  - `timestamp`: string (ISO 8601 timestamp with timezone)
  - `event_type`: string (deployment event type)
  - `revision`: number (deployment revision number)
  - `replicaSet`: string (ReplicaSet name with hash)
  - `image`: string (Docker image reference)
  - `outcome`: string (deployment outcome status)
  - `pod_name`: string (pod name)
  - `pod_ready`: boolean (pod readiness status)
  - `restart_count`: number (container restart count)
  - `notes`: string (additional information)

---

### 4. Historical Deployments Section
**Corresponds to pbx-web: `historical_deployments_beyond_30_days`**

```json
{
  "historical_deployments_beyond_30_days": [
    {
      "date": "2026-06-15",
      "timestamp": "2026-06-15T18:11:38Z",
      "revision": 30,
      "replicaSet": "whisper-stt-5b8558f478",
      "image": "ronaldraygun/whisper-stt:1.8.4",
      "notes": "Prior to 30-day window"
    }
  ]
}
```

**Field Types:**
- `historical_deployments_beyond_30_days`: array of historical deployment objects
  - `date`: string (ISO 8601 date format)
  - `timestamp`: string (ISO 8601 timestamp with timezone)
  - `revision`: number (deployment revision number)
  - `replicaSet`: string (ReplicaSet name)
  - `image`: string (Docker image reference)
  - `notes`: string (context information)

---

### 5. Deployment Metrics Section
**Corresponds to pbx-web: `deployment_metrics`**

```json
{
  "deployment_metrics": {
    "total_deployments_last_30_days": 4,
    "successful_deployments": 4,
    "failed_deployments": 0,
    "deployment_frequency_days": 7,
    "unique_images_deployed": 2,
    "images_used_last_30_days": [
      "ronaldraygun/whisper-stt:1.8.6",
      "ronaldraygun/whisper-stt:1.8.4"
    ],
    "current_uptime_days": 25,
    "last_deployment": "2026-07-12T16:54:57Z",
    "days_since_last_deployment": 25
  }
}
```

**Field Types:**
- `total_deployments_last_30_days`: number (deployment count)
- `successful_deployments`: number (successful deployment count)
- `failed_deployments`: number (failed deployment count)
- `deployment_frequency_days`: number (average days between deployments)
- `unique_images_deployed`: number (unique image count)
- `images_used_last_30_days`: array of strings (Docker image references)
- `current_uptime_days`: number (current deployment uptime in days)
- `last_deployment`: string (ISO 8601 timestamp)
- `days_since_last_deployment`: number (days since last deployment)

---

### 6. Pod Health Section
**Corresponds to pbx-web: `pod_health`**

```json
{
  "pod_health": {
    "current_pod": {
      "name": "whisper-stt-847fd8d7b9-v2rs5",
      "created_at": "2026-07-12T16:53:42Z",
      "phase": "Running",
      "ready": true,
      "restart_count": 0,
      "uptime_days": 25,
      "containers": [
        {
          "name": "whisper-stt",
          "image": "ronaldraygun/whisper-stt:1.8.6",
          "ready": true,
          "restartCount": 0,
          "running_since": "2026-07-12T16:55:49Z"
        }
      ]
    },
    "health_indicators": {
      "no_crashes": true,
      "no_restart_loops": true,
      "no_image_pull_errors": true,
      "liveness_probes_passing": true,
      "readiness_probes_passing": true
    }
  }
}
```

**Field Types:**
- `current_pod`: object (pod details)
  - `name`: string (pod name)
  - `created_at`: string (ISO 8601 timestamp)
  - `phase`: string (pod phase: Running, Pending, etc.)
  - `ready`: boolean (pod readiness)
  - `restart_count`: number (container restart count)
  - `uptime_days`: number (pod uptime in days)
  - `containers`: array of container objects
    - `name`: string (container name)
    - `image`: string (Docker image)
    - `ready`: boolean (container readiness)
    - `restartCount`: number (container restart count)
    - `running_since`: string (ISO 8601 timestamp)
- `health_indicators`: object (health status flags)
  - Each indicator: boolean (true = healthy, false = unhealthy)

---

### 7. Operational Logs Section
**Corresponds to pbx-web: `operational_logs_sample`**

```json
{
  "operational_logs_sample": {
    "recent_activity": "Normal operation - no error patterns detected",
    "last_log_analysis": "2026-08-06T09:07:50Z",
    "analysis_period": "2026-07-12 to 2026-08-06",
    "log_health": "normal - no errors or warnings in recent logs",
    "service_specific": {
      "transcription_activity": "Low usage - service available for on-demand transcription",
      "model_cache_status": "Models cached and ready",
      "api_response_times": "Normal - average response time under 2s"
    }
  }
}
```

**Field Types:**
- `recent_activity`: string (activity description)
- `last_log_analysis`: string (ISO 8601 timestamp)
- `analysis_period`: string (time range description)
- `log_health`: string (log health status)
- `service_specific`: object (service-specific operational data)
  - Whisper-STT specific fields as needed

---

### 8. Infrastructure Details Section
**Corresponds to pbx-web: `infrastructure_details`**

```json
{
  "infrastructure_details": {
    "resource_limits": {
      "whisper-stt": {
        "cpu_limit": "8",
        "memory_limit": "8Gi",
        "cpu_request": "1",
        "memory_request": "4Gi"
      }
    },
    "volumes": [
      {
        "name": "whisper-model-cache",
        "type": "persistentVolumeClaim",
        "pvc": "whisper-model-cache",
        "capacity": "10Gi",
        "storage_class": "longhorn",
        "purpose": "Cache for Whisper ML models"
      },
      {
        "name": "whisper-stt-jobs",
        "type": "persistentVolumeClaim", 
        "pvc": "whisper-stt-jobs",
        "capacity": "1Gi",
        "storage_class": "longhorn",
        "purpose": "Temporary transcription job storage"
      }
    ],
    "environment_variables": {
      "WHISPER_MODEL": "medium",
      "WHISPER_LANGUAGE": "en",
      "LOG_LEVEL": "info"
    },
    "secrets_used": [
      "whisper-stt-api-keys",
      "whisper-stt-config"
    ],
    "liveness_probes": {
      "whisper_stt": {
        "path": "/health",
        "port": 8000,
        "initialDelaySeconds": 30,
        "periodSeconds": 10,
        "timeoutSeconds": 5,
        "failureThreshold": 3
      }
    },
    "readiness_probes": {
      "whisper_stt": {
        "path": "/ready",
        "port": 8000,
        "initialDelaySeconds": 10,
        "periodSeconds": 5,
        "timeoutSeconds": 3,
        "failureThreshold": 3
      }
    }
  }
}
```

**Field Types:**
- `resource_limits`: object (container resource limits)
  - Per-container: `cpu_limit`, `memory_limit`, `cpu_request`, `memory_request` (strings)
- `volumes`: array of volume objects
  - `name`: string (volume name)
  - `type`: string (volume type)
  - `pvc`: string (PVC name, if applicable)
  - `capacity`: string (storage capacity)
  - `storage_class`: string (storage class)
  - `purpose`: string (volume purpose)
- `environment_variables`: object (env var key-value pairs)
- `secrets_used`: array of strings (secret names)
- `liveness_probes`: object (probe configurations)
- `readiness_probes`: object (probe configurations)

---

### 9. Summary Section
**Corresponds to pbx-web: `summary`**

```json
{
  "summary": {
    "overall_health": "excellent",
    "deployment_stability": "stable",
    "uptime": "25 days continuous",
    "issues_last_30_days": 0,
    "rollbacks_last_30_days": 0,
    "deployment_success_rate": "100%",
    "recommendation": "Service is healthy with stable deployment pattern. Zero incidents, zero downtime, zero restarts."
  }
}
```

**Field Types:**
- `overall_health`: string (health status: excellent, good, degraded, poor, critical)
- `deployment_stability`: string (stability assessment: stable, moderate, unstable)
- `uptime`: string (uptime description)
- `issues_last_30_days`: number (issue count)
- `rollbacks_last_30_days`: number (rollback count)
- `deployment_success_rate`: string (percentage format)
- `recommendation`: string (operational recommendation)

---

## Data Type Alignment Summary

| Field Category | pbx-web Type | whisper-stt Type | Alignment Status |
|---------------|-------------|------------------|------------------|
| **Identifiers** | | | |
| service names | string (1-63 chars) | string (1-63 chars) | ✅ Matched |
| cluster name | string (DNS pattern) | string (DNS pattern) | ✅ Matched |
| namespace | string (1-63 chars) | string (1-63 chars) | ✅ Matched |
| **Timestamps** | | | |
| dates/times | ISO 8601 | ISO 8601 | ✅ Matched |
| **Counts** | | | |
| replica counts | number (0-100) | number (0-100) | ✅ Matched |
| revision numbers | number | number | ✅ Matched |
| **Images** | | | |
| image references | Docker format | Docker format | ✅ Matched |
| **Arrays** | | | |
| events | array of objects | array of objects | ✅ Matched |
| volumes | array of objects | array of objects | ✅ Matched |
| conditions | array of objects | array of objects | ✅ Matched |
| **Nested Objects** | | | |
| time_period | object | object | ✅ Matched |
| current_pod | object with nested arrays | object with nested arrays | ✅ Matched |
| resource_limits | object of objects | object of objects | ✅ Matched |

---

## Implementation Notes

### Whisper-STT Specific Considerations

1. **Multi-Deployment Namespace**: whisper-stt namespace contains both `whisper-stt` and `whisper-openai` deployments. The schema should handle multiple deployments per namespace.

2. **Storage-Heavy Service**: whisper-stt uses PVCs for model caching and job storage, which should be documented in the `volumes` section.

3. **GPU vs CPU**: Different deployments may have different resource requirements (CPU vs GPU), which should be reflected in `resource_limits`.

4. **Service-Specific Metrics**: The `operational_logs_sample` section includes whisper-stt specific fields like transcription activity and model cache status.

### Data Transformation Requirements

To convert existing whisper-stt data to the pbx-web format:

1. Flatten nested deployment objects in `current_status`
2. Restructure `deployment_history_30_days` to match `deployment_events_last_30_days` format
3. Separate historical deployments beyond 30 days into `historical_deployments_beyond_30_days`
4. Restructure `operational_metrics` into `deployment_metrics` and `pod_health` sections
5. Extract infrastructure details into dedicated `infrastructure_details` section
6. Create a summary section based on calculated metrics

### Validation Rules

- All timestamps must be ISO 8601 format with timezone
- All counts must be non-negative integers
- Replica counts must respect hierarchy (ready ≤ total, etc.)
- Image references must follow Docker format and avoid `:latest` tag
- Kubernetes names must follow naming conventions (1-63 chars, alphanumeric with hyphens)

---

## Schema Validation

This schema design ensures:

✅ **Field Consistency**: All field types match pbx-web format  
✅ **Structural Alignment**: Nesting and arrays match pbx-web structure  
✅ **Data Completeness**: All whisper-stt specific data is preserved  
✅ **Cross-Service Compatibility**: Enables comparative analysis  
✅ **Validation**: Type constraints and validation rules defined  

---

## Next Steps

1. **Implement Data Transformer**: Create conversion utility to transform existing whisper-stt data to new schema
2. **Update Data Collection**: Modify data collection scripts to output pbx-web format
3. **Validation Testing**: Create validation tests to ensure schema compliance
4. **Comparative Analysis**: Apply comparative analysis tools to both services

---

**Document Status:** ✅ Schema design complete and ready for implementation
**Related Files:**
- `pbx-web-deployment-data-30days.json` (reference structure)
- `whisper-stt-deployment-data-30days.json` (source data to transform)
- `src/schemas/whisper_stt_deployment.py` (existing schema to update)