# whisper-stt Deployment Data Schema

**Purpose**: Define the deployment data schema for whisper-stt service to match the pbx-web format identified in previous analysis.

**Schema Version**: 1.0  
**Date**: 2026-08-06  
**Bead ID**: adc-63f3u  
**Reference**: Based on pbx-web deployment data structure from `deployment_data_raw.json`

---

## Schema Overview

The whisper-stt deployment schema follows the same structure as pbx-web, enabling:
- Consistent data analysis across services
- Unified validation and processing pipelines
- Cross-service deployment comparisons
- Standardized reporting formats

---

## Top-Level Schema Structure

```json
{
  "metadata": {
    "generated_at": "ISO 8601 timestamp",
    "data_period_start": "ISO 8601 timestamp", 
    "data_period_end": "ISO 8601 timestamp",
    "services": ["whisper-stt"],
    "clusters": ["ardenone-cluster"],
    "data_sources": ["kubernetes_replicasets", "argo_workflows", "argo_cd"]
  },
  "argo_workflows": { ... },
  "argo_cd": { ... },
  "cluster_deployments": {
    "whisper-stt": { ... }
  },
  "summary": { ... },
  "notes": [ ... ]
}
```

---

## Field Definitions

### 1. Metadata Section

**Type**: Object  
**Required**: Yes  
**Description**: Top-level metadata describing the dataset

```json
{
  "metadata": {
    "generated_at": "2026-08-06T09:30:00Z",           // ISO 8601 UTC timestamp
    "data_period_start": "2026-07-06T00:00:00Z",      // Analysis start date
    "data_period_end": "2026-08-06T09:30:00Z",        // Analysis end date
    "services": ["whisper-stt"],                      // Services in this dataset
    "clusters": ["ardenone-cluster"],                 // Kubernetes clusters
    "data_sources": ["kubernetes_replicasets",         // Data collection methods
                   "argo_workflows", 
                   "argo_cd"]
  }
}
```

**Field Types**:
- `generated_at`: string (ISO 8601 timestamp, required)
- `data_period_start`: string (ISO 8601 timestamp, required)
- `data_period_end`: string (ISO 8601 timestamp, required)
- `services`: array of strings (required)
- `clusters`: array of strings (required)
- `data_sources`: array of strings (required)

---

### 2. Argo Workflows Section

**Type**: Object  
**Required**: Yes  
**Description**: CI/CD workflow data from Argo Workflows

```json
{
  "argo_workflows": {
    "whisper_stt_build": {
      "template_name": "whisper-stt-build",           // WorkflowTemplate name
      "template_created": "2026-05-27T02:26:47Z",     // Template creation timestamp
      "workflow_runs_last_30_days": 0,                // Number of workflow runs
      "workflow_runs": []                              // Array of workflow run objects
    }
  }
}
```

**Field Types**:
- `template_name`: string (required)
- `template_created`: string (ISO 8601 timestamp, required)
- `workflow_runs_last_30_days`: integer (required, min: 0)
- `workflow_runs`: array of objects (required, can be empty)

**Workflow Run Object** (if present):
```json
{
  "workflow_name": "whisper-stt-build-xxxxx",
  "started_at": "2026-07-01T10:00:00Z",
  "finished_at": "2026-07-01T10:15:00Z",
  "status": "Succeeded",  // or "Failed", "Running"
  "git_revision": "abc123",
  "image_tag": "1.8.6"
}
```

---

### 3. ArgoCD Section

**Type**: Object  
**Required**: Yes  
**Description**: ArgoCD application management data

```json
{
  "argo_cd": {
    "whisper-stt": {
      "application_found": false,                       // ArgoCD app exists
      "applications": []                                // Array of ArgoCD app objects
    }
  }
}
```

**Field Types**:
- `application_found`: boolean (required)
- `applications`: array of objects (required, can be empty)

**ArgoCD Application Object** (if present):
```json
{
  "name": "whisper-stt",
  "namespace": "whisper-stt",
  "project": "default",
  "sync_status": "Synced",
  "health_status": "Healthy",
  "server": "https://kubernetes.default.svc",
  "namespace": "whisper-stt"
}
```

---

### 4. Cluster Deployments Section

**Type**: Object  
**Required**: Yes  
**Description**: Core Kubernetes deployment data

