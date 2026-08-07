#!/usr/bin/env python3
"""
Analyze failure patterns for pbx-web and whisper-stt services.
Extracts top 5 error types for each service and identifies shared root causes.
"""

import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from datetime import datetime

def parse_pbx_web_errors(file_path):
    """Parse pbx-web parsed errors and categorize by type."""
    errors = []

    with open(file_path, 'r') as f:
        for line in f:
            try:
                entry = json.loads(line.strip())
                if 'error_type' in entry:
                    errors.append({
                        'error_type': entry['error_type'],
                        'severity': entry.get('severity', 'unknown'),
                        'message': entry.get('message', '')[:200],  # Truncate long messages
                        'source': entry.get('source', 'unknown')
                    })
            except json.JSONDecodeError:
                continue

    return errors

def parse_whisper_stt_errors(file_path):
    """Parse whisper-stt logs and extract error patterns."""
    errors = []
    error_patterns = [
        (r'5\d{2}', 'http_5xx'),  # HTTP 5xx errors
        (r'4\d{2}', 'http_4xx'),  # HTTP 4xx errors
        (r'Connection.*reset', 'connection_reset'),
        (r'Connection.*refused', 'connection_refused'),
        (r'Connection.*timeout', 'timeout'),
        (r'Timeout', 'timeout'),
        (r'OOMKilled', 'oom_killed'),
        (r'CrashLoopBackOff', 'crash_loop_back_off'),
        (r'Error', 'generic_error'),
        (r'Failed', 'generic_failure'),
        (r'Exception', 'exception'),
        (r'errno \d+', 'errno_error'),
    ]

    with open(file_path, 'r') as f:
        for line in f:
            try:
                entry = json.loads(line.strip())
                message = entry.get('message', '')
                log_level = entry.get('log_level', '')

                # Check for error indicators
                if log_level in ['ERROR', 'WARN', 'WARNING', 'CRITICAL']:
                    error_type = 'unknown_error'

                    # Try to match specific patterns
                    for pattern, category in error_patterns:
                        if re.search(pattern, message, re.IGNORECASE):
                            error_type = category
                            break

                    errors.append({
                        'error_type': error_type,
                        'severity': log_level,
                        'message': message[:200],
                        'source': 'container_logs'
                    })
            except json.JSONDecodeError:
                continue

    return errors

def categorize_and_rank(errors, service_name):
    """Categorize errors and rank by frequency."""
    # Count by error type
    error_counts = Counter(error['error_type'] for error in errors)

    # Get top 5
    top_5 = error_counts.most_common(5)

    # Get detailed breakdown for top 5
    detailed = []
    for error_type, count in top_5:
        # Get sample messages for this error type
        samples = [e['message'] for e in errors if e['error_type'] == error_type][:3]

        # Get severity breakdown
        severity_counts = Counter(e['severity'] for e in errors if e['error_type'] == error_type)

        detailed.append({
            'error_type': error_type,
            'count': count,
            'percentage': (count / len(errors)) * 100 if errors else 0,
            'severity_breakdown': dict(severity_counts),
            'sample_messages': samples
        })

    return {
        'service': service_name,
        'total_errors': len(errors),
        'unique_error_types': len(error_counts),
        'top_5': detailed
    }

def identify_shared_root_causes(pbx_results, whisper_results):
    """Identify shared root causes between services."""
    pbx_error_types = set(item['error_type'] for item in pbx_results['top_5'])
    whisper_error_types = set(item['error_type'] for item in whisper_results['top_5'])

    shared = pbx_error_types & whisper_error_types

    # Map shared errors to likely root causes
    root_cause_mapping = {
        'connection_reset': 'Network instability or upstream service failures',
        'connection_refused': 'Service unavailable or port binding issues',
        'timeout': 'Resource exhaustion, slow upstream services, or network latency',
        'http_5xx': 'Upstream service failures or internal server errors',
        'http_4xx': 'Client request errors or rate limiting',
        'oom_killed': 'Memory exhaustion, memory leaks, or insufficient limits',
        'crash_loop_back_off': 'Application crashes, missing dependencies, or config errors',
    }

    shared_root_causes = {}
    for error_type in shared:
        if error_type in root_cause_mapping:
            shared_root_causes[error_type] = root_cause_mapping[error_type]

    # Identify service-specific patterns
    pbx_specific = pbx_error_types - whisper_error_types
    whisper_specific = whisper_error_types - pbx_error_types

    return {
        'shared_error_types': list(shared),
        'shared_root_causes': shared_root_causes,
        'pbx_specific_patterns': list(pbx_specific),
        'whisper_specific_patterns': list(whisper_specific)
    }

