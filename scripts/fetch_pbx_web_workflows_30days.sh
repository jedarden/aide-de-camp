#!/bin/bash
#
# fetch_pbx_web_workflows_30days.sh
#
# Retrieve pbx-web-build workflows from the last 30 days using jq post-processing
#
# Approach: jq post-processing (client-side filtering)
# Rationale: kubectl field selectors do not work with Argo Workflow CRDs
# Reference: /home/coding/aide-de-camp/scratch/filtering-decision.md

set -euo pipefail

# Configuration
NAMESPACE="argo-workflows"
LABEL_FILTER="workflows.argoproj.io/workflow-template=pbx-web-build"
OUTPUT_FILE="/home/coding/scratch/pbx-web-filtered-test.json"
KUBECONFIG="/home/coding/.kube/iad-ci.kubeconfig"

# Calculate 30-day window
SINCE_DATE=$(date -d "30 days ago" -u +"%Y-%m-%dT%H:%M:%SZ")
UNTIL_DATE=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

echo "=== pbx-web-build 30-Day Workflow Query ==="
echo "Start Date: $SINCE_DATE"
echo "End Date: $UNTIL_DATE"
echo "Label Filter: $LABEL_FILTER"
echo ""

# Function to handle edge cases
handle_edge_case() {
    local case_name="$1"
    local details="$2"
    echo "⚠️  EDGE CASE: $case_name"
    echo "   $details"
    echo ""
}

# Check if jq is available
if ! command -v jq &> /dev/null; then
    echo "ERROR: jq is not installed. Install with: apt install jq"
    exit 1
fi

# Check if kubeconfig exists
if [[ ! -f "$KUBECONFIG" ]]; then
    handle_edge_case "Kubeconfig Missing" \
        "File not found: $KUBECONFIG. Trying read-only proxy instead."
    KUBECONFIG=""
    KUBECTL_OPTS="--server=http://traefik-iad-ci:8001"
else
    KUBECTL_OPTS="--kubeconfig=$KUBECONFIG"
fi

# Check kubectl connectivity
echo "Testing kubectl connectivity..."
if ! kubectl $KUBECTL_OPTS get workflows -n "$NAMESPACE" --request-timeout=10 &> /dev/null; then
    echo "ERROR: Cannot connect to cluster. Check kubectl access."
    exit 1
fi
echo "✅ Cluster connectivity verified"
echo ""

# Execute query with jq post-processing
echo "Fetching pbx-web-build workflows..."
echo ""

kubectl $KUBECTL_OPTS get workflows -n "$NAMESPACE" \
  -l "$LABEL_FILTER" \
  -o json | \
jq --arg since "$SINCE_DATE" --arg until "$UNTIL_DATE" \
  '{
    query_metadata: {
      namespace: "'"$NAMESPACE"'",
      label_filter: "'"$LABEL_FILTER"'",
      since_date: $since,
      until_date: $until,
      query_timestamp: (now | todate),
      filtering_method: "jq post-processing",
      rationale: "kubectl field selectors do not support Argo Workflow CRD timestamp filtering"
    },
    total_workflows: (.items | length),
    filtered_workflows: (
      .items | map(select(
        (.metadata.creationTimestamp // "") >= $since and
        (.metadata.creationTimestamp // "") < $until
      )))
  }' > "$OUTPUT_FILE"

# Extract and display results
TOTAL=$(jq -r '.query_metadata.total_workflows // 0' "$OUTPUT_FILE")
FILTERED=$(jq -r '.filtered_workflows | length' "$OUTPUT_FILE")

echo "=== Query Results ==="
echo "Total workflows found: $TOTAL"
echo "Filtered workflows (last 30 days): $FILTERED"
echo ""

# Handle edge case: No workflows found
if [[ "$FILTERED" -eq 0 ]]; then
    handle_edge_case "No Workflows in 30-Day Window" \
        "No pbx-web-build workflows executed between $SINCE_DATE and $UNTIL_DATE.

        Possible reasons:
        1. No deployments in this period
        2. Aggressive workflow cleanup policy (workflows auto-deleted)
        3. Deployments managed via ArgoCD, not CI workflows
        4. WorkflowTemplate exists but no executions

        Recommendation: Check ArgoCD sync history or declarative-config git commits."
fi

# Handle edge case: Workflows exist but none in date range
if [[ "$TOTAL" -gt 0 ]] && [[ "$FILTERED" -eq 0 ]]; then
    handle_edge_case "Workflows Exist But Outside Date Range" \
        "Found $TOTAL workflows total, but none in the 30-day window.

        All workflows are either:
        1. Older than 30 days (before $SINCE_DATE)
        2. Newer than current time (timestamp errors)"

    # Show oldest and newest workflow dates
    OLDEST=$(jq -r '.items | map(.metadata.creationTimestamp) | sort | first' "$OUTPUT_FILE")
    NEWEST=$(jq -r '.items | map(.metadata.creationTimestamp) | sort | last' "$OUTPUT_FILE")
    echo "   Date range of existing workflows: $OLDEST to $NEWEST"
    echo ""
fi

# Show sample workflow data if found
if [[ "$FILTERED" -gt 0 ]]; then
    echo "Sample workflow data:"
    jq -r '.filtered_workflows[0] | {
        name: .metadata.name,
        created: .metadata.creationTimestamp,
        phase: .status.phase,
        message: .status.message
    }' "$OUTPUT_FILE"
    echo ""
fi

echo "✅ Results saved to: $OUTPUT_FILE"
echo ""
echo "=== Filtering Method ==="
echo "Method: jq post-processing"
echo "Rationale: kubectl field selectors cannot filter Argo Workflow CRDs by timestamp"
echo "Reference: /home/coding/aide-de-camp/scratch/filtering-decision.md"

exit 0
