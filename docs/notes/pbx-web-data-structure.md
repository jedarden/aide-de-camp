# pbx-web Deployment Data Structure

This document describes the structure and format of pbx-web deployment data used in the aide-de-camp analysis system.

## Overview

The pbx-web deployment data is structured as a comprehensive JSON document that captures the complete state, history, and operational metrics of the pbx-web Kubernetes deployment. There are two main data formats:

1. **Primary Deployment Data** - Comprehensive operational state and metrics
2. **Deployment Report Format** - Historical analysis and incident tracking

## Primary Deployment Data Structure

### Root Level Structure

```json
{
  "metadata": {...},
  "current_status": {...},
  "deployment_events_last_30_days": [...],
  "historical_deployments_beyond_30_days": [...],
  "deployment_metrics": {...},
  "pod_health": {...},
  "operational_logs_sample": {...},
  "infrastructure_details": {...},
  "summary": {...}
}
```

### 1. Metadata Section (REQUIRED)

```json
{
  "metadata": {
    "service": "pbx-web",              // REQUIRED: Service name
    "namespace": "pbx-web",            // REQUIRED: Kubernetes namespace
    "cluster": "ardenone-cluster",     // REQUIRED: Cluster name
    "data_collected_at": "2026-08-06T12:37:36Z",  // REQUIRED: ISO 8601 timestamp
    "time_period": {
      "start": "2026-07-07T00:00:00Z",           // REQUIRED: Analysis window start
      "end": "2026-08-06T12:37:36Z",             // REQUIRED: Analysis window end
      "description": "Last 30 days"              // OPTIONAL: Human-readable description
    },
    "managed_by": "ArgoCD",            // REQUIRED: Deployment management system
    "strategy": "Recreate"             // REQUIRED: Deployment strategy
  }
}
```

**Field Types:**
- `service`: string (max 100 chars)
- `namespace`: string (max 100 chars)
- `cluster`: string (max 100 chars)
- `data_collected_at`: ISO 8601 datetime string
- `time_period`: object with datetime strings
- `managed_by`: string (enum: ["ArgoCD", "kubectl", "Helm", "manual"])
- `strategy`: string (enum: ["Recreate", "RollingUpdate", "Rollback"])

**Validation Rules:**
- All string fields must be non-empty
- Timestamps must be valid ISO 8601 format
- `end` timestamp must be >= `start` timestamp
- `strategy` must match Kubernetes deployment strategies

### 2. Current Status Section (REQUIRED)

```json
{
  "current_status": {
    "deployment_name": "pbx-web",                    // REQUIRED: Deployment name
    "current_revision": 14,                          // REQUIRED: Integer revision number
    "current_image": "ronaldraygun/pbx-web:1.0.9",   // REQUIRED: Full image reference
    "generation": 36,                                // REQUIRED: Kubernetes generation
    "replicas": 1,                                   // REQUIRED: Desired replica count
    "readyReplicas": 1,                              // REQUIRED: Ready replica count
    "updatedReplicas": 1,                            // REQUIRED: Updated replica count
    "availableReplicas": 1,                          // REQUIRED: Available replica count
    "current_pod": "pbx-web-5ff68464d-mkn8n",       // REQUIRED: Current pod name
    "pod_created_at": "2026-07-28T17:26:12Z",        // REQUIRED: Pod creation timestamp
    "conditions": [...],                              // REQUIRED: Array of condition objects
  }
}
```

**Field Types:**
- `deployment_name`: string (max 100 chars)
- `current_revision`: integer >= 0
- `current_image`: string (valid image reference format)
- `generation`: integer >= 0
- `replicas`: integer >= 0
- `readyReplicas`: integer >= 0
- `updatedReplicas`: integer >= 0
- `availableReplicas`: integer >= 0
- `current_pod`: string (valid Kubernetes pod name)
- `pod_created_at`: ISO 8601 datetime string

