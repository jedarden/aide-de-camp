# Read-Only Step Types

This document describes the 6 read-only step types in the Action Execution Model. These steps query external systems (Argo Workflows, kubectl proxy, git, bf) without mutating any state.

## Overview

Read-only steps are used for:
- **Status checks** - Verify current system state
- **Health queries** - Check pod/deployment/app health
- **Data retrieval** - Fetch git history, open beads, or cluster state
- **Pre-flight validation** - Ensure conditions before mutating steps

All read-only steps follow a common pattern:
1. Accept configuration from project context
2. Query external API or command
3. Parse and normalize response
4. Return structured StepResult with success/failure status

---

## 1. argocd_sync_status

### Purpose
Poll ArgoCD application status until it reaches `Synced` and `Healthy` state, or timeout. Used to verify GitOps sync completion after `gitops_commit` step.

### Parameters
- `project_slug` (optional) - Project identifier for app name lookup
- `project_cfg.cluster` - Cluster name for logging
- `project_cfg.argocd_app` - ArgoCD application name (defaults to `project_slug`)
- `timeout` - Maximum poll duration (default: 300 seconds / 5 minutes)
- `poll_interval` - Seconds between polls (default: 5 seconds)

### Output Format
```python
{
    "status": "synced",           # "synced", "unknown", or "timeout"
    "sync_status": "Synced",       # ArgoCD sync status
    "health_status": "Healthy",    # ArgoCD health status
    "application": "app-name",    # ArgoCD app name
    "cluster": "rs-manager",       # Cluster name
    "duration_seconds": 12.5       # Time to sync
}
```

### Usage Example
```python
from src.action.steps import execute_argocd_sync_status_step

result = await execute_argocd_sync_status_step(
    intent_id="intent-123",
    session_id="session-456",
    project_slug="pbx-web",
    project_cfg={
        "cluster": "rs-manager",
        "argocd_app": "pbx-web"
    }
)

if result["status"] == "synced":
    print(f"App synced in {result['duration_seconds']}s")
```

### Error Cases
- **ArgoCD API timeout** - Network/proxy connectivity issue
- **App not found** - Returns `status: "unknown"` with `sync_status: "Unknown"`
- **Timeout exceeded** - Returns `status: "timeout"` after 300 seconds
- **ArgoCD base URL not configured** - RuntimeError from missing `config/registry.yaml`

### Implementation
- **Source**: `src/action/steps.py:execute_argocd_sync_status_step()`
- **API**: ArgoCD read-only proxy at `https://argocd-ro-ardenone-manager-ts.ardenone.com:8444`
- **Config**: ArgoCD base URL from `config/registry.yaml`
- **Polling**: Async sleep with 5-second intervals

---

## 2. pod_status

### Purpose
Query pod health in a Kubernetes namespace via kubectl proxy. Returns pod phases, ready counts, and container status for monitoring and troubleshooting.

### Parameters
- `project_cfg.namespace` (required) - Kubernetes namespace
- `project_cfg.cluster` - Cluster name for proxy lookup
- `proxy_url` (optional) - Override auto-detected proxy URL
- `timeout` - HTTP request timeout (default: 10.0 seconds)

### Output Format
```python
{
    "total_pods": 5,
    "phase_counts": {
        "Running": 4,
        "Pending": 1,
        "Failed": 0,
        "Succeeded": 0,
        "Unknown": 0
    },
    "pods": [
        {
            "name": "pod-name-1",
            "phase": "Running",
            "ready": 2,
            "total": 2,
            "ready_ratio": "2/2"
        },
        {
            "name": "pod-name-2",
            "phase": "Pending",
            "ready": 0,
            "total": 1,
            "ready_ratio": "0/1"
        }
    ],
    "namespace": "prod",
    "cluster": "rs-manager"
}
```

### Usage Example
```python
from src.action.steps import execute_pod_status_step

result = await execute_pod_status_step(
    intent_id="intent-123",
    session_id="session-456",
    project_slug="pbx-web",
    project_cfg={
        "namespace": "pbx-web",
        "cluster": "rs-manager"
    }
)

running = result["phase_counts"]["Running"]
print(f"{running}/{result['total_pods']} pods running")
```

### Error Cases
- **Namespace not configured** - ValueError if `project_cfg.namespace` is None
- **Cluster proxy not found** - ValueError if cluster lacks proxy in `config/clusters.yaml`
- **HTTP timeout** - HTTPError from kubectl proxy
- **Malformed pod data** - Exception during parsing

