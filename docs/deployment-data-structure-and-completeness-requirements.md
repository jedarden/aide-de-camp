# Deployment Data Structure and 30-Day Completeness Requirements

## Overview

This document describes the deployment data schema, 30-day completeness requirements, and edge case handling for the aide-de-camp project's deployment tracking system.

**Schema Version**: 1.0  
**Last Updated**: 2026-08-07  
**Bead ID**: adc-vicjy  
**Primary Implementation**: `whisper_stt_deployment_schema.py`

## Data Schema Fields

### Top-Level Structure

The deployment data follows a hierarchical structure with the following top-level sections:

#### 1. Metadata (Required)
Defines the temporal bounds and provenance of the deployment data.

```json
"metadata": {
  "generated_at": "2026-08-06T12:03:32.329077Z",        // ISO 8601 timestamp
  "data_period_start": "2026-07-07T09:07:50Z",        // Analysis window start
  "data_period_end": "2026-08-06T09:07:50Z",          // Analysis window end
  "services": ["whisper-stt", "whisper-openai"],       // Services tracked
  "clusters": ["ardenone-cluster"],                    // Kubernetes clusters
  "data_sources": ["kubernetes_replicasets", "argo_cd"] // Data origins
}
```

**Field Constraints**:
- `generated_at` must be ≥ `data_period_end`
- `data_period_start` < `data_period_end`
- Time period should span approximately 30 days (28-32 days accepted)
- All timestamps use ISO 8601 format with UTC timezone ('Z' suffix)

#### 2. Argo Workflows (Required)
CI/CD workflow execution data for deployment automation.

```json
"argo_workflows": {
  "whisper_stt_build": {
    "template_name": "whisper-stt-build",
    "template_created": "2026-05-27T02:26:47Z",
    "workflow_runs_last_30_days": 0,                   // Integer ≥ 0
    "workflow_runs": []                                // Array of workflow runs
  }
}
```

**WorkflowRun Structure**:
```json
{
  "workflow_name": "whisper-stt-build-abc123",
  "started_at": "2026-07-12T16:53:42Z",
  "status": "Succeeded",                               // Enum: Succeeded|Failed|Running
  "finished_at": "2026-07-12T16:55:30Z",              // Optional
  "git_revision": "abc123def456",                      // Optional
  "image_tag": "1.8.6"                                 // Optional
}
```

#### 3. ArgoCD (Required)
GitOps deployment management and synchronization state.

```json
"argo_cd": {
  "whisper-stt": {
    "application_found": true,
    "applications": [
      {
        "name": "whisper-stt",
        "namespace": "whisper-stt",
        "project": "default",
        "sync_status": "Synced",                       // Enum: Synced|OutOfSync|Unknown
        "health_status": "Healthy"                     // Enum: Healthy|Progressing|Degraded|Missing|Unknown
      }
    ]
  }
}
```

#### 4. Cluster Deployments (Required)
Kubernetes deployment metrics and ReplicaSet history.

```json
"cluster_deployments": {
  "whisper-stt": {
    "namespace": "whisper-stt",
    "deployment_name": "whisper-stt",
    "created_at": "2026-05-01T17:26:49Z",
    "current_image": "ronaldraygun/whisper-stt:1.8.6",
    "current_replicas": 1,                              // Integer ≥ 0
    "last_updated": "2026-07-12T16:54:57Z",          // Optional
    "replica_history": [],                             // ReplicaSet entries
    "deployments_last_30_days": 2,                     // Integer ≥ 0
    "successful_deployments": 2,                       // Integer ≥ 0
    "failed_deployments": 0,                            // Integer ≥ 0
    "deployment_versions": ["1.8.6"],
    "all_versions_in_history": ["1.2.5", "1.3.0", "1.8.6"]
  }
}
```

