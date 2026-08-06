# Task: Retrieve whisper-stt deployment logs for last 30 days

## Task ID: adc-1y4g8
## Date: 2026-08-06

## Findings

### Summary
**No whisper-stt deployment logs found in Argo Workflows for the last 30 days.**

### Investigation Details

#### Workflow Template Status
- **Template name:** `whisper-stt-build`
- **Template exists:** ✓ Yes
- **Template created:** 2026-05-27T02:26:47Z
- **TTL strategy:** None configured at template level

#### Workflow Execution History
Searched for workflows with:
- Template reference: `whisper-stt-build`
- Name pattern: `*whisper*`
- Timeframe: 2026-07-07 to 2026-08-06 (last 30 days)

**Result:** Zero workflows found matching `whisper-stt-build`.

#### System Workflow Retention Analysis
Current workflow history in Argo Workflows (`iad-ci` cluster):
- **Total workflows in system:** ~16
- **Oldest workflow:** 2026-07-27
- **Newest workflow:** 2026-08-06
- **Retention period:** ~10 days

Recent workflows observed:
- `armor-build-*` (armor-build template)
- `seam-ci-*` (seam-ci template)
- `needle-ci-*` (needle-ci template)
- `b2-usage-exporter-build-manual-*` (b2-usage-exporter-build template)
- `warden-build-manual-*` (warden-build template)
- `gribtract-ci-manual-*` (gribtract-ci template)

### Conclusions

1. **No deployment activity:** The `whisper-stt-build` workflow template exists but has not been executed in the available workflow history.

2. **Limited retention:** Even if whisper-stt deployments had occurred, Argo Workflows retains only ~10 days of workflow history, which is insufficient to provide a full 30-day deployment history.

3. **Template availability:** The template is available for use (created 2026-05-27) but appears to be dormant or unused.

### Alternative Data Sources

For obtaining 30-day deployment history, consider:
- **Git repository history:** Check `jedarden/nixos-asterisk` for deployment commits or tag history
- **Image registry:** Query container registry for `ronaldraygun/whisper-stt` image build/push timestamps
- **Cluster deployment logs:** Check target cluster for deployment events
- **ArgoCD application history:** If deployed via GitOps, check ArgoCD application sync history

### Recommendation

Since no CI workflow executions exist for whisper-stt, the deployment logs are not available through Argo Workflows. To obtain 30-day deployment history, query the container registry or git history instead.

---

## Commands Executed

```bash
# Check for whisper-stt workflows by template reference
kubectl --kubeconfig=/home/coding/.kube/iad-ci.kubeconfig get workflows -n argo-workflows \
  -l workflows.argoproj.io/workflow-template-ref-name=whisper-stt-build \
  --sort-by=.metadata.creationTimestamp -o json

# Check workflow template details
kubectl --kubeconfig=/home/coding/.kube/iad-ci.kubeconfig get workflowtemplate whisper-stt-build \
  -n argo-workflows -o json

# List all workflow templates
kubectl --kubeconfig=/home/coding/.kube/iad-ci.kubeconfig get workflowtemplates \
  -n argo-workflows -o json

# Get recent workflows for retention analysis
kubectl --kubeconfig=/home/coding/.kube/iad-ci.kubeconfig get workflows -n argo-workflows \
  --sort-by=.metadata.creationTimestamp -o json
```
