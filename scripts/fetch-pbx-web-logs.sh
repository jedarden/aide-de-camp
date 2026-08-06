#!/bin/bash
# pbx-web Log Retrieval Script
# Fetches logs from pbx-web pods with date range support, pod history handling, and JSON output
#
# Usage:
#   ./fetch-pbx-web-logs.sh [options]
#
# Options:
#   --namespace <ns>           Kubernetes namespace (default: pbx-web)
#   --cluster <cluster>        Cluster name (default: ardenone-cluster)
#   --days <n>                 Number of days to look back (default: 30, max: 90)
#   --since <date>             Start date (YYYY-MM-DD format)
#   --until <date>             End date (YYYY-MM-DD format)
#   --output-dir <dir>         Output directory (default: logs/pbx-web-<date-range>)
#   --format <format>          Output format: json or jsonl (default: jsonl)
#   --include-history          Include ReplicaSet history and restart events
#   --pod-history-depth <n>    How many pod generations back to check (default: 5)
#   --kubeconfig <path>        Kubeconfig path (default: system proxy)
#   --verbose                  Enable verbose output
#   --help                     Show this help message
#
# Examples:
#   # Fetch last 30 days of logs (default)
#   ./fetch-pbx-web-logs.sh
#
#   # Fetch last 7 days with JSON output
#   ./fetch-pbx-web-logs.sh --days 7 --format json
#
#   # Fetch specific date range
#   ./fetch-pbx-web-logs.sh --since 2026-07-01 --until 2026-07-15
#
#   # Include pod history and events
#   ./fetch-pbx-web-logs.sh --days 30 --include-history
#
# Output:
#   Creates structured JSON/JSONL output with:
#   - Pod metadata (name, namespace, labels, creation time)
#   - Log entries with timestamps
#   - Container information
#   - Restart history
#   - Event history (OOMKilled, evictions, errors)
#
# Author: aide-de-camp
# Date: 2026-08-06

set -euo pipefail

# Configuration defaults
NAMESPACE="pbx-web"
CLUSTER="ardenone-cluster"
DAYS=30
OUTPUT_DIR=""
OUTPUT_FORMAT="jsonl"
INCLUDE_HISTORY=false
POD_HISTORY_DEPTH=5
KUBECONFIG_CONTEXT="http://traefik-ardenone-cluster:8001"
SINCE_DATE=""
UNTIL_DATE=""
VERBOSE=false

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging functions
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

log_debug() {
    if [ "$VERBOSE" = true ]; then
        echo -e "${BLUE}[DEBUG]${NC} $1"
    fi
}

# Help function
show_help() {
    grep "^#" "$0" | grep -v "!/bin/bash" | sed 's/^# //' | sed 's/^#//'
    exit 0
}

# Parse command line arguments
parse_args() {
    while [[ $# -gt 0 ]]; do
        case $1 in
            --namespace)
                NAMESPACE="$2"
                shift 2
                ;;
            --cluster)
                CLUSTER="$2"
                shift 2
                ;;
            --days)
                DAYS="$2"
                shift 2
                ;;
            --since)
                SINCE_DATE="$2"
                shift 2
                ;;
            --until)
                UNTIL_DATE="$2"
                shift 2
                ;;
            --output-dir)
                OUTPUT_DIR="$2"
                shift 2
                ;;
            --format)
                OUTPUT_FORMAT="$2"
                shift 2
                ;;
            --include-history)
                INCLUDE_HISTORY=true
                shift
                ;;
            --pod-history-depth)
                POD_HISTORY_DEPTH="$2"
                shift 2
                ;;
            --kubeconfig)
                KUBECONFIG_CONTEXT="$2"
                shift 2
                ;;
            --verbose)
                VERBOSE=true
                shift
                ;;
            --help)
                show_help
                ;;
            *)
                log_error "Unknown option: $1"
                show_help
                ;;
        esac
    done

    # Validate days parameter
    if [ "$DAYS" -gt 90 ]; then
        log_warn "Days parameter exceeds 90, capping at 90"
        DAYS=90
    fi

    # Calculate dates if not provided
    if [ -z "$SINCE_DATE" ]; then
        SINCE_DATE=$(date -u -d "$DAYS days ago" +"%Y-%m-%d" 2>/dev/null || date -u -v-${DAYS}d +"%Y-%m-%d")
    fi

    if [ -z "$UNTIL_DATE" ]; then
        UNTIL_DATE=$(date -u +"%Y-%m-%d")
    fi

    # Set output directory if not specified
    if [ -z "$OUTPUT_DIR" ]; then
        OUTPUT_DIR="logs/pbx-web-${DAYS}day"
    fi

    # Validate output format
    if [ "$OUTPUT_FORMAT" != "json" ] && [ "$OUTPUT_FORMAT" != "jsonl" ]; then
        log_error "Invalid output format: $OUTPUT_FORMAT (must be 'json' or 'jsonl')"
        exit 1
    fi
}

