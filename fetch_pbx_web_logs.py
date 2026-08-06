#!/usr/bin/env python3
"""
Fetch pbx-web deployment logs for the last 30 days.

This script retrieves logs from pbx-web, lab-rebuild-relay, and pbx-rebuild-relay pods,
plus deployment history and events, then outputs them in JSONL format.
"""

import subprocess
import json
import re
from datetime import datetime, timedelta
from typing import List, Dict, Any

def run_kubectl(cmd: List[str]) -> str:
    """Run kubectl command and return stdout."""
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        check=False
    )
    return result.stdout

def parse_log_line(line: str, pod_name: str, namespace: str) -> Dict[str, Any]:
    """Parse a log line into structured JSONL format."""
    entry = {
        "timestamp": None,
        "pod_name": pod_name,
        "namespace": namespace,
        "log_level": "INFO",
        "message": line.strip(),
        "service": "pbx-web"
    }

    # Try to extract timestamp from line
    # Format: 2026-07-10T13:39:33.767796087-04:00 INFO: ...
    ts_match = re.match(r'^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d+[-+]\d{2}:\d{2})', line)
    if ts_match:
        entry["timestamp"] = ts_match.group(1)

        # Extract log level if present
        level_match = re.search(r'\b(INFO|WARNING|ERROR|DEBUG)\b:', line[ts_match.end():])
        if level_match:
            entry["log_level"] = level_match.group(1)
            entry["message"] = line[ts_match.end() + level_match.end():].strip()

    return entry

def get_pod_logs(namespace: str, pod_name: str) -> List[Dict[str, Any]]:
    """Fetch logs from a specific pod."""
    print(f"Fetching logs from pod {pod_name}...")

    cmd = [
        "kubectl", "--server=http://traefik-ardenone-manager:8001",
        "logs", "-n", namespace, pod_name,
        "--timestamps"
    ]

    output = run_kubectl(cmd)
    lines = output.strip().split('\n') if output.strip() else []

    entries = []
    for line in lines:
        if line.strip():
            entry = parse_log_line(line, pod_name, namespace)
            entries.append(entry)

    return entries

def get_pods(namespace: str) -> List[Dict[str, Any]]:
    """Get all pods in a namespace."""
    cmd = [
        "kubectl", "--server=http://traefik-ardenone-manager:8001",
        "get", "pods", "-n", namespace,
        "-o", "json"
    ]

    output = run_kubectl(cmd)
    if not output.strip():
        return []

    data = json.loads(output)
    return data.get("items", [])

def get_replica_sets(namespace: str) -> List[Dict[str, Any]]:
    """Get replica sets for pod history."""
    cmd = [
        "kubectl", "--server=http://traefik-ardenone-manager:8001",
        "get", "replicasets", "-n", namespace,
        "-o", "json"
    ]

    output = run_kubectl(cmd)
    if not output.strip():
        return []

    data = json.loads(output)
    return data.get("items", [])

def get_deployments(namespace: str) -> List[Dict[str, Any]]:
    """Get deployments."""
    cmd = [
        "kubectl", "--server=http://traefik-ardenone-manager:8001",
        "get", "deployments", "-n", namespace,
        "-o", "json"
    ]

    output = run_kubectl(cmd)
    if not output.strip():
        return []

    data = json.loads(output)
    return data.get("items", [])

def create_deployment_event(deployment: Dict[str, Any], event_type: str) -> Dict[str, Any]:
    """Create a deployment event entry."""
    metadata = deployment.get("metadata", {})
    spec = deployment.get("spec", {})
    status = deployment.get("status", {})

    return {
        "timestamp": metadata.get("creationTimestamp"),
        "pod_name": None,
        "namespace": metadata.get("namespace"),
        "log_level": "INFO",
        "message": f"Deployment {event_type}: {metadata.get('name')} - Replicas: {status.get('replicas', 'unknown')}/{status.get('updatedReplicas', 'unknown')}",
        "service": "pbx-web",
        "event_type": event_type,
        "deployment_name": metadata.get("name"),
        "replicas": status.get("replicas"),
        "available_replicas": status.get("availableReplicas"),
        "updated_replicas": status.get("updatedReplicas")
    }

