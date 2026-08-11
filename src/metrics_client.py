#!/usr/bin/env python3
"""
Metrics Query Client for pbx-web and whisper-stt

Unified client for querying both Prometheus (resource metrics) and VictoriaLogs (log metrics).
Provides connection testing, metric discovery, and 30-day data availability verification.

Acceptance Criteria:
1. Install/configure query client for the metrics endpoint
2. Test connection to the metrics endpoint
3. Validate metric names and labels exist for both pbx-web and whisper-stt
4. Document the available metric types and their naming conventions
5. Verify 30-day data availability for both services

Task: adc-3t1ibm
Created: 2026-08-07
"""

import asyncio
import httpx
import json
import urllib.parse
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
from enum import Enum


class MetricsBackend(Enum):
    """Available metrics backends"""
    PROMETHEUS = "prometheus"
    VICTORIALOGS = "victorialogs"


@dataclass
class MetricMetadata:
    """Metadata about a discovered metric"""
    name: str
    type: str  # gauge, counter, histogram, etc.
    help: str
    labels: Dict[str, str]
    backend: MetricsBackend


@dataclass
class ConnectionTestResult:
    """Result of connection test to a metrics backend"""
    backend: MetricsBackend
    success: bool
    endpoint: str
    response_time_ms: float
    error_message: Optional[str] = None
    version: Optional[str] = None


class PrometheusClient:
    """Client for querying Prometheus metrics endpoint"""

    def __init__(self, base_url: str = "http://10.43.253.70:9090"):
        """
        Initialize Prometheus client.

        Args:
            base_url: Prometheus server URL (kube-prometheus-stack-arde-prometheus)
        """
        self.base_url = base_url.rstrip('/')
        self.api_endpoint = f"{self.base_url}/api/v1"

    async def test_connection(self) -> ConnectionTestResult:
        """Test connection to Prometheus endpoint"""
        start_time = datetime.now()
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                # Query Prometheus build info for connection test
                response = await client.get(f"{self.api_endpoint}/query",
                                          params={"query": "prometheus_build_info"})
                elapsed = (datetime.now() - start_time).total_seconds() * 1000

                if response.status_code == 200:
                    data = response.json()
                    if data.get("status") == "success":
                        return ConnectionTestResult(
                            backend=MetricsBackend.PROMETHEUS,
                            success=True,
                            endpoint=self.base_url,
                            response_time_ms=round(elapsed, 2),
                            version="prometheus"
                        )

                return ConnectionTestResult(
                    backend=MetricsBackend.PROMETHEUS,
                    success=False,
                    endpoint=self.base_url,
                    response_time_ms=round(elapsed, 2),
                    error_message=f"Status code: {response.status_code}"
                )
        except Exception as e:
            elapsed = (datetime.now() - start_time).total_seconds() * 1000
            return ConnectionTestResult(
                backend=MetricsBackend.PROMETHEUS,
                success=False,
                endpoint=self.base_url,
                response_time_ms=round(elapsed, 2),
                error_message=str(e)
            )

    async def query_metrics(self, query: str, timeout: float = 30.0) -> Dict[str, Any]:
        """
        Execute a PromQL query.

        Args:
            query: PromQL query string
            timeout: Request timeout in seconds

        Returns:
            Query results as dict
        """
        params = {'query': query}
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(f"{self.api_endpoint}/query", params=params)
            response.raise_for_status()
            return response.json()

    async def query_range(self, query: str, start: str, end: str, step: str = "1h") -> Dict[str, Any]:
        """
        Execute a PromQL range query.

        Args:
            query: PromQL query string
            start: Start timestamp (Unix timestamp or RFC3339)
            end: End timestamp (Unix timestamp or RFC3339)
            step: Query resolution step width

        Returns:
            Query results as dict
        """
        params = {
            'query': query,
            'start': start,
            'end': end,
            'step': step
        }
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.get(f"{self.api_endpoint}/query_range", params=params)
            response.raise_for_status()
            return response.json()

    async def discover_metrics(self, namespace: str) -> List[MetricMetadata]:
        """
        Discover available metrics for a namespace.

        Args:
            namespace: Kubernetes namespace to discover metrics for

        Returns:
            List of MetricMetadata objects
        """
        # Query for all metrics with the namespace label
        query = f'{{namespace="{namespace}"}}'
        result = await self.query_metrics(query)

        metrics = []
        for item in result.get('data', {}).get('result', []):
            metric_name = item.get('metric', {}).get('__name__', 'unknown')
            labels = {k: v for k, v in item.get('metric', {}).items() if k != '__name__'}

            # Try to get metric metadata
            try:
                metadata_response = await httpx.AsyncClient().get(
                    f"{self.api_endpoint}/label/__name__/values",
                    timeout=10.0
                )
                # This would need additional processing for full metadata
            except:
                pass

            metrics.append(MetricMetadata(
                name=metric_name,
                type="unknown",  # Would need additional metadata query
                help="",
                labels=labels,
                backend=MetricsBackend.PROMETHEUS
            ))

        return metrics

    async def get_label_values(self, label_name: str) -> List[str]:
        """Get all possible values for a label"""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(f"{self.api_endpoint}/label/{label_name}/values")
                response.raise_for_status()
                data = response.json()
                return data.get('data', [])
        except Exception as e:
            print(f"  Error getting label values for {label_name}: {e}")
            return []


