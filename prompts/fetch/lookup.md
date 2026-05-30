# Fetch Strand: Lookup Intent

This document defines the fetch strategy for `intent_type: lookup` queries.

## What We Fetch

For a lookup query, we need to find specific information:

1. **Logs**: Recent log output from pods/services
2. **Events**: Kubernetes events for the namespace
3. **Pod status**: Current state of pods
4. **Config data**: Configuration files, env vars (if applicable)

## Command Matrix

```bash
# Pod logs (tail last 100 lines)
kubectl --server=${KUBECONTROL_PROXY} logs -n ${NAMESPACE} ${POD_NAME} --tail=100

# Events for namespace
kubectl --server=${KUBECONTROL_PROXY} get events -n ${NAMESPACE} --sort-by='.lastTimestamp'

# Pod status
kubectl --server=${KUBECONTROL_PROXY} get pods -n ${NAMESPACE} -o json
```

## Parallel Execution

All fetch sources run concurrently. Logs may take longer; stream them if possible.

Timeout per source:
- Logs: 10 seconds (can be slow for large pods)
- Events: 5 seconds
- Pod status: 5 seconds

## Result Structure

```json
{
  "logs": {
    "status": "success|timeout|error",
    "data": {
      "pod": "pod-name",
      "logs": "log output here",
      "line_count": 100
    }
  },
  "events": {
    "status": "success|timeout|error",
    "data": [ /* event objects */ ]
  },
  "pods": {
    "status": "success|timeout|error",
    "data": [ /* pod objects */ ]
  },
  "coverage": {
    "logs": true,
    "events": true,
    "pods": true
  }
}
```

## Streaming Support

For logs, prefer streaming the response line-by-line as they arrive from kubectl.
This makes the lookup feel faster even when logs are large.

## Context Expansion

For lookup queries, include these context fields if available:

- **Pod context**: Which pod, namespace, container
- **Time context**: Recent timestamp from user query ("last hour", "since 2pm")
- **Filter context**: Error-only, warnings, specific keywords

The fetch layer is deterministic. No LLM calls here — just execute the command matrix and return structured data.
