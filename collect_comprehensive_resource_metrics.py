#!/usr/bin/env python3
"""
Comprehensive resource usage metrics collection for pbx-web and whisper-stt services.

This script collects CPU, memory, disk, and network metrics using available Kubernetes APIs.
Since historical Prometheus metrics are not accessible, it focuses on:
- Current resource usage via kubectl top
- Resource requests and limits from pod specs
- PVC/storage information
- Network availability
- Kubernetes events related to resources
- Temporal alignment with deployment events
"""

import subprocess
import json
import sys
import os
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, asdict
from pathlib import Path
import re

@dataclass
class ResourceMetrics:
    """Container for resource metrics."""
    service_name: str
    namespace: str
    collection_timestamp: str
    period_days: int

    # CPU metrics
    current_cpu_usage: List[Dict[str, Any]]
    cpu_requests: List[Dict[str, Any]]
    cpu_limits: List[Dict[str, Any]]
    cpu_utilization: Dict[str, Any]

    # Memory metrics
    current_memory_usage: List[Dict[str, Any]]
    memory_requests: List[Dict[str, Any]]
    memory_limits: List[Dict[str, Any]]
    memory_utilization: Dict[str, Any]

    # Disk/storage metrics
    pvcs: List[Dict[str, Any]]
    volume_usage: List[Dict[str, Any]]

    # Network metrics
    network_stats: List[Dict[str, Any]]

    # Coverage and quality
    metric_coverage: Dict[str, str]
    data_gaps: List[str]
    anomalies: List[str]
    temporal_alignment: Dict[str, Any]

