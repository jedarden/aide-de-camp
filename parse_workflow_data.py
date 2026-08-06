#!/usr/bin/env python3
"""
Parse Argo Workflow JSON and extract deployment metrics.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


def parse_timestamp(ts: Optional[str]) -> Optional[datetime]:
    """Parse ISO 8601 timestamp string to datetime object."""
    if not ts:
        return None
    try:
        # Remove 'Z' suffix if present and parse
        ts_clean = ts.rstrip('Z')
        return datetime.fromisoformat(ts_clean)
    except (ValueError, AttributeError):
        return None


def calculate_duration_seconds(started: Optional[datetime], finished: Optional[datetime]) -> Optional[float]:
    """Calculate duration in seconds between two timestamps."""
    if started and finished:
        return (finished - started).total_seconds()
    return None


def format_duration(seconds: Optional[float]) -> Optional[str]:
    """Format duration in seconds to human-readable string."""
    if seconds is None:
        return None
    if seconds < 60:
        return f"{seconds:.1f}s"
    elif seconds < 3600:
        mins = seconds / 60
        return f"{mins:.1f}m"
    else:
        hours = seconds / 3600
        return f"{hours:.1f}h"


def extract_workflow_metrics(item: Dict[str, Any]) -> Dict[str, Any]:
    """Extract relevant metrics from a single workflow item."""
    metadata = item.get("metadata", {})
    status = item.get("status", {})

    # Extract timestamps
    started_ts = status.get("startedAt")
    finished_ts = status.get("finishedAt")
    started = parse_timestamp(started_ts)
    finished = parse_timestamp(finished_ts)

    # Calculate duration
    duration_seconds = calculate_duration_seconds(started, finished)
    duration_formatted = format_duration(duration_seconds)

    return {
        "workflow_name": metadata.get("name", "unknown"),
        "namespace": metadata.get("namespace", "argo-workflows"),
        "workflow_template": metadata.get("labels", {}).get("workflows.argoproj.io/workflow-template", "unknown"),
        "started_at": started_ts,
        "finished_at": finished_ts,
        "phase": status.get("phase"),
        "message": status.get("message"),
        "duration_seconds": duration_seconds,
        "duration_formatted": duration_formatted,
        "uid": metadata.get("uid"),
    }


def parse_workflow_json(input_path: Path) -> Dict[str, Any]:
    """Parse workflow JSON and extract deployment metrics."""
    with open(input_path, "r") as f:
        data = json.load(f)

    items = data.get("items", [])
    summary = data.get("summary", {})

    # Extract metrics for each workflow
    deployments = [extract_workflow_metrics(item) for item in items]

    # Create summary metadata
    result = {
        "query": summary.get("query"),
        "time_range": summary.get("timeRange"),
        "total_found": summary.get("totalFound", len(items)),
        "namespace": data.get("metadata", {}).get("namespace"),
        "deployments": deployments,
        "note": summary.get("note") if len(items) == 0 else None,
    }

    return result


def main():
    """Main entry point."""
    input_path = Path.home() / "scratch" / "pbx-web-raw.json"
    output_path = Path.home() / "scratch" / "pbx-web-parsed.json"

    # Parse the workflow JSON
    parsed_data = parse_workflow_json(input_path)

    # Write parsed output
    with open(output_path, "w") as f:
        json.dump(parsed_data, f, indent=2)

    # Print summary
    print(f"Query: {parsed_data['query']}")
    print(f"Time Range: {parsed_data['time_range']}")
    print(f"Total Found: {parsed_data['total_found']}")
    print(f"Deployments Parsed: {len(parsed_data['deployments'])}")

    if parsed_data.get('note'):
        print(f"Note: {parsed_data['note']}")

    print(f"\nParsed data written to: {output_path}")


if __name__ == "__main__":
    main()
