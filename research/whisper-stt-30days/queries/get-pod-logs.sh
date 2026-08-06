#!/bin/bash
# Collect whisper-stt pod logs day-by-day for the 30-day research period
# Time range: 2026-07-07 to 2026-08-06

NAMESPACE="${1:-whisper-stt}"
SELECTOR="${2:-app.kubernetes.io/name=whisper-stt}"
POD_LOGS_DIR="$(dirname "$0")/../pod-logs"

# Ensure output directory exists
mkdir -p "$POD_LOGS_DIR"

# Generate daily log files
current_date="2026-07-07"
end_date="2026-08-07"  # One day past to include full 2026-08-06

while [[ "$current_date" < "$end_date" ]]; do
    next_date=$(date -d "$current_date + 1 day" +%Y-%m-%d)
    output_file="$POD_LOGS_DIR/${current_date}.log"

    echo "Collecting logs for $current_date → $output_file"

    # Convert dates to Unix timestamps for --since-time and --until-time
    since_ts=$(date -d "${current_date}T00:00:00Z" +%s)
    until_ts=$(date -d "${current_date}T23:59:59Z" +%s)

    kubectl logs -n "$NAMESPACE" -l "$SELECTOR" \
      --since-time="$since_ts" \
      --until-time="$until_ts" \
      --timestamps=true \
      > "$output_file" 2>&1

    # Check if any logs were collected
    if [[ -s "$output_file" ]]; then
        log_size=$(wc -l < "$output_file")
        echo "  ✓ Collected $log_size lines"
    else
        echo "  ⚠ No logs found (check namespace/selector)"
    fi

    current_date="$next_date"
done

echo "Pod logs collection complete."
