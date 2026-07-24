#!/usr/bin/env python3
"""
Failure Pattern Analysis for pbx-web and whisper-stt deployment logs
Analyzes 30-day window logs to identify distinct failure modes, categorize them, and generate frequency counts.
"""

import json
import re
from pathlib import Path
from datetime import datetime
from collections import defaultdict, Counter
import sys

def load_k8s_logs():
    """Load the k8s logs JSON"""
    k8s_path = Path("/home/coding/aide-de-camp/data/adc-9jq0t/k8s-logs.json")
    if k8s_path.exists():
        with open(k8s_path) as f:
            return json.load(f)
    return None

def load_argo_logs():
    """Load the argo logs JSON"""
    argo_path = Path("/home/coding/aide-de-camp/data/adc-9jq0t/argo-logs.json")
    if argo_path.exists():
        with open(argo_path) as f:
            return json.load(f)
    return None

def categorize_failure(reason, message, service_name):
    """
    Categorize failure by type based on Kubernetes patterns
    Categories: infrastructure, service-specific, configuration, environmental
    """
    reason_lower = reason.lower() if reason else ""
    message_lower = message.lower() if message else ""

    # Infrastructure failures
    if any(keyword in reason_lower for keyword in ['evicted', 'oomkilled', 'nodestage']):
        return 'infrastructure'
    if 'ephemeral-storage' in message_lower or 'memory' in message_lower or 'disk' in message_lower or 'low on resource' in message_lower:
        return 'infrastructure'

    # Configuration failures
    if any(keyword in message_lower for keyword in ['imagepull', 'configmap', 'secret', 'invalid', 'deprecated']):
        return 'configuration'
    if 'deprecated' in reason_lower or 'deprecated' in message_lower:
        return 'configuration'

    # Service-specific failures (application-level)
    if any(keyword in reason_lower for keyword in ['crashloopbackoff', 'error', 'terminated']):
        if any(keyword in message_lower for keyword in ['exit code', 'command', 'permission']):
            return 'service-specific'

    # Environmental failures
    if 'network' in message_lower or 'timeout' in message_lower or 'dns' in message_lower or 'broken pipe' in message_lower:
        return 'environmental'

    # Default to infrastructure for eviction-related issues
    if 'evicted' in reason_lower:
        return 'infrastructure'

    return 'other'

def analyze_k8s_events(k8s_data):
    """Analyze Kubernetes events for failure patterns"""
    events_analysis = defaultdict(lambda: {
        'count': 0,
        'services': Counter(),
        'severity': [],
        'examples': []
    })

    if not k8s_data or 'services' not in k8s_data:
        return events_analysis

    for service_name, service_data in k8s_data['services'].items():
        if 'events' not in service_data:
            continue

        for event in service_data['events']:
            event_type = event.get('event_type', 'Unknown')
            reason = event.get('reason', 'Unknown')
            message = event.get('message', '')
            count = event.get('count', 1)

            # Only analyze warnings and errors
            if event_type not in ['Warning', 'Error']:
                continue

            failure_key = f"{event_type}:{reason}"
            category = categorize_failure(reason, message, service_name)

            events_analysis[failure_key]['count'] += count
            events_analysis[failure_key]['services'][service_name] += count
            events_analysis[failure_key]['category'] = category
            events_analysis[failure_key]['severity'] = event_type
            events_analysis[failure_key]['examples'].append({
                'service': service_name,
                'reason': reason,
                'message': message[:200],  # Truncate long messages
                'count': count
            })

    return events_analysis

def analyze_pod_failures(k8s_data):
    """Analyze pod failures and statuses"""
    pods_analysis = defaultdict(lambda: {
        'count': 0,
        'services': Counter(),
        'restarts': [],
        'examples': []
    })

    if not k8s_data or 'services' not in k8s_data:
        return pods_analysis

    for service_name, service_data in k8s_data['services'].items():
        if 'pods' not in service_data:
            continue

        for pod in service_data['pods']:
            status = pod.get('status', 'Unknown')
            restarts = pod.get('restarts', 0)
            pod_name = pod.get('name', 'Unknown')

            # Focus on failed and problematic pods
            if status in ['Failed', 'Error', 'CrashLoopBackOff'] or restarts > 0:
                failure_key = f"Pod:{status}"
                category = categorize_failure(
                    pod.get('failure_reason', ''),
                    pod.get('failure_message', ''),
                    service_name
                )

                pods_analysis[failure_key]['count'] += 1
                pods_analysis[failure_key]['services'][service_name] += 1
                pods_analysis[failure_key]['category'] = category
                pods_analysis[failure_key]['restarts'].append(restarts)
                pods_analysis[failure_key]['examples'].append({
                    'service': service_name,
                    'pod_name': pod_name,
                    'status': status,
                    'restarts': restarts,
                    'failure_reason': pod.get('failure_reason', 'N/A'),
                    'failure_message': pod.get('failure_message', 'N/A')
                })

    return pods_analysis

