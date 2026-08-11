#!/bin/bash
set -e

# Script to query resource usage metrics from Prometheus for pbx-web and whisper-stt
# Uses pod-based direct access to Prometheus API

OUTPUT_DIR="/home/coding/aide-de-camp/data/resource_metrics"
mkdir -p "$OUTPUT_DIR"

START_TIME=$(date -u -d '30 days ago' +"%Y-%m-%dT%H:%M:%SZ" 2>/dev/null || date -u -v-30d +"%Y-%m-%dT%H:%M:%SZ")
END_TIME=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
STEP="1h"  # 1-hour resolution

START_TS=$(date -d "$START_TIME" +%s)000
END_TS=$(date -d "$END_TIME" +%s)000

echo "Querying metrics from $START_TIME to $END_TIME"
echo "Output directory: $OUTPUT_DIR"
echo "Time range: $START_TS to $END_TS"

# Find Prometheus pod
PROM_POD=$(kubectl --server=http://traefik-ardenone-cluster:8001 get pods -n monitoring -l app.kubernetes.io/name=prometheus -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)

if [ -z "$PROM_POD" ]; then
    echo "ERROR: Could not find Prometheus pod"
    echo "Available pods in monitoring namespace:"
    kubectl --server=http://traefik-ardenone-cluster:8001 get pods -n monitoring
    exit 1
fi

echo "Using Prometheus pod: $PROM_POD"

# Function to run a single query via kubectl exec
run_query() {
    local query=$1
    local output_file=$2
    local description=$3

    echo "Querying: $description"

    # URL encode the query using jq
    ENCODED_QUERY=$(echo "$query" | jq -sRr @uri)

    # Build the curl command
    PROM_URL="http://localhost:9090/api/v1/query_range?query=${ENCODED_QUERY}&start=${START_TS}&end=${END_TS}&step=${STEP}"

    # Execute query via kubectl exec
    kubectl --server=http://traefik-ardenone-cluster:8001 exec -n monitoring "$PROM_POD" -- \
        curl -s "$PROM_URL" > "$output_file" 2>&1 || {
        echo "  -> ERROR: Query failed"
        return 1
    }

    # Check response
    if jq -e '.data.result' "$output_file" > /dev/null 2>&1; then
        DATA_POINTS=$(jq -r '.data.result | length' "$output_file" 2>/dev/null || echo "0")
        echo "  -> SUCCESS: Got $DATA_POINTS data points"

        # Print sample data
        if [ "$DATA_POINTS" -gt 0 ]; then
            echo "  -> Sample data: $(jq -r '.data.result[0].metric | @json' "$output_file" 2>/dev/null | head -c 100)..."
        fi
    else
        echo "  -> WARNING: No valid data returned"
        echo "  -> Response: $(head -c 200 "$output_file")"
    fi

    return 0
}

echo "=== Starting metrics collection ==="

# CPU METRICS
echo "--- CPU Metrics ---"

run_query \
    'sum(rate(container_cpu_usage_seconds_total{namespace="pbx-web",container!=""}[5m])) by (container)' \
    "$OUTPUT_DIR/pbx-web-cpu-usage.json" \
    "pbx-web CPU usage (cores)"

run_query \
    'sum(rate(container_cpu_usage_seconds_total{namespace="whisper-stt",container!=""}[5m])) by (container)' \
    "$OUTPUT_DIR/whisper-stt-cpu-usage.json" \
    "whisper-stt CPU usage (cores)"

run_query \
    'rate(container_cpu_cfs_throttled_periods_total{namespace="pbx-web",container!=""}[5m])' \
    "$OUTPUT_DIR/pbx-web-cpu-throttling.json" \
    "pbx-web CPU throttling"

run_query \
    'rate(container_cpu_cfs_throttled_periods_total{namespace="whisper-stt",container!=""}[5m])' \
    "$OUTPUT_DIR/whisper-stt-cpu-throttling.json" \
    "whisper-stt CPU throttling"

# MEMORY METRICS
echo "--- Memory Metrics ---"

run_query \
    'sum(container_memory_working_set_bytes{namespace="pbx-web",container!=""}) by (container)' \
    "$OUTPUT_DIR/pbx-web-memory-usage.json" \
    "pbx-web memory usage (bytes)"

run_query \
    'sum(container_memory_working_set_bytes{namespace="whisper-stt",container!=""}) by (container)' \
    "$OUTPUT_DIR/whisper-stt-memory-usage.json" \
    "whisper-stt memory usage (bytes)"

run_query \
    'sum(container_memory_cache{namespace="pbx-web",container!=""}) by (container)' \
    "$OUTPUT_DIR/pbx-web-memory-cache.json" \
    "pbx-web memory cache (bytes)"

run_query \
    'sum(container_memory_cache{namespace="whisper-stt",container!=""}) by (container)' \
    "$OUTPUT_DIR/whisper-stt-memory-cache.json" \
    "whisper-stt memory cache (bytes)"

# DISK I/O METRICS
echo "--- Disk I/O Metrics ---"

run_query \
    'sum(rate(container_fs_reads_bytes_total{namespace="pbx-web",container!=""}[5m])) by (container)' \
    "$OUTPUT_DIR/pbx-web-disk-reads.json" \
    "pbx-web disk read rate (bytes/sec)"

run_query \
    'sum(rate(container_fs_reads_bytes_total{namespace="whisper-stt",container!=""}[5m])) by (container)' \
    "$OUTPUT_DIR/whisper-stt-disk-reads.json" \
    "whisper-stt disk read rate (bytes/sec)"

run_query \
    'sum(rate(container_fs_writes_bytes_total{namespace="pbx-web",container!=""}[5m])) by (container)' \
    "$OUTPUT_DIR/pbx-web-disk-writes.json" \
    "pbx-web disk write rate (bytes/sec)"

run_query \
    'sum(rate(container_fs_writes_bytes_total{namespace="whisper-stt",container!=""}[5m])) by (container)' \
    "$OUTPUT_DIR/whisper-stt-disk-writes.json" \
    "whisper-stt disk write rate (bytes/sec)"

# NETWORK METRICS
echo "--- Network Metrics ---"

run_query \
    'sum(rate(container_network_receive_bytes_total{namespace="pbx-web",container!=""}[5m])) by (container)' \
    "$OUTPUT_DIR/pbx-web-network-rx.json" \
    "pbx-web network receive rate (bytes/sec)"

run_query \
    'sum(rate(container_network_receive_bytes_total{namespace="whisper-stt",container!=""}[5m])) by (container)' \
    "$OUTPUT_DIR/whisper-stt-network-rx.json" \
    "whisper-stt network receive rate (bytes/sec)"

run_query \
    'sum(rate(container_network_transmit_bytes_total{namespace="pbx-web",container!=""}[5m])) by (container)' \
    "$OUTPUT_DIR/pbx-web-network-tx.json" \
    "pbx-web network transmit rate (bytes/sec)"

run_query \
    'sum(rate(container_network_transmit_bytes_total{namespace="whisper-stt",container!=""}[5m])) by (container)' \
    "$OUTPUT_DIR/whisper-stt-network-tx.json" \
    "whisper-stt network transmit rate (bytes/sec)"

# Additional pod-level metrics
echo "--- Pod Status Metrics ---"

run_query \
    'kube_pod_status_phase{namespace="pbx-web"}' \
    "$OUTPUT_DIR/pbx-web-pod-status.json" \
    "pbx-web pod status"

run_query \
    'kube_pod_status_phase{namespace="whisper-stt"}' \
    "$OUTPUT_DIR/whisper-stt-pod-status.json" \
    "whisper-stt pod status"

run_query \
    'kube_pod_container_status_ready{namespace="pbx-web"}' \
    "$OUTPUT_DIR/pbx-web-container-ready.json" \
    "pbx-web container readiness"

run_query \
    'kube_pod_container_status_ready{namespace="whisper-stt"}' \
    "$OUTPUT_DIR/whisper-stt-container-ready.json" \
    "whisper-stt container readiness"

echo "=== Metrics collection complete ==="
echo "Output files:"
ls -la "$OUTPUT_DIR"
