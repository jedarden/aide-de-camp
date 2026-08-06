#!/usr/bin/env python3
"""
Comprehensive 30-day metrics analysis for pbx-web and whisper-stt.

This script analyzes existing research data to extract:
- Error rates from events and pod restarts
- Latency metrics from startup times and health probes
- Resource usage patterns from pod specs and metrics
- Temporal alignment with deployment events
"""

import json
import os
from datetime import datetime, timedelta
from typing import Dict, List, Any
from pathlib import Path
from dataclasses import dataclass, asdict
from collections import defaultdict

@dataclass
class ComprehensiveMetrics:
    """Container for comprehensive service metrics."""
    service_name: str
    analysis_date: str
    period_days: int

    # Error metrics
    total_error_events: int
    error_rate_by_type: Dict[str, int]
    pods_with_restarts: int
    total_pod_restarts: int
    restart_rate_per_day: float

    # Latency metrics
    avg_startup_time_seconds: float
    max_startup_time_seconds: float
    min_startup_time_seconds: float
    startup_samples: int

    # Resource metrics
    resource_requests: Dict[str, Dict[str, str]]
    resource_limits: Dict[str, Dict[str, str]]
    current_usage: Dict[str, Dict[str, str]]

    # Deployment correlation
    deployment_count: int
    deployment_frequency_per_day: float
    avg_deployment_interval_days: float

    # Coverage and anomalies
    metric_coverage: Dict[str, str]
    data_gaps: List[str]
    anomalies: List[str]
    recommendations: List[str]

