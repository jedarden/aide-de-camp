# Field Mapping: Whisper-STT → PBX-Web Schema

**Generated:** 2026-08-06  
**Purpose:** Map whisper-stt deployment data fields to pbx-web schema structure  
**Source Bead:** adc-6bj26  
**Prerequisite:** adc-3mmf8 (field extraction)

---

## Executive Summary

Whisper-stt deployment data uses a **simplified schema** designed for cross-service comparability, mapping to a **subset of pbx-web fields**. The whisper-stt schema intentionally focuses on core deployment metrics and excludes operational, infrastructure, and application-specific details present in pbx-web.

**Key Findings:**
- **Direct mappings:** 18 field pairs with exact alignment
- **Partial mappings:** 5 fields with structural differences
- **Gaps (pbx-web fields missing from whisper-stt):** 60+ fields across 6 categories
- **Mismatches:** 8 fields with different naming or structure
- **Coverage:** whisper-stt covers ~28% of pbx-web schema

---

## Mapping Table

### ✅ Direct Mappings (Perfect Alignment)

| Whisper-STT Field | PBX-Web Field | Type Match | Location in PBX-Web |
|------------------|---------------|------------|---------------------|
| `service` | `metadata.service` | ✅ string | metadata |
| `cluster` | `metadata.cluster` | ✅ string | metadata |
| `namespace` | `metadata.namespace` | ✅ string | metadata |
| `timestamp` | `deployment_events_last_30_days[].timestamp` | ✅ ISO 8601 | deployment_events |
| `date` | `deployment_events_last_30_days[].date` | ✅ date | deployment_events |
| `revision` | `deployment_events_last_30_days[].revision` | ✅ number/string | deployment_events |
| `deployment_name` | `deployment_events_last_30_days[].deployment` | ✅ string | deployment_events |
| `replicaSet` | `deployment_events_last_30_days[].replicaSet` | ✅ string | deployment_events |
| `image` | `deployment_events_last_30_days[].image` | ✅ string | deployment_events |
| `status` | `deployment_events_last_30_days[].outcome` | ✅ enum | deployment_events |
| `overall_health` | `summary.overall_health` | ✅ enum | summary |
| `deployment_stability` | `summary.deployment_stability` | ✅ enum | summary |
| `uptime_percentage` | `summary.uptime` | ✅ percentage | summary |
| `successful_deployment_rate` | `summary.deployment_success_rate` | ✅ percentage | summary |
| `total_deployments` | `deployment_metrics.total_deployments_last_30_days` | ✅ number | deployment_metrics |
| `successful_updates` | `deployment_metrics.successful_deployments` | ✅ number | deployment_metrics |
| `failed_rollouts` | `deployment_metrics.failed_deployments` | ✅ number | deployment_metrics |
| `last_deployment_update` | `deployment_metrics.last_deployment` | ✅ ISO 8601 | deployment_metrics |

**Notes:**
- All direct mappings use identical field names or equivalent semantics
- Type formats match (ISO 8601 timestamps, enums, percentages)
- Whisper-stt flattens nested pbx-web structure into top-level fields

---

### 🔄 Partial Mappings (Structural Differences)

