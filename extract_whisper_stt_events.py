#!/usr/bin/env python3
"""
Parse whisper-stt logs and extract structured events.

Extracts:
- HTTP 5xx errors
- Pod restart events (OOMKilled, CrashLoopBackOff, etc.)
- Latency indicators (slow requests, timeouts, etc.)
"""

import json
import re
from datetime import datetime
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Any


def parse_timestamp(ts_str: str) -> str:
    """Parse and normalize timestamp."""
    # Timestamps are already in ISO format, just return them
    return ts_str


def extract_http_status(log_message: str) -> Dict[str, Any]:
    """Extract HTTP status code and method from log message."""
    # Pattern: INFO:     IP:PORT - "METHOD /path HTTP/1.1" STATUS
    pattern = r'"(\w+)\s+(\S+)\s+HTTP/[\d.]+"\s+(\d+)\s+(\S+)'
    match = re.search(pattern, log_message)

    if match:
        method, path, status, status_text = match.groups()
        return {
            "method": method,
            "path": path,
            "status_code": int(status),
            "status_text": status_text
        }
    return None


def classify_event(log_entry: Dict[str, Any]) -> Dict[str, Any]:
    """
    Classify a log entry as an event of interest.

    Returns None if the entry is not a significant event.
    """
    log_message = log_entry.get("log_message", "")
    timestamp = parse_timestamp(log_entry.get("timestamp", ""))

    # Extract HTTP status
    http_info = extract_http_status(log_message)

    # Check for HTTP 5xx errors
    if http_info and http_info["status_code"] >= 500:
        return {
            "event_type": "http_error",
            "severity": "error",
            "timestamp": timestamp,
            "pod_name": log_entry.get("pod_name"),
            "namespace": log_entry.get("namespace"),
            "details": {
                "status_code": http_info["status_code"],
                "method": http_info["method"],
                "path": http_info["path"],
                "status_text": http_info["status_text"],
                "raw_message": log_message
            }
        }

    # Check for HTTP 4xx errors
    if http_info and http_info["status_code"] >= 400 and http_info["status_code"] < 500:
        return {
            "event_type": "http_client_error",
            "severity": "warning",
            "timestamp": timestamp,
            "pod_name": log_entry.get("pod_name"),
            "namespace": log_entry.get("namespace"),
            "details": {
                "status_code": http_info["status_code"],
                "method": http_info["method"],
                "path": http_info["path"],
                "status_text": http_info["status_text"],
                "raw_message": log_message
            }
        }

    # Check for error/failure keywords
    error_patterns = [
        (r"OOMKilled", "pod_oom_kill"),
        (r"CrashLoopBackOff", "pod_crash_loop"),
        (r"Error from server", "kubernetes_error"),
        (r"exception", "application_exception"),
        (r"failed", "operation_failure"),
        (r"timeout", "timeout"),
    ]

    log_lower = log_message.lower()
    for pattern, event_type in error_patterns:
        if re.search(pattern, log_lower):
            return {
                "event_type": event_type,
                "severity": "error" if "error" in event_type or "fail" in event_type else "warning",
                "timestamp": timestamp,
                "pod_name": log_entry.get("pod_name"),
                "namespace": log_entry.get("namespace"),
                "details": {
                    "raw_message": log_message
                }
            }

    # Check for latency indicators
    latency_patterns = [
        r"slow request",
        r"high latency",
        r"took \d+ms",
        r"took \d+ seconds?",
        r"latency.*\d+ms",
    ]

    for pattern in latency_patterns:
        if re.search(pattern, log_lower):
            return {
                "event_type": "latency_issue",
                "severity": "warning",
                "timestamp": timestamp,
                "pod_name": log_entry.get("pod_name"),
                "namespace": log_entry.get("namespace"),
                "details": {
                    "raw_message": log_message
                }
            }

    # Check for pod lifecycle events
    lifecycle_patterns = [
        (r"pod started", "pod_started"),
        (r"pod stopped", "pod_stopped"),
        (r"pod restarted", "pod_restarted"),
        (r"container started", "container_started"),
        (r"container stopped", "container_stopped"),
    ]

    for pattern, event_type in lifecycle_patterns:
        if re.search(pattern, log_lower):
            return {
                "event_type": event_type,
                "severity": "info",
                "timestamp": timestamp,
                "pod_name": log_entry.get("pod_name"),
                "namespace": log_entry.get("namespace"),
                "details": {
                    "raw_message": log_message
                }
            }

    # Not a significant event
    return None