**Validation Rules:**
- `readyReplicas` <= `replicas`
- `updatedReplicas` <= `replicas`
- `availableReplicas` <= `replicas`
- All replica counts must be non-negative

**Conditions Array:**
```json
{
  "conditions": [
    {
      "type": "Progressing",                      // REQUIRED: Condition type
      "status": "True",                          // REQUIRED: Condition status
      "reason": "NewReplicaSetAvailable",        // REQUIRED: Machine-readable reason
      "message": "ReplicaSet \"...\" has progressed.",  // REQUIRED: Human-readable message
      "lastTransitionTime": "2026-05-01T20:57:27Z"  // REQUIRED: ISO 8601 timestamp
    }
  ]
}
```

**Condition Types:**
- `Progressing`: Deployment is making progress
- `Available`: Deployment has minimum availability
- `ReplicaFailure`: Replica set failure

**Status Values:** `True`, `False`, `Unknown`

### 3. Deployment Events Array (REQUIRED)

```json
{
  "deployment_events_last_30_days": [
    {
      "date": "2026-07-28",                      // REQUIRED: Event date (YYYY-MM-DD)
      "timestamp": "2026-07-28T17:26:12Z",      // REQUIRED: ISO 8601 timestamp
      "event_type": "deployment_rollout",       // REQUIRED: Event type
      "deployment": "pbx-web",                   // OPTIONAL: Deployment name
      "revision": 14,                            // OPTIONAL: Revision number
      "replicaSet": "pbx-web-5ff68464d",        // OPTIONAL: ReplicaSet name
      "image": "ronaldraygun/pbx-web:1.0.9",   // OPTIONAL: Image reference
      "outcome": "success",                     // REQUIRED: Event outcome
      "pod_name": "pbx-web-5ff68464d-mkn8n",   // OPTIONAL: Pod name
      "pod_ready": true,                        // OPTIONAL: Pod ready status
      "restart_count": 0,                       // OPTIONAL: Container restart count
      "notes": "Current active deployment"      // OPTIONAL: Additional context
    }
  ]
}
```

**Event Types:**
- `deployment_rollout`: New deployment created
- `deployment_rollback`: Deployment rolled back
- `scaling_change`: Replica count changed
- `image_update`: Container image updated
- `config_update`: Configuration changed

**Outcome Values:**
- `success`: Operation completed successfully
- `failed`: Operation failed
- `rolled_back`: Deployment was rolled back
- `partial`: Partial success/failure

**Field Types:**
- `date`: string (YYYY-MM-DD format)
- `timestamp`: ISO 8601 datetime string
- `event_type`: string (enum above)
- `deployment`: string (max 100 chars)
- `revision`: integer >= 0
- `replicaSet`: string (valid Kubernetes ReplicaSet name)
- `image`: string (valid image reference)
- `outcome`: string (enum above)
- `pod_name`: string (valid Kubernetes pod name)
- `pod_ready`: boolean
- `restart_count`: integer >= 0
- `notes`: string (max 500 chars)

### 4. Historical Deployments Array (OPTIONAL)

```json
{
  "historical_deployments_beyond_30_days": [
    {
      "date": "2026-06-25",                      // REQUIRED: Event date
      "timestamp": "2026-06-25T15:23:48Z",      // REQUIRED: ISO 8601 timestamp
      "revision": 10,                            // REQUIRED: Revision number
      "replicaSet": "pbx-web-6d86477cdb",      // REQUIRED: ReplicaSet name
      "image": "ronaldraygun/pbx-web:1.0.7",   // REQUIRED: Image reference
      "notes": "Prior to 30-day window"         // OPTIONAL: Context
    }
  ]
}
```

**Field Types:** Same as deployment events, but with fewer required fields.

### 5. Deployment Metrics Section (REQUIRED)

