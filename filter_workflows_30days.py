#!/usr/bin/env python3
"""
Filter workflows by last 30 days (2026-07-07 to 2026-08-06).
Parses kubectl JSON output and filters workflows by creation timestamp.
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List


def parse_timestamp(ts: str) -> datetime:
    """Parse ISO 8601 timestamp string to datetime object."""
    # Remove 'Z' suffix and parse
    ts_clean = ts.rstrip('Z')
    return datetime.fromisoformat(ts_clean).replace(tzinfo=timezone.utc)


def filter_workflows_by_date(input_path: Path, cutoff_date: str) -> Dict[str, Any]:
    """
    Filter workflows by creation timestamp >= cutoff date.

    Args:
        input_path: Path to kubectl JSON output file
        cutoff_date: Cutoff date string (YYYY-MM-DD)

    Returns:
        Dictionary with filtered workflows and summary statistics
    """
    with open(input_path, 'r') as f:
        data = json.load(f)

    all_items = data.get('items', [])
    cutoff_dt = datetime.fromisoformat(cutoff_date).replace(tzinfo=timezone.utc)

    # Filter workflows by creation timestamp
    filtered_items = []
    for item in all_items:
        metadata = item.get('metadata', {})
        creation_ts = metadata.get('creationTimestamp')

        if creation_ts:
            created_dt = parse_timestamp(creation_ts)
            if created_dt >= cutoff_dt:
                filtered_items.append(item)

    # Create result
    result = {
        'cutoff_date': cutoff_date,
        'total_workflows': len(all_items),
        'filtered_workflows': len(filtered_items),
        'workflows_removed': len(all_items) - len(filtered_items),
        'filtered_items': filtered_items
    }

    return result


def main():
    """Main entry point."""
    input_path = Path('/home/coding/scratch/all-workflows.json')
    output_path = Path('/home/coding/aide-de-camp/notes/adc-20tux-workflows-filtered.json')
    cutoff_date = '2026-07-07'

    # Filter workflows
    result = filter_workflows_by_date(input_path, cutoff_date)

    # Write filtered output
    with open(output_path, 'w') as f:
        json.dump(result, f, indent=2)

    # Print summary
    print(f"30-Day Workflow Filtering Results")
    print(f"=" * 50)
    print(f"Cutoff Date: {result['cutoff_date']}")
    print(f"Total Workflows (before filtering): {result['total_workflows']}")
    print(f"Filtered Workflows (last 30 days): {result['filtered_workflows']}")
    print(f"Workflows Removed (older than 30 days): {result['workflows_removed']}")
    print(f"\nFiltered data written to: {output_path}")


if __name__ == '__main__':
    main()
