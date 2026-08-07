# Whisper-STT Deployment Data Structure Analysis

**Task ID:** adc-2uq7s  
**Date:** 2026-08-06  
**Purpose:** Analyze whisper-stt deployment data structure to inform schema design

## Executive Summary

The whisper-stt deployment data file follows a hierarchical JSON structure with **10 major top-level sections** and **approximately 85+ individual fields**. The structure is designed for 30-day deployment analysis with validation already implemented in both JSON Schema and Python dataclass formats.

---

## Top-Level Structure

The deployment data file consists of these main sections:

| Section | Required | Purpose |
|---------|----------|---------|
| `report_metadata` | Yes | Generation timestamps, time range, cluster/service info |
| `current_status.deployments` | Yes | Current deployment state and configuration |
| `deployment_history_30_days` | Yes | ReplicaSet history and events |
| `pod_status` | Yes | Current pod health and metrics |
| `operational_metrics` | Yes | Uptime, restarts, resources, storage |
| `log_analysis` | Yes | Log entry analysis |
| `argo_cd_integration` | Yes | ArgoCD tracking information |
| `error_incidents` | Yes | Error tracking (currently empty) |
| `deployment_health_assessment` | Yes | Overall health scoring |
| `comparison_with_previous_analysis` | No | Historical comparison |
| `recommendations` | No | Analysis recommendations |
| `summary` | Yes | Aggregate statistics |

---

## Field Inventory by Section

### 1. `report_metadata` (10 fields)

| Field | Type | Format/Pattern | Example |
|-------|------|----------------|---------|
| `generated_at` | string | ISO 8601 timestamp | `"2026-08-06T09:07:50Z"` |
| `time_range_start` | string | ISO 8601 timestamp | `"2026-07-07T09:07:50Z"` |
| `time_range_end` | string | ISO 8601 timestamp | `"2026-08-06T09:07:50Z"` |
| `cluster` | string | cluster name | `"ardenone-cluster"` |
| `service` | string | service name | `"whisper-stt"` |
| `namespace` | string | Kubernetes namespace | `"whisper-stt"` |
| `data_source` | string | source description | `"kubectl read-only proxy"` |
| `report_type` | string | report type description | `"30-day deployment analysis"` |

### 2. `current_status.deployments` (15+ fields per deployment)

| Field | Type | Format/Pattern | Example |
|-------|------|----------------|---------|
| `name` | string | deployment name | `"whisper-stt"` |
| `namespace` | string | Kubernetes namespace | `"whisper-stt"` |
| `creationTimestamp` | string | ISO 8601 timestamp | `"2026-05-01T17:26:49Z"` |
| `age_days` | integer | days (>= 0) | `96` |
| `generation` | integer | generation number | `353` |
| `revision` | integer | revision number | `32` |
| `replicas` | integer | count (>= 0) | `1` |
| `readyReplicas` | integer | count (>= 0) | `1` |
| `availableReplicas` | integer | count (>= 0) | `1` |
| `updatedReplicas` | integer | count (>= 0) | `1` |
| `strategy` | string | deployment strategy | `"Recreate"` or `"RollingUpdate"` |
| `images` | object | container images map | `{"whisper-stt": "ronaldraygun/whisper-stt:1.8.6"}` |
| `conditions` | array | deployment conditions | See below |
| `resources` | object | CPU/memory limits/requests | See below |

#### Nested Structures:

**Image Pattern:**
```regex
^[a-z0-9-]+/[a-z0-9-]+:[\w.+]+$
```
Examples: `ronaldraygun/whisper-stt:1.8.6`, `fedirz/faster-whisper-server:latest-cpu`

**Conditions Array (each entry):**
| Field | Type | Values |
|-------|------|--------|
| `type` | string | `"Progressing"`, `"Available"` |
| `status` | string | `"True"`, `"False"`, `"Unknown"` |
| `reason` | string | e.g., `"NewReplicaSetAvailable"` |
| `message` | string | Human-readable message |
| `lastTransitionTime` | string | ISO 8601 timestamp |

**Resources Object:**
```
requests: { cpu: string, memory: string }
limits: { cpu: string, memory: string }
```
CPU format: cores (`"1"`) or millicores (`"100m"`)  
Memory format: Kubernetes units (`"4Gi"`, `"512Mi"`)  
Pattern: `^[\d]+(Ei|Pi|Ti|Gi|Mi|Ki|E|P|T|G|M|K)?$`

