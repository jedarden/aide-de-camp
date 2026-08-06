#!/usr/bin/env python3
"""
Extract deployment metadata from filtered workflows.
Parses workflows to extract: name, timestamps, phase, and image info.
"""

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional


def extract_image_info(workflow: Dict[str, Any]) -> Optional[str]:
    """
    Extract image digest/tag from workflow.
    Checks multiple locations where image info might be stored.
    """
    # Check status.nodes for build outputs with image digest
    status = workflow.get("status", {})
    nodes = status.get("nodes", {})

    for node_id, node in nodes.items():
        # Check outputs for image-related parameters
        outputs = node.get("outputs", {})
        parameters = outputs.get("parameters", [])

        for param in parameters:
            name = param.get("name", "")
            value = param.get("value", "")

            # Look for image digest or tag parameters
            if "image" in name.lower() or "digest" in name.lower() or "tag" in name.lower():
                if value and not value.startswith("{{"):
                    return value

        # Check artifacts for image references
        artifacts = outputs.get("artifacts", [])
        for artifact in artifacts:
            if "image" in artifact.get("name", "").lower():
                return artifact.get("digest", artifact.get("name"))

    # Check workflow-level outputs
    if "outputs" in status:
        outputs = status["outputs"]
        parameters = outputs.get("parameters", [])

        for param in parameters:
            name = param.get("name", "")
            value = param.get("value", "")

            if "image" in name.lower() or "digest" in name.lower():
                if value and not value.startswith("{{"):
                    return value

        artifacts = outputs.get("artifacts", [])
        for artifact in artifacts:
            if "image" in artifact.get("name", "").lower():
                return artifact.get("digest", artifact.get("name"))

    # Check spec.arguments.parameters for build-related info
    spec = workflow.get("spec", {})
    arguments = spec.get("arguments", {})
    parameters = arguments.get("parameters", [])

    for param in parameters:
        name = param.get("name", "")
        value = param.get("value", "")

        if "image" in name.lower() or "tag" in name.lower():
            if value and not value.startswith("{{"):
                return value

    return None


def extract_deployment_metadata(workflow: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract deployment metadata from a single workflow.
    """
    metadata = workflow.get("metadata", {})
    status = workflow.get("status", {})

    deployment = {
        "workflow_name": metadata.get("name", ""),
        "creationTimestamp": metadata.get("creationTimestamp"),
        "phase": status.get("phase"),
        "startedAt": status.get("startedAt"),
        "finishedAt": status.get("finishedAt"),
        "image_digest_tag": extract_image_info(workflow),
    }

    return deployment


def main():
    # Load filtered workflows
    input_file = Path("notes/adc-20tux-workflows-filtered.json")

    if not input_file.exists():
        print(f"Error: {input_file} not found")
        sys.exit(1)

    with open(input_file, "r") as f:
        data = json.load(f)

    workflows = data.get("filtered_items", [])

    print(f"Processing {len(workflows)} workflows...")

    # Extract metadata from each workflow
    deployments = []
    for workflow in workflows:
        deployment = extract_deployment_metadata(workflow)
        deployments.append(deployment)

    # Output results
    output_data = {
        "total_workflows": len(workflows),
        "deployments": deployments,
    }

    output_file = Path("notes/adc-yeect-deployment-metadata.json")
    with open(output_file, "w") as f:
        json.dump(output_data, f, indent=2)

    print(f"Extracted metadata for {len(deployments)} deployments")
    print(f"Output saved to {output_file}")

    # Print summary
    with_image = sum(1 for d in deployments if d["image_digest_tag"])
    finished = sum(1 for d in deployments if d["finishedAt"])

    print(f"\nSummary:")
    print(f"  Total deployments: {len(deployments)}")
    print(f"  With image info: {with_image}")
    print(f"  Finished: {finished}")
    print(f"  Still running: {len(deployments) - finished}")


if __name__ == "__main__":
    main()
