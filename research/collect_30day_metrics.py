#!/usr/bin/env python3
"""
Collect comprehensive 30-day metrics for pbx-web and whisper-stt services.

This script collects:
- Error rates from Kubernetes events and pod status
- Latency metrics from pod startup times and health probes
- Resource usage from Kubernetes metrics API
- Temporal alignment with deployment events
"""

import json
import subprocess
import re
import os
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, asdict
from pathlib import Path
import sys

@dataclass
class ServiceMetrics:
    """Container for service metrics."""
    service_name: str
    collection_date: str
    period_days: int

    # Error metrics
    error_rate_events: List[Dict[str, Any]]
    pod_restart_counts: List[Dict[str, Any]]
    crash_loop_backoffs: List[Dict[str, Any]]

    # Latency metrics
    pod_startup_times: List[Dict[str, Any]]
    health_check_failures: List[Dict[str, Any]]

    # Resource metrics
    current_resource_usage: Dict[str, Any]
    resource_requests_vs_limits: Dict[str, Any]

    # Coverage info
    metric_coverage: Dict[str, str]
    data_gaps: List[str]
    anomalies: List[str]

class MetricsCollector:
    """Collects metrics from Kubernetes and VictoriaLogs."""

    def __init__(self, days: int = 30):
        self.days = days
        self.since_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

    def run_kubectl(self, cmd: List[str]) -> str:
        """Run kubectl command and return output."""
        try:
            full_cmd = ["kubectl", "--server=http://traefik-ardenone-cluster:8001"] + cmd
            result = subprocess.run(full_cmd, capture_output=True, text=True, timeout=30)
            if result.returncode != 0:
                print(f"Warning: kubectl command failed: {' '.join(cmd)}", file=sys.stderr)
                return ""
            return result.stdout
        except subprocess.TimeoutExpired:
            print(f"Warning: kubectl command timed out: {' '.join(cmd)}", file=sys.stderr)
            return ""
        except Exception as e:
            print(f"Warning: kubectl command error: {e}", file=sys.stderr)
            return ""

    def collect_error_events(self, namespace: str, service: str) -> List[Dict[str, Any]]:
        """Collect Kubernetes error events for the service."""
        events = []

        # Get events for the namespace with field selector for warnings
        cmd = ["get", "events", "-n", namespace, "--field-selector=type=Warning", "-o", "json"]
        output = self.run_kubectl(cmd)

        if not output:
            return [{"note": "Could not retrieve events from Kubernetes API"}]

        try:
            data = json.loads(output)
            for item in data.get("items", []):
                event_type = item.get("type", "")
                reason = item.get("reason", "")
                message = item.get("message", "")
                timestamp = item.get("lastTimestamp", "")

                # All returned events are warnings, filter by relevance
                involved_obj = item.get("involvedObject", {})
                obj_name = involved_obj.get("name", "")

                # Include if service name appears in event details
                if service.lower() in message.lower() or service.lower() in reason.lower() or service.lower() in obj_name.lower():
                    events.append({
                        "timestamp": timestamp,
                        "type": event_type,
                        "reason": reason,
                        "message": message[:200],  # Truncate long messages
                        "involved_object": {
                            "name": obj_name,
                            "kind": involved_obj.get("kind", ""),
                            "namespace": involved_obj.get("namespace", "")
                        }
                    })
        except json.JSONDecodeError as e:
            events.append({"error": f"Failed to parse events JSON: {str(e)}"})

        return events

    def collect_pod_metrics(self, namespace: str, service: str) -> Dict[str, Any]:
        """Collect pod restart counts and startup times."""
        pod_metrics = {
            "pods_analyzed": 0,
            "total_restarts": 0,
            "crash_loop_pods": [],
            "startup_times": [],
            "resource_usage": []
        }

        # Get pods in the namespace
        cmd = ["get", "pods", "-n", namespace, "-o", "json"]
        output = self.run_kubectl(cmd)

        if not output:
            return {"error": "Could not retrieve pods from Kubernetes API"}

        try:
            data = json.loads(output)
            for pod in data.get("items", []):
                pod_name = pod.get("metadata", {}).get("name", "")
                creation_time = pod.get("metadata", {}).get("creationTimestamp", "")
                phase = pod.get("status", {}).get("phase", "")

                # Check if this pod belongs to our service
                if not pod_name or service.lower() not in pod_name.lower():
                    continue

                pod_metrics["pods_analyzed"] += 1

                # Collect restart counts
                for container in pod.get("status", {}).get("containerStatuses", []):
                    restart_count = container.get("restartCount", 0)
                    container_name = container.get("name", "")

                    pod_metrics["total_restarts"] += restart_count

                    if restart_count > 0:
                        pod_metrics["resource_usage"].append({
                            "pod": pod_name,
                            "container": container_name,
                            "restart_count": restart_count
                        })

                    # Check for crash loop backoff
                    last_state = container.get("lastState", {})
                    if last_state.get("terminated", {}).get("reason") == "CrashLoopBackOff":
                        pod_metrics["crash_loop_pods"].append({
                            "pod": pod_name,
                            "container": container_name,
                            "exit_code": last_state.get("terminated", {}).get("exitCode", -1)
                        })

                    # Get startup time (creation to ready)
                    started_at = container.get("state", {}).get("running", {}).get("startedAt")
                    if started_at and creation_time:
                        try:
                            creation = datetime.fromisoformat(creation_time.replace('Z', '+00:00'))
                            started = datetime.fromisoformat(started_at.replace('Z', '+00:00'))
                            startup_seconds = (started - creation).total_seconds()

                            pod_metrics["startup_times"].append({
                                "pod": pod_name,
                                "container": container_name,
                                "creation_time": creation_time,
                                "ready_time": started_at,
                                "startup_seconds": startup_seconds
                            })
                        except ValueError:
                            pass

        except json.JSONDecodeError as e:
            return {"error": f"Failed to parse pods JSON: {str(e)}"}

        return pod_metrics

    def collect_current_resource_usage(self, namespace: str) -> Dict[str, Any]:
        """Collect current resource usage from metrics-server."""
        usage_data = {"note": "Attempting to collect current resource usage"}

        # Try to get current metrics
        cmd = ["top", "pods", "-n", namespace]
        output = self.run_kubectl(cmd)

        if output:
            usage_data["raw_output"] = output
            # Parse the output to extract usage
            lines = output.split('\n')
            metrics = []
            for line in lines[1:]:  # Skip header
                if line.strip():
                    parts = line.split()
                    if len(parts) >= 3:
                        metrics.append({
                            "pod": parts[0],
                            "cpu": parts[1],
                            "memory": parts[2]
                        })
            usage_data["parsed_metrics"] = metrics
        else:
            usage_data["note"] = "kubectl top pods not available - metrics-server may not be configured"

        return usage_data

    def collect_deployment_correlation(self, namespace: str, deployments_file: str) -> Dict[str, Any]:
        """Load deployment events for temporal correlation."""
        deployment_data = {}

        try:
            with open(deployments_file, 'r') as f:
                data = json.load(f)
                deployment_data = data
        except FileNotFoundError:
            deployment_data = {"error": f"Deployment file not found: {deployments_file}"}
        except json.JSONDecodeError as e:
            deployment_data = {"error": f"Failed to parse deployment JSON: {str(e)}"}

        return deployment_data

    def load_existing_research_data(self, service: str) -> Dict[str, Any]:
        """Load existing research data for the service."""
        research_data = {}

        # Define possible research data paths
        if service == "pbx-web":
            research_dir = "/home/coding/aide-de-camp/research/pbx-web-30days"
        else:  # whisper-stt
            research_dir = "/home/coding/aide-de-camp/research/whisper-stt-30days"

        research_path = Path(research_dir)

        if not research_path.exists():
            return {"error": f"Research directory not found: {research_dir}"}

        # Load pods data
        pods_file = research_path / "pods-current.json"
        if pods_file.exists():
            try:
                with open(pods_file, 'r') as f:
                    research_data["pods"] = json.load(f)
            except Exception as e:
                research_data["pods_error"] = str(e)

        # Load events data
        events_file = research_path / "events.json"
        if events_file.exists():
            try:
                with open(events_file, 'r') as f:
                    research_data["events"] = json.load(f)
            except Exception as e:
                research_data["events_error"] = str(e)

        # Load deployment data
        deployments_file = research_path / "deployments-30days.json"
        if deployments_file.exists():
            try:
                with open(deployments_file, 'r') as f:
                    research_data["deployments"] = json.load(f)
            except Exception as e:
                research_data["deployments_error"] = str(e)

        # Load replica sets data if available
        replicasets_file = research_path / "replicasets.json"
        if replicasets_file.exists():
            try:
                with open(replicasets_file, 'r') as f:
                    research_data["replicasets"] = json.load(f)
            except Exception as e:
                research_data["replicasets_error"] = str(e)

        return research_data

