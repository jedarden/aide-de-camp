#!/usr/bin/env python3
"""Validate deployment data completeness and 30-day coverage."""

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Tuple
import sys


def load_json(file_path: Path) -> Dict[str, Any]:
    """Load and parse a JSON file."""
    try:
        with open(file_path, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"ERROR: File not found: {file_path}")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"ERROR: Invalid JSON in {file_path}: {e}")
        sys.exit(1)


def parse_timestamp(ts: str) -> datetime:
    """Parse ISO8601 timestamp."""
    try:
        # Handle both 'Z' suffix and no timezone
        if ts.endswith('Z'):
            ts = ts[:-1] + '+00:00'
        return datetime.fromisoformat(ts)
    except ValueError as e:
        print(f"ERROR: Invalid timestamp format: {ts}")
        sys.exit(1)


def check_required_fields(deployment: Dict[str, Any]) -> List[str]:
    """Check for missing required fields in a deployment."""
    required_fields = ['timestamp', 'image_tag', 'status']
    missing = []
    for field in required_fields:
        if field not in deployment or deployment[field] is None:
            missing.append(field)
    return missing


def check_critical_nulls(deployment: Dict[str, Any]) -> List[str]:
    """Check for null values in critical fields."""
    critical_fields = ['timestamp', 'image_tag', 'status']
    null_fields = []
    for field in critical_fields:
        if field in deployment and deployment[field] is None:
            null_fields.append(field)
    return null_fields


def analyze_deployments(data: Dict[str, Any]) -> Dict[str, Any]:
    """Analyze deployment data for quality and completeness."""
    deployments = data.get('deployments', [])
    service = data.get('service', 'unknown')

    if not deployments:
        return {
            'service': service,
            'total_deployments': 0,
            'success_count': 0,
            'failed_count': 0,
            'oldest_timestamp': None,
            'newest_timestamp': None,
            'date_range_days': 0,
            'missing_fields_issues': [],
            'null_value_issues': [],
            'gaps': [],
            'valid': False,
            'error': 'No deployments found'
        }

    # Parse timestamps and check validity
    timestamps = []
    missing_fields_issues = []
    null_value_issues = []

    for i, deployment in enumerate(deployments):
        # Check required fields
        missing = check_required_fields(deployment)
        if missing:
            missing_fields_issues.append({
                'index': i,
                'timestamp': deployment.get('timestamp', 'unknown'),
                'missing_fields': missing
            })

        # Check for null critical values
        nulls = check_critical_nulls(deployment)
        if nulls:
            null_value_issues.append({
                'index': i,
                'timestamp': deployment.get('timestamp', 'unknown'),
                'null_fields': nulls
            })

        # Parse timestamp
        try:
            ts = parse_timestamp(deployment['timestamp'])
            timestamps.append((ts, deployment['timestamp']))
        except (ValueError, KeyError) as e:
            print(f"WARNING: Invalid timestamp at index {i}: {deployment.get('timestamp')}")
            continue

    # Count successes and failures
    success_count = sum(1 for d in deployments if d.get('status') == 'success')
    failed_count = sum(1 for d in deployments if d.get('status') == 'failed')

    # Calculate date range
    if timestamps:
        timestamps.sort(key=lambda x: x[0])
        oldest = timestamps[0][0]
        newest = timestamps[-1][0]
        date_range_days = (newest - oldest).days
    else:
        oldest = None
        newest = None
        date_range_days = 0

    # Check for gaps > 7 days
    gaps = []
    for i in range(1, len(timestamps)):
        gap_days = (timestamps[i][0] - timestamps[i-1][0]).days
        if gap_days > 7:
            gaps.append({
                'gap_start': timestamps[i-1][1],
                'gap_end': timestamps[i][1],
                'gap_days': gap_days
            })

    return {
        'service': service,
        'total_deployments': len(deployments),
        'success_count': success_count,
        'failed_count': failed_count,
        'oldest_timestamp': timestamps[0][1] if timestamps else None,
        'newest_timestamp': timestamps[-1][1] if timestamps else None,
        'date_range_days': date_range_days,
        'missing_fields_issues': missing_fields_issues,
        'null_value_issues': null_value_issues,
        'gaps': gaps,
        'valid': len(missing_fields_issues) == 0 and len(null_value_issues) == 0 and date_range_days >= 30
    }


