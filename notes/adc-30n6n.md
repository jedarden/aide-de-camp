# iad-ci Cluster Access & Workflow Query Syntax Verification

## Task Completion Status
✅ Cluster access verified and query syntax documented

## Cluster Access Verification

### Basic Access Test
```bash
kubectl --kubeconfig=/home/coding/.kube/iad-ci.kubeconfig get workflows -n argo-workflows --sort-by=.metadata.creationTimestamp | head -20
```
**Result:** ✅ Successfully connected and listed workflows.

### Workflow Template Verification
```bash
kubectl --kubeconfig=/home/coding/.kube/iad-ci.kubeconfig get workflowtemplates -n argo-workflows
```
**Result:** Both `pbx-web-build` and `whisper-stt-build` templates exist (71 days old).

## Workflow Query Syntax

### Template-Specific Query
```bash
kubectl --kubeconfig=/home/coding/.kube/iad-ci.kubeconfig get workflows -n argo-workflows -l workflows.argoproj.io/workflow-template=pbx-web-build --sort-by=.metadata.creationTimestamp
```

### Date Range Filtering (30-Day Lookback)

**Note:** kubectl field selectors do NOT support comparison operators (`>=`, `<=`, etc.) on `metadata.creationTimestamp`. The client-side filtering approach is required:

```bash
# Get all workflows, filter by template label, sorted by creation time
kubectl --kubeconfig=/home/coding/.kube/iad-ci.kubeconfig get workflows -n argo-workflows \
  -l workflows.argoproj.io/workflow-template=pbx-web-build \
  --sort-by=.metadata.creationTimestamp \
  -o jsonpath='{range .items[*]}{.metadata.creationTimestamp}{"\t"}{.metadata.name}{"\t"}{.status.phase}{"\n"}{end}' | \
  awk -v cutoff="$(date -d '30 days ago' -u +%Y-%m-%dT%H:%M:%SZ)" '$1 >= cutoff'
```

**Alternative (more portable):**
```bash
# Use jq for JSON filtering
kubectl --kubeconfig=/home/coding/.kube/iad-ci.kubeconfig get workflows -n argo-workflows \
  -l workflows.argoproj.io/workflow-template=pbx-web-build \
  -o json | \
  jq -r --arg cutoff "$(date -d '30 days ago' -u +%Y-%m-%dT%H:%M:%SZ)" \
    '.items[] | select(.metadata.creationTimestamp >= $cutoff) | "\(.metadata.creationTimestamp)\t\(.metadata.name)\t\(.status.phase)"'
```

### Python Script Approach (Recommended for Production)
```python
from datetime import datetime, timedelta
import subprocess
import json

def get_workflows_last_30_days(template_name):
    cutoff = (datetime.utcnow() - timedelta(days=30)).isoformat() + "Z"
    
    result = subprocess.run([
        "kubectl", "--kubeconfig=/home/coding/.kube/iad-ci.kubeconfig",
        "get", "workflows", "-n", "argo-workflows",
        f"-l=workflows.argoproj.io/workflow-template={template_name}",
        "-o=json"
    ], capture_output=True, text=True)
    
    workflows = json.loads(result.stdout)
    filtered = [
        w for w in workflows.get("items", [])
        if w.get("metadata", {}).get("creationTimestamp", "") >= cutoff
    ]
    
    return filtered
```

## Current Status
- **pbx-web-build:** 0 workflow runs in history
- **whisper-stt-build:** 0 workflow runs in history
- Both templates exist and are 71 days old

## Next Steps
To analyze deployment frequency for pbx-web vs whisper-stt, the workflows need to be executed. The query syntax documented above will be used for the 30-day deployment comparison analysis once workflow data exists.
