#!/bin/bash
# Pod Log Fetcher
# Fetches logs from Kubernetes pods with proper error handling, metadata, and timeout support
# Usage: ./fetch_pod_logs.sh <pod-name> <namespace> [kubeconfig-context]

set -euo pipefail

# Configuration
POD_NAME="${1}"
NAMESPACE="${2}"
KUBECONFIG_CONTEXT="${3:-http://traefik-ardenone-cluster:8001}"
TIMEOUT_SECONDS=30
TEMP_DIR="/tmp/pod-logs-$(date +%Y%m%d-%H%M%S)"
METADATA_FILE=""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
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

# Create temporary directory
mkdir -p "${TEMP_DIR}"

# Generate metadata header
create_metadata_header() {
    local log_type="$1"
    local timestamp=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

    cat <<EOF
# Log metadata
# Pod: ${POD_NAME}
# Namespace: ${NAMESPACE}
# Cluster: ardenone-cluster
# Fetched at: ${timestamp}
# Log type: ${log_type}
# Previous logs flag: ${log_type}
# ---
EOF
}

# Fetch current logs
fetch_current_logs() {
    local output_file="${TEMP_DIR}/${POD_NAME}-current.log"
    METADATA_FILE="${output_file}"

    log_info "Fetching current logs for ${POD_NAME}..."

    # Create metadata header
    create_metadata_header "current" > "${output_file}"

    # Fetch logs with timeout
    if timeout "${TIMEOUT_SECONDS}" kubectl --server="${KUBECONFIG_CONTEXT}" logs "${POD_NAME}" -n "${NAMESPACE}" >> "${output_file}" 2>&1; then
        local log_size=$(wc -c < "${output_file}")
        log_info "✓ Current logs fetched successfully (${log_size} bytes)"
        return 0
    else
        local exit_code=$?
        if [ $exit_code -eq 124 ]; then
            log_error "Timeout after ${TIMEOUT_SECONDS} seconds"
            echo "[TIMEOUT] Command timed out after ${TIMEOUT_SECONDS} seconds" >> "${output_file}"
        else
            log_error "Failed to fetch current logs (exit code: ${exit_code})"
            echo "[ERROR] Failed to fetch logs (exit code: ${exit_code})" >> "${output_file}"
        fi
        return 1
    fi
}

# Fetch previous logs (from restarted containers)
fetch_previous_logs() {
    local output_file="${TEMP_DIR}/${POD_NAME}-previous.log"

    log_info "Fetching previous logs for ${POD_NAME}..."

    # Create metadata header
    create_metadata_header "previous" > "${output_file}"

    # Fetch previous logs with timeout
    if timeout "${TIMEOUT_SECONDS}" kubectl --server="${KUBECONFIG_CONTEXT}" logs "${POD_NAME}" -n "${NAMESPACE}" --previous=true >> "${output_file}" 2>&1; then
        local log_size=$(wc -c < "${output_file}")
        # Check if we got actual logs or just an error message
        if grep -q "previous terminated container.*not found" "${output_file}"; then
            log_warn "No previous container logs found (pod has not restarted)"
            echo "[INFO] No previous container logs available - pod has not restarted" >> "${output_file}"
            return 0
        else
            log_info "✓ Previous logs fetched successfully (${log_size} bytes)"
            return 0
        fi
    else
        local exit_code=$?
        if [ $exit_code -eq 124 ]; then
            log_error "Timeout after ${TIMEOUT_SECONDS} seconds"
            echo "[TIMEOUT] Command timed out after ${TIMEOUT_SECONDS} seconds" >> "${output_file}"
        else
            log_warn "Failed to fetch previous logs (exit code: ${exit_code})"
            echo "[ERROR] Failed to fetch previous logs (exit code: ${exit_code})" >> "${output_file}"
        fi
        return 1
    fi
}

# Verify pod exists and get info
verify_pod() {
    log_info "Verifying pod ${POD_NAME} in namespace ${NAMESPACE}..."

    if kubectl --server="${KUBECONFIG_CONTEXT}" get pod "${POD_NAME}" -n "${NAMESPACE}" &>/dev/null; then
        log_info "✓ Pod found"
        return 0
    else
        log_error "Pod ${POD_NAME} not found in namespace ${NAMESPACE}"
        return 1
    fi
}

# Main execution
main() {
    log_info "Starting log collection for pod: ${POD_NAME}"
    log_info "Namespace: ${NAMESPACE}"
    log_info "Kubectl context: ${KUBECONFIG_CONTEXT}"
    log_info "Temporary directory: ${TEMP_DIR}"
    echo ""

    # Verify pod exists
    if ! verify_pod; then
        log_error "Pod verification failed. Creating error report..."
        mkdir -p "${TEMP_DIR}"
        echo "# Log metadata" > "${TEMP_DIR}/${POD_NAME}-error.log"
        echo "# Pod: ${POD_NAME}" >> "${TEMP_DIR}/${POD_NAME}-error.log"
        echo "# Namespace: ${NAMESPACE}" >> "${TEMP_DIR}/${POD_NAME}-error.log"
        echo "# Fetched at: $(date -u +"%Y-%m-%dT%H:%M:%SZ")" >> "${TEMP_DIR}/${POD_NAME}-error.log"
        echo "# Status: POD_NOT_FOUND" >> "${TEMP_DIR}/${POD_NAME}-error.log"
        echo "# ---" >> "${TEMP_DIR}/${POD_NAME}-error.log"
        echo "[ERROR] Pod ${POD_NAME} not found in namespace ${NAMESPACE}" >> "${TEMP_DIR}/${POD_NAME}-error.log"
        echo "${TEMP_DIR}"
        return 1
    fi

    # Fetch current logs
    fetch_current_logs
    local current_status=$?

    echo ""

    # Fetch previous logs
    fetch_previous_logs
    local previous_status=$?

    echo ""
    log_info "Log collection complete"
    log_info "Logs stored in: ${TEMP_DIR}"

    # Summary
    if [ $current_status -eq 0 ] || [ $previous_status -eq 0 ]; then
        log_info "✓ At least one log type collected successfully"
        echo "${TEMP_DIR}"
        return 0
    else
        log_error "Failed to collect any logs"
        echo "${TEMP_DIR}"
        return 1
    fi
}

# Run main function
main "$@"