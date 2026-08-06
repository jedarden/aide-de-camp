#!/usr/bin/env python3
"""Parse whisper-stt deployment logs and extract key metrics for 30-day analysis."""

import json
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Any

# Constants
OUTPUT_DIR = Path("/home/coding/aide-de-camp/logs")
OUTPUT_FILE = OUTPUT_DIR / "whisper-stt-30day.jsonl"

def parse_http_log_line(line: str) -> Dict[str, Any]:
    """Parse HTTP log lines for errors and latency."""
    if not line.strip():
        return None

    # Match common HTTP log patterns
    # Uvicorn/FastAPI pattern: INFO:     IP:PORT - "METHOD PATH HTTP/1.1" STATUS MESSAGE
    uvicorn_pattern = r'INFO:\s+(\d+\.\d+\.\d+\.\d+):(\d+)\s+-\s+"([^"]+)"\s+(\d+)\s+(\S+)'
    match = re.search(uvicorn_pattern, line)

    if match:
        ip, port, request, status, message = match.groups()
        return {
            'type': 'http_access',
            'ip': ip,
            'request': request,
            'status_code': int(status),
            'message': message,
            'is_error': int(status) >= 500,
            'raw_line': line.strip()
        }

    return None

def extract_pod_restart_data(describe_file: Path) -> List[Dict[str, Any]]:
    """Extract pod restart information from describe output."""
    events = []

    if not describe_file.exists():
        return events

    content = describe_file.read_text()

    # Extract restart count
    restart_match = re.search(r'Restart Count:\s+(\d+)', content)
    if restart_match:
        restart_count = int(restart_match.group(1))
        events.append({
            'type': 'pod_restart',
            'pod_name': describe_file.stem.replace('whisper-stt-', '').replace('-describe', ''),
            'restart_count': restart_count,
            'timestamp': datetime.now().isoformat()
        })

    # Check for OOMKilled or CrashLoopBackOff
    if 'OOMKilled' in content or 'CrashLoopBackOff' in content:
        events.append({
            'type': 'pod_crash',
            'pod_name': describe_file.stem.replace('whisper-stt-', '').replace('-describe', ''),
            'reason': 'OOMKilled' if 'OOMKilled' in content else 'CrashLoopBackOff',
            'timestamp': datetime.now().isoformat()
        })

    return events

def parse_replica_sets(replicasets_file: Path) -> List[Dict[str, Any]]:
    """Parse replica set history for deployment events."""
    events = []

    if not replicasets_file.exists():
        return events

    try:
        with open(replicasets_file) as f:
            data = json.load(f)

        for rs in data.get('items', []):
            creation_time = rs.get('metadata', {}).get('creationTimestamp')
            name = rs.get('metadata', {}).get('name')
            replicas = rs.get('spec', {}).get('replicas', 0)

            events.append({
                'type': 'deployment',
                'replica_set_name': name,
                'creation_timestamp': creation_time,
                'replicas': replicas,
                'timestamp': creation_time
            })
    except Exception as e:
        print(f"Error parsing replica sets: {e}")

    return events

def analyze_log_patterns() -> Dict[str, Any]:
    """Analyze overall log patterns."""
    return {
        'total_logs_processed': 0,
        'http_5xx_errors': 0,
        'pod_restarts': 0,
        'deployment_events': 0,
        'data_gaps': []
    }

def main():
    """Main parsing function."""
    all_events = []

    # Parse pod logs for HTTP errors
    for log_file in OUTPUT_DIR.glob("whisper-stt-*-logs.txt"):
        if 'whisper-openai-logs.txt' in log_file.name or 'whisper-stt-' in log_file.name:
            print(f"Processing {log_file.name}...")

            try:
                content = log_file.read_text()
                for line in content.split('\n'):
                    parsed = parse_http_log_line(line)
                    if parsed:
                        all_events.append(parsed)
            except Exception as e:
                print(f"  Error: {e}")

    # Parse pod describe files for restart data
    for describe_file in OUTPUT_DIR.glob("whisper-stt-*-describe.txt"):
        events = extract_pod_restart_data(describe_file)
        all_events.extend(events)

    # Parse replica sets for deployment history
    replicasets_file = OUTPUT_DIR / "whisper-stt-replicasets.json"
    deployment_events = parse_replica_sets(replicasets_file)
    all_events.extend(deployment_events)

    # Generate analysis summary
    http_5xx_count = sum(1 for e in all_events if e.get('type') == 'http_access' and e.get('is_error'))
    pod_restart_count = sum(1 for e in all_events if e.get('type') == 'pod_restart' and e.get('restart_count', 0) > 0)
    deployment_count = sum(1 for e in all_events if e.get('type') == 'deployment')

    summary = {
        'collection_timestamp': datetime.now().isoformat(),
        'analysis_period': '30 days (2026-07-07 to 2026-08-06)',
        'namespace': 'whisper-stt',
        'cluster': 'ardenone-cluster',
        'metrics': {
            'total_http_5xx_errors': http_5xx_count,
            'total_pod_restarts': pod_restart_count,
            'total_deployment_events': deployment_count,
            'total_events': len(all_events)
        },
        'events': all_events
    }

    # Write JSONL output
    with open(OUTPUT_FILE, 'w') as f:
        for event in all_events:
            f.write(json.dumps(event) + '\n')

    print(f"\n=== Analysis Complete ===")
    print(f"Total events: {len(all_events)}")
    print(f"HTTP 5xx errors: {http_5xx_count}")
    print(f"Pod restarts: {pod_restart_count}")
    print(f"Deployment events: {deployment_count}")
    print(f"Output: {OUTPUT_FILE}")

if __name__ == '__main__':
    main()