```json
{
  "deployment_metrics": {
    "total_deployments_last_30_days": 5,        // REQUIRED: Total deployment count
    "successful_deployments": 5,                // REQUIRED: Success count
    "failed_deployments": 0,                     // REQUIRED: Failure count
    "deployment_frequency_days": 6,            // REQUIRED: Days between deployments
    "unique_images_deployed": 3,                 // REQUIRED: Unique image count
    "images_used_last_30_days": [                // REQUIRED: Array of image references
      "ronaldraygun/pbx-web:1.0.9",
      "ronaldraygun/pbx-web:1.0.8",
      "python:3-slim"
    ],
    "current_uptime_days": 9,                   // REQUIRED: Current uptime in days
    "last_deployment": "2026-07-28T17:26:12Z",  // REQUIRED: Last deployment timestamp
    "days_since_last_deployment": 9             // REQUIRED: Days since last deployment
  }
}
```

**Field Types:**
- All counts: integers >= 0
- `deployment_frequency_days`: number >= 0
- `current_uptime_days`: number >= 0
- `days_since_last_deployment`: number >= 0
- `last_deployment`: ISO 8601 datetime string

**Validation Rules:**
- `successful_deployments` <= `total_deployments_last_30_days`
- `failed_deployments` <= `total_deployments_last_30_days`
- `total_deployments_last_30_days` == `successful_deployments` + `failed_deployments`

### 6. Pod Health Section (REQUIRED)

```json
{
  "pod_health": {
    "current_pod": {
      "name": "pbx-web-5ff68464d-mkn8n",       // REQUIRED: Pod name
      "created_at": "2026-07-28T17:26:12Z",    // REQUIRED: Creation timestamp
      "phase": "Running",                      // REQUIRED: Pod phase
      "ready": true,                            // REQUIRED: Ready status
      "restart_count": 0,                       // REQUIRED: Restart count
      "uptime_days": 9,                         // REQUIRED: Uptime in days
      "containers": [...]                       // REQUIRED: Array of container objects
    },
    "health_indicators": {
      "no_crashes": true,                        // REQUIRED: No crashes indicator
      "no_restart_loops": true,                 // REQUIRED: No restart loops
      "no_image_pull_errors": true,             // REQUIRED: No image pull errors
      "liveness_probes_passing": true,           // REQUIRED: Liveness probe status
      "readiness_probes_passing": true           // REQUIRED: Readiness probe status
    }
  }
}
```

**Pod Phases:** `Pending`, `Running`, `Succeeded`, `Failed`, `Unknown`

**Container Object:**
```json
{
  "containers": [
    {
      "name": "nginx",                           // REQUIRED: Container name
      "image": "localhost:7439/nginx:alpine",   // REQUIRED: Image reference
      "ready": true,                             // REQUIRED: Ready status
      "restartCount": 0,                         // REQUIRED: Restart count
      "running_since": "2026-07-28T17:26:13Z"   // REQUIRED: Start timestamp
    }
  ]
}
```

### 7. Operational Logs Sample Section (OPTIONAL)

```json
{
  "operational_logs_sample": {
    "recent_activity": "Pagefind search index rebuilding",  // REQUIRED: Activity description
    "last_rebuild": "2026-08-05T21:46:11.870571Z",         // REQUIRED: Last activity timestamp
    "rebuild_frequency": "triggered by bucket signature changes",  // REQUIRED: Frequency description
    "search_index_stats": {                                 // OPTIONAL: Statistics object
      "indexed_pages": 197,                                // Integer >= 0
      "indexed_words": 7592,                               // Integer >= 0
      "languages": 1,                                      // Integer >= 0
      "build_time_avg_seconds": 2.0                        // Number >= 0
    },
    "log_health": "normal - no errors or warnings in recent logs"  // REQUIRED: Health status
  }
}
```

### 8. Infrastructure Details Section (REQUIRED)

