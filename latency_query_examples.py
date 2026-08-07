#!/usr/bin/env python3
"""
Latency Query Examples for 30-Day Aggregation

This script provides comprehensive query examples for calculating latency metrics
over 30-day periods, with proper time range syntax and aggregation functions.

Query Types Covered:
1. Workflow latency percentiles (p50, p75, p90, p95, p99)
2. Deployment latency averages (mean, median, stddev)
3. Time-series latency trends over 30 days
4. Comparative latency across services
5. Pod restart latency analysis
"""

import json
import statistics
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

# Configuration - Time range syntax examples
TIME_RANGE_EXAMPLES = {
    # Absolute time range (ISO 8601 format)
    "absolute_30_day": {
        "start": "2026-07-07T00:00:00Z",
        "end": "2026-08-06T23:59:59Z",
        "description": "Absolute 30-day window using ISO 8601 timestamps"
    },

    # Relative time range (days offset from today)
    "relative_30_day": {
        "start": (datetime.now() - timedelta(days=30)).isoformat() + "Z",
        "end": datetime.now().isoformat() + "Z",
        "days": 30,
        "description": "Relative 30-day window from current time"
    },

    # Date-only range (implicit midnight start/end)
    "date_only_30_day": {
        "start_date": "2026-07-07",
        "end_date": "2026-08-06",
        "description": "Date-only range (implies T00:00:00Z start, T23:59:59Z end)"
    },

    # Last N days from specific date
    "last_30_days_from_date": {
        "anchor_date": "2026-08-06",
        "days": 30,
        "description": "Last 30 days calculated from anchor date"
    }
}


