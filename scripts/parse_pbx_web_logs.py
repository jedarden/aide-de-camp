#!/usr/bin/env python3
"""
Parse pbx-web logs from multiple sources for deployment-relevant events.

Data sources:
- VictoriaLogs JSON (nginx access logs)
- Events JSON (pod events, deployment history)
- Pod logs (container logs with error patterns)

Extracts:
- HTTP 5xx errors (500, 502, 503, 504)
- Pod restart indicators (OOMKilled, CrashLoopBackOff)
- Latency indicators (slow requests, timeouts)
- Connection errors (errno 104, broken pipe)
- Recording fetch failures
"""

import json
import re
from datetime import datetime
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Any, Optional


def parse_nginx_log(msg: str) -> Optional[Dict[str, Any]]:
    """Parse nginx access log message."""
    # Nginx log format: IP - - [timestamp] "METHOD PATH PROTO" STATUS SIZE "REFERER" "UA" "EXTRA"
    pattern = r'(\S+) - - \[([^\]]+)\] "(\S+) (\S+) (\S+)" (\d+) (\d+) "([^"]*)" "([^"]*)" "([^"]*)"'
    match = re.match(pattern, msg)

    if match:
        return {
            'ip': match.group(1),
            'timestamp': match.group(2),
            'method': match.group(3),
            'path': match.group(4),
            'protocol': match.group(5),
            'status': int(match.group(6)),
            'size': int(match.group(7)),
            'referer': match.group(8),
            'user_agent': match.group(9),
            'extra': match.group(10)
        }
    return None


def parse_events_json(events_path: Path) -> List[Dict[str, Any]]:
    """Parse events JSON file for pod and deployment events."""
    events = []

    if not events_path.exists():
        return events

    with open(events_path, 'r') as f:
        for line in f:
            try:
                event = json.loads(line.strip())

                # Skip empty list responses
                if event.get('kind') == 'List' and not event.get('items'):
                    continue

                # Extract deployment-relevant information
                if event.get('error_type'):
                    events.append({
                        'source': 'events_json',
                        'error_type': event.get('error_type'),
                        'severity': event.get('severity'),
                        'context': event.get('context'),
                        'pattern': event.get('error_pattern'),
                        'status_code': event.get('status_code'),
                        'frequency': event.get('frequency')
                    })

                # Extract pod restart information
                if event.get('metric_type') == 'deployment_history':
                    events.append({
                        'source': 'events_json',
                        'metric_type': 'deployment_history',
                        'replica_sets': event.get('pbx_web_replica_sets'),
                        'oldest_age_days': event.get('oldest_replica_set_age_days'),
                        'current_age_days': event.get('current_deployment_age_days')
                    })

                # Extract health metrics
                if event.get('health_metric'):
                    events.append({
                        'source': 'events_json',
                        'health_metric': event.get('health_metric'),
                        'value': event.get('value'),
                        'status': event.get('status'),
                        'period': event.get('time_period'),
                        'oomkilled': event.get('oomkilled_events'),
                        'crashloopbackoff': event.get('crashloopbackoff_events')
                    })

            except (json.JSONDecodeError, KeyError):
                continue

    return events


def parse_container_logs(log_path: Path) -> List[Dict[str, Any]]:
    """Parse container logs for error patterns."""
    errors = []

    if not log_path.exists():
        return errors

    # Error patterns to look for
    error_patterns = [
        (r'\[Errno 104\] Connection reset by peer', 'connection_reset', 'errno 104'),
        (r'\[Errno 32\] Broken pipe', 'broken_pipe', 'errno 32'),
        (r'500', 'http_500', 'status 500'),
        (r'502', 'http_502', 'status 502'),
        (r'503', 'http_503', 'status 503'),
        (r'504', 'http_504', 'status 504'),
        (r'timeout', 'timeout', 'timeout'),
        (r'OOMKilled', 'oom_killed', 'pod terminated'),
        (r'CrashLoopBackOff', 'crash_loop_back_off', 'pod restart'),
    ]

    with open(log_path, 'r') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue

            for pattern, error_type, severity in error_patterns:
                if re.search(pattern, line, re.IGNORECASE):
                    errors.append({
                        'source': 'container_logs',
                        'error_type': error_type,
                        'severity': severity,
                        'message': line[:500]  # Truncate long messages
                    })
                    break

    return errors


def process_victoria_logs(input_path: Path) -> List[Dict[str, Any]]:
    """Process VictoriaLogs JSON file."""
    parsed_entries = []

    if not input_path.exists():
        return parsed_entries

    print(f"Processing VictoriaLogs: {input_path}")

    with open(input_path, 'r') as f:
        for line_num, line in enumerate(f, 1):
            try:
                log_entry = json.loads(line.strip())

                # Extract basic info
                timestamp = log_entry.get('_time', '')
                msg = log_entry.get('_msg', '')
                pod_name = log_entry.get('kubernetes', {}).get('pod_name', 'unknown')

                # Parse nginx log
                nginx_log = parse_nginx_log(msg)

                if nginx_log:
                    status = nginx_log.get('status', 0)

                    # Check for server errors
                    if 500 <= status < 600:
                        parsed_entries.append({
                            'timestamp': timestamp,
                            'source': 'victoria_logs',
                            'event_type': 'http_error',
                            'status_code': status,
                            'path': nginx_log.get('path'),
                            'method': nginx_log.get('method'),
                            'pod_name': pod_name,
                            'ip': nginx_log.get('ip'),
                            'raw_msg': msg
                        })

            except json.JSONDecodeError:
                continue

    return parsed_entries