### 3. `deployment_history_30_days.replicasets` (10 fields per entry)

| Field | Type | Format/Pattern | Example |
|-------|------|----------------|---------|
| `name` | string | ReplicaSet name | `"whisper-stt-847fd8d7b9"` |
| `created` | string | ISO 8601 timestamp | `"2026-07-12T16:53:42Z"` |
| `status` | string | Status values | `"active"` or `"inactive"` |
| `replicas` | integer | count (>= 0) | `1` |
| `readyReplicas` | integer | count (>= 0, optional) | `1` |
| `availableReplicas` | integer | count (>= 0, optional) | `1` |
| `revision` | integer | revision number | `32` |
| `deployment` | string | parent deployment name | `"whisper-stt"` |
| `image` | string | container image | `"ronaldraygun/whisper-stt:1.8.6"` |

**Status Values:** `"active"`, `"inactive"`, `"failed"`, `"scaled_down"`

### 4. `deployment_history_30_days.deployment_events_summary` (6 fields)

| Field | Type | Description |
|-------|------|-------------|
| `total_deployments` | integer | Total deployments in namespace |
| `total_replicasets_in_30d` | integer | ReplicaSets created in period |
| `failed_rollouts` | integer | Failed deployment count |
| `rollback_events` | integer | Rollback count |
| `successful_updates` | integer | Successful update count |
| `rapid_deployments_on_2026_07_08` | integer | Special tracking field |
| `last_deployment_update` | string | ISO 8601 timestamp |

### 5. `pod_status.current_pods` (8 fields per pod)

| Field | Type | Format/Pattern | Example |
|-------|------|----------------|---------|
| `name` | string | Pod name | `"whisper-stt-847fd8d7b9-v2rs5"` |
| `created` | string | ISO 8601 timestamp | `"2026-07-12T16:53:42Z"` |
| `age_days` | integer | days (>= 0) | `25` |
| `status` | string | Pod status enum | `"Running"` |
| `containers` | array | Container status list | See below |
| `totalRestartCount` | integer | restart count (>= 0) | `0` |
| `node` | string | Node name | `"k3s-agent-minisforum"` |

**Pod Status Enum:** `"Running"`, `"Pending"`, `"Failed"`, `"Succeeded"`, `"Unknown"`

**Container Array (each entry):**
| Field | Type | Example |
|-------|------|---------|
| `name` | string | `"whisper-stt"` |
| `image` | string | `"ronaldraygun/whisper-stt:1.8.6"` |
| `ready` | boolean | `true` |
| `restartCount` | integer | `0` |
| `started` | string (optional) | ISO 8601 timestamp |

### 6. `pod_status.pod_metrics` (7 fields)

| Field | Type | Description |
|-------|------|-------------|
| `total_pods` | integer | Total pod count |
| `running_pods` | integer | Running pod count |
| `total_containers` | integer | Total container count |
| `total_restarts` | integer | Total restarts across all pods |
| `crashloops` | integer | CrashLoopBackOff count |
| `oomkills` | integer | OOMKilled event count |
| `failed_pods` | integer | Failed pod count |
| `pending_pods` | integer | Pending pod count |

All counts are non-negative integers.

### 7. `operational_metrics.uptime` (2 fields)

Per-service uptime strings:
- Format: `"<N> days continuous"`
- Example: `"25 days continuous"`

### 8. `operational_metrics.restart_analysis` (5 fields)

| Field | Type | Description |
|-------|------|-------------|
| `total_restarts` | integer | Total restarts |
| `crash_loop_backoffs` | integer | CrashLoopBackOff events |
| `oom_killed` | integer | OOMKilled events |
| `evicted_pods` | integer | Evicted pod count |
| `error_state_pods` | integer | Pods in error state |

### 9. `operational_metrics.resource_limits` (8 fields per service)

Per-service CPU/memory specifications:
```
<service_name>: {
  cpu_requests: string,
  cpu_limits: string,
  memory_requests: string,
  memory_limits: string
}
```

All fields use Kubernetes resource format.

### 10. `operational_metrics.storage` (4 fields per PVC)