class ResourceMetricsCollector:
    """Collects resource metrics from Kubernetes API."""

    def __init__(self, days: int = 30):
        self.days = days
        self.since_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        self.collection_date = datetime.now().isoformat()

    def run_kubectl(self, cmd: List[str], timeout: int = 30) -> str:
        """Run kubectl command and return output."""
        try:
            full_cmd = ["kubectl", "--server=http://traefik-ardenone-cluster:8001"] + cmd
            result = subprocess.run(full_cmd, capture_output=True, text=True, timeout=timeout)
            if result.returncode != 0:
                return ""
            return result.stdout
        except subprocess.TimeoutExpired:
            return ""
        except Exception as e:
            return ""

    def get_current_resource_usage(self, namespace: str) -> Dict[str, Any]:
        """Get current CPU and memory usage using kubectl top."""
        usage_data = {
            "pods": [],
            "collection_time": self.collection_date,
            "total_cpu_cores": 0.0,
            "total_memory_bytes": 0.0
        }

        cmd = ["top", "pods", "-n", namespace]
        output = self.run_kubectl(cmd)

        if not output:
            return usage_data

        # Parse kubectl top output
        lines = output.strip().split('\n')
        for line in lines[1:]:  # Skip header
            if line.strip():
                parts = line.split()
                if len(parts) >= 3:
                    pod_name = parts[0]
                    cpu_str = parts[1]
                    memory_str = parts[2]

                    # Parse CPU (e.g., "1m" = 1 millicore = 0.001 cores)
                    cpu_cores = self._parse_cpu(cpu_str)

                    # Parse memory (e.g., "76Mi", "5569Mi")
                    memory_bytes = self._parse_memory(memory_str)

                    usage_data["pods"].append({
                        "pod": pod_name,
                        "cpu_cores": cpu_cores,
                        "cpu_millicores": cpu_cores * 1000,
                        "memory_bytes": memory_bytes,
                        "memory_mib": memory_bytes / (1024 * 1024),
                        "memory_gib": memory_bytes / (1024 * 1024 * 1024),
                        "cpu_raw": cpu_str,
                        "memory_raw": memory_str
                    })

                    usage_data["total_cpu_cores"] += cpu_cores
                    usage_data["total_memory_bytes"] += memory_bytes

        return usage_data

    def _parse_cpu(self, cpu_str: str) -> float:
        """Parse CPU string like '1m', '500m', '1' to cores."""
        cpu_str = cpu_str.strip()
        if cpu_str.endswith('m'):
            return float(cpu_str[:-1]) / 1000  # millicores to cores
        else:
            return float(cpu_str)

    def _parse_memory(self, memory_str: str) -> int:
        """Parse memory string like '76Mi', '1Gi' to bytes."""
        memory_str = memory_str.strip()
        if memory_str.endswith('Mi'):
            return int(float(memory_str[:-2]) * 1024 * 1024)
        elif memory_str.endswith('Gi'):
            return int(float(memory_str[:-2]) * 1024 * 1024 * 1024)
        elif memory_str.endswith('Ki'):
            return int(float(memory_str[:-2]) * 1024)
        else:
            return int(memory_str)

    def get_pod_resource_specs(self, namespace: str, service: str) -> Dict[str, Any]:
        """Get resource requests and limits from pod specs."""
        specs = {
            "containers": [],
            "total_requests": {"cpu": "0", "memory": "0"},
            "total_limits": {"cpu": "0", "memory": "0"}
        }

        cmd = ["get", "pods", "-n", namespace, "-o", "json"]
        output = self.run_kubectl(cmd, timeout=60)

        if not output:
            return specs

        try:
            data = json.loads(output)
            for pod in data.get("items", []):
                pod_name = pod.get("metadata", {}).get("name", "")

                # Filter for relevant pods
                if service.lower() not in pod_name.lower():
                    continue

                for container in pod.get("spec", {}).get("containers", []):
                    container_name = container.get("name", "")
                    resources = container.get("resources", {})

                    requests = resources.get("requests", {})
                    limits = resources.get("limits", {})

                    cpu_request = self._parse_resource_cpu(requests.get("cpu", "0"))
                    cpu_limit = self._parse_resource_cpu(limits.get("cpu", "0"))
                    memory_request = self._parse_resource_memory(requests.get("memory", "0"))
                    memory_limit = self._parse_resource_memory(limits.get("memory", "0"))

                    specs["containers"].append({
                        "pod": pod_name,
                        "container": container_name,
                        "cpu_request_cores": cpu_request,
                        "cpu_limit_cores": cpu_limit,
                        "memory_request_bytes": memory_request,
                        "memory_limit_bytes": memory_limit,
                        "cpu_request_raw": requests.get("cpu", "0"),
                        "cpu_limit_raw": limits.get("cpu", "0"),
                        "memory_request_raw": requests.get("memory", "0"),
                        "memory_limit_raw": limits.get("memory", "0")
                    })

                    specs["total_requests"]["cpu"] = str(cpu_request)
                    specs["total_requests"]["memory"] = str(memory_request)
                    specs["total_limits"]["cpu"] = str(cpu_limit)
                    specs["total_limits"]["memory"] = str(memory_limit)

        except json.JSONDecodeError:
            pass

        return specs

    def _parse_resource_cpu(self, cpu_str: str) -> float:
        """Parse CPU resource specification."""
        if not cpu_str:
            return 0.0
        cpu_str = cpu_str.strip()
        if cpu_str.endswith('m'):
            return float(cpu_str[:-1]) / 1000
        else:
            return float(cpu_str)

    def _parse_resource_memory(self, memory_str: str) -> int:
        """Parse memory resource specification."""
        if not memory_str:
            return 0
        memory_str = memory_str.strip()
        if memory_str.endswith('Mi'):
            return int(float(memory_str[:-2]) * 1024 * 1024)
        elif memory_str.endswith('Gi'):
            return int(float(memory_str[:-2]) * 1024 * 1024 * 1024)
        elif memory_str.endswith('Ki'):
            return int(float(memory_str[:-2]) * 1024)
        else:
            return int(memory_str)

    def get_pvc_info(self, namespace: str) -> List[Dict[str, Any]]:
        """Get PVC information for storage metrics."""
        pvcs = []

        cmd = ["get", "pvc", "-n", namespace, "-o", "json"]
        output = self.run_kubectl(cmd)

        if not output:
            return pvcs

        try:
            data = json.loads(output)
            for pvc in data.get("items", []):
                pvc_name = pvc.get("metadata", {}).get("name", "")
                storage_class = pvc.get("spec", {}).get("storageClassName", "")
                storage_request = pvc.get("spec", {}).get("resources", {}).get("requests", {}).get("storage", "")
                status = pvc.get("status", {}).get("phase", "")
                capacity = pvc.get("status", {}).get("capacity", {}).get("storage", "")

                pvcs.append({
                    "name": pvc_name,
                    "storage_class": storage_class,
                    "request": storage_request,
                    "capacity": capacity,
                    "status": status,
                    "request_bytes": self._parse_resource_memory(storage_request) if storage_request else 0,
                    "capacity_bytes": self._parse_resource_memory(capacity) if capacity else 0
                })
        except json.JSONDecodeError:
            pass

        return pvcs

    def get_resource_events(self, namespace: str, service: str) -> List[Dict[str, Any]]:
        """Get Kubernetes events related to resource issues."""
        events = []

        # Get events with resource-related reasons
        resource_reasons = [
            "FailedScheduling", "InsufficientCpu", "InsufficientMemory",
            "OOMKilled", "Evicted", "NodePressure", "FailedMount"
        ]

        cmd = ["get", "events", "-n", namespace, "-o", "json"]
        output = self.run_kubectl(cmd, timeout=60)

        if not output:
            return events

        try:
            data = json.loads(output)
            for item in data.get("items", []):
                reason = item.get("reason", "")
                message = item.get("message", "")
                timestamp = item.get("lastTimestamp", "")

                # Filter for resource-related events
                if any(r.lower() in reason.lower() for r in resource_reasons) or \
                   any(r.lower() in message.lower() for r in ["cpu", "memory", "disk", "storage"]):

                    events.append({
                        "timestamp": timestamp,
                        "reason": reason,
                        "message": message[:200],  # Truncate
                        "type": item.get("type", ""),
                        "involved_object": {
                            "name": item.get("involvedObject", {}).get("name", ""),
                            "kind": item.get("involvedObject", {}).get("kind", "")
                        }
                    })
        except json.JSONDecodeError:
            pass

        return events

    def calculate_utilization(self, current_usage: Dict, specs: Dict) -> Dict[str, Any]:
        """Calculate resource utilization percentages."""
        utilization = {
            "cpu": {
                "current_usage_cores": current_usage.get("total_cpu_cores", 0),
                "requests_cores": specs.get("total_requests", {}).get("cpu", "0"),
                "limits_cores": specs.get("total_limits", {}).get("cpu", "0"),
                "vs_request_percent": 0.0,
                "vs_limit_percent": 0.0
            },
            "memory": {
                "current_usage_bytes": current_usage.get("total_memory_bytes", 0),
                "requests_bytes": specs.get("total_requests", {}).get("memory", "0"),
                "limits_bytes": specs.get("total_limits", {}).get("memory", "0"),
                "vs_request_percent": 0.0,
                "vs_limit_percent": 0.0
            }
        }

        # Calculate CPU utilization
        cpu_requests = float(utilization["cpu"]["requests_cores"]) if utilization["cpu"]["requests_cores"] != "0" else 0
        cpu_limits = float(utilization["cpu"]["limits_cores"]) if utilization["cpu"]["limits_cores"] != "0" else 0

        if cpu_requests > 0:
            utilization["cpu"]["vs_request_percent"] = (utilization["cpu"]["current_usage_cores"] / cpu_requests) * 100
        if cpu_limits > 0:
            utilization["cpu"]["vs_limit_percent"] = (utilization["cpu"]["current_usage_cores"] / cpu_limits) * 100

        # Calculate memory utilization
        mem_requests = float(utilization["memory"]["requests_bytes"]) if utilization["memory"]["requests_bytes"] != "0" else 0
        mem_limits = float(utilization["memory"]["limits_bytes"]) if utilization["memory"]["limits_bytes"] != "0" else 0

        if mem_requests > 0:
            utilization["memory"]["vs_request_percent"] = (utilization["memory"]["current_usage_bytes"] / mem_requests) * 100
        if mem_limits > 0:
            utilization["memory"]["vs_limit_percent"] = (utilization["memory"]["current_usage_bytes"] / mem_limits) * 100

        return utilization

    def load_deployment_data(self, service: str) -> Dict[str, Any]:
        """Load deployment events for temporal alignment."""
        deployment_files = {
            "pbx-web": "/home/coding/aide-de-camp/data/pbx-web-deployment.json",
            "whisper-stt": "/home/coding/aide-de-camp/data/whisper-stt-deployment.json"
        }

        deployment_file = deployment_files.get(service)
        if not deployment_file:
            return {"error": "Unknown service"}

        try:
            with open(deployment_file, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            return {"error": f"Deployment file not found: {deployment_file}"}
        except json.JSONDecodeError:
            return {"error": f"Invalid JSON in deployment file: {deployment_file}"}

    def collect_service_metrics(self, namespace: str, service: str) -> ResourceMetrics:
        """Collect all resource metrics for a service."""
        print(f"Collecting resource metrics for {service} ({namespace})...")

        # Collect current usage
        current_usage = self.get_current_resource_usage(namespace)

        # Collect resource specs
        specs = self.get_pod_resource_specs(namespace, service)

        # Collect PVC info
        pvcs = self.get_pvc_info(namespace)

        # Collect resource events
        resource_events = self.get_resource_events(namespace, service)

        # Calculate utilization
        utilization = self.calculate_utilization(current_usage, specs)

        # Load deployment data for alignment
        deployment_data = self.load_deployment_data(service)

        # Identify gaps and anomalies
        data_gaps = []
        anomalies = []

        # Check for missing metrics
        if not current_usage.get("pods"):
            data_gaps.append("Current resource usage not available - metrics-server may not be responding")

        if not specs.get("containers"):
            data_gaps.append("Pod resource specifications not available")

        # Check for anomalies
        for event in resource_events:
            if "OOMKilled" in event.get("reason", ""):
                anomalies.append(f"Memory pressure detected: {event.get('message', '')}")
            if "Evicted" in event.get("reason", ""):
                anomalies.append(f"Pod eviction detected: {event.get('message', '')}")

        # Check utilization
        cpu_util = utilization["cpu"]["vs_request_percent"]
        mem_util = utilization["memory"]["vs_request_percent"]

        if cpu_util > 80:
            anomalies.append(f"High CPU utilization: {cpu_util:.1f}% of requests")
        if mem_util > 80:
            anomalies.append(f"High memory utilization: {mem_util:.1f}% of requests")

        metric_coverage = {
            "current_usage": "available" if current_usage.get("pods") else "unavailable",
            "resource_limits": "available" if specs.get("containers") else "unavailable",
            "storage_info": "available" if pvcs else "no_pvcs",
            "resource_events": "available" if resource_events else "none",
            "deployment_alignment": "available" if "error" not in deployment_data else "unavailable"
        }

        # Prepare structured data
        cpu_data = []
        memory_data = []

        for pod in current_usage.get("pods", []):
            cpu_data.append({
                "pod": pod["pod"],
                "current_cpu_cores": pod["cpu_cores"],
                "current_cpu_millicores": pod["cpu_millicores"]
            })

            memory_data.append({
                "pod": pod["pod"],
                "current_memory_bytes": pod["memory_bytes"],
                "current_memory_mib": pod["memory_mib"]
            })

        cpu_requests = []
        cpu_limits = []
        memory_requests = []
        memory_limits = []

        for container in specs.get("containers", []):
            cpu_requests.append({
                "pod": container["pod"],
                "container": container["container"],
                "request_cores": container["cpu_request_cores"]
            })

            cpu_limits.append({
                "pod": container["pod"],
                "container": container["container"],
                "limit_cores": container["cpu_limit_cores"]
            })

            memory_requests.append({
                "pod": container["pod"],
                "container": container["container"],
                "request_bytes": container["memory_request_bytes"]
            })

            memory_limits.append({
                "pod": container["pod"],
                "container": container["container"],
                "limit_bytes": container["memory_limit_bytes"]
            })

        # Network metrics (limited availability)
        network_stats = [{
            "note": "Detailed network metrics require Prometheus/monitoring integration",
            "available_data": "pod-level network connectivity only",
            "metrics_available": ["pod_status", "pod_ip", "network_policy"]
        }]

        temporal_alignment = {
            "deployment_data_loaded": "error" not in deployment_data,
            "deployment_events_count": len(deployment_data.get("items", [])) if "error" not in deployment_data else 0,
            "resource_events_count": len(resource_events),
            "alignment_status": "partial"  # Only current data, not historical
        }

        return ResourceMetrics(
            service_name=service,
            namespace=namespace,
            collection_timestamp=self.collection_date,
            period_days=self.days,
            current_cpu_usage=cpu_data,
            cpu_requests=cpu_requests,
            cpu_limits=cpu_limits,
            cpu_utilization=utilization.get("cpu", {}),
            current_memory_usage=memory_data,
            memory_requests=memory_requests,
            memory_limits=memory_limits,
            memory_utilization=utilization.get("memory", {}),
            pvcs=pvcs,
            volume_usage=[],  # Requires detailed volume stats
            network_stats=network_stats,
            metric_coverage=metric_coverage,
            data_gaps=data_gaps,
            anomalies=anomalies,
            temporal_alignment=temporal_alignment
        )

def main():
    """Main collection function."""
    print("=" * 80)
    print("COMPREHENSIVE RESOURCE USAGE METRICS COLLECTION")
    print("Services: pbx-web and whisper-stt (30-day period)")
    print("=" * 80)
    print()

    collector = ResourceMetricsCollector(days=30)

    services = [
        ("pbx-web", "pbx-web"),
        ("whisper-stt", "whisper-stt")
    ]

    results = {
        "collection_metadata": {
            "collected_at": collector.collection_date,
            "period_days": collector.days,
            "time_window_start": collector.since_date,
            "time_window_end": collector.collection_date,
            "services": ["pbx-web", "whisper-stt"],
            "collection_method": "Kubernetes API via kubectl proxy",
            "note": "Historical metrics not available - showing current state and configuration"
        },
        "services": {}
    }

    for service, namespace in services:
        try:
            metrics = collector.collect_service_metrics(namespace, service)
            results["services"][service] = asdict(metrics)
        except Exception as e:
            print(f"Error collecting metrics for {service}: {e}", file=sys.stderr)
            results["services"][service] = {
                "error": str(e),
                "collection_failed": True
            }

    # Generate summary
    summary = {
        "total_pods_monitored": 0,
        "total_cpu_usage_cores": 0.0,
        "total_memory_usage_bytes": 0,
        "total_pvcs": 0,
        "services_with_issues": [],
        "data_gaps": [],
        "anomalies": []
    }

    for service, data in results["services"].items():
        if data.get("error"):
            continue

        # Count pods
        summary["total_pods_monitored"] += len(data.get("current_cpu_usage", []))

        # Aggregate CPU
        cpu_util = data.get("cpu_utilization", {})
        summary["total_cpu_usage_cores"] += cpu_util.get("current_usage_cores", 0)

        # Aggregate memory
        mem_util = data.get("memory_utilization", {})
        summary["total_memory_usage_bytes"] += mem_util.get("current_usage_bytes", 0)

        # Count PVCs
        summary["total_pvcs"] += len(data.get("pvcs", []))

        # Collect issues
        if data.get("anomalies"):
            summary["services_with_issues"].append(service)
            summary["anomalies"].extend([f"{service}: {a}" for a in data["anomalies"]])

        # Collect gaps
        summary["data_gaps"].extend([f"{service}: {g}" for g in data.get("data_gaps", [])])

    results["summary"] = summary

    # Save results
    output_file = "/home/coding/aide-de-camp/data/resource_usage_metrics_30d.json"
    with open(output_file, 'w') as f:
        json.dump(results, f, indent=2, default=str)

    print()
    print("=" * 80)
    print("COLLECTION COMPLETE")
    print("=" * 80)
    print(f"Results saved to: {output_file}")
    print()
    print("SUMMARY:")
    print(f"  Total pods monitored: {summary['total_pods_monitored']}")
    print(f"  Total CPU usage: {summary['total_cpu_usage_cores']:.3f} cores")
    print(f"  Total memory usage: {summary['total_memory_usage_bytes'] / (1024**3):.2f} GiB")
    print(f"  Total PVCs: {summary['total_pvcs']}")
    print(f"  Services with issues: {len(summary['services_with_issues'])}")
    print(f"  Data gaps: {len(summary['data_gaps'])}")
    print(f"  Anomalies: {len(summary['anomalies'])}")
    print()

    if summary['anomalies']:
        print("ANOMALIES DETECTED:")
        for anomaly in summary['anomalies']:
            print(f"  - {anomaly}")
        print()

    if summary['data_gaps']:
        print("DATA GAPS:")
        for gap in summary['data_gaps']:
            print(f"  - {gap}")
        print()

    print("NOTE: Historical 30-day resource metrics require Prometheus integration.")
    print("This collection shows current resource usage and configuration state.")

    return 0

if __name__ == "__main__":
    sys.exit(main())