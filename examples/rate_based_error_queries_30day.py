#!/usr/bin/env python3
"""
Comprehensive 30-Day Error Rate Queries using rate() Function

This script demonstrates rate-based error rate aggregation patterns for 30-day periods.
It includes optimized query patterns, best practices, and examples for both pbx-web and whisper-stt services.

Run with: .venv/bin/python3 examples/rate_based_error_queries_30day.py
"""

import json
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import statistics

# Configuration for 30-day analysis period
ANALYSIS_PERIOD = {
    "start": "2026-07-07T00:00:00Z",
    "end": "2026-08-06T23:59:59Z",
    "days": 30,
    "period_hours": 30 * 24,
    "period_seconds": 30 * 24 * 3600
}

SERVICES = ["pbx-web", "whisper-stt"]
RESEARCH_DIR = Path("/home/coding/aide-de-camp/research")
OUTPUT_DIR = Path("/home/coding/aide-de-camp/data")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


class RateBasedErrorQuery:
    """
    Rate-based error rate query system using the rate() function pattern.

    The rate() function calculates per-second or per-time-unit rates:
    rate(count, time_window_seconds) -> errors_per_second

    Common patterns:
    - rate(errors, 86400) -> daily error rate
    - rate(errors, 3600) -> hourly error rate
    - rate(errors, period_seconds) -> period error rate
    """

    def __init__(self, service: str):
        self.service = service
        self.service_dir = RESEARCH_DIR / f"{service}-30days"
        self.query_results = {
            "service": service,
            "analysis_period": ANALYSIS_PERIOD,
            "queries_executed": [],
            "query_timestamp": datetime.now().isoformat()
        }

    def rate(self, count: int, time_window_seconds: int) -> float:
        """
        Calculate rate as count per time window.

        Args:
            count: Total count over the period
            time_window_seconds: Time window in seconds for rate normalization

        Returns:
            Rate as count per time window (float)
        """
        if time_window_seconds == 0:
            return 0.0
        return count / time_window_seconds

    def rate_per_day(self, count: int, days: int = 30) -> float:
        """Calculate rate as count per day."""
        if days == 0:
            return 0.0
        return count / days

    def rate_per_hour(self, count: int, hours: int = None) -> float:
        """Calculate rate as count per hour."""
        if hours is None:
            hours = ANALYSIS_PERIOD["period_hours"]
        if hours == 0:
            return 0.0
        return count / hours

    def rate_percent(self, count: int, total: int) -> float:
        """Calculate percentage rate (0-1)."""
        if total == 0:
            return 0.0
        return count / total

    def weighted_error_score(self, errors: Dict[str, int], weights: Dict[str, float]) -> float:
        """
        Calculate weighted error score for multi-dimensional error analysis.

        Args:
            errors: Dict of error types with counts
            weights: Dict of error types with weights (critical=3.0, high=2.0, medium=1.0, low=0.5)

        Returns:
            Weighted error score
        """
        score = 0.0
        for error_type, count in errors.items():
            weight = weights.get(error_type, 1.0)
            score += count * weight
        return score

    def query_http_error_rates(self) -> Dict[str, Any]:
        """
        Query HTTP error rates using rate() function patterns.

        Rate patterns:
        - rate(http_5xx_errors, total_requests) -> HTTP 5xx error rate (ratio)
        - rate_per_day(http_5xx_errors) -> Daily HTTP 5xx error rate
        """
        pod_logs_dir = self.service_dir / "pod-logs"

        result = {
            "query_type": "http_error_rates",
            "rate_patterns_used": [
                "rate(http_5xx_errors, total_requests)",
                "rate_per_day(http_5xx_errors)",
                "rate_per_hour(http_4xx_errors)"
            ],
            "http_5xx_errors": 0,
            "http_4xx_errors": 0,
            "http_total_requests": 0,
            "http_5xx_error_rate": 0.0,
            "http_4xx_error_rate": 0.0,
            "http_5xx_per_day": 0.0,
            "http_4xx_per_day": 0.0,
            "http_5xx_per_hour": 0.0,
            "http_4xx_per_hour": 0.0,
            "data_sources": [],
            "log_files_analyzed": 0
        }

        # Look for nginx log files
        nginx_logs = list(pod_logs_dir.glob("*nginx*.log"))

        for nginx_log in nginx_logs:
            try:
                result["data_sources"].append(nginx_log.name)
                result["log_files_analyzed"] += 1

                with open(nginx_log, 'r') as f:
                    lines = f.readlines()

                for line in lines:
                    # Parse nginx log format for HTTP status codes
                    status_match = re.search(r'"\w+ [^\s]+ HTTP/\d\.\d" (\d+)', line)
                    if status_match:
                        status_code = int(status_match.group(1))
                        result["http_total_requests"] += 1

                        if status_code >= 500:
                            result["http_5xx_errors"] += 1
                        elif status_code >= 400:
                            result["http_4xx_errors"] += 1

            except Exception as e:
                result["data_sources"].append(f"Error reading {nginx_log.name}: {e}")

        # Calculate rates using rate() function patterns
        if result["http_total_requests"] > 0:
            result["http_5xx_error_rate"] = self.rate_percent(result["http_5xx_errors"], result["http_total_requests"])
            result["http_4xx_error_rate"] = self.rate_percent(result["http_4xx_errors"], result["http_total_requests"])

        result["http_5xx_per_day"] = self.rate_per_day(result["http_5xx_errors"])
        result["http_4xx_per_day"] = self.rate_per_day(result["http_4xx_errors"])
        result["http_5xx_per_hour"] = self.rate_per_hour(result["http_5xx_errors"])
        result["http_4xx_per_hour"] = self.rate_per_hour(result["http_4xx_errors"])

        self.query_results["queries_executed"].append("http_error_rates")
        return result

    def query_application_error_rates(self) -> Dict[str, Any]:
        """
        Query application error rates using rate() function patterns.

        Rate patterns:
        - rate_per_day(application_errors) -> Daily application error rate
        - rate(application_errors, total_pods) -> Per-pod error rate
        """
        pod_logs_dir = self.service_dir / "pod-logs"

        result = {
            "query_type": "application_error_rates",
            "rate_patterns_used": [
                "rate_per_day(application_errors)",
                "rate(application_errors, total_pods)",
                "rate(application_errors, analysis_period_hours)"
            ],
            "total_pods_analyzed": 0,
            "pods_with_errors": 0,
            "pods_without_errors": 0,
            "total_error_count": 0,
            "error_rate_per_pod": 0.0,
            "error_rate_per_day": 0.0,
            "error_rate_per_hour": 0.0,
            "pods_with_error_details": []
        }

        analysis_files = list(pod_logs_dir.glob("*-analysis.json"))

        for analysis_file in analysis_files:
            try:
                with open(analysis_file, 'r') as f:
                    data = json.load(f)

                pod_name = analysis_file.stem.replace("-analysis", "")
                error_count = data.get("patterns", {}).get("error", {}).get("count", 0)

                result["total_pods_analyzed"] += 1

                if error_count > 0:
                    result["pods_with_errors"] += 1
                    result["total_error_count"] += error_count
                    result["pods_with_error_details"].append({
                        "pod": pod_name,
                        "errors": error_count
                    })
                else:
                    result["pods_without_errors"] += 1

            except Exception as e:
                result["pods_with_error_details"].append(f"Error reading {analysis_file.name}: {e}")

        # Calculate rates using rate() function patterns
        if result["total_pods_analyzed"] > 0:
            result["error_rate_per_pod"] = self.rate(result["total_error_count"], result["total_pods_analyzed"])

        result["error_rate_per_day"] = self.rate_per_day(result["total_error_count"])
        result["error_rate_per_hour"] = self.rate_per_hour(result["total_error_count"])

        self.query_results["queries_executed"].append("application_error_rates")
        return result

    def query_oom_kill_rates(self) -> Dict[str, Any]:
        """
        Query OOM kill rates using rate() function patterns.

        Rate patterns:
        - rate_per_day(oom_kills) -> Daily OOM kill rate
        - rate(oom_kills, affected_pods) -> Per-affected-pod OOM rate
        """
        pod_logs_dir = self.service_dir / "pod-logs"

        result = {
            "query_type": "oom_kill_rates",
            "rate_patterns_used": [
                "rate_per_day(total_oom_kill_count)",
                "rate(oom_kills, pods_with_oom_kills)",
                "rate(oom_kills, total_pods)"
            ],
            "total_pods_analyzed": 0,
            "pods_with_oom_kills": 0,
            "total_oom_kill_count": 0,
            "oom_kill_rate_per_pod": 0.0,
            "oom_kill_rate_per_day": 0.0,
            "oom_kill_rate_per_hour": 0.0,
            "pods_affected_details": []
        }

        analysis_files = list(pod_logs_dir.glob("*-analysis.json"))

        for analysis_file in analysis_files:
            try:
                with open(analysis_file, 'r') as f:
                    data = json.load(f)

                pod_name = analysis_file.stem.replace("-analysis", "")
                oom_kill_count = data.get("patterns", {}).get("oom_kill", {}).get("count", 0)

                result["total_pods_analyzed"] += 1

                if oom_kill_count > 0:
                    result["pods_with_oom_kills"] += 1
                    result["total_oom_kill_count"] += oom_kill_count
                    result["pods_affected_details"].append({
                        "pod": pod_name,
                        "oom_kills": oom_kill_count
                    })

            except Exception:
                pass

        # Calculate rates using rate() function patterns
        if result["total_pods_analyzed"] > 0:
            result["oom_kill_rate_per_pod"] = self.rate(result["total_oom_kill_count"], result["total_pods_analyzed"])

        result["oom_kill_rate_per_day"] = self.rate_per_day(result["total_oom_kill_count"])
        result["oom_kill_rate_per_hour"] = self.rate_per_hour(result["total_oom_kill_count"])

        self.query_results["queries_executed"].append("oom_kill_rates")
        return result

    def query_deployment_error_rates(self) -> Dict[str, Any]:
        """
        Query deployment error rates using rate() function patterns.

        Rate patterns:
        - rate(failed_deployments, total_deployments) -> Deployment failure rate
        - rate_per_day(deployments) -> Daily deployment rate
        """
        result = {
            "query_type": "deployment_error_rates",
            "rate_patterns_used": [
                "rate(failed_deployments, total_deployments)",
                "rate_per_day(total_deployments)",
                "rate(successful_deployments, total_deployments)"
            ],
            "total_deployments": 0,
            "successful_deployments": 0,
            "failed_deployments": 0,
            "deployment_error_rate": 0.0,
            "deployment_success_rate": 0.0,
            "deployment_rate_per_day": 0.0,
            "deployment_times": [],
            "timing_stats": {}
        }

        # Try multiple deployment data sources
        deployment_files = [
            self.service_dir / "deployments-30days.json",
            RESEARCH_DIR / f"{self.service}-deployments-30days.json"
        ]

        deployments = []
        for deployment_file in deployment_files:
            if deployment_file.exists():
                try:
                    with open(deployment_file, 'r') as f:
                        data = json.load(f)

                    # Handle different data formats
                    if isinstance(data, dict) and "deployment_events" in data:
                        deployments = data["deployment_events"]
                    elif isinstance(data, list):
                        deployments = data
                    elif isinstance(data, dict) and self.service in data:
                        service_data = data[self.service]
                        if isinstance(service_data, dict) and "deployment_events" in service_data:
                            deployments = service_data["deployment_events"]
                        elif isinstance(service_data, list):
                            deployments = service_data
                    break
                except Exception:
                    continue

        for deployment in deployments:
            if not isinstance(deployment, dict):
                continue

            result["total_deployments"] += 1

            status = deployment.get("status", "unknown")
            if status == "failed" or not deployment.get("success", True):
                result["failed_deployments"] += 1
            else:
                result["successful_deployments"] += 1

            # Extract deployment timing
            duration = deployment.get("deployment_duration_seconds")
            if duration and isinstance(duration, (int, float)) and duration > 0:
                result["deployment_times"].append(duration)

        # Calculate rates using rate() function patterns
        if result["total_deployments"] > 0:
            result["deployment_error_rate"] = self.rate_percent(result["failed_deployments"], result["total_deployments"])
            result["deployment_success_rate"] = self.rate_percent(result["successful_deployments"], result["total_deployments"])

        result["deployment_rate_per_day"] = self.rate_per_day(result["total_deployments"])

        # Calculate timing statistics
        if result["deployment_times"]:
            result["timing_stats"] = self._calculate_percentiles(result["deployment_times"])

        self.query_results["queries_executed"].append("deployment_error_rates")
        return result

    def query_overall_error_rates(self) -> Dict[str, Any]:
        """
        Query overall error rates combining all sources using weighted rate() patterns.

        Rate patterns:
        - weighted_error_score(all_errors) -> Combined error severity score
        - rate_per_day(weighted_score) -> Daily weighted error rate
        """
        http_errors = self.query_http_error_rates()
        app_errors = self.query_application_error_rates()
        oom_errors = self.query_oom_kill_rates()
        deployment_errors = self.query_deployment_error_rates()

        result = {
            "query_type": "overall_error_rates",
            "rate_patterns_used": [
                "weighted_error_score(all_errors, severity_weights)",
                "rate_per_day(total_errors_all_sources)",
                "rate_per_day(weighted_error_score)"
            ],
            "total_errors_all_sources": 0,
            "error_rate_per_day": 0.0,
            "weighted_error_score": 0.0,
            "weighted_error_rate_per_day": 0.0,
            "error_breakdown": {},
            "component_metrics": {}
        }

        # Error breakdown
        http_5xx = http_errors.get("http_5xx_errors", 0)
        http_4xx = http_errors.get("http_4xx_errors", 0)
        app_errors_count = app_errors.get("total_error_count", 0)
        oom_kills = oom_errors.get("total_oom_kill_count", 0)
        deployment_failures = deployment_errors.get("failed_deployments", 0)

        total_errors = http_5xx + http_4xx + app_errors_count + oom_kills + deployment_failures

        result["error_breakdown"] = {
            "http_5xx_errors": http_5xx,
            "http_4xx_errors": http_4xx,
            "app_errors": app_errors_count,
            "oom_kills": oom_kills,
            "deployment_failures": deployment_failures
        }

        result["total_errors_all_sources"] = total_errors
        result["error_rate_per_day"] = self.rate_per_day(total_errors)

        # Calculate weighted error score (severity weights)
        error_weights = {
            "http_5xx": 3.0,      # Critical
            "oom_kills": 3.0,     # Critical
            "deployment_failures": 2.0,  # High
            "app_errors": 1.0,    # Medium
            "http_4xx": 0.5       # Low
        }

        weighted_score = (
            http_5xx * error_weights["http_5xx"] +
            oom_kills * error_weights["oom_kills"] +
            deployment_failures * error_weights["deployment_failures"] +
            app_errors_count * error_weights["app_errors"] +
            http_4xx * error_weights["http_4xx"]
        )

        result["weighted_error_score"] = weighted_score
        result["weighted_error_rate_per_day"] = self.rate_per_day(weighted_score)

        # Component metrics
        result["component_metrics"] = {
            "http": http_errors,
            "application": app_errors,
            "oom": oom_errors,
            "deployment": deployment_errors
        }

        self.query_results["queries_executed"].append("overall_error_rates")
        return result

    def _calculate_percentiles(self, data: List[float]) -> Dict[str, float]:
        """Calculate percentile statistics for numeric data."""
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

    def run_all_queries(self) -> Dict[str, Any]:
        """Execute all rate-based queries and return comprehensive results."""
        print(f"\n{'='*70}")
        print(f"Running Rate-Based Error Queries for: {self.service}")
        print(f"{'='*70}")
        print(f"Analysis Period: {ANALYSIS_PERIOD['start']} to {ANALYSIS_PERIOD['end']}")
        print(f"Duration: {ANALYSIS_PERIOD['days']} days")

        results = {
            "service": self.service,
            "time_range": ANALYSIS_PERIOD,
            "queries": {}
        }

        # Execute individual queries
        print("\nExecuting HTTP error rates query...")
        results["queries"]["http_error_rates"] = self.query_http_error_rates()

        print("Executing application error rates query...")
        results["queries"]["application_error_rates"] = self.query_application_error_rates()

        print("Executing OOM kill rates query...")
        results["queries"]["oom_kill_rates"] = self.query_oom_kill_rates()

        print("Executing deployment error rates query...")
        results["queries"]["deployment_error_rates"] = self.query_deployment_error_rates()

        print("Executing overall error rates query...")
        results["queries"]["overall_error_rates"] = self.query_overall_error_rates()

        # Add execution metadata
        results["query_timestamp"] = datetime.now().isoformat()
        results["queries_executed"] = self.query_results["queries_executed"]

        return results


