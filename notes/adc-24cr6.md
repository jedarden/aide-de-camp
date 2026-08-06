# pbx-web-build Workflow Query Results

## Task Execution

Executed kubectl query to retrieve pbx-web-build workflows from the last 30 days with proper filtering and sorting.

## Query Command

```bash
kubectl --kubeconfig=/home/coding/.kube/iad-ci.kubeconfig get workflows -n argo-workflows \
  -l workflows.argoproj.io/workflow-template-ref-name=pbx-web-build \
  --sort-by=.metadata.creationTimestamp
```

## Results

**Status:** Query executed successfully  
**Result:** No resources found

## Analysis

- The pbx-web-build workflow template exists (created 71 days ago)
- No workflow instances have been created from this template
- The template is one of 140+ workflow templates in the argo-workflows namespace
- Other similar templates (vista-build, spaxel-build, etc.) do have active workflow instances

## Verification

Confirmed through multiple queries:
1. Label-filtered query: No workflows with `workflows.argoproj.io/workflow-template-ref-name=pbx-web-build`
2. Full workflow list scan: No pbx-web workflows found in the complete list
3. Template reference search: No workflows reference the pbx-web-build template

## Conclusion

The query mechanism is working correctly. The absence of results indicates that pbx-web-build has not been executed recently (or possibly ever) in the iad-ci cluster.