def main():
    namespace = "pbx-web"
    all_entries = []

    print("=== Fetching pbx-web deployment logs ===\n")

    # Get current pods
    print("Fetching current pods...")
    pods = get_pods(namespace)

    for pod in pods:
        pod_name = pod.get("metadata", {}).get("name")
        pod_age = pod.get("metadata", {}).get("creationTimestamp")

        print(f"  Found pod: {pod_name} (created: {pod_age})")

        # Get logs from this pod
        try:
            entries = get_pod_logs(namespace, pod_name)
            print(f"    Retrieved {len(entries)} log entries")
            all_entries.extend(entries)
        except Exception as e:
            print(f"    Error fetching logs: {e}")

    # Get deployment info
    print("\nFetching deployment information...")
    deployments = get_deployments(namespace)

    for deployment in deployments:
        event = create_deployment_event(deployment, "status")
        all_entries.append(event)
        print(f"  Added deployment status: {event['deployment_name']}")

    # Get replica set info for pod restart history
    print("\nFetching replica set history...")
    replicasets = get_replica_sets(namespace)

    for rs in replicasets:
        metadata = rs.get("metadata", {})
        name = metadata.get("name")
        creation_time = metadata.get("creationTimestamp")
        replicas = rs.get("spec", {}).get("replicas")

        event = {
            "timestamp": creation_time,
            "pod_name": None,
            "namespace": namespace,
            "log_level": "INFO",
            "message": f"ReplicaSet {name} - Replicas: {replicas}",
            "service": "pbx-web",
            "event_type": "replicaset",
            "replicaset_name": name,
            "replicas": replicas
        }
        all_entries.append(event)

    # Sort entries by timestamp
    print(f"\nTotal entries collected: {len(all_entries)}")

    # Filter entries within last 30 days
    # Use timezone-aware datetime for comparison
    cutoff_date = datetime.now(tz=datetime.now().astimezone().tzinfo) - timedelta(days=30)
    filtered_entries = []

    for entry in all_entries:
        ts_str = entry.get("timestamp")
        if ts_str:
            try:
                # Parse timestamp like "2026-07-10T13:39:33.767796087-04:00"
                ts = datetime.fromisoformat(ts_str)
                # Make both datetimes timezone-aware for comparison
                if ts.tzinfo is not None and cutoff_date.tzinfo is None:
                    cutoff_date = cutoff_date.replace(tzinfo=ts.tzinfo)
                elif ts.tzinfo is None and cutoff_date.tzinfo is not None:
                    ts = ts.replace(tzinfo=cutoff_date.tzinfo)
                if ts >= cutoff_date:
                    filtered_entries.append(entry)
            except ValueError:
                # If we can't parse the timestamp, keep the entry
                filtered_entries.append(entry)
        else:
            # No timestamp, keep the entry
            filtered_entries.append(entry)

    print(f"Entries within last 30 days: {len(filtered_entries)}")

    # Write to JSONL file
    output_file = "/home/coding/aide-de-camp/data/pbx-web-logs.jsonl"
    print(f"\nWriting to {output_file}...")

    with open(output_file, 'w') as f:
        for entry in filtered_entries:
            f.write(json.dumps(entry) + '\n')

    print(f"Done! Wrote {len(filtered_entries)} entries to {output_file}")

    # Print summary
    if filtered_entries:
        print("\n=== Log Summary ===")
        timestamps = [e.get("timestamp") for e in filtered_entries if e.get("timestamp")]
        if timestamps:
            print(f"Date range: {min(timestamps)} to {max(timestamps)}")

        pod_names = set(e.get("pod_name") for e in filtered_entries if e.get("pod_name"))
        print(f"Pods covered: {', '.join(pod_names)}")

        event_types = set(e.get("event_type", "log") for e in filtered_entries)
        print(f"Event types: {', '.join(event_types)}")

if __name__ == "__main__":
    main()
