#!/usr/bin/env python3
"""
Test script to find available Prometheus metrics for pbx-web and whisper-stt
"""

import subprocess
import json
import sys
from datetime import datetime, timedelta
import urllib.parse

def test_prometheus_query(query: str):
    """Test a single Prometheus query"""
    prometheus_ip = "10.43.253.70"
    encoded_query = urllib.parse.quote(query)

    cmd = f"""
    kubectl --server=http://traefik-ardenone-cluster:8001 run --rm -i --restart=Never curl-prometheus --image=curlimages/curl:latest --command -- curl -s 'http://{prometheus_ip}:9090/api/v1/query?query={encoded_query}'
    """

    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=120)
        if result.returncode == 0:
            data = json.loads(result.stdout)
            if data.get("status") == "success":
                return data.get("data", {}).get("result", [])
            else:
                print(f"Query failed: {data.get('error', 'Unknown error')}")
                return []
        else:
            print(f"Command failed: {result.stderr}")
            return []
    except Exception as e:
        print(f"Exception: {e}")
        return []

def main():
    """Main execution"""
    print("Testing Prometheus metrics for pbx-web and whisper-stt namespaces...")

    # Test different queries
    test_queries = [
        ("1. Basic container CPU usage", 'rate(container_cpu_usage_seconds_total{namespace="pbx-web"}[5m])'),
        ("2. Container memory usage", 'container_memory_usage_bytes{namespace="pbx-web"}'),
        ("3. Network receive rate", 'rate(container_network_receive_bytes_total{namespace="pbx-web"}[5m])'),
        ("4. All metrics with pbx-web namespace", 'up{namespace="pbx-web"}'),
        ("5. All metrics with whisper-stt namespace", 'up{namespace="whisper-stt"}'),
        ("6. Pod CPU usage", 'rate(container_cpu_usage_seconds_total{namespace="whisper-stt"}[5m])'),
        ("7. Pod memory usage", 'container_memory_usage_bytes{namespace="whisper-stt"}'),
    ]

    for description, query in test_queries:
        print(f"\n{description}")
        print(f"Query: {query}")
        results = test_prometheus_query(query)
        print(f"Results: {len(results)} data points returned")

        if results:
            print("Sample data:")
            for i, result in enumerate(results[:3]):  # Show first 3 results
                metric = result.get("metric", {})
                value = result.get("value", [])
                print(f"  {i+1}. Metric: {metric}")
                print(f"     Value: {value}")
        else:
            print("  No data returned")

    return 0

if __name__ == "__main__":
    sys.exit(main())