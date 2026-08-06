#!/bin/bash
# Whisper-STT 30-Day Deployment Log Gathering
# Based on pbx-web approach for consistency

set -e

OUTPUT_DIR="/home/coding/aide-de-camp/logs"
mkdir -p "$OUTPUT_DIR"

echo "=== Whisper-STT 30-Day Deployment Log Gathering ==="
echo "Date: $(date)"
echo "Output Directory: $OUTPUT_DIR"
echo

# VictoriaLogs query setup
VL_HOST="http://victorialogs-single-ardenone-cluster-vector.monitoring.svc.cluster.local:9428"
NAMESPACE="whisper-stt"

# Calculate 30 days ago
CUTOFF_DATE=$(date -d "30 days ago" +%Y-%m-%dT%H:%M:%S%z)
echo "Cutoff Date: $CUTOFF_DATE"
echo

echo "=== 1. Querying VictoriaLogs for whisper-stt ==="
VL_OUTPUT="$OUTPUT_DIR/whisper-stt-30day-victorialogs.jsonl"
curl -s "$VL_HOST/select/logomic/query" \
  --data-urlencode "query={namespace=\"whisper-stt\"} | format {{.Time}} {{.Message}}" \
  --data-urlencode "start=$CUTOFF_DATE" \
  --data-urlencode "limit=10000" \
  > "$VL_OUTPUT" || echo "VictoriaLogs query failed or returned no data"

if [ -s "$VL_OUTPUT" ]; then
  LINES=$(wc -l < "$VL_OUTPUT")
  echo "VictoriaLogs: $LINES log entries retrieved"
else
  echo "VictoriaLogs: No data retrieved or query failed"
fi
echo

echo "=== 2. Getting current pod information ==="
kubectl --server=http://traefik-ardenone-cluster:8001 get pods -n "$NAMESPACE" -o json > "$OUTPUT_DIR/whisper-stt-pods-current.json"
POD_COUNT=$(jq '.items | length' "$OUTPUT_DIR/whisper-stt-pods-current.json")
echo "Current pods: $POD_COUNT"
echo

echo "=== 3. Getting pod logs for current pods ==="
for POD in $(kubectl --server=http://traefik-ardenone-cluster:8001 get pods -n "$NAMESPACE" -o name); do
  POD_NAME=$(basename "$POD")
  echo "Fetching logs for: $POD_NAME"

  # Get all containers in the pod
  CONTAINERS=$(kubectl --server=http://traefik-ardenone-cluster:8001 get "$POD" -n "$NAMESPACE" -o json | jq -r '.spec.containers[].name')

  for CONTAINER in $CONTAINERS; do
    LOG_FILE="$OUTPUT_DIR/whisper-stt-${POD_NAME}-${CONTAINER}-logs.txt"
    kubectl --server=http://traefik-ardenone-cluster:8001 logs "$POD" -n "$NAMESPACE" -c "$CONTAINER" \
      --since-time="$(date -d "30 days ago" +%s)" > "$LOG_FILE" 2>&1 || echo "Failed to get logs for $POD_NAME/$CONTAINER"

    if [ -s "$LOG_FILE" ]; then
      LINES=$(wc -l < "$LOG_FILE")
      SIZE=$(du -h "$LOG_FILE" | cut -f1)
      echo "  $CONTAINER: $LINES lines ($SIZE)"
    else
      echo "  $CONTAINER: No logs or failed"
    fi
  done
done
echo

echo "=== 4. Getting replica set history ==="
kubectl --server=http://traefik-ardenone-cluster:8001 get replicasets -n "$NAMESPACE" -o json > "$OUTPUT_DIR/whisper-stt-replicasets.json"
RS_COUNT=$(jq '.items | length' "$OUTPUT_DIR/whisper-stt-replicasets.json")
echo "Total replica sets: $RS_COUNT"
echo

echo "=== 5. Getting deployment information ==="
kubectl --server=http://traefik-ardenone-cluster:8001 get deployments -n "$NAMESPACE" -o json > "$OUTPUT_DIR/whisper-stt-deployments.json"
kubectl --server=http://traefik-ardenone-cluster:8001 describe deployment -n "$NAMESPACE" > "$OUTPUT_DIR/whisper-stt-deployment-describe.txt" 2>&1
echo "Deployment information saved"
echo

echo "=== 6. Getting cluster events ==="
kubectl --server=http://traefik-ardenone-cluster:8001 get events -n "$NAMESPACE" --sort-by='.lastTimestamp' > "$OUTPUT_DIR/whisper-stt-events.txt" 2>&1
EVENT_COUNT=$(wc -l < "$OUTPUT_DIR/whisper-stt-events.txt")
echo "Events: $EVENT_COUNT lines"
echo

echo "=== 7. Getting pod descriptions for restart history ==="
for POD in $(kubectl --server=http://traefik-ardenone-cluster:8001 get pods -n "$NAMESPACE" -o name); do
  POD_NAME=$(basename "$POD")
  kubectl --server=http://traefik-ardenone-cluster:8001 describe pod "$POD_NAME" -n "$NAMESPACE" > "$OUTPUT_DIR/whisper-stt-${POD_NAME}-describe.txt" 2>&1
  RESTARTS=$(grep "Restart Count" "$OUTPUT_DIR/whisper-stt-${POD_NAME}-describe.txt" | awk '{print $NF}')
  echo "Pod $POD_NAME restarts: $RESTARTS"
done
echo

echo "=== Log Gathering Complete ==="
echo "All outputs saved to: $OUTPUT_DIR"
ls -lh "$OUTPUT_DIR"/whisper-stt-*
