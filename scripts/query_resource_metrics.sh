#!/bin/bash
set -e

# Script to query resource usage metrics from Prometheus for pbx-web and whisper-stt
# Time window: 30 days
# Output: JSON files with metrics data

PROMETHEUS_URL="http://kube-prometheus-stack-arde-prometheus.monitoring.svc.cluster.local:9090"
START_TIME=$(date -u -d '30 days ago' +"%Y-%m-%dT%H:%M:%SZ" 2>/dev/null || date -u -v-30d +"%Y-%m-%dT%H:%M:%SZ")
END_TIME=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
STEP="1h"  # 1-hour resolution

# Create output directory
OUTPUT_DIR="/home/coding/aide-de-camp/data/resource_metrics"
mkdir -p "$OUTPUT_DIR"

echo "Querying metrics from $START_TIME to $END_TIME"
echo "Output directory: $OUTPUT_DIR"

# Function to query Prometheus
query_prometheus() {
    local query=$1
    local output_file=$2
    local description=$3

    echo "Querying: $description"
    echo "Query: $query"

    # URL encode the query (simple version)
    ENCODED_QUERY=$(echo "$query" | jq -sRr @uri)

    # Calculate timestamps
    START_TS=$(date -d "$START_TIME" +%s)000
    END_TS=$(date -d "$END_TIME" +%s)000

    # Use kubectl exec to run curl inside the prometheus pod
    PROM_POD=$(kubectl --server=http://traefik-ardenone-cluster:8001 get pods -n monitoring -l app.kubernetes.io/name=prometheus -o jsonpath='{.items[0].metadata.name}')

    if [ -z "$PROM_POD" ]; then
        echo "  -> ERROR: Could not find Prometheus pod"
        return 1
    fi

    # Query via exec (using localhost inside the pod)
    kubectl --server=http://traefik-ardenone-cluster:8001 exec -n monitoring "$PROM_POD" -- \
        curl -s "http://localhost:9090/api/v1/query_range?query=${ENCODED_QUERY}&start=${START_TS}&end=${END_TS}&step=${STEP}" > "$output_file" 2>&1 || {
        echo "  -> Failed to query: $description"
        return 1
    }

    # Check if we got data
    DATA_POINTS=$(jq -r '.data.result | length' "$output_file" 2>/dev/null || echo "0")
    echo "  -> Got $DATA_POINTS data points"

    return 0
}

# ===== CPU METRICS =====
echo "=== CPU Metrics ==="

# CPU usage rate (cores) - pbx-web
query_prometheus \
    'sum(rate(container_cpu_usage_seconds_total{namespace="pbx-web",container!=""}[5m])) by (container)' \
    "$OUTPUT_DIR/pbx-web-cpu-usage.json" \
    "pbx-web CPU usage (cores)"

# CPU usage rate (cores) - whisper-stt
query_prometheus \
    'sum(rate(container_cpu_usage_seconds_total{namespace="whisper-stt",container!=""}[5m])) by (container)' \
    "$OUTPUT_DIR/whisper-stt-cpu-usage.json" \
    "whisper-stt CPU usage (cores)"

# CPU throttling - pbx-web
query_prometheus \
    'sum(rate(container_cpu_cfs_throttled_periods_total{namespace="pbx-web",container!=""}[5m])) by (container)' \
    "$OUTPUT_DIR/pbx-web-cpu-throttling.json" \
    "pbx-web CPU throttling"

# CPU throttling - whisper-stt
query_prometheus \
    'sum(rate(container_cpu_cfs_throttled_periods_total{namespace="whisper-stt",container!=""}[5m])) by (container)' \
    "$OUTPUT_DIR/whisper-stt-cpu-throttling.json" \
    "whisper-stt CPU throttling"

# ===== MEMORY METRICS =====
echo "=== Memory Metrics ==="

# Memory usage (bytes) - pbx-web
query_prometheus \
    'sum(container_memory_working_set_bytes{namespace="pbx-web",container!=""}) by (container)' \
    "$OUTPUT_DIR/pbx-web-memory-usage.json" \
    "pbx-web memory usage (bytes)"

# Memory usage (bytes) - whisper-stt
query_prometheus \
    'sum(container_memory_working_set_bytes{namespace="whisper-stt",container!=""}) by (container)' \
    "$OUTPUT_DIR/whisper-stt-memory-usage.json" \
    "whisper-stt memory usage (bytes)"

# Memory cache (bytes) - pbx-web
query_prometheus \
    'sum(container_memory_cache{namespace="pbx-web",container!=""}) by (container)' \
    "$OUTPUT_DIR/pbx-web-memory-cache.json" \
    "pbx-web memory cache (bytes)"

# Memory cache (bytes) - whisper-stt
query_prometheus \
    'sum(container_memory_cache{namespace="whisper-stt",container!=""}) by (container)' \
    "$OUTPUT_DIR/whisper-stt-memory-cache.json" \
    "whisper-stt memory cache (bytes)"

# Page faults - pbx-web
query_prometheus \
    'sum(rate(container_memory_failures_total{namespace="pbx-web",container!=""}[5m])) by (container)' \
    "$OUTPUT_DIR/pbx-web-memory-failures.json" \
    "pbx-web memory failures"

# Page faults - whisper-stt
query_prometheus \
    'sum(rate(container_memory_failures_total{namespace="whisper-stt",container!=""}[5m])) by (container)' \
    "$OUTPUT_DIR/whisper-stt-memory-failures.json" \
    "whisper-stt memory failures"

# ===== DISK I/O METRICS =====
echo "=== Disk I/O Metrics ==="

# Disk read rate (bytes/sec) - pbx-web
query_prometheus \
    'sum(rate(container_fs_reads_bytes_total{namespace="pbx-web",container!=""}[5m])) by (container)' \
    "$OUTPUT_DIR/pbx-web-disk-reads.json" \
    "pbx-web disk read rate (bytes/sec)"

# Disk read rate (bytes/sec) - whisper-stt
query_prometheus \
    'sum(rate(container_fs_reads_bytes_total{namespace="whisper-stt",container!=""}[5m])) by (container)' \
    "$OUTPUT_DIR/whisper-stt-disk-reads.json" \
    "whisper-stt disk read rate (bytes/sec)"

# Disk write rate (bytes/sec) - pbx-web
query_prometheus \
    'sum(rate(container_fs_writes_bytes_total{namespace="pbx-web",container!=""}[5m])) by (container)' \
    "$OUTPUT_DIR/pbx-web-disk-writes.json" \
    "pbx-web disk write rate (bytes/sec)"

# Disk write rate (bytes/sec) - whisper-stt
query_prometheus \
    'sum(rate(container_fs_writes_bytes_total{namespace="whisper-stt",container!=""}[5m])) by (container)' \
    "$OUTPUT_DIR/whisper-stt-disk-writes.json" \
    "whisper-stt disk write rate (bytes/sec)"

# ===== NETWORK METRICS =====
echo "=== Network Metrics ==="

# Network receive rate (bytes/sec) - pbx-web
query_prometheus \
    'sum(rate(container_network_receive_bytes_total{namespace="pbx-web",container!=""}[5m])) by (container)' \
    "$OUTPUT_DIR/pbx-web-network-rx.json" \
    "pbx-web network receive rate (bytes/sec)"

# Network receive rate (bytes/sec) - whisper-stt
query_prometheus \
    'sum(rate(container_network_receive_bytes_total{namespace="whisper-stt",container!=""}[5m])) by (container)' \
    "$OUTPUT_DIR/whisper-stt-network-rx.json" \
    "whisper-stt network receive rate (bytes/sec)"

# Network transmit rate (bytes/sec) - pbx-web
query_prometheus \
    'sum(rate(container_network_transmit_bytes_total{namespace="pbx-web",container!=""}[5m])) by (container)' \
    "$OUTPUT_DIR/pbx-web-network-tx.json" \
    "pbx-web network transmit rate (bytes/sec)"

# Network transmit rate (bytes/sec) - whisper-stt
query_prometheus \
    'sum(rate(container_network_transmit_bytes_total{namespace="whisper-stt",container!=""}[5m])) by (container)' \
    "$OUTPUT_DIR/whisper-stt-network-tx.json" \
    "whisper-stt network transmit rate (bytes/sec)"

# Network receive packets/sec - pbx-web
query_prometheus \
    'sum(rate(container_network_receive_packets_total{namespace="pbx-web",container!=""}[5m])) by (container)' \
    "$OUTPUT_DIR/pbx-web-network-rx-packets.json" \
    "pbx-web network receive packets/sec"

# Network receive packets/sec - whisper-stt
query_prometheus \
    'sum(rate(container_network_receive_packets_total{namespace="whisper-stt",container!=""}[5m])) by (container)' \
    "$OUTPUT_DIR/whisper-stt-network-rx-packets.json" \
    "whisper-stt network receive packets/sec"

# Network transmit packets/sec - pbx-web
query_prometheus \
    'sum(rate(container_network_transmit_packets_total{namespace="pbx-web",container!=""}[5m])) by (container)' \
    "$OUTPUT_DIR/pbx-web-network-tx-packets.json" \
    "pbx-web network transmit packets/sec"

# Network transmit packets/sec - whisper-stt
query_prometheus \
    'sum(rate(container_network_transmit_packets_total{namespace="whisper-stt",container!=""}[5m])) by (container)' \
    "$OUTPUT_DIR/whisper-stt-network-tx-packets.json" \
    "whisper-stt network transmit packets/sec"

echo "=== Metrics collection complete ==="
echo "Output files saved to: $OUTPUT_DIR"
ls -la "$OUTPUT_DIR"