def test_query_returns_data(query_result: Dict[str, Any]) -> Dict[str, Any]:
    """
    Test if a query returns actual data (not all zeros).

    Returns test result with pass/fail status and message.
    """
    test_result = {
        "passed": False,
        "message": "",
        "positive_values_count": 0,
        "zero_values_count": 0
    }

    query_type = query_result.get("query_type", "unknown")

    # Count positive (non-zero) values in the query result
    positive_values = []
    zero_values = []

    for key, value in query_result.items():
        if key == "query_type" or key == "rate_patterns_used":
            continue
        if isinstance(value, (int, float)):
            if value > 0:
                positive_values.append((key, value))
            elif value == 0:
                zero_values.append((key, value))
        elif isinstance(value, list):
            if len(value) > 0:
                positive_values.append((key, f"list with {len(value)} items"))

    test_result["positive_values_count"] = len(positive_values)
    test_result["zero_values_count"] = len(zero_values)

    # Determine if query passes (has at least one positive value)
    if len(positive_values) >= 1:
        test_result["passed"] = True
        test_result["message"] = f"{query_type}: ✓ Returns actual data ({len(positive_values)} positive values)"
    else:
        test_result["message"] = f"{query_type}: All metric values are zero - no data collected"

    return test_result


def main():
    """Execute rate-based 30-day error rate queries for all services."""
    print("="*70)
    print("Rate-Based 30-Day Error Rate Queries")
    print("="*70)
    print(f"Analysis Period: {ANALYSIS_PERIOD['start']} to {ANALYSIS_PERIOD['end']}")
    print(f"Services: {', '.join(SERVICES)}")

    all_results = {
        "collection_metadata": {
            "timestamp": datetime.now().isoformat(),
            "analysis_period": ANALYSIS_PERIOD,
            "services_analyzed": SERVICES,
            "query_methodology": "rate-based aggregation patterns"
        },
        "services": {}
    }

    # Run queries for each service
    for service in SERVICES:
        query_engine = RateBasedErrorQuery(service)
        service_results = query_engine.run_all_queries()

        # Test each query
        test_results = {}
        print(f"\n{service.upper()} Query Tests:")
        print("-" * 50)

        for query_name, query_data in service_results["queries"].items():
            test_result = test_query_returns_data(query_data)
            test_results[query_name] = test_result
            print(f"  {test_result['message']}")

        service_results["test_results"] = test_results
        all_results["services"][service] = service_results

    # Save comprehensive results
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = OUTPUT_DIR / f"tested_error_rate_queries_{timestamp}.json"

    with open(output_file, 'w') as f:
        json.dump(all_results, f, indent=2, default=str)

    print(f"\n{'='*70}")
    print(f"✓ Comprehensive query results saved to: {output_file}")
    print(f"{'='*70}")

    # Print summary statistics
    print("\nQuery Execution Summary:")
    for service in SERVICES:
        service_data = all_results["services"][service]
        print(f"\n{service.upper()}:")

        for query_name, query_data in service_data["queries"].items():
            print(f"  {query_name}:")
            # Print key metrics
            for key, value in query_data.items():
                if key not in ["query_type", "rate_patterns_used", "data_sources", "pods_with_error_details", "pods_affected_details"]:
                    if isinstance(value, (int, float)) and value > 0:
                        print(f"    {key}: {value}")

    return all_results


if __name__ == "__main__":
    main()