```json
{
  "infrastructure_details": {
    "resource_limits": {
      "site_generator": {
        "cpu_limit": "500m",                    // REQUIRED: CPU limit (Kubernetes format)
        "memory_limit": "512Mi",               // REQUIRED: Memory limit
        "cpu_request": "10m",                  // REQUIRED: CPU request
        "memory_request": "128Mi"              // REQUIRED: Memory request
      },
      "nginx": {
        "cpu_limit": "100m",
        "memory_limit": "128Mi",
        "cpu_request": "5m",
        "memory_request": "32Mi"
      }
    },
    "volumes": [...],                            // REQUIRED: Array of volume objects
    "environment_variables": {...},             // REQUIRED: Environment variables object
    "secrets_used": [...],                       // REQUIRED: Array of secret names
    "liveness_probes": {...},                    // REQUIRED: Probe configurations
    "readiness_probes": {...}                    // REQUIRED: Probe configurations
  }
}
```

**Volume Object:**
```json
{
  "volumes": [
    {
      "name": "www",                             // REQUIRED: Volume name
      "type": "emptyDir",                        // REQUIRED: Volume type
      "purpose": "shared content between containers",  // OPTIONAL: Purpose description
      "configMap": "pbx-web-nginx-conf",        // CONDITIONAL: ConfigMap name (if type=ConfigMap)
      "medium": "Memory",                        // OPTIONAL: Medium for emptyDir
      "sizeLimit": "16Mi"                       // OPTIONAL: Size limit
    }
  ]
}
```

**Volume Types:** `emptyDir`, `configMap`, `secret`, `persistentVolumeClaim`

**Environment Variables:**
```json
{
  "environment_variables": {
    "S3_ENDPOINT": "http://garage.garage-operator.svc.cluster.local:3900",
    "S3_BUCKET": "recordings",
    "PYTHONUNBUFFERED": "1"
  }
}
```

**Probe Configuration:**
```json
{
  "liveness_probes": {
    "site_generator": {
      "path": "/health",                        // REQUIRED: Probe path
      "port": 9000,                              // REQUIRED: Port number
      "initialDelaySeconds": 10,                // REQUIRED: Initial delay
      "periodSeconds": 30,                      // REQUIRED: Check period
      "timeoutSeconds": 5,                      // REQUIRED: Timeout
      "failureThreshold": 3                     // REQUIRED: Failure threshold
    }
  }
}
```

### 9. Summary Section (REQUIRED)

```json
{
  "summary": {
    "overall_health": "excellent",               // REQUIRED: Health status
    "deployment_stability": "stable",           // REQUIRED: Stability status
    "uptime": "9 days continuous",              // REQUIRED: Uptime description
    "issues_last_30_days": 0,                   // REQUIRED: Issue count
    "rollbacks_last_30_days": 1,                // REQUIRED: Rollback count
    "deployment_success_rate": "100%",          // REQUIRED: Success rate string
    "recommendation": "Service is healthy..."   // REQUIRED: Recommendation text
  }
}
```

**Health Status Values:** `excellent`, `good`, `fair`, `poor`, `critical`

**Stability Status Values:** `stable`, `unstable`, `degrading`, `recovering`

## Deployment Report Format

The deployment report format provides historical analysis and incident tracking.

### Structure

```json
{
  "report_metadata": {...},
  "deployment_summary": {...},
  "operational_metrics": {...},
  "incident_analysis": {...},
  "argo_cd_integration": {...},
  "log_analysis": {...},
  "security_observations": {...},
  "overall_assessment": {...}
}
```

### Key Differences from Primary Format

1. **Report Metadata** replaces deployment metadata
2. **Deployment Summary** includes historical ReplicaSets
3. **Incident Analysis** provides detailed error patterns
4. **Log Analysis** categorizes log streams
5. **Security Observations** tracks security-relevant events

## CSV Deployment Events Format

The CSV format provides a simplified view of deployment events for data exchange and analysis.

### Structure

```csv
date,timestamp,event_type,deployment,revision,replicaSet,image,outcome,pod_name,pod_ready,restart_count,notes
2026-07-28,2026-07-28T17:26:12Z,deployment_rollout,pbx-web,14,pbx-web-5ff68464d,ronaldraygun/pbx-web:1.0.9,success,pbx-web-5ff68464d-mkn8n,true,0,Current active deployment
```

