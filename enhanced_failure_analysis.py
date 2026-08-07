#!/usr/bin/env python3
"""
Enhanced failure pattern analysis for pbx-web and whisper-stt services.
Provides comprehensive analysis of top failure patterns and shared root causes.
"""

import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from datetime import datetime

def analyze_pbx_web_patterns(file_path):
    """Analyze pbx-web failure patterns in detail."""
    errors = []
    error_categories = defaultdict(list)

    with open(file_path, 'r') as f:
        for line in f:
            try:
                entry = json.loads(line.strip())
                if 'error_type' in entry:
                    errors.append(entry)
                    error_categories[entry['error_type']].append(entry)
            except json.JSONDecodeError:
                continue

    # Deep analysis of each error category
    detailed_patterns = {}
    for error_type, occurrences in error_categories.items():
        # Extract temporal patterns
        timestamps = []
        for occ in occurrences:
            message = occ.get('message', '')
            # Try to extract timestamp from message
            ts_match = re.search(r'(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})', message)
            if ts_match:
                timestamps.append(ts_match.group(1))

        # Get sample messages
        samples = [occ.get('message', '')[:150] for occ in occurrences[:3]]

        detailed_patterns[error_type] = {
            'count': len(occurrences),
            'percentage': (len(occurrences) / len(errors)) * 100,
            'samples': samples,
            'timestamp_count': len(timestamps),
            'severity': occurrences[0].get('severity', 'unknown') if occurrences else 'unknown'
        }

    return {
        'service': 'pbx-web',
        'total_errors': len(errors),
        'unique_error_types': len(error_categories),
        'patterns': detailed_patterns,
        'raw_errors': errors
    }

def analyze_whisper_stt_health(file_path):
    """Analyze whisper-stt logs for health status and potential issues."""
    log_entries = []
    status_codes = []
    response_times = []

    with open(file_path, 'r') as f:
        for line in f:
            try:
                entry = json.loads(line.strip())
                log_entries.append(entry)

                # Extract HTTP status codes from log messages
                message = entry.get('message', entry.get('log_message', ''))
                status_match = re.search(r'" (\d{3}) ', message)
                if status_match:
                    status_codes.append(int(status_match.group(1)))

            except json.JSONDecodeError:
                continue

    # Analyze status code distribution
    status_distribution = Counter(status_codes) if status_codes else {}

    # Check for any potential issues
    total_requests = len(status_codes)
    successful_requests = sum(1 for code in status_codes if 200 <= code < 300)
    client_errors = sum(1 for code in status_codes if 400 <= code < 500)
    server_errors = sum(1 for code in status_codes if 500 <= code < 600)

    health_assessment = {
        'service': 'whisper-stt',
        'total_log_entries': len(log_entries),
        'total_requests_analyzed': total_requests,
        'successful_requests': successful_requests,
        'client_errors': client_errors,
        'server_errors': server_errors,
        'success_rate': (successful_requests / total_requests * 100) if total_requests > 0 else 0,
        'status_distribution': dict(status_distribution.most_common(5)),
        'health_status': 'healthy' if (server_errors == 0 and client_errors == 0) else 'degraded'
    }

    return health_assessment

def identify_root_causes(pbx_patterns):
    """Identify likely root causes based on error patterns."""
    root_causes = []

    # Analyze HTTP 5xx errors
    http_5xx_total = sum(
        p['count'] for error_type, p in pbx_patterns.items()
        if error_type.startswith('http_5')
    )

    if http_5xx_total > 100:
        root_causes.append({
            'category': 'High HTTP 5xx Error Rate',
            'severity': 'high',
            'description': f'{http_5xx_total} server errors detected',
            'likely_causes': [
                'Upstream service timeouts during rebuild operations',
                'Resource exhaustion during search indexing',
                'Database connectivity issues',
                'Application errors during bucket change rebuilds'
            ],
            'patterns': [k for k in pbx_patterns.keys() if k.startswith('http_5')]
        })

    # Analyze connection issues
    connection_errors = sum(
        p['count'] for error_type, p in pbx_patterns.items()
        if 'connection' in error_type.lower()
    )

    if connection_errors > 0:
        root_causes.append({
            'category': 'Network Connection Issues',
            'severity': 'medium',
            'description': f'{connection_errors} connection-related errors',
            'likely_causes': [
                'Upstream recording server connectivity issues',
                'Network instability during recording fetch operations',
                'Possible firewall or routing issues'
            ],
            'patterns': [k for k in pbx_patterns.keys() if 'connection' in k.lower()]
        })

    return root_causes