**ReplicaHistoryEntry Structure**:
```json
{
  "name": "whisper-stt-847fd8d7b9",
  "created_at": "2026-07-12T16:53:42Z",
  "image": "ronaldraygun/whisper-stt:1.8.6",
  "replicas": 1,                                       // Integer ≥ 0
  "available_replicas": 1,                            // Optional
  "ready_replicas": 1,                                // Optional
  "status": "successful",                             // Enum: successful|rolled_over|scaled_down_or_failed
  "days_ago": 25                                      // Integer ≥ 0
}
```

**Validation Constraints**:
- `successful_deployments + failed_deployments ≤ deployments_last_30_days`
- All replica history entries must have valid timestamps
- `days_ago` calculated relative to `generated_at`

#### 5. Summary (Required)
High-level metrics and completeness indicators for the 30-day period.

```json
"summary": {
  "total_deployments_last_30_days": 2,                // Integer ≥ 0
  "whisper_stt_deployments": 1,                       // Integer ≥ 0
  "successful_deployments": 2,                        // Integer ≥ 0
  "failed_or_scaled_down": 0,                          // Integer ≥ 0
  "data_coverage": "100%",                             // String percentage
  "gaps_detected": false,                              // Boolean
  "largest_gap_days": 0                                // Integer ≥ 0
}
```

#### 6. Pod Health (Required)
Current pod status and aggregate health metrics.

```json
"pod_health": {
  "current_pods": [
    {
      "name": "whisper-stt-847fd8d7b9-v2rs5",
      "created": "2026-07-12T16:53:42Z",
      "age_days": 25,                                  // Integer ≥ 0
      "status": "Running",                             // Enum: Running|Pending|Failed|Succeeded|Unknown
      "restart_count": 0,                              // Integer ≥ 0
      "node": "k3s-agent-minisforum",
      "containers": [
        {
          "name": "whisper-stt",
          "image": "ronaldraygun/whisper-stt:1.8.6",
          "ready": true,
          "restart_count": 0                           // Integer ≥ 0
        }
      ]
    }
  ],
  "pod_metrics": {
    "total_pods": 2,                                   // Integer ≥ 0
    "running_pods": 2,                                 // Integer ≥ 0, ≤ total_pods
    "total_containers": 2,                             // Integer ≥ 0
    "total_restarts": 0,                               // Integer ≥ 0
    "crashloops": 0,                                   // Integer ≥ 0
    "oomkills": 0,                                     // Integer ≥ 0
    "failed_pods": 0,                                  // Integer ≥ 0
    "pending_pods": 0                                  // Integer ≥ 0
  }
}
```

#### 7. Resources (Optional)
CPU and memory allocation specifications.

```json
"resources": {
  "whisper-stt": {
    "cpu_request": "500m",
    "cpu_limit": "1000m",
    "memory_request": "512Mi",
    "memory_limit": "1Gi"
  }
}
```

#### 8. Storage (Optional)
PVC configuration and status information.

```json
"storage": {
  "whisper-stt-data": {
    "capacity": "10Gi",
    "storage_class": "sata-large",
    "status": "Bound",                                 // Enum: Bound|Pending|Lost
    "age_days": 90                                     // Integer ≥ 0
  }
}
```

#### 9. Error Incidents (Optional)
Error and failure tracking with severity levels.

```json
"error_incidents": {
  "total_incidents": 3,                                // Integer ≥ 0
  "critical_incidents": 1,                             // Integer ≥ 0
  "warning_incidents": 2,                             // Integer ≥ 0
  "incident_details": [
    {
      "timestamp": "2026-07-08T14:23:11Z",
      "severity": "critical",                          // Enum: critical|warning|info
      "message": "PodCrashLoopBackOff",
      "affected_component": "whisper-stt"
    }
  ]
}
```

#### 10. Notes (Optional)
Additional context and observations.

```json
"notes": [
  "No Argo Workflow runs found for whisper-stt in the last 30 days",
  "Deployments appear to be managed via ArgoCD or manual kubectl operations",
  "Service experienced rapid deployment sequence on 2026-07-08 before stabilizing"
]
```

## 30-Day Completeness Requirements

### Definition of a Complete 30-Day Period

