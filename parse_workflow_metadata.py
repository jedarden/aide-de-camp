#!/usr/bin/env python3
"""
Parse pbx-web workflow metadata from kubectl output.

Extracts relevant fields from Argo Workflow records:
- metadata.name (workflow ID)
- status.phase (success/failure/running)
- status.startedAt
- status.finishedAt
- status.message (error messages if any)
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Any


def calculate_duration(started_at: str, finished_at: str) -> Dict[str, Any]:
    """
    Calculate duration between two ISO 8601 timestamps.

    Args:
        started_at: Start timestamp string
        finished_at: End timestamp string

    Returns:
        Dictionary with duration information including total seconds,
        human-readable format, and calculation status
    """
    duration_info = {
        'total_seconds': 0,
        'human_readable': '',
        'calculation_status': 'unknown'
    }

    if not started_at:
        duration_info['calculation_status'] = 'missing_start_time'
        return duration_info

    try:
        from datetime import datetime
        start_time = datetime.fromisoformat(started_at.replace('Z', '+00:00'))

        if finished_at:
            end_time = datetime.fromisoformat(finished_at.replace('Z', '+00:00'))
            duration_seconds = (end_time - start_time).total_seconds()
            duration_info['calculation_status'] = 'complete'
        else:
            # Workflow still running or incomplete - use current time
            now = datetime.now(timezone.utc)
            duration_seconds = (now - start_time).total_seconds()
            duration_info['calculation_status'] = 'incomplete'

        duration_info['total_seconds'] = duration_seconds

        # Calculate human-readable format
        if duration_seconds >= 3600:
            hours = int(duration_seconds // 3600)
            minutes = int((duration_seconds % 3600) // 60)
            duration_info['human_readable'] = f"{hours}h {minutes}m"
        elif duration_seconds >= 60:
            minutes = int(duration_seconds // 60)
            seconds = int(duration_seconds % 60)
            duration_info['human_readable'] = f"{minutes}m {seconds}s"
        else:
            duration_info['human_readable'] = f"{int(duration_seconds)}s"

    except (ValueError, AttributeError) as e:
        duration_info['calculation_status'] = f'invalid_timestamp: {str(e)}'

    return duration_info


def extract_failure_conditions(item: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract failure conditions and error details from workflow status.

    Args:
        item: Workflow item dictionary

    Returns:
        Dictionary with failure condition details
    """
    failure_info = {
        'failed': False,
        'failure_type': '',
        'error_message': '',
        'failed_nodes': []
    }

    status = item.get('status', {})
    phase = status.get('phase', '')

    # Determine if workflow failed
    if phase == 'Failed':
        failure_info['failed'] = True
        failure_info['failure_type'] = 'workflow_failed'
        failure_info['error_message'] = status.get('message', 'No error message provided')

    # Extract failed nodes if available
    nodes = status.get('nodes', {})
    for node_id, node in nodes.items():
        node_phase = node.get('phase', '')
        if node_phase in ('Failed', 'Error'):
            failure_info['failed_nodes'].append({
                'node_id': node_id,
                'name': node.get('name', ''),
                'phase': node_phase,
                'message': node.get('message', '')
            })

    return failure_info


def parse_json_workflows(input_file: Path) -> List[Dict[str, Any]]:
    """
    Parse kubectl JSON output for workflows.

    Handles multiple formats:
    1. Full kubectl format with nested metadata/status/spec
    2. Simplified format with just name/created/phase
    3. Array format or {"items": [...]} format

    Args:
        input_file: Path to file containing kubectl -o json output

    Returns:
        List of workflow records with extracted metadata
    """
    with open(input_file, 'r') as f:
        data = json.load(f)

    # Handle both array format and {"items": [...]} format
    items = data if isinstance(data, list) else data.get('items', [])

    workflows = []
    for item in items:
        # Detect format type
        if 'metadata' in item and 'status' in item:
            # Full kubectl format
            started_at = item.get('status', {}).get('startedAt', '')
            finished_at = item.get('status', {}).get('finishedAt', '')

            # Calculate duration
            duration_info = calculate_duration(started_at, finished_at)

            # Extract failure conditions
            failure_info = extract_failure_conditions(item)

            workflow = {
                'metadata': {
                    'name': item.get('metadata', {}).get('name', ''),
                    'namespace': item.get('metadata', {}).get('namespace', ''),
                    'creationTimestamp': item.get('metadata', {}).get('creationTimestamp', ''),
                    'labels': item.get('metadata', {}).get('labels', {}),
                    'annotations': item.get('metadata', {}).get('annotations', {}),
                },
                'status': {
                    'phase': item.get('status', {}).get('phase', 'Unknown'),
                    'startedAt': started_at,
                    'finishedAt': finished_at,
                    'message': item.get('status', {}).get('message', ''),
                    'resourcesDuration': item.get('status', {}).get('resourcesDuration', {}),
                    'duration': duration_info,  # Added duration calculation
                    'failures': failure_info    # Added failure conditions
                },
                'spec': {
                    'workflowTemplateRef': item.get('spec', {}).get('workflowTemplateRef', {}),
                    'arguments': item.get('spec', {}).get('arguments', {}),
                }
            }
        elif 'name' in item and 'phase' in item:
            # Simplified format (name, created, phase)
            started_at = item.get('created', '')
            finished_at = item.get('finished', '')  # Might not exist in simplified format

            # Calculate duration
            duration_info = calculate_duration(started_at, finished_at)

            # Basic failure info for simplified format
            failure_info = {
                'failed': item.get('phase', '') == 'Failed',
                'failure_type': 'workflow_failed' if item.get('phase', '') == 'Failed' else '',
                'error_message': item.get('error', ''),
                'failed_nodes': []
            }

            workflow = {
                'metadata': {
                    'name': item.get('name', ''),
                    'namespace': '',
                    'creationTimestamp': item.get('created', ''),
                    'labels': {},
                    'annotations': {},
                },
                'status': {
                    'phase': item.get('phase', 'Unknown'),
                    'startedAt': started_at,
                    'finishedAt': finished_at,
                    'message': item.get('error', ''),
                    'resourcesDuration': {},
                    'duration': duration_info,  # Added duration calculation
                    'failures': failure_info    # Added failure conditions
                },
                'spec': {
                    'workflowTemplateRef': {},
                    'arguments': {},
                }
            }
        else:
            # Unknown format, create minimal structure with duration and failure info
            workflow = {
                'metadata': {
                    'name': str(item.get('name', item.get('metadata', {}).get('name', ''))),
                    'namespace': '',
                    'creationTimestamp': '',
                    'labels': {},
                    'annotations': {},
                },
                'status': {
                    'phase': 'Unknown',
                    'startedAt': '',
                    'finishedAt': '',
                    'message': '',
                    'resourcesDuration': {},
                    'duration': calculate_duration('', ''),  # Empty duration for unknown format
                    'failures': extract_failure_conditions(item)  # Try to extract failure info anyway
                },
                'spec': {
                    'workflowTemplateRef': {},
                    'arguments': {},
                }
            }
        workflows.append(workflow)

    return workflows


