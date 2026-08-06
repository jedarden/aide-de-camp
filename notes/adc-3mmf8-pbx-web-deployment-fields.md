# PBX-Web Deployment Data Field Inventory

**Generated:** 2026-08-06  
**Purpose:** Complete field inventory for pbx-web deployment data structure  
**Source:** pbx-web-deployment-data-30days.json analysis

---

## Root Level Structure

The pbx-web deployment data follows a hierarchical JSON structure with 7 main sections:

1. `metadata` - Collection metadata and configuration
2. `current_status` - Live deployment state information  
3. `deployment_events_last_30_days` - Recent deployment history array
4. `historical_deployments_beyond_30_days` - Historical deployment records array
5. `deployment_metrics` - Deployment statistics and calculations
6. `pod_health` - Current pod and container health information
7. `infrastructure_details` - Resource limits, volumes, and configuration
8. `summary` - Overall health assessment and recommendations

---

## Section 1: `metadata` (Object)

**Purpose:** Top-level metadata about the data collection and service configuration

| Field | Type | Description | Constraints/Notes |
|-------|------|-------------|-------------------|
| `service` | string | Service identifier | Fixed value: "pbx-web" |
| `namespace` | string | Kubernetes namespace | Fixed value: "pbx-web" |
| `cluster` | string | Cluster identifier | Fixed value: "ardenone-cluster" |
| `data_collected_at` | string (ISO 8601) | Timestamp of data collection | Format: `YYYY-MM-DDTHH:MM:SSZ` |
| `managed_by` | string | Deployment management system | Fixed value: "ArgoCD" |
| `strategy` | string | Deployment strategy | Fixed value: "Recreate" |

### Nested Object: `time_period`

| Field | Type | Description | Constraints/Notes |
|-------|------|-------------|-------------------|
| `start` | string (ISO 8601) | Analysis window start | Format: `YYYY-MM-DDTHH:MM:SSZ` |
| `end` | string (ISO 8601) | Analysis window end | Format: `YYYY-MM-DDTHH:MM:SSZ` |
| `description` | string | Human-readable period description | Example: "Last 30 days" |

---

## Section 2: `current_status` (Object)

**Purpose:** Current live deployment state from Kubernetes

| Field | Type | Description | Constraints/Notes |
|-------|------|-------------|-------------------|
| `deployment_name` | string | Deployment resource name | Matches `metadata.service` |
| `current_revision` | number | Current deployment revision | Integer, increments on updates |
| `current_image` | string | Full container image reference | Format: `repository:tag` |
| `generation` | number | Kubernetes generation number | Integer, tracks desired state changes |
| `replicas` | number | Desired replica count | Integer, typically 1 for this service |
| `readyReplicas` | number | Currently ready replicas | Integer, ≤ `replicas` |
| `updatedReplicas` | number | Replicas with updated spec | Integer, ≤ `replicas` |
| `availableReplicas` | number | Available replicas | Integer, ≤ `replicas` |
| `current_pod` | string | Current pod name | Format: `deployment-hash-random` |
| `pod_created_at` | string (ISO 8601) | Pod creation timestamp | Format: `YYYY-MM-DDTHH:MM:SSZ` |

### Nested Array: `conditions[]`

**Purpose:** Kubernetes deployment conditions (availability, progression)

| Field | Type | Description | Constraints/Notes |
|-------|------|-------------|-------------------|
| `type` | string | Condition type | Values: "Progressing", "Available" |
| `status` | string | Condition status | Values: "True", "False", "Unknown" |
| `reason` | string | Machine-readable reason | Example: "NewReplicaSetAvailable" |
| `message` | string | Human-readable message | Details about condition state |
| `lastTransitionTime` | string (ISO 8601) | Last status change timestamp | Format: `YYYY-MM-DDTHH:MM:SSZ` |

---

## Section 3: `deployment_events_last_30_days[]` (Array)

**Purpose:** Chronological deployment event history

