# pbx-web-build Workflow Query Results

## Task Execution Date
2026-08-06

## Query Executed
```bash
kubectl --kubeconfig=/home/coding/.kube/iad-ci.kubeconfig get workflows -n argo-workflows \
  -l workflows.argoproj.io/workflow-template-ref-name=pbx-web-build \
  --sort-by=.metadata.creationTimestamp
```

## Result
**No resources found in argo-workflows namespace.**

## Verification Steps
1. Checked all workflows in argo-workflows namespace - none with pbx-web prefix
2. Verified workflow template exists:
   ```
   pbx-web-build   71d
   ```
3. Searched for any workflows referencing pbx-web-build template - none found

## Conclusion
The `pbx-web-build` workflow template exists in the iad-ci cluster (created 71 days ago), but **no workflow executions have been created from it**. This means either:
- The template has never been manually triggered
- All past executions have been deleted (TTL/cleanup)
- The template is defined but not actively used

## Impact on Analysis
Without workflow execution data, the following analysis cannot proceed:
- Success/failure rates
- Execution duration trends
- Resource utilization patterns
- Last successful execution timestamp

## Next Steps
To gather pbx-web build data, consider:
1. Manually triggering a pbx-web-build workflow to generate test data
2. Checking if build logs are available from another source (GitHub Actions, container registry)
3. Verifying if pbx-web builds are handled through a different CI/CD pipeline