def generate_report(pbx_analysis: Dict[str, Any], whisper_analysis: Dict[str, Any]) -> str:
    """Generate a markdown validation report."""
    report_lines = [
        "# Deployment Data Validation Report",
        "",
        f"**Generated:** {datetime.now().isoformat()}",
        "",
        "## Summary",
        "",
    ]

    # Overall validation status
    both_valid = pbx_analysis.get('valid', False) and whisper_analysis.get('valid', False)
    report_lines.append(f"**Overall Status:** {'✅ VALID' if both_valid else '❌ INVALID'}")
    report_lines.append("")

    # Combined statistics
    total_deployments = pbx_analysis['total_deployments'] + whisper_analysis['total_deployments']
    total_success = pbx_analysis['success_count'] + whisper_analysis['success_count']
    total_failed = pbx_analysis['failed_count'] + whisper_analysis['failed_count']

    # Date range across both services
    all_dates = []
    if pbx_analysis['oldest_timestamp'] and pbx_analysis['newest_timestamp']:
        all_dates.append((parse_timestamp(pbx_analysis['oldest_timestamp']), parse_timestamp(pbx_analysis['newest_timestamp'])))
    if whisper_analysis['oldest_timestamp'] and whisper_analysis['newest_timestamp']:
        all_dates.append((parse_timestamp(whisper_analysis['oldest_timestamp']), parse_timestamp(whisper_analysis['newest_timestamp'])))

    if all_dates:
        overall_oldest = min(d[0] for d in all_dates)
        overall_newest = max(d[1] for d in all_dates)
        overall_range = (overall_newest - overall_oldest).days
    else:
        overall_range = 0

    report_lines.extend([
        f"- **Total Deployments:** {total_deployments}",
        f"- **Successful:** {total_success}",
        f"- **Failed:** {total_failed}",
        f"- **Overall Date Range:** {overall_range} days",
        ""
    ])

    # 30-day coverage check
    report_lines.extend([
        "## 30-Day Coverage Check",
        "",
        f"**Requirement:** At least 30 days of deployment data",
        f"**Actual Coverage:** {overall_range} days",
        f"**Status:** {'✅ PASS' if overall_range >= 30 else '❌ FAIL'}",
        ""
    ])

    if overall_range < 30:
        report_lines.extend([
            f"**WARNING:** Dataset covers only {overall_range} days, short of the 30-day requirement.",
            ""
        ])

    # Per-service details
    for analysis in [pbx_analysis, whisper_analysis]:
        service = analysis['service']
        report_lines.extend([
            f"## {service.upper()} Service",
            "",
            f"**Total Deployments:** {analysis['total_deployments']}",
            f"**Success:** {analysis['success_count']}",
            f"**Failed:** {analysis['failed_count']}",
            f"**Date Range:** {analysis['date_range_days']} days",
            f"**Oldest:** {analysis['oldest_timestamp']}",
            f"**Newest:** {analysis['newest_timestamp']}",
            ""
        ])

        # Validation status
        status = "✅ VALID" if analysis['valid'] else "❌ INVALID"
        report_lines.extend([
            f"**Validation Status:** {status}",
            ""
        ])

        # Issues found
        if analysis['missing_fields_issues']:
            report_lines.extend([
                "### Missing Required Fields",
                ""
            ])
            for issue in analysis['missing_fields_issues']:
                report_lines.append(
                    f"- Deployment #{issue['index']} ({issue['timestamp']}): "
                    f"missing {', '.join(issue['missing_fields'])}"
                )
            report_lines.append("")

        if analysis['null_value_issues']:
            report_lines.extend([
                "### Null Critical Values",
                ""
            ])
            for issue in analysis['null_value_issues']:
                report_lines.append(
                    f"- Deployment #{issue['index']} ({issue['timestamp']}): "
                    f"null values in {', '.join(issue['null_fields'])}"
                )
            report_lines.append("")

        if analysis['gaps']:
            report_lines.extend([
                "### Data Gaps (>7 days)",
                ""
            ])
            for gap in analysis['gaps']:
                report_lines.append(
                    f"- Gap of {gap['gap_days']} days: {gap['gap_start']} to {gap['gap_end']}"
                )
            report_lines.append("")

        if analysis.get('error'):
            report_lines.extend([
                f"### Error",
                "",
                f"{analysis['error']}",
                ""
            ])

    # Overall recommendations
    report_lines.extend([
        "## Recommendations",
        ""
    ])

    issues = []
    if overall_range < 30:
        issues.append(f"⚠️ Expand data collection to cover 30 days (currently {overall_range} days)")

    if pbx_analysis.get('gaps') or whisper_analysis.get('gaps'):
        issues.append("⚠️ Investigate deployment gaps >7 days - may indicate missing events")

    if pbx_analysis.get('missing_fields_issues') or whisper_analysis.get('missing_fields_issues'):
        issues.append("⚠️ Fix missing required fields in deployment records")

    if pbx_analysis.get('null_value_issues') or whisper_analysis.get('null_value_issues'):
        issues.append("⚠️ Address null values in critical fields")

    if not issues:
        issues.append("✅ All validation checks passed - data is complete and covers 30+ days")

    report_lines.extend(issues)

    return "\n".join(report_lines)


def main():
    """Main validation entry point."""
    base_dir = Path("/home/coding/aide-de-camp/docs/research/deployment-data")

    print("Loading deployment files...")
    pbx_data = load_json(base_dir / "pbx-web-deployments.json")
    whisper_data = load_json(base_dir / "whisper-stt-deployments.json")

    print("Analyzing pbx-web deployments...")
    pbx_analysis = analyze_deployments(pbx_data)

    print("Analyzing whisper-stt deployments...")
    whisper_analysis = analyze_deployments(whisper_data)

    print("Generating validation report...")
    report = generate_report(pbx_analysis, whisper_analysis)

    report_path = base_dir / "validation-report.md"
    with open(report_path, 'w') as f:
        f.write(report)

    print(f"✅ Validation report saved to: {report_path}")
    print()

    # Print summary to console
    print("=== VALIDATION SUMMARY ===")
    print(f"Total deployments: {pbx_analysis['total_deployments'] + whisper_analysis['total_deployments']}")
    print(f"Overall date range: {pbx_analysis['date_range_days']} and {whisper_analysis['date_range_days']} days")
    print(f"Overall status: {'VALID' if pbx_analysis['valid'] and whisper_analysis['valid'] else 'INVALID'}")

    # Exit with appropriate code
    sys.exit(0 if pbx_analysis['valid'] and whisper_analysis['valid'] else 1)


if __name__ == "__main__":
    main()
