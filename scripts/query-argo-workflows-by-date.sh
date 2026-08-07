#!/bin/bash
# query-argo-workflows-by-date.sh
# Query Argo Workflows filtered by workflow template and creation date
# Usage: ./query-argo-workflows-by-date.sh <template-name> <days-ago>

set -euo pipefail

TEMPLATE_NAME="${1:-pbx-web-build}"
DAYS_AGO="${2:-30}"
KUBECONFIG="${KUBECONFIG:-/home/coding/.kube/iad-ci.kubeconfig}"
NAMESPACE="${NAMESPACE:-argo-workflows}"

# Calculate date threshold
SINCE_DATE=$(date -u -d "${DAYS_AGO} days ago" +"%Y-%m-%dT%H:%M:%SZ")

echo "Querying workflows for template: ${TEMPLATE_NAME}"
echo "Date range: ${SINCE_DATE} to present"
echo "Namespace: ${NAMESPACE}"
echo "---"

# Execute query
kubectl --kubeconfig="${KUBECONFIG}" \
  get workflows -n "${NAMESPACE}" \
  -l "workflows.argoproj.io/workflow-template=${TEMPLATE_NAME}" \
  -o json | \
jq --arg since "$SINCE_DATE" \
  '.items | map(select((.metadata.creationTimestamp // "") >= $since)) |
   {count: (. | length), workflows: [.[] | {name: .metadata.name, created: .metadata.creationTimestamp, phase: .status.phase}]}'

echo "---"
echo "Query complete."