def parse_text_workflows(input_file: Path) -> List[Dict[str, Any]]:
    """
    Parse kubectl text/table output for workflows.

    This is a fallback for when JSON output is not available.
    Parses the standard kubectl table format.

    Args:
        input_file: Path to file containing kubectl text output

    Returns:
        List of workflow records with extracted metadata
    """
    workflows = []

    with open(input_file, 'r') as f:
        lines = f.readlines()

    # Skip header lines and look for data
    in_data_section = False
    for line in lines:
        line = line.strip()

        # Detect when we're in the data section
        if line.startswith('NAME') and 'PHASE' in line:
            in_data_section = True
            continue

        # Skip empty lines and comments
        if not line or line.startswith('#') or not in_data_section:
            continue

        # Parse workflow line (basic parsing of table format)
        parts = line.split()
        if len(parts) >= 2:
            phase = parts[1] if len(parts) > 1 else 'Unknown'

            workflows.append({
                'metadata': {
                    'name': parts[0],
                    'namespace': '',  # Not available in basic format
                    'creationTimestamp': '',  # Not available in basic format
                    'labels': {},
                    'annotations': {},
                },
                'status': {
                    'phase': phase,
                    'startedAt': '',
                    'finishedAt': '',
                    'message': '',
                    'resourcesDuration': {},
                    'duration': calculate_duration('', ''),  # No timestamps available in text format
                    'failures': {  # Basic failure info for text format
                        'failed': phase == 'Failed',
                        'failure_type': 'workflow_failed' if phase == 'Failed' else '',
                        'error_message': '',
                        'failed_nodes': []
                    }
                },
                'spec': {
                    'workflowTemplateRef': {},
                    'arguments': {},
                }
            })

    return workflows


def parse_kubectl_output(input_file: Path, output_format: str = 'auto') -> Dict[str, Any]:
    """
    Main function to parse kubectl workflow output.

    Args:
        input_file: Path to kubectl output file
        output_format: 'auto', 'json', or 'text'

    Returns:
        Dictionary containing parsed workflow metadata
    """
    if not input_file.exists():
        return {
            'workflows': [],
            'summary': {
                'total_count': 0,
                'by_phase': {},
                'parsing_errors': ['Input file not found']
            }
        }

    try:
        # Auto-detect format if requested
        if output_format == 'auto':
            with open(input_file, 'r') as f:
                first_line = f.readline().strip()
                output_format = 'json' if first_line.startswith('{') or first_line.startswith('[') else 'text'

        # Parse based on format
        if output_format == 'json':
            workflows = parse_json_workflows(input_file)
        else:
            workflows = parse_text_workflows(input_file)

        # Generate summary statistics
        summary = {
            'total_count': len(workflows),
            'by_phase': {},
            'date_range': {
                'earliest': None,
                'latest': None
            },
            'parsing_errors': []
        }

        # Count by phase and find date range
        for wf in workflows:
            phase = wf.get('status', {}).get('phase', 'Unknown')
            summary['by_phase'][phase] = summary['by_phase'].get(phase, 0) + 1

            started = wf.get('status', {}).get('startedAt', '')
            if started:
                if not summary['date_range']['earliest'] or started < summary['date_range']['earliest']:
                    summary['date_range']['earliest'] = started
                if not summary['date_range']['latest'] or started > summary['date_range']['latest']:
                    summary['date_range']['latest'] = started

        return {
            'workflows': workflows,
            'summary': summary,
            'metadata': {
                'parsed_at': datetime.now().isoformat(),
                'input_format': output_format,
                'input_file': str(input_file)
            }
        }

    except Exception as e:
        return {
            'workflows': [],
            'summary': {
                'total_count': 0,
                'by_phase': {},
                'parsing_errors': [str(e)]
            }
        }


def main():
    """Main entry point for command-line usage."""
    if len(sys.argv) < 2:
        print("Usage: parse_workflow_metadata.py <input_file> [output_file]")
        sys.exit(1)

    input_file = Path(sys.argv[1])
    output_file = Path(sys.argv[2]) if len(sys.argv) > 2 else None

    result = parse_kubectl_output(input_file)

    # Output results
    if output_file:
        with open(output_file, 'w') as f:
            json.dump(result, f, indent=2)
        print(f"Parsed {result['summary']['total_count']} workflows")
        print(f"Results saved to {output_file}")
    else:
        print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
