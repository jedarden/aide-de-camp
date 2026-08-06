#!/usr/bin/env python3
"""
Format pbx-web workflow metadata into structured deployment log.
Reads from research/pbx-web-workflows-raw.json and outputs to research/pbx-web-deployments-30days.json
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List


def calculate_duration(started_at: str, finished_at: str) -> float:
    """Calculate duration in seconds between two ISO timestamps."""
    if not started_at or not finished_at:
        return None

    try:
        start = datetime.fromisoformat(started_at.replace('Z', '+00:00'))
        finish = datetime.fromisoformat(finished_at.replace('Z', '+00:00'))
        return (finish - start).total_seconds()
    except (ValueError, AttributeError):
        return None


def format_deployment_entry(workflow: Dict[str, Any]) -> Dict[str, Any]:
    """Convert a workflow object into a deployment log entry."""
    status = workflow.get("status", {})
    metadata = workflow.get("metadata", {})

    deployment_id = metadata.get("name", "unknown")
    started_at = status.get("startedAt")
    finished_at = status.get("finishedAt")
    phase = status.get("phase", "Unknown")
    message = status.get("message", "")

    entry = {
        "deployment_id": deployment_id,
        "timestamp": started_at,
        "duration": calculate_duration(started_at, finished_at),
        "status": phase,
        "error_message": message if phase in ["Failed", "Error"] else None
    }

    return entry


def main():
    # Paths
    workspace = Path("/home/coding/aide-de-camp")
    input_file = workspace / "research" / "pbx-web-workflows-raw.json"
    output_file = workspace / "research" / "pbx-web-deployments-30days.json"

    # Read intermediate workflow data
    with open(input_file, 'r') as f:
        workflow_data = json.load(f)

    workflows = workflow_data.get("workflows", [])
    context = workflow_data.get("context", {})
    summary = workflow_data.get("summary", {})

    # Filter for pbx-web-build workflows only
    pbx_web_workflows = [
        wf for wf in workflows
        if wf.get("spec", {}).get("workflowTemplateRef", {}).get("name") == "pbx-web-build"
    ]

    # Format deployment entries
    deployments = [format_deployment_entry(wf) for wf in pbx_web_workflows]

    # Sort by timestamp (newest first)
    deployments.sort(key=lambda x: x["timestamp"] or "", reverse=True)

    # Create output structure
    output = {
        "deployments": deployments,
        "summary": {
            "total_deployment_count": len(deployments),
            "time_period": {
                "start": "2026-07-06T00:00:00Z",
                "end": "2026-08-06T23:59:59Z",
                "requested_lookback_days": 30
            },
            "data_availability": {
                "status": "no_data_found" if len(deployments) == 0 else "success",
                "reason": "workflow_retention_policy" if len(deployments) == 0 else "data_available",
                "cluster_workflows_found": summary.get("total_count", 0),
                "pbx_web_workflows_found": len(deployments)
            },
            "findings": context.get("findings", {}),
            "alternatives_considered": context.get("recommendations", [])
        },
        "metadata": {
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "source": str(input_file.name),
            "cluster": "iad-ci",
            "namespace": "argo-workflows",
            "workflow_template": "pbx-web-build",
            "note": "Deployment log derived from Argo workflow metadata" if len(deployments) > 0 else "No pbx-web-build workflow runs found in available retention window"
        }
    }

    # Write output
    with open(output_file, 'w') as f:
        json.dump(output, f, indent=2)

    print(f"✅ Formatted {len(deployments)} deployment entries")
    print(f"📁 Output saved to: {output_file}")

    if len(deployments) == 0:
        print("⚠️  No pbx-web-build workflows found - retention policy limits analysis to ~10 days")


if __name__ == "__main__":
    main()