| Whisper-STT Field | PBX-Web Field(s) | Mapping Type | Notes |
|------------------|------------------|--------------|-------|
| `metadata.generated_at` | `metadata.data_collected_at` | ✅ Equivalent | Different naming, same purpose |
| `metadata.source_files[]` | *(not present in pbx-web)* | ➡️ Extension | Whisper-stt tracks data lineage |
| `metadata.total_records` | *(derived from array lengths)* | ➕ Derived | pbx-web doesn't pre-compute |
| `total_replicasets` | *(derived from deployment_events)* | ➕ Derived | pbx-web stores in events array |
| `replicas` | `current_status.replicas` + `pod_health.current_pod` | 🔀 Split | pbx-web separates current vs historical |
| `ready_replicas` | `current_status.readyReplicas` | ✅ Equivalent | camelCase vs snake_case |
| `available_replicas` | `current_status.availableReplicas` | ✅ Equivalent | camelCase vs snake_case |
| `total_pods` | *(derived from multiple sources)* | ➕ Derived | Not directly in pbx-web |
| `running_pods` | *(derived from pod_health)* | ➕ Derived | Computed from pod status |
| `total_restarts` | `pod_health.current_pod.restart_count` | ✅ Equivalent | Aggregated vs per-pod |
| `crashloops` | *(derived from health_indicators.no_restart_loops)* | 🔀 Inverted | Boolean → count |
| `oomkills` | *(not present in pbx-web)* | ❌ No equivalent | OOM tracking not in pbx-web schema |
| `total_incidents` | `summary.issues_last_30_days` | ✅ Equivalent | Different naming |
| `critical_incidents` | *(subset of total_incidents)* | ➕ Derived | pbx-web doesn't categorize severity |
| `warning_incidents` | *(subset of total_incidents)* | ➕ Derived | pbx-web doesn't categorize severity |
| `log_errors` | *(not present in pbx-web)* | ❌ No equivalent | Log analysis not in pbx-web |
| `rollback_events` | `summary.rollbacks_last_30_days` | ✅ Equivalent | Different naming |

---

### ❌ Gaps: PBX-Web Fields Missing from Whisper-STT

#### Category 1: Current Live Status (7 fields)

| PBX-Web Field | Type | Whisper-STT Coverage |
|---------------|------|---------------------|
| `current_status.deployment_name` | string | ✅ `deployment_name` |
| `current_status.current_revision` | number | ✅ `revision` (in summary) |
| `current_status.current_image` | string | ✅ `image` (in records) |
| `current_status.generation` | number | ❌ **Missing** - Kubernetes generation tracking |
| `current_status.updatedReplicas` | number | ❌ **Missing** - Separate from ready/available |
| `current_status.current_pod` | string | ❌ **Missing** - Current pod name |
| `current_status.pod_created_at` | string | ❌ **Missing** - Current pod creation time |
| `current_status.conditions[]` | array | ❌ **Missing** - Kubernetes conditions (progression/availability) |

#### Category 2: Historical Deployments (3 fields)

| PBX-Web Field | Type | Whisper-STT Coverage |
|---------------|------|---------------------|
| `historical_deployments_beyond_30_days[]` | array | ❌ **Missing** - No historical data beyond 30-day window |
| `deployment_metrics.deployment_frequency_days` | number | ❌ **Missing** - Deployment cadence metric |
| `deployment_metrics.unique_images_deployed` | number | ❌ **Missing** - Image diversity tracking |
| `deployment_metrics.current_uptime_days` | number | ❌ **Missing** - Current deployment uptime |
| `deployment_metrics.days_since_last_deployment` | number | ❌ **Missing** - Recency metric |
| `deployment_metrics.images_used_last_30_days[]` | array | ❌ **Missing** - Image enumeration |

#### Category 3: Pod Health & Containers (15 fields)

| PBX-Web Field | Type | Whisper-STT Coverage |
|---------------|------|---------------------|
| `pod_health.current_pod.name` | string | ❌ **Missing** - Current pod name |
| `pod_health.current_pod.created_at` | string | ❌ **Missing** - Pod creation timestamp |
| `pod_health.current_pod.phase` | string | ❌ **Missing** - Pod phase (Running/Pending/Failed) |
| `pod_health.current_pod.ready` | boolean | ❌ **Missing** - Pod readiness boolean |
| `pod_health.current_pod.uptime_days` | number | ❌ **Missing** - Pod uptime metric |
| `pod_health.current_pod.containers[]` | array | ❌ **Missing** - Multi-container tracking |
| `pod_health.current_pod.containers[].name` | string | ❌ **Missing** - Container names |
| `pod_health.current_pod.containers[].image` | string | ❌ **Missing** - Per-container images |
| `pod_health.current_pod.containers[].ready` | boolean | ❌ **Missing** - Per-container readiness |
| `pod_health.current_pod.containers[].restartCount` | number | ❌ **Missing** - Per-container restarts |
| `pod_health.current_pod.containers[].running_since` | string | ❌ **Missing** - Container start time |
| `pod_health.health_indicators.no_crashes` | boolean | ❌ **Missing** - Crash detection |
| `pod_health.health_indicators.no_restart_loops` | boolean | ❌ **Missing** - Loop detection |
| `pod_health.health_indicators.no_image_pull_errors` | boolean | ❌ **Missing** - Image pull tracking |
| `pod_health.health_indicators.liveness_probes_passing` | boolean | ❌ **Missing** - Liveness probe status |
| `pod_health.health_indicators.readiness_probes_passing` | boolean | ❌ **Missing** - Readiness probe status |

