#!/usr/bin/env bash
#
# Query pbx-web-build workflows from the last 30 days.
# Uses jq post-processing for date filtering since kubectl field selectors
# do not support inequality operators on creationTimestamp.
#
# Usage: ./scripts/query_pbx_web_workflows_30days.sh [output-file]
#

set -euo pipefail

# Calculate cutoff date (30 days ago in ISO 8601 format)
CUTOFF_DATE=$(date -u -d "30 days ago" +"%Y-%m-%dT%H:%M:%SZ" 2>/dev/null || date -u -v-30d +"%Y-%m-%dT%H:%M:%SZ")
OUTPUT_FILE="${1:-/home/coding/scratch/pbx-web-filtered-test.json}"

echo "Querying pbx-web-build workflows from the last 30 days..."
echo "Cutoff date: ${CUTOFF_DATE}"
echo "Output file: ${OUTPUT_FILE}"

# Fetch all workflows and filter by date using jq
kubectl --kubeconfig=/home/coding/.kube/iad-ci.kubeconfig get workflows \
  -n argo-workflows \
  -l workflows.argoproj.io/workflow-template=pbx-web-build \
  -o json | jq \
  --arg cutoff "${CUTOFF_DATE}" \
  '{
    cutoff_date: $cutoff,
    query_time: now | todate,
    total_workflows: (.items | length),
    filtered_workflows: ([.items[] | select(.metadata.creationTimestamp >= $cutoff)] | length),
    workflows_removed: ([.items[] | select(.metadata.creationTimestamp < $cutoff)] | length),
    items: [.items[] | select(.metadata.creationTimestamp >= $cutoff)]
  }' > "${OUTPUT_FILE}"

# Display results
TOTAL=$(jq -r '.total_workflows' "${OUTPUT_FILE}")
FILTERED=$(jq -r '.filtered_workflows' "${OUTPUT_FILE}")
REMOVED=$(jq -r '.workflows_removed' "${OUTPUT_FILE}")

echo "30-Day Workflow Filtering Results"
echo "==================================="
echo "Total workflows (before filtering): ${TOTAL}"
echo "Filtered workflows (last 30 days): ${FILTERED}"
echo "Workflows removed (older than 30 days): ${REMOVED}"
echo ""
echo "Filtered data saved to: ${OUTPUT_FILE}"

# Edge case: no workflows found
if [ "${TOTAL}" -eq 0 ]; then
    echo ""
    echo "NOTE: No pbx-web-build workflows found in the cluster."
    echo "This is expected if:"
    echo "  - The workflow template exists but has never been run"
    echo "  - All workflow runs have been garbage collected"
    echo "  - You're querying the wrong cluster/namespace"
fi