# Date conversion functions
date_to_timestamp() {
    local date_str="$1"
    local timestamp
    timestamp=$(date -u -d "$date_str" +"%s" 2>/dev/null)
    if [ -z "$timestamp" ]; then
        # Try macOS date format
        timestamp=$(date -u -j -f "%Y-%m-%d" "$date_str" +"%s" 2>/dev/null)
    fi
    if [ -z "$timestamp" ]; then
        log_error "Invalid date format: $date_str"
        echo "0"
        return 1
    fi
    echo "$timestamp"
}

timestamp_to_kubectl_format() {
    local timestamp="$1"
    echo "${timestamp}"
}

# Create output directory
setup_output_dir() {
    mkdir -p "$OUTPUT_DIR"
    log_info "Output directory: $OUTPUT_DIR"
}

# Get all pbx-web related pods
get_pods() {
    log_info "Fetching pods from namespace: $NAMESPACE"

    local pods
    pods=$(kubectl --server="$KUBECONFIG_CONTEXT" get pods -n "$NAMESPACE" -o json 2>&1) || true

    # Check if response is valid JSON
    if ! echo "$pods" | jq empty 2>/dev/null; then
        log_error "Invalid JSON response from kubectl"
        log_error "Response: $(echo "$pods" | head -c 200)"
        return 1
    fi

    echo "$pods"
}

# Get ReplicaSet history for pod restart analysis
get_replica_history() {
    log_debug "Fetching ReplicaSet history..."

    local replicasets
    replicasets=$(kubectl --server="$KUBECONFIG_CONTEXT" get replicasets -n "$NAMESPACE" -o json 2>/dev/null || echo "")

    echo "$replicasets"
}

# Get pod events for OOMKilled, eviction, error detection
get_pod_events() {
    local pod_name="$1"
    local namespace="${2:-$NAMESPACE}"
    local kubeconfig="${3:-$KUBECONFIG_CONTEXT}"

    log_debug "Fetching events for pod: $pod_name"

    local events
    events=$(kubectl --server="$kubeconfig" get events -n "$namespace" --field-selector=involvedObject.name="$pod_name" -o json 2>/dev/null || echo '{"items":[]}')

    echo "$events"
}

# Fetch logs for a specific pod
fetch_pod_logs() {
    local pod_name="$1"
    local container="${2:-}"
    local previous="${3:-false}"
    local namespace="${4:-$NAMESPACE}"
    local kubeconfig="${5:-$KUBECONFIG_CONTEXT}"
    local since_date="${6:-$SINCE_DATE}"

    local since_timestamp
    since_timestamp=$(date_to_timestamp "$since_date")

    local cmd="kubectl --server='$kubeconfig' logs '$pod_name' -n '$namespace'"

    if [ "$previous" = true ]; then
        cmd="$cmd --previous=true"
    fi

    if [ -n "$container" ]; then
        cmd="$cmd -c '$container'"
    fi

    # Add time filter
    cmd="$cmd --since-time=$since_timestamp"

    log_debug "Running: $cmd"

    local output
    output=$(eval "$cmd" 2>&1) || true

    if [ -n "$output" ]; then
        echo "$output"
        return 0
    else
        # Check if it's just "no previous logs" error
        if echo "$output" | grep -q "previous terminated container.*not found"; then
            log_debug "No previous logs for $pod_name"
            echo ""
            return 0
        else
            log_debug "No logs returned for $pod_name"
            echo ""
            return 0
        fi
    fi
}