#### Category 4: Infrastructure Details (20+ fields)

| PBX-Web Field | Type | Whisper-STT Coverage |
|---------------|------|---------------------|
| `infrastructure_details.resource_limits` | object | ❌ **Missing** - Entire resource tracking section |
| `infrastructure_details.resource_limits.*.cpu_limit` | string | ❌ **Missing** - CPU limit specification |
| `infrastructure_details.resource_limits.*.memory_limit` | string | ❌ **Missing** - Memory limit specification |
| `infrastructure_details.resource_limits.*.cpu_request` | string | ❌ **Missing** - CPU request specification |
| `infrastructure_details.resource_limits.*.memory_request` | string | ❌ **Missing** - Memory request specification |
| `infrastructure_details.volumes[]` | array | ❌ **Missing** - Volume specifications |
| `infrastructure_details.volumes[].name` | string | ❌ **Missing** - Volume names |
| `infrastructure_details.volumes[].type` | string | ❌ **Missing** - Volume types |
| `infrastructure_details.volumes[].purpose` | string | ❌ **Missing** - Volume purposes |
| `infrastructure_details.volumes[].configMap` | string | ❌ **Missing** - ConfigMap references |
| `infrastructure_details.volumes[].medium` | string | ❌ **Missing** - Storage medium |
| `infrastructure_details.volumes[].sizeLimit` | string | ❌ **Missing** - Size limits |
| `infrastructure_details.environment_variables` | object | ❌ **Missing** - Environment config |
| `infrastructure_details.secrets_used[]` | array | ❌ **Missing** - Secret references |
| `infrastructure_details.liveness_probes` | object | ❌ **Missing** - Liveness probe configs |
| `infrastructure_details.readiness_probes` | object | ❌ **Missing** - Readiness probe configs |
| `infrastructure_details.liveness_probes.*.path` | string | ❌ **Missing** - Probe paths |
| `infrastructure_details.liveness_probes.*.port` | number | ❌ **Missing** - Probe ports |
| `infrastructure_details.liveness_probes.*.initialDelaySeconds` | number | ❌ **Missing** - Probe delays |
| `infrastructure_details.liveness_probes.*.periodSeconds` | number | ❌ **Missing** - Probe intervals |
| `infrastructure_details.liveness_probes.*.timeoutSeconds` | number | ❌ **Missing** - Probe timeouts |
| `infrastructure_details.liveness_probes.*.failureThreshold` | number | ❌ **Missing** - Probe thresholds |

#### Category 5: Operational Logs (6 fields)

| PBX-Web Field | Type | Whisper-STT Coverage |
|---------------|------|---------------------|
| `operational_logs_sample.recent_activity` | string | ❌ **Missing** - Activity description |
| `operational_logs_sample.last_rebuild` | string | ❌ **Missing** - Rebuild tracking |
| `operational_logs_sample.rebuild_frequency` | string | ❌ **Missing** - Rebuild patterns |
| `operational_logs_sample.log_health` | string | ❌ **Missing** - Log assessment |
| `operational_logs_sample.search_index_stats.indexed_pages` | number | ❌ **Missing** - Index metrics |
| `operational_logs_sample.search_index_stats.indexed_words` | number | ❌ **Missing** - Index metrics |
| `operational_logs_sample.search_index_stats.languages` | number | ❌ **Missing** - Index metrics |
| `operational_logs_sample.search_index_stats.build_time_avg_seconds` | number | ❌ **Missing** - Index metrics |

#### Category 6: Metadata & Strategy (3 fields)

