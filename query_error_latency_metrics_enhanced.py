#!/usr/bin/env python3
"""
Enhanced Error Rates and Latency Metrics Query for pbx-web and whisper-stt

This script collects error rates and latency metrics for pbx-web and whisper-stt
covering the 30-day window from 2026-07-07 to 2026-08-06.

Features enhanced deployment data reading and application log timing extraction.
"""

import json
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional
import statistics

# Configuration
ANALYSIS_PERIOD = {
    "start": "2026-07-07T00:00:00Z",
    "end": "2026-08-06T23:59:59Z",
    "days": 30
}

SERVICES = ["pbx-web", "whisper-stt"]

RESEARCH_DIR = Path("/home/coding/aide-de-camp/research")
OUTPUT_DIR = Path("/home/coding/aide-de-camp/data")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


class EnhancedErrorLatencyMetricsCollector:
    """Enhanced collector for error rates and latency metrics."""

    def __init__(self, service: str):
        self.service = service
        self.service_dir = RESEARCH_DIR / f"{service}-30days"
        self.metrics = {
            "service": service,
            "analysis_period": ANALYSIS_PERIOD,
            "error_metrics": {},
            "latency_metrics": {},
            "data_gaps": [],
            "collection_timestamp": datetime.now().isoformat()
        }

    def collect_pod_logs_analysis(self) -> Dict[str, Any]:
        """Collect error metrics from pod log analysis files."""
        pod_logs_dir = self.service_dir / "pod-logs"

        if not pod_logs_dir.exists():
            self.metrics["data_gaps"].append(f"pod-logs directory not found")
            return {}

        error_metrics = {
            "total_pods_analyzed": 0,
            "pods_with_errors": 0,
            "pods_with_oom_kills": 0,
            "total_error_count": 0,
            "total_oom_kill_count": 0,
            "error_samples": [],
            "oom_kill_samples": [],
            "pods_details": [],
            "performance_samples": []
        }

        # Find all analysis files
        analysis_files = list(pod_logs_dir.glob("*-analysis.json"))

        for analysis_file in analysis_files:
            try:
                with open(analysis_file, 'r') as f:
                    analysis_data = json.load(f)

                pod_name = analysis_file.stem.replace("-analysis", "")
                patterns = analysis_data.get("patterns", {})

                error_count = patterns.get("error", {}).get("count", 0)
                oom_kill_count = patterns.get("oom_kill", {}).get("count", 0)
                performance_count = patterns.get("performance", {}).get("count", 0)

                error_samples = patterns.get("error", {}).get("samples", [])
                oom_kill_samples = patterns.get("oom_kill", {}).get("samples", [])
                performance_samples = patterns.get("performance", {}).get("samples", [])

                pod_detail = {
                    "pod_name": pod_name,
                    "error_count": error_count,
                    "oom_kill_count": oom_kill_count,
                    "performance_count": performance_count,
                    "error_samples": error_samples[:3],
                    "oom_kill_samples": oom_kill_samples[:3],
                    "performance_samples": performance_samples[:3]
                }

                error_metrics["pods_details"].append(pod_detail)
                error_metrics["total_pods_analyzed"] += 1

                if error_count > 0:
                    error_metrics["pods_with_errors"] += 1
                    error_metrics["total_error_count"] += error_count
                    error_metrics["error_samples"].extend(error_samples[:2])

                if oom_kill_count > 0:
                    error_metrics["pods_with_oom_kills"] += 1
                    error_metrics["total_oom_kill_count"] += oom_kill_count
                    error_metrics["oom_kill_samples"].extend(oom_kill_samples[:2])

                # Collect performance samples for latency analysis
                if performance_samples:
                    error_metrics["performance_samples"].extend(performance_samples)

            except Exception as e:
                self.metrics["data_gaps"].append(f"Failed to read {analysis_file}: {e}")

        # Calculate error rates
        if error_metrics["total_pods_analyzed"] > 0:
            error_metrics["error_rate_per_pod"] = (
                error_metrics["total_error_count"] / error_metrics["total_pods_analyzed"]
            )
            error_metrics["oom_kill_rate_per_pod"] = (
                error_metrics["total_oom_kill_count"] / error_metrics["total_pods_analyzed"]
            )
        else:
            error_metrics["error_rate_per_pod"] = 0.0
            error_metrics["oom_kill_rate_per_pod"] = 0.0

        return error_metrics

    def collect_nginx_metrics(self) -> Dict[str, Any]:
        """Collect HTTP error rates from nginx logs."""
        pod_logs_dir = self.service_dir / "pod-logs"

        nginx_metrics = {
            "http_5xx_errors": 0,
            "http_4xx_errors": 0,
            "http_total_requests": 0,
            "response_times": [],
            "error_details": [],
            "log_file_found": False,
            "log_file_size": 0,
            "log_lines_analyzed": 0
        }

        # Look for nginx log files
        nginx_logs = list(pod_logs_dir.glob("*nginx*.log"))

        if not nginx_logs:
            self.metrics["data_gaps"].append("No nginx log files found")
            return nginx_metrics

        for nginx_log in nginx_logs:
            try:
                file_size = nginx_log.stat().st_size
                nginx_metrics["log_file_found"] = True
                nginx_metrics["log_file_size"] = file_size

                with open(nginx_log, 'r') as f:
                    lines = f.readlines()
                    nginx_metrics["log_lines_analyzed"] = len(lines)

                for line in lines:
                    # Parse nginx log format for HTTP status codes
                    status_match = re.search(r'"\w+ [^\s]+ HTTP/\d\.\d" (\d+)', line)
                    if status_match:
                        status_code = int(status_match.group(1))
                        nginx_metrics["http_total_requests"] += 1

                        if status_code >= 500:
                            nginx_metrics["http_5xx_errors"] += 1
                            nginx_metrics["error_details"].append({
                                "status": status_code,
                                "line": line.strip()[:200]
                            })
                        elif status_code >= 400:
                            nginx_metrics["http_4xx_errors"] += 1

            except Exception as e:
                self.metrics["data_gaps"].append(f"Failed to analyze {nginx_log}: {e}")

        # Calculate HTTP error rates
        if nginx_metrics["http_total_requests"] > 0:
            nginx_metrics["http_5xx_error_rate"] = (
                nginx_metrics["http_5xx_errors"] / nginx_metrics["http_total_requests"]
            )
            nginx_metrics["http_4xx_error_rate"] = (
                nginx_metrics["http_4xx_errors"] / nginx_metrics["http_total_requests"]
            )
        else:
            nginx_metrics["http_5xx_error_rate"] = 0.0
            nginx_metrics["http_4xx_error_rate"] = 0.0

        return nginx_metrics

    def collect_deployment_metrics(self) -> Dict[str, Any]:
        """Collect deployment timing and success metrics."""
        deployment_metrics = {
            "total_deployments": 0,
            "successful_deployments": 0,
            "failed_deployments": 0,
            "deployment_times": [],
            "deployment_error_rate": 0.0,
            "deployment_found": False,
            "deployment_events": []
        }

        # Try multiple possible locations for deployment data
        deployment_file_locations = [
            self.service_dir / "deployments-30days.json",
            RESEARCH_DIR / f"{self.service}-deployments-30days.json",
            self.service_dir / "k8s-events" / f"{self.service}-deployments.json"
        ]

        deployment_file = None
        for location in deployment_file_locations:
            if location.exists():
                deployment_file = location
                break

        if not deployment_file:
            self.metrics["data_gaps"].append("Deployment data file not found in any expected location")
            return deployment_metrics

        try:
            with open(deployment_file, 'r') as f:
                deployment_data = json.load(f)

            deployment_metrics["deployment_found"] = True

            # Handle different deployment data formats
            deployments = []

            if isinstance(deployment_data, dict):
                # Check for nested structure
                if "deployments" in deployment_data:
                    deployments_data = deployment_data["deployments"]

                    # Handle service-specific deployments
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
            elif isinstance(deployment_data, list):
                deployments = deployment_data

            # Process deployment events
            for deployment in deployments:
                if not isinstance(deployment, dict):
                    continue

                deployment_metrics["total_deployments"] += 1
                deployment_metrics["deployment_events"].append(deployment)

                # Check deployment status
                success = deployment.get("success", True)
                if deployment.get("status") == "failed" or not success:
                    deployment_metrics["failed_deployments"] += 1
                else:
                    deployment_metrics["successful_deployments"] += 1

                # Extract timing if available
                duration = deployment.get("deployment_duration_seconds")
                if duration and isinstance(duration, (int, float)) and duration > 0:
                    deployment_metrics["deployment_times"].append(duration)

            # Calculate deployment error rate
            if deployment_metrics["total_deployments"] > 0:
                deployment_metrics["deployment_error_rate"] = (
                    deployment_metrics["failed_deployments"] / deployment_metrics["total_deployments"]
                )

            # Calculate deployment timing statistics
            if deployment_metrics["deployment_times"]:
                deployment_metrics["timing_stats"] = self._calculate_percentiles(
                    deployment_metrics["deployment_times"]
                )

        except Exception as e:
            self.metrics["data_gaps"].append(f"Failed to read deployments file: {e}")

        return deployment_metrics

    def extract_application_timing(self) -> Dict[str, Any]:
        """Extract timing information from application logs."""
        pod_logs_dir = self.service_dir / "pod-logs"

        timing_metrics = {
            "application_timing_samples": [],
            "timestamp_deltas": [],
            "processing_durations": [],
            "log_files_analyzed": 0,
            "total_timing_samples": 0
        }

        # Look for application log files (non-nginx, non-analysis)
        app_logs = []
        for log_file in pod_logs_dir.glob("*.log"):
            if "nginx" not in log_file.name and "analysis" not in log_file.name:
                app_logs.append(log_file)

        if not app_logs:
            self.metrics["data_gaps"].append("No application log files found for timing extraction")
            return timing_metrics

        for app_log in app_logs:
            try:
                timing_metrics["log_files_analyzed"] += 1

                with open(app_log, 'r') as f:
                    lines = f.readlines()

                # Extract timestamps and processing information
                timestamps = []
                for line in lines:
                    # Extract ISO timestamps
                    ts_match = re.match(r'^(\d{4}-\d{2}-\d{2}T[\d:T\-\.]+)', line)
                    if ts_match:
                        try:
                            timestamps.append(ts_match.group(1))
                        except:
                            pass

                    # Look for timing-related keywords
                    timing_keywords = ['duration', 'elapsed', 'processing', 'completed', 'finished', 'done in']
                    if any(keyword in line.lower() for keyword in timing_keywords):
                        timing_metrics["application_timing_samples"].append(line.strip()[:200])

                # Calculate timestamp deltas as proxy for processing time
                if len(timestamps) > 1:
                    for i in range(1, len(timestamps)):
                        try:
                            ts1 = datetime.fromisoformat(timestamps[i-1].replace('Z', '+00:00'))
                            ts2 = datetime.fromisoformat(timestamps[i].replace('Z', '+00:00'))
                            delta = (ts2 - ts1).total_seconds()

                            # Only include reasonable deltas (0-60 seconds)
                            if 0 < delta < 60:
                                timing_metrics["timestamp_deltas"].append(delta)
                        except:
                            pass

                timing_metrics["total_timing_samples"] += len(timing_metrics["application_timing_samples"])

            except Exception as e:
                self.metrics["data_gaps"].append(f"Failed to analyze {app_log}: {e}")

        # Calculate timing statistics from timestamp deltas
        if timing_metrics["timestamp_deltas"]:
            timing_metrics["delta_stats"] = self._calculate_percentiles(timing_metrics["timestamp_deltas"])

        return timing_metrics

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

    def collect_all_metrics(self) -> Dict[str, Any]:
        """Collect all error and latency metrics for the service."""
        print(f"\n{'='*60}")
        print(f"Collecting metrics for: {self.service}")
        print(f"{'='*60}")

        # Collect error metrics
        print("Collecting pod logs analysis...")
        self.metrics["error_metrics"]["pod_logs"] = self.collect_pod_logs_analysis()

        print("Collecting nginx metrics...")
        self.metrics["error_metrics"]["nginx"] = self.collect_nginx_metrics()

        print("Collecting deployment metrics...")
        self.metrics["error_metrics"]["deployments"] = self.collect_deployment_metrics()

        # Calculate overall error rates
        self._calculate_overall_error_rates()

        # Collect latency metrics
        print("Extracting application timing data...")
        app_timing = self.extract_application_timing()
        self.metrics["latency_metrics"]["application"] = app_timing

        self._collect_latency_metrics()

        return self.metrics

    def _calculate_overall_error_rates(self):
        """Calculate overall error rates across all sources."""
        error_metrics = self.metrics["error_metrics"]

        # Get error counts from pod logs
        pod_errors = error_metrics.get("pod_logs", {}).get("total_error_count", 0)
        pod_oom = error_metrics.get("pod_logs", {}).get("total_oom_kill_count", 0)

        # Get HTTP errors from nginx
        http_5xx = error_metrics.get("nginx", {}).get("http_5xx_errors", 0)
        http_4xx = error_metrics.get("nginx", {}).get("http_4xx_errors", 0)

        # Get deployment errors
        deploy_errors = error_metrics.get("deployments", {}).get("failed_deployments", 0)

        # Calculate daily rates (30-day period)
        days = ANALYSIS_PERIOD["days"]

        overall_error_metrics = {
            "total_errors_all_sources": pod_errors + pod_oom + http_5xx + http_4xx + deploy_errors,
            "error_rate_per_day": (pod_errors + pod_oom + http_5xx + http_4xx + deploy_errors) / days,
            "pod_errors_per_day": pod_errors / days,
            "oom_kills_per_day": pod_oom / days,
            "http_5xx_per_day": http_5xx / days,
            "http_4xx_per_day": http_4xx / days,
            "deployment_errors_per_day": deploy_errors / days,
            "deployment_success_rate": 0.0
        }

        # Calculate deployment success rate
        total_deploys = error_metrics.get("deployments", {}).get("total_deployments", 0)
        successful_deploys = error_metrics.get("deployments", {}).get("successful_deployments", 0)

        if total_deploys > 0:
            overall_error_metrics["deployment_success_rate"] = successful_deploys / total_deploys

        self.metrics["error_metrics"]["overall"] = overall_error_metrics

    def _collect_latency_metrics(self):
        """Collect latency metrics from all available sources."""
        latency_metrics = {}

        # Deployment times
        deployment_data = self.metrics["error_metrics"].get("deployments", {})
        if deployment_data.get("deployment_times"):
            latency_metrics["deployment_durations"] = deployment_data.get("timing_stats", {})

        # Application timing from logs
        app_timing = self.metrics.get("latency_metrics", {}).get("application", {})
        if app_timing.get("timestamp_deltas"):
            latency_metrics["application_timestamp_deltas"] = app_timing.get("delta_stats", {})
            latency_metrics["application_timing_samples"] = app_timing.get("application_timing_samples", [])[:10]

        # Extract performance-related timing from pod logs
        pod_data = self.metrics["error_metrics"].get("pod_logs", {})
        pod_performance_samples = pod_data.get("performance_samples", [])

        if pod_performance_samples:
            # Try to extract numeric timing values from performance samples
            timing_values = []
            for sample in pod_performance_samples:
                # Look for patterns like "Slow query: 5.2s", "Request timeout: 30000ms"
                time_matches = re.findall(r'(\d+(?:\.\d+)?)\s*(ms|s|m)?', str(sample))
                for value, unit in time_matches:
                    try:
                        time_val = float(value)
                        # Convert to milliseconds
                        if unit == 's':
                            time_val *= 1000
                        elif unit == 'm':
                            time_val *= 60000

                        if 0 < time_val < 3600000:  # Sanity check (0-1 hour)
                            timing_values.append(time_val)
                    except ValueError:
                        pass

            if timing_values:
                latency_metrics["pod_performance_times"] = self._calculate_percentiles(timing_values)

        self.metrics["latency_metrics"].update(latency_metrics)