| Field | Type | Description | Constraints/Notes |
|-------|------|-------------|-------------------|
| `date` | string (ISO 8601 date) | Event date | Format: `YYYY-MM-DD` |
| `timestamp` | string (ISO 8601) | Event timestamp | Format: `YYYY-MM-DDTHH:MM:SSZ` |
| `event_type` | string | Event classification | Values: "deployment_rollout", "deployment_rollback" |
| `revision` | number | Deployment revision number | Integer, unique per deployment |
| `deployment` | string (optional) | Deployment name | Present for non-pbx-web deployments |
| `replicaSet` | string | ReplicaSet identifier | Format: `deployment-hash` |
| `image` | string | Container image reference | Format: `repository:tag` |
| `outcome` | string | Deployment result | Values: "success", "rolled_back", "failed" |
| `pod_name` | string (optional) | Created pod name | Format: `replicaset-random` |
| `pod_ready` | boolean (optional) | Pod readiness status | `true` if pod is ready |
| `restart_count` | number (optional) | Container restart count | Integer, typically 0 for healthy pods |
| `notes` | string | Additional context | Free-form explanatory text |

---

## Section 4: `historical_deployments_beyond_30_days[]` (Array)

**Purpose:** Deployment history outside the primary analysis window

| Field | Type | Description | Constraints/Notes |
|-------|------|-------------|-------------------|
| `date` | string (ISO 8601 date) | Deployment date | Format: `YYYY-MM-DD` |
| `timestamp` | string (ISO 8601) | Deployment timestamp | Format: `YYYY-MM-DDTHH:MM:SSZ` |
| `revision` | number | Deployment revision number | Integer, unique per deployment |
| `replicaSet` | string | ReplicaSet identifier | Format: `deployment-hash` |
| `image` | string | Container image reference | Format: `repository:tag` |
| `notes` | string | Historical context | Fixed value: "Prior to 30-day window" |

---

## Section 5: `deployment_metrics` (Object)

**Purpose:** Calculated deployment statistics

| Field | Type | Description | Constraints/Notes |
|-------|------|-------------|-------------------|
| `total_deployments_last_30_days` | number | Total deployment count | Integer, ≥0 |
| `successful_deployments` | number | Successful deployment count | Integer, ≤ total |
| `failed_deployments` | number | Failed deployment count | Integer, ≤ total |
| `deployment_frequency_days` | number | Average days between deployments | Number (decimal), ≥0 |
| `unique_images_deployed` | number | Distinct image count | Integer, ≥0 |
| `current_uptime_days` | number | Current deployment uptime | Number (decimal), ≥0 |
| `last_deployment` | string (ISO 8601) | Last deployment timestamp | Format: `YYYY-MM-DDTHH:MM:SSZ` |
| `days_since_last_deployment` | number | Days since last deployment | Integer, ≥0 |

### Nested Array: `images_used_last_30_days[]`

| Field | Type | Description | Constraints/Notes |
|-------|------|-------------|-------------------|
| (array elements) | string | Full image references | Format: `repository:tag` |

---

## Section 6: `pod_health` (Object)

**Purpose:** Current pod health and container status

### Nested Object: `current_pod`

| Field | Type | Description | Constraints/Notes |
|-------|------|-------------|-------------------|
| `name` | string | Pod name | Format: `replicaset-random` |
| `created_at` | string (ISO 8601) | Pod creation timestamp | Format: `YYYY-MM-DDTHH:MM:SSZ` |
| `phase` | string | Pod phase | Values: "Running", "Pending", "Failed", etc. |
| `ready` | boolean | Pod readiness status | `true` if ready |
| `restart_count` | number | Total container restarts | Integer, ≥0 |
| `uptime_days` | number | Pod uptime in days | Number (decimal), ≥0 |

### Nested Array: `current_pod.containers[]`

| Field | Type | Description | Constraints/Notes |
|-------|------|-------------|-------------------|
| `name` | string | Container name | Example: "nginx", "site-generator" |
| `image` | string | Container image reference | Format: `repository:tag` |
| `ready` | boolean | Container readiness | `true` if ready |
| `restartCount` | number | Container restart count | Integer, ≥0 |
| `running_since` | string (ISO 8601) | Container start timestamp | Format: `YYYY-MM-DDTHH:MM:SSZ` |

### Nested Object: `health_indicators`