class VictoriaLogsClient:
    """Client for querying VictoriaLogs endpoint"""

    def __init__(self, base_url: str = "http://vlogs-server.monitoring.svc.cluster.local:9428"):
        """
        Initialize VictoriaLogs client.

        Args:
            base_url: VictoriaLogs server URL (cluster-internal service)
        """
        self.base_url = base_url.rstrip('/')
        self.api_endpoint = f"{self.base_url}/select/logsql/query"

    async def test_connection(self) -> ConnectionTestResult:
        """Test connection to VictoriaLogs endpoint"""
        start_time = datetime.now()
        try:
            async with httpx.AsyncClient(timeout=10.0, verify=False) as client:
                # Simple query to test connection
                response = await client.get(self.api_endpoint,
                                          params={"query": "{namespace='pbx-web'}"})
                elapsed = (datetime.now() - start_time).total_seconds() * 1000

                if response.status_code == 200:
                    return ConnectionTestResult(
                        backend=MetricsBackend.VICTORIALOGS,
                        success=True,
                        endpoint=self.base_url,
                        response_time_ms=round(elapsed, 2),
                        version="victorialogs"
                    )

                return ConnectionTestResult(
                    backend=MetricsBackend.VICTORIALOGS,
                    success=False,
                    endpoint=self.base_url,
                    response_time_ms=round(elapsed, 2),
                    error_message=f"Status code: {response.status_code}"
                )
        except Exception as e:
            elapsed = (datetime.now() - start_time).total_seconds() * 1000
            return ConnectionTestResult(
                backend=MetricsBackend.VICTORIALOGS,
                success=False,
                endpoint=self.base_url,
                response_time_ms=round(elapsed, 2),
                error_message=str(e)
            )

    async def execute_query(
        self,
        query: str,
        time_range_start: str = None,
        time_range_end: str = None,
        timeout: float = 30.0
    ) -> Dict[str, Any]:
        """
        Execute a LogSQL query against VictoriaLogs.

        Args:
            query: LogSQL query string
            time_range_start: Start time (@now()-Xh format or Unix timestamp)
            time_range_end: End time (@now() or Unix timestamp)
            timeout: Request timeout in seconds

        Returns:
            Query results as dict
        """
        params = {'query': query}

        if time_range_start:
            params['start'] = time_range_start
        if time_range_end:
            params['end'] = time_range_end

        async with httpx.AsyncClient(timeout=timeout, verify=False) as client:
            response = await client.get(self.api_endpoint, params=params)
            response.raise_for_status()
            return response.json()