| PBX-Web Field | Type | Whisper-STT Coverage |
|---------------|------|---------------------|
| `metadata.managed_by` | string | ❌ **Missing** - Management system |
| `metadata.strategy` | string | ❌ **Missing** - Deployment strategy |
| `metadata.time_period` | object | ❌ **Missing** - Analysis window definition |

---

### ⚠️ Mismatches (Fields That Don't Align)

| Whisper-STT Field | PBX-Web Field | Mismatch Type | Impact |
|------------------|---------------|---------------|--------|
| `summaries` (object) | `current_status` + `summary` (separate objects) | 🏗️ Structural | Whisper-stt merges current status + summary into single `summaries` object |
| `deployment_records[]` (flat array) | `deployment_events_last_30_days[]` (nested array) | 🏗️ Structural | Different array names, same content |
| `status` = "pending" | `outcome` (no "pending" value) | 🔀 Enum values | Whisper-stt adds "pending" state not in pbx-web |
| `status` = "rollback" | `event_type` = "deployment_rollback" + `outcome` = "rolled_back" | 🔀 Encoding | pbx-web splits rollback into type + outcome |
| `failure_type` enum | *(inferred from health_indicators)* | 🔀 Derivation | pbx-web doesn't explicitly categorize failure types |
| `replicaset_name` | `replicaSet` (camelCase) | 📝 Naming | snake_case vs camelCase convention |
| `zero_downtime_deployment` | *(not present, derived from strategy)* | 🔀 Inference | pbx-web implies via "Recreate" strategy |
| `uptime_percentage` | `uptime` (human-readable text) | 📊 Format | Percentage vs descriptive text |

---

## Schema Structure Comparison

### Whisper-STT Schema (3-section structure)

```
whisper-stt-data
├── metadata (3 fields)
│   ├── generated_at
│   ├── source_files[]
│   └── total_records
├── summaries (23 fields per service)
│   ├── service identifiers (4)
│   ├── deployment counts (4)
│   ├── health & stability (3)
│   ├── pod metrics (6)
│   └── incident tracking (6)
└── deployment_records[] (13 fields per record)
    ├── identifiers (5)
    ├── timestamps (2)
    ├── status & outcomes (2)
    ├── replica counts (3)
    └── image (1)
```

**Total Fields:** ~39 (including nested)

### PBX-Web Schema (9-section structure)

```
pbx-web-data
├── metadata (5 fields + time_period object)
├── current_status (7 fields + conditions array)
├── deployment_events_last_30_days[] (11 fields)
├── historical_deployments_beyond_30_days[] (6 fields)
├── deployment_metrics (8 fields + images array)
├── pod_health
│   ├── current_pod (6 fields)
│   ├── containers[] (5 fields)
│   └── health_indicators (5 fields)
├── infrastructure_details
│   ├── resource_limits (per-container)
│   ├── volumes[] (7 fields)
│   ├── environment_variables (3+ fields)
│   ├── secrets_used[]
│   ├── liveness_probes (per-container)
│   └── readiness_probes (per-container)
├── operational_logs_sample (4 fields + search_index_stats)
└── summary (7 fields)
```

**Total Fields:** ~80+ (including nested)

---

## Enum Value Comparison

### `overall_health` / `summary.overall_health`

| Whisper-STT | PBX-Web | Status |
|-------------|---------|--------|
| `healthy` | `excellent`, `good` | 🔄 Mapped |
| `degraded` | `moderate` | 🔄 Mapped |
| `unhealthy` | `poor` | 🔄 Mapped |
| `unknown` | *(no equivalent)* | ➕ Whisper-STT extension |

### `deployment_stability` / `summary.deployment_stability`

| Whisper-STT | PBX-Web | Status |
|-------------|---------|--------|
| `high` | `stable` | 🔄 Mapped |
| `medium` | `moderate` | 🔄 Mapped |
| `low` | `unstable` | 🔄 Mapped |
| `unknown` | *(no equivalent)* | ➕ Whisper-STT extension |

### `status` / `outcome`

| Whisper-STT | PBX-Web | Status |
|-------------|---------|--------|
| `success` | `success` | ✅ Exact match |
| `failed` | `failed` | ✅ Exact match |
| `pending` | *(no equivalent)* | ➕ Whisper-STT extension |
| `rollback` | `event_type="deployment_rollback"` + `outcome="rolled_back"` | 🔀 Different encoding |