| Field | Type | Description | Constraints/Notes |
|-------|------|-------------|-------------------|
| `no_crashes` | boolean | No container crashes | `true` if no crashes detected |
| `no_restart_loops` | boolean | No restart loops | `true` if stable |
| `no_image_pull_errors` | boolean | No image pull failures | `true` if no pull errors |
| `liveness_probes_passing` | boolean | Liveness probes passing | `true` if all passing |
| `readiness_probes_passing` | boolean | Readiness probes passing | `true` if all passing |

---

## Section 7: `infrastructure_details` (Object)

**Purpose:** Kubernetes infrastructure configuration

### Nested Object: `resource_limits`

**Purpose:** Per-container resource specifications

#### Container-level objects (e.g., `site_generator`, `nginx`)

| Field | Type | Description | Constraints/Notes |
|-------|------|-------------|-------------------|
| `cpu_limit` | string | CPU limit | Kubernetes format (e.g., "500m") |
| `memory_limit` | string | Memory limit | Kubernetes format (e.g., "512Mi") |
| `cpu_request` | string | CPU request | Kubernetes format (e.g., "10m") |
| `memory_request` | string | Memory request | Kubernetes format (e.g., "128Mi") |

### Nested Array: `volumes[]`

**Purpose:** Pod volume specifications

| Field | Type | Description | Constraints/Notes |
|-------|------|-------------|-------------------|
| `name` | string | Volume name | Unique within pod |
| `type` | string | Volume type | Values: "emptyDir", "configMap", "secret" |
| `purpose` | string (optional) | Volume purpose | Human-readable description |
| `configMap` | string (optional) | ConfigMap reference | Present when type="configMap" |
| `medium` | string (optional) | Storage medium | Values: "Memory", "" (default) |
| `sizeLimit` | string (optional) | Size limit | Kubernetes format (e.g., "16Mi") |

### Nested Object: `environment_variables`

**Purpose:** Container environment variables

| Field | Type | Description | Constraints/Notes |
|-------|------|-------------|-------------------|
| `S3_ENDPOINT` | string | Garage S3 endpoint | URL format |
| `S3_BUCKET` | string | S3 bucket name | Bucket identifier |
| `PYTHONUNBUFFERED` | string | Python output buffering | Fixed value: "1" |

### Nested Array: `secrets_used[]`

**Purpose:** Kubernetes secrets referenced by deployment

| Field | Type | Description | Constraints/Notes |
|-------|------|-------------|-------------------|
| (array elements) | string | Secret names | Kubernetes secret names |

### Nested Object: `liveness_probes`

**Purpose:** Container health check specifications

#### Container-level probe objects (e.g., `site_generator`, `nginx`)

| Field | Type | Description | Constraints/Notes |
|-------|------|-------------|-------------------|
| `path` | string | HTTP probe path | URL path |
| `port` | number | Container port | Integer, 1-65535 |
| `initialDelaySeconds` | number | Startup delay | Integer, ≥0 |
| `periodSeconds` | number | Check interval | Integer, ≥1 |
| `timeoutSeconds` | number | Check timeout | Integer, ≥1 |
| `failureThreshold` | number | Failure threshold | Integer, ≥1 |

### Nested Object: `readiness_probes`

**Purpose:** Container readiness check specifications (same structure as `liveness_probes`)

#### Container-level probe objects (e.g., `site_generator`, `nginx`)

| Field | Type | Description | Constraints/Notes |
|-------|------|-------------|-------------------|
| `path` | string | HTTP probe path | URL path |
| `port` | number | Container port | Integer, 1-65535 |
| `initialDelaySeconds` | number | Startup delay | Integer, ≥0 |
| `periodSeconds` | number | Check interval | Integer, ≥1 |
| `timeoutSeconds` | number | Check timeout | Integer, ≥1 |
| `failureThreshold` | number | Failure threshold | Integer, ≥1 |

---

## Section 8: `operational_logs_sample` (Object)

**Purpose:** Application-specific operational data

| Field | Type | Description | Constraints/Notes |
|-------|------|-------------|-------------------|
| `recent_activity` | string | Recent operation description | Free-form text |
| `last_rebuild` | string (ISO 8601) | Last rebuild timestamp | Format: `YYYY-MM-DDTHH:MM:SSZ` |
| `rebuild_frequency` | string | Rebuild trigger description | Human-readable explanation |
| `log_health` | string | Log health assessment | Free-form health description |