def analyze_argo_workflows(argo_data):
    """Analyze Argo workflow failures"""
    workflows_analysis = {
        'total_runs': 0,
        'successful': 0,
        'failed': 0,
        'error_patterns': Counter()
    }

    if not argo_data:
        return workflows_analysis

    # Check for pbx-web workflows
    pbx_workflows = argo_data.get('pbx_web_build_workflows', {})
    workflows_analysis['total_runs'] += pbx_workflows.get('total_runs_found', 0)

    # Check for whisper-stt workflows
    whisper_workflows = argo_data.get('whisper_stt_build_workflows', {})
    workflows_analysis['total_runs'] += whisper_workflows.get('total_runs_found', 0)

    # Note: The current data shows no workflow runs in the 30-day window
    workflows_analysis['note'] = "No workflow executions found in 30-day retention window"

    return workflows_analysis

def parse_application_logs(log_file_path, service_name):
    """Parse application logs for error patterns"""
    log_patterns = {
        'broken_pipe': {'pattern': r'BrokenPipeError|Broken pipe', 'category': 'environmental'},
        'connection_error': {'pattern': r'Connection.*refused|Connection.*reset|Network.*unreachable', 'category': 'environmental'},
        'timeout': {'pattern': r'timeout|timed out', 'category': 'environmental'},
        'permission_denied': {'pattern': r'Permission.*denied|Access.*denied', 'category': 'configuration'},
        'file_not_found': {'pattern': r'File.*not.*found|No such file', 'category': 'configuration'},
        'value_error': {'pattern': r'ValueError|TypeError|AttributeError', 'category': 'service-specific'},
        'http_error': {'pattern': r'HTTP.*5\d\d|5\d\d.*error', 'category': 'service-specific'},
        'oom': {'pattern': r'out of memory|OOM|Cannot allocate memory', 'category': 'infrastructure'},
    }

    results = defaultdict(lambda: {
        'count': 0,
        'category': '',
        'examples': []
    })

    log_path = Path(log_file_path)
    if not log_path.exists():
        return results

    try:
        with open(log_path, 'r') as f:
            content = f.read()

        for pattern_name, pattern_info in log_patterns.items():
            matches = re.findall(pattern_info['pattern'], content, re.IGNORECASE)
            if matches:
                results[pattern_name]['count'] = len(matches)
                results[pattern_name]['category'] = pattern_info['category']
                # Get first few examples
                examples = re.findall(pattern_info['pattern'], content, re.IGNORECASE)[:3]
                results[pattern_name]['examples'] = examples

    except Exception as e:
        print(f"Error parsing {log_file_path}: {e}", file=sys.stderr)

    return results