### Implementation
- **Source**: `src/action/steps.py:execute_pod_status_step()`
- **API**: kubectl proxy at `{proxy_url}/api/v1/namespaces/{namespace}/pods`
- **Config**: Cluster proxy from `config/clusters.yaml`
- **Parsing**: Counts container ready status from `containerStatuses[]`

---

## 3. deployment_info

### Purpose
Get Deployment and StatefulSet details from a Kubernetes namespace. Returns replica counts, ready replicas, and updated replicas for monitoring rollout status.

### Parameters
- `project_cfg.namespace` (required) - Kubernetes namespace
- `project_cfg.cluster` - Cluster name for proxy lookup
- `timeout` - HTTP request timeout (default: 10.0 seconds)

### Output Format
```python
{
    "deployments": [
        {
            "name": "my-app",
            "replicas": 3,
            "ready": 3,
            "updated": 3
        }
    ],
    "statefulsets": [
        {
            "name": "my-db",
            "replicas": 1,
            "ready": 1
        }
    ],
    "namespace": "prod",
    "cluster": "rs-manager"
}
```

### Usage Example
```python
from src.action.steps import execute_deployment_info_step

result = await execute_deployment_info_step(
    intent_id="intent-123",
    session_id="session-456",
    project_slug="pbx-web",
    project_cfg={
        "namespace": "pbx-web",
        "cluster": "rs-manager"
    }
)

for deployment in result["deployments"]:
    print(f"{deployment['name']}: {deployment['ready']}/{deployment['replicas']} ready")
```

### Error Cases
- **Namespace not configured** - ValueError if `project_cfg.namespace` is None
- **Cluster proxy not found** - ValueError if cluster lacks proxy
- **HTTP timeout** - HTTPError from kubectl proxy
- **RBAC denied** - HTTPError 403 if proxy lacks permissions

### Implementation
- **Source**: `src/action/steps.py:execute_deployment_info_step()`
- **API**: 
  - Deployments: `{proxy_url}/apis/apps/v1/namespaces/{namespace}/deployments`
  - StatefulSets: `{proxy_url}/apis/apps/v1/namespaces/{namespace}/statefulsets`
- **Config**: Cluster proxy from `config/clusters.yaml`
- **Parsing**: Extracts replica counts from `spec.replicas` and status fields

---

## 4. git_log

### Purpose
Get recent git history from a local repository. Returns last 10 commits for change tracking and audit trails.

### Parameters
- `project_cfg.repo_path` (required) - Local git repository path
- `commit_limit` - Number of commits to return (default: 10)

### Output Format
```python
{
    "commits": [
        {
            "hash": "a1b2c3d",
            "message": "feat: add new feature"
        },
        {
            "hash": "e5f6g7h",
            "message": "fix: resolve bug"
        }
    ],
    "count": 2,
    "repo_path": "/path/to/repo"
}
```

### Usage Example
```python
from src.action.steps import execute_git_log_step

result = await execute_git_log_step(
    intent_id="intent-123",
    session_id="session-456",
    project_slug="pbx-web",
    project_cfg={
        "repo_path": "/home/coding/pbx-web"
    }
)

print(f"Last commit: {result['commits'][0]['message']}")
```

### Error Cases
- **repo_path not configured** - ValueError if `project_cfg.repo_path` is None
- **Repository path does not exist** - RuntimeError if path not on disk
- **git command timeout** - RuntimeError after 10 seconds
- **git log failure** - RuntimeError from stderr

### Implementation
- **Source**: `src/action/steps.py:execute_git_log_step()`
- **Command**: `git -C {repo_path} log -{limit} --oneline`
- **Parsing**: Splits line by space into hash + message
- **Timeout**: 10 seconds on subprocess execution

---

## 5. argocd_apps

### Purpose
Get ArgoCD application status across all apps or filtered by project. Returns sync status, health status, and active operations for monitoring GitOps state.

### Parameters
- `project_slug` (optional) - Filter to specific app name
- `project_cfg.cluster` - Cluster name for logging
- `project_cfg.argocd_app` - ArgoCD app name (defaults to `project_slug`)
- `timeout` - HTTP request timeout (default: 10.0 seconds)

### Output Format
```python
{
    "applications": [
        {
            "name": "pbx-web",
            "namespace": "argocd",
            "sync_status": "Synced",
            "health_status": "Healthy",
            "operation": null
        },
        {
            "name": "another-app",
            "namespace": "argocd",
            "sync_status": "OutOfSync",
            "health_status": "Healthy",
            "operation": {"sync": {"startedAt": "2026-08-06T12:00:00Z"}}
        }
    ],
    "cluster": "rs-manager"
}
```

