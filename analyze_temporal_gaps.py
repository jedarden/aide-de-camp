#!/usr/bin/env python3
"""
Temporal Gap Analysis for pbx-web and whisper-stt datasets.
Analyzes coverage, detects gaps, and generates comprehensive reports.
"""

import csv
import json
import sys
from datetime import datetime, timedelta
from collections import defaultdict
from pathlib import Path

def parse_timestamp(ts_str):
    """Parse ISO 8601 timestamp with timezone handling."""
    try:
        # Handle various timestamp formats
        if ts_str.endswith('Z'):
            return datetime.fromisoformat(ts_str.replace('Z', '+00:00'))
        elif '+' in ts_str or ts_str.count('-') > 2:  # Has timezone
            return datetime.fromisoformat(ts_str)
        else:  # No timezone, assume UTC
            return datetime.fromisoformat(ts_str).replace(tzinfo=None)
    except Exception as e:
        print(f"Error parsing timestamp '{ts_str}': {e}", file=sys.stderr)
        return None

def analyze_jsonl_file(file_path, dataset_name):
    """Analyze a JSONL file for temporal gaps."""
    print(f"\n{'='*60}")
    print(f"Analyzing: {dataset_name}")
    print(f"File: {file_path}")
    print(f"{'='*60}")

    if not Path(file_path).exists():
        return {
            "error": "File not found",
            "file_path": str(file_path),
            "dataset_name": dataset_name
        }

    records = []
    timestamps = []

    try:
        with open(file_path, 'r') as f:
            for line_num, line in enumerate(f, 1):
                if not line.strip():
                    continue
                try:
                    record = json.loads(line)
                    timestamps.append(record)
                    # Extract timestamp from various possible fields
                    ts_str = None
                    if 'timestamp' in record:
                        ts_str = record['timestamp']
                    elif 'time' in record:
                        ts_str = record['time']
                    elif '@timestamp' in record:
                        ts_str = record['@timestamp']

                    if ts_str:
                        ts = parse_timestamp(ts_str)
                        if ts:
                            records.append({
                                'timestamp': ts,
                                'raw_timestamp': ts_str,
                                'line_num': line_num,
                                'record': record
                            })
                except json.JSONDecodeError as e:
                    print(f"JSON decode error at line {line_num}: {e}", file=sys.stderr)

    except Exception as e:
        return {
            "error": f"Failed to read file: {e}",
            "file_path": str(file_path),
            "dataset_name": dataset_name
        }

    if not records:
        return {
            "error": "No valid timestamp records found",
            "file_path": str(file_path),
            "dataset_name": dataset_name,
            "total_lines": len(timestamps)
        }

    # Sort by timestamp
    records.sort(key=lambda x: x['timestamp'])

    # Calculate statistics
    first_ts = records[0]['timestamp']
    last_ts = records[-1]['timestamp']
    time_span = last_ts - first_ts

    # Hourly coverage
    hourly_counts = defaultdict(int)
    daily_counts = defaultdict(int)

    for rec in records:
        ts = rec['timestamp']
        hour_key = ts.strftime('%Y-%m-%d-%H')
        day_key = ts.strftime('%Y-%m-%d')
        hourly_counts[hour_key] += 1
        daily_counts[day_key] += 1

    # Detect gaps
    gaps = []
    expected_hours = int((time_span.total_seconds() / 3600)) + 1
    actual_hours = len(hourly_counts)

    # Find missing hours
    current_hour = first_ts.replace(minute=0, second=0, microsecond=0)
    end_hour = last_ts.replace(minute=0, second=0, microsecond=0)

    while current_hour <= end_hour:
        hour_key = current_hour.strftime('%Y-%m-%d-%H')
        if hour_key not in hourly_counts:
            gap_start = current_hour
            gap_end = gap_start + timedelta(hours=1)
            gaps.append({
                'start': gap_start.isoformat(),
                'end': gap_end.isoformat(),
                'duration_hours': 1,
                'severity': 'minor'
            })
        current_hour += timedelta(hours=1)

    # Find consecutive gaps and merge them
    merged_gaps = []
    if gaps:
        current_gap = gaps[0].copy()
        for gap in gaps[1:]:
            gap_start = datetime.fromisoformat(gap['start'])
            current_gap_end = datetime.fromisoformat(current_gap['end'])
            if gap_start == current_gap_end:
                # Consecutive gap, merge
                current_gap['end'] = gap['end']
                current_gap['duration_hours'] += 1
            else:
                # Non-consecutive, save current and start new
                merged_gaps.append(current_gap)
                current_gap = gap.copy()
        merged_gaps.append(current_gap)

    # Classify gap severity
    for gap in merged_gaps:
        duration = gap['duration_hours']
        if duration >= 24:
            gap['severity'] = 'critical'
        elif duration >= 6:
            gap['severity'] = 'major'
        else:
            gap['severity'] = 'minor'

    # Find partial data periods (low record count per hour)
    hourly_avg = sum(hourly_counts.values()) / len(hourly_counts) if hourly_counts else 0
    partial_periods = []
    for hour_key, count in hourly_counts.items():
        if count < hourly_avg * 0.1:  # Less than 10% of average
            hour_dt = datetime.strptime(hour_key, '%Y-%m-%d-%H')
            partial_periods.append({
                'timestamp': hour_dt.isoformat(),
                'record_count': count,
                'expected_avg': round(hourly_avg, 2),
                'severity': 'critical' if count < hourly_avg * 0.01 else 'major'
            })

    return {
        'dataset_name': dataset_name,
        'file_path': str(file_path),
        'file_size_mb': Path(file_path).stat().st_size / (1024*1024),
        'total_records': len(records),
        'first_timestamp': first_ts.isoformat(),
        'last_timestamp': last_ts.isoformat(),
        'time_span_days': time_span.total_seconds() / 86400,
        'expected_hours': expected_hours,
        'actual_hours_with_data': actual_hours,
        'hourly_coverage_pct': (actual_hours / expected_hours * 100) if expected_hours > 0 else 0,
        'daily_coverage_days': len(daily_counts),
        'gaps': merged_gaps,
        'total_gap_hours': sum(g['duration_hours'] for g in merged_gaps),
        'partial_periods': partial_periods[:20],  # Limit to first 20
        'hourly_avg_records': round(hourly_avg, 2),
        'data_quality': 'good' if len(merged_gaps) == 0 else 'degraded' if len(merged_gaps) < 10 else 'poor'
    }