def generate_report(pbx_results, whisper_results, shared_analysis):
    """Generate a comprehensive markdown report."""
    report = []

    report.append("# Failure Patterns Analysis Report")
    report.append(f"\nGenerated: {datetime.now().isoformat()}")
    report.append("\n## Overview")
    report.append(f"- pbx-web total errors: {pbx_results['total_errors']}")
    report.append(f"- pbx-web unique error types: {pbx_results['unique_error_types']}")
    report.append(f"- whisper-stt total errors: {whisper_results['total_errors']}")
    report.append(f"- whisper-stt unique error types: {whisper_results['unique_error_types']}")

    report.append("\n## pbx-web Top 5 Failure Patterns")
    for i, item in enumerate(pbx_results['top_5'], 1):
        report.append(f"\n### {i}. {item['error_type']}")
        report.append(f"- **Count**: {item['count']}")
        report.append(f"- **Percentage**: {item['percentage']:.2f}%")
        report.append(f"- **Severity breakdown**: {item['severity_breakdown']}")
        report.append(f"- **Sample messages**:")
        for msg in item['sample_messages']:
            report.append(f"  - `{msg[:100]}...`")

    report.append("\n## whisper-stt Top 5 Failure Patterns")
    for i, item in enumerate(whisper_results['top_5'], 1):
        report.append(f"\n### {i}. {item['error_type']}")
        report.append(f"- **Count**: {item['count']}")
        report.append(f"- **Percentage**: {item['percentage']:.2f}%")
        report.append(f"- **Severity breakdown**: {item['severity_breakdown']}")
        report.append(f"- **Sample messages**:")
        for msg in item['sample_messages']:
            report.append(f"  - `{msg[:100]}...`")

    report.append("\n## Shared Root Causes")
    if shared_analysis['shared_error_types']:
        report.append(f"\n### Common Error Types")
        for error_type in shared_analysis['shared_error_types']:
            report.append(f"- **{error_type}**")

        report.append(f"\n### Shared Root Causes")
        for error_type, root_cause in shared_analysis['shared_root_causes'].items():
            report.append(f"- **{error_type}**: {root_cause}")
    else:
        report.append("\nNo shared error types found in top 5.")

    report.append(f"\n### pbx-web Specific Patterns")
    for pattern in shared_analysis['pbx_specific_patterns']:
        report.append(f"- {pattern}")

    report.append(f"\n### whisper-stt Specific Patterns")
    for pattern in shared_analysis['whisper_specific_patterns']:
        report.append(f"- {pattern}")

    report.append("\n## Recommendations")

    if 'connection_reset' in shared_analysis['shared_error_types'] or 'timeout' in shared_analysis['shared_error_types']:
        report.append("- **Network/Timeout issues**: Review network stability and upstream service health. Consider implementing retry logic with exponential backoff.")

    if 'http_5xx' in shared_analysis['shared_error_types']:
        report.append("- **HTTP 5xx errors**: Investigate upstream service failures. Implement circuit breakers and fallback mechanisms.")

    if 'oom_killed' in str(shared_analysis):
        report.append("- **Memory issues**: Review memory limits and investigate potential memory leaks. Consider increasing limits or optimizing memory usage.")

    if 'crash_loop_back_off' in str(shared_analysis):
        report.append("- **Crash loops**: Check application logs for startup failures. Validate configuration and dependencies.")

    return "\n".join(report)

def main():
    """Main execution."""
    base_path = Path('/home/coding/aide-de-camp')

    # File paths
    pbx_parsed_file = base_path / 'logs' / 'pbx-web-parsed.jsonl'
    whisper_logs_file = base_path / 'logs' / 'whisper-stt-30day.jsonl'
    output_file = base_path / 'analysis' / 'failure-patterns.md'

    # Ensure output directory exists
    output_file.parent.mkdir(exist_ok=True)

    print("Analyzing failure patterns...")

    # Parse pbx-web errors
    print(f"Parsing pbx-web errors from {pbx_parsed_file}...")
    pbx_errors = parse_pbx_web_errors(pbx_parsed_file)
    print(f"  Found {len(pbx_errors)} errors")

    # Parse whisper-stt errors
    print(f"Parsing whisper-stt errors from {whisper_logs_file}...")
    whisper_errors = parse_whisper_stt_errors(whisper_logs_file)
    print(f"  Found {len(whisper_errors)} errors")

    # Categorize and rank
    print("Categorizing and ranking errors...")
    pbx_results = categorize_and_rank(pbx_errors, 'pbx-web')
    whisper_results = categorize_and_rank(whisper_errors, 'whisper-stt')

    # Identify shared root causes
    print("Identifying shared root causes...")
    shared_analysis = identify_shared_root_causes(pbx_results, whisper_results)

    # Generate report
    print("Generating report...")
    report = generate_report(pbx_results, whisper_results, shared_analysis)

    # Save report
    with open(output_file, 'w') as f:
        f.write(report)

    print(f"\nReport saved to {output_file}")
    print("\n=== SUMMARY ===")
    print(f"pbx-web: {pbx_results['total_errors']} errors, {pbx_results['unique_error_types']} unique types")
    print(f"whisper-stt: {whisper_results['total_errors']} errors, {whisper_results['unique_error_types']} unique types")
    print(f"Shared error types: {len(shared_analysis['shared_error_types'])}")

    return pbx_results, whisper_results, shared_analysis

if __name__ == '__main__':
    main()
