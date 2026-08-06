#!/usr/bin/env python3
"""
Example: Query Error Rates and Latency Metrics for 30-Day Period

This script demonstrates the query patterns documented in
docs/query-patterns-and-time-ranges.md

Run with: .venv/bin/python3 examples/query_example_30day_metrics.py
"""

import json
import statistics
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Any


class QueryExample:
    """Example queries for 30-day error rates and latency metrics."""

    def __init__(self, service: str):
        self.service = service
        self.time_range = {
            "start": "2026-07-07T00:00:00Z",
            "end": "2026-08-06T23:59:59Z",
            "days": 30
        }

    def rate(self, count: int, total: int) -> float:
        """Calculate rate as ratio."""
        if total == 0:
            return 0.0
        return count / total

    def percentile(self, values: List[float], p: float) -> float:
        """Calculate percentile value."""
        if not values:
            return 0.0
        sorted_values = sorted(values)
        n = len(sorted_values)
        index = int(n * p)
        return sorted_values[min(index, n - 1)]

    def calculate_percentiles(self, data: List[float]) -> Dict[str, float]:
        """Calculate complete percentile statistics."""
        if not data:
            return {"count": 0, "mean": 0, "median": 0, "p50": 0, "p95": 0, "min": 0, "max": 0}

        sorted_data = sorted(data)
        n = len(sorted_data)

        return {
            "count": n,
            "mean": statistics.mean(data),
            "median": statistics.median(data),
            "p50": sorted_data[int(n * 0.5)],
            "p95": sorted_data[int(n * 0.95)] if n >= 20 else sorted_data[-1],
            "min": min(data),
            "max": max(data)
        }

    def query_http_error_rates(self) -> Dict[str, Any]:
        """Example: Query HTTP error rates from nginx logs."""
        # Simulated data - in practice, read from nginx logs
        nginx_data = {
            "http_5xx_errors": 42,
            "http_4xx_errors": 158,
            "http_total_requests": 12500
        }

        return {
            "http_5xx_errors": nginx_data["http_5xx_errors"],
            "http_4xx_errors": nginx_data["http_4xx_errors"],
            "http_total_requests": nginx_data["http_total_requests"],
            "http_5xx_error_rate": self.rate(nginx_data["http_5xx_errors"], nginx_data["http_total_requests"]),
            "http_4xx_error_rate": self.rate(nginx_data["http_4xx_errors"], nginx_data["http_total_requests"])
        }

    def query_application_error_rates(self) -> Dict[str, Any]:
        """Example: Query application error rates from pod logs."""
        service_dir = Path(f"/home/coding/aide-de-camp/research/{self.service}-30days/pod-logs")
        analysis_files = list(service_dir.glob("*-analysis.json"))

        total_errors = 0
        pods_with_errors = 0

        for analysis_file in analysis_files:
            try:
                with open(analysis_file, 'r') as f:
                    data = json.load(f)
                error_count = data.get("patterns", {}).get("error", {}).get("count", 0)
                if error_count > 0:
                    pods_with_errors += 1
                    total_errors += error_count
            except Exception:
                pass

        return {
            "total_pods_analyzed": len(analysis_files),
            "pods_with_errors": pods_with_errors,
            "total_error_count": total_errors,
            "error_rate_per_pod": self.rate(total_errors, len(analysis_files)) if analysis_files else 0,
            "error_rate_per_day": self.rate(total_errors, self.time_range["days"])
        }

    def query_deployment_metrics(self) -> Dict[str, Any]:
        """Example: Query deployment success/failure rates."""
        # Simulated data - in practice, read from deployment files
        deployment_data = {
            "total_deployments": 24,
            "successful_deployments": 22,
            "failed_deployments": 2
        }

        return {
            "total_deployments": deployment_data["total_deployments"],
            "successful_deployments": deployment_data["successful_deployments"],
            "failed_deployments": deployment_data["failed_deployments"],
            "deployment_error_rate": self.rate(deployment_data["failed_deployments"], deployment_data["total_deployments"]),
            "deployment_success_rate": self.rate(deployment_data["successful_deployments"], deployment_data["total_deployments"])
        }

    def query_response_times(self) -> Dict[str, Any]:
        """Example: Query response time percentiles."""
        # Sample response times in milliseconds
        sample_times = [45, 52, 39, 61, 42, 48, 55, 38, 57, 44, 125, 198, 245, 312]

        return {
            "response_time_stats": self.calculate_percentiles(sample_times)
        }

    def query_deployment_durations(self) -> Dict[str, Any]:
        """Example: Query deployment duration percentiles."""
        # Sample deployment durations in seconds
        durations = [45.2, 52.1, 38.9, 61.5, 42.3, 48.7, 55.2]

        return {
            "deployment_times": durations,
            "timing_stats": self.calculate_percentiles(durations)
        }

    def run_complete_query(self) -> Dict[str, Any]:
        """Run complete query for all metrics."""
        print(f"Running query for: {self.service}")
        print(f"Time range: {self.time_range['start']} to {self.time_range['end']}")

        return {
            "service": self.service,
            "time_range": self.time_range,
            "error_metrics": {
                "http_errors": self.query_http_error_rates(),
                "application_errors": self.query_application_error_rates(),
                "deployment_errors": self.query_deployment_metrics()
            },
            "latency_metrics": {
                "response_times": self.query_response_times(),
                "deployment_durations": self.query_deployment_durations()
            },
            "query_timestamp": datetime.now().isoformat()
        }


def main():
    """Run example queries for both services."""
    print("=" * 70)
    print("Example: 30-Day Error Rates and Latency Metrics Query")
    print("=" * 70)

    for service in ["pbx-web", "whisper-stt"]:
        print(f"\n{'=' * 70}")
        print(f"Querying: {service}")
        print('=' * 70)

        query = QueryExample(service)
        results = query.run_complete_query()

        # Print error metrics
        print("\nError Rates:")
        http = results["error_metrics"]["http_errors"]
        print(f"  HTTP 5xx Error Rate: {http['http_5xx_error_rate']:.2%}")
        print(f"  HTTP 4xx Error Rate: {http['http_4xx_error_rate']:.2%}")

        app = results["error_metrics"]["application_errors"]
        print(f"  Application Error Rate/Day: {app['error_rate_per_day']:.2f}")

        deploy = results["error_metrics"]["deployment_errors"]
        print(f"  Deployment Success Rate: {deploy['deployment_success_rate']:.2%}")

        # Print latency metrics
        print("\nLatency Metrics:")
        resp = results["latency_metrics"]["response_times"]["response_time_stats"]
        print(f"  Response Time p50: {resp['p50']:.0f}ms")
        print(f"  Response Time p95: {resp['p95']:.0f}ms")

        dur = results["latency_metrics"]["deployment_durations"]["timing_stats"]
        print(f"  Deployment Duration p50: {dur['p50']:.1f}s")
        print(f"  Deployment Duration p95: {dur['p95']:.1f}s")

        # Save results
        output_file = Path(f"/home/coding/aide-de-camp/data/example_query_{service}_30d.json")
        output_file.parent.mkdir(parents=True, exist_ok=True)
        with open(output_file, 'w') as f:
            json.dump(results, f, indent=2)
        print(f"\nResults saved to: {output_file}")

    print(f"\n{'=' * 70}")
    print("✓ Example queries completed successfully")
    print('=' * 70)


if __name__ == "__main__":
    main()