# Create JSON output for a pod
create_pod_json() {
    local pod_name="$1"
    local pod_json="$2"
    local logs="$3"
    local events="$4"
    local previous_logs="$5"

    local timestamp
    timestamp=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

    cat <<EOF
{
  "collection_timestamp": "$timestamp",
  "cluster": "$CLUSTER",
  "namespace": "$NAMESPACE",
  "pod": {
    "name": "$pod_name",
    $pod_json
  },
  "logs": $(echo "$logs" | jq -Rs '.' | jq 'split("\n")' | jq 'map(select(length > 0))'),
  "previous_logs": $(echo "$previous_logs" | jq -Rs '.' | jq 'split("\n")' | jq 'map(select(length > 0))'),
  "events": $events,
  "log_metadata": {
    "date_range": {
      "start": "$SINCE_DATE",
      "end": "$UNTIL_DATE"
    },
    "source": "kubectl",
    "include_history": $INCLUDE_HISTORY
  }
}
EOF
}

# Create JSONL output for a pod
create_pod_jsonl() {
    local pod_name="$1"
    local pod_json="$2"
    local logs="$3"
    local events="$4"
    local previous_logs="$5"

    local timestamp
    timestamp=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

    # Create metadata line
    echo "{\"type\":\"metadata\",\"collection_timestamp\":\"$timestamp\",\"cluster\":\"$CLUSTER\",\"namespace\":\"$NAMESPACE\",\"pod_name\":\"$pod_name\",\"date_range_start\":\"$SINCE_DATE\",\"date_range_end\":\"$UNTIL_DATE\"}"

    # Create log lines (simplified approach without complex jq)
    if [ -n "$logs" ]; then
        local log_count=0
        while IFS= read -r log_line; do
            if [ -n "$log_line" ]; then
                log_count=$((log_count + 1))
                # Simple JSON escaping - replace quotes and newlines
                local escaped_log
                escaped_log=$(echo "$log_line" | sed 's/\\/\\\\/g' | sed 's/"/\\"/g' | tr -d '\n' | tr -d '\r')
                echo "{\"type\":\"log_entry\",\"timestamp\":\"$timestamp\",\"cluster\":\"$CLUSTER\",\"namespace\":\"$NAMESPACE\",\"pod_name\":\"$pod_name\",\"log_stream\":\"current\",\"line_number\":$log_count,\"content\":\"$escaped_log\"}"
            fi
        done <<< "$logs"
    fi

    # Create previous log lines
    if [ -n "$previous_logs" ]; then
        local prev_log_count=0
        while IFS= read -r log_line; do
            if [ -n "$log_line" ]; then
                prev_log_count=$((prev_log_count + 1))
                local escaped_log
                escaped_log=$(echo "$log_line" | sed 's/\\/\\\\/g' | sed 's/"/\\"/g' | tr -d '\n' | tr -d '\r')
                echo "{\"type\":\"log_entry\",\"timestamp\":\"$timestamp\",\"cluster\":\"$CLUSTER\",\"namespace\":\"$NAMESPACE\",\"pod_name\":\"$pod_name\",\"log_stream\":\"previous\",\"line_number\":$prev_log_count,\"content\":\"$escaped_log\"}"
            fi
        done <<< "$previous_logs"
    fi

    # Create event lines - skip if events are empty or invalid
    if [ -n "$events" ] && [ "$events" != "null" ]; then
        echo "$events" | jq -r '.items[]? | select(. != null) | {
            type: "event",
            timestamp: (.lastTimestamp // .eventTime // "unknown"),
            cluster: "'"$CLUSTER"'",
            namespace: "'"$NAMESPACE"'",
            pod_name: "'"$pod_name"'",
            event_type: (.type // "Unknown"),
            reason: (.reason // "Unknown"),
            message: (.message // ""),
            source: (.source.component // "unknown")
        }' 2>/dev/null || true
    fi
}

# Process a single pod
process_pod() {
    local pod_name="$1"
    local pod_metadata="$2"
    local output_file="$3"

    log_info "Processing pod: $pod_name"

    # Fetch current logs
    local current_logs
    current_logs=$(fetch_pod_logs "$pod_name")

    # Fetch previous logs if history is enabled
    local previous_logs=""
    if [ "$INCLUDE_HISTORY" = true ]; then
        previous_logs=$(fetch_pod_logs "$pod_name" "" true)
    fi

    # Get events
    local events
    events=$(get_pod_events "$pod_name")

    # Output in requested format
    if [ "$OUTPUT_FORMAT" = "json" ]; then
        create_pod_json "$pod_name" "$pod_metadata" "$current_logs" "$events" "$previous_logs" >> "$output_file"
        echo "," >> "$output_file"
    else
        create_pod_jsonl "$pod_name" "$pod_metadata" "$current_logs" "$events" "$previous_logs" >> "$output_file"
    fi
}

# Main execution
main() {
    parse_args "$@"

    log_info "=== pbx-web Log Retrieval ==="
    log_info "Cluster: $CLUSTER"
    log_info "Namespace: $NAMESPACE"
    log_info "Date range: $SINCE_DATE to $UNTIL_DATE ($DAYS days)"
    log_info "Output format: $OUTPUT_FORMAT"
    log_info "Include history: $INCLUDE_HISTORY"
    log_info "Output directory: $OUTPUT_DIR"
    echo ""

    setup_output_dir

    # Get pods
    local pods_json
    if ! pods_json=$(get_pods); then
        log_error "Failed to fetch pods from namespace: $NAMESPACE"
        exit 1
    fi

    if [ -z "$pods_json" ]; then
        log_error "No pods found in namespace: $NAMESPACE"
        exit 1
    fi

    # Count pods
    local pod_count
    pod_count=$(echo "$pods_json" | jq -r '.items | length')
    if [ "$pod_count" -eq 0 ]; then
        log_error "No pods found in namespace: $NAMESPACE"
        exit 1
    fi
    log_info "Found $pod_count pods"

    # Setup output file
    local timestamp
    timestamp=$(date -u +"%Y%m%d-%H%M%S")
    local output_file="$OUTPUT_DIR/pbx-web-logs-${timestamp}.${OUTPUT_FORMAT}"

    # Initialize JSON array if needed
    if [ "$OUTPUT_FORMAT" = "json" ]; then
        echo "[" > "$output_file"
    fi

    # Process each pod
    local processed=0
    while IFS= read -r pod_name; do
        if [ -n "$pod_name" ]; then
            log_debug "Processing pod: $pod_name"

            local pod_metadata
            pod_metadata=$(echo "$pods_json" | jq -r ".items[] | select(.metadata.name == \"$pod_name\")")

            if [ -n "$pod_metadata" ] && [ "$pod_metadata" != "null" ]; then
                process_pod "$pod_name" "$pod_metadata" "$output_file"
                processed=$((processed + 1))
                log_debug "Completed pod: $pod_name"
            else
                log_warn "Could not find metadata for pod: $pod_name"
            fi
        fi
    done < <(echo "$pods_json" | jq -r '.items[] | .metadata.name')

    # Close JSON array if needed
    if [ "$OUTPUT_FORMAT" = "json" ]; then
        # Remove trailing comma and close array
        sed -i '$ s/,$//' "$output_file"
        echo "]" >> "$output_file"
    fi

    log_info "=== Log Retrieval Complete ==="
    log_info "Processed $processed pods"
    log_info "Output saved to: $output_file"
    log_info "File size: $(wc -c < "$output_file") bytes"

    # Create summary metadata
    local summary_file="$OUTPUT_DIR/fetch-summary-${timestamp}.json"
    cat > "$summary_file" <<EOF
{
  "collection_timestamp": "$(date -u +"%Y-%m-%dT%H:%M:%SZ")",
  "cluster": "$CLUSTER",
  "namespace": "$NAMESPACE",
  "date_range": {
    "start": "$SINCE_DATE",
    "end": "$UNTIL_DATE",
    "days": $DAYS
  },
  "pods_processed": $processed,
  "output_file": "$output_file",
  "output_format": "$OUTPUT_FORMAT",
  "include_history": $INCLUDE_HISTORY,
  "command": "$(basename "$0") $@"
}
EOF

    log_info "Summary saved to: $summary_file"
}

# Run main function
main "$@"