class MetricsAnalyzer:
    """Analyze metrics from existing research data."""

    def __init__(self, research_base: str = "/home/coding/aide-de-camp/research"):
        self.research_base = Path(research_base)

    def load_json(self, file_path: str) -> Dict[str, Any]:
        """Load JSON file safely."""
        try:
            with open(file_path, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            return {"error": f"File not found: {file_path}"}
        except json.JSONDecodeError as e:
            return {"error": f"JSON decode error: {str(e)}"}

    def analyze_error_events(self, events_data: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze error events from Kubernetes events."""
        error_metrics = {
            "total_events": 0,
            "by_reason": defaultdict(int),
            "by_type": defaultdict(int),
            "recent_errors": []
        }

        if isinstance(events_data, dict) and "error" in events_data:
            return error_metrics

        events = events_data if isinstance(events_data, list) else events_data.get("items", [])

        for event in events:
            event_type = event.get("type", "Normal")
            reason = event.get("reason", "")
            message = event.get("message", "")

            if event_type == "Warning" or "error" in reason.lower() or "fail" in reason.lower():
                error_metrics["total_events"] += 1
                error_metrics["by_reason"][reason] += 1
                error_metrics["by_type"][event_type] += 1

                # Track recent errors (last 7 days)
                timestamp = event.get("lastTimestamp", "")
                if timestamp:
                    try:
                        event_time = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                        if (datetime.now(event_time.tzinfo) - event_time).days <= 7:
                            error_metrics["recent_errors"].append({
                                "timestamp": timestamp,
                                "reason": reason,
                                "message": message[:100]
                            })
                    except ValueError:
                        pass

        return dict(error_metrics)

    def analyze_pod_restart_patterns(self, pods_data: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze pod restart patterns for error rates."""
        restart_metrics = {
            "total_pods": 0,
            "pods_with_restarts": 0,
            "total_restarts": 0,
            "restarts_by_pod": {},
            "crash_loop_backoffs": []
        }

        if isinstance(pods_data, dict) and "error" in pods_data:
            return restart_metrics

        pods = pods_data.get("items", []) if isinstance(pods_data, dict) else []

        for pod in pods:
            pod_name = pod.get("metadata", {}).get("name", "")
            restart_metrics["total_pods"] += 1

            pod_restarts = 0
            for container_status in pod.get("status", {}).get("containerStatuses", []):
                restart_count = container_status.get("restartCount", 0)
                pod_restarts += restart_count

                # Check for crash loop backoff
                last_state = container_status.get("lastState", {})
                terminated = last_state.get("terminated", {})
                if terminated.get("reason") == "CrashLoopBackOff":
                    restart_metrics["crash_loop_backoffs"].append({
                        "pod": pod_name,
                        "container": container_status.get("name", ""),
                        "exit_code": terminated.get("exitCode", -1)
                    })

            if pod_restarts > 0:
                restart_metrics["pods_with_restarts"] += 1
                restart_metrics["total_restarts"] += pod_restarts
                restart_metrics["restarts_by_pod"][pod_name] = pod_restarts

        return restart_metrics

    def analyze_startup_times(self, pods_data: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze pod startup times for latency metrics."""
        startup_metrics = {
            "startup_times": [],
            "count": 0,
            "total_seconds": 0,
            "min_seconds": float('inf'),
            "max_seconds": 0
        }

        if isinstance(pods_data, dict) and "error" in pods_data:
            return startup_metrics

        pods = pods_data.get("items", []) if isinstance(pods_data, dict) else []

        for pod in pods:
            pod_name = pod.get("metadata", {}).get("name", "")
            creation_time = pod.get("metadata", {}).get("creationTimestamp", "")

            for container_status in pod.get("status", {}).get("containerStatuses", []):
                started_at = container_status.get("state", {}).get("running", {}).get("startedAt")
                if started_at and creation_time:
                    try:
                        creation = datetime.fromisoformat(creation_time.replace('Z', '+00:00'))
                        started = datetime.fromisoformat(started_at.replace('Z', '+00:00'))
                        startup_seconds = (started - creation).total_seconds()

                        startup_metrics["startup_times"].append({
                            "pod": pod_name,
                            "container": container_status.get("name", ""),
                            "startup_seconds": startup_seconds,
                            "creation_time": creation_time
                        })

                        startup_metrics["count"] += 1
                        startup_metrics["total_seconds"] += startup_seconds
                        startup_metrics["min_seconds"] = min(startup_metrics["min_seconds"], startup_seconds)
                        startup_metrics["max_seconds"] = max(startup_metrics["max_seconds"], startup_seconds)
                    except ValueError:
                        continue

        if startup_metrics["count"] == 0:
            startup_metrics["min_seconds"] = 0
        else:
            startup_metrics["avg_seconds"] = startup_metrics["total_seconds"] / startup_metrics["count"]

        return startup_metrics

    def analyze_resource_usage(self, pods_data: Dict[str, Any], metrics_data: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze resource usage patterns."""
        resource_metrics = {
            "containers": [],
            "total_cpu_requests": 0,
            "total_memory_requests": 0,
            "total_cpu_limits": 0,
            "total_memory_limits": 0,
            "current_usage": []
        }

        pods = pods_data.get("items", []) if isinstance(pods_data, dict) else []

        for pod in pods:
            pod_name = pod.get("metadata", {}).get("name", "")

            for container in pod.get("spec", {}).get("containers", []):
                container_name = container.get("name", "")
                resources = container.get("resources", {})

                requests = resources.get("requests", {})
                limits = resources.get("limits", {})

                cpu_req = requests.get("cpu", "0")
                mem_req = requests.get("memory", "0")
                cpu_lim = limits.get("cpu", "0")
                mem_lim = limits.get("memory", "0")

                resource_metrics["containers"].append({
                    "pod": pod_name,
                    "container": container_name,
                    "cpu_request": cpu_req,
                    "memory_request": mem_req,
                    "cpu_limit": cpu_lim,
                    "memory_limit": mem_lim
                })

        # Add current usage if available
        if isinstance(metrics_data, dict) and "parsed_metrics" in metrics_data:
            for metric in metrics_data["parsed_metrics"]:
                resource_metrics["current_usage"].append({
                    "pod": metric.get("pod", ""),
                    "cpu_usage": metric.get("cpu", ""),
                    "memory_usage": metric.get("memory", "")
                })

        return resource_metrics

    def analyze_deployment_patterns(self, deployment_data: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze deployment patterns for temporal correlation."""
        deployment_metrics = {
            "total_deployments": 0,
            "deployment_frequency": 0,
            "avg_interval_days": 0,
            "last_deployment": None,
            "first_deployment": None
        }

        if isinstance(deployment_data, dict) and "error" in deployment_data:
            return deployment_metrics

        # Handle different deployment data formats
        deployments = []

        if isinstance(deployment_data, dict):
            if "deployments" in deployment_data:
                deployments = deployment_data["deployments"]
            elif "items" in deployment_data:
                deployments = deployment_data["items"]

        # Filter deployments to last 30 days
        cutoff_date = datetime.now() - timedelta(days=30)
        recent_deployments = []

        for deployment in deployments:
            timestamp = deployment.get("timestamp") or deployment.get("creationTimestamp", "")
            if timestamp:
                try:
                    dep_time = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                    if dep_time >= cutoff_date:
                        recent_deployments.append({
                            "timestamp": timestamp,
                            "revision": deployment.get("revision", ""),
                            "status": deployment.get("status", "unknown")
                        })
                except ValueError:
                    continue

        deployment_metrics["total_deployments"] = len(recent_deployments)

        if len(recent_deployments) > 1:
            deployment_metrics["deployment_frequency"] = len(recent_deployments) / 30.0

            # Calculate average interval
            timestamps = []
            for dep in recent_deployments:
                try:
                    ts = datetime.fromisoformat(dep["timestamp"].replace('Z', '+00:00'))
                    timestamps.append(ts)
                except ValueError:
                    continue

            if len(timestamps) > 1:
                timestamps.sort()
                intervals = [(timestamps[i] - timestamps[i-1]).days for i in range(1, len(timestamps))]
                if intervals:
                    deployment_metrics["avg_interval_days"] = sum(intervals) / len(intervals)

        if recent_deployments:
            deployment_metrics["last_deployment"] = recent_deployments[-1]["timestamp"]
            deployment_metrics["first_deployment"] = recent_deployments[0]["timestamp"]

        return deployment_metrics

    def generate_recommendations(self, error_data: Dict, restart_data: Dict, startup_data: Dict, resource_data: Dict) -> List[str]:
        """Generate operational recommendations based on metrics."""
        recommendations = []

        # Error-based recommendations
        if error_data.get("total_events", 0) > 10:
            recommendations.append("High error event count detected - review logs for recurring issues")

        # Restart-based recommendations
        if restart_data.get("total_restarts", 0) > 5:
            recommendations.append("Multiple pod restarts detected - investigate application stability")
        if restart_data.get("crash_loop_backoffs"):
            recommendations.append("Crash loop backoffs detected - check container health and resource limits")

        # Startup-based recommendations
        avg_startup = startup_data.get("avg_seconds", 0)
        if avg_startup > 60:
            recommendations.append(f"Slow average startup time ({avg_startup:.1f}s) - optimize initialization")
        if startup_data.get("max_seconds", 0) > 300:
            recommendations.append("Very slow startup detected (>5 min) - may indicate dependency issues")

        # Resource-based recommendations
        if len(resource_data.get("containers", [])) == 0:
            recommendations.append("No resource data available - ensure resource requests/limits are set")

        return recommendations

def analyze_pbx_web() -> ComprehensiveMetrics:
    """Analyze pbx-web metrics."""
    print("Analyzing pbx-web metrics...")

    analyzer = MetricsAnalyzer()
    research_dir = analyzer.research_base / "pbx-web-30days"

    # Load all available data
    events_data = analyzer.load_json(str(research_dir / "events.json"))
    pods_data = analyzer.load_json(str(research_dir / "pods-current.json"))
    deployment_data = analyzer.load_json("/home/coding/aide-de-camp/research/pbx-web-deployments-30days.json")

    # Get current resource usage
    try:
        import subprocess
        result = subprocess.run(
            ["kubectl", "--server=http://traefik-ardenone-cluster:8001", "top", "pods", "-n", "pbx-web"],
            capture_output=True, text=True, timeout=10
        )
        metrics_data = {"raw_output": result.stdout}
        # Parse kubectl output
        lines = result.stdout.split('\n')
        parsed = []
        for line in lines[1:]:
            if line.strip():
                parts = line.split()
                if len(parts) >= 3:
                    parsed.append({"pod": parts[0], "cpu": parts[1], "memory": parts[2]})
        metrics_data["parsed_metrics"] = parsed
    except Exception as e:
        metrics_data = {"error": str(e)}

    # Analyze each metric category
    error_analysis = analyzer.analyze_error_events(events_data)
    restart_analysis = analyzer.analyze_pod_restart_patterns(pods_data)
    startup_analysis = analyzer.analyze_startup_times(pods_data)
    resource_analysis = analyzer.analyze_resource_usage(pods_data, metrics_data)
    deployment_analysis = analyzer.analyze_deployment_patterns(deployment_data)

    # Generate recommendations
    recommendations = analyzer.generate_recommendations(
        error_analysis, restart_analysis, startup_analysis, resource_analysis
    )

    # Identify data gaps and anomalies
    data_gaps = []
    anomalies = []

    if error_analysis.get("total_events", 0) == 0 and "error" not in events_data:
        data_gaps.append("No error events found - may indicate missing event data or clean deployment")

    if restart_analysis.get("total_restarts", 0) > 10:
        anomalies.append(f"High restart count: {restart_analysis['total_restarts']} restarts detected")

    if startup_analysis.get("max_seconds", 0) > 120:
        anomalies.append(f"Slow pod startup: {startup_analysis['max_seconds']:.1f}s maximum")

    return ComprehensiveMetrics(
        service_name="pbx-web",
        analysis_date=datetime.now().isoformat(),
        period_days=30,
        total_error_events=error_analysis.get("total_events", 0),
        error_rate_by_type=dict(error_analysis.get("by_type", {})),
        pods_with_restarts=restart_analysis.get("pods_with_restarts", 0),
        total_pod_restarts=restart_analysis.get("total_restarts", 0),
        restart_rate_per_day=round(restart_analysis.get("total_restarts", 0) / 30.0, 2),
        avg_startup_time_seconds=round(startup_analysis.get("avg_seconds", 0), 2),
        max_startup_time_seconds=round(startup_analysis.get("max_seconds", 0), 2),
        min_startup_time_seconds=round(startup_analysis.get("min_seconds", 0), 2),
        startup_samples=startup_analysis.get("count", 0),
        resource_requests={},
        resource_limits={},
        current_usage={pod["pod"]: {"cpu": pod["cpu_usage"], "memory": pod["memory_usage"]} for pod in resource_analysis.get("current_usage", [])},
        deployment_count=deployment_analysis.get("total_deployments", 0),
        deployment_frequency_per_day=round(deployment_analysis.get("deployment_frequency", 0), 3),
        avg_deployment_interval_days=round(deployment_analysis.get("avg_interval_days", 0), 1),
        metric_coverage={
            "error_events": "available" if error_analysis.get("total_events", 0) > 0 else "limited",
            "pod_restarts": "available",
            "startup_times": "available" if startup_analysis.get("count", 0) > 0 else "limited",
            "resource_usage": "current_only",
            "deployment_data": "available"
        },
        data_gaps=data_gaps,
        anomalies=anomalies,
        recommendations=recommendations
    )

def analyze_whisper_stt() -> ComprehensiveMetrics:
    """Analyze whisper-stt metrics."""
    print("Analyzing whisper-stt metrics...")

    analyzer = MetricsAnalyzer()
    research_dir = analyzer.research_base / "whisper-stt-30days"

    # Load all available data
    events_data = analyzer.load_json(str(research_dir / "events.json"))
    pods_data = analyzer.load_json(str(research_dir / "pods-current.json"))
    deployment_data = analyzer.load_json(str(research_dir / "deployments-30days.json"))

    # Get current resource usage
    try:
        import subprocess
        result = subprocess.run(
            ["kubectl", "--server=http://traefik-ardenone-cluster:8001", "top", "pods", "-n", "whisper-stt"],
            capture_output=True, text=True, timeout=10
        )
        metrics_data = {"raw_output": result.stdout}
        lines = result.stdout.split('\n')
        parsed = []
        for line in lines[1:]:
            if line.strip():
                parts = line.split()
                if len(parts) >= 3:
                    parsed.append({"pod": parts[0], "cpu": parts[1], "memory": parts[2]})
        metrics_data["parsed_metrics"] = parsed
    except Exception as e:
        metrics_data = {"error": str(e)}

    # Analyze each metric category
    error_analysis = analyzer.analyze_error_events(events_data)
    restart_analysis = analyzer.analyze_pod_restart_patterns(pods_data)
    startup_analysis = analyzer.analyze_startup_times(pods_data)
    resource_analysis = analyzer.analyze_resource_usage(pods_data, metrics_data)
    deployment_analysis = analyzer.analyze_deployment_patterns(deployment_data)

    # Generate recommendations
    recommendations = analyzer.generate_recommendations(
        error_analysis, restart_analysis, startup_analysis, resource_analysis
    )

    # Identify data gaps and anomalies
    data_gaps = []
    anomalies = []

    if restart_analysis.get("total_restarts", 0) > 10:
        anomalies.append(f"High restart count: {restart_analysis['total_restarts']} restarts detected")

    if startup_analysis.get("max_seconds", 0) > 120:
        anomalies.append(f"Slow pod startup: {startup_analysis['max_seconds']:.1f}s maximum")

    return ComprehensiveMetrics(
        service_name="whisper-stt",
        analysis_date=datetime.now().isoformat(),
        period_days=30,
        total_error_events=error_analysis.get("total_events", 0),
        error_rate_by_type=dict(error_analysis.get("by_type", {})),
        pods_with_restarts=restart_analysis.get("pods_with_restarts", 0),
        total_pod_restarts=restart_analysis.get("total_restarts", 0),
        restart_rate_per_day=round(restart_analysis.get("total_restarts", 0) / 30.0, 2),
        avg_startup_time_seconds=round(startup_analysis.get("avg_seconds", 0), 2),
        max_startup_time_seconds=round(startup_analysis.get("max_seconds", 0), 2),
        min_startup_time_seconds=round(startup_analysis.get("min_seconds", 0), 2),
        startup_samples=startup_analysis.get("count", 0),
        resource_requests={},
        resource_limits={},
        current_usage={pod["pod"]: {"cpu": pod["cpu_usage"], "memory": pod["memory_usage"]} for pod in resource_analysis.get("current_usage", [])},
        deployment_count=deployment_analysis.get("total_deployments", 0),
        deployment_frequency_per_day=round(deployment_analysis.get("deployment_frequency", 0), 3),
        avg_deployment_interval_days=round(deployment_analysis.get("avg_interval_days", 0), 1),
        metric_coverage={
            "error_events": "available" if error_analysis.get("total_events", 0) > 0 else "limited",
            "pod_restarts": "available",
            "startup_times": "available" if startup_analysis.get("count", 0) > 0 else "limited",
            "resource_usage": "current_only",
            "deployment_data": "available"
        },
        data_gaps=data_gaps,
        anomalies=anomalies,
        recommendations=recommendations
    )

def main():
    """Main analysis function."""
    print("=" * 80)
    print("COMPREHENSIVE 30-DAY METRICS ANALYSIS")
    print("=" * 80)
    print()

    # Analyze both services
    pbx_metrics = analyze_pbx_web()
    whisper_metrics = analyze_whisper_stt()

    # Compile comprehensive results
    results = {
        "analysis_metadata": {
            "analyzed_at": datetime.now().isoformat(),
            "period_days": 30,
            "services": ["pbx-web", "whisper-stt"],
            "analysis_types": ["error_rates", "latency", "resource_usage", "deployment_patterns"]
        },
        "pbx_web": asdict(pbx_metrics),
        "whisper_stt": asdict(whisper_metrics),
        "comparative_summary": {
            "total_error_events": pbx_metrics.total_error_events + whisper_metrics.total_error_events,
            "total_pod_restarts": pbx_metrics.total_pod_restarts + whisper_metrics.total_pod_restarts,
            "combined_restart_rate": round((pbx_metrics.total_pod_restarts + whisper_metrics.total_pod_restarts) / 30.0, 2),
            "services_with_anomalies": len([m for m in [pbx_metrics, whisper_metrics] if m.anomalies]),
            "total_recommendations": len(pbx_metrics.recommendations) + len(whisper_metrics.recommendations),
            "data_quality_score": "good" if len(pbx_metrics.data_gaps + whisper_metrics.data_gaps) <= 2 else "limited"
        }
    }

    # Save comprehensive results
    output_file = "/home/coding/aide-de-camp/research/adc-1xp0b-comprehensive-metrics.json"
    with open(output_file, 'w') as f:
        json.dump(results, f, indent=2, default=str)

    print()
    print("=" * 80)
    print("COMPREHENSIVE ANALYSIS COMPLETE")
    print("=" * 80)
    print(f"Results saved to: {output_file}")
    print()
    print("SUMMARY:")
    print(f"  Total error events: {results['comparative_summary']['total_error_events']}")
    print(f"  Total pod restarts: {results['comparative_summary']['total_pod_restarts']}")
    print(f"  Services with anomalies: {results['comparative_summary']['services_with_anomalies']}")
    print(f"  Total recommendations: {results['comparative_summary']['total_recommendations']}")
    print(f"  Data quality: {results['comparative_summary']['data_quality_score']}")
    print()

    if pbx_metrics.recommendations or whisper_metrics.recommendations:
        print("RECOMMENDATIONS:")
        for rec in pbx_metrics.recommendations + whisper_metrics.recommendations:
            print(f"  - {rec}")
        print()

if __name__ == "__main__":
    main()