# Base kubectl Query for pbx-web-build Workflow Template

## Query

```bash
kubectl --kubeconfig=/home/coding/.kube/iad-ci.kubeconfig \
  get workflows -n argo-workflows \
  -l workflows.argoproj.io/workflow-template=pbx-web-build \
  -o custom-columns=NAME:.metadata.name,PHASE:.status.phase,CREATED:.metadata.creationTimestamp
```

## Query Components

1. **Namespace**: `-n argo-workflows`
   - Workflows are stored in the `argo-workflows` namespace

2. **Label Selector**: `-l workflows.argoproj.io/workflow-template=pbx-web-build`
   - Filters workflows created from the `pbx-web-build` workflow template
   - The label is automatically applied when a workflow is created via `workflowTemplateRef`

3. **Output Format**: `-o custom-columns=...`
   - `NAME:.metadata.name` - Workflow name (includes auto-generated suffix)
   - `PHASE:.status.phase` - Current status (Running, Succeeded, Failed, Error)
   - `CREATED:.metadata.creationTimestamp` - Creation timestamp

## Expected Output

When pbx-web-build workflows exist:

```
NAME                           PHASE       CREATED
pbx-web-build-abc12            Succeeded   2026-08-05T14:30:00Z
pbx-web-build-def34            Running     2026-08-06T10:15:00Z
pbx-web-build-ghi56            Failed      2026-08-06T12:00:00Z
```

## Alternative Output Formats

### JSON Output (for programmatic access)
```bash
kubectl --kubeconfig=/home/coding/.kube/iad-ci.kubeconfig \
  get workflows -n argo-workflows \
  -l workflows.argoproj.io/workflow-template=pbx-web-build \
  -o json
```

### Wide Output (includes additional fields)
```bash
kubectl --kubeconfig=/home/coding/.kube/iad-ci.kubeconfig \
  get workflows -n argo-workflows \
  -l workflows.argoproj.io/workflow-template=pbx-web-build \
  -o wide
```

## Verification

The workflow template exists in the cluster:
```bash
kubectl --kubeconfig=/home/coding/.kube/iad-ci.kubeconfig \
  get workflowtemplates -n argo-workflows | grep pbx-web
# Output: pbx-web-build                             71d
```

## Notes

- As of 2026-08-06, there are no active pbx-web-build workflow runs in the cluster
- The query will return empty results until a pbx-web-build workflow is manually submitted or triggered
- Workflows are automatically labeled with their template reference when created via `workflowTemplateRef` in the workflow spec
