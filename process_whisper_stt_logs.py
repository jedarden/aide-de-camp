#!/usr/bin/env python3
"""Process whisper-stt logs from kubectl and convert to JSONL format."""

import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

def fetch_pod_logs(pod_name, namespace="whisper-stt"):
    """Fetch logs from a specific pod with timestamps."""
    cmd = [
        "kubectl",
        "--server", "http://traefik-ardenone-cluster:8001",
        "logs",
        "-n", namespace,
        pod_name,
        "--tail=-1",  # All logs
        "--timestamps"
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if result.returncode != 0:
            print(f"Error fetching logs for {pod_name}: {result.stderr}", file=sys.stderr)
            return []
        return result.stdout.strip().split('\n')
    except subprocess.TimeoutExpired:
        print(f"Timeout fetching logs for {pod_name}", file=sys.stderr)
        return []
    except Exception as e:
        print(f"Exception fetching logs for {pod_name}: {e}", file=sys.stderr)
        return []

def parse_log_line(line, pod_name, namespace="whisper-stt"):
    """Parse a kubectl log line with timestamp into JSONL format."""
    if not line or line.startswith("Defaulted container"):
        return None

    # Match timestamp at the beginning of the line
    timestamp_match = re.match(r'^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d+[-+]\d{2}:\d{2}) (.+)', line)
    if not timestamp_match:
        return None

    timestamp_str = timestamp_match.group(1)
    log_message = timestamp_match.group(2)

    return {
        "timestamp": timestamp_str,
        "pod_name": pod_name,
        "namespace": namespace,
        "log_message": log_message,
        "source": "kubectl"
    }

def main():
    output_file = Path("logs/whisper-stt-all-raw.jsonl")
    output_file.parent.mkdir(parents=True, exist_ok=True)

    pods = [
        "whisper-openai-68966786fb-jsb5d",
        "whisper-stt-847fd8d7b9-v2rs5"
    ]

    all_logs = []
    stats = {
        "total_pods": len(pods),
        "successful_fetches": 0,
        "total_records": 0,
        "pods_with_logs": [],
        "pods_without_logs": [],
        "time_range": {"earliest": None, "latest": None}
    }

    for pod in pods:
        print(f"Fetching logs from pod: {pod}")
        log_lines = fetch_pod_logs(pod)

        if not log_lines or len(log_lines) == 0:
            print(f"  No logs found for {pod}")
            stats["pods_without_logs"].append(pod)
            continue

        print(f"  Processing {len(log_lines)} log lines from {pod}")
        pod_records = []

        for line in log_lines:
            parsed = parse_log_line(line, pod)
            if parsed:
                pod_records.append(parsed)

        if pod_records:
            all_logs.extend(pod_records)
            stats["successful_fetches"] += 1
            stats["pods_with_logs"].append(pod)
            stats["total_records"] += len(pod_records)

            # Track time range
            timestamps = [r["timestamp"] for r in pod_records]
            if timestamps:
                earliest = min(timestamps)
                latest = max(timestamps)

                if stats["time_range"]["earliest"] is None or earliest < stats["time_range"]["earliest"]:
                    stats["time_range"]["earliest"] = earliest
                if stats["time_range"]["latest"] is None or latest > stats["time_range"]["latest"]:
                    stats["time_range"]["latest"] = latest

            print(f"  Successfully processed {len(pod_records)} records from {pod}")
        else:
            print(f"  No valid log records found in {pod}")
            stats["pods_without_logs"].append(pod)

    # Write JSONL output
    print(f"\nWriting {len(all_logs)} records to {output_file}")
    with open(output_file, 'w') as f:
        for record in all_logs:
            f.write(json.dumps(record) + '\n')

    # Create summary
    summary = {
        "collection_timestamp": datetime.now().isoformat(),
        "cluster": "ardenone-cluster",
        "namespace": "whisper-stt",
        "stats": stats
    }

    summary_file = Path("logs/whisper-stt-all-summary.json")
    with open(summary_file, 'w') as f:
        json.dump(summary, f, indent=2)

    print(f"\nSummary written to {summary_file}")
    print(f"\nCollection Summary:")
    print(f"  Total pods: {stats['total_pods']}")
    print(f"  Pods with logs: {len(stats['pods_with_logs'])}")
    print(f"  Pods without logs: {len(stats['pods_without_logs'])}")
    print(f"  Total records: {stats['total_records']}")
    print(f"  Time range: {stats['time_range']['earliest']} to {stats['time_range']['latest']}")
    print(f"  Output file: {output_file}")

if __name__ == "__main__":
    main()