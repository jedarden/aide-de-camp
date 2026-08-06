#!/bin/bash
# Collect Argo Workflow runs for whisper-stt-build over the 30-day research period
# Time range: 2026-07-07 to 2026-08-06

NAMESPACE="argo-workflows"
TEMPLATE="whisper-stt-build"
SINCE="2026-07-07T00:00:00Z"
UNTIL="2026-08-07T00:00:00Z"
KUBECONFIG="${KUBECONFIG:-/home/coding/.kube/iad-ci.kubeconfig}"

kubectl --kubeconfig="$KUBECONFIG" get workflows -n "$NAMESPACE" \
  -l workflows.argoproj.io/workflow-template="$TEMPLATE" \
  --field-selector creationTimestamp">=$SINCE",creationTimestamp"<$UNTIL" \
  -o json | \
  jq -r '.items[] | @json' > argo-workflows.jsonl

echo "Collected workflows: $(wc -l < argo-workflows.jsonl)"
