# whisper-stt Deployment Data Schema

**Schema Version:** 1.0  
**Last Updated:** 2026-08-06  
**Purpose:** Match pbx-web data structure for consistent comparative analysis

## Overview

This schema defines the standardized data structure for whisper-stt deployment analytics, matching the pbx-web format to enable consistent comparative analysis between services.

## Schema Structure

### 1. metadata (Top-level)

```json
{
  "metadata": {
    "service": "whisper-stt",           // string: Service name
    "namespace": "whisper-stt",         // string: Kubernetes namespace
    "cluster": "ardenone-cluster",     // string: Cluster identifier
    "data_collected_at": "2026-08-06T14:30:00Z",  // string: ISO 8601 timestamp
    "time_period": {
      "start": "2026-07-07T00:00:00Z", // string: Analysis window start
      "end": "2026-08-06T14:30:00Z",   // string: Analysis window end
      "description": "Last 30 days"    // string: Human-readable period
    },
    "managed_by": "ArgoCD",            // string: Deployment management system
    "strategy": "Recreate",             // string: Deployment strategy
    "data_source": "kubectl read-only proxy" // string: Data collection method
  }
}
```

### 2. current_status

```json
{
  "current_status": {
    "deployment_name": "whisper-stt",              // string
    "current_revision": 32,                        // number: Current deployment revision
    "current_image": "ronaldraygun/whisper-stt:1.8.6", // string
    "generation": 353,                             // number: Kubernetes generation
    "replicas": 1,                                 // number: Desired replica count
    "readyReplicas": 1,                           // number: Ready replicas
    "updatedReplicas": 1,                         // number: Updated replicas
    "availableReplicas": 1,                       // number: Available replicas
    "current_pod": "whisper-stt-847fd8d7b9-v2rs5", // string: Current primary pod
    "pod_created_at": "2026-07-12T16:54:57Z",     // string: Pod creation timestamp
    "conditions": [                               // array: Deployment conditions
      {
        "type": "Progressing",                    // string: Condition type
        "status": "True",                         // string: Condition status
        "reason": "NewReplicaSetAvailable",       // string: Human-readable reason
        "message": "ReplicaSet \"whisper-stt-847fd8d7b9\" has progressed.",
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

### 3. deployment_events_last_30_days

```json
{
  "deployment_events_last_30_days": [
    {
      "date": "2026-07-12",                      // string: YYYY-MM-DD
      "timestamp": "2026-07-12T16:54:57Z",        // string: ISO 8601 timestamp
      "event_type": "deployment_rollout",        // string: Event category
      "outcome": "success",                      // string: success|failed|rolled_back|partial
      "revision": 32,                            // number: Deployment revision
      "replicaSet": "whisper-stt-847fd8d7b9",     // string: ReplicaSet name
      "image": "ronaldraygun/whisper-stt:1.8.6",  // string: Container image
      "previous_image": "ronaldraygun/whisper-stt:1.8.4", // string: Previous image
      "pod_name": "whisper-stt-847fd8d7b9-v2rs5", // string: Created pod name
      "pod_ready": true,                         // boolean: Pod readiness
      "restart_count": 0,                        // number: Container restarts
      "rollback_from": null,                    // string|null: Source revision if rollback
      "notes": "fix(whisper-stt): prefer big-CPU nodes via soft nodeAffinity"
    },
    {
      "date": "2026-07-07",
      "timestamp": "2026-07-07T14:22:10Z",
      "event_type": "deployment_rollout",
      "outcome": "success",
      "revision": 31,
      "replicaSet": "whisper-stt-679cb4b6b7",
      "image": "ronaldraygun/whisper-stt:1.8.6",
      "previous_image": "ronaldraygun/whisper-stt:1.8.4",
      "pod_name": "whisper-stt-679cb4b6b7-j5mdk",
      "pod_ready": true,
      "restart_count": 0,
      "rollback_from": null,
      "notes": "feat(whisper-stt): deploy 1.8.6, route /jobs/{id} + /jobs/chunked/* off Google auth"
    }
  ]
}
```

### 4. historical_deployments_beyond_30_days

```json
{
  "historical_deployments_beyond_30_days": [
    {
      "date": "2026-06-24",
      "timestamp": "2026-06-24T18:45:30Z",
      "event_type": "deployment_rollout",
      "outcome": "success",
      "revision": 25,
      "replicaSet": "whisper-stt-5d6f7c8b9a",
      "image": "ronaldraygun/whisper-stt:1.2.5",
      "notes": "chore(whisper-stt): bump image to 1.2.5 (OAuth-removal build)"
    }
  ]
}
```

### 5. deployment_metrics

```json
{
  "deployment_metrics": {
    "total_deployments_last_30_days": 7,        // number: Total deployments
    "successful_deployments": 6,                 // number: Successful deployments
    "failed_deployments": 1,                     // number: Failed deployments
    "deployment_frequency_days": 4.3,            // number: Avg days between deployments
    "unique_images_deployed": 4,                 // number: Unique image versions
    "images_used_last_30_days": [                // array: Image history
      "ronaldraygun/whisper-stt:1.8.6",
      "ronaldraygun/whisper-stt:1.8.4",
      "ronaldraygun/whisper-stt:1.8.2",
      "ronaldraygun/whisper-stt:1.2.5"
    ],
    "current_uptime_days": 24,                   // number: Days since current deployment
    "last_deployment": "2026-07-12T16:54:57Z",   // string: Last deployment timestamp
    "days_since_last_deployment": 24,           // number: Days since last deployment
    "rollbacks_last_30_days": 0,                // number: Rollback count
    "deployment_success_rate": 0.857            // number: Success rate (0-1)
  }
}
```

### 6. pod_health

```json
{
  "pod_health": {
    "current_pod": {
      "name": "whisper-stt-847fd8d7b9-v2rs5",
      "namespace": "whisper-stt",
      "created_at": "2026-07-12T16:54:57Z",
      "node_name": "k3s-agent-server",
      "pod_ip": "10.42.1.123",
      "phase": "Running",                        // string: Pod phase
      "ready": true,                            // boolean: Pod readiness
      "restart_count": 0,                       // number: Total restarts
      "containers": [
        {
          "name": "whisper-stt",
          "ready": true,
          "restart_count": 0,
          "image": "ronaldraygun/whisper-stt:1.8.6",
          "image_id": "docker.io/ronaldraygun/whisper-stt@sha256:abc123...",
          "state": "running",                   // string: Container state
          "started_at": "2026-07-12T16:55:12Z"
        }
      ],
      "conditions": [                           // array: Pod conditions
        {
          "type": "Ready",
          "status": "True",
          "lastTransitionTime": "2026-07-12T16:55:12Z"
        },
        {
          "type": "PodScheduled",
          "status": "True",
          "lastTransitionTime": "2026-07-12T16:54:57Z"
        }
      ],
      "volume_mounts": [                        // array: Volume attachments
        {
          "name": "model-cache",
          "path": "/models",
          "type": "persistentVolumeClaim"
        }
      ]
    },
    "health_indicators": {
      "total_pods": 2,                          // number: Total pods in deployment
      "healthy_pods": 1,                       // number: Healthy pods
      "unhealthy_pods": 1,                     // number: Unhealthy pods
      "failed_pods": 0,                       // number: Failed pods
      "pending_pods": 0,                      // number: Pending pods
      "success_rate": 0.5,                    // number: Pod success rate (0-1)
      "total_restarts": 0,                    // number: Total container restarts
      "avg_pod_age_days": 18,                 // number: Average pod age
      "oldest_pod_age_days": 24,              // number: Oldest pod age
      "pvc_mount_issues": 0                  // number: PVC mounting problems
    }
  }
}
```

### 7. operational_logs_sample

```json
{
  "operational_logs_sample": {
    "recent_errors": [                         // array: Recent error log excerpts
      {
        "timestamp": "2026-07-10T14:23:45Z",
        "pod": "whisper-openai-6885fc878b-jjm5j",
        "container": "whisper-stt",
        "level": "ERROR",
        "message": "Failed to mount PVC: model-cache claim not found"
      }
    ],
    "recent_warnings": [                       // array: Recent warning log excerpts
      {
        "timestamp": "2026-07-08T09:15:22Z",
        "pod": "whisper-stt-847fd8d7b9-v2rs5",
        "container": "whisper-stt",
        "level": "WARNING",
        "message": "High memory usage: 7.2Gi / 8Gi"
      }
    ],
    "startup_events": [                        // array: Pod startup events
      {
        "timestamp": "2026-07-12T16:55:10Z",
        "pod": "whisper-stt-847fd8d7b9-v2rs5",
        "event": "Pulling image ronaldraygun/whisper-stt:1.8.6"
      },
      {
        "timestamp": "2026-07-12T16:55:12Z",
        "pod": "whisper-stt-847fd8d7b9-v2rs5",
        "event": "Container whisper-stt started"
      }
    ]
  }
}
```

### 8. infrastructure_details

```json
{
  "infrastructure_details": {
    "resource_limits": {
      "whisper-stt": {
        "cpu": {
          "request": "1",                       // string: CPU request
          "limit": "8"                         // string: CPU limit
        },
        "memory": {
          "request": "4Gi",                    // string: Memory request
          "limit": "8Gi"                      // string: Memory limit
        }
      }
    },
    "volumes": [                               // array: Volume configurations
      {
        "name": "model-cache",
        "type": "persistentVolumeClaim",
        "claim": "whisper-stt-model-cache",
        "size": "10Gi",
        "storage_class": "sata-large",
        "mount_path": "/models",
        "read_only": false
      },
      {
        "name": "tmp",
        "type": "emptyDir",
        "medium": "Memory",
        "size_limit": "2Gi",
        "mount_path": "/tmp"
      }
    ],
    "environment_variables": {                 // object: Key env vars (no secret values)
      "PYTHONUNBUFFERED": "1",
      "MODEL_CACHE_DIR": "/models",
      "MAX_CONCURRENT_JOBS": "4",
      "LOG_LEVEL": "INFO"
    },
    "secrets_used": [                         // array: Secret references
      {
        "name": "whisper-stt-openai-creds",
        "keys": ["api-key"],
        "type": "ExternalSecret"
      }
    ],
    "liveness_probes": {                      // object: Health check configurations
      "whisper-stt": {
        "enabled": true,
        "path": "/health",
        "port": 8000,
        "initial_delay_seconds": 30,
        "period_seconds": 30,
        "timeout_seconds": 5,
        "failure_threshold": 3
      }
    },
    "readiness_probes": {
      "whisper-stt": {
        "enabled": true,
        "path": "/ready",
        "port": 8000,
        "initial_delay_seconds": 10,
        "period_seconds": 10,
        "timeout_seconds": 3,
        "failure_threshold": 3
      }
    },
    "node_affinity": {                        // object: Node placement rules
      "preferred_during_scheduling": {
        "cpu_preference": "high",             // string: CPU resource preference
        "weight": 100
      }
    }
  }
}
```

### 9. summary

```json
{
  "summary": {
    "overall_health": "degraded",              // string: excellent|good|degraded|poor|critical
    "deployment_stability": "moderate",       // string: stable|moderate|volatile
    "uptime": "24 days continuous",          // string: Human-readable uptime
    "issues_last_30_days": 2,                 // number: Total issues/incidents
    "rollbacks_last_30_days": 0,             // number: Rollback operations
    "deployment_success_rate": "85.7%",       // string: Formatted success rate
    "critical_issues": [                      // array: Critical problems
      {
        "issue": "Pod failure: whisper-openai-6885fc878b-jjm5j",
        "duration": "40+ days",
        "impact": "Reduced capacity, PVC mount errors cascading"
      }
    ],
    "recommendation": "Service operational with degraded reliability. " +
                      "Critical pod failure requires immediate attention. " +
                      "Recommend investigating PVC mounting issues and " +
                      "considering resource reallocation."
  }
}
```

## Field Type Reference

| Field Name | Type | Required? | Description |
|------------|------|-----------|-------------|
| `metadata.service` | string | ✅ | Service identifier |
| `metadata.namespace` | string | ✅ | Kubernetes namespace |
| `current_status.current_revision` | number | ✅ | Deployment revision number |
| `current_status.replicas` | number | ✅ | Desired replica count |
| `deployment_events_last_30_days[].date` | string | ✅ | Event date (YYYY-MM-DD) |
| `deployment_events_last_30_days[].outcome` | string | ✅ | Event outcome enum |
| `deployment_metrics.deployment_success_rate` | number | ✅ | Decimal 0-1 |
| `pod_health.health_indicators.success_rate` | number | ✅ | Pod success rate decimal |
| `infrastructure_details.resource_limits` | object | ✅ | Resource requirements |
| `summary.overall_health` | string | ✅ | Health status enum |

## Type Mappings from pbx-web to whisper-stt

| pbx-web Field | whisper-stt Field | Type Consistency |
|---------------|------------------|------------------|
| `512Mi` memory limit | `8Gi` memory limit | ✅ string (resource notation) |
| `500m` CPU limit | `8` CPU limit | ✅ string (resource notation) |
| `EmptyDir` volumes | `PVC` volumes | ✅ array of volume objects |
| Deployment revision | Deployment revision | ✅ number |
| Pod restart counts | Pod restart counts | ✅ number |
| ISO 8601 timestamps | ISO 8601 timestamps | ✅ string format |

## Data Validation Rules

1. **Timestamp Format**: All timestamps must be ISO 8601 compliant (`YYYY-MM-DDTHH:MM:SSZ`)
2. **Event Outcome**: Must be one of `["success", "failed", "rolled_back", "partial"]`
3. **Health Status**: Must be one of `["excellent", "good", "degraded", "poor", "critical"]`
4. **Deployment Success Rate**: Decimal value between 0.0 and 1.0
5. **Resource Notation**: CPU/memory must use Kubernetes notation (`500m`, `1`, `512Mi`, `8Gi`)

## Comparison Keys for pbx-web Analysis

When comparing whisper-stt to pbx-web, these fields align:

| Comparison Metric | pbx-web Field | whisper-stt Field |
|------------------|---------------|-------------------|
| Deployment Velocity | `deployment_metrics.total_deployments_last_30_days` | Same |
| Success Rate | `deployment_metrics.deployment_success_rate` | Same |
| Resource Usage | `infrastructure_details.resource_limits` | Same |
| Pod Health | `pod_health.health_indicators.success_rate` | Same |
| Uptime | `deployment_metrics.current_uptime_days` | Same |
| Failure Count | `summary.issues_last_30_days` | Same |

## Implementation Notes

1. **Event Type Enum**: `["deployment_rollout", "deployment_rollback", "scaling_change", "config_change", "infrastructure_event"]`
2. **Condition Type Enum**: Matches Kubernetes condition types for deployments and pods
3. **Volume Types**: `["persistentVolumeClaim", "emptyDir", "configMap", "secret"]`
4. **Storage Classes**: Use Rackspace Spot classes: `["sata", "sata-large", "ssd", "ssd-large"]`
5. **Secret Types**: `["Secret", "ExternalSecret", "SealedSecret"]`

---

**Schema Author:** aide-de-camp agent  
**Based on:** pbx-web deployment data structure analysis  
**Validation:** Ready for implementation
