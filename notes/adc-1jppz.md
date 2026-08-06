# Test Basic Workflow Query Functionality

## Task
Test that we can query Argo Workflows in the argo-workflows namespace without filters.

## Command Executed
```bash
kubectl --kubeconfig=/home/coding/.kube/iad-ci.kubeconfig get workflows -n argo-workflows --sort-by=.metadata.creationTimestamp
```

## Results
✅ **SUCCESS** - All acceptance criteria met:

1. **Authentication**: Successfully authenticated to iad-ci cluster using kubeconfig at `/home/coding/.kube/iad-ci.kubeconfig`
2. **Query Execution**: Command successfully listed workflows in argo-workflows namespace
3. **Valid Data**: Returned 11 workflow objects with various statuses (Error, Failed, Running)
4. **Readable Format**: Output in table format with columns: NAME, STATUS, AGE, MESSAGE

## Sample Output
```
NAME                                   STATUS    AGE     MESSAGE
gribtract-ci-manual-mbntt              Error     10d     workflowtemplates.argoproj.io "gribtract-ci" not found
warden-build-manual-bxbqp              Error     8d      workflowtemplates.argoproj.io "warden-build" not found
needle-ci-x2wx2                        Failed    18h     Max duration limit exceeded
vista-build-7x4jb                      Running   48s
```

## Workflow Statuses Observed
- **Error**: Template not found errors for deleted workflow templates
- **Failed**: Duration limit exceeded or build errors
- **Running**: Active workflows currently executing

## Conclusion
Basic kubectl workflow query functionality is confirmed working. This validates the foundation for adding more complex queries with workflow template filters in future tasks.

## Dependencies Met
Depends on: needle-xxx (Verify kubectl access to iad-ci cluster) - ✅ Confirmed working