```json
{
  "cluster_deployments": {
    "whisper-stt": {
      "namespace": "whisper-stt",
      "deployment_name": "whisper-stt",
      "created_at": "2026-05-01T17:26:49Z",
      "current_image": "ronaldraygun/whisper-stt:1.8.6",
      "current_replicas": 1,
      "last_updated": "2026-07-12T16:54:57Z",
      "replica_history": [ ... ],
      "deployments_last_30_days": 4,
      "successful_deployments": 1,
      "failed_deployments": 3,
      "deployment_versions": ["1.8.6", "1.8.4", "1.8.2"],
      "all_versions_in_history": ["1.2.5", "1.3.0", "1.3.1", "1.4.1", "1.5.1", "1.6.0", "1.7.0", "1.8.2", "1.8.4", "1.8.6"]
    }
  }
}
```

**Field Types**:
- `namespace`: string (required)
- `deployment_name`: string (required)
- `created_at`: string (ISO 8601 timestamp, required)
- `current_image`: string (required, format: `repo/image:tag`)
- `current_replicas`: integer (required, min: 0)
- `last_updated`: string (ISO 8601 timestamp, optional)
- `replica_history`: array of objects (required)
- `deployments_last_30_days`: integer (required, min: 0)
- `successful_deployments`: integer (required, min: 0)
- `failed_deployments`: integer (required, min: 0)
- `deployment_versions`: array of strings (required)
- `all_versions_in_history`: array of strings (required)

**Replica History Object**:
```json
{
  "name": "whisper-stt-847fd8d7b9",                   // ReplicaSet name
  "created_at": "2026-07-12T16:53:42Z",              // Creation timestamp
  "image": "ronaldraygun/whisper-stt:1.8.6",         // Container image
  "replicas": 1,                                      // Current replica count
  "available_replicas": 1,                            // Available replicas
  "ready_replicas": 1,                               // Ready replicas
  "status": "successful",                             // "successful", "rolled_over", "scaled_down_or_failed"
  "days_ago": 25                                     // Days since creation
}
```

**Replica History Field Types**:
- `name`: string (required)
- `created_at`: string (ISO 8601 timestamp, required)
- `image`: string (required)
- `replicas`: integer (required, min: 0)
- `available_replicas`: integer or null (required)
- `ready_replicas`: integer or null (required)
- `status`: string (required, enum: ["successful", "rolled_over", "scaled_down_or_failed"])
- `days_ago`: integer (required, min: 0)

---

### 5. Summary Section

**Type**: Object  
**Required**: Yes  
**Description**: High-level metrics and statistics

```json
{
  "summary": {
    "total_deployments_last_30_days": 6,            // Total deployments across services
    "whisper_stt_deployments": 4,                   // Service-specific deployments
    "successful_deployments": 2,                      // Successful deployments
    "failed_or_scaled_down": 4,                      // Failed/scaled-down deployments
    "data_coverage": "100%",                         // Data completeness percentage
    "gaps_detected": false,                          // Whether gaps exist in data
    "largest_gap_days": 0                            // Largest gap in days (if gaps detected)
  }
}
```

**Field Types**:
- `total_deployments_last_30_days`: integer (required, min: 0)
- `whisper_stt_deployments`: integer (required, min: 0)
- `successful_deployments`: integer (required, min: 0)
- `failed_or_scaled_down`: integer (required, min: 0)
- `data_coverage`: string (required, format: "XX%")
- `gaps_detected`: boolean (required)
- `largest_gap_days`: integer (required, min: 0)

---

### 6. Notes Section

**Type**: Array of strings  
**Required**: Yes  
**Description**: Qualitative observations and context

```json
{
  "notes": [
    "No Argo Workflow runs found for whisper-stt in the last 30 days",
    "Deployments appear to be managed via ArgoCD or manual kubectl operations",
    "whisper-stt had multiple deployment attempts on 2026-07-08 before stabilizing on 2026-07-12",
    "Service is running on ardenone-cluster",
    "Current version: whisper-stt 1.8.6"
  ]
}
```

**Field Types**:
- Array of strings (required, can be empty)

---

## Extended Schema Fields (Optional but Recommended)

For enhanced analysis, these optional fields can be added:

### A. Pod Health Metrics

