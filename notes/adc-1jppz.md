# Task adc-1jppz: Test Basic Workflow Query Functionality

## Task
Test that we can query Argo Workflows in the argo-workflows namespace without filters.

## Execution
Command executed:
```bash
kubectl --kubeconfig=/home/coding/.kube/iad-ci.kubeconfig get workflows -n argo-workflows --sort-by=.metadata.creationTimestamp
```

## Results
✅ **SUCCESS** - All acceptance criteria met:

1. **kubectl command successfully lists workflows** - Command executed without error
2. **Returns valid workflow objects** - 15 workflows returned with complete metadata
3. **Output format is readable** - Table format with columns: NAME, STATUS, AGE, MESSAGE

## Sample Output
```
NAME                                   STATUS      AGE     MESSAGE
gribtract-ci-manual-mbntt              Error       10d     workflowtemplates.argoproj.io "gribtract-ci" not found
warden-build-manual-bxbqp              Error       8d      workflowtemplates.argoproj.io "warden-build" not found
needle-ci-x2wx2                        Failed      19h     Max duration limit exceeded
vista-build-7x4jb                      Succeeded   10m     
seam-ci-gn5rh                          Failed      7m43s   main: Error (exit code 1)
```

## Verification
- Workflows are properly sorted by creation timestamp (oldest first)
- Multiple workflow statuses represented (Error, Failed, Succeeded)
- Workflow objects contain expected fields (name, status, age, message)
- kubectl access to iad-ci cluster is confirmed working

## Conclusion
Basic workflow query functionality is working correctly. Ready to proceed with template-filtered queries in subsequent tasks.
