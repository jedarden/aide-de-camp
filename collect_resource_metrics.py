#!/usr/bin/env python3
"""
Resource usage metrics collector for pbx-web and whisper-stt services.
Collects CPU, memory, disk, and network metrics over 30-day period.
"""

import subprocess
import json
import sys
from datetime import datetime, timedelta
from typing import Dict, List, Any
import os

class PrometheusMetricsCollector:
    """Collect metrics from Prometheus via kubectl exec"""

    def __init__(self, prometheus_ip: str = "10.43.253.70"):
        self.prometheus_ip = prometheus_ip
        self.prometheus_url = f"http://{prometheus_ip}:9090"
        self.metrics_data = {
            "collection_metadata": {
                "collected_at": datetime.now().isoformat(),
                "collection_period_days": 30,
                "time_window_start": (datetime.now() - timedelta(days=30)).isoformat(),
                "time_window_end": datetime.now().isoformat(),
                "services": ["pbx-web", "whisper-stt"],
                "prometheus_instance": prometheus_ip
            },
            "services": {}
        }

    def _run_prometheus_query(self, query: str, timeout: str = "30d") -> List[Dict]:
        """Execute a PromQL query and return results"""
        # URL encode the query
        encoded_query = query.replace(" ", "%20").replace('"', "%22").replace("{", "%7B").replace("}", "%7D")

        cmd = f"""
        kubectl --server=http://traefik-ardenone-cluster:8001 run --rm -i --restart=Never curl-prometheus --image=curlimages/curl:latest --command -- curl -s '{self.prometheus_url}/api/v1/query?query={encoded_query}'
        """

        try:
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=120)
            if result.returncode == 0:
                data = json.loads(result.stdout)
                if data.get("status") == "success":
                    return data.get("data", {}).get("result", [])
            return []
        except Exception as e:
            print(f"Error executing query: {e}", file=sys.stderr)
            return []

    def _run_prometheus_range_query(self, query: str, start: str, end: str, step: str = "1h") -> List[Dict]:
        """Execute a PromQL range query"""
        encoded_query = query.replace(" ", "%20").replace('"', "%22").replace("{", "%7B").replace("}", "%7D")

        cmd = f"""
        kubectl --server=http://traefik-ardenone-cluster:8001 run --rm -i --restart=Never curl-prometheus --image=curlimages/curl:latest --command -- curl -s '{self.prometheus_url}/api/v1/query_range?query={encoded_query}&start={start}&end={end}&step={step}'
        """

        try:
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=120)
            if result.returncode == 0:
                data = json.loads(result.stdout)
                if data.get("status") == "success":
                    return data.get("data", {}).get("result", [])
            return []
        except Exception as e:
            print(f"Error executing range query: {e}", file=sys.stderr)
            return []

    def collect_cpu_metrics(self, namespace: str, service: str):
        """Collect CPU utilization metrics"""
        print(f"Collecting CPU metrics for {service}...")

        cpu_metrics = {
            "current_cpu_usage": [],
            "cpu_limit_utilization": [],
            "cpu_requests_utilization": []
        }

        # Current CPU usage by container
        query = f'rate(container_cpu_usage_seconds_total{{namespace="{namespace}"}}[5m]) * 100'
        results = self._run_prometheus_query(query)

        for result in results:
            metric = result.get("metric", {})
            value = result.get("value", [])
            if len(value) >= 2:
                cpu_metrics["current_cpu_usage"].append({
                    "container": metric.get("container", "unknown"),
                    "pod": metric.get("pod", "unknown"),
                    "timestamp": value[0],
                    "cpu_cores": float(value[1]),
                    "cpu_percent": float(value[1]) * 100
                })

        # CPU limits and requests info
        query = f'kube_pod_container_resource_requests{{namespace="{namespace}",resource="cpu"}}'
        results = self._run_prometheus_query(query)

        for result in results:
            metric = result.get("metric", {})
            value = result.get("value", [])
            if len(value) >= 2:
                cpu_metrics["cpu_requests_utilization"].append({
                    "container": metric.get("container", "unknown"),
                    "pod": metric.get("pod", "unknown"),
                    "request_cores": float(value[1])
                })

        query = f'kube_pod_container_resource_limits{{namespace="{namespace}",resource="cpu"}}'
        results = self._run_prometheus_query(query)

        for result in results:
            metric = result.get("metric", {})
            value = result.get("value", [])
            if len(value) >= 2:
                cpu_metrics["cpu_limit_utilization"].append({
                    "container": metric.get("container", "unknown"),
                    "pod": metric.get("pod", "unknown"),
                    "limit_cores": float(value[1])
                })

        return cpu_metrics

    def collect_memory_metrics(self, namespace: str, service: str):
        """Collect memory usage metrics"""
        print(f"Collecting memory metrics for {service}...")

        memory_metrics = {
            "current_memory_usage": [],
            "memory_working_set": [],
            "memory_cache": [],
            "memory_limits": [],
            "memory_requests": []
        }

        # Current memory usage
        query = f'container_memory_usage_bytes{{namespace="{namespace}"}}'
        results = self._run_prometheus_query(query)

        for result in results:
            metric = result.get("metric", {})
            value = result.get("value", [])
            if len(value) >= 2:
                memory_metrics["current_memory_usage"].append({
                    "container": metric.get("container", "unknown"),
                    "pod": metric.get("pod", "unknown"),
                    "timestamp": value[0],
                    "memory_bytes": float(value[1]),
                    "memory_mb": float(value[1]) / (1024 * 1024),
                    "memory_gb": float(value[1]) / (1024 * 1024 * 1024)
                })

        # Memory working set (more accurate for pod memory usage)
        query = f'container_memory_working_set_bytes{{namespace="{namespace}"}}'
        results = self._run_prometheus_query(query)

        for result in results:
            metric = result.get("metric", {})
            value = result.get("value", [])
            if len(value) >= 2:
                memory_metrics["memory_working_set"].append({
                    "container": metric.get("container", "unknown"),
                    "pod": metric.get("pod", "unknown"),
                    "working_set_bytes": float(value[1]),
                    "working_set_mb": float(value[1]) / (1024 * 1024)
                })

        # Memory limits and requests
        query = f'kube_pod_container_resource_requests{{namespace="{namespace}",resource="memory"}}'
        results = self._run_prometheus_query(query)

        for result in results:
            metric = result.get("metric", {})
            value = result.get("value", [])
            if len(value) >= 2:
                memory_metrics["memory_requests"].append({
                    "container": metric.get("container", "unknown"),
                    "pod": metric.get("pod", "unknown"),
                    "request_bytes": float(value[1]),
                    "request_mb": float(value[1]) / (1024 * 1024)
                })

        query = f'kube_pod_container_resource_limits{{namespace="{namespace}",resource="memory"}}'
        results = self._run_prometheus_query(query)

        for result in results:
            metric = result.get("metric", {})
            value = result.get("value", [])
            if len(value) >= 2:
                memory_metrics["memory_limits"].append({
                    "container": metric.get("container", "unknown"),
                    "pod": metric.get("pod", "unknown"),
                    "limit_bytes": float(value[1]),
                    "limit_mb": float(value[1]) / (1024 * 1024)
                })

        return memory_metrics

    def collect_disk_metrics(self, namespace: str, service: str):
        """Collect disk I/O and storage metrics"""
        print(f"Collecting disk metrics for {service}...")

        disk_metrics = {
            "disk_usage_bytes": [],
            "volume_usage": [],
            "pod_volumes": []
        }

        # Check for persistent volume claims
        try:
            cmd = f"kubectl --server=http://traefik-ardenone-cluster:8001 get pvc -n {namespace} -o json"
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
            if result.returncode == 0:
                pvc_data = json.loads(result.stdout)
                for pvc in pvc_data.get("items", []):
                    pvc_name = pvc.get("metadata", {}).get("name", "unknown")
                    storage = pvc.get("spec", {}).get("resources", {}).get("requests", {}).get("storage", "unknown")
                    disk_metrics["pod_volumes"].append({
                        "pvc_name": pvc_name,
                        "storage_request": storage,
                        "status": pvc.get("status", {}).get("phase", "unknown")
                    })
        except Exception as e:
            print(f"Error collecting PVC data: {e}", file=sys.stderr)

        return disk_metrics

    def collect_network_metrics(self, namespace: str, service: str):
        """Collect network traffic metrics"""
        print(f"Collecting network metrics for {service}...")

        network_metrics = {
            "network_receive_bytes_total": [],
            "network_transmit_bytes_total": [],
            "network_receive_rate": [],
            "network_transmit_rate": []
        }

        # Network receive bytes
        query = f'rate(container_network_receive_bytes_total{{namespace="{namespace}"}}[5m])'
        results = self._run_prometheus_query(query)

        for result in results:
            metric = result.get("metric", {})
            value = result.get("value", [])
            if len(value) >= 2:
                network_metrics["network_receive_rate"].append({
                    "container": metric.get("container", "unknown"),
                    "pod": metric.get("pod", "unknown"),
                    "interface": metric.get("interface", "unknown"),
                    "timestamp": value[0],
                    "receive_bytes_per_sec": float(value[1]),
                    "receive_kbps": (float(value[1]) * 8) / 1000,
                    "receive_mbps": (float(value[1]) * 8) / (1000 * 1000)
                })

        # Network transmit bytes
        query = f'rate(container_network_transmit_bytes_total{{namespace="{namespace}"}}[5m])'
        results = self._run_prometheus_query(query)

        for result in results:
            metric = result.get("metric", {})
            value = result.get("value", [])
            if len(value) >= 2:
                network_metrics["network_transmit_rate"].append({
                    "container": metric.get("container", "unknown"),
                    "pod": metric.get("pod", "unknown"),
                    "interface": metric.get("interface", "unknown"),
                    "timestamp": value[0],
                    "transmit_bytes_per_sec": float(value[1]),
                    "transmit_kbps": (float(value[1]) * 8) / 1000,
                    "transmit_mbps": (float(value[1]) * 8) / (1000 * 1000)
                })

        return network_metrics

    def collect_service_metrics(self, namespace: str, service: str):
        """Collect all metrics for a service"""
        print(f"\n=== Collecting metrics for {service} ({namespace}) ===")

        service_metrics = {
            "service": service,
            "namespace": namespace,
            "collection_timestamp": datetime.now().isoformat(),
            "cpu_metrics": self.collect_cpu_metrics(namespace, service),
            "memory_metrics": self.collect_memory_metrics(namespace, service),
            "disk_metrics": self.collect_disk_metrics(namespace, service),
            "network_metrics": self.collect_network_metrics(namespace, service)
        }

        return service_metrics

    def collect_all_metrics(self):
        """Collect metrics for all services"""
        services = [
            ("pbx-web", "pbx-web"),
            ("whisper-stt", "whisper-stt")
        ]

        for service, namespace in services:
            try:
                service_metrics = self.collect_service_metrics(namespace, service)
                self.metrics_data["services"][service] = service_metrics
            except Exception as e:
                print(f"Error collecting metrics for {service}: {e}", file=sys.stderr)
                self.metrics_data["services"][service] = {
                    "service": service,
                    "error": str(e),
                    "collection_failed": True
                }

        return self.metrics_data

