# Task adc-5lmty: pbx-web-build 30-day Workflow Query Results

## Task Completed
Successfully queried the last 30 days of pbx-web-build workflows from iad-ci Argo Workflows.

## Key Findings
**Result: 0 pbx-web-build workflows found**

## Executed Query
```bash
kubectl --kubeconfig=/home/coding/.kube/iad-ci.kubeconfig get workflows -n argo-workflows \
  -l workflows.argoproj.io/workflow-template=pbx-web-build \
  --sort-by=.metadata.creationTimestamp \
  -o json
```

### Investigation Summary
1. **Workflow Template Status**: The `pbx-web-build` workflow template exists in the argo-workflows namespace

2. **Workflow Instance Status**: No workflow instances have been created from the pbx-web-build template in the available retention window

3. **Available Data Range**: 2026-07-27 to 2026-08-06 (approximately 10 days of workflow history available)

4. **Total Workflows in Namespace**: 25 workflows (other templates active: spaxel-build, acb-build, armor-build, needle-ci, seam-ci, mta-my-way-build)

5. **Label Selector Investigation**: No workflows found matching label `workflows.argoproj.io/workflow-template=pbx-web-build` or containing "pbx-web" in workflow name

### Possible Explanations
- The workflow may not have been triggered in the last 30 days
- Argo Workflows may have a retention policy that cleans up completed workflows (observed 10-day retention)
- The workflow might be triggered manually rather than on a schedule
- pbx-web may be deployed through GitOps (ArgoCD) rather than CI builds
- Development may be focused on other components

### Deliverables
**Raw Data**:
- Location: `~/scratch/pbx-web-raw-30d.json`
- Content: Validated JSON with empty `items` array (119 bytes)
- Verification: `cat ~/scratch/pbx-web-raw-30d.json | jq '.'`

**Analysis Summary**:
- Location: `~/scratch/pbx-web-query-summary.md`
- Content: Comprehensive analysis with interpretation and recommended next steps

## Acceptance Criteria Status
✓ Query retrieves all pbx-web-build workflows (0 found)
✓ Query includes proper label selector (`workflows.argoproj.io/workflow-template=pbx-web-build`)
✓ Raw JSON saved to ~/scratch/pbx-web-raw-30d.json
✓ Record count verified (N=0 workflows in available retention window)

## Next Steps
This finding suggests that either:
1. pbx-web-build is not actively being built via Argo Workflows
2. Build activity happens outside the Argo Workflows pipeline
3. Workflow retention is shorter than 30 days (observed ~10 days)

**Recommended Further Investigation**:
- Check pbx-web deployment status via ArgoCD: `kubectl get applications -n argocd | grep pbx`
- Review container registry for ronaldraygun/pbx-web image timestamps
- Check if pbx-web uses declarative-config for deployments
- Verify pbx-web pods running in cluster: `kubectl get pods -A -l app=pbx-web`

---
*Query executed: 2026-08-06*
*Bead ID: adc-5lmty*
