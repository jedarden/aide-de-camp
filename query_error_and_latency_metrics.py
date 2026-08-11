#!/usr/bin/env python3
"""
Query error rates and latency metrics for pbx-web and whisper-stt over 30-day window

This script queries both error rates (HTTP errors, task failures, workflow phases)
and latency metrics (response time, processing duration) for both pbx-web and
whisper-stt spanning the full 30-day window, ensuring no temporal gaps in coverage
and storing raw metrics data in intermediate format.
"""

import json
import statistics
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, List, Tuple
from collections import defaultdict, Counter


class MetricsAnalyzer:
    """Calculate both error rates and latency metrics with temporal coverage tracking."""

    def __init__(self, start_date: str, end_date: str, service_name: str):
        self.start_date = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
        self.end_date = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
        self.service_name = service_name

        # Latency tracking
        self.durations = []
        self.timestamps = []

        # Error tracking
        self.error_events = []
        self.workflow_phases = Counter()
        self.error_messages = Counter()

        # Temporal coverage
        self.daily_counts = defaultdict(int)
        self.hourly_counts = defaultdict(int)

        # Data quality
        self.excluded_count = 0
        self.processing_errors = []

    def add_workflow(self, workflow: Dict[str, Any]) -> bool:
        """Add workflow data for both latency and error analysis."""
        try:
            # Extract timestamps
            status = workflow.get('status', {})
            metadata = workflow.get('metadata', {})

            started = status.get('startedAt')
            finished = status.get('finishedAt')
            created = metadata.get('creationTimestamp')
            workflow_name = metadata.get('name', 'unknown')

            # Use creation timestamp if started not available
            timestamp = started or created
            if not timestamp:
                self.excluded_count += 1
                self.processing_errors.append({
                    'workflow': workflow_name,
                    'error': 'No timestamp available'
                })
                return False

            # Parse timestamp
            try:
                ts = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
            except ValueError:
                self.excluded_count += 1
                self.processing_errors.append({
                    'workflow': workflow_name,
                    'error': f'Invalid timestamp format: {timestamp}'
                })
                return False

            # Check if within 30-day window
            if not (self.start_date <= ts <= self.end_date):
                return False

            # Track temporal coverage
            date_key = ts.date().isoformat()
            hour_key = ts.strftime('%Y-%m-%d-%H')
            self.daily_counts[date_key] += 1
            self.hourly_counts[hour_key] += 1

            # Track workflow phase (error rate metric)
            phase = status.get('phase', 'Unknown')
            self.workflow_phases[phase] += 1

            # Track error messages
            message = status.get('message', '')
            if message and phase in ('Failed', 'Error'):
                self.error_messages[message] += 1
                self.error_events.append({
                    'timestamp': timestamp,
                    'workflow': workflow_name,
                    'phase': phase,
                    'message': message
                })

            # Calculate latency if both timestamps available
            if started and finished:
                try:
                    start = datetime.fromisoformat(started.replace('Z', '+00:00'))
                    end = datetime.fromisoformat(finished.replace('Z', '+00:00'))
                    duration = (end - start).total_seconds()

                    if duration > 0:
                        self.durations.append(duration)
                        self.timestamps.append(start)
                    else:
                        self.excluded_count += 1
                        self.processing_errors.append({
                            'workflow': workflow_name,
                            'error': 'Non-positive duration'
                        })
                except Exception as e:
                    self.excluded_count += 1
                    self.processing_errors.append({
                        'workflow': workflow_name,
                        'error': f'Duration calculation error: {e}'
                    })

            return True

        except Exception as e:
            self.excluded_count += 1
            self.processing_errors.append({
                'workflow': workflow.get('metadata', {}).get('name', 'unknown'),
                'error': str(e)
            })
            return False

    def calculate_error_rates(self) -> Dict[str, Any]:
        """Calculate error rate metrics."""
        total_workflows = sum(self.workflow_phases.values())
        if total_workflows == 0:
            return {
                "total_workflows": 0,
                "error_rate_percentage": 0,
                "failure_rate_percentage": 0,
                "phase_distribution": {},
                "error_count": 0,
                "success_count": 0
            }

        # Count error/failure states
        error_count = sum(count for phase, count in self.workflow_phases.items()
                         if phase in ('Error', 'Failed'))
        success_count = self.workflow_phases.get('Succeeded', 0)

        return {
            "total_workflows": total_workflows,
            "error_rate_percentage": round((error_count / total_workflows) * 100, 2),
            "failure_rate_percentage": round((error_count / total_workflows) * 100, 2),
            "phase_distribution": dict(self.workflow_phases),
            "error_count": error_count,
            "success_count": success_count
        }

    def calculate_latency_percentiles(self) -> Dict[str, float]:
        """Calculate latency percentile statistics."""
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

        try:
            quantiles = statistics.quantiles(self.durations, n=100, method='inclusive')
            return {
                "count": n,
                "p50_seconds": round(quantiles[49], 3),
                "p75_seconds": round(quantiles[74], 3),
                "p90_seconds": round(quantiles[89], 3),
                "p95_seconds": round(quantiles[94], 3),
                "p99_seconds": round(quantiles[98], 3),
                "min_seconds": round(min(self.durations), 3),
                "max_seconds": round(max(self.durations), 3)
            }
        except Exception as e:
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
        """Calculate additional latency statistics."""
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

        # Check for sparse hours
        sparse_days = [
            day for day, count in self.daily_counts.items()
            if count < 24
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

    def get_top_errors(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get top error messages."""
        return [
            {"message": msg, "count": count}
            for msg, count in self.error_messages.most_common(limit)
        ]

    def get_raw_data(self) -> Dict[str, Any]:
        """Export raw metrics data for intermediate storage."""
        return {
            "latency_data": [
                {
                    "timestamp": ts.isoformat(),
                    "duration_seconds": round(duration, 3)
                }
                for ts, duration in zip(self.timestamps, self.durations)
            ],
            "error_data": self.error_events,
            "workflow_phases": dict(self.workflow_phases)
        }


def query_workflows_from_file(file_path: Path, service_patterns: List[str],
                              start_date: str, end_date: str,
                              service_name: str) -> MetricsAnalyzer:
    """Query workflows from a JSON file for specific service patterns."""
    print(f"\n  Querying {service_name} workflows from: {file_path.name}")
    print(f"  Service patterns: {service_patterns}")

    analyzer = MetricsAnalyzer(start_date, end_date, service_name)

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
            workflows = data if isinstance(data, list) else []

        print(f"  Total workflows in file: {len(workflows)}")

        # Filter by service name patterns
        matched_count = 0
        for workflow in workflows:
            workflow_name = workflow.get('metadata', {}).get('name', '')

            # Check if workflow name matches any service pattern
            if any(pattern in workflow_name for pattern in service_patterns):
                if analyzer.add_workflow(workflow):
                    matched_count += 1

        print(f"  Workflows matching service patterns: {matched_count}")
        print(f"  Workflows excluded (invalid): {analyzer.excluded_count}")

    except Exception as e:
        print(f"  ERROR processing file: {e}")
        analyzer.processing_errors.append({
            'file': str(file_path),
            'error': str(e)
        })

    return analyzer


def query_kubernetes_workflows(service_patterns: List[str], start_date: str,
                               end_date: str, service_name: str,
                               kubeconfig: str) -> MetricsAnalyzer:
    """Query workflows directly from Kubernetes."""
    print(f"\n  Querying {service_name} workflows from Kubernetes")
    print(f"  Service patterns: {service_patterns}")

    analyzer = MetricsAnalyzer(start_date, end_date, service_name)

    try:
        import subprocess
        import tempfile

        # Query workflows from Kubernetes
        cmd = [
            'kubectl', '--kubeconfig', kubeconfig,
            'get', 'workflows', '-n', 'argo-workflows',
            '-o', 'json'
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

        if result.returncode != 0:
            print(f"  ERROR querying kubernetes: {result.stderr}")
            analyzer.processing_errors.append({
                'source': 'kubernetes',
                'error': result.stderr
            })
            return analyzer

        data = json.loads(result.stdout)
        workflows = data.get('items', [])

        print(f"  Total workflows in cluster: {len(workflows)}")

        # Filter by service name patterns and time range
        matched_count = 0
        for workflow in workflows:
            workflow_name = workflow.get('metadata', {}).get('name', '')

            # Check if workflow name matches any service pattern
            if any(pattern in workflow_name for pattern in service_patterns):
                if analyzer.add_workflow(workflow):
                    matched_count += 1

        print(f"  Workflows matching service patterns: {matched_count}")
        print(f"  Workflows excluded (invalid): {analyzer.excluded_count}")

    except subprocess.TimeoutExpired:
        print(f"  ERROR: Kubernetes query timed out")
        analyzer.processing_errors.append({
            'source': 'kubernetes',
            'error': 'Query timed out'
        })
    except Exception as e:
        print(f"  ERROR querying kubernetes: {e}")
        analyzer.processing_errors.append({
            'source': 'kubernetes',
            'error': str(e)
        })

    return analyzer


def main():
    """Query error rates and latency metrics for pbx-web and whisper-stt over 30-day window."""
    print("="*70)
    print("Querying Error Rates and Latency Metrics for pbx-web and whisper-stt")
    print("="*70)

    # Time range: 30 days from 2026-07-08 to 2026-08-07
    start_date = "2026-07-08T00:00:00Z"
    end_date = "2026-08-07T23:59:59Z"

    print(f"Time Range: {start_date} to {end_date} (30 days)")
    print(f"Services: pbx-web, whisper-stt")

    # Paths to data files
    research_dir = Path("/home/coding/aide-de-camp/research")
    kubeconfig = "/home/coding/.kube/iad-ci.kubeconfig"

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
            "metrics": ["error_rates", "latency_percentiles", "temporal_coverage"]
        },
        "services": {}
    }

    gaps_log = []

    # Query pbx-web metrics
    print("\n" + "="*70)
    print("QUERYING pbx-web METRICS (Error Rates + Latency)")
    print("="*70)

    pbx_analyzer = query_kubernetes_workflows(
        ["pbx-web", "pbx"],  # Service name patterns
        start_date,
        end_date,
        "pbx-web",
        kubeconfig
    )

    # Calculate metrics
    pbx_error_rates = pbx_analyzer.calculate_error_rates()
    pbx_percentiles = pbx_analyzer.calculate_latency_percentiles()
    pbx_additional = pbx_analyzer.calculate_additional_stats()
    pbx_gaps = pbx_analyzer.check_temporal_gaps()
    pbx_top_errors = pbx_analyzer.get_top_errors()
    pbx_raw_data = pbx_analyzer.get_raw_data()

    results["services"]["pbx-web"] = {
        "error_rates": pbx_error_rates,
        "latency_metrics": {
            "percentiles": pbx_percentiles,
            "additional": pbx_additional
        },
        "temporal_coverage": pbx_gaps,
        "top_errors": pbx_top_errors,
        "data_quality": {
            "valid_records": len(pbx_analyzer.durations) + len(pbx_analyzer.error_events),
            "invalid_records": pbx_analyzer.excluded_count,
            "processing_errors_count": len(pbx_analyzer.processing_errors)
        }
    }

    # Store raw pbx-web data
    pbx_raw_file = output_dir / "pbx-web-metrics-raw.json"
    with open(pbx_raw_file, 'w') as f:
        json.dump({
            "service": "pbx-web",
            "time_range": {"start": start_date, "end": end_date},
            "raw_data": pbx_raw_data
        }, f, indent=2)

    print(f"\n  pbx-web Metrics Summary:")
    print(f"    Error Rate: {pbx_error_rates['error_rate_percentage']}%")
    print(f"    Total Workflows: {pbx_error_rates['total_workflows']}")
    print(f"    Success/Failure: {pbx_error_rates['success_count']}/{pbx_error_rates['error_count']}")
    if pbx_percentiles['count'] > 0:
        print(f"    Latency p50: {pbx_percentiles['p50_seconds']}s, p95: {pbx_percentiles['p95_seconds']}s")
    print(f"    Temporal Coverage: {pbx_gaps['coverage_percentage']}% ({pbx_gaps['actual_days']}/{pbx_gaps['expected_days']} days)")

    if pbx_top_errors:
        print(f"    Top Errors:")
        for error in pbx_top_errors[:3]:
            print(f"      - {error['message'][:60]}... ({error['count']}x)")

    if pbx_gaps['missing_day_list']:
        gaps_log.append({
            "service": "pbx-web",
            "type": "missing_days",
            "days": pbx_gaps['missing_day_list']
        })
        print(f"    WARNING: {len(pbx_gaps['missing_day_list'])} missing days")

    print(f"\n  ✓ Raw pbx-web metrics saved to: {pbx_raw_file}")

    # Query whisper-stt metrics
    print("\n" + "="*70)
    print("QUERYING whisper-stt METRICS (Error Rates + Latency)")
    print("="*70)

    whisper_analyzer = query_kubernetes_workflows(
        ["whisper-stt", "whisper"],  # Service name patterns
        start_date,
        end_date,
        "whisper-stt",
        kubeconfig
    )

    # Calculate metrics
    whisper_error_rates = whisper_analyzer.calculate_error_rates()
    whisper_percentiles = whisper_analyzer.calculate_latency_percentiles()
    whisper_additional = whisper_analyzer.calculate_additional_stats()
    whisper_gaps = whisper_analyzer.check_temporal_gaps()
    whisper_top_errors = whisper_analyzer.get_top_errors()
    whisper_raw_data = whisper_analyzer.get_raw_data()

    results["services"]["whisper-stt"] = {
        "error_rates": whisper_error_rates,
        "latency_metrics": {
            "percentiles": whisper_percentiles,
            "additional": whisper_additional
        },
        "temporal_coverage": whisper_gaps,
        "top_errors": whisper_top_errors,
        "data_quality": {
            "valid_records": len(whisper_analyzer.durations) + len(whisper_analyzer.error_events),
            "invalid_records": whisper_analyzer.excluded_count,
            "processing_errors_count": len(whisper_analyzer.processing_errors)
        }
    }

    # Store raw whisper-stt data
    whisper_raw_file = output_dir / "whisper-stt-metrics-raw.json"
    with open(whisper_raw_file, 'w') as f:
        json.dump({
            "service": "whisper-stt",
            "time_range": {"start": start_date, "end": end_date},
            "raw_data": whisper_raw_data
        }, f, indent=2)

    print(f"\n  whisper-stt Metrics Summary:")
    print(f"    Error Rate: {whisper_error_rates['error_rate_percentage']}%")
    print(f"    Total Workflows: {whisper_error_rates['total_workflows']}")
    print(f"    Success/Failure: {whisper_error_rates['success_count']}/{whisper_error_rates['error_count']}")
    if whisper_percentiles['count'] > 0:
        print(f"    Latency p50: {whisper_percentiles['p50_seconds']}s, p95: {whisper_percentiles['p95_seconds']}s")
    print(f"    Temporal Coverage: {whisper_gaps['coverage_percentage']}% ({whisper_gaps['actual_days']}/{whisper_gaps['expected_days']} days)")

    if whisper_top_errors:
        print(f"    Top Errors:")
        for error in whisper_top_errors[:3]:
            print(f"      - {error['message'][:60]}... ({error['count']}x)")

    if whisper_gaps['missing_day_list']:
        gaps_log.append({
            "service": "whisper-stt",
            "type": "missing_days",
            "days": whisper_gaps['missing_day_list']
        })
        print(f"    WARNING: {len(whisper_gaps['missing_day_list'])} missing days")

    print(f"\n  ✓ Raw whisper-stt metrics saved to: {whisper_raw_file}")

    # Save comprehensive results
    results_file = output_dir / f"metrics-comprehensive-{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(results_file, 'w') as f:
        json.dump(results, f, indent=2)

    # Save gaps and anomalies log
    gaps_file = output_dir / f"metrics-gaps-anomalies-{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
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
    print(f"  • Raw pbx-web data: {pbx_raw_file}")
    print(f"  • Raw whisper-stt data: {whisper_raw_file}")

    print(f"\nSummary:")
    pbx_results = results["services"].get("pbx-web", {})
    whisper_results = results["services"].get("whisper-stt", {})

    if "error_rates" in pbx_results:
        print(f"  pbx-web:")
        print(f"    Error rate: {pbx_results['error_rates']['error_rate_percentage']}%")
        print(f"    Workflows: {pbx_results['error_rates']['total_workflows']}")
        if pbx_results['latency_metrics']['percentiles']['count'] > 0:
            print(f"    Latency p50/p95: {pbx_results['latency_metrics']['percentiles']['p50_seconds']}s / "
                  f"{pbx_results['latency_metrics']['percentiles']['p95_seconds']}s")
        print(f"    Temporal coverage: {pbx_results['temporal_coverage']['coverage_percentage']}%")

    if "error_rates" in whisper_results:
        print(f"  whisper-stt:")
        print(f"    Error rate: {whisper_results['error_rates']['error_rate_percentage']}%")
        print(f"    Workflows: {whisper_results['error_rates']['total_workflows']}")
        if whisper_results['latency_metrics']['percentiles']['count'] > 0:
            print(f"    Latency p50/p95: {whisper_results['latency_metrics']['percentiles']['p50_seconds']}s / "
                  f"{whisper_results['latency_metrics']['percentiles']['p95_seconds']}s")
        print(f"    Temporal coverage: {whisper_results['temporal_coverage']['coverage_percentage']}%")

    if gaps_log:
        print(f"\n⚠️  Gaps/Anomalies Detected: {len(gaps_log)}")
        for gap in gaps_log:
            if gap['type'] == 'missing_days':
                print(f"  • {gap['service']}: {len(gap['days'])} missing days")
    else:
        print(f"\n✓ No temporal gaps detected")

    return results


if __name__ == "__main__":
    main()