def main():
    """Main execution"""
    collector = PrometheusMetricsCollector()

    print("Starting resource usage metrics collection...")
    print(f"Time window: 30 days ending {datetime.now().isoformat()}")
    print(f"Services: pbx-web, whisper-stt")

    metrics_data = collector.collect_all_metrics()

    # Save to file
    output_file = "/home/coding/aide-de-camp/data/resource_metrics_30d.json"
    with open(output_file, 'w') as f:
        json.dump(metrics_data, f, indent=2)

    print(f"\nMetrics collection complete. Data saved to {output_file}")

    # Print summary
    print("\n=== COLLECTION SUMMARY ===")
    for service, data in metrics_data["services"].items():
        if data.get("collection_failed"):
            print(f"❌ {service}: Collection failed - {data.get('error', 'Unknown error')}")
        else:
            print(f"✅ {service}: Collection successful")

            cpu_count = len(data.get("cpu_metrics", {}).get("current_cpu_usage", []))
            memory_count = len(data.get("memory_metrics", {}).get("current_memory_usage", []))
            network_count = len(data.get("network_metrics", {}).get("network_receive_rate", []))

            print(f"   - CPU metrics: {cpu_count}")
            print(f"   - Memory metrics: {memory_count}")
            print(f"   - Network metrics: {network_count}")

    return 0

if __name__ == "__main__":
    sys.exit(main())