#!/bin/bash
# Query pbx-web-build workflows from the last 30 days
# Usage: ./query_pbx_workflows.sh [days]
#   days: number of days to look back (default: 30)

DAYS=${1:-30}
KUBECONFIG="/home/coding/.kube/iad-ci.kubeconfig"
NAMESPACE="argo-workflows"
TEMPLATE_NAME="pbx-web-build"

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
    print("Found workflows:")
    print("-" * 80)
    for name, status, created in workflows:
        print(f"{name:50} | {status:10} | {created}")
else:
    print(f"No {template_name} workflows found in the last {days} days")
PYEOF