### Usage Example
```python
from src.action.steps import execute_argocd_apps_step

# Get all apps
result = await execute_argocd_apps_step(
    intent_id="intent-123",
    session_id="session-456",
    project_slug=None,
    project_cfg={"cluster": "rs-manager"}
)

# Filter for single app
result = await execute_argocd_apps_step(
    intent_id="intent-123",
    session_id="session-456",
    project_slug="pbx-web",
    project_cfg={
        "cluster": "rs-manager",
        "argocd_app": "pbx-web"
    }
)

for app in result["applications"]:
    print(f"{app['name']}: {app['sync_status']}, {app['health_status']}")
```

### Error Cases
- **ArgoCD base URL not configured** - RuntimeError from missing `config/registry.yaml`
- **HTTP timeout** - HTTPError from ArgoCD API
- **RBAC denied** - HTTPError 403 if proxy token lacks permissions
- **App not found** - Returns empty `applications` list (no error)

### Implementation
- **Source**: `src/action/steps.py:execute_argocd_apps_step()`
- **API**: `{argocd_base_url}/api/v1/applications`
- **Config**: ArgoCD base URL from `config/registry.yaml`
- **Filtering**: Client-side filter by `app.metadata.name == argocd_app_name`

---

## 6. open_beads

### Purpose
Get open beads (tracking issues) for a project from the bf CLI. Returns bead list for work-in-progress tracking.

### Parameters
- `project_slug` (optional) - Project filter for `bf list --project`
- `project_cfg.repo_path` - Repository path (defaults to `/home/coding/aide-de-camp`)
- `timeout` - Command timeout (default: 10 seconds)

### Output Format
```python
{
    "open_beads": [
        {
            "id": "adc-mis2c",
            "title": "Document read-only step types",
            "status": "open",
            "type": "documentation"
        }
    ],
    "count": 1,
    "repo_path": "/home/coding/aide-de-camp",
    "project_filter": "adc"
}
```

### Usage Example
```python
from src.action.steps import execute_open_beads_step

result = await execute_open_beads_step(
    intent_id="intent-123",
    session_id="session-456",
    project_slug="adc",
    project_cfg={
        "repo_path": "/home/coding/aide-de-camp"
    }
)

print(f"{result['count']} open beads for project")
```

### Error Cases
- **bf command not found** - RuntimeError if `bf` not in PATH
- **bf list timeout** - RuntimeError after 10 seconds
- **JSON parse error** - Returns empty `open_beads` list (no error)
- **Repository path does not exist** - RuntimeError if path not on disk

### Implementation
- **Source**: `src/action/steps.py:execute_open_beads_step()`
- **Command**: `bf list --status open --format json --project {project_slug}`
- **Working Directory**: `cwd=repo_path`
- **Parsing**: JSON parse of `bf list` output, falls back to empty list

---

## Common Patterns

### StepResult Structure
All read-only steps return a dict (not the `StepResult` class from `read.py`) with:
- `success: bool` - Implicit from absence of raised exception
- `data: dict` - Structured result data
- Error cases raise `RuntimeError` or `ValueError`

### Configuration Sources
- **Cluster proxy URLs**: `config/clusters.yaml` → `clusters.{cluster}.proxy`
- **ArgoCD base URL**: `config/registry.yaml` → `argocd.base_url`
- **Project context**: `project_cfg` dict from action intent metadata

### Timeouts
- **HTTP requests**: 10 seconds default (httpx.AsyncClient)
- **kubectl/git commands**: 10-15 seconds (subprocess timeout)
- **ArgoCD polling**: 300 seconds total with 5-second intervals

### Error Handling
All read-only steps follow consistent error patterns:
1. **Missing required config** - ValueError (e.g., no namespace)
2. **External API timeout** - HTTPError or RuntimeError
3. **Command timeout** - RuntimeError with subprocess context
4. **Malformed response** - RuntimeError or ValueError during parsing

---

## See Also

- [Action Execution Steps](action-execution-steps.md) - Write/mutating step types
- [Action Execution Data Structures](action-execution-data-structures.md) - ExecutionContext, StepResult models
- `src/action/steps.py` - All step implementations
- `src/action/steps/read.py` - CIStatusStep, PodStatusStep, ImageTagStep classes