def collect_pbx_web_metrics(collector: MetricsCollector) -> ServiceMetrics:
    """Collect metrics for pbx-web service."""
    print("Collecting pbx-web metrics...")

    # Load existing research data first
    research_data = collector.load_existing_research_data("pbx-web")

    # Error events - pbx-web is in its own namespace
    error_events = collector.collect_error_events("pbx-web", "pbx-web")

    # Pod metrics
    pod_metrics = collector.collect_pod_metrics("pbx-web", "pbx-web")

    # Resource usage
    resource_usage = collector.collect_current_resource_usage("pbx-web")

    # Deployment correlation
    deployment_data = collector.collect_deployment_correlation(
        "pbx-web",
        "/home/coding/aide-de-camp/research/pbx-web-deployments-30days.json"
    )

    # Identify data gaps and anomalies
    data_gaps = []
    anomalies = []

    if isinstance(pod_metrics, dict) and "error" in pod_metrics:
        data_gaps.append(f"Pod metrics incomplete: {pod_metrics['error']}")

    if isinstance(resource_usage, dict) and "note" in resource_usage and "metrics-server may not be configured" in resource_usage["note"]:
        data_gaps.append("Historical resource usage not available - metrics-server needed")

    # Check for high restart counts
    if isinstance(pod_metrics, dict):
        total_restarts = pod_metrics.get("total_restarts", 0)
        if total_restarts > 5:
            anomalies.append(f"High restart count detected: {total_restarts} restarts")

    metric_coverage = {
        "error_events": "available" if error_events else "limited",
        "pod_restart_counts": "available" if isinstance(pod_metrics, dict) and "error" not in pod_metrics else "unavailable",
        "resource_usage": "limited_current_only",
        "deployment_alignment": "available" if isinstance(deployment_data, dict) and "error" not in deployment_data else "unavailable"
    }

    return ServiceMetrics(
        service_name="pbx-web",
        collection_date=datetime.now().isoformat(),
        period_days=30,
        error_rate_events=error_events,
        pod_restart_counts=[pod_metrics] if isinstance(pod_metrics, dict) else [pod_metrics],
        crash_loop_backoffs=pod_metrics.get("crash_loop_pods", []) if isinstance(pod_metrics, dict) else [],
        pod_startup_times=pod_metrics.get("startup_times", []) if isinstance(pod_metrics, dict) else [],
        health_check_failures=[],  # Would need VictoriaLogs for this
        current_resource_usage=resource_usage,
        resource_requests_vs_limits={},  # Can derive from pod specs
        metric_coverage=metric_coverage,
        data_gaps=data_gaps,
        anomalies=anomalies
    )

