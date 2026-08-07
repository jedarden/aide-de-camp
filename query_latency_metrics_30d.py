#!/usr/bin/env python3
"""
Query latency metrics for pbx-web and whisper-stt over 30-day window.

This script queries latency metrics (response time, processing duration) for both
pbx-web and whisper-stt spanning the full 30-day window from 2026-07-07 to 2026-08-06.
It ensures no temporal gaps in coverage and stores raw latency data in intermediate format.
"""

import json
import statistics
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, List, Optional
from collections import defaultdict


class LatencyMetricsCollector:
    """Collect latency metrics for both pbx-web and whisper-stt services."""

    def __init__(self, start_date: str = "2026-07-07T00:00:00Z", end_date: str = "2026-08-06T23:59:59Z"):
        self.start_date = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
        self.end_date = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
        self.research_dir = Path("/home/coding/aide-de-camp/research")
        self.data_dir = Path("/home/coding/aide-de-camp/data")
        self.data_dir.mkdir(parents=True, exist_ok=True)

        self.results = {
            "query_metadata": {
                "start_date": start_date,
                "end_date": end_date,
                "period_days": 30,
                "query_timestamp": datetime.now().isoformat(),
                "services": ["pbx-web", "whisper-stt"]
            },
            "services": {}
        }

    def query_pbx_web_latency(self) -> Dict[str, Any]:
        """Query pbx-web latency metrics from workflow data."""
        print(f"\n{'='*60}")
        print("Querying pbx-web latency metrics...")
        print(f"{'='*60}")

        service_data = {
            "service": "pbx-web",
            "data_sources": [],
            "latency_metrics": {},
            "coverage_analysis": {},
            "raw_data": {}
        }

        # Query 1: Workflow latency percentiles
        workflow_file = self.research_dir / "pbx-web-workflows-raw.json"
        if workflow_file.exists():
            print(f"  Reading workflow data from {workflow_file.name}...")
            service_data["data_sources"].append("workflow_executions")

            with open(workflow_file, 'r') as f:
                data = json.load(f)

            workflows = data.get('workflows', [])
            durations = []
            workflow_samples = []
            coverage_by_day = defaultdict(int)

            for workflow in workflows:
                status = workflow.get('status', {})
                started = status.get('startedAt')
                finished = status.get('finishedAt')

                if started and finished:
                    try:
                        start = datetime.fromisoformat(started.replace('Z', '+00:00'))
                        end = datetime.fromisoformat(finished.replace('Z', '+00:00'))

                        # Check if within 30-day window
                        if self.start_date <= start <= self.end_date:
                            duration = (end - start).total_seconds()
                            if duration > 0:
                                durations.append(duration)
                                day_key = start.date().isoformat()
                                coverage_by_day[day_key] += 1

                                if len(workflow_samples) < 10:
                                    workflow_samples.append({
                                        "workflow": workflow.get('metadata', {}).get('name', 'unknown'),
                                        "started_at": started,
                                        "finished_at": finished,
                                        "duration_seconds": round(duration, 2),
                                        "status": status.get('phase', 'unknown')
                                    })
                    except Exception as e:
                        pass

            # Calculate percentiles
            if durations:
                sorted_durations = sorted(durations)
                quantiles = statistics.quantiles(sorted_durations, n=100, method='inclusive')

                service_data["latency_metrics"]["workflow_percentiles"] = {
                    "count": len(durations),
                    "p50_seconds": round(quantiles[49], 3),
                    "p75_seconds": round(quantiles[74], 3),
                    "p90_seconds": round(quantiles[89], 3),
                    "p95_seconds": round(quantiles[94], 3),
                    "p99_seconds": round(quantiles[98], 3),
                    "min_seconds": round(min(durations), 3),
                    "max_seconds": round(max(durations), 3),
                    "mean_seconds": round(statistics.mean(durations), 3),
                    "median_seconds": round(statistics.median(durations), 3),
                    "stddev_seconds": round(statistics.stdev(durations), 3)
                }

                service_data["raw_data"]["workflow_durations"] = [round(d, 3) for d in durations]
                service_data["raw_data"]["workflow_samples"] = workflow_samples

                print(f"  ✓ Workflow data: {len(durations)} valid durations")
                print(f"    p50: {quantiles[49]:.1f}s, p95: {quantiles[94]:.1f}s, p99: {quantiles[98]:.1f}s")
            else:
                print(f"  ⚠ No valid workflow durations found")
                service_data["latency_metrics"]["workflow_percentiles"] = {"error": "No valid durations"}

            # Coverage analysis
            expected_days = (self.end_date - self.start_date).days + 1
            actual_days = len(coverage_by_day)
            coverage_percentage = (actual_days / expected_days) * 100

            service_data["coverage_analysis"]["workflow_data"] = {
                "expected_days": expected_days,
                "days_with_data": actual_days,
                "coverage_percentage": round(coverage_percentage, 1),
                "gaps": self._identify_gaps(coverage_by_day),
                "daily_distribution": dict(coverage_by_day)
            }

            print(f"  Coverage: {actual_days}/{expected_days} days ({coverage_percentage:.1f}%)")
        else:
            print(f"  ⚠ Workflow file not found: {workflow_file}")
            service_data["latency_metrics"]["workflow_percentiles"] = {"error": "File not found"}

        # Query 2: Deployment intervals
        deployment_interval_file = self.research_dir / "deployment-interval-statistics.json"
        if deployment_interval_file.exists():
            print(f"  Reading deployment interval data...")
            service_data["data_sources"].append("deployment_intervals")

            with open(deployment_interval_file, 'r') as f:
                data = json.load(f)

            if 'pbx_web' in data:
                intervals = data['pbx_web'].get('interval_statistics', {}).get('intervals_hours', [])
                durations_seconds = [interval * 3600 for interval in intervals]

                if durations_seconds:
                    service_data["latency_metrics"]["deployment_intervals"] = {
                        "count": len(durations_seconds),
                        "mean_seconds": round(statistics.mean(durations_seconds), 3),
                        "median_seconds": round(statistics.median(durations_seconds), 3),
                        "stddev_seconds": round(statistics.stdev(durations_seconds), 3),
                        "min_seconds": round(min(durations_seconds), 3),
                        "max_seconds": round(max(durations_seconds), 3)
                    }

                    service_data["raw_data"]["deployment_intervals_seconds"] = [round(d, 3) for d in durations_seconds]
                    print(f"  ✓ Deployment intervals: {len(durations_seconds)} intervals")
                    print(f"    Mean: {statistics.mean(durations_seconds) / 3600:.1f}h")
                else:
                    print(f"  ⚠ No deployment intervals found")
                    service_data["latency_metrics"]["deployment_intervals"] = {"error": "No intervals"}
        else:
            print(f"  ⚠ Deployment interval file not found")
            service_data["latency_metrics"]["deployment_intervals"] = {"error": "File not found"}

        return service_data

    def query_whisper_stt_latency(self) -> Dict[str, Any]:
        """Query whisper-stt latency metrics from deployment and pod data."""
        print(f"\n{'='*60}")
        print("Querying whisper-stt latency metrics...")
        print(f"{'='*60}")

        service_data = {
            "service": "whisper-stt",
            "data_sources": [],
            "latency_metrics": {},
            "coverage_analysis": {},
            "raw_data": {}
        }

        # Query 1: Deployment event intervals
        deployment_file = self.research_dir / "whisper-stt-30days" / "deployments-30days.json"
        if deployment_file.exists():
            print(f"  Reading deployment data from {deployment_file.name}...")
            service_data["data_sources"].append("deployment_events")

            with open(deployment_file, 'r') as f:
                data = json.load(f)

            deployments = data.get('deployments', {}).get('whisper-stt', {}).get('deployment_events', [])
            timestamps = []
            deployment_samples = []

            for deployment in deployments:
                timestamp_str = deployment.get('timestamp')
                if timestamp_str:
                    try:
                        timestamp = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                        if self.start_date <= timestamp <= self.end_date:
                            timestamps.append(timestamp)
                            if len(deployment_samples) < 10:
                                deployment_samples.append({
                                    "revision": deployment.get('revision'),
                                    "replicaset": deployment.get('replicaset'),
                                    "timestamp": timestamp_str,
                                    "status": deployment.get('status')
                                })
                    except Exception as e:
                        pass

            # Calculate deployment intervals
            if len(timestamps) > 1:
                sorted_timestamps = sorted(timestamps)
                intervals = []
                for i in range(1, len(sorted_timestamps)):
                    interval_hours = (sorted_timestamps[i] - sorted_timestamps[i-1]).total_seconds() / 3600
                    intervals.append(interval_hours)

                if intervals:
                    service_data["latency_metrics"]["deployment_frequency"] = {
                        "total_deployments": len(timestamps),
                        "deployment_count_30days": len(timestamps),
                        "intervals_hours": {
                            "count": len(intervals),
                            "mean_hours": round(statistics.mean(intervals), 2),
                            "median_hours": round(statistics.median(intervals), 2),
                            "min_hours": round(min(intervals), 2),
                            "max_hours": round(max(intervals), 2)
                        }
                    }

                    service_data["raw_data"]["deployment_intervals_hours"] = [round(i, 2) for i in intervals]
                    service_data["raw_data"]["deployment_samples"] = deployment_samples

                    print(f"  ✓ Deployment events: {len(timestamps)} deployments")
                    print(f"    Mean interval: {statistics.mean(intervals):.1f}h between deployments")
                else:
                    print(f"  ⚠ Insufficient deployment data for interval calculation")
                    service_data["latency_metrics"]["deployment_frequency"] = {"error": "Insufficient data"}
            else:
                print(f"  ⚠ Found {len(timestamps)} deployment events (need at least 2)")
                service_data["latency_metrics"]["deployment_frequency"] = {"error": "Insufficient events"}

            # Coverage analysis for deployments
            coverage_by_day = defaultdict(int)
            for timestamp in timestamps:
                day_key = timestamp.date().isoformat()
                coverage_by_day[day_key] += 1

            expected_days = (self.end_date - self.start_date).days + 1
            actual_days = len(coverage_by_day)
            coverage_percentage = (actual_days / expected_days) * 100

            service_data["coverage_analysis"]["deployment_data"] = {
                "expected_days": expected_days,
                "days_with_deployments": actual_days,
                "coverage_percentage": round(coverage_percentage, 1),
                "gaps": self._identify_gaps(coverage_by_day),
                "deployment_distribution": dict(coverage_by_day)
            }

            print(f"  Coverage: {actual_days}/{expected_days} days with deployments ({coverage_percentage:.1f}%)")
        else:
            print(f"  ⚠ Deployment file not found: {deployment_file}")
            service_data["latency_metrics"]["deployment_frequency"] = {"error": "File not found"}

        # Query 2: Pod restart analysis (if available)
        pod_logs_dir = self.research_dir / "whisper-stt-30days" / "pod-logs"
        if pod_logs_dir.exists():
            print(f"  Checking pod logs for latency data...")
            analysis_files = list(pod_logs_dir.glob("*-analysis.json"))

            restart_count = 0
            startup_events = []
            error_count = 0

            for analysis_file in analysis_files:
                try:
                    with open(analysis_file, 'r') as f:
                        data = json.load(f)

                    patterns = data.get("patterns", {})
                    restart_count += patterns.get("restart", {}).get("count", 0)
                    startup_events.extend(patterns.get("startup", {}).get("samples", []))
                    error_count += patterns.get("error", {}).get("count", 0)
                except Exception:
                    pass

            service_data["latency_metrics"]["pod_health"] = {
                "pods_analyzed": len(analysis_files),
                "restart_count": restart_count,
                "startup_events": len(startup_events),
                "error_count": error_count
            }

            if restart_count > 0 or error_count > 0:
                print(f"  ⚠ Pod health issues found: {restart_count} restarts, {error_count} errors")
            else:
                print(f"  ✓ Pod health: Good (no significant issues)")
        else:
            print(f"  ⚠ Pod logs directory not found")
            service_data["latency_metrics"]["pod_health"] = {"error": "Directory not found"}

        return service_data

    def _identify_gaps(self, coverage_by_day: Dict[str, int]) -> List[Dict[str, str]]:
        """Identify temporal gaps in coverage."""
        gaps = []
        current_date = self.start_date.date()
        end_date = self.end_date.date()

        while current_date <= end_date:
            day_str = current_date.isoformat()
            if day_str not in coverage_by_day:
                gaps.append({
                    "date": day_str,
                    "type": "missing_data"
                })
            current_date += timedelta(days=1)

        return gaps[:10]  # Return first 10 gaps to avoid overwhelming output

    def run_comprehensive_analysis(self) -> Dict[str, Any]:
        """Run comprehensive latency analysis for both services."""
        print(f"\n{'='*70}")
        print("COMPREHENSIVE 30-DAY LATENCY METRICS QUERY")
        print(f"{'='*70}")
        print(f"Period: {self.start_date.date()} to {self.end_date.date()}")
        print(f"Services: pbx-web, whisper-stt")

        # Query pbx-web
        pbx_web_data = self.query_pbx_web_latency()
        self.results["services"]["pbx-web"] = pbx_web_data

        # Query whisper-stt
        whisper_stt_data = self.query_whisper_stt_latency()
        self.results["services"]["whisper-stt"] = whisper_stt_data

        # Add summary
        self._add_summary()

        return self.results

    def _add_summary(self):
        """Add summary statistics."""
        summary = {
            "data_quality": {},
            "latency_comparison": {},
            "coverage_summary": {}
        }

        # Data quality assessment
        for service_name, service_data in self.results["services"].items():
            has_latency_data = bool(service_data.get("latency_metrics", {}))
            has_coverage_data = bool(service_data.get("coverage_analysis", {}))
            data_sources = service_data.get("data_sources", [])

            summary["data_quality"][service_name] = {
                "has_latency_data": has_latency_data,
                "has_coverage_data": has_coverage_data,
                "data_sources": data_sources,
                "overall_quality": "good" if has_latency_data and has_coverage_data else "partial"
            }

        # Coverage summary
        for service_name, service_data in self.results["services"].items():
            coverage = service_data.get("coverage_analysis", {})
            for data_type, coverage_info in coverage.items():
                key = f"{service_name}_{data_type}"
                summary["coverage_summary"][key] = {
                    "coverage_percentage": coverage_info.get("coverage_percentage", 0),
                    "gap_count": len(coverage_info.get("gaps", [])),
                    "days_with_data": coverage_info.get("days_with_data", 0)
                }

        self.results["summary"] = summary

    def save_results(self, filename: Optional[str] = None) -> Path:
        """Save results to file."""
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"latency_metrics_30d_{timestamp}.json"

        output_file = self.data_dir / filename

        with open(output_file, 'w') as f:
            json.dump(self.results, f, indent=2, default=str)

        print(f"\n{'='*70}")
        print(f"✓ Results saved to: {output_file}")
        print(f"{'='*70}")

        return output_file

    def print_summary(self):
        """Print summary of results."""
        print(f"\n{'='*70}")
        print("LATENCY METRICS SUMMARY")
        print(f"{'='*70}")

        for service_name, service_data in self.results["services"].items():
            print(f"\n{service_name.upper()}:")
            print(f"  Data Sources: {', '.join(service_data.get('data_sources', []))}")

            latency_metrics = service_data.get("latency_metrics", {})
            for metric_type, metrics in latency_metrics.items():
                if "error" not in metrics:
                    print(f"  {metric_type}:")
                    for key, value in metrics.items():
                        if isinstance(value, (int, float)) and not key.endswith("_samples"):
                            print(f"    {key}: {value}")

            coverage = service_data.get("coverage_analysis", {})
            if coverage:
                print(f"  Coverage:")
                for data_type, coverage_info in coverage.items():
                    coverage_pct = coverage_info.get("coverage_percentage", 0)
                    gap_count = len(coverage_info.get("gaps", []))
                    print(f"    {data_type}: {coverage_pct}% coverage, {gap_count} gaps")


def main():
    """Main execution."""
    print("="*70)
    print("30-DAY LATENCY METRICS QUERY FOR PBX-WEB AND WHISPER-STT")
    print("="*70)

    collector = LatencyMetricsCollector()
    results = collector.run_comprehensive_analysis()

    # Save results
    output_file = collector.save_results()

    # Print summary
    collector.print_summary()

    print(f"\n{'='*70}")
    print("QUERY COMPLETE")
    print(f"{'='*70}")
    print(f"Output file: {output_file}")
    print(f"Services queried: {len(results['services'])}")
    print(f"Period: 30 days (2026-07-07 to 2026-08-06)")

    return results


if __name__ == "__main__":
    main()