### `failure_type`

| Whisper-STT | PBX-Web Equivalent |
|-------------|-------------------|
| `image_pull_error` | `health_indicators.no_image_pull_errors = false` |
| `crash_loop_back_off` | `health_indicators.no_restart_loops = false` |
| `oom_killed` | *(no tracking)* ❌ |
| `probe_failure` | `health_indicators.liveness_probes_passing = false` |
| `pvc_mount_failed` | *(no tracking)* ❌ |
| `resource_limit_exceeded` | *(no tracking)* ❌ |
| `unknown` | *(no explicit failure)* |

---

## Type Format Comparison

| Field Category | Whisper-STT Format | PBX-Web Format | Compatibility |
|----------------|-------------------|----------------|----------------|
| Timestamps | ISO 8601 with timezone offset (`+00:00`) | ISO 8601 with `Z` suffix | ✅ Compatible (different timezone notation) |
| Revisions | String (`"29"`) | Number (`29`) | ⚠️ Type mismatch |
| Percentages | String with `%` suffix (`"100%"`) | String with `%` suffix | ✅ Compatible |
| Booleans | `true`/`false` | `true`/`false` | ✅ Compatible |
| Enums | String values | String values | ✅ Compatible |
| Arrays | Present (can be empty) | Present (can be empty) | ✅ Compatible |

---

## Key Design Differences

### 1. Granularity vs. Aggregation

| Aspect | Whisper-STT | PBX-Web |
|--------|-------------|---------|
| **Current state** | Aggregated in `summaries` | Split across `current_status` + `pod_health` |
| **Historical data** | Single `deployment_records[]` array | Split into 30-day + beyond-30-day arrays |
| **Incidents** | Categorized by severity (critical/warning) | Uncategorized total count |
| **Restarts** | Aggregated total | Per-container breakdown |

### 2. Scope of Coverage

| Category | Whisper-STT | PBX-Web |
|----------|-------------|---------|
| **Deployment tracking** | ✅ Core metrics only | ✅ Comprehensive + cadence metrics |
| **Pod health** | ✅ Aggregate stats | ✅ Per-pod + per-container + probes |
| **Infrastructure** | ❌ Not tracked | ✅ Full resource limits + volumes + secrets |
| **Operational data** | ❌ Not tracked | ✅ App-specific logs + search index stats |
| **Failure taxonomy** | ✅ Explicit categorization | ❌ Inferred from health indicators |

### 3. Extensibility Model

| Aspect | Whisper-STT | PBX-Web |
|--------|-------------|---------|
| **Service-specific data** | ❌ No extension points | ✅ `operational_logs_sample` for app-specific |
| **Multi-container pods** | ❌ Not supported | ✅ Full per-container tracking |
| **Custom metrics** | ❌ Fixed schema | ✅ Flexible nested objects |
| **Historical windowing** | ❌ Fixed 30-day | ✅ Split windows (30-day + historical) |

---

## Coverage Analysis