def collect_whisper_stt_metrics(collector: MetricsCollector) -> ServiceMetrics:
    """Collect metrics for whisper-stt service."""
    print("Collecting whisper-stt metrics...")

    # Load existing research data first
    research_data = collector.load_existing_research_data("whisper-stt")

    # Error events
    error_events = collector.collect_error_events("whisper-stt", "whisper")

    # Pod metrics
    pod_metrics = collector.collect_pod_metrics("whisper-stt", "whisper")

    # Resource usage
    resource_usage = collector.collect_current_resource_usage("whisper-stt")

    # Deployment correlation
    deployment_data = collector.collect_deployment_correlation(
        "whisper-stt",
        "/home/coding/aide-de-camp/research/whisper-stt-30days/deployments-30days.json"
    )

    # Identify data gaps and anomalies
    data_gaps = []
    anomalies = []

    if isinstance(pod_metrics, dict) and "error" in pod_metrics:
        data_gaps.append(f"Pod metrics incomplete: {pod_metrics['error']}")

    if isinstance(resource_usage, dict) and "note" in resource_usage and "metrics-server may not be configured" in resource_usage.get("note", ""):
        data_gaps.append("Historical resource usage not available - metrics-server needed")

    # Check for high restart counts or crash loops
    if isinstance(pod_metrics, dict):
        total_restarts = pod_metrics.get("total_restarts", 0)
        if total_restarts > 5:
            anomalies.append(f"High restart count detected: {total_restarts} restarts")

        crash_loops = pod_metrics.get("crash_loop_pods", [])
        if crash_loops:
            anomalies.append(f"Crash loop backoffs detected: {len(crash_loops)} pods affected")

    metric_coverage = {
        "error_events": "available" if error_events else "limited",
        "pod_restart_counts": "available" if isinstance(pod_metrics, dict) and "error" not in pod_metrics else "unavailable",
        "resource_usage": "limited_current_only",
        "deployment_alignment": "available" if isinstance(deployment_data, dict) and "error" not in deployment_data else "unavailable"
    }

    return ServiceMetrics(
        service_name="whisper-stt",
        collection_date=datetime.now().isoformat(),
        period_days=30,
        error_rate_events=error_events,
        pod_restart_counts=[pod_metrics] if isinstance(pod_metrics, dict) else [pod_metrics],
        crash_loop_backoffs=pod_metrics.get("crash_loop_pods", []) if isinstance(pod_metrics, dict) else [],
        pod_startup_times=pod_metrics.get("startup_times", []) if isinstance(pod_metrics, dict) else [],
        health_check_failures=[],
        current_resource_usage=resource_usage,
        resource_requests_vs_limits={},
        metric_coverage=metric_coverage,
        data_gaps=data_gaps,
        anomalies=anomalies
    )