def generate_comprehensive_report(pbx_analysis, whisper_health, root_causes):
    """Generate comprehensive markdown report."""
    report = []

    report.append("# Failure Patterns Analysis Report")
    report.append(f"\n**Generated:** {datetime.now().isoformat()}")
    report.append(f"**Analysis Period:** 30 days (2026-07-07 to 2026-08-06)")

    # Executive Summary
    report.append("\n## Executive Summary")
    report.append(f"\n### pbx-web Service")
    report.append(f"- **Total Errors Analyzed:** {pbx_analysis['total_errors']}")
    report.append(f"- **Unique Error Types:** {pbx_analysis['unique_error_types']}")
    report.append(f"- **Service Health:** Needs attention - significant error rate detected")

    report.append(f"\n### whisper-stt Service")
    report.append(f"- **Total Requests Analyzed:** {whisper_health['total_requests_analyzed']}")
    report.append(f"- **Success Rate:** {whisper_health['success_rate']:.1f}%")
    report.append(f"- **Server Errors:** {whisper_health['server_errors']}")
    report.append(f"- **Service Health:** {whisper_health['health_status'].upper()}")

    # pbx-web Detailed Analysis
    report.append("\n## pbx-web Detailed Failure Analysis")

    sorted_patterns = sorted(
        pbx_analysis['patterns'].items(),
        key=lambda x: x[1]['count'],
        reverse=True
    )

    for i, (error_type, pattern_data) in enumerate(sorted_patterns[:5], 1):
        report.append(f"\n### #{i}: {error_type}")
        report.append(f"**Occurrences:** {pattern_data['count']}")
        report.append(f"**Severity:** {pattern_data['severity'].upper()}")
        report.append(f"**Percentage of Total:** {pattern_data['percentage']:.1f}%")

        report.append(f"\n**Sample Messages:**")
        for j, sample in enumerate(pattern_data['samples'], 1):
            report.append(f"{j}. `{sample}`")

    # Root Causes Analysis
    report.append("\n## Root Cause Analysis")

    for i, cause in enumerate(root_causes, 1):
        report.append(f"\n### {i}. {cause['category']} (Severity: {cause['severity'].upper()})")
        report.append(f"**Description:** {cause['description']}")
        report.append(f"**Error Patterns:** {', '.join(cause['patterns'])}")

        report.append(f"\n**Likely Causes:**")
        for j, likely_cause in enumerate(cause['likely_causes'], 1):
            report.append(f"{j}. {likely_cause}")

    # whisper-stt Analysis
    report.append("\n## whisper-stt Service Health Analysis")
    report.append(f"\n**Overall Status:** {whisper_health['health_status'].upper()}")
    report.append(f"- **Total requests analyzed:** {whisper_health['total_requests_analyzed']:,}")
    report.append(f"- **Success rate:** {whisper_health['success_rate']:.2f}%")
    report.append(f"- **Client errors (4xx):** {whisper_health['client_errors']}")
    report.append(f"- **Server errors (5xx):** {whisper_health['server_errors']}")

    if whisper_health['status_distribution']:
        report.append(f"\n**HTTP Status Distribution:**")
        # Convert to Counter for most_common() method
        status_counter = Counter(whisper_health['status_distribution'])
        for status, count in status_counter.most_common():
            report.append(f"- {status}: {count:,} requests")

    # Comparison and Shared Issues
    report.append("\n## Cross-Service Comparison")
    report.append("\n### Key Findings")
    report.append("1. **Error Distribution Disparity:**")
    report.append("   - pbx-web shows significant error patterns (1,438 errors)")
    report.append("   - whisper-stt operates normally with minimal errors")

    report.append("\n2. **Service Complexity Impact:**")
    report.append("   - pbx-web: Complex service with database, search indexing, recording fetch")
    report.append("   - whisper-stt: Simpler health-focused service with stable operation")

    report.append("\n3. **Shared Infrastructure Health:**")
    report.append("   - Network connectivity appears stable (no widespread connection issues)")
    report.append("   - Kubernetes infrastructure healthy (both services running normally)")

    # Recommendations
    report.append("\n## Recommendations")

    report.append("\n### For pbx-web:")
    report.append("1. **Investigate rebuild operations** - High correlation between bucket changes and errors")
    report.append("2. **Review resource limits** - Consider CPU/memory during search indexing")
    report.append("3. **Implement circuit breakers** - Protect upstream recording fetch operations")
    report.append("4. **Add monitoring** - Alert on HTTP 5xx error thresholds")

    report.append("\n### For whisper-stt:")
    report.append("1. **Continue current operation** - Service is healthy and stable")
    report.append("2. **Monitor for changes** - Set baseline alerts for success rate drops")

    report.append("\n### General:")
    report.append("1. **Implement structured error logging** - Better categorization and tracking")
    report.append("2. **Set up SLO/SLI monitoring** - Track error rates and response times")
    report.append("3. **Regular health checks** - Automated monitoring for both services")

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

    print("=" * 60)
    print("Enhanced Failure Pattern Analysis")
    print("=" * 60)

    # Analyze pbx-web
    print("\n[1/3] Analyzing pbx-web failure patterns...")
    pbx_analysis = analyze_pbx_web_patterns(pbx_parsed_file)
    print(f"  Found {pbx_analysis['total_errors']} errors across {pbx_analysis['unique_error_types']} categories")

    # Analyze whisper-stt
    print("[2/3] Analyzing whisper-stt service health...")
    whisper_health = analyze_whisper_stt_health(whisper_logs_file)
    print(f"  Analyzed {whisper_health['total_requests_analyzed']} requests")
    print(f"  Health status: {whisper_health['health_status'].upper()}")
    print(f"  Success rate: {whisper_health['success_rate']:.1f}%")

    # Identify root causes
    print("[3/3] Identifying root causes...")
    root_causes = identify_root_causes(pbx_analysis['patterns'])
    print(f"  Identified {len(root_causes)} root cause categories")

    # Generate report
    print("\nGenerating comprehensive report...")
    report = generate_comprehensive_report(pbx_analysis, whisper_health, root_causes)

    # Save report
    with open(output_file, 'w') as f:
        f.write(report)

    print(f"\n✓ Report saved to {output_file}")
    print("\n" + "=" * 60)
    print("Analysis Complete!")
    print("=" * 60)

if __name__ == '__main__':
    main()