```
┌─────────────────────────────────────────────────────────────────┐
│                    PBX-Web Field Coverage                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Total PBX-Web Fields:  ~80                                    │
│                                                                 │
│  Whisper-STT Coverage:                                         │
│  ├─ Direct mappings (18) ████████░░░░░░░░░░░░░░░ 22%          │
│  ├─ Partial mappings (5)  ███░░░░░░░░░░░░░░░░░░░  6%          │
│  ├─ Gaps (60+)           ░░░░░░░░░░░░░░░░░░░░░░░ 72%          │
│  └─ Mismatches (8)       ████░░░░░░░░░░░░░░░░░░░  10%         │
│                                                                 │
│  Overall Coverage:      28% (18 + 5 derived from 80)           │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

**Coverage by Section:**

| PBX-Web Section | Fields | Whisper-STT Coverage | % |
|-----------------|--------|---------------------|---|
| metadata | 5 | 3 | 60% |
| current_status | 7 + conditions | 2 | 20% |
| deployment_events | 11 | 9 | 82% |
| historical_deployments | 6 | 0 | 0% |
| deployment_metrics | 8 | 3 | 38% |
| pod_health | 16 | 3 | 19% |
| infrastructure_details | 20+ | 0 | 0% |
| operational_logs | 8 | 0 | 0% |
| summary | 7 | 4 | 57% |

---

## Transformation Guide: Whisper-STT → PBX-Web

### 1. Direct Field Mapping

```python
# Whisper-STT → PBX-Web direct mappings
pbx_web = {
    "metadata": {
        "service": whisper_stt["deployment_records"][0]["service"],
        "cluster": whisper_stt["deployment_records"][0]["cluster"],
        "namespace": whisper_stt["deployment_records"][0]["namespace"],
    },
    "deployment_events_last_30_days": [
        {
            "timestamp": rec["timestamp"],
            "date": rec["timestamp"][:10],  # Extract date from ISO timestamp
            "revision": int(rec["revision"]),  # String → number
            "deployment": rec["deployment_name"],
            "replicaSet": rec["replicaset_name"],
            "image": rec["image"],
            "outcome": rec["status"],
        }
        for rec in whisper_stt["deployment_records"]
    ],
    "summary": {
        "overall_health": map_health_enum(whisper_stt["summaries"]["whisper-stt"]["overall_health"]),
        "deployment_stability": map_stability_enum(whisper_stt["summaries"]["whisper-stt"]["deployment_stability"]),
        "deployment_success_rate": whisper_stt["summaries"]["whisper-stt"]["successful_deployment_rate"],
    },
}
```

### 2. Enum Mapping Functions

```python
def map_health_enum(whisper_health: str) -> str:
    """Map whisper-stt health enum to pbx-web health enum"""
    mapping = {
        "healthy": "excellent",  # or "good" based on uptime
        "degraded": "moderate",
        "unhealthy": "poor",
        "unknown": "moderate",  # Default fallback
    }
    return mapping.get(whisper_health, "moderate")

def map_stability_enum(whisper_stability: str) -> str:
    """Map whisper-stt stability enum to pbx-web stability enum"""
    mapping = {
        "high": "stable",
        "medium": "moderate",
        "low": "unstable",
        "unknown": "moderate",  # Default fallback
    }
    return mapping.get(whisper_stability, "moderate")
```

### 3. Type Conversions

```python
def convert_revision(whisper_revision: str) -> int:
    """Convert string revision to number"""
    return int(whisper_revision)

def convert_timestamp(whisper_timestamp: str) -> str:
    """Convert timestamp from +00:00 to Z suffix"""
    return whisper_timestamp.replace("+00:00", "Z")
```

### 4. Derived Field Calculations

```python
# Fields not in whisper-stt but can be derived
pbx_web["deployment_metrics"] = {
    "total_deployments_last_30_days": whisper_stt["summaries"]["whisper-stt"]["total_deployments"],
    "successful_deployments": whisper_stt["summaries"]["whisper-stt"]["successful_updates"],
    "failed_deployments": whisper_stt["summaries"]["whisper-stt"]["failed_rollouts"],
    "last_deployment": convert_timestamp(whisper_stt["summaries"]["whisper-stt"]["last_deployment_update"]),
}

