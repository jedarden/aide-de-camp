#!/usr/bin/env python3
"""Extract whisper-stt deployment records from JSON data."""

import json
from datetime import datetime
from pathlib import Path


def parse_timestamp(ts_str: str) -> str:
    """Parse timestamp to ISO format."""
    if ts_str:
        return ts_str
    return ""


def map_status(status: str, replicas: int) -> str:
    """Map replicaSet status to success/failed."""
    if status == "active" and replicas > 0:
        return "success"
    elif status == "inactive" or replicas == 0:
        # Inactive with 0 replicas means it was rolled over or failed
        return "failed"
    else:
        return "unknown"


def extract_image_tag(image: str) -> str:
    """Extract image tag from full image string."""
    if not image:
        return ""
    if ":" in image:
        return image.split(":")[-1]
    return "latest"


def main():
    # Read source data
    source_file = Path("/home/coding/aide-de-camp/whisper-stt-deployment-data-30days.json")
    output_file = Path("/home/coding/aide-de-camp/docs/research/deployment-data/whisper-stt-deployments.json")

    with open(source_file, "r") as f:
        data = json.load(f)

    deployments = []

    # Extract from deployment_history_30_days.replicasets
    replicasets = data.get("deployment_history_30_days", {}).get("replicasets", [])

    for rs in replicasets:
        timestamp = parse_timestamp(rs.get("created", ""))
        image = rs.get("image", "")
        image_tag = extract_image_tag(image)
        status = rs.get("status", "")
        replicas = rs.get("replicas", 0)
        deployment_status = map_status(status, replicas)

        deployment = {
            "timestamp": timestamp,
            "image_tag": image_tag,
            "status": deployment_status,
            "duration_seconds": None,  # No duration data for ReplicaSets
            "image": image,
            "revision": rs.get("revision"),
            "replicaSet": rs.get("name"),
            "deployment": rs.get("deployment"),
            "replicas": replicas,
            "readyReplicas": rs.get("readyReplicas"),
            "availableReplicas": rs.get("availableReplicas")
        }

        deployments.append(deployment)

    # Sort by timestamp
    deployments.sort(key=lambda x: x["timestamp"])

    # Write output
    output_data = {
        "service": "whisper-stt",
        "namespace": "whisper-stt",
        "cluster": "ardenone-cluster",
        "extracted_at": datetime.utcnow().isoformat() + "Z",
        "total_deployments": len(deployments),
        "deployments": deployments
    }

    with open(output_file, "w") as f:
        json.dump(output_data, f, indent=2)

    print(f"Extracted {len(deployments)} whisper-stt deployment records to {output_file}")


if __name__ == "__main__":
    main()
