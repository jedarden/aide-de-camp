# Fetch Strand: Monitoring-Config Intent

This document defines the fetch strategy for `intent_type: monitoring-config` queries.

## What We Fetch

For a monitoring-config query (configure ambient monitoring rules), we need:

1. **Component list**: What components exist for this project
2. **Pod status**: Current state of pods
3. **Existing monitoring rules**: What's already being monitored
4. **Recent events**: What's been happening

## Command Matrix

```bash
# List components for project
components list --project ${PROJECT_SLUG}

# Get pod status
kubectl --server=${KUBECONTROL_PROXY} get pods -n ${NAMESPACE} -o json

# Get existing monitoring rules
monitoring rules --project ${PROJECT_SLUG}

# Get recent events
kubectl --server=${KUBECONTROL_PROXY} get events -n ${NAMESPACE} --sort-by='.lastTimestamp'
```

## Parallel Execution

All sources run concurrently.

Timeout per source: 5 seconds

## Result Structure

```json
{
  "components": {
    "status": "success|timeout|error",
    "data": [ /* component objects */ ]
  },
  "pods": {
    "status": "success|timeout|error",
    "data": [ /* pod objects */ ]
  },
  "monitoring_rules": {
    "status": "success|timeout|error",
    "data": {
      "rules": [
        {
          "component": "component-name",
          "check_type": "health|logs|events",
          "interval_seconds": 60,
          "enabled": true
        }
      ],
      "count": 3
    }
  },
  "events": {
    "status": "success|timeout|error",
    "data": [ /* event objects */ ]
  },
  "coverage": {
    "components": true,
    "pods": true,
    "monitoring_rules": true,
    "events": false
  }
}
```

## Monitoring Rule Types

- **Health checks**: Monitor pod/deployment health
- **Log patterns**: Alert on specific log patterns (errors, warnings)
- **Event monitoring**: Alert on specific kubernetes events
- **Custom metrics**: Project-specific metrics

## Context Expansion

For monitoring-config queries, include these context fields if available:

- **Project scope**: Which project to monitor
- **Alert targets**: Where to send alerts (telegram, canvas, etc.)
- **Thresholds**: What thresholds to use for alerts

The fetch layer is deterministic. No LLM calls here — just execute the command matrix and return structured data.
