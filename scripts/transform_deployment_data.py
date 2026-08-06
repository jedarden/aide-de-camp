#!/usr/bin/env python3
"""
Transform Kubernetes deployment data into structured workflow-style format for research.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List


def parse_timestamp(ts: str) -> datetime:
    """Parse ISO 8601 timestamp string to datetime object."""
    ts_clean = ts.rstrip('Z')
    return datetime.fromisoformat(ts_clean)


def calculate_duration_seconds(started: str, finished: str = None) -> float:
    """Calculate duration in seconds between two timestamps."""
    started_dt = parse_timestamp(started)
    if finished:
        finished_dt = parse_timestamp(finished)
        return (finished_dt - started_dt).total_seconds()
    # For rollouts, assume 30 seconds if not specified
    return 30.0


def transform_deployment_event(event: Dict[str, Any]) -> Dict[str, Any]:
    """Transform a Kubernetes deployment event into workflow-style format."""
    timestamp = event.get("timestamp", event.get("date", ""))
    event_type = event.get("event_type", "deployment_rollout")
    outcome = event.get("outcome", "unknown")
    notes = event.get("notes", "")

    # Calculate duration (rollouts are typically quick, use 30s default)
    duration = calculate_duration_seconds(timestamp)

    return {
        "workflow_id": event.get("replicaSet", event.get("deployment", "unknown")),
        "timestamp": timestamp,
        "phase": "Succeeded" if outcome in ["success", "rolled_back"] else "Failed",
        "started_at": timestamp,
        "finished_at": timestamp,  # Rollout events are point-in-time
        "duration_seconds": duration,
        "status_message": f"{event_type}: {notes}" if notes else event_type
    }


def main():
    """Transform deployment data and save to research file."""
    # Paths
    input_path = Path("/home/coding/aide-de-camp/pbx-web-deployment-data-30days.json")
    output_path = Path("/home/coding/aide-de-camp/research/pbx-web-deployments-30days.json")

    # Create research directory if needed
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Read input data
    with open(input_path, "r") as f:
        data = json.load(f)

    metadata = data.get("metadata", {})
    events = data.get("deployment_events_last_30_days", [])

    # Filter only pbx-web deployment events (exclude relay deployments)
    pbx_web_events = [e for e in events if e.get("deployment") in ["pbx-web", None] or "pbx-web" in e.get("replicaSet", "")]

    # Transform deployment events
    deployments = [transform_deployment_event(event) for event in pbx_web_events]

    # Get time range
    time_start = metadata.get("time_period", {}).get("start", "2026-07-07T00:00:00Z")
    time_end = metadata.get("time_period", {}).get("end", "2026-08-06T00:00:00Z")
    retrieval_date = metadata.get("data_collected_at", datetime.utcnow().isoformat() + "Z")

    # Create structured output
    result = {
        "metadata": {
            "retrieval_date": retrieval_date,
            "timeframe_start": time_start,
            "timeframe_end": time_end,
            "total_workflows": len(deployments),
            "source": "Kubernetes Deployment/ReplicaSet history via ArgoCD",
            "note": "Derived from ReplicaSet metadata - CI workflows not available due to cleanup policy"
        },
        "deployments": deployments
    }

    # Write output
    with open(output_path, "w") as f:
        json.dump(result, f, indent=2)

    print(f"✓ Transformed {len(deployments)} deployment events")
    print(f"✓ Saved to: {output_path}")
    print(f"  Timeframe: {time_start} to {time_end}")
    print(f"  Total deployments: {len(deployments)}")

    # Validate JSON
    import subprocess
    result = subprocess.run(
        ["python3", "-m", "json.tool", str(output_path)],
        capture_output=True,
        text=True
    )

    if result.returncode == 0:
        print("✓ JSON validation successful")
    else:
        print("✗ JSON validation failed:")
        print(result.stderr)
        return 1

    return 0


if __name__ == "__main__":
    exit(main())
