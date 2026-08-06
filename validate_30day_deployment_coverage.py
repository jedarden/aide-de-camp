#!/usr/bin/env python3
"""
Validate deployment data completeness and 30-day coverage.
Analyzes pbx-web-deployments.json and whisper-stt-deployments.json
"""

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List
from collections import defaultdict


def load_json(filepath: Path) -> List[Dict[str, Any]]:
    """Load and parse JSON file."""
    try:
        with open(filepath, 'r') as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading {filepath}: {e}")
        return []


def validate_timestamp(ts: str) -> bool:
    """Validate ISO8601 timestamp format."""
    try:
        datetime.fromisoformat(ts.replace('Z', '+00:00'))
        return True
    except Exception:
        return False


def validate_deployment_entry(entry: Dict[str, Any], index: int) -> List[str]:
    """Validate a single deployment entry."""
    errors = []

    # Check required fields
    required_fields = ['timestamp', 'image_tag', 'status']
    for field in required_fields:
        if field not in entry:
            errors.append(f"Entry {index}: Missing required field '{field}'")

    # Validate timestamp format
    if 'timestamp' in entry:
        if not validate_timestamp(entry['timestamp']):
            errors.append(f"Entry {index}: Invalid timestamp format '{entry['timestamp']}'")

    # Check for null critical values
    if 'timestamp' in entry and entry['timestamp'] is None:
        errors.append(f"Entry {index}: Null timestamp")
    if 'image_tag' in entry and entry['image_tag'] is None:
        errors.append(f"Entry {index}: Null image_tag")
    if 'status' in entry and entry['status'] is None:
        errors.append(f"Entry {index}: Null status")

    # Validate status values
    if 'status' in entry and entry['status'] not in ['success', 'failed']:
        errors.append(f"Entry {index}: Invalid status value '{entry['status']}' (must be 'success' or 'failed')")

    return errors


def analyze_deployments(deployment_data: Dict[str, Any]) -> Dict[str, Any]:
    """Analyze deployment data for a service."""
    if not deployment_data or 'deployments' not in deployment_data:
        return {
            'service': 'unknown',
            'total_deployments': 0,
            'successful_deployments': 0,
            'failed_deployments': 0,
            'errors': ['No deployment data found'],
            'date_range': None,
            'days_covered': 0,
            'gaps': []
        }

    deployments = deployment_data['deployments']
    service_name = deployment_data.get('service', 'unknown')

    if not deployments:
        return {
            'service': service_name,
            'total_deployments': 0,
            'successful_deployments': 0,
            'failed_deployments': 0,
            'errors': ['No deployment records found'],
            'date_range': None,
            'days_covered': 0,
            'gaps': []
        }

    # Validate entries
    all_errors = []
    for i, entry in enumerate(deployments):
        errors = validate_deployment_entry(entry, i)
        all_errors.extend(errors)

    # Extract timestamps
    timestamps = []
    for entry in deployments:
        try:
            ts = datetime.fromisoformat(entry['timestamp'].replace('Z', '+00:00'))
            timestamps.append(ts)
        except Exception:
            pass

    if not timestamps:
        return {
            'service': service_name,
            'total_deployments': len(deployments),
            'successful_deployments': 0,
            'failed_deployments': 0,
            'errors': all_errors + ['No valid timestamps found'],
            'date_range': None,
            'days_covered': 0,
            'gaps': []
        }

    # Sort timestamps
    timestamps.sort()

    # Calculate date range
    oldest = timestamps[0]
    newest = timestamps[-1]
    days_covered = (newest - oldest).days

    # Count success/failure using status field
    successful = sum(1 for entry in deployments if entry.get('status') == 'success')
    failed = sum(1 for entry in deployments if entry.get('status') == 'failed')

    # Identify gaps > 7 days
    gaps = []
    for i in range(1, len(timestamps)):
        gap_days = (timestamps[i] - timestamps[i-1]).days
        if gap_days > 7:
            gaps.append({
                'gap_start': timestamps[i-1].isoformat(),
                'gap_end': timestamps[i].isoformat(),
                'gap_days': gap_days
            })

    return {
        'service': service_name,
        'total_deployments': len(deployments),
        'successful_deployments': successful,
        'failed_deployments': failed,
        'errors': all_errors,
        'date_range': {
            'oldest': oldest.isoformat(),
            'newest': newest.isoformat()
        },
        'days_covered': days_covered,
        'gaps': gaps
    }