def main():
    input_file = Path("logs/whisper-stt-raw.jsonl")
    output_file = Path("logs/whisper-stt-events.jsonl")
    summary_file = Path("logs/whisper-stt-events-summary.json")

    if not input_file.exists():
        print(f"Error: {input_file} not found")
        return 1

    events = []
    stats = {
        "total_log_entries": 0,
        "events_by_type": defaultdict(int),
        "events_by_severity": defaultdict(int),
        "events_by_pod": defaultdict(int),
        "time_range": {
            "earliest": None,
            "latest": None
        }
    }

    print(f"Parsing {input_file}...")

    with open(input_file, "r") as f:
        for line_num, line in enumerate(f, 1):
            if not line.strip():
                continue

            stats["total_log_entries"] += 1

            try:
                log_entry = json.loads(line)
                event = classify_event(log_entry)

                if event:
                    events.append(event)
                    stats["events_by_type"][event["event_type"]] += 1
                    stats["events_by_severity"][event["severity"]] += 1
                    stats["events_by_pod"][event["pod_name"]] += 1

                    # Track time range
                    if stats["time_range"]["earliest"] is None:
                        stats["time_range"]["earliest"] = event["timestamp"]
                    stats["time_range"]["latest"] = event["timestamp"]

            except json.JSONDecodeError as e:
                print(f"Warning: Failed to parse line {line_num}: {e}")
                continue

            if line_num % 10000 == 0:
                print(f"  Processed {line_num} lines, found {len(events)} events")

    # Write events to JSONL
    print(f"\nWriting {len(events)} events to {output_file}...")
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, "w") as f:
        for event in events:
            f.write(json.dumps(event) + "\n")

    # Prepare summary statistics
    summary = {
        "total_log_entries": stats["total_log_entries"],
        "total_events": len(events),
        "events_by_type": dict(stats["events_by_type"]),
        "events_by_severity": dict(stats["events_by_severity"]),
        "events_by_pod": dict(stats["events_by_pod"]),
        "time_range": stats["time_range"],
        "parsing_timestamp": datetime.utcnow().isoformat()
    }

    # Write summary
    print(f"Writing summary to {summary_file}...")
    with open(summary_file, "w") as f:
        json.dump(summary, f, indent=2)

    # Print summary
    print("\n" + "=" * 60)
    print("EVENT EXTRACTION SUMMARY")
    print("=" * 60)
    print(f"Total log entries processed: {stats['total_log_entries']:,}")
    print(f"Total events extracted: {len(events):,}")
    print(f"\nEvents by type:")
    for event_type, count in sorted(stats["events_by_type"].items()):
        print(f"  {event_type}: {count:,}")
    print(f"\nEvents by severity:")
    for severity, count in sorted(stats["events_by_severity"].items()):
        print(f"  {severity}: {count:,}")
    print(f"\nTime range:")
    print(f"  Earliest: {stats['time_range']['earliest']}")
    print(f"  Latest: {stats['time_range']['latest']}")

    if len(events) == 0:
        print("\n" + "=" * 60)
        print("NO SIGNIFICANT EVENTS FOUND")
        print("=" * 60)
        print("The logs contain only routine health check requests (200 OK).")
        print("No errors, failures, or latency issues were detected.")

    return 0


if __name__ == "__main__":
    exit(main())