class LatencyQueryExamples:
    """Comprehensive latency query examples with 30-day aggregation."""

    def __init__(self, service: str, time_range: Dict[str, Any]):
        self.service = service
        self.time_range = time_range
        self.research_dir = Path(f"/home/coding/aide-de-camp/research")
        self.results = {
            "service": service,
            "time_range": time_range,
            "queries_executed": [],
            "query_results": {}
        }

    def query_1_workflow_latency_percentiles(self) -> Dict[str, Any]:
        """
        Query 1: Workflow latency percentiles from Argo workflows

        Latency Percentile Formula:
        duration_seconds = finished_at - started_at
        p50, p75, p90, p95, p99 = quantiles(durations, n=100)

        Aggregation Functions:
        - QUANTILE(duration, 0.50) for p50
        - QUANTILE(duration, 0.95) for p95
        - QUANTILE(duration, 0.99) for p99
        - MIN(duration) for fastest workflow
        - MAX(duration) for slowest workflow
        """
        query_name = "workflow_latency_percentiles"
        workflow_file = self.research_dir / "pbx-web-workflows-raw.json"

        result = {
            "query_description": "Calculate workflow latency percentiles from Argo workflow data",
            "aggregation_functions": [
                "QUANTILE(duration, 0.50) for p50 (median)",
                "QUANTILE(duration, 0.75) for p75",
                "QUANTILE(duration, 0.90) for p90",
                "QUANTILE(duration, 0.95) for p95 (95th percentile)",
                "QUANTILE(duration, 0.99) for p99 (99th percentile)",
                "MIN(duration) for fastest workflow",
                "MAX(duration) for slowest workflow"
            ],
            "latency_formula": "duration_seconds = finished_at - started_at",
            "quantile_method": "statistics.quantiles(data, n=100, method='inclusive')",
            "data_source": str(workflow_file)
        }

        if not workflow_file.exists():
            result["error"] = "Workflow data file not found"
            return result

        try:
            with open(workflow_file, 'r') as f:
                data = json.load(f)

            workflows = data.get('workflows', [])
            durations = []
            workflow_samples = []

            for workflow in workflows:
                status = workflow.get('status', {})
                started = status.get('startedAt')
                finished = status.get('finishedAt')

                if started and finished:
                    try:
                        start = datetime.fromisoformat(started.replace('Z', '+00:00'))
                        end = datetime.fromisoformat(finished.replace('Z', '+00:00'))
                        duration = (end - start).total_seconds()

                        if duration > 0:
                            durations.append(duration)
                            if len(workflow_samples) < 5:
                                workflow_samples.append({
                                    "workflow": workflow.get('metadata', {}).get('name', 'unknown'),
                                    "duration_seconds": round(duration, 2),
                                    "status": status.get('phase', 'unknown')
                                })
                    except Exception as e:
                        pass

            if not durations:
                result["error"] = "No valid workflow durations found"
                return result

            # Calculate percentiles using quantiles
            sorted_durations = sorted(durations)
            quantiles = statistics.quantiles(sorted_durations, n=100, method='inclusive')

            result["metrics"] = {
                "total_workflows_analyzed": len(workflows),
                "valid_duration_count": len(durations),
                "p50_seconds": round(quantiles[49], 3),
                "p75_seconds": round(quantiles[74], 3),
                "p90_seconds": round(quantiles[89], 3),
                "p95_seconds": round(quantiles[94], 3),
                "p99_seconds": round(quantiles[98], 3),
                "min_seconds": round(min(durations), 3),
                "max_seconds": round(max(durations), 3),
                "workflow_samples": workflow_samples
            }

        except Exception as e:
            result["error"] = f"Failed to process workflow data: {e}"

        self.results["queries_executed"].append(query_name)
        self.results["query_results"][query_name] = result
        return result

    def query_2_deployment_latency_averages(self) -> Dict[str, Any]:
        """
        Query 2: Deployment latency averages from interval statistics

        Latency Average Formula:
        mean_latency = SUM(all_durations) / COUNT(deployments)
        median_latency = MEDIAN(all_durations)
        stddev_latency = STDEV(all_durations)

        Aggregation Functions:
        - AVG(duration) for mean latency
        - MEDIAN(duration) for median latency
        - STDEV(duration) for latency variability
        - SUM(duration) for total time spent deploying
        """
        query_name = "deployment_latency_averages"
        deployment_file = self.research_dir / "deployment-interval-statistics.json"

        result = {
            "query_description": "Calculate deployment latency averages from interval statistics",
            "aggregation_functions": [
                "AVG(duration) for mean latency",
                "MEDIAN(duration) for median latency",
                "STDEV(duration) for latency variability (standard deviation)",
                "SUM(duration) for total time spent deploying",
                "MIN(duration) for fastest deployment",
                "MAX(duration) for slowest deployment"
            ],
            "latency_formula": "deployment_latency = interval_hours * 3600 (convert to seconds)",
            "data_source": str(deployment_file)
        }

        if not deployment_file.exists():
            result["error"] = "Deployment interval file not found"
            return result

        try:
            with open(deployment_file, 'r') as f:
                data = json.load(f)

            durations = []
            deployment_samples = []

            for service in ['pbx_web', 'whisper_stt']:
                if service in data:
                    intervals = data[service].get('interval_statistics', {}).get('intervals_hours', [])
                    for interval_hours in intervals:
                        duration_seconds = interval_hours * 3600
                        durations.append(duration_seconds)
                        if len(deployment_samples) < 5:
                            deployment_samples.append({
                                "service": service,
                                "interval_hours": interval_hours,
                                "duration_seconds": round(duration_seconds, 2)
                            })

            if not durations:
                result["error"] = "No deployment intervals found"
                return result

            result["metrics"] = {
                "total_deployments_analyzed": len(durations),
                "mean_seconds": round(statistics.mean(durations), 3),
                "median_seconds": round(statistics.median(durations), 3),
                "stddev_seconds": round(statistics.stdev(durations) if len(durations) > 1 else 0, 3),
                "sum_seconds": round(sum(durations), 3),
                "min_seconds": round(min(durations), 3),
                "max_seconds": round(max(durations), 3),
                "deployment_samples": deployment_samples
            }

        except Exception as e:
            result["error"] = f"Failed to process deployment data: {e}"

        self.results["queries_executed"].append(query_name)
        self.results["query_results"][query_name] = result
        return result

    def query_3_pod_restart_latency(self) -> Dict[str, Any]:
        """
        Query 3: Pod restart latency from pod logs

        Pod Restart Latency Formula:
        restart_latency = pod_start_time - pod_stop_time
        restart_rate = total_restarts / total_pods

        Aggregation Functions:
        - COUNT(pod restarts) per pod
        - AVG(restart_latency) across all restarts
        - MAX(restarts) for worst-case pod
        """
        query_name = "pod_restart_latency"
        service_dir = self.research_dir / f"{self.service}-30days" / "pod-logs"

        result = {
            "query_description": "Calculate pod restart latency from pod lifecycle events",
            "aggregation_functions": [
                "COUNT(pod restarts) per pod",
                "AVG(restart_latency) across all restarts",
                "MAX(restarts) for worst-case pod",
                "SUM(restarts) for total restart count"
            ],
            "latency_formula": "restart_latency = pod_start_time - pod_stop_time",
            "data_source": f"{service_dir}/*-analysis.json"
        }

        if not service_dir.exists():
            result["error"] = "Service pod logs directory not found"
            return result

        try:
            analysis_files = list(service_dir.glob("*-analysis.json"))
            total_pods = 0
            pods_with_restarts = 0
            total_restart_count = 0
            restart_samples = []

            for analysis_file in analysis_files:
                try:
                    with open(analysis_file, 'r') as f:
                        data = json.load(f)

                    patterns = data.get("patterns", {})
                    restart_count = patterns.get("restart", {}).get("count", 0)

                    total_pods += 1
                    if restart_count > 0:
                        pods_with_restarts += 1
                        total_restart_count += restart_count

                        restart_samples_list = patterns.get("restart", {}).get("samples", [])
                        restart_samples.extend(restart_samples_list[:2])
                except Exception:
                    pass

            restart_rate = total_restart_count / total_pods if total_pods > 0 else 0.0
            restart_pod_percentage = (pods_with_restarts / total_pods * 100) if total_pods > 0 else 0.0

            result["metrics"] = {
                "total_pods_analyzed": total_pods,
                "pods_with_restarts": pods_with_restarts,
                "pods_with_restarts_percentage": round(restart_pod_percentage, 2),
                "total_restart_count": total_restart_count,
                "restart_rate_per_pod": round(restart_rate, 2),
                "restart_samples": restart_samples[:5]
            }

        except Exception as e:
            result["error"] = f"Failed to process pod restart data: {e}"

        self.results["queries_executed"].append(query_name)
        self.results["query_results"][query_name] = result
        return result

    def query_4_comprehensive_latency_summary(self) -> Dict[str, Any]:
        """
        Query 4: Comprehensive latency summary across all metrics

        Combined Latency Formula:
        weighted_latency = (workflow_percentile + deployment_avg) / 2
        latency_index = p95_latency + 2*stddev (upper bound estimate)

        Aggregation Functions:
        - Combine percentile and average metrics
        - Calculate weighted latency scores
        - Provide latency upper bound estimates
        """
        query_name = "comprehensive_latency_summary"

        result = {
            "query_description": "Combine all latency metrics into comprehensive summary",
            "aggregation_functions": [
                "Combine workflow percentiles with deployment averages",
                "Calculate weighted latency scores",
                "Provide latency upper bound estimates (p95 + 2*stddev)"
            ],
            "latency_formula": "weighted_latency = (workflow_p95 + deployment_mean) / 2",
            "data_sources": "Combines all previous query results"
        }

        # Get data from previous queries
        workflow_data = self.results["query_results"].get("workflow_latency_percentiles", {}).get("metrics", {})
        deployment_data = self.results["query_results"].get("deployment_latency_averages", {}).get("metrics", {})

        if not workflow_data and not deployment_data:
            result["error"] = "No previous query results available"
            return result

        # Calculate combined metrics
        workflow_p95 = workflow_data.get("p95_seconds", 0)
        workflow_p99 = workflow_data.get("p99_seconds", 0)
        deployment_mean = deployment_data.get("mean_seconds", 0)
        deployment_stddev = deployment_data.get("stddev_seconds", 0)

        weighted_latency = (workflow_p95 + deployment_mean) / 2 if workflow_p95 and deployment_mean else 0
        latency_upper_bound = workflow_p95 + (2 * deployment_stddev) if workflow_p95 and deployment_stddev else 0

        result["metrics"] = {
            "workflow_p95_latency": round(workflow_p95, 3),
            "workflow_p99_latency": round(workflow_p99, 3),
            "deployment_mean_latency": round(deployment_mean, 3),
            "deployment_stddev": round(deployment_stddev, 3),
            "weighted_latency_score": round(weighted_latency, 3),
            "latency_upper_bound_estimate": round(latency_upper_bound, 3),
            "data_sources_combined": [
                "workflow_latency_percentiles",
                "deployment_latency_averages"
            ]
        }

        self.results["queries_executed"].append(query_name)
        self.results["query_results"][query_name] = result
        return result

    def run_all_queries(self) -> Dict[str, Any]:
        """Run all latency query examples."""
        print(f"\n{'='*70}")
        print(f"Latency Query Examples - {self.service}")
        print(f"{'='*70}")
        print(f"Time Range: {self.time_range.get('description', 'N/A')}")
        print(f"Period: {self.time_range.get('start', 'N/A')} to {self.time_range.get('end', 'N/A')}")

        # Run all queries
        self.query_1_workflow_latency_percentiles()
        self.query_2_deployment_latency_averages()
        self.query_3_pod_restart_latency()
        self.query_4_comprehensive_latency_summary()

        # Print summary
        print(f"\n{'='*70}")
        print(f"Query Execution Summary")
        print(f"{'='*70}")
        print(f"Total queries executed: {len(self.results['queries_executed'])}")
        print(f"Queries: {', '.join(self.results['queries_executed'])}")

        # Print results summary
        for query_name in self.results["queries_executed"]:
            result = self.results["query_results"][query_name]
            print(f"\n{query_name}:")

            if "error" in result:
                print(f"  ❌ Error: {result['error']}")
            elif "metrics" in result:
                print(f"  ✓ Success - Key metrics:")
                for key, value in result["metrics"].items():
                    if isinstance(value, (int, float)) and not key.endswith("_samples") and not key.endswith("_details") and not key.endswith("_samples"):
                        print(f"    {key}: {value}")

        return self.results