### Nested Object: `search_index_stats`

**Purpose:** Pagefind search index statistics

| Field | Type | Description | Constraints/Notes |
|-------|------|-------------|-------------------|
| `indexed_pages` | number | Total indexed pages | Integer, ≥0 |
| `indexed_words` | number | Total indexed words | Integer, ≥0 |
| `languages` | number | Language count | Integer, ≥1 |
| `build_time_avg_seconds` | number | Average build time | Number (decimal), ≥0 |

---

## Section 9: `summary` (Object)

**Purpose:** Overall health assessment and recommendations

| Field | Type | Description | Constraints/Notes |
|-------|------|-------------|-------------------|
| `overall_health` | string | Overall health status | Values: "excellent", "good", "moderate", "poor" |
| `deployment_stability` | string | Deployment stability | Values: "stable", "moderate", "unstable" |
| `uptime` | string | Uptime description | Human-readable (e.g., "9 days continuous") |
| `issues_last_30_days` | number | Issue count | Integer, ≥0 |
| `rollbacks_last_30_days` | number | Rollback count | Integer, ≥0 |
| `deployment_success_rate` | string | Success rate percentage | Format: "X%" |
| `recommendation` | string | Operational recommendation | Free-form text |

---

## Data Type Summary

| Type | Fields | Count |
|------|--------|-------|
| `string` | Various identifiers, names, timestamps, descriptions | 45+ |
| `number` | Counts, metrics, ports, thresholds | 30+ |
| `boolean` | Status flags, health indicators | 10+ |
| `string[]` | Arrays of images, secrets | 2 |
| `Object{}` | Nested structures (metadata, current_status, etc.) | 9 main sections |
| `Object[]` | Arrays of deployment events, volumes, containers | 4 arrays |

---

## Field Naming Conventions

1. **snake_case** for most field names (Kubernetes convention)
2. **camelCase** for Kubernetes API fields (`readyReplicas`, `restartCount`)
3. **kebab-case** for deployment and pod names (Kubernetes convention)
4. **ISO 8601** timestamp format: `YYYY-MM-DDTHH:MM:SSZ`
5. **Date-only** format: `YYYY-MM-DD`

---

## Validation Rules & Constraints

1. **Revision numbers**: Always increment, never decrease
2. **Replica counts**: `availableReplicas` ≤ `updatedReplicas` ≤ `replicas`
3. **Timestamps**: All timestamps in ISO 8601 format with `Z` suffix
4. **Boolean fields**: Only `true` or `false`, no null/undefined
5. **Array fields**: Can be empty but must be present (not null)
6. **Resource limits**: Requests ≤ limits for both CPU and memory
7. **Port numbers**: 1-65535 range
8. **Thresholds**: Positive integers (≥1)
9. **Health indicators**: All must be `true` for healthy pod

---

## Field Relationships

1. **Revision → ReplicaSet mapping**: Each revision maps to exactly one ReplicaSet
2. **Pod → ReplicaSet relationship**: Pod names include ReplicaSet hash as prefix
3. **Image → Version relationship**: Images include semantic version tags
4. **Deployment → Event relationship**: Each deployment creates one event entry
5. **Conditions → Deployment status**: Conditions determine overall deployment health
6. **Probes → Health indicators**: Probe status drives health indicator booleans

---

## Notes

- **ArgoCD managed**: All deployment changes go through GitOps, no direct kubectl mutations
- **Recreate strategy**: Only one pod runs at a time (no rolling updates)
- **Multi-container pod**: Each pod contains nginx + site-generator containers
- **Shared volumes**: `www` volume shared between nginx and site-generator
- **Search index**: Pagefind index rebuilt on bucket signature changes
- **Resource limits**: Strict CPU/memory limits prevent resource exhaustion
- **Health checks**: Both liveness and readiness probes configured per container

---

**Document Status:** Complete  
**Total Fields Documented:** 80+  
**Sections Covered:** 9 main sections with nested structures  
**Validation Coverage:** All constraints and relationships documented