A deployment dataset is considered **complete** for a 30-day period when it meets the following criteria:

1. **Temporal Coverage**:
   - `data_period_start` to `data_period_end` spans exactly 30 days (±2 days tolerance)
   - Acceptable range: 28-32 days
   - Example: `2026-07-07T09:07:50Z` to `2026-08-06T09:07:50Z` = 30 days

2. **Data Integrity**:
   - All required fields are present and non-null
   - All timestamps are valid ISO 8601 format
   - All counts are non-negative integers
   - Enum values match defined sets
   - Referential integrity maintained (e.g., `successful + failed ≤ total`)

3. **Coverage Metrics**:
   - `summary.data_coverage` reflects actual data availability
   - `summary.gaps_detected` accurately indicates missing periods
   - `summary.largest_gap_days` reports the maximum consecutive day gap

4. **Consistency Validation**:
   - `metadata.data_period_end ≤ metadata.generated_at`
   - `cluster_deployments` sums match `summary` totals
   - Pod health metrics align with deployment data
   - Replica history covers all deployment events in the period

### Completeness Categories

| Category | Coverage % | Gap Count | Data Quality | Interpretation |
|----------|------------|-----------|--------------|----------------|
| **Excellent** | >75% | <5 | excellent | High confidence in analysis |
| **Good** | >50% | <10 | good | Reliable for most analysis |
| **Fair** | 10-50% | 10-20 | fair | Use with caution, note limitations |
| **Poor** | <10% | >20 | poor | Insufficient for reliable analysis |

### Completeness Calculation

```python
def calculate_completeness(data_period_start: datetime, 
                           data_period_end: datetime,
                           deployment_events: List[datetime]) -> Dict[str, Any]:
    """
    Calculate completeness metrics for deployment data.
    
    Returns:
        {
            "expected_days": 30,
            "days_with_data": 28,
            "coverage_percentage": 93.3,
            "gaps": [{"date": "2026-07-15", "consecutive": 1}],
            "largest_gap_days": 1,
            "data_quality": "excellent"
        }
    """
    expected_days = (data_period_end - data_period_start).days
    unique_days_with_data = len(set(event.date() for event in deployment_events))
    coverage_percentage = (unique_days_with_data / expected_days) * 100
    
    # Gap detection logic
    all_dates = set((data_period_start + timedelta(days=d)).date() 
                    for d in range(expected_days))
    dates_with_data = set(event.date() for event in deployment_events)
    gaps = [{"date": date.isoformat(), "consecutive": 1} 
            for date in all_dates - dates_with_data]
    
    # Classify consecutive gaps
    # (implementation details in validate_coverage_and_gaps.py)
    
    return {
        "expected_days": expected_days,
        "days_with_data": unique_days_with_data,
        "coverage_percentage": round(coverage_percentage, 1),
        "gaps": gaps,
        "largest_gap_days": max(len(gap) for gap in consecutive_gaps_groups) if gaps else 0
    }
```

## Edge Cases and Handling

### 1. Temporal Edge Cases

#### Partial Day Coverage
**Scenario**: Data collection starts/ends mid-day  
**Handling**: 
- Include partial days in coverage calculation
- Document partial day nature in `notes`
- Example: Period `2026-07-07T14:00:00Z` to `2026-08-06T10:00:00Z` counts as 30 days

#### Daylight Saving Time Transitions
**Scenario**: Period crosses DST boundary  
**Handling**:
- Use UTC timestamps exclusively (avoid local time)
- ISO 8601 'Z' suffix ensures UTC interpretation
- Duration calculation handles 23/25-hour days automatically

#### Month Boundaries
**Scenario**: 30-day period crosses month end  
**Handling**:
- Duration calculation uses exact day count, not calendar months
- `2026-07-15` to `2026-08-14` = 30 days (regardless of month lengths)

### 2. Data Gaps