def analyze_csv_file(file_path, dataset_name):
    """Analyze a CSV deployment events file for temporal gaps."""
    print(f"\n{'='*60}")
    print(f"Analyzing CSV: {dataset_name}")
    print(f"File: {file_path}")
    print(f"{'='*60}")

    if not Path(file_path).exists():
        return {
            "error": "CSV file not found",
            "file_path": str(file_path),
            "dataset_name": dataset_name
        }

    records = []
    timestamps = []

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for line_num, row in enumerate(reader, 1):
                # Extract timestamp from CSV
                timestamp_str = row.get('timestamp', '')
                if timestamp_str and timestamp_str.strip():
                    ts = parse_timestamp(timestamp_str)
                    if ts:
                        records.append({
                            'timestamp': ts,
                            'raw_timestamp': timestamp_str,
                            'line_num': line_num,
                            'record': row
                        })
                        timestamps.append(ts)
    except Exception as e:
        return {
            "error": f"Failed to read CSV file: {e}",
            "file_path": str(file_path),
            "dataset_name": dataset_name
        }

    if not records:
        return {
            "error": "No valid timestamp records found in CSV",
            "file_path": str(file_path),
            "dataset_name": dataset_name,
            "total_lines": line_num if 'line_num' in locals() else 0
        }

    # Sort by timestamp
    records.sort(key=lambda x: x['timestamp'])

    # Calculate statistics
    first_ts = records[0]['timestamp']
    last_ts = records[-1]['timestamp']
    time_span = last_ts - first_ts

    # Daily coverage
    daily_counts = defaultdict(int)

    for rec in records:
        ts = rec['timestamp']
        day_key = ts.strftime('%Y-%m-%d')
        daily_counts[day_key] += 1

    # Detect gaps
    gaps = []
    expected_days = int((time_span.total_seconds() / 86400)) + 1
    actual_days = len(daily_counts)

    # Find missing days
    current_day = first_ts.date()
    end_day = last_ts.date()

    while current_day <= end_day:
        day_key = current_day.strftime('%Y-%m-%d')
        if day_key not in daily_counts:
            gap_start = current_day
            gap_end = gap_start + timedelta(days=1)
            gaps.append({
                'start': gap_start.isoformat(),
                'end': gap_end.isoformat(),
                'duration_days': 1,
                'severity': 'minor'
            })
        current_day += timedelta(days=1)

    # Merge consecutive gaps
    merged_gaps = []
    if gaps:
        current_gap = gaps[0].copy()
        for gap in gaps[1:]:
            gap_start = datetime.fromisoformat(gap['start']).date()
            current_gap_end = datetime.fromisoformat(current_gap['end']).date()
            if gap_start == current_gap_end:
                # Consecutive gap, merge
                current_gap['end'] = gap['end']
                current_gap['duration_days'] += 1
            else:
                # Non-consecutive, save current and start new
                merged_gaps.append(current_gap)
                current_gap = gap.copy()
        merged_gaps.append(current_gap)

    # Classify gap severity
    for gap in merged_gaps:
        duration = gap['duration_days']
        if duration >= 7:
            gap['severity'] = 'critical'
        elif duration >= 3:
            gap['severity'] = 'major'
        else:
            gap['severity'] = 'minor'

    # Calculate coverage percentage
    coverage_pct = (actual_days / expected_days * 100) if expected_days > 0 else 0

    return {
        'dataset_name': dataset_name,
        'file_path': str(file_path),
        'file_size_mb': Path(file_path).stat().st_size / (1024*1024),
        'total_records': len(records),
        'first_timestamp': first_ts.isoformat(),
        'last_timestamp': last_ts.isoformat(),
        'time_span_days': time_span.total_seconds() / 86400,
        'expected_days': expected_days,
        'actual_days_with_data': actual_days,
        'daily_coverage_pct': coverage_pct,
        'gaps': merged_gaps,
        'total_gap_days': sum(g['duration_days'] for g in merged_gaps),
        'daily_avg_records': round(sum(daily_counts.values()) / len(daily_counts), 2) if daily_counts else 0,
        'data_quality': 'good' if len(merged_gaps) == 0 else 'degraded' if len(merged_gaps) < 5 else 'poor'
    }

