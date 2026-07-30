# NEEDLE Task adc-q6oxj: kubectl delete pod

## Task
Execute a `kubectl delete pod` command by identifying the correct target pod based on cluster state.

## Execution

### Discovery
Scanned the `iad-ci` cluster for problematic pods using:
```bash
kubectl --kubeconfig=/home/coding/.kube/iad-ci.kubeconfig get pods --all-namespaces | grep -E "(CrashLoopBackOff|Error|ImagePull|Failed|Evicted|Unknown)"
```

### Target Selection
Identified `docker-push-helper` in the `argo-workflows` namespace as the deletion target:
- **Status**: Failed
- **Age**: 9 days (since 2026-07-14)
- **Container states**: dind (Error), docker-cli (Completed)
- **Reason**: Workflow helper pod stuck in failed state, should have been auto-cleaned

### Execution
```bash
kubectl --kubeconfig=/home/coding/.kube/iad-ci.kubeconfig delete pod docker-push-helper -n argo-workflows
```

Result: `pod "docker-push-helper" deleted`

### Verification
Confirmed pod is no longer present in the cluster:
```bash
kubectl --kubeconfig=/home/coding/.kube/iad-ci.kubeconfig get pod docker-push-helper -n argo-workflows
# Output: Pod successfully deleted and not found
```

## Success Criteria
- ✅ Target pod successfully deleted from cluster
- ✅ Deletion status verified (pod removed from cluster)
- ✅ Target was unambiguous (failed workflow helper pod)

## Date
2026-07-24