#### Isolated Gaps
**Definition**: Missing days surrounded by days with data  
**Impact**: Minimal - may represent no-activity periods  
**Handling**:
- Count in `summary.gaps_detected` = `true`
- Report in `summary.largest_gap_days`
- If gap ≥ 7 days, add note to `notes` array

#### Consecutive Gaps
**Definition**: Multiple consecutive missing days  
**Impact**: Moderate to severe depending on duration  
**Handling**:
- Classify as consecutive sequence in gap analysis
- Flag in data quality assessment
- Generate recommendation if ≥ 3 consecutive days

#### Leading/Trailing Gaps
**Definition**: Missing data at period boundaries  
**Impact**: N/A - period definition is fixed  
**Handling**:
- Adjust `data_period_start`/`data_period_end` to match actual data
- Document adjustment in `notes`
- Example: If data starts `2026-07-10`, set period start accordingly

### 3. Zero Deployment Events

#### Scenario: No Deployments in 30-Day Period
**Validity**: Legitimate - stable service with no changes  
**Indicators**:
- `deployments_last_30_days = 0`
- `replica_history = []` (or entries outside period)
- `successful_deployments = 0`, `failed_deployments = 0`

**Handling**:
- Set `summary.data_coverage = "100%"` (no missing data, just no activity)
- Set `summary.gaps_detected = false`
- Add note: "No deployment activity detected in analysis period"
- Verify with current pod status (service should be running)

### 4. Deployment Frequency Anomalies

#### Rapid Succession Deployments
**Scenario**: Multiple deployments within short timeframe  
**Example**: 5 deployments in 2 hours  
**Handling**:
- Normal for debugging/fix iterations
- Add note describing pattern
- Flag if >50% of deployments failed (indicates instability)

#### Long Stable Periods
**Scenario**: Single deployment for entire 30-day period  
**Handling**:
- Normal for mature, stable services
- High data quality (100% coverage with 1 deployment event)
- Document current uptime in days

### 5. Data Source Inconsistencies

#### Argo Workflow vs ReplicaSet Mismatch
**Scenario**: ReplicaSets exist but no Argo workflow runs  
**Interpretation**: Deployments via ArgoCD sync or manual kubectl  
**Handling**:
- Set `argo_workflows.workflow_runs_last_30_days = 0`
- Add note: "Deployments managed outside CI workflow"
- Cross-reference with `argo_cd` sync status

#### ArgoCD Out of Sync with Live State
**Scenario**: ArgoCD reports "OutOfSync" but pods are Running  
**Interpretation**: Manual overrides or drift  
**Handling**:
- Document in `notes`
- Flag as potential operational issue
- Recommend reconciliation in `notes`

### 6. Missing Optional Fields

#### Missing Pod Health Data
**Impact**: Reduced operational visibility  
**Handling**:
- Field is optional - validation passes
- Add warning in completeness check
- Note: "Pod health data unavailable - verify cluster access"

#### Missing Error Incidents
**Impact**: Unknown failure patterns  
**Handling**:
- Field is optional - validation passes
- Set to `null` or omit entirely
- Note: "Error incident tracking not enabled"

### 7. ReplicaSet History Edge Cases

#### ReplicaSets Outside Analysis Period
**Scenario**: `replica_history` contains entries older than 30 days  
**Handling**:
- Filter to only include entries where `days_ago ≤ 30`
- Use `all_versions_in_history` for complete historical record
- Keep older entries in `all_versions_in_history` array

#### ReplicaSets with Zero Replicas
**Scenario**: ReplicaSet with `replicas: 0` and `status: rolled_over`  
**Interpretation**: Successful deployment, later replaced  
**Handling**:
- Count in `deployments_last_30_days`
- Classify as `successful` (not failed)
- Do NOT count in `failed_deployments`

#### ReplicaSets with Missing Ready Replicas
**Scenario**: `available_replicas = null`, `ready_replicas = null`  
**Interpretation**: Rolled over before achieving readiness  
**Handling**:
- Normal for rapid replacement scenarios
- Validate based on `status` field
- Add note if pattern persists across multiple ReplicaSets

## Validation Workflow

