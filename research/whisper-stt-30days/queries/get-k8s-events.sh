#!/bin/bash
# Collect Kubernetes events for whisper-stt over the 30-day research period
# Time range: 2026-07-07 to 2026-08-06

NAMESPACE="${1:-whisper-stt}"
SINCE="2026-07-07T00:00:00Z"
UNTIL="2026-08-07T00:00:00Z"

kubectl get events -n "$NAMESPACE" \
  --field-selector creationTimestamp">=$SINCE",creationTimestamp"<$UNTIL" \
  --sort-by=.lastTimestamp \
  -o json | \
  jq -r '.items[] | @json' > k8s-events.jsonl

echo "Collected events: $(wc -l < k8s-events.jsonl)"
