#!/usr/bin/bash
# Script to gather deployment failure data for pbx-web and whisper-stt
# Time window: Last 30 days

set -e

RESEARCH_DIR="/home/coding/aide-de-camp/research-data"
mkdir -p "$RESEARCH_DIR"

# Calculate timestamp for 30 days ago (format: YYYY-MM-DDTHH:MM:SSZ)
SINCE=$(date -d "30 days ago" +"%Y-%m-%dT%H:%M:%SZ")
echo "Gathering data since: $SINCE"

echo "====================================="
echo "Gathering EVENTS from last 30 days"
echo "====================================="

# pbx-web events
echo "→ pbx-web events..."
kubectl --server=http://traefik-ardenone-cluster:8001 get events -n pbx-web \
  --field-selector type!=Normal \
  --sort-by='.lastTimestamp' > "$RESEARCH_DIR/pbx-web-events.txt" 2>&1 || true

# whisper-stt events
echo "→ whisper-stt events..."
kubectl --server=http://traefik-ardenone-cluster:8001 get events -n whisper-stt \
  --field-selector type!=Normal \
  --sort-by='.lastTimestamp' > "$RESEARCH_DIR/whisper-stt-events.txt" 2>&1 || true

echo ""
echo "====================================="
echo "Gathering POD HISTORY"
echo "====================================="

# Get all pods with their restart counts and ages
echo "→ pbx-web pods..."
kubectl --server=http://traefik-ardenone-cluster:8001 get pods -n pbx-web \
  -o wide > "$RESEARCH_DIR/pbx-web-pods.txt" 2>&1

echo "→ whisper-stt pods..."
kubectl --server=http://traefik-ardenone-cluster:8001 get pods -n whisper-stt \
  -o wide > "$RESEARCH_DIR/whisper-stt-pods.txt" 2>&1

echo ""
echo "====================================="
echo "Gathering LOGS (last 30 days)"
echo "====================================="

# Function to get logs from all containers in a pod
get_pod_logs() {
  local namespace=$1
  local pod=$2
  local output_dir=$3

  echo "  → Fetching logs for pod: $pod"

  # Get all containers in the pod
  containers=$(kubectl --server=http://traefik-ardenone-cluster:8001 get pod "$pod" -n "$namespace" \
    -o jsonpath='{.spec.containers[*].name}' 2>/dev/null || true)

  for container in $containers; do
    echo "    → Container: $container"
    kubectl --server=http://traefik-ardenone-cluster:8001 logs "$pod" -n "$namespace" \
      -c "$container" --since-time=$(date -d "30 days ago" +%s) \
      > "$output_dir/${pod}_${container}_logs.txt" 2>&1 || true
  done
}

# Get logs from current pods
echo "→ pbx-web logs..."
for pod in $(kubectl --server=http://traefik-ardenone-cluster:8001 get pods -n pbx-web \
  -o jsonpath='{.items[*].metadata.name}' 2>/dev/null || true); do
  get_pod_logs "pbx-web" "$pod" "$RESEARCH_DIR/pbx-web"
done

echo "→ whisper-stt logs..."
for pod in $(kubectl --server=http://traefik-ardenone-cluster:8001 get pods -n whisper-stt \
  -o jsonpath='{.items[*].metadata.name}' 2>/dev/null || true); do
  get_pod_logs "whisper-stt" "$pod" "$RESEARCH_DIR/whisper-stt"
done

echo ""
echo "====================================="
echo "Gathering REPLICASET HISTORY"
echo "====================================="

# Check for failed ReplicaSets (indicates deployment issues)
echo "→ pbx-web replicasets..."
kubectl --server=http://traefik-ardenone-cluster:8001 get replicasets -n pbx-web \
  -o wide > "$RESEARCH_DIR/pbx-web-replicasets.txt" 2>&1

echo "→ whisper-stt replicasets..."
kubectl --server=http://traefik-ardenone-cluster:8001 get replicasets -n whisper-stt \
  -o wide > "$RESEARCH_DIR/whisper-stt-replicasets.txt" 2>&1

echo ""
echo "====================================="
echo "COMPLETE"
echo "====================================="
echo "Data saved to: $RESEARCH_DIR"
ls -lh "$RESEARCH_DIR"
