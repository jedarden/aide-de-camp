#!/usr/bin/env python3
"""
30-Day Error Rate Query Examples and Testing

This script provides comprehensive examples for querying 30-day error rates
and testing that they return actual data from the research datasets.

Error Rate Types Covered:
- HTTP error rates (5xx, 4xx) from nginx logs
- Application error rates from pod logs
- Deployment error rates from deployment records
- OOM kill rates from pod analysis
- Overall system error rates

Author: aide-de-camp
Date: 2026-08-06
"""

import json
import statistics
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
import re


class ThirtyDayErrorRateQueries:
    """Comprehensive 30-day error rate query examples and testing."""

    def __init__(self, service: str = "pbx-web"):
        self.service = service
        self.time_range = {
            "start": "2026-07-07T00:00:00Z",
            "end": "2026-08-06T23:59:59Z",
            "days": 30
        }
        self.research_dir = Path(f"/home/coding/aide-de-camp/research/{service}-30days")

    def rate(self, count: int, total: int) -> float:
        """
        Calculate rate as ratio.

        Best Practice: Always handle division by zero to avoid NaN results.
        Consider the temporal context (per day, per hour, per request).
        """
        if total == 0:
            return 0.0
        return count / total

    def rate_per_day(self, count: int, days: int = 30) -> float:
        """
        Calculate rate per day for normalized comparison.

        Optimization: Use per-day rates when comparing time periods of
        different lengths to normalize for temporal differences.
        """
        if days == 0:
            return 0.0
        return count / days

    def calculate_percentiles(self, data: List[float]) -> Dict[str, float]:
        """
        Calculate comprehensive percentile statistics.

        Returns count, mean, median, p50, p95, min, max for dataset.
        Handles empty datasets gracefully.
        """
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
        """
        Query 1: HTTP Error Rates from nginx logs

        Returns 5xx and 4xx error rates as percentages of total requests.

        Query Pattern:
        - Parse nginx access logs for HTTP status codes
        - Count total requests, 5xx errors, 4xx errors
        - Calculate rate() for each error class

        Best Practices:
        - Separate 5xx (server errors) from 4xx (client errors)
        - Use both absolute counts and percentages
        - Consider time-series analysis for trend detection
        """
        pod_logs_dir = self.research_dir / "pod-logs"

        http_metrics = {
            "http_5xx_errors": 0,
            "http_4xx_errors": 0,
            "http_total_requests": 0,
            "http_5xx_error_rate": 0.0,
            "http_4xx_error_rate": 0.0,
            "data_sources": [],
            "log_files_analyzed": 0
        }

        # Find nginx log files
        nginx_logs = list(pod_logs_dir.glob("*nginx*.log"))
        http_metrics["data_sources"] = [log.name for log in nginx_logs]

        for nginx_log in nginx_logs:
            try:
                with open(nginx_log, 'r') as f:
                    lines = f.readlines()
                    http_metrics["log_files_analyzed"] += 1

                for line in lines:
                    # Parse HTTP status codes from nginx logs
                    status_match = re.search(r'"\w+ [^\s]+ HTTP/\d\.\d" (\d+)', line)
                    if status_match:
                        status_code = int(status_match.group(1))
                        http_metrics["http_total_requests"] += 1

                        if status_code >= 500:
                            http_metrics["http_5xx_errors"] += 1
                        elif status_code >= 400:
                            http_metrics["http_4xx_errors"] += 1

            except Exception as e:
                print(f"  Warning: Failed to analyze {nginx_log}: {e}")

        # Calculate error rates
        if http_metrics["http_total_requests"] > 0:
            http_metrics["http_5xx_error_rate"] = self.rate(
                http_metrics["http_5xx_errors"],
                http_metrics["http_total_requests"]
            )
            http_metrics["http_4xx_error_rate"] = self.rate(
                http_metrics["http_4xx_errors"],
                http_metrics["http_total_requests"]
            )

        return http_metrics

    def query_application_error_rates(self) -> Dict[str, Any]:
        """
        Query 2: Application Error Rates from pod logs

        Returns application-level error counts and rates from pod analysis.

        Query Pattern:
        - Read pod log analysis JSON files
        - Aggregate error counts across all pods
        - Calculate rate_per_pod and rate_per_day

        Best Practices:
        - Distinguish between error count and error rate
        - Track which pods have errors vs total pods
        - Use per-day rates for cross-period comparison
        """
        pod_logs_dir = self.research_dir / "pod-logs"
        analysis_files = list(pod_logs_dir.glob("*-analysis.json"))

        app_metrics = {
            "total_pods_analyzed": len(analysis_files),
            "pods_with_errors": 0,
            "pods_without_errors": 0,
            "total_error_count": 0,
            "error_rate_per_pod": 0.0,
            "error_rate_per_day": 0.0,
            "pods_with_error_details": []
        }

        for analysis_file in analysis_files:
            try:
                with open(analysis_file, 'r') as f:
                    data = json.load(f)

                error_count = data.get("patterns", {}).get("error", {}).get("count", 0)
                pod_name = analysis_file.stem.replace("-analysis", "")

                if error_count > 0:
                    app_metrics["pods_with_errors"] += 1
                    app_metrics["total_error_count"] += error_count
                    app_metrics["pods_with_error_details"].append({
                        "pod": pod_name,
                        "errors": error_count
                    })
                else:
                    app_metrics["pods_without_errors"] += 1

            except Exception as e:
                print(f"  Warning: Failed to read {analysis_file}: {e}")

        # Calculate error rates
        if app_metrics["total_pods_analyzed"] > 0:
            app_metrics["error_rate_per_pod"] = self.rate(
                app_metrics["total_error_count"],
                app_metrics["total_pods_analyzed"]
            )

        app_metrics["error_rate_per_day"] = self.rate_per_day(
            app_metrics["total_error_count"],
            self.time_range["days"]
        )

        return app_metrics

    def query_oom_kill_rates(self) -> Dict[str, Any]:
        """
        Query 3: OOM Kill Error Rates from pod analysis

        Returns OOM (Out Of Memory) kill rates which indicate resource exhaustion.

        Query Pattern:
        - Extract OOM kill counts from pod analysis
        - Calculate per-pod and per-day OOM rates
        - Track which pods experienced OOM kills

        Best Practices:
        - OOM kills are severe - track them separately from app errors
        - High OOM rates indicate memory leaks or underprovisioning
        - Use per-day rates to detect increasing trends
        """
        pod_logs_dir = self.research_dir / "pod-logs"
        analysis_files = list(pod_logs_dir.glob("*-analysis.json"))

        oom_metrics = {
            "total_pods_analyzed": len(analysis_files),
            "pods_with_oom_kills": 0,
            "total_oom_kill_count": 0,
            "oom_kill_rate_per_pod": 0.0,
            "oom_kill_rate_per_day": 0.0,
            "pods_affected_details": []
        }

        for analysis_file in analysis_files:
            try:
                with open(analysis_file, 'r') as f:
                    data = json.load(f)

                oom_count = data.get("patterns", {}).get("oom_kill", {}).get("count", 0)
                pod_name = analysis_file.stem.replace("-analysis", "")

                if oom_count > 0:
                    oom_metrics["pods_with_oom_kills"] += 1
                    oom_metrics["total_oom_kill_count"] += oom_count
                    oom_metrics["pods_affected_details"].append({
                        "pod": pod_name,
                        "oom_kills": oom_count
                    })

            except Exception as e:
                print(f"  Warning: Failed to read {analysis_file}: {e}")

        # Calculate OOM kill rates
        if oom_metrics["total_pods_analyzed"] > 0:
            oom_metrics["oom_kill_rate_per_pod"] = self.rate(
                oom_metrics["total_oom_kill_count"],
                oom_metrics["total_pods_analyzed"]
            )

        oom_metrics["oom_kill_rate_per_day"] = self.rate_per_day(
            oom_metrics["total_oom_kill_count"],
            self.time_range["days"]
        )

        return oom_metrics

    def query_deployment_error_rates(self) -> Dict[str, Any]:
        """
        Query 4: Deployment Error Rates from deployment records

        Returns deployment success/failure rates and timing metrics.

        Query Pattern:
        - Read deployment records for the 30-day period
        - Count successful vs failed deployments
        - Calculate deployment error rate and success rate
        - Extract deployment timing metrics

        Best Practices:
        - Track both error rate AND success rate (complementary metrics)
        - Deployment timing affects error rate (longer = more failure risk)
        - Consider deployment frequency when analyzing rates
        """
        deployment_file = self.research_dir / "../deployments-30days.json"

        deploy_metrics = {
            "total_deployments": 0,
            "successful_deployments": 0,
            "failed_deployments": 0,
            "deployment_error_rate": 0.0,
            "deployment_success_rate": 0.0,
            "deployment_times": [],
            "timing_stats": {}
        }

        # Try multiple possible deployment file locations
        possible_paths = [
            self.research_dir / "deployments-30days.json",
            self.research_dir.parent / "pbx-web-deployments-30days" / "deployments.json",
            Path("/home/coding/aide-de-camp/research/deployment-comparison-30days/pbx-web.json")
        ]

        deployment_data = None
        for path in possible_paths:
            if path.exists():
                deployment_file = path
                try:
                    with open(deployment_file, 'r') as f:
                        deployment_data = json.load(f)
                    break
                except Exception:
                    continue

        if deployment_data:
            deployments = deployment_data if isinstance(deployment_data, list) else deployment_data.get("deployments", [])

            for deployment in deployments:
                deploy_metrics["total_deployments"] += 1

                status = deployment.get("status", "").lower()
                if "fail" in status:
                    deploy_metrics["failed_deployments"] += 1
                else:
                    deploy_metrics["successful_deployments"] += 1

                # Extract timing data
                if "duration" in deployment:
                    try:
                        duration = float(deployment["duration"])
                        if duration > 0:
                            deploy_metrics["deployment_times"].append(duration)
                    except (ValueError, TypeError):
                        pass

            # Calculate deployment rates
            if deploy_metrics["total_deployments"] > 0:
                deploy_metrics["deployment_error_rate"] = self.rate(
                    deploy_metrics["failed_deployments"],
                    deploy_metrics["total_deployments"]
                )
                deploy_metrics["deployment_success_rate"] = self.rate(
                    deploy_metrics["successful_deployments"],
                    deploy_metrics["total_deployments"]
                )

            # Calculate timing statistics
            if deploy_metrics["deployment_times"]:
                deploy_metrics["timing_stats"] = self.calculate_percentiles(
                    deploy_metrics["deployment_times"]
                )

        return deploy_metrics

    def query_overall_error_rates(self) -> Dict[str, Any]:
        """
        Query 5: Overall System Error Rate (composite metric)

        Returns aggregated error rate across all sources for holistic view.

        Query Pattern:
        - Combine all error sources into single metric
        - Calculate total error rate per day
        - Weight by severity (5xx > 4xx > app errors)

        Best Practices:
        - Use composite metrics for executive dashboards
        - Maintain drill-down capability to source metrics
        - Consider severity weighting for alerting thresholds
        """
        # Get all individual error metrics
        http_metrics = self.query_http_error_rates()
        app_metrics = self.query_application_error_rates()
        oom_metrics = self.query_oom_kill_rates()
        deploy_metrics = self.query_deployment_error_rates()

        # Calculate total errors across all sources
        total_errors = (
            http_metrics["http_5xx_errors"] +
            http_metrics["http_4xx_errors"] +
            app_metrics["total_error_count"] +
            oom_metrics["total_oom_kill_count"] +
            deploy_metrics["failed_deployments"]
        )

        # Calculate weighted error score (5xx weighted higher)
        weighted_errors = (
            http_metrics["http_5xx_errors"] * 5.0 +  # Server errors = 5x weight
            http_metrics["http_4xx_errors"] * 2.0 +  # Client errors = 2x weight
            app_metrics["total_error_count"] * 1.0 +  # App errors = 1x weight
            oom_metrics["total_oom_kill_count"] * 3.0 +  # OOM kills = 3x weight
            deploy_metrics["failed_deployments"] * 4.0  # Deploy failures = 4x weight
        )

        overall_metrics = {
            "total_errors_all_sources": total_errors,
            "error_rate_per_day": self.rate_per_day(total_errors, self.time_range["days"]),
            "weighted_error_score": weighted_errors,
            "weighted_error_rate_per_day": self.rate_per_day(weighted_errors, self.time_range["days"]),
            "error_breakdown": {
                "http_5xx_errors": http_metrics["http_5xx_errors"],
                "http_4xx_errors": http_metrics["http_4xx_errors"],
                "app_errors": app_metrics["total_error_count"],
                "oom_kills": oom_metrics["total_oom_kill_count"],
                "deployment_failures": deploy_metrics["failed_deployments"]
            },
            "component_metrics": {
                "http": http_metrics,
                "application": app_metrics,
                "oom": oom_metrics,
                "deployment": deploy_metrics
            }
        }

        return overall_metrics

    def test_query_returns_data(self, query_name: str, query_result: Dict[str, Any]) -> Tuple[bool, str]:
        """
        Test that a query returns actual data (not empty/zero).

        Returns (success: bool, message: str) indicating if query has data.

        Test Criteria:
        - Query executes without errors
        - Returns non-zero values for key metrics
        - Has valid data sources identified
        - No critical data gaps
        """
        # Check for basic execution success
        if not query_result:
            return False, f"{query_name}: Query returned None or empty result"

        # Check for data sources
        if "data_sources" in query_result and not query_result["data_sources"]:
            return False, f"{query_name}: No data sources found"

        # Check for zero metrics across the board
        total_values = sum(
            1 for v in query_result.values()
            if isinstance(v, (int, float)) and v > 0
        )

        if total_values == 0:
            return False, f"{query_name}: All metric values are zero - no data collected"

        # Check for critical data gaps
        if "total_pods_analyzed" in query_result and query_result["total_pods_analyzed"] == 0:
            return False, f"{query_name}: No pods analyzed - data collection failed"

        return True, f"{query_name}: ✓ Returns actual data ({total_values} positive values)"

    def run_all_queries_with_tests(self) -> Dict[str, Any]:
        """
        Run all error rate queries and test they return data.

        Executes each query type, validates results, and provides
        comprehensive test output with pass/fail status.
        """
        print("=" * 70)
        print("30-Day Error Rate Query Examples and Testing")
        print("=" * 70)
        print(f"Service: {self.service}")
        print(f"Time Range: {self.time_range['start']} to {self.time_range['end']}")
        print(f"Period: {self.time_range['days']} days")
        print("=" * 70)

        results = {
            "service": self.service,
            "time_range": self.time_range,
            "queries": {},
            "test_results": {},
            "query_timestamp": datetime.now().isoformat()
        }

        # Define all queries to run
        queries = {
            "http_error_rates": self.query_http_error_rates,
            "application_error_rates": self.query_application_error_rates,
            "oom_kill_rates": self.query_oom_kill_rates,
            "deployment_error_rates": self.query_deployment_error_rates,
            "overall_error_rates": self.query_overall_error_rates
        }

        # Run each query and test results
        for query_name, query_func in queries.items():
            print(f"\n{'=' * 70}")
            print(f"Query: {query_name}")
            print('=' * 70)

            try:
                query_result = query_func()
                results["queries"][query_name] = query_result

                # Test that query returns actual data
                success, message = self.test_query_returns_data(query_name, query_result)
                results["test_results"][query_name] = {"passed": success, "message": message}

                print(f"\nResults:")
                self._print_query_summary(query_name, query_result)
                print(f"\nTest: {message}")

            except Exception as e:
                error_msg = f"{query_name}: Query execution failed - {str(e)}"
                results["test_results"][query_name] = {"passed": False, "message": error_msg}
                print(f"\n✗ Error: {error_msg}")

        # Print overall test summary
        self._print_test_summary(results["test_results"])

        return results

    def _print_query_summary(self, query_name: str, result: Dict[str, Any]):
        """Print formatted summary of query results."""
        if query_name == "http_error_rates":
            print(f"  HTTP 5xx Errors: {result['http_5xx_errors']}")
            print(f"  HTTP 4xx Errors: {result['http_4xx_errors']}")
            print(f"  Total Requests: {result['http_total_requests']}")
            print(f"  5xx Error Rate: {result['http_5xx_error_rate']:.2%}")
            print(f"  4xx Error Rate: {result['http_4xx_error_rate']:.2%}")
            print(f"  Log Files Analyzed: {result['log_files_analyzed']}")

        elif query_name == "application_error_rates":
            print(f"  Total Pods Analyzed: {result['total_pods_analyzed']}")
            print(f"  Pods With Errors: {result['pods_with_errors']}")
            print(f"  Total Error Count: {result['total_error_count']}")
            print(f"  Error Rate Per Pod: {result['error_rate_per_pod']:.2f}")
            print(f"  Error Rate Per Day: {result['error_rate_per_day']:.2f}")

        elif query_name == "oom_kill_rates":
            print(f"  Total Pods Analyzed: {result['total_pods_analyzed']}")
            print(f"  Pods With OOM Kills: {result['pods_with_oom_kills']}")
            print(f"  Total OOM Kill Count: {result['total_oom_kill_count']}")
            print(f"  OOM Kill Rate Per Pod: {result['oom_kill_rate_per_pod']:.2f}")
            print(f"  OOM Kill Rate Per Day: {result['oom_kill_rate_per_day']:.2f}")

        elif query_name == "deployment_error_rates":
            print(f"  Total Deployments: {result['total_deployments']}")
            print(f"  Successful Deployments: {result['successful_deployments']}")
            print(f"  Failed Deployments: {result['failed_deployments']}")
            print(f"  Deployment Error Rate: {result['deployment_error_rate']:.2%}")
            print(f"  Deployment Success Rate: {result['deployment_success_rate']:.2%}")
            if result.get('timing_stats'):
                stats = result['timing_stats']
                print(f"  Deployment Time p50: {stats.get('p50', 0):.1f}s")
                print(f"  Deployment Time p95: {stats.get('p95', 0):.1f}s")

        elif query_name == "overall_error_rates":
            print(f"  Total Errors (All Sources): {result['total_errors_all_sources']}")
            print(f"  Error Rate Per Day: {result['error_rate_per_day']:.2f}")
            print(f"  Weighted Error Score: {result['weighted_error_score']:.1f}")
            print(f"  Weighted Error Rate Per Day: {result['weighted_error_rate_per_day']:.2f}")

            print(f"\n  Error Breakdown:")
            for error_type, count in result['error_breakdown'].items():
                print(f"    {error_type}: {count}")

    def _print_test_summary(self, test_results: Dict[str, Any]):
        """Print overall test summary with pass/fail status."""
        print(f"\n{'=' * 70}")
        print("TEST SUMMARY")
        print('=' * 70)

        passed = sum(1 for r in test_results.values() if r.get("passed", False))
        total = len(test_results)

        print(f"\nTests Passed: {passed}/{total}")

        for query_name, result in test_results.items():
            status = "✓ PASS" if result.get("passed", False) else "✗ FAIL"
            print(f"  {status}: {query_name}")
            print(f"    {result['message']}")

        print(f"\n{'=' * 70}")
        if passed == total:
            print("✓ ALL TESTS PASSED - All queries return actual data")
        else:
            print(f"⚠ {total - passed} TEST(S) FAILED - Some queries need investigation")
        print('=' * 70)


def main():
    """Main execution for running and testing 30-day error rate queries."""
    print("\n" + "=" * 70)
    print("30-DAY ERROR RATE QUERY EXAMPLES AND TESTING")
    print("=" * 70)

    # Test both services
    for service in ["pbx-web", "whisper-stt"]:
        print(f"\n\n{'#' * 70}")
        print(f"# TESTING SERVICE: {service.upper()}")
        print('#' * 70)

        try:
            query_system = ThirtyDayErrorRateQueries(service)
            results = query_system.run_all_queries_with_tests()

            # Save results to file
            output_dir = Path("/home/coding/aide-de-camp/data")
            output_dir.mkdir(parents=True, exist_ok=True)

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_file = output_dir / f"tested_error_rate_queries_{service}_{timestamp}.json"

            with open(output_file, 'w') as f:
                json.dump(results, f, indent=2, default=str)

            print(f"\n✓ Results saved to: {output_file}")

        except Exception as e:
            print(f"\n✗ Failed to test {service}: {e}")

    print(f"\n\n{'=' * 70}")
    print("QUERY TESTING COMPLETE")
    print('=' * 70)


if __name__ == "__main__":
    main()