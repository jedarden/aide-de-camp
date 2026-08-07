#!/bin/bash
# Query Argo Workflows by template name and date range
# Usage: ./query_workflow_template.sh <template-name> [days]
#   template-name: WorkflowTemplate name (e.g., pbx-web-build, armor-build)
#   days: number of days to look back (default: 30)

TEMPLATE_NAME=${1}
DAYS=${2:-30}
KUBECONFIG="/home/coding/.kube/iad-ci.kubeconfig"
NAMESPACE="argo-workflows"

if [ -z "$TEMPLATE_NAME" ]; then
    echo "Error: Template name is required"
    echo "Usage: $0 <template-name> [days]"
    echo "Example: $0 pbx-web-build 30"
    exit 1
fi

# Use a temporary file for the JSON output
TMPFILE=$(mktemp)
trap "rm -f $TMPFILE" EXIT

kubectl --kubeconfig="$KUBECONFIG" get workflows -n "$NAMESPACE" -o json > "$TMPFILE" 2>/dev/null

python3 - "$DAYS" "$TEMPLATE_NAME" "$TMPFILE" <<'PYEOF'
import sys
import json
from datetime import datetime, timedelta

days = int(sys.argv[1])
template_name = sys.argv[2]
tmpfile = sys.argv[3]

with open(tmpfile, 'r') as f:
    data = json.load(f)

cutoff_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%dT%H:%M:%SZ')

print(f"Query: {template_name} workflows from last {days} days")
print(f"Cutoff date: {cutoff_date}")
print()

workflows = []
for wf in data['items']:
    template_ref = wf['spec'].get('workflowTemplateRef', {}).get('name', '')
    if template_ref == template_name:
        created = wf['metadata']['creationTimestamp']
        name = wf['metadata']['name']
        status = wf.get('status', {}).get('phase', 'Unknown')
        if created >= cutoff_date:
            workflows.append((name, status, created))

if workflows:
    print(f"Found {len(workflows)} {template_name} workflows:")
    print("-" * 80)
    for name, status, created in workflows:
        print(f"{name:50} | {status:10} | {created}")
else:
    print(f"No {template_name} workflows found in the last {days} days")
PYEOF