### Step 1: Structural Validation
```bash
python3 validate_deployment_data.py whisper-stt-deployments-30d.json
```

Checks:
- ✓ Required fields present
- ✓ Data types correct
- ✓ Timestamps valid ISO 8601
- ✓ Enums match defined values
- ✓ Numeric constraints satisfied (≥ 0, ≤ totals)

### Step 2: 30-Day Completeness Check
```python
from datetime import datetime
start = datetime.fromisoformat(data["metadata"]["data_period_start"])
end = datetime.fromisoformat(data["metadata"]["data_period_end"])
duration = (end - start).days

if 28 <= duration <= 32:
    print(f"✓ Valid 30-day period: {duration} days")
else:
    print(f"⚠️  Period out of range: {duration} days")
```

### Step 3: Coverage Analysis
```bash
python3 validate_coverage_and_gaps.py
```

Outputs:
- Coverage percentage by data source
- Gap classification (isolated vs consecutive)
- Data quality rating (excellent/good/fair/poor)
- Recommendations for improvement

### Step 4: Cross-Validation
```python
# Verify summary totals match cluster deployments
total_deployments = data["summary"]["total_deployments_last_30_days"]
cluster_total = data["cluster_deployments"]["whisper-stt"]["deployments_last_30_days"]

if total_deployments >= cluster_total:
    print("✓ Summary totals consistent")
else:
    print("⚠️  Summary total less than cluster total")
```

## Implementation Reference

### Python Validation
```python
from whisper_stt_deployment_schema import (
    WhisperSTTDeploymentSchema,
    validate_deployment_data
)

# Load and validate
with open('whisper-stt-deployments-30d.json') as f:
    data = json.load(f)

result = validate_deployment_data(data)
if result["valid"]:
    print("✓ Deployment data valid")
    schema = result["schema"]
    print(f"Period: {schema.metadata.data_period_start} to {schema.metadata.data_period_end}")
    print(f"Coverage: {schema.summary.data_coverage}")
else:
    print("✗ Validation failed:")
    for error in result["errors"]:
        print(f"  - {error}")
```

### CLI Validation
```bash
# Validate specific file
.venv/bin/python validate_deployment_data.py whisper-stt-deployments-30d.json

# Skip 30-day check (for partial data)
.venv/bin/python validate_deployment_data.py --no-30-day-check partial-data.json

# Custom schema
.venv/bin/python validate_deployment_data.py --schema custom-schema.json data.json
```

## Data Quality Recommendations

### For Excellent Quality
1. Maintain 100% coverage (no missing days)
2. Include optional fields (pod_health, error_incidents)
3. Add contextual notes for anomalies
4. Cross-validate data sources (Argo vs ArgoCD vs ReplicaSets)

### For Good Quality
1. Coverage > 75% with gaps < 5 days
2. All required fields present and valid
3. Gap analysis documented in `notes`

### For Fair Quality
1. Coverage 50-75% with gaps 5-10 days
2. Most required fields present
3. Note limitations in analysis

### For Poor Quality
1. Coverage < 50% or gaps > 10 days
2. Missing required fields
3. Recommend extending collection period or investigating data pipeline

## Maintenance

- **Schema updates**: Modify `whisper_stt_deployment_schema.py` and increment version
- **Validation updates**: Update `validate_deployment_data.py` with new checks
- **Documentation**: Update this file with new edge cases or requirements
- **Testing**: Add regression tests for new validation rules

## Related Files

- Schema Implementation: `whisper_stt_deployment_schema.py`
- Validation Script: `validate_deployment_data.py`
- Coverage Analysis: `validate_coverage_and_gaps.py`
- 30-Day Files: `whisper-stt-deployments-30d.json`, `pbx-web-deployment-data-30days.json`
- Validation Status: `docs/deployment-data-files-2026-08-06.md`

---

**Document Control**  
Created: 2026-08-07  
Last Modified: 2026-08-07  
Author: Automated Documentation  
Status: Complete  
Bead: adc-vicjy  
