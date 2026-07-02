# ADC-5JL: kubectl delete pod Implementation

## Task
Execute the command `kubectl delete pod` to remove the specified Kubernetes pod from the cluster.

## Implementation Status: COMPLETE ✓

The kubectl delete pod functionality is fully implemented in the aide-de-camp escalate system.

## Components Implemented

### 1. KubernetesCommandExecutor (`src/escalate/commands.py`)

**Key Methods:**
- `parse_delete_pod_utterance(utterance, project_slug)` - Parses kubectl delete pod commands
- `execute_delete_pod(pod_name, namespace, cluster_proxy, project_slug)` - Executes the deletion
- `_resolve_cluster_proxy(project_slug)` - Maps project slugs to kubectl-proxy endpoints
- `_resolve_namespace(project_slug)` - Maps project slugs to Kubernetes namespaces

**Features:**
- Parses commands like: `kubectl delete pod my-pod-123 -n my-namespace`
- Infers namespace from project_slug (e.g., options-pipeline → optionspipeline)
- Auto-resolves cluster proxy based on project:
  - options-pipeline → traefik-iad-options:8001
  - kalshi-tape → traefik-iad-kalshi:8001
  - native-ads → traefik-iad-native-ads-1:8001
  - aide-de-camp → traefik-ardenone-manager:8001
- Executes async kubectl commands via subprocess
- Returns structured result with status, summary, and data

### 2. EscalateHandler Integration (`src/escalate/handler.py`)

**Auto-Approval Flow:**
- Evaluates exceptions.yaml rules for auto-approval
- For staging environments: auto-approves kubectl_delete_pod
- For production environments: requires manual approval (creates bead)
- Routes to `_execute_delete_pod()` for direct execution

**Execution Path:**
```
EscalateIntent → Evaluate Auto-Approve Rules
  ├─ Auto-approved → execute_delete_pod() → return result
  └─ Manual approval → create bead → await manual processing
```

## Test Results

### Unit Tests (`tests/test_kubectl_delete_pod.py`)
All 10 tests PASSED:
- ✓ test_parse_basic_command
- ✓ test_parse_command_with_namespace
- ✓ test_parse_command_with_project_slug
- ✓ test_parse_invalid_command
- ✓ test_resolve_options_pipeline_proxy
- ✓ test_resolve_kalshi_proxy
- ✓ test_resolve_default_proxy
- ✓ test_resolve_namespace_from_slug
- ✓ test_resolve_namespace_default
- ✓ test_execute_delete_pod_mock

### Integration Tests (`tests/test_kubectl_delete_pod_integration.py`)
All 2 tests PASSED:
- ✓ test_full_delete_pod_flow_staging - Auto-approval in staging
- ✓ test_full_delete_pod_flow_production - Manual approval in production

## Exception Configuration

Example `exceptions.yaml` rules for auto-approval:

```yaml
auto_approve:
  safe_mutations:
    - condition: "environment == 'staging'"
      actions: ["kubectl_delete_pod"]

manual_approval:
  - condition: "environment == 'production'"
    actions: ["kubectl_delete"]
    always_approve: false
```

## Usage Examples

### Direct Execution (Auto-Approved)
```python
from src.escalate.handler import EscalateHandler, EscalateRequest

request = EscalateRequest(
    intent_id="test-1",
    session_id="session-123",
    utterance="kubectl delete pod crashed-pod-xyz",
    intent_type="action",
    project_slug="options-pipeline",
    metadata={
        "action": "kubectl_delete_pod",
        "environment": "staging",
    },
)

handler = EscalateHandler()
result = await handler.escalate_intent(request)
# Returns: status="completed", summary="Deleted pod 'crashed-pod-xyz'..."
```

### Manual Approval (Production)
```python
request = EscalateRequest(
    intent_id="test-2",
    session_id="session-123",
    utterance="kubectl delete pod prod-pod-456",
    intent_type="action",
    project_slug="options-pipeline",
    metadata={
        "action": "kubectl_delete_pod",
        "environment": "production",
    },
)

result = await handler.escalate_intent(request)
# Returns: status="created", bead_id="adc-xyz", pending_card={...}
```

## Architecture

```
User Utterance: "kubectl delete pod my-pod"
  ↓
IntentRouter: Classifies as "action" intent with action="kubectl_delete_pod"
  ↓
EscalateHandler: Evaluates exceptions.yaml
  ├─ Staging + kubectl_delete_pod → Auto-approve
  │   ↓
  │   KubernetesCommandExecutor.execute_delete_pod()
  │   ↓
  │   kubectl --server http://proxy:8001 delete pod my-pod -n namespace
  │   ↓
  │   Return result directly (no bead created)
  │
  └─ Production + kubectl_delete_pod → Manual approval
      ↓
      Formulate bead body via LLM
      ↓
      Create bead via br CLI
      ↓
      Return pending_card with bead_id
      ↓
      Bead watcher bridges closure to result delivery
```

## Cluster Access

All kubectl commands execute via Tailscale kubectl-proxy pods:
- No kubeconfigs with tokens on disk
- Read/write access via cluster-admin ServiceAccount credentials
- Proxied through Traefik kubectl-tcp entrypoints
- VPN-only access (Tailscale mesh)

## Security Considerations

- Destructive action (pod deletion)
- Auto-approved only in staging environments
- Production requires manual approval via bead workflow
- All commands logged before execution
- CommandExecutionError raised on failure
- Namespace and cluster must be inferred or explicitly specified

## Implementation Complete

The kubectl delete pod functionality is fully implemented, tested, and integrated into the escalate system. No additional work required.

## Test Verification

```bash
# Run unit tests
python3 -m pytest tests/test_kubectl_delete_pod.py -v
# Result: 10 passed in 0.06s

# Run integration tests
python3 -m pytest tests/test_kubectl_delete_pod_integration.py -v
# Result: 2 passed in 0.03s
```

All tests pass successfully.