def generate_report(pbx_analysis, whisper_analysis):
    """Generate comprehensive gap analysis report."""
    timestamp = datetime.now().isoformat()

    report = f"""# Temporal Gap Analysis Report
**Generated:** {timestamp}
**Analysis Type:** Coverage and temporal gap detection

## Executive Summary

"""

    # Extract best pbx-web data source (prioritize CSV)
    pbx_best = None
    pbx_csv = pbx_analysis.get('csv', {})
    pbx_metadata = pbx_analysis.get('metadata', {})
    pbx_parsed = pbx_analysis.get('parsed', {})
    pbx_victoria = pbx_analysis.get('victoria_logs', {})

    # Use CSV if available, else parsed logs, else victoria logs, else metadata
    if pbx_csv.get('total_records', 0) > 0:
        pbx_best = pbx_csv
        report += f"### pbx-web Dataset (using CSV deployment events)\n"
    elif pbx_parsed.get('total_records', 0) > 0:
        pbx_best = pbx_parsed
        report += f"### pbx-web Dataset (using parsed logs)\n"
    elif pbx_victoria.get('total_records', 0) > 0:
        pbx_best = pbx_victoria
        report += f"### pbx-web Dataset (using victoria logs)\n"
    else:
        report += f"### pbx-web Dataset Analysis: FAILED\n"
        report += f"- Error: No valid timestamp data found\n"
        report += f"- Metadata only available (no temporal records)\n"

    if pbx_best:
        if 'daily_coverage_pct' in pbx_best:
            report += f"""- **Time Span:** {pbx_best['time_span_days']:.1f} days
- **Total Records:** {pbx_best['total_records']:,}
- **Daily Coverage:** {pbx_best['daily_coverage_pct']:.1f}%
- **Data Quality:** {pbx_best['data_quality'].upper()}
- **Gap Days:** {pbx_best['total_gap_days']}
"""
        else:
            report += f"""- **Time Span:** {pbx_best['time_span_days']:.1f} days
- **Total Records:** {pbx_best['total_records']:,}
- **Hourly Coverage:** {pbx_best['hourly_coverage_pct']:.1f}%
- **Data Quality:** {pbx_best['data_quality'].upper()}
- **Gap Hours:** {pbx_best['total_gap_hours']}
"""

    # Extract best whisper-stt data source (prioritize CSV)
    whisper_best = None
    whisper_csv = whisper_analysis.get('csv', {})
    whisper_main = whisper_analysis.get('main', {})
    whisper_victoria = whisper_analysis.get('victoria_logs', {})

    if whisper_csv.get('total_records', 0) > 0:
        whisper_best = whisper_csv
        report += f"\n### whisper-stt Dataset (using CSV deployment events)\n"
    elif whisper_main.get('total_records', 0) > 0:
        whisper_best = whisper_main
        report += f"\n### whisper-stt Dataset (using main logs)\n"
    elif whisper_victoria.get('total_records', 0) > 0:
        whisper_best = whisper_victoria
        report += f"\n### whisper-stt Dataset (using victoria logs)\n"
    else:
        report += f"\n### whisper-stt Dataset Analysis: FAILED\n"

    if whisper_best:
        if 'daily_coverage_pct' in whisper_best:
            report += f"""- **Time Span:** {whisper_best['time_span_days']:.1f} days
- **Total Records:** {whisper_best['total_records']:,}
- **Daily Coverage:** {whisper_best['daily_coverage_pct']:.1f}%
- **Data Quality:** {whisper_best['data_quality'].upper()}
- **Gap Days:** {whisper_best['total_gap_days']}
"""
        else:
            report += f"""- **Time Span:** {whisper_best['time_span_days']:.1f} days
- **Total Records:** {whisper_best['total_records']:,}
- **Hourly Coverage:** {whisper_best['hourly_coverage_pct']:.1f}%
- **Data Quality:** {whisper_best['data_quality'].upper()}
- **Gap Hours:** {whisper_best['total_gap_hours']}
"""

    report += "\n## Data Sources Analyzed\n"

    report += f"\n### pbx-web Data Sources\n"
    report += f"- CSV deployment events: {pbx_csv.get('total_records', 0)} records\n"
    report += f"- Metadata file: {pbx_metadata.get('total_records', 0)} records (metadata only)\n"
    report += f"- Parsed logs: {pbx_parsed.get('total_records', 0)} records\n"
    report += f"- Victoria logs: {pbx_victoria.get('total_records', 0)} records\n"
    report += f"- **Total combined:** {pbx_analysis['total_records']:,} records\n"

    report += f"\n### whisper-stt Data Sources\n"
    report += f"- CSV deployment events: {whisper_csv.get('total_records', 0)} records\n"
    report += f"- Main logs: {whisper_main.get('total_records', 0)} records\n"
    report += f"- Victoria logs: {whisper_victoria.get('total_records', 0)} records\n"
    report += f"- **Total combined:** {whisper_analysis['total_records']:,} records\n"

    # Detailed findings for pbx-web
    if pbx_best:
        report += f"""## pbx-web Detailed Analysis

### Temporal Coverage
- **First Record:** {pbx_best['first_timestamp']}
- **Last Record:** {pbx_best['last_timestamp']}
"""
        if 'daily_coverage_pct' in pbx_best:
            # CSV data (daily granularity)
            report += f"""- **Expected Days:** {pbx_best['expected_days']}
- **Days with Data:** {pbx_best['actual_days_with_data']}
- **Average Records/Day:** {pbx_best['daily_avg_records']}

### Detected Gaps ({len(pbx_best['gaps'])})
"""
            if pbx_best['gaps']:
                report += "\n| Start | End | Duration (days) | Severity |\n|-------|-----|----------------|----------|\n"
                for gap in pbx_best['gaps']:
                    report += f"| {gap['start']} | {gap['end']} | {gap['duration_days']} | {gap['severity'].upper()} |\n"
            else:
                report += "\n✅ **No temporal gaps detected**\n"
        else:
            # JSONL data (hourly granularity)
            report += f"""- **Expected Hours:** {pbx_best['expected_hours']}
- **Hours with Data:** {pbx_best['actual_hours_with_data']}
- **Average Records/Hour:** {pbx_best['hourly_avg_records']}

### Detected Gaps ({len(pbx_best['gaps'])})
"""
            if pbx_best['gaps']:
                report += "\n| Start | End | Duration (hrs) | Severity |\n|-------|-----|----------------|----------|\n"
                for gap in pbx_best['gaps']:
                    report += f"| {gap['start']} | {gap['end']} | {gap['duration_hours']} | {gap['severity'].upper()} |\n"
            else:
                report += "\n✅ **No temporal gaps detected**\n"

            if pbx_best['partial_periods']:
                report += f"\n### Partial Data Periods (Low Record Count)\n| Timestamp | Records | Expected Avg | Severity |\n|-----------|---------|--------------|----------|\n"
                for period in pbx_best['partial_periods'][:10]:
                    report += f"| {period['timestamp']} | {period['record_count']} | {period['expected_avg']} | {period['severity'].upper()} |\n"
    else:
        report += "\n## pbx-web Analysis: NO VALID DATA\n"

    # Detailed findings for whisper-stt
    if whisper_best:
        report += f"""## whisper-stt Detailed Analysis

### Temporal Coverage
- **First Record:** {whisper_best['first_timestamp']}
- **Last Record:** {whisper_best['last_timestamp']}
"""
        if 'daily_coverage_pct' in whisper_best:
            # CSV data (daily granularity)
            report += f"""- **Expected Days:** {whisper_best['expected_days']}
- **Days with Data:** {whisper_best['actual_days_with_data']}
- **Average Records/Day:** {whisper_best['daily_avg_records']}

### Detected Gaps ({len(whisper_best['gaps'])})
"""
            if whisper_best['gaps']:
                report += "\n| Start | End | Duration (days) | Severity |\n|-------|-----|----------------|----------|\n"
                for gap in whisper_best['gaps']:
                    report += f"| {gap['start']} | {gap['end']} | {gap['duration_days']} | {gap['severity'].upper()} |\n"
            else:
                report += "\n✅ **No temporal gaps detected**\n"
        else:
            # JSONL data (hourly granularity)
            report += f"""- **Expected Hours:** {whisper_best['expected_hours']}
- **Hours with Data:** {whisper_best['actual_hours_with_data']}
- **Average Records/Hour:** {whisper_best['hourly_avg_records']}

### Detected Gaps ({len(whisper_best['gaps'])})
"""
            if whisper_best['gaps']:
                report += "\n| Start | End | Duration (hrs) | Severity |\n|-------|-----|----------------|----------|\n"
                for gap in whisper_best['gaps']:
                    report += f"| {gap['start']} | {gap['end']} | {gap['duration_hours']} | {gap['severity'].upper()} |\n"
            else:
                report += "\n✅ **No temporal gaps detected**\n"

            if whisper_best['partial_periods']:
                report += f"\n### Partial Data Periods (Low Record Count)\n| Timestamp | Records | Expected Avg | Severity |\n|-----------|---------|--------------|----------|\n"
                for period in whisper_best['partial_periods'][:10]:
                    report += f"| {period['timestamp']} | {period['record_count']} | {period['expected_avg']} | {period['severity'].upper()} |\n"
    else:
        report += "\n## whisper-stt Analysis: NO VALID DATA\n"

    # Summary and recommendations
    report += "\n## Severity Assessment\n\n"

    total_gaps = 0
    critical_gaps = 0
    major_gaps = 0

    if pbx_best:
        pbx_critical = len([g for g in pbx_best['gaps'] if g['severity'] == 'critical'])
        pbx_major = len([g for g in pbx_best['gaps'] if g['severity'] == 'major'])
        critical_gaps += pbx_critical
        major_gaps += pbx_major
        total_gaps += len(pbx_best['gaps'])

    if whisper_best:
        whisper_critical = len([g for g in whisper_best['gaps'] if g['severity'] == 'critical'])
        whisper_major = len([g for g in whisper_best['gaps'] if g['severity'] == 'major'])
        critical_gaps += whisper_critical
        major_gaps += whisper_major
        total_gaps += len(whisper_best['gaps'])

    report += f"""- **Total Gaps Detected:** {total_gaps}
- **Critical Gaps (≥24hrs):** {critical_gaps}
- **Major Gaps (≥6hrs):** {major_gaps}

## Anomalies Detected

"""

    if not pbx_best:
        report += "### ⚠️ CRITICAL: pbx-web dataset has no valid temporal data\n"
        report += "- Metadata file exists but contains no timestamped records\n"
        report += "- Victoria logs and parsed logs should be used instead\n"
        report += "- Suggests data collection pipeline is outputting metadata instead of log events\n\n"

    if pbx_best and pbx_best.get('file_size_mb', 0) < 0.1:
        report += f"### ⚠️ WARNING: pbx-web file size is suspiciously small ({pbx_best.get('file_size_mb', 0):.3f} MB)\n"
        report += "- Expected size for 30-day latency data should be significantly larger\n"
        report += "- Indicates incomplete data collection or extraction issue\n\n"

    if whisper_best and whisper_best.get('total_records', 0) > 0 and whisper_best.get('hourly_avg_records', 0) < 100:
        report += f"### ⚠️ WARNING: whisper-stt has unusually low record density ({whisper_best.get('hourly_avg_records', 0):.1f} records/hour)\n"
        report += "- May indicate log filtering, sampling, or collection issues\n"
        report += "- Expected hourly count for health checks alone should be higher\n\n"

    report += "## Recommendations\n\n"

    if critical_gaps > 0:
        report += "1. **URGENT:** Investigate critical gaps - check system availability, log collection failures\n"
    if major_gaps > 0:
        report += "2. **HIGH:** Review major gaps for patterns (specific times, scheduled maintenance, etc.)\n"
    if not pbx_best:
        report += "3. **URGENT:** Fix pbx-web data collection pipeline - ensure log events are captured, not just metadata\n"
    report += "4. **Implement:** Continuous monitoring with gap detection alerts\n"
    report += "5. **Archive:** Store raw data with redundant backups to prevent data loss\n"
    report += "6. **Standardize:** Implement unified data collection across both services\n"

    return report