def main():
    """Main collection function."""
    print("=" * 80)
    print("30-DAY METRICS COLLECTION FOR pbx-web AND whisper-stt")
    print("=" * 80)
    print()

    collector = MetricsCollector(days=30)

    # Collect metrics for both services
    pbx_metrics = collect_pbx_web_metrics(collector)
    whisper_metrics = collect_whisper_stt_metrics(collector)

    # Convert to dictionaries for JSON output
    results = {
        "collection_metadata": {
            "collected_at": datetime.now().isoformat(),
            "period_days": 30,
            "services": ["pbx-web", "whisper-stt"]
        },
        "pbx_web_metrics": asdict(pbx_metrics),
        "whisper_stt_metrics": asdict(whisper_metrics),
        "summary": {
            "total_error_events": len(pbx_metrics.error_rate_events) + len(whisper_metrics.error_rate_events),
            "total_pods_analyzed": pbx_metrics.pod_restart_counts[0].get("pods_analyzed", 0) if pbx_metrics.pod_restart_counts and isinstance(pbx_metrics.pod_restart_counts[0], dict) else 0 +
                                 whisper_metrics.pod_restart_counts[0].get("pods_analyzed", 0) if whisper_metrics.pod_restart_counts and isinstance(whisper_metrics.pod_restart_counts[0], dict) else 0,
            "data_gaps": pbx_metrics.data_gaps + whisper_metrics.data_gaps,
            "anomalies": pbx_metrics.anomalies + whisper_metrics.anomalies,
            "metric_availability": {
                "pbx_web": pbx_metrics.metric_coverage,
                "whisper_stt": whisper_metrics.metric_coverage
            }
        }
    }

    # Save to file
    output_file = "/home/coding/aide-de-camp/research/adc-1xp0b-metrics-30day.json"
    with open(output_file, 'w') as f:
        json.dump(results, f, indent=2, default=str)

    print()
    print("=" * 80)
    print("COLLECTION COMPLETE")
    print("=" * 80)
    print(f"Results saved to: {output_file}")
    print()
    print("SUMMARY:")
    print(f"  Total error events: {results['summary']['total_error_events']}")
    print(f"  Total pods analyzed: {results['summary']['total_pods_analyzed']}")
    print(f"  Data gaps detected: {len(results['summary']['data_gaps'])}")
    print(f"  Anomalies detected: {len(results['summary']['anomalies'])}")
    print()

    if results['summary']['data_gaps']:
        print("DATA GAPS:")
        for gap in results['summary']['data_gaps']:
            print(f"  - {gap}")
        print()

    if results['summary']['anomalies']:
        print("ANOMALIES:")
        for anomaly in results['summary']['anomalies']:
            print(f"  - {anomaly}")
        print()

if __name__ == "__main__":
    main()