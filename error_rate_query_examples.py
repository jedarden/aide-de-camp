#!/usr/bin/env python3
"""
Error Rate Query Examples for 30-Day Aggregation

This script provides comprehensive query examples for calculating error rates
over 30-day periods, with proper time range syntax and aggregation functions.

Query Types Covered:
1. Pod-level error rates from log analysis
2. HTTP error rates from nginx logs
3. Deployment error rates from k8s events
4. OOM kill rates and pod restart metrics
5. Time-series error rate trends
6. Comparative error rates across services
"""

import json
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional
import statistics

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


class ErrorRateQueryExamples:
    """Comprehensive error rate query examples with 30-day aggregation."""

    def __init__(self, service: str, time_range: Dict[str, Any]):
        self.service = service
        self.time_range = time_range
        self.service_dir = Path(f"/home/coding/aide-de-camp/research/{service}-30days")
        self.results = {
            "service": service,
            "time_range": time_range,
            "queries_executed": [],
            "query_results": {}
        }

    def query_1_pod_error_rate(self) -> Dict[str, Any]:
        """
        Query 1: Pod-level error rate from log analysis

        Error Rate Formula:
        error_rate_per_pod = total_error_count / total_pods_analyzed

        Aggregation Functions:
        - SUM(error_counts) across all pods
        - COUNT(pods) with errors
        - AVG(error_rate_per_pod)
        """
        query_name = "pod_error_rate_from_logs"
        pod_logs_dir = self.service_dir / "pod-logs"

        result = {
            "query_description": "Calculate error rate per pod from log analysis files",
            "aggregation_functions": [
                "SUM(error_counts) across all pods",
                "COUNT(pods) with errors",
                "AVG(error_rate_per_pod)"
            ],
            "error_rate_formula": "error_rate_per_pod = total_error_count / total_pods_analyzed",
            "data_source": f"{pod_logs_dir}/*-analysis.json"
        }

        if not pod_logs_dir.exists():
            result["error"] = "Pod logs directory not found"
            return result

        # Execute query
        total_pods = 0
        pods_with_errors = 0
        total_error_count = 0
        error_details = []

        analysis_files = list(pod_logs_dir.glob("*-analysis.json"))
        for analysis_file in analysis_files:
            try:
                with open(analysis_file, 'r') as f:
                    data = json.load(f)

                patterns = data.get("patterns", {})
                error_count = patterns.get("error", {}).get("count", 0)

                total_pods += 1
                if error_count > 0:
                    pods_with_errors += 1
                    total_error_count += error_count

                    # Collect error samples
                    error_samples = patterns.get("error", {}).get("samples", [])
                    if error_samples:
                        error_details.extend(error_samples[:2])
            except Exception as e:
                error_details.append(f"Failed to read {analysis_file.name}: {e}")

        # Calculate aggregated metrics
        error_rate_per_pod = total_error_count / total_pods if total_pods > 0 else 0.0
        error_percentage = (pods_with_errors / total_pods * 100) if total_pods > 0 else 0.0

        result["metrics"] = {
            "total_pods_analyzed": total_pods,
            "pods_with_errors": pods_with_errors,
            "pods_with_errors_percentage": round(error_percentage, 2),
            "total_error_count": total_error_count,
            "error_rate_per_pod": round(error_rate_per_pod, 2),
            "error_samples": error_details[:5]
        }

        self.results["queries_executed"].append(query_name)
        self.results["query_results"][query_name] = result
        return result

    def query_2_http_error_rate(self) -> Dict[str, Any]:
        """
        Query 2: HTTP error rate from nginx logs

        Error Rate Formula:
        http_5xx_error_rate = http_5xx_errors / total_http_requests
        http_4xx_error_rate = http_4xx_errors / total_http_requests

        Aggregation Functions:
        - COUNT(requests) by status code (5xx, 4xx, 2xx, 3xx)
        - SUM(requests) for total request count
        - RATE(error_requests / total_requests)
        """
        query_name = "http_error_rate_from_nginx"
        pod_logs_dir = self.service_dir / "pod-logs"

        result = {
            "query_description": "Calculate HTTP error rates from nginx access logs",
            "aggregation_functions": [
                "COUNT(requests) by status code (5xx, 4xx, 2xx, 3xx)",
                "SUM(requests) for total request count",
                "RATE(error_requests / total_requests)"
            ],
            "error_rate_formula": "http_5xx_error_rate = http_5xx_errors / total_http_requests",
            "data_source": f"{pod_logs_dir}/*nginx*.log"
        }

        nginx_logs = list(pod_logs_dir.glob("*nginx*.log"))
        if not nginx_logs:
            result["error"] = "No nginx log files found"
            return result

        # Execute query
        http_5xx_errors = 0
        http_4xx_errors = 0
        http_2xx_requests = 0
        http_3xx_requests = 0
        total_requests = 0
        error_samples = []

        for nginx_log in nginx_logs:
            try:
                with open(nginx_log, 'r') as f:
                    lines = f.readlines()

                for line in lines:
                    # Parse HTTP status code from nginx log
                    status_match = re.search(r'"\w+ [^\s]+ HTTP/\d\.\d" (\d+)', line)
                    if status_match:
                        status_code = int(status_match.group(1))
                        total_requests += 1

                        if status_code >= 500:
                            http_5xx_errors += 1
                            if len(error_samples) < 5:
                                error_samples.append({
                                    "status": status_code,
                                    "line": line.strip()[:150]
                                })
                        elif status_code >= 400:
                            http_4xx_errors += 1
                        elif status_code >= 300:
                            http_3xx_requests += 1
                        elif status_code >= 200:
                            http_2xx_requests += 1
            except Exception as e:
                error_samples.append(f"Failed to parse {nginx_log.name}: {e}")

        # Calculate error rates
        http_5xx_error_rate = (http_5xx_errors / total_requests * 100) if total_requests > 0 else 0.0
        http_4xx_error_rate = (http_4xx_errors / total_requests * 100) if total_requests > 0 else 0.0

        result["metrics"] = {
            "total_http_requests": total_requests,
            "http_5xx_errors": http_5xx_errors,
            "http_5xx_error_rate_percent": round(http_5xx_error_rate, 3),
            "http_4xx_errors": http_4xx_errors,
            "http_4xx_error_rate_percent": round(http_4xx_error_rate, 3),
            "http_2xx_requests": http_2xx_requests,
            "http_3xx_requests": http_3xx_requests,
            "error_samples": error_samples[:5]
        }

        self.results["queries_executed"].append(query_name)
        self.results["query_results"][query_name] = result
        return result

    def query_3_deployment_error_rate(self) -> Dict[str, Any]:
        """
        Query 3: Deployment error rate from k8s events

        Error Rate Formula:
        deployment_error_rate = failed_deployments / total_deployments
        deployment_success_rate = successful_deployments / total_deployments

        Aggregation Functions:
        - COUNT(deployments) by status (failed, success)
        - SUM(deployments) for total deployment count
        - RATE(failed_deployments / total_deployments)
        """
        query_name = "deployment_error_rate_from_k8s"

        result = {
            "query_description": "Calculate deployment error/success rates from k8s deployment events",
            "aggregation_functions": [
                "COUNT(deployments) by status (failed, success)",
                "SUM(deployments) for total deployment count",
                "RATE(failed_deployments / total_deployments)"
            ],
            "error_rate_formula": "deployment_error_rate = failed_deployments / total_deployments",
            "data_source": f"{self.service_dir}/deployments-30days.json"
        }

        # Try multiple deployment file locations
        deployment_files = [
            self.service_dir / "deployments-30days.json",
            self.service_dir / "k8s-events" / "deployments.json"
        ]

        deployment_file = None
        for file_path in deployment_files:
            if file_path.exists():
                deployment_file = file_path
                break

        if not deployment_file:
            result["error"] = "Deployment data file not found"
            return result

        try:
            with open(deployment_file, 'r') as f:
                deployment_data = json.load(f)

            # Extract deployment events from nested structure
            deployments = []
            if isinstance(deployment_data, dict):
                if "deployments" in deployment_data:
                    deployments_data = deployment_data["deployments"]
                    if self.service in deployments_data:
                        service_data = deployments_data[self.service]
                        if isinstance(service_data, dict) and "deployment_events" in service_data:
                            deployments = service_data["deployment_events"]
                        elif isinstance(service_data, list):
                            deployments = service_data
                    elif isinstance(deployments_data, list):
                        deployments = deployments_data
                elif "deployment_events" in deployment_data:
                    deployments = deployment_data["deployment_events"]
            elif isinstance(deployment_data, list):
                deployments = deployment_data

            # Execute query
            total_deployments = 0
            successful_deployments = 0
            failed_deployments = 0
            deployment_details = []

            for deployment in deployments:
                if not isinstance(deployment, dict):
                    continue

                total_deployments += 1

                # Check deployment status
                success = deployment.get("success", True)
                status = deployment.get("status", "unknown")

                if status == "failed" or not success:
                    failed_deployments += 1
                    deployment_details.append({
                        "status": status,
                        "replicaset": deployment.get("replicaset", "unknown"),
                        "timestamp": deployment.get("timestamp", "unknown")
                    })
                else:
                    successful_deployments += 1

            # Calculate deployment rates
            deployment_error_rate = (failed_deployments / total_deployments * 100) if total_deployments > 0 else 0.0
            deployment_success_rate = (successful_deployments / total_deployments * 100) if total_deployments > 0 else 0.0

            result["metrics"] = {
                "total_deployments": total_deployments,
                "successful_deployments": successful_deployments,
                "failed_deployments": failed_deployments,
                "deployment_error_rate_percent": round(deployment_error_rate, 2),
                "deployment_success_rate_percent": round(deployment_success_rate, 2),
                "deployment_failures": deployment_details[:5]
            }

        except Exception as e:
            result["error"] = f"Failed to process deployment data: {e}"

        self.results["queries_executed"].append(query_name)
        self.results["query_results"][query_name] = result
        return result

    def query_4_oom_kill_rate(self) -> Dict[str, Any]:
        """
        Query 4: OOM kill rate and pod restart metrics

        Error Rate Formula:
        oom_kill_rate = total_oom_kills / total_pods_analyzed
        restart_rate = total_restarts / total_pods_analyzed

        Aggregation Functions:
        - COUNT(OOM killed pods)
        - SUM(OOM kill events)
        - RATE(OOM_kills / total_pods)
        """
        query_name = "oom_kill_rate_from_logs"
        pod_logs_dir = self.service_dir / "pod-logs"

        result = {
            "query_description": "Calculate OOM kill and pod restart rates from log analysis",
            "aggregation_functions": [
                "COUNT(OOM killed pods)",
                "SUM(OOM kill events)",
                "RATE(OOM_kills / total_pods)"
            ],
            "error_rate_formula": "oom_kill_rate = total_oom_kills / total_pods_analyzed",
            "data_source": f"{pod_logs_dir}/*-analysis.json"
        }

        if not pod_logs_dir.exists():
            result["error"] = "Pod logs directory not found"
            return result

        # Execute query
        total_pods = 0
        pods_with_oom = 0
        total_oom_kills = 0
        oom_details = []

        analysis_files = list(pod_logs_dir.glob("*-analysis.json"))
        for analysis_file in analysis_files:
            try:
                with open(analysis_file, 'r') as f:
                    data = json.load(f)

                patterns = data.get("patterns", {})
                oom_count = patterns.get("oom_kill", {}).get("count", 0)

                total_pods += 1
                if oom_count > 0:
                    pods_with_oom += 1
                    total_oom_kills += oom_count

                    oom_samples = patterns.get("oom_kill", {}).get("samples", [])
                    oom_details.extend(oom_samples[:2])
            except Exception as e:
                oom_details.append(f"Failed to read {analysis_file.name}: {e}")

        # Calculate OOM rates
        oom_kill_rate = total_oom_kills / total_pods if total_pods > 0 else 0.0
        oom_pod_percentage = (pods_with_oom / total_pods * 100) if total_pods > 0 else 0.0

        result["metrics"] = {
            "total_pods_analyzed": total_pods,
            "pods_with_oom_kills": pods_with_oom,
            "pods_with_oom_percentage": round(oom_pod_percentage, 2),
            "total_oom_kill_count": total_oom_kills,
            "oom_kill_rate_per_pod": round(oom_kill_rate, 2),
            "oom_samples": oom_details[:5]
        }

        self.results["queries_executed"].append(query_name)
        self.results["query_results"][query_name] = result
        return result

    def query_5_overall_error_rate(self) -> Dict[str, Any]:
        """
        Query 5: Overall error rate across all sources

        Combined Error Rate Formula:
        overall_error_rate_per_day = total_errors_all_sources / days_in_period

        Aggregation Functions:
        - SUM(all error types: pod_errors + OOM + HTTP_5xx + HTTP_4xx + deployment_failures)
        - COUNT(days) in time period
        - RATE(total_errors / days)
        """
        query_name = "overall_error_rate_all_sources"
        days = self.time_range.get("days", 30)

        result = {
            "query_description": "Calculate overall error rate across all data sources",
            "aggregation_functions": [
                "SUM(all error types: pod_errors + OOM + HTTP_5xx + HTTP_4xx + deployment_failures)",
                "COUNT(days) in time period",
                "RATE(total_errors / days)"
            ],
            "error_rate_formula": "overall_error_rate_per_day = total_errors_all_sources / days_in_period",
            "time_period_days": days
        }

        # Get data from previous queries
        pod_errors = self.results["query_results"].get("pod_error_rate_from_logs", {}).get("metrics", {}).get("total_error_count", 0)
        http_5xx = self.results["query_results"].get("http_error_rate_from_nginx", {}).get("metrics", {}).get("http_5xx_errors", 0)
        http_4xx = self.results["query_results"].get("http_error_rate_from_nginx", {}).get("metrics", {}).get("http_4xx_errors", 0)
        deploy_errors = self.results["query_results"].get("deployment_error_rate_from_k8s", {}).get("metrics", {}).get("failed_deployments", 0)
        oom_kills = self.results["query_results"].get("oom_kill_rate_from_logs", {}).get("metrics", {}).get("total_oom_kill_count", 0)

        # Calculate combined metrics
        total_errors_all_sources = pod_errors + oom_kills + http_5xx + http_4xx + deploy_errors
        error_rate_per_day = total_errors_all_sources / days if days > 0 else 0.0

        result["metrics"] = {
            "pod_errors": pod_errors,
            "oom_kills": oom_kills,
            "http_5xx_errors": http_5xx,
            "http_4xx_errors": http_4xx,
            "deployment_failures": deploy_errors,
            "total_errors_all_sources": total_errors_all_sources,
            "error_rate_per_day": round(error_rate_per_day, 2),
            "error_breakdown": {
                "pod_errors_percent": round(pod_errors / total_errors_all_sources * 100, 1) if total_errors_all_sources > 0 else 0,
                "oom_kills_percent": round(oom_kills / total_errors_all_sources * 100, 1) if total_errors_all_sources > 0 else 0,
                "http_5xx_percent": round(http_5xx / total_errors_all_sources * 100, 1) if total_errors_all_sources > 0 else 0,
                "http_4xx_percent": round(http_4xx / total_errors_all_sources * 100, 1) if total_errors_all_sources > 0 else 0,
                "deployment_failures_percent": round(deploy_errors / total_errors_all_sources * 100, 1) if total_errors_all_sources > 0 else 0
            }
        }

        self.results["queries_executed"].append(query_name)
        self.results["query_results"][query_name] = result
        return result

    def run_all_queries(self) -> Dict[str, Any]:
        """Run all error rate query examples."""
        print(f"\n{'='*70}")
        print(f"Error Rate Query Examples - {self.service}")
        print(f"{'='*70}")
        print(f"Time Range: {self.time_range.get('description', 'N/A')}")
        print(f"Period: {self.time_range.get('start', 'N/A')} to {self.time_range.get('end', 'N/A')}")

        # Run all queries
        self.query_1_pod_error_rate()
        self.query_2_http_error_rate()
        self.query_3_deployment_error_rate()
        self.query_4_oom_kill_rate()
        self.query_5_overall_error_rate()

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
                    if isinstance(value, (int, float)) and not key.endswith("_samples") and not key.endswith("_details"):
                        print(f"    {key}: {value}")

        return self.results