# Cannot be derived (require infrastructure access)
# - resource_limits, volumes, probes, etc.
```

---

## Reverse Transformation Guide: PBX-Web → Whisper-STT

### 1. Projection to Core Fields

```python
whisper_stt = {
    "metadata": {
        "generated_at": pbx_web["metadata"]["data_collected_at"],
        "source_files": ["pbx-web-transform.json"],
        "total_records": len(pbx_web["deployment_events_last_30_days"]),
    },
    "summaries": {
        "pbx-web": {
            "service": pbx_web["metadata"]["service"],
            "total_deployments": pbx_web["deployment_metrics"]["total_deployments_last_30_days"],
            "successful_updates": pbx_web["deployment_metrics"]["successful_deployments"],
            "failed_rollouts": pbx_web["deployment_metrics"]["failed_deployments"],
            "last_deployment_update": pbx_web["deployment_metrics"]["last_deployment"],
            "overall_health": reverse_map_health(pbx_web["summary"]["overall_health"]),
            "deployment_stability": reverse_map_stability(pbx_web["summary"]["deployment_stability"]),
            "successful_deployment_rate": pbx_web["summary"]["deployment_success_rate"],
            # ... aggregate pod_health metrics
            "total_pods": 1,  # Fixed for Recreate strategy
            "running_pods": 1 if pbx_web["pod_health"]["current_pod"]["ready"] else 0,
            "total_restarts": pbx_web["pod_health"]["current_pod"]["restart_count"],
            "crashloops": 0 if pbx_web["pod_health"]["health_indicators"]["no_restart_loops"] else 1,
            "oomkills": 0,  # Not tracked in pbx-web
            "total_incidents": pbx_web["summary"]["issues_last_30_days"],
            "critical_incidents": 0,  # Not categorized in pbx-web
            "warning_incidents": pbx_web["summary"]["issues_last_30_days"],
            "log_errors": 0,  # Not tracked in pbx-web
        }
    },
    "deployment_records": [
        {
            "service": pbx_web["metadata"]["service"],
            "deployment_name": event.get("deployment", pbx_web["metadata"]["service"]),
            "replicaset_name": event["replicaSet"],
            "timestamp": event["timestamp"],
            "status": event["outcome"],
            "failure_type": None,  # Would need inference logic
            "revision": str(event["revision"]),  # Number → string
            "replicas": 1,  # Fixed for Recreate strategy
            "ready_replicas": 1 if event["outcome"] == "success" else 0,
            "available_replicas": 1 if event["outcome"] == "success" else 0,
            "image": event["image"],
            "cluster": pbx_web["metadata"]["cluster"],
            "namespace": pbx_web["metadata"]["namespace"],
        }
        for event in pbx_web["deployment_events_last_30_days"]
    ],
}
```

---

## Recommendations

### For Cross-Service Analysis

1. **Use whisper-stt schema as the baseline** - It's designed for comparability
2. **Project pbx-web to whisper-stt structure** before comparative analysis
3. **Focus on the 18 directly-mapped core metrics** for cross-service trends
4. **Treat infrastructure/operational gaps as service-specific context**, not comparison blockers

### For Extending Whisper-STT Schema

1. **Add `infrastructure_details` section** for resource tracking
2. **Split `deployment_records` into time windows** (30-day + historical)
3. **Add `pod_health.current_pod` object** for per-pod granularity
4. **Include `health_indicators` booleans** for explicit health checks
5. **Track `deployment_metrics.deployment_frequency_days`** for cadence analysis

### For Normalizing PBX-Web Schema

1. **Standardize on snake_case** field names (drop camelCase)
2. **Use string for `revision`** to match whisper-stt convention
3. **Add `failure_type` enum** to `deployment_events` for explicit categorization
4. **Flatten `summaries` object** to merge `current_status` + `summary` metrics
5. **Add `total_incidents` categorization** by severity level

---

## Conclusion

The whisper-stt deployment schema successfully maps to **28% of the pbx-web schema**, covering the **core deployment metrics and health indicators** necessary for cross-service comparability. The **72% gap** represents pbx-web's **operational, infrastructure, and application-specific tracking** that whisper-stt intentionally excludes to maintain a **simplified, service-agnostic format**.

**Key Takeaways:**
- ✅ **18 fields align perfectly** for direct comparison
- ⚠️ **8 fields require enum mapping or type conversion**
- ❌ **60+ pbx-web fields have no whisper-stt equivalent** (infrastructure, multi-container, operational)
- 🔄 **Transformation is bidirectional** with projection/aggregation logic
- 📊 **For comparative analysis, use whisper-stt structure as the baseline** and project pbx-web onto it

---

**Document Status:** Complete  
**Total Field Pairs Analyzed:** 80+ pbx-web fields vs 39 whisper-stt fields  
**Direct Mappings:** 18 (45% of whisper-stt fields)  
**Gap Analysis:** 60+ pbx-web fields not covered by whisper-stt  
**Generated by:** Bead adc-6bj26  
**Dependencies:** Bead adc-3mmf8 (pbx-web field inventory)