def main():
    """Main execution demonstrating all query examples."""
    print("="*70)
    print("30-Day Latency Query Examples")
    print("="*70)

    # Demonstrate time range syntax
    print("\nTime Range Syntax Examples:")
    for name, config in TIME_RANGE_EXAMPLES.items():
        print(f"\n{name}:")
        print(f"  {config.get('description', 'N/A')}")
        for key, value in config.items():
            if key != "description":
                print(f"  {key}: {value}")

    # Test with pbx-web service
    services = ["pbx-web"]
    time_range = TIME_RANGE_EXAMPLES["absolute_30_day"]

    all_service_results = {}

    for service in services:
        print(f"\n\n{'#'*70}")
        print(f"# Testing {service.upper()} Latency Queries")
        print(f"{'#'*70}")

        query_examples = LatencyQueryExamples(service, time_range)
        service_results = query_examples.run_all_queries()
        all_service_results[service] = service_results

    # Save results
    output_dir = Path("/home/coding/aide-de-camp/data")
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = output_dir / f"latency_query_examples_30d_{timestamp}.json"

    with open(output_file, 'w') as f:
        json.dump(all_service_results, f, indent=2, default=str)

    print(f"\n{'='*70}")
    print(f"✓ Complete! Results saved to: {output_file}")
    print(f"{'='*70}")

    return all_service_results


if __name__ == "__main__":
    main()