### Column Specifications

| Column | Type | Required | Description | Format |
|--------|------|----------|-------------|---------|
| date | string | Yes | Event date | YYYY-MM-DD |
| timestamp | string | Yes | Full timestamp | ISO 8601 |
| event_type | string | Yes | Event type | deployment_rollout, deployment_rollback, etc. |
| deployment | string | No | Deployment name | Kubernetes resource name |
| revision | integer | No | Revision number | Non-negative integer |
| replicaSet | string | No | ReplicaSet name | Kubernetes ReplicaSet name |
| image | string | No | Container image | image:tag format |
| outcome | string | Yes | Event outcome | success, failed, rolled_back |
| pod_name | string | No | Pod name | Kubernetes pod name |
| pod_ready | boolean | No | Pod ready status | true, false |
| restart_count | integer | No | Container restarts | Non-negative integer |
| notes | string | No | Additional context | Free text |

## Validation Rules Summary

### Required Fields Across All Formats

1. **All formats must include:**
   - Timestamp information (date/timestamp)
   - Event type or deployment status
   - Outcome or health status

2. **Timestamps must:**
   - Use ISO 8601 format (YYYY-MM-DDTHH:MM:SSZ)
   - Include timezone information (Z or ±HH:MM)
   - Be chronologically consistent (end >= start)

3. **Numeric fields must:**
   - Be non-negative integers (counts, revisions)
   - Be non-negative numbers (resource quantities, times)
   - Respect logical bounds (ready <= total)

4. **String fields must:**
   - Be non-empty where required
   - Respect maximum length constraints
   - Use valid Kubernetes naming where applicable

### Data Quality Checks

1. **Consistency:**
   - `readyReplicas <= replicas`
   - `updatedReplicas <= replicas`
   - `successful + failed = total`

2. **Referential Integrity:**
   - All referenced resources (pods, ReplicaSets) should exist
   - Image references should be pullable
   - Secrets referenced should exist

3. **Temporal Integrity:**
   - Creation timestamps <= current timestamps
   - Event dates within analysis window
   - Sequential revisions where applicable

## Usage Guidelines

### When Creating New Deployment Data

1. Always include all required fields
2. Use consistent timestamp formats throughout
3. Validate numeric constraints (counts, bounds)
4. Include meaningful optional fields for better analysis

### When Migrating Data

1. Map source fields to target structure precisely
2. Convert timestamps to ISO 8601 format
3. Normalize enum values to match allowed values
4. Validate all constraints before submission

### When Analyzing Data

1. Check for missing required fields
2. Validate numeric ranges and constraints
3. Verify temporal consistency
4. Cross-reference related objects (pods, ReplicaSets)

## Common Patterns and Anti-Patterns

### Patterns

1. **Consistent naming:** Use Kubernetes naming conventions throughout
2. **Complete timestamps:** Always include timezone information
3. **Detailed outcomes:** Use specific outcome values beyond success/failure
4. **Rich metadata:** Include optional context fields for better analysis

### Anti-Patterns

1. **Missing required fields:** All required fields must be present
2. **Inconsistent timestamps:** Mix date-only and datetime formats
3. **Logical violations:** readyReplicas > replicas
4. **Empty critical values:** Missing deployment names, image references

## Related Documentation

- [pbx-web Deployment Analysis](/home/coding/aide-de-camp/docs/pbx-web-whisper-stt-30-day-deployment-analysis.md)
- [Deployment Comparison Reports](/home/coding/aide-de-camp/comprehensive_comparison_report_pbx_web_vs_whisper_stt_july_2026.md)
- [Kubernetes Deployment API](https://kubernetes.io/docs/concepts/workloads/controllers/deployment/)

## Version History

- **2026-08-06:** Initial documentation based on 30-day deployment data analysis
- Derived from actual pbx-web deployment data collected from ardenone-cluster
- Documented structure supports aide-de-camp analysis and monitoring systems