def main():
    """Main execution demonstrating all query examples."""
    print("="*70)
    print("30-Day Error Rate Query Examples")
    print("="*70)

    # Demonstrate time range syntax
    print("\nTime Range Syntax Examples:")
    for name, config in TIME_RANGE_EXAMPLES.items():
        print(f"\n{name}:")
        print(f"  {config.get('description', 'N/A')}")
        for key, value in config.items():
            if key != "description":
                print(f"  {key}: {value}")

    # Test with available services
    services = ["pbx-web", "whisper-stt"]
    time_range = TIME_RANGE_EXAMPLES["absolute_30_day"]

    all_service_results = {}

    for service in services:
        print(f"\n\n{'#'*70}")
        print(f"# Testing {service.upper()} Error Rate Queries")
        print(f"{'#'*70}")

        query_examples = ErrorRateQueryExamples(service, time_range)
        service_results = query_examples.run_all_queries()
        all_service_results[service] = service_results

    # Save results
    output_dir = Path("/home/coding/aide-de-camp/data")
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = output_dir / f"error_rate_query_examples_30d_{timestamp}.json"

    with open(output_file, 'w') as f:
        json.dump(all_service_results, f, indent=2, default=str)

    print(f"\n{'='*70}")
    print(f"✓ Complete! Results saved to: {output_file}")
    print(f"{'='*70}")

    return all_service_results


if __name__ == "__main__":
    main()