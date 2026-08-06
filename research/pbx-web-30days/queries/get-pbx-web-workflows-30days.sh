#!/bin/bash
# Collect Argo Workflow runs for pbx-web-build over the last 30 days
# Time range: 2026-07-07 to 2026-08-06 (current date: 2026-08-06)
#
# This script demonstrates TWO approaches for date filtering:
# Approach A: kubectl field selector (recommended - server-side filtering)
# Approach B: jq post-processing (fallback - client-side filtering)

set -e

NAMESPACE="argo-workflows"
TEMPLATE="pbx-web-build"
SINCE="2026-07-07T00:00:00Z"
UNTIL="2026-08-07T00:00:00Z"
KUBECONFIG="${KUBECONFIG:-/home/coding/.kube/iad-ci.kubeconfig}"
OUTPUT_DIR="/home/coding/scratch"
APPROACH_A_OUTPUT="$OUTPUT_DIR/pbx-web-workflows-approach-a.json"
APPROACH_B_OUTPUT="$OUTPUT_DIR/pbx-web-workflows-approach-b.json"
FINAL_OUTPUT="$OUTPUT_DIR/pbx-web-filtered-test.json"

echo "==================================="
echo "PBX-Web Build Workflow Query - 30 Day Filter"
echo "==================================="
echo "Template: $TEMPLATE"
echo "Since: $SINCE"
echo "Until: $UNTIL"
echo "Kubeconfig: $KUBECONFIG"
echo ""

# Ensure output directory exists
mkdir -p "$OUTPUT_DIR"

# APPROACH A: kubectl field selector (server-side filtering)
# This is the RECOMMENDED approach when it works
echo "Approach A: Testing kubectl field selector..."

# Note: field selectors need proper quoting for comparison operators
FIELD_SELECTOR="creationTimestamp>=$SINCE,creationTimestamp<$UNTIL"

if kubectl --kubeconfig="$KUBECONFIG" get workflows -n "$NAMESPACE" \
  --field-selector="$FIELD_SELECTOR" \
  -o json > /dev/null 2>&1; then

  echo "✓ Field selector syntax is supported by this kubectl version"

  # Try with workflow template label
  if kubectl --kubeconfig="$KUBECONFIG" get workflows -n "$NAMESPACE" \
    -l workflows.argoproj.io/workflow-template="$TEMPLATE" \
    --field-selector="$FIELD_SELECTOR" \
    -o json > "$APPROACH_A_OUTPUT"; then

    COUNT=$(jq '.items | length' "$APPROACH_A_OUTPUT")
    echo "✓ Found $COUNT pbx-web-build workflows using field selector"
  else
    echo "⚠ No workflows found with template label, trying name pattern..."

    # Fallback: get all workflows in date range, filter by name pattern
    kubectl --kubeconfig="$KUBECONFIG" get workflows -n "$NAMESPACE" \
      --field-selector creationTimestamp">=$SINCE",creationTimestamp"<$UNTIL" \
      -o json | \
      jq '.items | select(.metadata.name | test("pbx-web-build"; "i"))' > "$APPROACH_A_OUTPUT"

    COUNT=$(jq 'if type == "array" then length else 1 end' "$APPROACH_A_OUTPUT")
    echo "✓ Found $COUNT pbx-web-build workflows using name pattern + field selector"
  fi
else
  echo "✗ Field selector not supported or failed"
  echo "Falling back to Approach B (jq post-processing)..."
  APPROACH_A_OUTPUT=""
fi

# APPROACH B: jq post-processing (client-side filtering)
# This is the FALLBACK approach when field selectors don't work
echo ""
echo "Approach B: Using jq post-processing..."