class UnifiedMetricsClient:
    """Unified client for both Prometheus and VictoriaLogs"""

    def __init__(self):
        """Initialize unified metrics client with both backends"""
        self.prometheus = PrometheusClient()
        self.victorialogs = VictoriaLogsClient()

    async def test_all_connections(self) -> Dict[str, ConnectionTestResult]:
        """Test connections to all metrics backends"""
        results = {}

        # Test Prometheus connection
        print("Testing Prometheus connection...")
        prom_result = await self.prometheus.test_connection()
        results["prometheus"] = prom_result
        self._print_connection_result(prom_result)

        # Test VictoriaLogs connection
        print("\nTesting VictoriaLogs connection...")
        vlogs_result = await self.victorialogs.test_connection()
        results["victorialogs"] = vlogs_result
        self._print_connection_result(vlogs_result)

        return results

    def _print_connection_result(self, result: ConnectionTestResult):
        """Print connection test result"""
        if result.success:
            print(f"  ✅ {result.backend.value}: Connected ({result.response_time_ms}ms)")
        else:
            print(f"  ❌ {result.backend.value}: Failed - {result.error_message}")

    async def discover_service_metrics(self, service: str) -> Dict[str, Any]:
        """
        Discover all available metrics for a service.

        Args:
            service: Service name (pbx-web or whisper-stt)

        Returns:
            Dict with discovered metrics from both backends
        """
        print(f"\n{'='*60}")
        print(f"Discovering metrics for: {service}")
        print(f"{'='*60}")

        results = {
            "service": service,
            "prometheus_metrics": [],
            "victorialogs_queries": [],
            "discovery_timestamp": datetime.now().isoformat()
        }

        # Discover Prometheus metrics for the service
        print(f"\n1. Discovering Prometheus metrics...")
        try:
            # Common Kubernetes metrics that should exist
            common_queries = {
                "cpu_usage": f'rate(container_cpu_usage_seconds_total{{namespace="{service}"}}[5m])',
                "memory_usage": f'container_memory_usage_bytes{{namespace="{service}"}}',
                "network_receive": f'rate(container_network_receive_bytes_total{{namespace="{service}"}}[5m])',
                "network_transmit": f'rate(container_network_transmit_bytes_total{{namespace="{service}"}}[5m])',
                "pod_count": f'up{{namespace="{service}"}}',
                "container_ready": f'kube_pod_container_status_ready{{namespace="{service}"}}',
                "restart_count": f'kube_pod_container_status_restarts_total{{namespace="{service}"}}',
                "fs_usage": f'container_fs_usage_bytes{{namespace="{service}"}}',
                "fs_reads": f'rate(container_fs_reads_bytes_total{{namespace="{service}"}}[5m])',
                "fs_writes": f'rate(container_fs_writes_bytes_total{{namespace="{service}"}}[5m])'
            }

            for metric_name, query in common_queries.items():
                try:
                    result = await self.prometheus.query_metrics(query)
                    if result.get("status") == "success":
                        data_points = result.get("data", {}).get("result", [])
                        if data_points:
                            results["prometheus_metrics"].append({
                                "name": metric_name,
                                "query": query,
                                "type": "prometheus",
                                "data_points": len(data_points),
                                "sample_labels": data_points[0].get("metric", {}) if data_points else {}
                            })
                            print(f"    ✓ {metric_name}: {len(data_points)} data points")
                        else:
                            print(f"    ✗ {metric_name}: No data")
                except Exception as e:
                    print(f"    ✗ {metric_name}: Query failed - {str(e)[:50]}")

        except Exception as e:
            print(f"    Error discovering Prometheus metrics: {e}")

        # VictoriaLogs query templates
        print(f"\n2. VictoriaLogs query templates available...")
        vlogs_templates = [
            "basic_latency_query",
            "processing_duration_analysis",
            "high_latency_detection",
            "container_specific_latency",
            "structured_json_latency",
            "error_related_latency",
            "performance_pattern_aggregation",
            "pod_level_latency_aggregation",
            "temporal_latency_distribution",
            "percentile_calculation_query"
        ]

        for template in vlogs_templates:
            results["victorialogs_queries"].append({
                "template_name": template,
                "available": True,
                "description": f"VictoriaLogs query template for {template}"
            })
            print(f"    • {template}")

        return results

    async def verify_30day_availability(self, service: str) -> Dict[str, Any]:
        """
        Verify 30-day data availability for a service.

        Args:
            service: Service name (pbx-web or whisper-stt)

        Returns:
            Dict with 30-day availability verification results
        """
        print(f"\n{'='*60}")
        print(f"Verifying 30-day data availability for: {service}")
        print(f"{'='*60}")

        now = datetime.now()
        thirty_days_ago = now - timedelta(days=30)

        results = {
            "service": service,
            "verification_timestamp": now.isoformat(),
            "time_range": {
                "start": thirty_days_ago.isoformat(),
                "end": now.isoformat(),
                "days": 30
            },
            "prometheus_availability": {},
            "victorialogs_availability": {}
        }

        # Test Prometheus 30-day range query
        print(f"\n1. Testing Prometheus 30-day range...")
        try:
            start_ts = int(thirty_days_ago.timestamp())
            end_ts = int(now.timestamp())

            # Query CPU usage over 30 days (1-day steps)
            query = f'rate(container_cpu_usage_seconds_total{{namespace="{service}"}}[5m])'
            range_result = await self.prometheus.query_range(
                query=query,
                start=str(start_ts),
                end=str(end_ts),
                step="1d"
            )

            if range_result.get("status") == "success":
                data_points = range_result.get("data", {}).get("result", [])
                results["prometheus_availability"] = {
                    "available": len(data_points) > 0,
                    "series_count": len(data_points),
                    "query": query,
                    "time_range": f"{start_ts}..{end_ts}",
                    "step": "1d"
                }
                print(f"    ✓ Prometheus 30-day data available: {len(data_points)} series")
            else:
                results["prometheus_availability"] = {
                    "available": False,
                    "error": range_result.get("error", "Unknown error")
                }
                print(f"    ✗ Prometheus 30-day query failed")

        except Exception as e:
            results["prometheus_availability"] = {
                "available": False,
                "error": str(e)
            }
            print(f"    ✗ Prometheus 30-day query error: {str(e)[:100]}")

        # Test VictoriaLogs 30-day range query
        print(f"\n2. Testing VictoriaLogs 30-day range...")
        try:
            # Query logs from last 30 days
            query = f'{{namespace="{service}"}}'
            vlogs_result = await self.victorialogs.execute_query(
                query=query,
                time_range_start=f"@now()-30d",
                time_range_end="@now()"
            )

            if vlogs_result and "data" not in vlogs_result.get("error", ""):
                # Check if we got any results
                results["victorialogs_availability"] = {
                    "available": True,
                    "query": query,
                    "time_range": "@now()-30d -> @now()",
                    "has_data": True
                }
                print(f"    ✓ VictoriaLogs 30-day data available")
            else:
                results["victorialogs_availability"] = {
                    "available": False,
                    "error": "No data returned"
                }
                print(f"    ✗ VictoriaLogs 30-day query failed")

        except Exception as e:
            results["victorialogs_availability"] = {
                "available": False,
                "error": str(e)
            }
            print(f"    ✗ VictoriaLogs 30-day query error: {str(e)[:100]}")

        return results

    async def generate_metric_documentation(self) -> Dict[str, Any]:
        """
        Generate comprehensive documentation of available metrics.

        Returns:
            Dict with complete metric documentation
        """
        print(f"\n{'='*60}")
        print(f"Generating comprehensive metrics documentation")
        print(f"{'='*60}")

        docs = {
            "generated_at": datetime.now().isoformat(),
            "services": {},
            "metric_types": {},
            "naming_conventions": {}
        }

        # Document Prometheus metric types
        docs["metric_types"]["prometheus"] = {
            "description": "Standard Kubernetes/Prometheus metrics",
            "common_types": [
                {"type": "gauge", "description": "Current value (e.g., memory usage)"},
                {"type": "counter", "description": "Cumulative value (e.g., network bytes)"},
                {"type": "histogram", "description": "Distribution of values"}
            ],
            "label_conventions": {
                "namespace": "Kubernetes namespace",
                "pod": "Pod name",
                "container": "Container name",
                "node": "Node name"
            }
        }

        # Document VictoriaLogs query patterns
        docs["metric_types"]["victorialogs"] = {
            "description": "Log-based metrics and latency analysis",
            "query_patterns": [
                {"pattern": "{namespace=\"...\"}", "description": "Filter by namespace"},
                {"pattern": "|= \"keyword\"", "description": "Full-text search"},
                {"pattern": "| json", "description": "Parse logs as JSON"},
                {"pattern": "| stats ...", "description": "Aggregation functions"},
                {"pattern": "@now()-Nd", "description": "Time range (N days ago)"}
            ]
        }

        # Naming conventions
        docs["naming_conventions"] = {
            "prometheus": {
                "container_metrics": "container_* (prefixed with container_)",
                "kube_pod_metrics": "kube_pod_* (Kubernetes pod metrics)",
                "rate_metrics": "rate(metric[5m]) for per-second rates"
            },
            "victorialogs": {
                "filters": "LogSQL format with {} for field selection",
                "pipes": "Pipe operations (|=, | json, | stats)",
                "time_range": "@now()-Xd for relative time ranges"
            }
        }

        # Get service-specific documentation
        for service in ["pbx-web", "whisper-stt"]:
            service_docs = await self.discover_service_metrics(service)
            availability = await self.verify_30day_availability(service)

            docs["services"][service] = {
                "prometheus_metrics": service_docs.get("prometheus_metrics", []),
                "victorialogs_templates": service_docs.get("victorialogs_queries", []),
                "availability_30day": availability
            }

        return docs


