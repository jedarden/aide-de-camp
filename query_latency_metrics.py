#!/usr/bin/env python3
"""
Query latency metrics for pbx-web and whisper-stt over 30-day window

This script queries latency metrics (response time, processing duration) for
both pbx-web and whisper-stt spanning the full 30-day window, ensuring no
temporal gaps in coverage and storing raw latency data in intermediate format.
"""

import json
import statistics
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, List, Tuple
from collections import defaultdict


class LatencyAnalyzer:
    """Calculate latency percentiles and check for temporal gaps."""

    def __init__(self, start_date: str, end_date: str, service_name: str):
        self.start_date = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
        self.end_date = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
        self.service_name = service_name
        self.durations = []
        self.timestamps = []
        self.excluded_count = 0
        self.errors = []

        # Track temporal coverage
        self.daily_counts = defaultdict(int)
        self.hourly_counts = defaultdict(int)

    def add_duration(self, started_at: str, finished_at: str, workflow_name: str = "") -> bool:
        """Add duration if within time range, returns True if added."""
        try:
            start = datetime.fromisoformat(started_at.replace('Z', '+00:00'))
            end = datetime.fromisoformat(finished_at.replace('Z', '+00:00'))

            # Check if within 30-day window
            if self.start_date <= start <= self.end_date:
                duration = (end - start).total_seconds()
                if duration > 0:  # Only include positive durations
                    self.durations.append(duration)
                    self.timestamps.append(start)

                    # Track temporal coverage
                    date_key = start.date().isoformat()
                    hour_key = start.strftime('%Y-%m-%d-%H')
                    self.daily_counts[date_key] += 1
                    self.hourly_counts[hour_key] += 1

                    return True
                else:
                    self.excluded_count += 1
                    self.errors.append({
                        'workflow': workflow_name,
                        'started_at': started_at,
                        'finished_at': finished_at,
                        'error': 'Non-positive duration'
                    })
            return False
        except Exception as e:
            self.excluded_count += 1
            self.errors.append({
                'workflow': workflow_name,
                'started_at': started_at,
                'finished_at': finished_at,
                'error': str(e)
            })
            return False

    def calculate_percentiles(self) -> Dict[str, float]:
        """Calculate percentile statistics using quantiles."""
        if not self.durations:
            return {
                "count": 0,
                "p50_seconds": 0,
                "p75_seconds": 0,
                "p90_seconds": 0,
                "p95_seconds": 0,
                "p99_seconds": 0,
                "min_seconds": 0,
                "max_seconds": 0
            }

        sorted_data = sorted(self.durations)
        n = len(sorted_data)

        # Using statistics.quantiles (Python 3.8+)
        try:
            quantiles = statistics.quantiles(self.durations, n=100, method='inclusive')
            return {
                "count": n,
                "p50_seconds": round(quantiles[49], 3),   # 50th percentile
                "p75_seconds": round(quantiles[74], 3),   # 75th percentile
                "p90_seconds": round(quantiles[89], 3),   # 90th percentile
                "p95_seconds": round(quantiles[94], 3),   # 95th percentile
                "p99_seconds": round(quantiles[98], 3),   # 99th percentile
                "min_seconds": round(min(self.durations), 3),
                "max_seconds": round(max(self.durations), 3)
            }
        except Exception as e:
            print(f"  Error using statistics.quantiles: {e}, using manual calculation")
            return self._manual_percentiles()

    def _manual_percentiles(self) -> Dict[str, float]:
        """Manual percentile calculation as fallback."""
        sorted_data = sorted(self.durations)
        n = len(sorted_data)

        def percentile(p: float) -> float:
            index = int(n * p / 100)
            return sorted_data[min(index, n - 1)]

        return {
            "count": n,
            "p50_seconds": round(percentile(50), 3),
            "p75_seconds": round(percentile(75), 3),
            "p90_seconds": round(percentile(90), 3),
            "p95_seconds": round(percentile(95), 3),
            "p99_seconds": round(percentile(99), 3),
            "min_seconds": round(min(self.durations), 3),
            "max_seconds": round(max(self.durations), 3)
        }

    def calculate_additional_stats(self) -> Dict[str, float]:
        """Calculate additional statistics."""
        if not self.durations:
            return {
                "mean_seconds": 0,
                "median_seconds": 0,
                "sum_seconds": 0,
                "stddev_seconds": 0
            }

        return {
            "mean_seconds": round(statistics.mean(self.durations), 3),
            "median_seconds": round(statistics.median(self.durations), 3),
            "sum_seconds": round(sum(self.durations), 3),
            "stddev_seconds": round(statistics.stdev(self.durations) if len(self.durations) > 1 else 0, 3)
        }

    def check_temporal_gaps(self) -> Dict[str, Any]:
        """Check for temporal gaps in coverage."""
        expected_days = (self.end_date - self.start_date).days + 1
        actual_days = len(self.daily_counts)
        missing_days = expected_days - actual_days

        # Find specific missing days
        all_days = []
        current = self.start_date
        while current <= self.end_date:
            all_days.append(current.date().isoformat())
            current += timedelta(days=1)

        missing_day_list = [day for day in all_days if day not in self.daily_counts]

        # Check for sparse hours (days with < 24 hours of data)
        sparse_days = [
            day for day, count in self.daily_counts.items()
            if count < 24  # Less than 24 hours of data
        ]

        return {
            "expected_days": expected_days,
            "actual_days": actual_days,
            "missing_days": missing_days,
            "missing_day_list": missing_day_list,
            "sparse_days": sparse_days,
            "coverage_percentage": round((actual_days / expected_days) * 100, 2) if expected_days > 0 else 0,
            "daily_average": round(sum(self.daily_counts.values()) / actual_days, 2) if actual_days > 0 else 0
        }

    def get_raw_latency_data(self) -> List[Dict[str, Any]]:
        """Export raw latency data for intermediate storage."""
        return [
            {
                "timestamp": ts.isoformat(),
                "duration_seconds": round(duration, 3)
            }
            for ts, duration in zip(self.timestamps, self.durations)
        ]