def generate_summary(all_events: List[Dict[str, Any]], output_path: Path):
    """Generate summary statistics from all events."""

    # Categorize events
    http_5xx_by_type = defaultdict(int)
    connection_errors = defaultdict(int)
    pod_events = defaultdict(int)
    deployment_events = []
    health_metrics = []

    for event in all_events:
        source = event.get('source', 'unknown')

        if source == 'victoria_logs':
            status = event.get('status_code')
            http_5xx_by_type[status] += 1

        elif source == 'events_json':
            error_type = event.get('error_type')
            if error_type:
                if 'connection' in error_type or 'errno' in str(event.get('pattern', '')):
                    connection_errors[error_type] += 1
                elif 'http_server_errors' in error_type:
                    http_5xx_by_type[event.get('status_code')] += 1
                elif 'recording_fetch' in error_type:
                    connection_errors[error_type] += 1

            if event.get('metric_type') == 'deployment_history':
                deployment_events.append(event)

            if event.get('health_metric'):
                health_metrics.append(event)

        elif source == 'container_logs':
            error_type = event.get('error_type')
            if error_type.startswith('http_'):
                status = int(error_type.replace('http_', ''))
                http_5xx_by_type[status] += 1
            elif error_type in ('connection_reset', 'broken_pipe'):
                connection_errors[error_type] += 1
            elif error_type in ('oom_killed', 'crash_loop_back_off'):
                pod_events[error_type] += 1

    # Build summary
    summary = {
        'analysis_date': datetime.now().isoformat(),
        'total_events': len(all_events),
        'http_5xx_errors': {
            'total': sum(http_5xx_by_type.values()),
            'by_type': dict(http_5xx_by_type)
        },
        'connection_errors': {
            'total': sum(connection_errors.values()),
            'by_type': dict(connection_errors)
        },
        'pod_events': {
            'total': sum(pod_events.values()),
            'by_type': dict(pod_events)
        },
        'deployment_history': deployment_events,
        'health_metrics': health_metrics
    }

    # Write summary
    with open(output_path, 'w') as f:
        json.dump(summary, f, indent=2)

    # Print summary
    print("\n" + "="*60)
    print("SUMMARY STATISTICS")
    print("="*60)
    print(f"Total events found: {summary['total_events']}")
    print(f"\nHTTP 5xx Errors: {summary['http_5xx_errors']['total']}")
    for status, count in sorted(summary['http_5xx_errors']['by_type'].items()):
        print(f"  HTTP {status}: {count}")

    print(f"\nConnection Errors: {summary['connection_errors']['total']}")
    for error, count in sorted(summary['connection_errors']['by_type'].items()):
        print(f"  {error}: {count}")

    print(f"\nPod Events: {summary['pod_events']['total']}")
    for event, count in sorted(summary['pod_events']['by_type'].items()):
        print(f"  {event}: {count}")

    if summary['deployment_history']:
        print(f"\nDeployment History:")
        for dep in summary['deployment_history']:
            print(f"  Replica sets: {dep.get('replica_sets')}")
            print(f"  Oldest age: {dep.get('oldest_age_days')} days")
            print(f"  Current age: {dep.get('current_age_days')} days")

    if summary['health_metrics']:
        print(f"\nHealth Metrics:")
        for metric in summary['health_metrics']:
            print(f"  {metric.get('health_metric')}: {metric.get('value')} ({metric.get('status')})")

    print("="*60)

    return summary


def main():
    """Main entry point."""
    base_dir = Path('/home/coding/aide-de-camp/logs')

    # All data sources
    victoria_logs = base_dir / 'pbx-web-victorialogs-raw.jsonl'
    events_json = base_dir / 'pbx-web-30day' / 'events-30day.json'
    container_logs = base_dir / 'pbx-web-30day' / 'pbx-web-main-current.log'

    output_file = base_dir / 'pbx-web-parsed.jsonl'
    summary_file = base_dir / 'pbx-web-summary.json'

    all_events = []

    # Process VictoriaLogs
    victoria_events = process_victoria_logs(victoria_logs)
    all_events.extend(victoria_events)
    print(f"  Found {len(victoria_events)} events in VictoriaLogs")

    # Process events JSON
    if events_json.exists():
        events = parse_events_json(events_json)
        all_events.extend(events)
        print(f"  Found {len(events)} events in events JSON")

    # Process container logs
    if container_logs.exists():
        container_errors = parse_container_logs(container_logs)
        all_events.extend(container_errors)
        print(f"  Found {len(container_errors)} events in container logs")

    # Write parsed output
    print(f"\nWriting parsed output to {output_file}...")
    with open(output_file, 'w') as f:
        for event in all_events:
            f.write(json.dumps(event) + '\n')

    # Generate summary
    summary = generate_summary(all_events, summary_file)

    print(f"\n✓ Parsed logs saved to: {output_file}")
    print(f"✓ Summary statistics saved to: {summary_file}")

    return 0


if __name__ == '__main__':
    exit(main())
