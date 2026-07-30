# Bead adc-5ry4p: kubectl delete pod

## Task Analysis

The user command "kubectl delete pod" is incomplete and missing critical information:
- **Pod name** (required)
- **Namespace** (optional, defaults to current context's namespace)
- **Cluster/context** (multiple clusters available)

## Available Clusters

Per system configuration, the following clusters are accessible via kubectl-proxy:
- apexalgo-iad: `kubectl --server=http://traefik-apexalgo-iad:8001`
- ardenone-cluster: `kubectl --server=http://traefik-ardenone-cluster:8001`
- ardenone-hub: `kubectl --server=http://traefik-ardenone-hub:8001`
- ardenone-manager: `kubectl --server=http://traefik-ardenone-manager:8001` (or direct kubeconfig)
- rs-manager: `kubectl --server=http://traefik-rs-manager:8001` (or direct kubeconfig)
- ord-devimprint: `kubectl --server=http://kubectl-proxy-ord-devimprint:8001`
- iad-ci: `kubectl --kubeconfig=/home/coding/.kube/iad-ci.kubeconfig`
- iad-kalshi: `kubectl --server=http://kubectl-proxy-iad-kalshi:8001`
- iad-options: `kubectl --server=http://traefik-iad-options:8001`

## Sample Pod Listing (apexalgo-iad)

Current pods visible in apexalgo-iad include:
- agent-observability/mission-control-server (CrashLoopBackOff for 11 days)
- ai-code-battle/ multiple pods (various error states)
- arc-systems/runner-controller pods
- 13-devtron/rollout pod

## Proper Procedure for Pod Deletion

1. **List pods** to identify target:
   ```bash
   kubectl --server=http://<cluster-proxy>:8001 get pods -A
   ```

2. **Confirm pod details** before deletion:
   - Check pod ownership (Deployment/ReplicaSet/StatefulSet)
   - Verify it's not a critical system component
   - Note if it will be recreated automatically

3. **Execute deletion**:
   ```bash
   kubectl --server=http://<cluster-proxy>:8001 delete pod <pod-name> -n <namespace>
   ```

## Completion Status

This bead documents the procedure but cannot execute an actual deletion without:
1. User specification of which pod to delete
2. Cluster and namespace context

The task is complete in terms of documenting the required procedure and available options.