Per-PVC storage information:
| Field | Type | Values |
|-------|------|--------|
| `capacity` | string | Kubernetes storage units (`"10Gi"`) |
| `storage_class` | string | StorageClass name (`"longhorn"`) |
| `status` | string | `"Bound"`, `"Pending"`, `"Lost"`, `"Available"` |
| `age_days` | integer | days (>= 0) |

### 11. `log_analysis` (6 fields per service)

Per-service log analysis:
| Field | Type | Description |
|-------|------|-------------|
| `log_period` | string | Date range string |
| `total_log_lines` | integer | Line count analyzed |
| `errors_detected` | integer | Error count |
| `primary_activities` | array | Activity description strings |
| `status` | string | Operation status |
| `note` | string (optional) | Additional notes |

### 12. `argo_cd_integration` (4 fields)

| Field | Type | Description |
|-------|------|-------------|
| `tracking_id` | string | ArgoCD tracking identifier |
| `reloader` | string | Auto-reload flag (`"auto: true"`) |
| `sync_status` | string | Sync status |
| `deployments` | array | Deployment list with tracking IDs |

### 13. `error_incidents` (4 fields)

| Field | Type | Description |
|-------|------|-------------|
| `total_incidents` | integer | Total incidents (>= 0) |
| `critical_incidents` | integer | Critical count (>= 0) |
| `warning_incidents` | integer | Warning count (>= 0) |
| `incident_details` | array | Incident objects (currently empty) |

**Incident Detail Structure (if present):**
| Field | Type | Format |
|-------|------|--------|
| `timestamp` | string | ISO 8601 timestamp |
| `severity` | string | `"critical"`, `"warning"`, `"info"` |
| `error_type` | string | Error classification |
| `description` | string | Detailed description |
| `affected_components` | array | Component name strings |
| `resolution` | string | Resolution details |

### 14. `deployment_health_assessment` (9 fields)

| Field | Type | Values |
|-------|------|--------|
| `overall_health` | string | `"healthy"`, `"degraded"`, `"unhealthy"` |
| `deployment_stability` | string | `"high"`, `"medium"`, `"low"` |
| `uptime_percentage` | string | Percentage string (`"100%"`) |
| `zero_downtime_deployment` | boolean | `true`/`false` |
| `successful_deployment_rate` | string | Percentage string |
| `health_indicators` | object | Boolean flags for specific health checks |

**Health Indicators Object:**
```json
{
  "all_pods_running": boolean,
  "zero_crashloops": boolean,
  "zero_oomkills": boolean,
  "zero_timeouts": boolean,
  "zero_failed_rollouts": boolean,
  "minimal_errors": boolean
}
```

### 15. `summary` (14 fields)

| Field | Type | Description |
|-------|------|-------------|
| `deployment_name` | string | Deployment identifier |
| `namespace` | string | Kubernetes namespace |
| `cluster` | string | Cluster name |
| `analysis_period` | string | Date range string |
| `deployments_in_namespace` | integer | Deployment count |
| `total_deployment_events` | integer | Event count |
| `successful_rollouts` | integer | Success count |
| `failed_rollouts` | integer | Failure count |
| `rollback_events` | integer | Rollback count |
| `crashloops` | integer | CrashLoopBackOff count |
| `oomkills` | integer | OOMKilled count |
| `pod_restarts` | integer | Restart count |
| `error_rate` | string | Error rate description |
| `availability` | string | Percentage string |
| `overall_status` | string | Status summary |

---

## Data Type Patterns

### Timestamp Fields (ISO 8601)

All timestamps follow ISO 8601 format with UTC timezone:
- Format: `YYYY-MM-DDTHH:MM:SSZ`
- Example: `"2026-08-06T09:07:50Z"`
- Validation: Must parse with `datetime.fromisoformat()` after handling 'Z' suffix

### Integer Count Fields

All integer count fields are non-negative:
- Minimum: `0`
- Maximum: Unbounded (typically < 1000 for pod counts)
- Examples: replicas, restart counts, deployment counts

### Percentage Fields

Percentage strings use format:
- Pattern: `^\d+%$`
- Examples: `"100%"`, `"95%"`, `"0%"`
- Range: 0-100

### Version Strings

