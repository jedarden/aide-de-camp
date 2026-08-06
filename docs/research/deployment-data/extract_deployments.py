#!/usr/bin/env python3
"""Extract deployment history from Kubernetes ReplicaSets for pbx-web and whisper-stt."""

import json
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path


def get_replicasets(namespace, label):
    """Get ReplicaSets for a deployment."""
    cmd = [
        "kubectl",
        "--server=http://traefik-ardenone-cluster:8001",
        "get", "replicaset",
        "-n", namespace,
        "-l", label,
        "-o", "json",
        "--sort-by=.metadata.creationTimestamp"
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return json.loads(result.stdout)


def extract_deployment_info(replicaset_json):
    """Extract deployment info from a ReplicaSet."""
    metadata = replicaset_json.get("metadata", {})
    annotations = metadata.get("annotations", {})

    revision = annotations.get("deployment.kubernetes.io/revision")
    creation_ts = metadata.get("creationTimestamp")
    name = metadata.get("name")

    # Extract image from the first container
    containers = replicaset_json.get("spec", {}).get("template", {}).get("spec", {}).get("containers", [])
    image = containers[0].get("image") if containers else None

    # Check if this ReplicaSet was ever used (replicas > 0 at some point)
    # We can infer this if it has a revision annotation
    was_deployed = revision is not None

    return {
        "name": name,
        "revision": revision,
        "creationTimestamp": creation_ts,
        "image": image,
        "was_deployed": was_deployed
    }


def filter_last_30_days(deployments):
    """Filter deployments to only include those from the last 30 days."""
    cutoff = datetime.utcnow() - timedelta(days=30)
    filtered = []

    for deployment in deployments:
        if deployment.get("creationTimestamp"):
            # Parse ISO timestamp (Z = UTC)
            ts_str = deployment["creationTimestamp"].replace("Z", "")
            ts = datetime.fromisoformat(ts_str)
            # Compare naive datetimes (both in UTC)
            if ts >= cutoff:
                filtered.append(deployment)

    return filtered


def main():
    services = [
        {"name": "pbx-web", "namespace": "pbx-web", "label": "app=pbx-web"},
        {"name": "whisper-stt", "namespace": "whisper-stt", "label": "app=whisper-stt"}
    ]

    output_dir = Path(__file__).parent

    for service in services:
        print(f"Fetching ReplicaSets for {service['name']}...")

        try:
            replicasets = get_replicasets(service["namespace"], service["label"])
            items = replicasets.get("items", [])

            deployments = []
            for rs in items:
                info = extract_deployment_info(rs)
                if info.get("was_deployed"):
                    deployments.append(info)

            # Sort by creation timestamp (newest first)
            deployments.sort(key=lambda x: x.get("creationTimestamp", ""), reverse=True)

            # Filter to last 30 days
            recent_deployments = filter_last_30_days(deployments)

            output_file = output_dir / f"{service['name']}-deployments.json"
            with open(output_file, "w") as f:
                json.dump(recent_deployments, f, indent=2)

            print(f"  Found {len(deployments)} total deployments")
            print(f"  Found {len(recent_deployments)} deployments in last 30 days")
            print(f"  Saved to {output_file}")

            if recent_deployments:
                oldest = min(d["creationTimestamp"] for d in recent_deployments)
                newest = max(d["creationTimestamp"] for d in recent_deployments)
                print(f"  Date range: {oldest} to {newest}")

        except subprocess.CalledProcessError as e:
            print(f"  Error fetching ReplicaSets: {e}", file=sys.stderr)
            continue


if __name__ == "__main__":
    main()
