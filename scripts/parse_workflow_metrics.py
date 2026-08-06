#!/usr/bin/env python3
"""
Parse and extract deployment metrics from kubectl workflow output.

Extracts structured metrics from raw workflow data including:
- workflow_id
- timestamp
- phase
- started_at
- finished_at
- duration_seconds
- status_message
"""

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Any, Optional


def parse_kubectl_output(raw_text: str) -> List[Dict[str, Any]]:
    """
    Parse raw kubectl get workflow output into structured metrics.

    Handles two formats:
    1. JSON output (kubectl get -o json)
    2. Table output (kubectl get default format)

    Args:
        raw_text: Raw kubectl output text

    Returns:
        List of workflow metric dictionaries
    """
    workflows = []
    lines = raw_text.strip().split('\n')

    # Check if this is the "no workflows found" message
    no_workflows_indicators = [
        'No workflows found',
        'no executions in the timeframe',
        'Workflow template.*exists but has no executions'
    ]

    for indicator in no_workflows_indicators:
        if indicator.lower() in raw_text.lower():
            print("No workflows found in query results")
            print("Query status indicates no workflow executions in timeframe")
            return []

    # Try JSON format first
    try:
        data = json.loads(raw_text)
        if 'items' in data:
            return [parse_workflow_item(item) for item in data['items']]
    except (json.JSONDecodeError, KeyError):
        pass

    # Fall back to table format parsing
    # Skip header line
    data_lines = [line for line in lines if line.strip() and not line.startswith('NAME')]

    for line in data_lines:
        # Parse table format: NAME PHASE STARTED FINISHED DURATION MESSAGE
        parts = line.split()
        if len(parts) >= 2:
            workflow = {
                'workflow_id': parts[0],
                'phase': parts[1],
                'started_at': parts[2] if len(parts) > 2 else None,
                'finished_at': parts[3] if len(parts) > 3 else None,
                'duration_seconds': None,
                'status_message': ' '.join(parts[4:]) if len(parts) > 4 else ''
            }
            workflows.append(workflow)

    return workflows


def parse_workflow_item(item: Dict[str, Any]) -> Dict[str, Any]:
    """
    Parse a single workflow item from kubectl JSON output.

    Args:
        item: Single workflow item from kubectl output

    Returns:
        Structured workflow metric dictionary
    """
    metadata = item.get('metadata', {})
    status = item.get('status', {})

    workflow_id = metadata.get('name', '')
    phase = status.get('phase', 'Unknown')
    started_at = status.get('startedAt')
    finished_at = status.get('finishedAt')
    status_message = status.get('message', '')

    # Calculate duration if both timestamps exist
    duration_seconds = None
    if started_at and finished_at:
        try:
            start = datetime.fromisoformat(started_at.replace('Z', '+00:00'))
            finish = datetime.fromisoformat(finished_at.replace('Z', '+00:00'))
            duration_seconds = (finish - start).total_seconds()
        except (ValueError, AttributeError):
            pass

    return {
        'workflow_id': workflow_id,
        'timestamp': metadata.get('creationTimestamp'),
        'phase': phase,
        'started_at': started_at,
        'finished_at': finished_at,
        'duration_seconds': duration_seconds,
        'status_message': status_message
    }


def filter_by_date_range(
    workflows: List[Dict[str, Any]],
    start_date: str,
    end_date: str
) -> List[Dict[str, Any]]:
    """
    Filter workflows to only include those within the date range.

    Args:
        workflows: List of workflow metrics
        start_date: ISO format start date (e.g., '2026-07-07')
        end_date: ISO format end date (e.g., '2026-08-06')

    Returns:
        Filtered list of workflows
    """
    start_dt = datetime.fromisoformat(start_date)
    end_dt = datetime.fromisoformat(end_date).replace(hour=23, minute=59, second=59)

    filtered = []
    for wf in workflows:
        timestamp = wf.get('timestamp') or wf.get('started_at')
        if not timestamp:
            continue

        try:
            # Handle different timestamp formats
            if isinstance(timestamp, str):
                ts_dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
            else:
                continue

            if start_dt <= ts_dt <= end_dt:
                filtered.append(wf)
        except (ValueError, AttributeError):
            continue

    return filtered


def validate_completeness(workflows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Validate data completeness and flag incomplete entries.

    Args:
        workflows: List of workflow metrics

    Returns:
        List of validated workflows with completeness flags
    """
    for wf in workflows:
        wf['data_complete'] = all([
            wf.get('workflow_id'),
            wf.get('phase'),
            wf.get('started_at')
        ])

        # For completed workflows, finishedAt is required
        if wf.get('phase') in ('Succeeded', 'Failed'):
            wf['data_complete'] = wf.get('data_complete') and bool(wf.get('finished_at'))

    return workflows


def main():
    """Main entry point for workflow metrics parsing."""
    if len(sys.argv) > 1:
        input_file = Path(sys.argv[1])
    else:
        input_file = Path('/tmp/pbx-web-workflows-raw.txt')

    if not input_file.exists():
        print(f"Error: Input file not found: {input_file}")
        sys.exit(1)

    # Read raw workflow data
    raw_text = input_file.read_text()

    # Parse into structured format
    workflows = parse_kubectl_output(raw_text)
    print(f"Parsed {len(workflows)} workflows from raw data")

    if not workflows:
        print("\nNo workflows to process - output will be empty list")
        output = {
            'total_count': 0,
            'timeframe': {
                'start': '2026-07-07',
                'end': '2026-08-06',
                'days': 30
            },
            'workflows': [],
            'summary': {
                'succeeded': 0,
                'failed': 0,
                'running': 0,
                'pending': 0
            }
        }
    else:
        # Filter by 30-day window
        workflows = filter_by_date_range(
            workflows,
            '2026-07-07',
            '2026-08-06'
        )
        print(f"Filtered to {len(workflows)} workflows within 30-day window")

        # Validate completeness
        workflows = validate_completeness(workflows)
        complete_count = sum(1 for wf in workflows if wf.get('data_complete'))
        print(f"Complete records: {complete_count}/{len(workflows)}")

        # Generate summary
        summary = {
            'succeeded': sum(1 for wf in workflows if wf.get('phase') == 'Succeeded'),
            'failed': sum(1 for wf in workflows if wf.get('phase') == 'Failed'),
            'running': sum(1 for wf in workflows if wf.get('phase') == 'Running'),
            'pending': sum(1 for wf in workflows if wf.get('phase') == 'Pending')
        }

        output = {
            'total_count': len(workflows),
            'timeframe': {
                'start': '2026-07-07',
                'end': '2026-08-06',
                'days': 30
            },
            'workflows': workflows,
            'summary': summary
        }

    # Output as JSON
    output_file = Path('/tmp/pbx-web-workflows-parsed.json')
    output_file.write_text(json.dumps(output, indent=2))
    print(f"\nStructured output written to: {output_file}")

    # Print summary
    print(f"\nSummary:")
    print(f"  Total workflows: {output['total_count']}")
    if output['total_count'] > 0:
        print(f"  Succeeded: {output['summary']['succeeded']}")
        print(f"  Failed: {output['summary']['failed']}")
        print(f"  Running: {output['summary']['running']}")
        print(f"  Pending: {output['summary']['pending']}")


if __name__ == '__main__':
    main()