def query_workflows_from_file(file_path: Path, workflow_template: str,
                              start_date: str, end_date: str,
                              service_name: str) -> LatencyAnalyzer:
    """Query workflows from a JSON file for specific workflow template."""
    print(f"\n  Querying {service_name} workflows from: {file_path.name}")
    print(f"  Workflow template: {workflow_template}")

    analyzer = LatencyAnalyzer(start_date, end_date, service_name)

    try:
        with open(file_path, 'r') as f:
            data = json.load(f)

        workflows = []

        # Handle both wrapped and direct workflow structures
        if 'workflows' in data:
            workflows = data['workflows']
        elif 'items' in data:
            workflows = data['items']
        else:
            # Assume it's a direct workflow list
            workflows = data if isinstance(data, list) else []

        print(f"  Total workflows in file: {len(workflows)}")

        for workflow in workflows:
            # Extract workflow template reference
            workflow_ref = None
            if 'spec' in workflow and 'workflowTemplateRef' in workflow['spec']:
                workflow_ref = workflow['spec']['workflowTemplateRef'].get('name')
            elif 'spec' in workflow and 'workflow' in workflow['spec'] and 'workflowTemplateRef' in workflow['spec']['workflow']:
                workflow_ref = workflow['spec']['workflow']['workflowTemplateRef'].get('name')

            # Filter by workflow template if specified
            if workflow_template and workflow_ref != workflow_template:
                continue

            # Extract timestamps
            status = workflow.get('status', {})
            started = status.get('startedAt')
            finished = status.get('finishedAt')
            workflow_name = workflow.get('metadata', {}).get('name', 'unknown')

            if started and finished:
                analyzer.add_duration(started, finished, workflow_name)

        print(f"  Workflows matching template: {len(analyzer.durations)}")
        print(f"  Workflows excluded (invalid): {analyzer.excluded_count}")

    except Exception as e:
        print(f"  ERROR processing file: {e}")
        analyzer.errors.append({
            'file': str(file_path),
            'error': str(e)
        })

    return analyzer