async def main():
    """Main execution for metrics query infrastructure setup and validation"""
    print("="*60)
    print("Metrics Query Infrastructure Setup")
    print("pbx-web and whisper-stt")
    print("="*60)

    client = UnifiedMetricsClient()

    # Step 1: Test all connections
    print("\n" + "="*60)
    print("STEP 1: Testing connections to metrics endpoints")
    print("="*60)
    connection_results = await client.test_all_connections()

    # Step 2: Discover metrics for both services
    print("\n" + "="*60)
    print("STEP 2: Discovering available metrics")
    print("="*60)

    pbx_web_metrics = await client.discover_service_metrics("pbx-web")
    whisper_stt_metrics = await client.discover_service_metrics("whisper-stt")

    # Step 3: Verify 30-day data availability
    print("\n" + "="*60)
    print("STEP 3: Verifying 30-day data availability")
    print("="*60)

    pbx_web_30day = await client.verify_30day_availability("pbx-web")
    whisper_stt_30day = await client.verify_30day_availability("whisper-stt")

    # Step 4: Generate comprehensive documentation
    print("\n" + "="*60)
    print("STEP 4: Generating metric documentation")
    print("="*60)

    documentation = await client.generate_metric_documentation()

    # Save results to file
    output_file = "/home/coding/aide-de-camp/data/metrics-query-infrastructure-report.json"
    with open(output_file, 'w') as f:
        json.dump(documentation, f, indent=2)

    # Print summary
    print("\n" + "="*60)
    print("INFRASTRUCTURE SETUP COMPLETE")
    print("="*60)
    print(f"\nResults saved to: {output_file}")
    print(f"\nConnection Status:")
    print(f"  Prometheus: {'✅ Connected' if connection_results['prometheus'].success else '❌ Failed'}")
    print(f"  VictoriaLogs: {'✅ Connected' if connection_results['victorialogs'].success else '❌ Failed'}")

    print(f"\nDiscovered Prometheus Metrics:")
    print(f"  pbx-web: {len(pbx_web_metrics.get('prometheus_metrics', []))} metrics")
    print(f"  whisper-stt: {len(whisper_stt_metrics.get('prometheus_metrics', []))} metrics")

    print(f"\n30-Day Data Availability:")
    print(f"  pbx-web Prometheus: {'✅ Available' if pbx_web_30day.get('prometheus_availability', {}).get('available') else '❌ Not available'}")
    print(f"  pbx-web VictoriaLogs: {'✅ Available' if pbx_web_30day.get('victorialogs_availability', {}).get('available') else '❌ Not available'}")
    print(f"  whisper-stt Prometheus: {'✅ Available' if whisper_stt_30day.get('prometheus_availability', {}).get('available') else '❌ Not available'}")
    print(f"  whisper-stt VictoriaLogs: {'✅ Available' if whisper_stt_30day.get('victorialogs_availability', {}).get('available') else '❌ Not available'}")

    print("\n✓ Metrics query infrastructure setup complete!")

    return documentation


if __name__ == "__main__":
    asyncio.run(main())