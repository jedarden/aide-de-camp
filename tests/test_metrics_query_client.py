"""Unit tests for the Prometheus/VictoriaLogs query client."""

from __future__ import annotations

import json

import httpx

from src.metrics_query_client import (
    MetricsQueryClient,
    PrometheusClient,
    VictoriaLogsClient,
    _json_lines,
)


def test_json_lines_decodes_victorialogs_response() -> None:
    assert _json_lines('{"count":"2"}\n{"count":"3"}\n') == [
        {"count": "2"},
        {"count": "3"},
    ]


def test_prometheus_inventory_and_availability_use_prometheus_shapes() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/-/healthy":
            return httpx.Response(200, text="Prometheus Server is Healthy.")
        if request.url.path == "/api/v1/status/buildinfo":
            return httpx.Response(200, json={"status": "success", "data": {"version": "3.10.0"}})
        if request.url.path == "/api/v1/status/flags":
            return httpx.Response(
                200,
                json={"status": "success", "data": {"storage.tsdb.retention.time": "10d"}},
            )
        if request.url.path == "/api/v1/labels":
            return httpx.Response(
                200,
                json={"status": "success", "data": ["__name__", "namespace", "pod", "container", "job"]},
            )
        if request.url.path == "/api/v1/metadata":
            metric = request.url.params.get("metric")
            types = {
                "container_cpu_usage_seconds_total": "counter",
                "container_memory_working_set_bytes": "gauge",
                "kube_pod_container_status_restarts_total": "counter",
                "kube_pod_info": "gauge",
            }
            return httpx.Response(
                200,
                json={
                    "status": "success",
                    "data": {
                        metric: [{"type": types[metric], "help": "test", "unit": ""}]
                    }
                    if metric in types
                    else {},
                },
            )
        if request.url.path == "/api/v1/query":
            query = request.url.params.get("query")
            if query == "time()":
                return httpx.Response(200, json={"status": "success", "data": {"result": [1000, "1000"]}})
            if query == 'count by (__name__) ({namespace="pbx-web"})':
                result = [
                    {"metric": {"__name__": name}, "value": [1000, "1"]}
                    for name in (
                        "container_cpu_usage_seconds_total",
                        "container_memory_working_set_bytes",
                        "kube_pod_container_status_restarts_total",
                        "kube_pod_info",
                        "prober_probe_duration_seconds_bucket",
                    )
                ]
                return httpx.Response(200, json={"status": "success", "data": {"result": result}})
        if request.url.path == "/api/v1/query_range":
            values = [[1000 + (index * 3600), "1"] for index in range(3)]
            return httpx.Response(
                200,
                json={"status": "success", "data": {"result": [{"metric": {}, "values": values}]}},
            )
        raise AssertionError(f"unexpected request: {request.method} {request.url}")

    with PrometheusClient("http://metrics", transport=httpx.MockTransport(handler)) as client:
        inventory = client.inventory("pbx-web")
        assert inventory["metric_family_count"] == 5
        assert inventory["all_expected_metrics_available"] is True
        assert inventory["all_required_labels_available"] is True
        assert inventory["expected_metrics"][-1]["observed_type"].startswith("histogram")

        availability = client.availability("pbx-web", days=0, step=3600)
        assert availability.data_available is True
        assert availability.sample_points == 3
        assert availability.internal_gaps == 0


def test_victorialogs_stats_query_parses_ndjson() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/health":
            return httpx.Response(200, text="OK")
        assert request.url.path == "/select/logsql/query"
        assert "stats" in request.url.params["query"]
        return httpx.Response(
            200,
            text=json.dumps(
                {
                    "count": "12",
                    "oldest": "2026-07-13T00:00:00Z",
                    "newest": "2026-08-10T00:00:00Z",
                }
            )
            + "\n",
        )

    with VictoriaLogsClient("http://logs", transport=httpx.MockTransport(handler)) as client:
        result = client.availability(
            "pbx-web", start="2026-07-11T00:00:00Z", end="2026-08-10T00:00:00Z"
        )
        assert result["log_count"] == 12
        assert result["data_available"] is True
        assert result["full_requested_window"] is False


def test_unified_client_reads_service_namespaces() -> None:
    config = {
        "cluster": "test",
        "prometheus": {"base_url": "http://prom"},
        "victorialogs": {"base_url": "http://logs"},
        "services": {
            "one": {"namespace": "first"},
            "two": {"namespace": "second"},
        },
    }
    with MetricsQueryClient(config) as client:
        assert client.namespaces == ("first", "second")