```json
{
  "pod_health": {
    "current_pods": [
      {
        "name": "whisper-stt-847fd8d7b9-v2rs5",
        "created": "2026-07-12T16:53:42Z",
        "age_days": 25,
        "status": "Running",
        "restart_count": 0,
        "node": "k3s-agent-minisforum",
        "containers": [
          {
            "name": "whisper-stt",
            "image": "ronaldraygun/whisper-stt:1.8.6",
            "ready": true,
            "restart_count": 0
          }
        ]
      }
    ],
    "pod_metrics": {
      "total_pods": 1,
      "running_pods": 1,
      "total_containers": 1,
      "total_restarts": 0,
      "crashloops": 0,
      "oomkills": 0,
      "failed_pods": 0,
      "pending_pods": 0
    }
  }
}
```

### B. Resource Utilization

```json
{
  "resources": {
    "cpu_requests": "1",
    "cpu_limits": "8",
    "memory_requests": "4Gi",
    "memory_limits": "8Gi",
    "current_cpu_usage": "5m",
    "current_memory_usage": "3137Mi"
  }
}
```

### C. Storage Information

```json
{
  "storage": {
    "whisper-model-cache": {
      "capacity": "10Gi",
      "storage_class": "longhorn",
      "status": "Bound",
      "age_days": 84
    },
    "whisper-openai-model-cache": {
      "capacity": "10Gi", 
      "storage_class": "longhorn",
      "status": "Bound",
      "age_days": 53
    },
    "whisper-stt-jobs": {
      "capacity": "1Gi",
      "storage_class": "longhorn", 
      "status": "Bound",
      "age_days": 42
    }
  }
}
```

### D. Error Incidents

```json
{
  "error_incidents": {
    "total_incidents": 0,
    "critical_incidents": 0,
    "warning_incidents": 0,
    "incident_details": []
  }
}
```

---

## Validation Rules

### Required Field Validation

1. **All top-level sections must be present**: `metadata`, `argo_workflows`, `argo_cd`, `cluster_deployments`, `summary`, `notes`

2. **Timestamps must be ISO 8601 format**: All timestamp fields must parse to valid datetime objects

3. **Numeric field constraints**:
   - All count fields must be ≥ 0
   - Replica counts must match Kubernetes spec
   - Success rates must be 0-100%

4. **Array field constraints**:
   - All arrays must be present (can be empty)
   - Service names in arrays must match actual services

### Data Consistency Validation

1. **Replica count consistency**: `successful_deployments` + `failed_deployments` ≤ `deployments_last_30_days`

2. **Timestamp ordering**: `data_period_start` < `data_period_end` < `generated_at`

3. **Image version consistency**: `current_image` tag must appear in `deployment_versions`

4. **Pod count consistency**: `running_pods` ≤ `total_pods`

---

## Comparison with pbx-web Schema

| Field Category | pbx-web | whisper-stt | Match Status |
|----------------|---------|-------------|--------------|
| **Metadata** | ✅ Present | ✅ Present | ✅ Identical |
| **Argo Workflows** | ✅ Present | ✅ Present | ✅ Identical |
| **ArgoCD** | ✅ Present | ✅ Present | ✅ Identical |
| **Cluster Deployments** | ✅ Present | ✅ Present | ✅ Identical |
| **Replica History** | ✅ Present | ✅ Present | ✅ Identical |
| **Deployment Metrics** | ✅ Present | ✅ Present | ✅ Identical |
| **Summary** | ✅ Present | ✅ Present | ✅ Identical |
| **Notes** | ✅ Present | ✅ Present | ✅ Identical |
| **Extended Fields** | ⚠️ Partial | ✅ Complete | ✅ Enhanced |

---

## Implementation Notes

### Data Collection Priority

1. **High Priority** (required for analysis):
   - `metadata`, `cluster_deployments`, `summary`
   - Replica history with timestamps
   - Deployment success/failure counts

2. **Medium Priority** (enhances analysis):
   - Pod health metrics
   - Resource utilization
   - Storage information

3. **Low Priority** (contextual):
   - Argo Workflows data (often empty)
   - ArgoCD application status
   - Error incident details

### Data Source Mapping

| Schema Field | Kubernetes Source | Collection Method |
|--------------|-------------------|-------------------|
| Replica history | `ReplicaSet` resources | `kubectl get replicasets` |
| Current status | `Deployment` resources | `kubectl get deployments` |
| Pod health | `Pod` resources | `kubectl get pods` |
| Storage info | `PersistentVolumeClaim` | `kubectl get pvc` |
| ArgoCD status | `Application` CRDs | ArgoCD API or kubectl |
| Workflows | `Workflow` CRDs | Argo Workflow API |

