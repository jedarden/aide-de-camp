#!/usr/bin/env python3
"""Extract pbx-web deployment records from JSON data."""

import json
from datetime import datetime
from pathlib import Path


def parse_timestamp(ts_str: str) -> str:
    """Parse timestamp to ISO format."""
    if ts_str:
        # Already in ISO format
        return ts_str
    return ""


def map_status(outcome: str, event_type: str) -> str:
    """Map outcome/event_type to success/failed status."""
    if outcome == "success" or outcome == "successful":
        return "success"
    elif outcome == "failed":
        return "failed"
    elif event_type == "deployment_rollback":
        return "failed"  # Rollback counts as failed deployment
    elif outcome == "rolled_back":
        return "failed"
    else:
        return "unknown"


def calculate_duration(started_at: str, finished_at: str) -> float:
    """Calculate duration in seconds between two timestamps."""
    if not started_at or not finished_at:
        return None

    try:
        start = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
        finish = datetime.fromisoformat(finished_at.replace("Z", "+00:00"))
        return (finish - start).total_seconds()
    except (ValueError, AttributeError):
        return None


def extract_image_tag(image: str) -> str:
    """Extract image tag from full image string."""
    if not image:
        return ""
    if ":" in image:
        return image.split(":")[-1]
    return "latest"


def main():
    # Read source data
    source_file = Path("/home/coding/aide-de-camp/pbx-web-deployment-data-30days.json")
    output_file = Path("/home/coding/aide-de-camp/docs/research/deployment-data/pbx-web-deployments.json")

    with open(source_file, "r") as f:
        data = json.load(f)

    deployments = []

    # Extract from deployment_events_last_30_days
    events = data.get("deployment_events_last_30_days", [])

    for event in events:
        timestamp = parse_timestamp(event.get("timestamp", ""))
        image = event.get("image", "")
        image_tag = extract_image_tag(image)
        outcome = event.get("outcome", "")
        event_type = event.get("event_type", "")
        status = map_status(outcome, event_type)

        deployment = {
            "timestamp": timestamp,
            "image_tag": image_tag,
            "status": status,
            "duration_seconds": None,  # No duration data for ReplicaSets
            "image": image,
            "revision": event.get("revision"),
            "replicaSet": event.get("replicaSet"),
            "pod_name": event.get("pod_name"),
            "event_type": event_type,
            "notes": event.get("notes", "")
        }

        deployments.append(deployment)

    # Sort by timestamp
    deployments.sort(key=lambda x: x["timestamp"])

    # Write output
    output_data = {
        "service": "pbx-web",
        "namespace": "pbx-web",
        "cluster": "ardenone-cluster",
        "extracted_at": datetime.utcnow().isoformat() + "Z",
        "total_deployments": len(deployments),
        "deployments": deployments
    }

    with open(output_file, "w") as f:
        json.dump(output_data, f, indent=2)

    print(f"Extracted {len(deployments)} pbx-web deployment records to {output_file}")


if __name__ == "__main__":
    main()