def generate_validation_report(pbx_web_data: List[Dict], whisper_stt_data: List[Dict]) -> str:
    """Generate comprehensive validation report."""

    pbx_analysis = analyze_deployments(pbx_web_data, 'pbx-web')
    whisper_analysis = analyze_deployments(whisper_stt_data, 'whisper-stt')

    # Calculate overall 30-day coverage
    all_timestamps = []
    for entry in pbx_web_data + whisper_stt_data:
        try:
            ts = datetime.fromisoformat(entry['timestamp'].replace('Z', '+00:00'))
            all_timestamps.append(ts)
        except Exception:
            pass

    all_timestamps.sort()
    overall_oldest = all_timestamps[0] if all_timestamps else None
    overall_newest = all_timestamps[-1] if all_timestamps else None
    overall_days = (overall_newest - overall_oldest).days if overall_oldest and overall_newest else 0

    # Generate report
    report_lines = [
        "# Deployment Data Validation Report",
        f"\nGenerated: {datetime.now().isoformat()}",
        "\n## Executive Summary",
        f"\n**Overall 30-Day Coverage:** {'✅ PASS' if overall_days >= 30 else '❌ FAIL'} ({overall_days} days)",
        f"\nTotal deployments analyzed: {pbx_analysis['total_deployments'] + whisper_analysis['total_deployments']}",
    ]

    # Data quality assessment
    total_errors = len(pbx_analysis['errors']) + len(whisper_analysis['errors'])
    if total_errors == 0:
        report_lines.append("\n**Data Quality:** ✅ EXCELLENT - No errors detected")
    elif total_errors <= 5:
        report_lines.append(f"\n**Data Quality:** ⚠️ ACCEPTABLE - {total_errors} minor issues")
    else:
        report_lines.append(f"\n**Data Quality:** ❌ POOR - {total_errors} errors detected")

    # PBX-Web Analysis
    report_lines.extend([
        "\n## PBX-Web Deployment Analysis",
        f"\n- **Total Deployments:** {pbx_analysis['total_deployments']}",
        f"- **Running (replicas > 0):** {pbx_analysis['running_deployments']}",
        f"- **Scaled Down (replicas = 0):** {pbx_analysis['scaled_down_deployments']}",
    ])

    if pbx_analysis['date_range']:
        report_lines.extend([
            f"- **Date Range:** {pbx_analysis['date_range']['oldest']} to {pbx_analysis['date_range']['newest']}",
            f"- **Days Covered:** {pbx_analysis['days_covered']} days",
            f"- **30-Day Coverage:** {'✅ PASS' if pbx_analysis['days_covered'] >= 30 else '⚠️ PARTIAL'}",
        ])

    if pbx_analysis['gaps']:
        report_lines.append("\n### Gaps Detected (> 7 days):")
        for gap in pbx_analysis['gaps']:
            report_lines.append(f"- **{gap['gap_days']} day gap:** {gap['gap_start']} to {gap['gap_end']}")
    else:
        report_lines.append("\n### Gaps: None - Good coverage")

    if pbx_analysis['errors']:
        report_lines.append("\n### Data Quality Issues:")
        for error in pbx_analysis['errors'][:10]:  # Limit to first 10
            report_lines.append(f"- {error}")
        if len(pbx_analysis['errors']) > 10:
            report_lines.append(f"- ... and {len(pbx_analysis['errors']) - 10} more errors")

    # Whisper-STT Analysis
    report_lines.extend([
        "\n## Whisper-STT Deployment Analysis",
        f"\n- **Total Deployments:** {whisper_analysis['total_deployments']}",
        f"- **Running (replicas > 0):** {whisper_analysis['running_deployments']}",
        f"- **Scaled Down (replicas = 0):** {whisper_analysis['scaled_down_deployments']}",
    ])

    if whisper_analysis['date_range']:
        report_lines.extend([
            f"- **Date Range:** {whisper_analysis['date_range']['oldest']} to {whisper_analysis['date_range']['newest']}",
            f"- **Days Covered:** {whisper_analysis['days_covered']} days",
            f"- **30-Day Coverage:** {'✅ PASS' if whisper_analysis['days_covered'] >= 30 else '⚠️ PARTIAL'}",
        ])

    if whisper_analysis['gaps']:
        report_lines.append("\n### Gaps Detected (> 7 days):")
        for gap in whisper_analysis['gaps']:
            report_lines.append(f"- **{gap['gap_days']} day gap:** {gap['gap_start']} to {gap['gap_end']}")
    else:
        report_lines.append("\n### Gaps: None - Good coverage")

    if whisper_analysis['errors']:
        report_lines.append("\n### Data Quality Issues:")
        for error in whisper_analysis['errors'][:10]:  # Limit to first 10
            report_lines.append(f"- {error}")
        if len(whisper_analysis['errors']) > 10:
            report_lines.append(f"- ... and {len(whisper_analysis['errors']) - 10} more errors")

    # Conclusions and Recommendations
    report_lines.extend([
        "\n## Conclusions and Recommendations",
        "\n### 30-Day Coverage Assessment:",
        f"- Overall dataset spans {overall_days} days ({'✅ meets requirement' if overall_days >= 30 else '❌ does not meet 30-day requirement'})",
    ])

    all_gaps = pbx_analysis['gaps'] + whisper_analysis['gaps']
    if all_gaps:
        report_lines.append(f"\n### Data Gaps:")
        report_lines.append(f"- {len(all_gaps)} gaps > 7 days detected across both services")
        for gap in sorted(all_gaps, key=lambda g: g['gap_days'], reverse=True)[:5]:
            report_lines.append(f"  - {gap['gap_days']} day gap in deployment data")
    else:
        report_lines.append("\n### Data Gaps: None - Excellent temporal coverage")

    report_lines.extend([
        "\n### Data Quality:",
        f"- Required fields present: {'✅ Yes' if total_errors == 0 else '❌ Issues detected'}",
        f"- ISO8601 timestamp format: {'✅ Valid' if all('Invalid' not in e and 'format' not in e for e in (pbx_analysis['errors'] + whisper_analysis['errors'])) else '❌ Invalid formats found'}",
        f"- Null critical values: {'✅ None' if all('Null' not in e for e in (pbx_analysis['errors'] + whisper_analysis['errors'])) else '❌ Null values detected'}",
    ])

    # Add recommendations based on findings
    report_lines.append("\n### Recommendations:")
    if overall_days < 30:
        report_lines.append("- ⚠️ **CRITICAL:** Dataset does not meet 30-day requirement. Consider extending data collection period.")
    if all_gaps:
        report_lines.append(f"- ⚠️ **WARNING:** {len(all_gaps)} significant gaps detected. Review deployment patterns for anomalies.")
    if total_errors > 0:
        report_lines.append(f"- ⚠️ **ACTION:** Fix {total_errors} data quality issues before using for analysis.")
    if total_errors == 0 and overall_days >= 30 and not all_gaps:
        report_lines.append("- ✅ **EXCELLENT:** Data quality and coverage meet all requirements. Ready for analysis.")

    return "\n".join(report_lines)


def main():
    """Main validation function."""
    base_dir = Path('/home/coding/aide-de-camp/docs/research/deployment-data')

    pbx_web_file = base_dir / 'pbx-web-deployments.json'
    whisper_stt_file = base_dir / 'whisper-stt-deployments.json'

    print("Loading deployment data...")
    pbx_web_data = load_json(pbx_web_file)
    whisper_stt_data = load_json(whisper_stt_file)

    print(f"Loaded pbx-web data: {pbx_web_data.get('service', 'unknown')}")
    print(f"Loaded whisper-stt data: {whisper_stt_data.get('service', 'unknown')}")

    print("Generating validation report...")
    report = generate_validation_report(pbx_web_data, whisper_stt_data)

    # Save report
    output_file = base_dir / 'validation-report.md'
    with open(output_file, 'w') as f:
        f.write(report)

    print(f"Report saved to {output_file}")
    print("\n" + "="*60)
    print(report)
    print("="*60)


if __name__ == '__main__':
    main()