def main():
    """Query latency metrics for pbx-web and whisper-stt over 30-day window."""
    print("="*70)
    print("Querying Latency Metrics for pbx-web and whisper-stt")
    print("="*70)

    # Time range: 30 days from 2026-07-08 to 2026-08-07
    start_date = "2026-07-08T00:00:00Z"
    end_date = "2026-08-07T23:59:59Z"

    print(f"Time Range: {start_date} to {end_date} (30 days)")
    print(f"Services: pbx-web, whisper-stt")

    # Paths to data files
    research_dir = Path("/home/coding/aide-de-camp/research")

    pbx_web_data_file = research_dir / "pbx-web-workflows-raw.json"
    whisper_stt_data_file = research_dir / "whisper-stt-30days/argo-runs/all-recent-workflows.json"

    # Create output directory
    output_dir = Path("/home/coding/aide-de-camp/data/latency-metrics")
    output_dir.mkdir(parents=True, exist_ok=True)

    results = {
        "query_metadata": {
            "timestamp": datetime.now().isoformat(),
            "time_period_days": 30,
            "start_date": start_date,
            "end_date": end_date,
            "services": ["pbx-web", "whisper-stt"],
            "metrics": ["p50", "p75", "p90", "p95", "p99", "mean", "median", "stddev"]
        },
        "services": {}
    }

    gaps_log = []

    # Query pbx-web latency metrics
    print("\n" + "="*70)
    print("QUERYING pbx-web LATENCY METRICS")
    print("="*70)

    if pbx_web_data_file.exists():
        pbx_analyzer = query_workflows_from_file(
            pbx_web_data_file,
            "pbx-web-build",  # Workflow template to filter for
            start_date,
            end_date,
            "pbx-web"
        )

        pbx_percentiles = pbx_analyzer.calculate_percentiles()
        pbx_additional = pbx_analyzer.calculate_additional_stats()
        pbx_gaps = pbx_analyzer.check_temporal_gaps()
        pbx_raw_data = pbx_analyzer.get_raw_latency_data()

        results["services"]["pbx-web"] = {
            "percentile_metrics": pbx_percentiles,
            "additional_metrics": pbx_additional,
            "temporal_coverage": pbx_gaps,
            "data_quality": {
                "valid_records": len(pbx_analyzer.durations),
                "invalid_records": pbx_analyzer.excluded_count,
                "errors_count": len(pbx_analyzer.errors)
            }
        }

        # Store raw pbx-web latency data
        pbx_raw_file = output_dir / "pbx-web-latency-raw.json"
        with open(pbx_raw_file, 'w') as f:
            json.dump({
                "service": "pbx-web",
                "time_range": {"start": start_date, "end": end_date},
                "raw_data": pbx_raw_data
            }, f, indent=2)

        print(f"\n  pbx-web Latency Metrics:")
        print(f"    Count: {pbx_percentiles['count']}")
        print(f"    p50: {pbx_percentiles['p50_seconds']}s")
        print(f"    p95: {pbx_percentiles['p95_seconds']}s")
        print(f"    p99: {pbx_percentiles['p99_seconds']}s")
        print(f"    Mean: {pbx_additional['mean_seconds']}s")
        print(f"    Temporal Coverage: {pbx_gaps['coverage_percentage']}% ({pbx_gaps['actual_days']}/{pbx_gaps['expected_days']} days)")

        if pbx_gaps['missing_day_list']:
            gaps_log.append({
                "service": "pbx-web",
                "type": "missing_days",
                "days": pbx_gaps['missing_day_list']
            })
            print(f"    WARNING: {len(pbx_gaps['missing_day_list'])} missing days")

        print(f"\n  ✓ Raw pbx-web latency data saved to: {pbx_raw_file}")

    else:
        print(f"  ERROR: pbx-web data file not found: {pbx_web_data_file}")
        results["services"]["pbx-web"] = {"error": "Data file not found"}
        gaps_log.append({
            "service": "pbx-web",
            "type": "error",
            "message": f"Data file not found: {pbx_web_data_file}"
        })

    # Query whisper-stt latency metrics
    print("\n" + "="*70)
    print("QUERYING whisper-stt LATENCY METRICS")
    print("="*70)

    if whisper_stt_data_file.exists():
        whisper_analyzer = query_workflows_from_file(
            whisper_stt_data_file,
            "whisper-stt-build",  # Workflow template to filter for
            start_date,
            end_date,
            "whisper-stt"
        )

        whisper_percentiles = whisper_analyzer.calculate_percentiles()
        whisper_additional = whisper_analyzer.calculate_additional_stats()
        whisper_gaps = whisper_analyzer.check_temporal_gaps()
        whisper_raw_data = whisper_analyzer.get_raw_latency_data()

        results["services"]["whisper-stt"] = {
            "percentile_metrics": whisper_percentiles,
            "additional_metrics": whisper_additional,
            "temporal_coverage": whisper_gaps,
            "data_quality": {
                "valid_records": len(whisper_analyzer.durations),
                "invalid_records": whisper_analyzer.excluded_count,
                "errors_count": len(whisper_analyzer.errors)
            }
        }

        # Store raw whisper-stt latency data
        whisper_raw_file = output_dir / "whisper-stt-latency-raw.json"
        with open(whisper_raw_file, 'w') as f:
            json.dump({
                "service": "whisper-stt",
                "time_range": {"start": start_date, "end": end_date},
                "raw_data": whisper_raw_data
            }, f, indent=2)

        print(f"\n  whisper-stt Latency Metrics:")
        print(f"    Count: {whisper_percentiles['count']}")
        print(f"    p50: {whisper_percentiles['p50_seconds']}s")
        print(f"    p95: {whisper_percentiles['p95_seconds']}s")
        print(f"    p99: {whisper_percentiles['p99_seconds']}s")
        print(f"    Mean: {whisper_additional['mean_seconds']}s")
        print(f"    Temporal Coverage: {whisper_gaps['coverage_percentage']}% ({whisper_gaps['actual_days']}/{whisper_gaps['expected_days']} days)")

        if whisper_gaps['missing_day_list']:
            gaps_log.append({
                "service": "whisper-stt",
                "type": "missing_days",
                "days": whisper_gaps['missing_day_list']
            })
            print(f"    WARNING: {len(whisper_gaps['missing_day_list'])} missing days")

        print(f"\n  ✓ Raw whisper-stt latency data saved to: {whisper_raw_file}")

    else:
        print(f"  ERROR: whisper-stt data file not found: {whisper_stt_data_file}")
        results["services"]["whisper-stt"] = {"error": "Data file not found"}
        gaps_log.append({
            "service": "whisper-stt",
            "type": "error",
            "message": f"Data file not found: {whisper_stt_data_file}"
        })

    # Save comprehensive results
    results_file = output_dir / f"latency-metrics-comprehensive-{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(results_file, 'w') as f:
        json.dump(results, f, indent=2)

    # Save gaps and anomalies log
    gaps_file = output_dir / f"latency-gaps-anomalies-{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(gaps_file, 'w') as f:
        json.dump({
            "timestamp": datetime.now().isoformat(),
            "gaps_and_anomalies": gaps_log
        }, f, indent=2)

    print(f"\n{'='*70}")
    print(f"QUERY COMPLETE")
    print(f"{'='*70}")
    print(f"\nOutput Files:")
    print(f"  • Comprehensive results: {results_file}")
    print(f"  • Gaps and anomalies: {gaps_file}")
    print(f"  • Raw pbx-web data: {pbx_raw_file if pbx_web_data_file.exists() else 'N/A'}")
    print(f"  • Raw whisper-stt data: {whisper_raw_file if whisper_stt_data_file.exists() else 'N/A'}")

    print(f"\nSummary:")
    pbx_results = results["services"].get("pbx-web", {})
    whisper_results = results["services"].get("whisper-stt", {})

    if "percentile_metrics" in pbx_results:
        print(f"  pbx-web:")
        print(f"    Valid records: {pbx_results['data_quality']['valid_records']}")
        print(f"    p50: {pbx_results['percentile_metrics']['p50_seconds']}s, "
              f"p95: {pbx_results['percentile_metrics']['p95_seconds']}s, "
              f"p99: {pbx_results['percentile_metrics']['p99_seconds']}s")
        print(f"    Temporal coverage: {pbx_results['temporal_coverage']['coverage_percentage']}%")

    if "percentile_metrics" in whisper_results:
        print(f"  whisper-stt:")
        print(f"    Valid records: {whisper_results['data_quality']['valid_records']}")
        print(f"    p50: {whisper_results['percentile_metrics']['p50_seconds']}s, "
              f"p95: {whisper_results['percentile_metrics']['p95_seconds']}s, "
              f"p99: {whisper_results['percentile_metrics']['p99_seconds']}s")
        print(f"    Temporal coverage: {whisper_results['temporal_coverage']['coverage_percentage']}%")

    if gaps_log:
        print(f"\n⚠️  Gaps/Anomalies Detected: {len(gaps_log)}")
        for gap in gaps_log:
            if gap['type'] == 'missing_days':
                print(f"  • {gap['service']}: {len(gap['days'])} missing days")
            elif gap['type'] == 'error':
                print(f"  • {gap['service']}: {gap['message']}")
    else:
        print(f"\n✓ No temporal gaps detected")

    return results


if __name__ == "__main__":
    main()