# Fetch all workflows with the template label (no date filter)
if kubectl --kubeconfig="$KUBECONFIG" get workflows -n "$NAMESPACE" \
  -l workflows.argoproj.io/workflow-template="$TEMPLATE" \
  -o json > "$APPROACH_B_OUTPUT.temp"; then

  # Apply 30-day date filter using jq
  jq --arg since "$SINCE" --arg until "$UNTIL" \
    '.items | map(select(
      .metadata.creationTimestamp >= $since and
      .metadata.creationTimestamp < $until
    )) | {items: .}' "$APPROACH_B_OUTPUT.temp" > "$APPROACH_B_OUTPUT"

  COUNT=$(jq '.items | length' "$APPROACH_B_OUTPUT")
  echo "✓ Found $COUNT pbx-web-build workflows using jq filtering"
  rm -f "$APPROACH_B_OUTPUT.temp"
else
  echo "⚠ No workflows found with template label, trying name pattern..."

  # Fallback: get all workflows, filter by name and date
  kubectl --kubeconfig="$KUBECONFIG" get workflows -n "$NAMESPACE" \
    -o json | \
    jq --arg since "$SINCE" --arg until "$UNTIL" \
    '.items | map(select(
      (.metadata.name | test("pbx-web-build"; "i")) and
      (.metadata.creationTimestamp // "" >= $since) and
      (.metadata.creationTimestamp // "" < $until)
    )) | {items: .}' > "$APPROACH_B_OUTPUT"

  COUNT=$(jq '.items | length' "$APPROACH_B_OUTPUT")
  echo "✓ Found $COUNT pbx-web-build workflows using name pattern + jq filtering"
fi

# Select the best result
echo ""
echo "==================================="
echo "Selecting Best Approach..."
echo "==================================="

if [ -n "$APPROACH_A_OUTPUT" ] && [ -f "$APPROACH_A_OUTPUT" ]; then
  COUNT_A=$(jq '.items | length' "$APPROACH_A_OUTPUT" 2>/dev/null || echo "0")
  COUNT_B=$(jq '.items | length' "$APPROACH_B_OUTPUT" 2>/dev/null || echo "0")

  if [ "$COUNT_A" -ge "$COUNT_B" ]; then
    echo "Using Approach A (kubectl field selector) - $COUNT_A workflows"
    cp "$APPROACH_A_OUTPUT" "$FINAL_OUTPUT"
    METHOD="kubectl_field_selector"
  else
    echo "Using Approach B (jq post-processing) - $COUNT_B workflows"
    cp "$APPROACH_B_OUTPUT" "$FINAL_OUTPUT"
    METHOD="jq_post_processing"
  fi
else
  echo "Using Approach B (jq post-processing)"
  cp "$APPROACH_B_OUTPUT" "$FINAL_OUTPUT"
  METHOD="jq_post_processing"
fi

# Add metadata to output
jq --arg method "$METHOD" --arg since "$SINCE" --arg until "$UNTIL" \
  '. + {
    metadata: {
      filtering_method: $method,
      date_range: {
        since: $since,
        until: $until
      },
      query_timestamp: now | todate
    }
  }' "$FINAL_OUTPUT" > "${FINAL_OUTPUT}.tmp" && mv "${FINAL_OUTPUT}.tmp" "$FINAL_OUTPUT"

# Print summary
echo ""
echo "==================================="
echo "Final Summary"
echo "==================================="
echo "Filtering method: $METHOD"
echo "Output file: $FINAL_OUTPUT"
TOTAL=$(jq '.items | length' "$FINAL_OUTPUT")
echo "Total workflows found: $TOTAL"

if [ "$TOTAL" -eq 0 ]; then
  echo ""
  echo "⚠ WARNING: No pbx-web-build workflows found in 30-day window"
  echo "This could mean:"
  echo "  - No pbx-web builds have run in the last 30 days"
  echo "  - Workflow template name is different than expected"
  echo "  - Workflows exist but use different labels/naming"
  echo ""
  echo "Available workflow templates in cluster:"
  kubectl --kubeconfig="$KUBECONFIG" get workflowtemplates -n "$NAMESPACE" -o json | \
    jq -r '.items[].metadata.name' | grep -E '(pbx|web)' || echo "  (no pbx/web templates found)"
fi

echo ""
echo "Query complete!"
