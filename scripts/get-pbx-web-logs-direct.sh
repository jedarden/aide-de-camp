#!/bin/bash
# Direct pbx-web log retrieval without timestamp conversion issues
# Fetches raw logs from all pods and containers

set -euo pipefail

NAMESPACE="pbx-web"
OUTPUT_DIR="logs/pbx-web-ardenone-cluster"
TIMESTAMP=$(date -u +"%Y%m%d-%H%M%S")
OUTPUT_FILE="$OUTPUT_DIR/pbx-web-raw-${TIMESTAMP}.jsonl"

mkdir -p "$OUTPUT_DIR"

echo "=== Direct pbx-web Log Retrieval ===" >&2
echo "Namespace: $NAMESPACE" >&2
echo "Output: $OUTPUT_FILE" >&2
echo "" >&2

# Get all pods
PODS=$(kubectl --server=http://traefik-ardenone-cluster:8001 get pods -n "$NAMESPACE" -o json | jq -r '.items[].metadata.name')

for POD in $PODS; do
    echo "Processing pod: $POD" >&2

    # Get containers for this pod
    CONTAINERS=$(kubectl --server=http://traefik-ardenone-cluster:8001 get pod "$POD" -n "$NAMESPACE" -o json | jq -r '.spec.containers[].name')

    for CONTAINER in $CONTAINERS; do
        echo "  Container: $CONTAINER" >&2

        # Get current logs
        kubectl --server=http://traefik-ardenone-cluster:8001 logs "$POD" -n "$NAMESPACE" -c "$CONTAINER" --timestamps=true 2>&1 | while IFS= read -r line; do
            if [ -n "$line" ]; then
                # Escape the line for JSON
                ESCAPED=$(echo "$line" | sed 's/\\/\\\\/g' | sed 's/"/\\"/g' | tr -d '\n' | tr -d '\r')
                echo "{\"type\":\"log\",\"pod\":\"$POD\",\"container\":\"$CONTAINER\",\"stream\":\"current\",\"content\":\"$ESCAPED\"}"
            fi
        done >> "$OUTPUT_FILE"

        # Try to get previous logs (may be empty)
        kubectl --server=http://traefik-ardenone-cluster:8001 logs "$POD" -n "$NAMESPACE" -c "$CONTAINER" --previous=true --timestamps=true 2>&1 | while IFS= read -r line; do
            if [ -n "$line" ] && ! echo "$line" | grep -q "previous terminated container"; then
                ESCAPED=$(echo "$line" | sed 's/\\/\\\\/g' | sed 's/"/\\"/g' | tr -d '\n' | tr -d '\r')
                echo "{\"type\":\"log\",\"pod\":\"$POD\",\"container\":\"$CONTAINER\",\"stream\":\"previous\",\"content\":\"$ESCAPED\"}"
            fi
        done >> "$OUTPUT_FILE"
    done
done

# Get pod metadata
kubectl --server=http://traefik-ardenone-cluster:8001 get pods -n "$NAMESPACE" -o json | jq -c '.items[] | {
    type: "pod_metadata",
    name: .metadata.name,
    namespace: .metadata.namespace,
    created: .metadata.creationTimestamp,
    restarts: .status.containerStatuses[0].restartCount,
    containers: [.spec.containers[].name]
}' >> "$OUTPUT_FILE"

# Get events
kubectl --server=http://traefik-ardenone-cluster:8001 get events -n "$NAMESPACE" -o json | jq -c '.items[] | {
    type: "event",
    timestamp: .lastTimestamp,
    reason: .reason,
    message: .message,
    involved_object: .involvedObject.name
}' >> "$OUTPUT_FILE" || true

echo "" >&2
echo "=== Log Retrieval Complete ===" >&2
echo "Output: $OUTPUT_FILE" >&2
echo "Lines: $(wc -l < "$OUTPUT_FILE")" >&2

# Create summary
cat > "$OUTPUT_DIR/direct-fetch-summary-${TIMESTAMP}.json" <<EOF
{
  "collection_timestamp": "$(date -u +"%Y-%m-%dT%H:%M:%SZ")",
  "cluster": "ardenone-cluster",
  "namespace": "$NAMESPACE",
  "method": "direct_kubectl",
  "output_file": "$OUTPUT_FILE",
  "pods_processed": $(echo "$PODS" | wc -w),
  "line_count": $(wc -l < "$OUTPUT_FILE")
}
EOF

echo "Summary: $OUTPUT_DIR/direct-fetch-summary-${TIMESTAMP}.json" >&2