def main():
    """Main analysis execution."""
    print("Starting temporal gap analysis...")
    print("="*60)

    # Analyze pbx-web datasets (multiple sources including CSV)
    pbx_csv = analyze_csv_file(
        './pbx-web-deployment-events-30days.csv',
        'pbx-web-csv'
    )

    pbx_metadata = analyze_jsonl_file(
        './logs/pbx-web-30day.jsonl',
        'pbx-web-metadata'
    )

    pbx_parsed = analyze_jsonl_file(
        './logs/pbx-web-parsed.jsonl',
        'pbx-web-parsed'
    )

    pbx_victoria = analyze_jsonl_file(
        './logs/pbx-web-victorialogs-raw.jsonl',
        'pbx-web-victoria-logs'
    )

    # Combine pbx-web analyses (prioritize CSV)
    pbx_analysis = {
        'csv': pbx_csv,
        'metadata': pbx_metadata,
        'parsed': pbx_parsed,
        'victoria_logs': pbx_victoria,
        'total_records': sum([
            pbx_csv.get('total_records', 0),
            pbx_metadata.get('total_records', 0),
            pbx_parsed.get('total_records', 0),
            pbx_victoria.get('total_records', 0)
        ]),
        'data_sources': ['csv', 'metadata', 'parsed_logs', 'victoria_logs']
    }

    # Analyze whisper-stt datasets (multiple sources including CSV)
    whisper_csv = analyze_csv_file(
        './whisper-stt-deployment-events-30days.csv',
        'whisper-stt-csv'
    )

    whisper_main = analyze_jsonl_file(
        './logs/whisper-stt-30day.jsonl',
        'whisper-stt-30day'
    )

    whisper_victoria = analyze_jsonl_file(
        './logs/whisper-stt-30day-victorialogs.jsonl',
        'whisper-stt-victoria-logs'
    )

    # Combine whisper-stt analyses (prioritize CSV)
    whisper_analysis = {
        'csv': whisper_csv,
        'main': whisper_main,
        'victoria_logs': whisper_victoria,
        'total_records': sum([
            whisper_csv.get('total_records', 0),
            whisper_main.get('total_records', 0),
            whisper_victoria.get('total_records', 0)
        ]),
        'data_sources': ['csv', 'main_logs', 'victoria_logs']
    }

    # Generate and save report
    report = generate_report(pbx_analysis, whisper_analysis)

    report_file = 'temporal-gap-analysis-report.md'
    with open(report_file, 'w') as f:
        f.write(report)

    print(f"\n✅ Report generated: {report_file}")

    # Also save detailed JSON analysis
    json_analysis = {
        'generated_at': datetime.now().isoformat(),
        'pbx_web': pbx_analysis,
        'whisper_stt': whisper_analysis
    }

    json_file = 'temporal-gap-analysis-details.json'
    with open(json_file, 'w') as f:
        json.dump(json_analysis, f, indent=2, default=str)

    print(f"✅ Detailed analysis saved: {json_file}")

    # Print summary
    print("\n" + "="*60)
    print("ANALYSIS SUMMARY")
    print("="*60)

    pbx_best = None
    if pbx_parsed.get('total_records', 0) > 0:
        pbx_best = pbx_parsed
    elif pbx_victoria.get('total_records', 0) > 0:
        pbx_best = pbx_victoria

    if pbx_best:
        print(f"pbx-web: {pbx_best['total_records']} records, {pbx_best['hourly_coverage_pct']:.1f}% coverage, {len(pbx_best['gaps'])} gaps")
    else:
        print(f"pbx-web: FAILED - No valid temporal data found")

    whisper_best = None
    if whisper_main.get('total_records', 0) > 0:
        whisper_best = whisper_main
    elif whisper_victoria.get('total_records', 0) > 0:
        whisper_best = whisper_victoria

    if whisper_best:
        print(f"whisper-stt: {whisper_best['total_records']} records, {whisper_best['hourly_coverage_pct']:.1f}% coverage, {len(whisper_best['gaps'])} gaps")
    else:
        print(f"whisper-stt: FAILED - No valid temporal data found")

    print("="*60)

if __name__ == '__main__':
    main()
