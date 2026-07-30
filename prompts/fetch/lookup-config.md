# Fetch Strand: Lookup Intent - Config Kind

This document defines the fetch strategy for `intent_type: lookup` with `lookup_kind: config`.

## What We Fetch

For a config lookup query, we need configuration and deployment state:

1. **ArgoCD app state**: Current sync status, health, and deployment info
2. **Kubernetes resources**: Deployments, services, configmaps, secrets (metadata only)
3. **Pod status**: Current pod state for running workloads
4. **Git status**: Recent commits to declarative-config (if applicable)

## Command Matrix

```bash
# ArgoCD application status
curl -s ${ARGOCD_PROXY}/api/v1/applications/${APP_NAME}

# Deployment resources
kubectl --server=${KUBECONTROL_PROXY} get deployment -n ${NAMESPACE} -o json

# Service resources
kubectl --server=${KUBECONTROL_PROXY} get service -n ${NAMESPACE} -o json

# ConfigMap metadata
kubectl --server=${KUBECONTROL_PROXY} get configmap -n ${NAMESPACE} -o json

# Pod status (for workload state)
kubectl --server=${KUBECONTROL_PROXY} get pods -n ${NAMESPACE} -o json

# Git log for declarative-config (if repo_path available)
git -C ${REPO_PATH} log -10 --oneline --pretty=format:'%h|%s|%an|%ar'
```

## Parallel Execution

All fetch sources run concurrently.

Timeout per source:
- ArgoCD app: 5 seconds
- Deployments: 5 seconds
- Services: 3 seconds
- ConfigMaps: 3 seconds
- Pods: 5 seconds
- Git log: 3 seconds

## Result Structure

```json
{
  "argocd_app": {
    "status": "success|timeout|error",
    "data": {
      "name": "app-name",
      "sync": {
        "status": "Synced|OutOfSync",
        "revision": "main@sha256:..."
      },
      "health": {
        "status": "Healthy|Degraded",
        "message": "..."
      },
      "operation": {
        "state": "...",
        "initiatedAt": "...",
        "finishedAt": "..."
      }
    }
  },
  "deployments": {
    "status": "success|timeout|error",
    "data": [ /* deployment objects */ ]
  },
  "services": {
    "status": "success|timeout|error",
    "data": [ /* service objects */ ]
  },
  "configmaps": {
    "status": "success|timeout|error",
    "data": [ /* configmap objects */ ]
  },
  "pods": {
    "status": "success|timeout|error",
    "data": [ /* pod objects */ ]
  },
  "git_log": {
    "status": "success|timeout|error",
    "data": [ /* commit entries */ ]
  },
  "coverage": {
    "argocd_app": true,
    "deployments": true,
    "services": true,
    "configmaps": true,
    "pods": true,
    "git_log": true
  }
}
```

## Context Expansion

For config lookup queries, include these context fields if available:

- **App context**: Which ArgoCD application, namespace
- **Resource type**: Which specific resources (deployment, service, configmap)
- **Time context**: "current state" vs historical
- **Scope**: Cluster-wide vs namespace-specific

The fetch layer is deterministic. No LLM calls here — just execute the command matrix and return structured data.
