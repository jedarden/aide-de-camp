# Fetch Strand: Action Intent

This document defines the fetch strategy for `intent_type: action` commands.

## What We Fetch

For an action intent, we need to:
1. **Validate preconditions** (is action allowed?)
2. **Check current state** (what are we about to change?)
3. **Identify side effects** (what else will be impacted?)

## Command Matrix

### Kubernetes Actions

```bash
# Pre-action state capture
kubectl --server=${KUBECONTROL_PROXY} get pods -n ${NAMESPACE} -o json
kubectl --server=${KUBECONTROL_PROXY} get deployment ${DEPLOYMENT} -n ${NAMESPACE} -o json

# Action execution (via NEEDLE task bead for safety)
# Actions are NOT executed directly. Create a task bead with:
# br create --type action --project ${PROJECT_SLUG} "${ACTION_COMMAND}"
```

### Git Actions

```bash
# Current state
git -C ${REPO_PATH} status
git -C ${REPO_PATH} log -1 --oneline

# Action (via NEEDLE task bead)
# Never execute git commands directly. Create bead for approval workflow.
```

### Deployment Actions

```bash
# Check current deploy state
kubectl --server=${KUBECONTROL_PROXY} get deployment ${DEPLOYMENT} -n ${NAMESPACE} -o json
curl -s https://argocd-ro-ardenone-manager-ts.ardenone.com:8444/api/v1/applications/${APP_NAME}

# CI workflow status
kubectl --kubeconfig=${KUBECONFIG} get workflows -n argo-workflows -l app=${APP_NAME} -o json
```

## Safety Model

**All mutable actions are routed through NEEDLE task beads**, never executed directly by the fetch strand.

This ensures:
- Audit trail (bead captures who/what/when)
- Approval workflow (bead closes only after user confirmation)
- Reversibility (bead body includes rollback instructions)

## Action Classification

### Auto-Approve Actions (Low Risk)

These can be auto-approved via exception rules:
- `kubectl logs` (read-only)
- `kubectl describe` (read-only)
- Git status checks (read-only)

### Manual Approval Required (High Risk)

These always go through bead approval workflow:
- `kubectl delete`
- `kubectl apply` with production changes
- Git push to main
- Deployment promotion

## Result Structure

```json
{
  "pre_state": {
    "pods": [ /* current pod state */ ],
    "deployment": { /* current deployment spec */ ],
    "argocd": { /* current sync state */ ]
  },
  "action_spec": {
    "type": "kubectl|git|workflow",
    "command": "the command to execute",
    "risk_level": "low|medium|high",
    "rollback": "how to undo this"
  },
  "impact_analysis": {
    "affected_resources": [ /* what will change */ ],
    "side_effects": [ /* what else is impacted */ ],
    "dependencies": [ /* other systems that care */ ]
  },
  "approval_required": true
}
```

## Escalation to Task Bead

For actions requiring approval, the fetch strand returns a result that prompts escalation:

```json
{
  "escalate": {
    "to_bead": true,
    "bead_spec": {
      "type": "action",
      "project": PROJECT_SLUG,
      "command": ACTION_COMMAND,
      "preconditions": PRE_STATE,
      "risk_level": RISK_LEVEL
    }
  }
}
```

The escalate strand creates the bead and returns a pending card.

## Context Expansion

For action queries, include:
- **User identity**: Who is requesting this action
- **Project context**: Which project/environment
- **Risk assessment**: Based on action type and target environment

Actions are irreversible. The fetch layer's job is to capture all context needed for safe approval.