---

## Type Definitions (Python)

For implementation, these Python type definitions can be used:

```python
from typing import Dict, List, Optional, Any
from datetime import datetime
from pydantic import BaseModel, Field, validator

class TimestampedModel(BaseModel):
    """Base model with timestamp validation."""
    
    @validator('*')
    def validate_timestamps(cls, v, field):
        if field.name.endswith(('_at', '_time')) and isinstance(v, str):
            try:
                datetime.fromisoformat(v.replace('Z', '+00:00'))
            except ValueError:
                raise ValueError(f"Invalid ISO 8601 timestamp: {v}")
        return v

class WorkflowRun(TimestampedModel):
    workflow_name: str
    started_at: str
    finished_at: Optional[str] = None
    status: str = Field(..., regex="^(Succeeded|Failed|Running)$")
    git_revision: Optional[str] = None
    image_tag: Optional[str] = None

class ArgoWorkflowData(TimestampedModel):
    template_name: str
    template_created: str
    workflow_runs_last_30_days: int = Field(..., ge=0)
    workflow_runs: List[WorkflowRun] = []

class ArgoCDApplication(TimestampedModel):
    name: str
    namespace: str
    project: str = "default"
    sync_status: Optional[str] = None
    health_status: Optional[str] = None

class ArgoCDData(TimestampedModel):
    application_found: bool
    applications: List[ArgoCDApplication] = []

class ReplicaHistoryEntry(TimestampedModel):
    name: str
    created_at: str
    image: str
    replicas: int = Field(..., ge=0)
    available_replicas: Optional[int] = None
    ready_replicas: Optional[int] = None
    status: str = Field(..., regex="^(successful|rolled_over|scaled_down_or_failed)$")
    days_ago: int = Field(..., ge=0)

class ClusterDeploymentData(TimestampedModel):
    namespace: str
    deployment_name: str
    created_at: str
    current_image: str
    current_replicas: int = Field(..., ge=0)
    last_updated: Optional[str] = None
    replica_history: List[ReplicaHistoryEntry]
    deployments_last_30_days: int = Field(..., ge=0)
    successful_deployments: int = Field(..., ge=0)
    failed_deployments: int = Field(..., ge=0)
    deployment_versions: List[str]
    all_versions_in_history: List[str]

class SummaryMetrics(BaseModel):
    total_deployments_last_30_days: int = Field(..., ge=0)
    whisper_stt_deployments: int = Field(..., ge=0)
    successful_deployments: int = Field(..., ge=0)
    failed_or_scaled_down: int = Field(..., ge=0)
    data_coverage: str = Field(..., regex="^\\d+%$")
    gaps_detected: bool
    largest_gap_days: int = Field(..., ge=0)

class Metadata(TimestampedModel):
    generated_at: str
    data_period_start: str
    data_period_end: str
    services: List[str]
    clusters: List[str]
    data_sources: List[str]

class WhisperSTTDeploymentSchema(TimestampedModel):
    """Complete schema for whisper-stt deployment data."""
    
    metadata: Metadata
    argo_workflows: Dict[str, ArgoWorkflowData]
    argo_cd: Dict[str, ArgoCDData]
    cluster_deployments: Dict[str, ClusterDeploymentData]
    summary: SummaryMetrics
    notes: List[str] = []
    
    class Config:
        json_schema_extra = {
            "example": {
                "metadata": {
                    "generated_at": "2026-08-06T09:30:00Z",
                    "data_period_start": "2026-07-06T00:00:00Z",
                    "data_period_end": "2026-08-06T09:30:00Z",
                    "services": ["whisper-stt"],
                    "clusters": ["ardenone-cluster"],
                    "data_sources": ["kubernetes_replicasets", "argo_workflows", "argo_cd"]
                }
            }
        }
```

---

## Schema Versioning

**Current Version**: 1.0  
**Compatibility**: Fully compatible with pbx-web schema structure  

**Version History**:
- v1.0 (2026-08-06): Initial schema definition matching pbx-web format

**Future Changes**:
- Additions will be backward compatible
- Field removals will be deprecated first
- Major version changes indicate breaking changes

---

## Example Complete Document

See `/home/coding/aide-de-camp/deployment_data_raw.json` for pbx-web example structure. whisper-stt data should follow identical structure with service-specific values.

---

**End of Schema Definition**