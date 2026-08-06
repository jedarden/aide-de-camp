#!/bin/bash
# pbx-web-build 30-day workflow query
# Filters workflows to last 30 days using jq post-processing

set -e

KUBECONFIG="/home/coding/.kube/iad-ci.kubeconfig"
NAMESPACE="argo-workflows"
WORKFLOW_TEMPLATE="pbx-web-build"
OUTPUT_FILE="$HOME/scratch/pbx-web-filtered-test.json"

# Calculate 30 days ago in ISO 8601 format (UTC)
CUTOFF_DATE=$(date -d "30 days ago" -u +%Y-%m-%dT%H:%M:%SZ)

echo "=== pbx-web-build 30-Day Workflow Query ==="
echo "Cutoff Date: $CUTOFF_DATE (UTC)"
echo "Workflow Template: $WORKFLOW_TEMPLATE"
echo "Namespace: $NAMESPACE"
echo

# Query with jq post-process filtering
# Note: kubectl field selectors do NOT support timestamp filtering for workflows
# Error: "invalid selector: 'metadata.creationTimestamp'; can't understand 'metadata.creationTimestamp'"
echo "Fetching workflows..."
kubectl --kubeconfig="$KUBECONFIG" get workflows -n "$NAMESPACE" -o json | \
  jq "[.items[] |
    select(.spec.workflowTemplateRef.name == \"$WORKFLOW_TEMPLATE\") |
    select(.metadata.creationTimestamp >= \"$CUTOFF_DATE\")] \
  | sort_by(.metadata.creationTimestamp) | reverse" > "$OUTPUT_FILE"

# Get count
COUNT=$(jq 'length' "$OUTPUT_FILE")
echo "Total pbx-web-build workflows in last 30 days: $COUNT"

# Edge case: no workflows
if [ "$COUNT" -eq 0 ]; then
  echo
  echo "⚠️  No pbx-web-build workflows found in the last 30 days"
  echo "This could mean:"
  echo "  - No workflows have been run in the last 30 days"
  echo "  - The workflow template name is incorrect"
  echo "  - Workflows are in a different namespace"
  echo
  echo "Checking available workflow templates..."
  kubectl --kubeconfig="$KUBECONFIG" get workflows -n "$NAMESPACE" -o json | \
    jq '[.items[] | .spec.workflowTemplateRef.name] | unique' | \
    head -10
  echo
  echo "Output file contains empty array: $OUTPUT_FILE"
else
  echo "Filtered results saved to: $OUTPUT_FILE"

  # Show date range
  FIRST_DATE=$(jq '.[0].metadata.creationTimestamp' "$OUTPUT_FILE" | tr -d '"')
  LAST_DATE=$(jq '.[-1].metadata.creationTimestamp' "$OUTPUT_FILE" | tr -d '"')
  echo "Date range: $FIRST_DATE to $LAST_DATE"

  # Show sample workflow
  echo
  echo "Sample workflow:"
  jq '.[0] | {name: .metadata.name, created: .metadata.creationTimestamp, status: .status.phase}' "$OUTPUT_FILE"
fi

echo
echo "=== Technical Details ==="
echo "Filtering method: jq post-processing"
echo "Reason: kubectl field selectors do not support timestamp filtering for Argo workflows"
echo "Timezone: UTC (uses -u flag for consistency)"
echo "Query: kubectl get workflows -o json | jq 'select(.metadata.creationTimestamp >= \"$CUTOFF_DATE\")'"