Image version tags follow semantic versioning:
- Pattern: `^[\d.]+$` or `latest-cpu`
- Examples: `"1.8.6"`, `"1.8.4"`, `"latest-cpu"`

---

## Status Enumerations

### Pod Status
| Value | Description |
|-------|-------------|
| `Running` | Pod is running normally |
| `Pending` | Pod is pending scheduling |
| `Failed` | Pod terminated in failure |
| `Succeeded` | Pod completed successfully |
| `Unknown` | Status unknown |

### Deployment Condition Types
| Value | Description |
|-------|-------------|
| `Progressing` | Deployment is progressing |
| `Available` | Deployment is available |

### ReplicaSet Status
| Value | Description |
|-------|-------------|
| `active` | Currently serving traffic |
| `inactive` | Not serving, scaled down |
| `failed` | Failed to deploy |
| `scaled_down_or_failed` | Scaled down or failed |

### PVC Status
| Value | Description |
|-------|-------------|
| `Bound` | PVC is bound to a PV |
| `Pending` | PVC is pending binding |
| `Lost` | PVC was lost |
| `Available` | PVC is available |

### Health Status
| Value | Description |
|-------|-------------|
| `Healthy` | System is healthy |
| `Degraded` | System is degraded |
| `Progressing` | System is progressing |
| `Missing` | Resource is missing |
| `Unknown` | Status unknown |

---

## Validation Requirements

### Existing Validation (from JSON Schema)

The existing `whisper-stt-deployment-schema.json` enforces:

1. **30-Day Completeness:**
   - `metadata.data_period_start` to `data_period_end` must be 30 days
   - `summary.data_coverage` must be percentage string
   - `summary.gaps_detected` boolean flag
   - `summary.largest_gap_days` integer (0-30)

2. **Type Safety:**
   - Timestamps: ISO 8601 format validation
   - Enums: Status values restricted to allowed sets
   - Counts: Non-negative integers with minimums
   - Images: Pattern validation for `registry/name:tag`

3. **Coverage Validation:**
   - `summary.data_coverage`: Pattern `^(100|[1-9]?[0-9])%$`
   - `summary.gaps_detected`: Boolean flag
   - `summary.largest_gap_days`: Integer 0-30

### Existing Validation (from Python Schema)

The `whisper_stt_deployment_schema.py` provides:

1. **Type Definitions:** Dataclasses for all entities
2. **Runtime Validation:** Post-init validation for:
   - Timestamp parsing
   - Timestamp ordering (start < end < generated)
   - Numeric ranges (>= 0)
   - Enum value constraints
3. **Schema Conversion:** `from_dict()` method for nested dataclass instantiation
4. **Validation Functions:** Standalone validation with error reporting

---

## Data Patterns Observed

### Date Ranges

- **Analysis Period:** Exactly 30 days
  - Start: 2026-07-07 (30 days before generation)
  - End: 2026-08-06 (generation date)
- **Deployment History:** Tracks all ReplicaSets within 30-day window
- **Age Calculations:** `age_days` fields show pod/replica age

### Deployment Patterns

- **Multiple Deployments:** 4 deployments in 30-day period for whisper-stt
- **Rapid Rollout:** 3 deployments on 2026-07-08 (1.8.2 → 1.8.4 → 1.8.6)
- **Stable Operation:** No restarts, no failures in current deployment
- **Zero Downtime:** All deployments successful

### Resource Allocation

- **CPU Requests:** 1 core per service
- **CPU Limits:** 8 cores per service
- **Memory Requests:** 4Gi per service
- **Memory Limits:** 8Gi per service
- **Pattern:** 1:8 CPU ratio, 1:2 memory ratio

### Storage Usage

- **Model Cache:** 10Gi per service, longhorn storage class
- **Jobs Storage:** 1Gi for job artifacts
- **Age:** 53-84 days (long-lived PVCs)

### Health Patterns

- **All Pods Running:** 2/2 pods running
- **Zero Restarts:** 0 total restarts across all pods
- **Zero Incidents:** 0 critical, 0 warning incidents
- **100% Availability:** Zero downtime deployment

---

## Schema Design Implications

### Required Schema Features

1. **30-Day Window Validation:**
   - Must enforce 30-day analysis period
   - Must detect and report data gaps
   - Must calculate coverage percentage