def generate_summary_report(k8s_events, pod_failures, argo_workflows, app_logs):
    """Generate comprehensive summary report"""
    report = {
        'analysis_date': datetime.now().isoformat(),
        'analysis_period': '30 days (2026-06-24 to 2026-07-24)',
        'services_analyzed': ['pbx-web', 'whisper-stt'],
        'findings': {
            'total_distinct_failure_modes': 0,
            'infrastructure_failures': {},
            'service_specific_failures': {},
            'configuration_failures': {},
            'environmental_failures': {},
            'other_failures': {}
        },
        'service_breakdown': {
            'pbx-web': {'failure_count': 0, 'categories': Counter()},
            'whisper-stt': {'failure_count': 0, 'categories': Counter()}
        },
        'severity_distribution': {},
        'recurring_issues': [],
        'one_off_issues': []
    }

    # Process all failure types
    all_failures = {}

    # Add K8s events
    for failure_key, data in k8s_events.items():
        category = data.get('category', 'other')
        all_failures[failure_key] = {
            'count': data['count'],
            'category': category,
            'severity': data.get('severity', 'Unknown'),
            'services': dict(data['services']),
            'source': 'kubernetes_events'
        }

    # Add pod failures
    for failure_key, data in pod_failures.items():
        category = data.get('category', 'other')
        all_failures[failure_key] = {
            'count': data['count'],
            'category': category,
            'severity': 'High',  # Pod failures are high severity
            'services': dict(data['services']),
            'source': 'pod_status'
        }

    # Add application log patterns
    for log_source, patterns in app_logs.items():
        service_name = log_source.split('_')[0]  # Extract service name from file path
        for pattern_name, data in patterns.items():
            if data['count'] > 0:
                failure_key = f"AppLog:{pattern_name}"
                all_failures[failure_key] = {
                    'count': data['count'],
                    'category': data.get('category', 'other'),
                    'severity': 'Medium',
                    'services': {service_name: data['count']},
                    'source': 'application_logs'
                }

    # Categorize failures
    for failure_key, failure_data in all_failures.items():
        category = failure_data['category']

        # Map category names to the dict keys in findings
        category_mapping = {
            'infrastructure': 'infrastructure_failures',
            'service-specific': 'service_specific_failures',
            'configuration': 'configuration_failures',
            'environmental': 'environmental_failures',
            'other': 'other_failures'
        }

        target_category = category_mapping.get(category, 'other_failures')

        report['findings'][target_category][failure_key] = failure_data

        # Track by service
        for service, count in failure_data['services'].items():
            report['service_breakdown'][service]['failure_count'] += count
            report['service_breakdown'][service]['categories'][category] += count

    # Calculate totals
    report['findings']['total_distinct_failure_modes'] = len(all_failures)

    # Identify recurring vs one-off issues
    for failure_key, failure_data in all_failures.items():
        if failure_data['count'] >= 3:
            report['recurring_issues'].append({
                'failure': failure_key,
                'count': failure_data['count'],
                'category': failure_data['category'],
                'services': failure_data['services']
            })
        elif failure_data['count'] == 1:
            report['one_off_issues'].append({
                'failure': failure_key,
                'category': failure_data['category'],
                'services': failure_data['services']
            })

    # Add workflow analysis
    report['workflow_analysis'] = argo_workflows

    return report

def main():
    print("Loading deployment logs...")
    k8s_data = load_k8s_logs()
    argo_data = load_argo_logs()

    print("Analyzing failure patterns...")
    k8s_events = analyze_k8s_events(k8s_data)
    pod_failures = analyze_pod_failures(k8s_data)
    argo_workflows = analyze_argo_workflows(argo_data)

    print("Parsing application logs...")
    app_logs = {}

    # Parse pbx-web logs
    pbx_logs = parse_application_logs("/tmp/pbx-web-pbx-web-logs.txt", "pbx-web")
    if pbx_logs:
        app_logs['pbx-web'] = pbx_logs

    # Parse whisper-stt logs (if available)
    whisper_logs = parse_application_logs("/tmp/whisper-stt-main-logs.txt", "whisper-stt")
    if whisper_logs:
        app_logs['whisper-stt'] = whisper_logs

    print("Generating summary report...")
    report = generate_summary_report(k8s_events, pod_failures, argo_workflows, app_logs)

    # Save report
    output_path = Path("/home/coding/aide-de-camp/data/adc-1gmwn/failure_analysis_report.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, 'w') as f:
        json.dump(report, f, indent=2, default=str)

    print(f"\n✅ Analysis complete! Report saved to: {output_path}")

    # Print summary
    print(f"\n📊 SUMMARY")
    print(f"=" * 50)
    print(f"Total distinct failure modes: {report['findings']['total_distinct_failure_modes']}")
    print(f"\n📈 Failure by Category:")

    category_order = ['infrastructure_failures', 'service_specific_failures', 'configuration_failures', 'environmental_failures', 'other_failures']
    category_names = {
        'infrastructure_failures': 'Infrastructure',
        'service_specific_failures': 'Service-Specific',
        'configuration_failures': 'Configuration',
        'environmental_failures': 'Environmental',
        'other_failures': 'Other'
    }

    for cat_key in category_order:
        failures = report['findings'][cat_key]
        if failures:
            print(f"\n{category_names[cat_key]}:")
            for failure_key, data in sorted(failures.items(), key=lambda x: x[1]['count'], reverse=True):
                print(f"  • {failure_key}: {data['count']} occurrences")

    print(f"\n🔍 Service Breakdown:")
    for service, data in report['service_breakdown'].items():
        if data['failure_count'] > 0:
            print(f"  {service}: {data['failure_count']} total failures")
            for cat, count in data['categories'].most_common():
                print(f"    - {cat}: {count}")

    print(f"\n🔄 Recurring Issues (≥3 occurrences): {len(report['recurring_issues'])}")
    for issue in report['recurring_issues']:
        print(f"  • {issue['failure']}: {issue['count']} times ({issue['category']})")

    print(f"\n✨ One-off Issues: {len(report['one_off_issues'])}")
    for issue in report['one_off_issues']:
        print(f"  • {issue['failure']} ({issue['category']})")

if __name__ == '__main__':
    main()