def main():
    """Main execution for enhanced error and latency metrics collection."""
    print("="*60)
    print("Enhanced Error Rates and Latency Metrics Query")
    print("="*60)
    print(f"Analysis period: {ANALYSIS_PERIOD['start']} to {ANALYSIS_PERIOD['end']}")
    print(f"Services: {', '.join(SERVICES)}")

    all_results = {
        "collection_metadata": {
            "timestamp": datetime.now().isoformat(),
            "analysis_period": ANALYSIS_PERIOD,
            "services_analyzed": SERVICES,
            "enhanced_collection": True
        },
        "services": {}
    }

    for service in SERVICES:
        collector = EnhancedErrorLatencyMetricsCollector(service)
        service_metrics = collector.collect_all_metrics()
        all_results["services"][service] = service_metrics

        # Print summary
        print(f"\n{service.upper()} Summary:")
        print(f"  Total errors (all sources): {service_metrics['error_metrics']['overall']['total_errors_all_sources']}")
        print(f"  Error rate per day: {service_metrics['error_metrics']['overall']['error_rate_per_day']:.2f}")
        print(f"  HTTP 5xx errors: {service_metrics['error_metrics']['nginx']['http_5xx_errors']}")
        print(f"  HTTP 4xx errors: {service_metrics['error_metrics']['nginx']['http_4xx_errors']}")
        print(f"  Deployment success rate: {service_metrics['error_metrics']['overall']['deployment_success_rate']:.1%}")
        print(f"  Data gaps: {len(service_metrics['data_gaps'])}")
        if service_metrics['data_gaps']:
            print(f"  Gap examples: {service_metrics['data_gaps'][:2]}")

    # Save results
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = OUTPUT_DIR / f"error_latency_metrics_30d_enhanced_{timestamp}.json"

    with open(output_file, 'w') as f:
        json.dump(all_results, f, indent=2, default=str)

    print(f"\n{'='*60}")
    print(f"✓ Results saved to: {output_file}")
    print(f"{'='*60}")

    # Print comparative summary
    print("\nComparative Error Summary:")
    print(f"{'Service':<15} {'Total Errors':>15} {'Error Rate/Day':>15} {'HTTP 5xx':>10} {'HTTP 4xx':>10} {'Deploy Success':>12}")
    print("-" * 80)

    for service in SERVICES:
        service_data = all_results["services"][service]
        overall = service_data["error_metrics"]["overall"]
        nginx = service_data["error_metrics"]["nginx"]

        print(f"{service:<15} {overall['total_errors_all_sources']:>15} "
              f"{overall['error_rate_per_day']:>15.2f} "
              f"{nginx['http_5xx_errors']:>10} "
              f"{nginx['http_4xx_errors']:>10} "
              f"{overall['deployment_success_rate']:>12.1%}")

    print("\nLatency Metrics Summary:")
    for service in SERVICES:
        service_data = all_results["services"][service]
        latency = service_data["latency_metrics"]

        print(f"\n{service.upper()}:")

        if "deployment_durations" in latency:
            stats = latency["deployment_durations"]
            print(f"  Deployment Duration: mean={stats.get('mean', 0):.1f}s, p95={stats.get('p95', 0):.1f}s")
        else:
            print(f"  Deployment Duration: Not available")

        if "application_timestamp_deltas" in latency:
            stats = latency["application_timestamp_deltas"]
            print(f"  App Log Deltas: mean={stats.get('mean', 0):.3f}s, p95={stats.get('p95', 0):.3f}s")
        else:
            print(f"  App Log Deltas: Not available")

        if "pod_performance_times" in latency:
            stats = latency["pod_performance_times"]
            print(f"  Pod Performance: mean={stats.get('mean', 0):.0f}ms, p95={stats.get('p95', 0):.0f}ms")
        else:
            print(f"  Pod Performance: Not available")

    print(f"\nData Gaps Summary:")
    for service in SERVICES:
        service_data = all_results["services"][service]
        gaps = service_data.get("data_gaps", [])
        print(f"  {service}: {len(gaps)} gaps")
        for gap in gaps[:3]:
            print(f"    - {gap}")

    return all_results


if __name__ == "__main__":
    main()