2. **Nested Object Validation:**
   - Three-level nesting (e.g., `conditions` within deployments)
   - Optional fields with proper null handling
   - Array validation with item schemas

3. **Enum Constraints:**
   - Status fields: Pods, deployments, PVCs, health
   - Strategy fields: Recreate, RollingUpdate
   - Severity fields: Critical, warning, info

4. **Pattern Validation:**
   - Timestamps: ISO 8601 with timezone
   - Images: `registry/name:tag` format
   - Resources: Kubernetes units (m, Mi, Gi, etc.)
   - Percentages: `\d+%` format

5. **Numeric Range Validation:**
   - Counts: Minimum 0, no maximum (practical limits)
   - Days ago: 0-30 range
   - Age days: Minimum 0

### Optional vs Required Fields

**Required Top-Level:**
- `metadata`
- `argo_workflows`
- `argo_cd`
- `cluster_deployments`
- `summary`
- `pod_health`

**Optional Top-Level:**
- `resources`
- `storage`
- `error_incidents`
- `notes`

### Cross-Field Validation

The schema enforces consistency:
- `successful_deployments + failed_deployments <= total_deployments`
- `running_pods <= total_pods`
- `data_period_start < data_period_end <= generated_at`

---

## Comparison: Data vs. Schema

### Schema Coverage

The actual data file (`whisper-stt-deployment-data-30days.json`) differs from the official schema (`whisper-stt-deployment-schema.json`):

**Schema Structure:**
- Uses `metadata` (not `report_metadata`)
- Uses `argo_workflows`, `argo_cd`, `cluster_deployments`, `summary` as required
- Uses `pod_health` (not `pod_status`)

**Data Structure:**
- Uses `report_metadata` (not `metadata`)
- Uses `current_status`, `deployment_history_30_days`, `pod_status` (not matching schema)
- Includes additional sections: `operational_metrics`, `log_analysis`, `argo_cd_integration`, `deployment_health_assessment`, `recommendations`

### Gap Analysis

**Fields in Data but Not in Schema:**
- `current_status.deployments[].generation`
- `current_status.deployments[].strategy`
- `deployment_history_30_days.deployment_events_summary.rapid_deployments_on_2026_07_08`
- `operational_metrics` (entire section)
- `log_analysis` (entire section)
- `deployment_health_assessment` (entire section)
- `comparison_with_previous_analysis` (entire section)
- `recommendations` (entire section)

**Fields in Schema but Not in Data:**
- Standardized `metadata` section (data uses `report_metadata`)
- Full `argo_workflows` structure (data has minimal workflow data)
- Full `argo_cd` structure (data has simplified tracking)

---

## Recommendations for Schema Design

1. **Align Terminology:**
   - Standardize on `report_metadata` vs `metadata`
   - Standardize on `pod_status` vs `pod_health`
   - Ensure field names match actual data

2. **Complete Coverage:**
   - Add missing sections to schema: `operational_metrics`, `log_analysis`, `deployment_health_assessment`
   - Add missing fields: `generation`, `strategy`, `rapid_deployments_on_2026_07_08`

3. **Validation Enhancement:**
   - Add cross-field validation (e.g., `running_pods <= total_pods`)
   - Add timestamp ordering validation
   - Add consistency checks for deployment counts

4. **Documentation:**
   - Document field semantics (not just types)
   - Document data collection frequency
   - Document data source reliability

---

## Conclusion

The whisper-stt deployment data structure is comprehensive and well-designed for operational analysis. The existing validation schema provides strong type safety and 30-day completeness requirements but does not fully align with the actual data file structure. 

**Key Findings:**
- **Total Fields:** ~85+ fields across 12 top-level sections
- **Field Types:** Timestamps (ISO 8601), integers (counts), strings (names, statuses), booleans (flags)
- **Patterns:** 30-day window, zero-downtime deployment, consistent resource allocation
- **Validation:** Strong type safety already implemented, but schema/data misalignment exists

**Schema Design Guidance:**
1. Align schema structure with actual data file
2. Add missing sections and fields
3. Implement cross-field validation
4. Document field semantics and constraints

This analysis provides a complete inventory of deployment data fields that will inform the comprehensive schema design for the persistence layer.
