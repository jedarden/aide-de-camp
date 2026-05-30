# Fetch Strand: Status Intent

This document defines the fetch strategy for `intent_type: status` queries.

## What We Fetch

For a status query, we want the current operational state of the target:

1. **Pod status** (if k8s project): Running pods, phases, restarts
2. **ArgoCD sync status** (if applicable): Sync health, last sync time
3. **Git log** (if repo): Recent commits, current branch
4. **Bead list** (if project uses NEEDLE): Open beads for this project
5. **CI workflow status** (if applicable): Recent CI runs, current build state

## Command Matrix

### Kubernetes Projects

```bash
# Pod status
kubectl --server=${KUBECONTROL_PROXY} get pods -n ${NAMESPACE} -o json

# ArgoCD application status (via read-only proxy)
curl -s https://argocd-ro-ardenone-manager-ts.ardenone.com:8444/api/v1/applications/${APP_NAME}

# CI workflow status (if applicable)
kubectl --kubeconfig=${KUBECONFIG} get workflows -n argo-workflows -l project=${PROJECT_SLUG} -o json
```

### Git Repositories

```bash
# Recent commits
git -C ${REPO_PATH} log -10 --oneline --pretty=format:'{"hash":"%h","message":"%s","author":"%an","date":"%ar"}'

# Current branch
git -C ${REPO_PATH} branch --show-current

# Uncommitted changes
git -C ${REPO_PATH} status --short
```

### NEEDLE Projects

```bash
# Open beads for project
br list --project ${PROJECT_SLUG} --status open --output json
```

## Parallel Execution

All fetch sources run concurrently. Partial results are passed to the Synthesize strand as they arrive.

Timeout per source: 5 seconds

## Result Structure

```json
{
  "pods": {
    "status": "success|timeout|error",
    "data": [ /* pod objects */ ],
    "cached_at": null
  },
  "argocd": {
    "status": "success|timeout|error",
    "data": { /* application state */ },
    "cached_at": "timestamp if cache was used"
  },
  "git": {
    "status": "success|timeout|error",
    "data": {
      "commits": [ /* commit objects */ ],
      "branch": "current-branch",
      "uncommitted": [ /* changed files */ ]
    }
  },
  "beads": {
    "status": "success|timeout|error",
    "data": [ /* bead objects */ ]
  },
  "coverage": {
    "pods": true,
    "argocd": false,
    "git": true,
    "beads": true
  }
}
```

## Fallback Behavior

- **Source timeout**: Mark as timeout, continue with other sources
- **All sources timeout**: Return error with caveat that infrastructure may be unreachable
- **Partial success**: Return what we have with coverage fields

## Context Expansion

For status queries, include these context fields if available:

- **Cluster context**: Which cluster this project runs on
- **Namespace context**: Which namespace
- **Repo path**: Local path to git repo
- **Project slug**: For bead lookup

The fetch layer is deterministic. No LLM calls here — just execute the command matrix and return structured data.
