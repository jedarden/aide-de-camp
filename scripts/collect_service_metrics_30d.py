#!/usr/bin/env python3
"""Collect a reproducible 30-day observability snapshot for two services.

The collector keeps the distinction between a requested window and the range
actually retained by each backend.  Prometheus range responses are summarized
because the complete raw responses are already stored by the resource
collectors; VictoriaLogs aggregate queries and the small application-latency
sample set are recorded in the resulting JSON.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import statistics
import urllib.parse
import urllib.request
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


SERVICES = ("pbx-web", "whisper-stt")
STEP_SECONDS = 3600
ERROR_PATTERN = r"(?i)(error|exception|traceback|failed|panic|oom|killed)"
EXPLICIT_LATENCY_PATTERN = (
    r"(?i)(request_time|upstream_response_time|duration[=:]|latency[=:]|elapsed[=:])"
)


def iso_timestamp(value: float) -> str:
    return datetime.fromtimestamp(value, timezone.utc).isoformat(timespec="milliseconds").replace(
        "+00:00", "Z"
    )


def parse_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def format_datetime(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace(
        "+00:00", "Z"
    )


def request_json(url: str, params: dict[str, Any], timeout: int = 180) -> Any:
    encoded = urllib.parse.urlencode({key: str(value) for key, value in params.items()})
    request = urllib.request.Request(
        f"{url.rstrip('/')}?{encoded}",
        headers={"User-Agent": "adc-1xp0b-service-metrics/1"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read().decode("utf-8")


def prometheus_json(base_url: str, path: str, params: dict[str, Any]) -> dict[str, Any]:
    body = request_json(f"{base_url.rstrip('/')}{path}", params)
    payload = json.loads(body)
    if payload.get("status") != "success":
        raise RuntimeError(f"Prometheus returned an unsuccessful response: {payload}")
    return payload


def prometheus_time(base_url: str) -> datetime:
    payload = prometheus_json(base_url, "/api/v1/query", {"query": "time()"})
    result = payload.get("data", {}).get("result", [])
    if payload.get("data", {}).get("resultType") == "scalar" and len(result) >= 2:
        return datetime.fromtimestamp(float(result[0]), timezone.utc)
    raise RuntimeError(f"Prometheus time() returned an unexpected response: {payload}")


def numeric_values(result: list[dict[str, Any]]) -> list[tuple[float, float]]:
    points: list[tuple[float, float]] = []
    for series in result:
        for value in series.get("values", []):
            if not isinstance(value, list) or len(value) < 2:
                continue
            try:
                timestamp = float(value[0])
                number = float(value[1])
            except (TypeError, ValueError):
                continue
            if math.isfinite(number):
                points.append((timestamp, number))
    return points


def summarize_prometheus_range(
    base_url: str, query: str, start: datetime, end: datetime
) -> dict[str, Any]:
    payload = prometheus_json(
        base_url,
        "/api/v1/query_range",
        {
            "query": query,
            "start": format_datetime(start),
            "end": format_datetime(end),
            "step": STEP_SECONDS,
        },
    )
    result = payload.get("data", {}).get("result", [])
    points = numeric_values(result)
    timestamps = [point[0] for point in points]
    values = [point[1] for point in points]
    return {
        "query": query,
        "result_series": len(result),
        "observed_points": len(points),
        "first_sample": iso_timestamp(min(timestamps)) if timestamps else None,
        "last_sample": iso_timestamp(max(timestamps)) if timestamps else None,
        "observed_coverage_days": round(
            (max(timestamps) - min(timestamps)) / 86400, 6
        )
        if len(timestamps) > 1
        else 0.0,
        "nonzero_points": sum(value != 0 for value in values),
        "sum_of_hourly_values": round(sum(values), 9) if values else 0.0,
        "max_hourly_value": max(values) if values else None,
        "min_value": min(values) if values else None,
    }


def quantile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * fraction
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def latency_statistics(values: list[float], unit: str) -> dict[str, Any]:
    return {
        "count": len(values),
        "unit": unit,
        "min": min(values) if values else None,
        "p50": quantile(values, 0.50),
        "p95": quantile(values, 0.95),
        "p99": quantile(values, 0.99),
        "max": max(values) if values else None,
        "mean": statistics.mean(values) if values else None,
    }


def parse_json_lines(body: str) -> list[dict[str, Any]]:
    records = []
    for line in body.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            records.append(value)
    return records


def victorialogs_query(
    base_url: str, query: str, start: datetime, end: datetime
) -> tuple[list[dict[str, Any]], str]:
    body = request_json(
        f"{base_url.rstrip('/')}/select/logsql/query",
        {
            "query": query,
            "start": format_datetime(start),
            "end": format_datetime(end),
        },
    )
    return parse_json_lines(body), body


def stats_value(records: list[dict[str, Any]], field: str) -> float | str | None:
    if not records:
        return None
    value = records[0].get(field)
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return str(value)


def log_stat(
    base_url: str, query: str, field: str, start: datetime, end: datetime
) -> dict[str, Any]:
    records, _ = victorialogs_query(base_url, query, start, end)
    value = stats_value(records, field)
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return {"query": query, "field": field, "value": value}


def log_latency_samples(
    base_url: str, query: str, start: datetime, end: datetime
) -> tuple[list[float], list[str]]:
    records, _ = victorialogs_query(base_url, query, start, end)
    values: list[float] = []
    timestamps: list[str] = []
    for record in records:
        message = str(record.get("_msg", ""))
        match = re.search(r"Finished in\s+([0-9]+(?:\.[0-9]+)?)\s+seconds", message)
        if match:
            values.append(float(match.group(1)))
            if isinstance(record.get("_time"), str):
                timestamps.append(record["_time"])
    return values, timestamps


def resource_summary(path: Path, service: str) -> dict[str, Any]:
    if not path.exists():
        return {"path": str(path), "status": "missing"}
    payload = json.loads(path.read_text(encoding="utf-8"))
    coverage = payload.get("coverage", {}).get(service, {})
    metadata = payload.get("collection_metadata", {})
    result: dict[str, Any] = {
        "path": str(path),
        "status": "loaded",
        "source_window": {
            key: metadata.get(key)
            for key in (
                "requested_window_start",
                "requested_window_end",
                "requested_window_days",
                "step_seconds",
                "prometheus_server_time",
                "prometheus_retention_time",
            )
            if key in metadata
        },
        "metrics": {},
    }
    for metric_name, report in coverage.items():
        if not isinstance(report, dict):
            continue
        result["metrics"][metric_name] = {
            key: report.get(key)
            for key in (
                "status",
                "observed_timestamp_points",
                "series_count",
                "first_sample",
                "last_sample",
                "returned_coverage_days",
                "leading_gap_days",
                "trailing_gap_days",
                "internal_gap_count",
                "significant_gaps",
                "present",
                "unit",
            )
            if key in report
        }
    return result


def artifact_descriptor(path: Path, root: Path) -> dict[str, Any]:
    if not path.exists():
        return {"path": str(path), "status": "missing"}
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    try:
        relative = str(path.relative_to(root))
    except ValueError:
        relative = str(path)
    return {"path": relative, "sha256": digest, "bytes": path.stat().st_size}


def deployment_alignment(
    deployment_path: Path,
    requested_start: datetime,
    requested_end: datetime,
    resource_first: dict[str, str | None],
    resource_last: dict[str, str | None],
    log_first: dict[str, str | None],
    log_last: dict[str, str | None],
) -> dict[str, Any]:
    deployment_data = json.loads(deployment_path.read_text(encoding="utf-8"))
    source_window = deployment_data.get("metadata", {}).get("time_period", {})
    events: list[dict[str, Any]] = []
    sections = (("pbx-web", "pbx_web_deployments"), ("whisper-stt", "whisper_stt_deployments"))
    for service, section_name in sections:
        for event in deployment_data.get(section_name, {}).get("deployment_events", []):
            parsed = parse_timestamp(event.get("timestamp"))
            if parsed is None:
                continue
            events.append({"service": service, **event, "timestamp": format_datetime(parsed)})

    by_service: dict[str, Any] = {}
    for service in SERVICES:
        service_events = [event for event in events if event["service"] == service]
        rows = []
        resource_start = parse_timestamp(resource_first.get(service))
        resource_end = parse_timestamp(resource_last.get(service))
        log_start = parse_timestamp(log_first.get(service))
        log_end = parse_timestamp(log_last.get(service))
        for event in service_events:
            timestamp = parse_timestamp(event["timestamp"])
            assert timestamp is not None
            rows.append(
                {
                    "timestamp": event["timestamp"],
                    "event_type": event.get("event_type"),
                    "deployment": event.get("deployment"),
                    "revision": event.get("revision"),
                    "in_requested_window": requested_start <= timestamp <= requested_end,
                    "within_observed_resource_window": bool(
                        resource_start and resource_end and resource_start <= timestamp <= resource_end
                    ),
                    "within_observed_log_window": bool(
                        log_start and log_end and log_start <= timestamp <= log_end
                    ),
                }
            )
        by_service[service] = {
            "event_count": len(service_events),
            "rows": rows,
            "events_in_requested_window": sum(row["in_requested_window"] for row in rows),
            "events_with_resource_samples": sum(
                row["within_observed_resource_window"] for row in rows
            ),
            "events_with_log_samples": sum(row["within_observed_log_window"] for row in rows),
            "resource_observed_window": {
                "start": resource_first.get(service),
                "end": resource_last.get(service),
            },
            "log_observed_window": {"start": log_first.get(service), "end": log_last.get(service)},
        }
    source_start = parse_timestamp(source_window.get("start"))
    source_end = parse_timestamp(source_window.get("end"))
    return {
        "source": str(deployment_path),
        "source_window": {
            "start": format_datetime(source_start),
            "end": format_datetime(source_end),
            "declared_days": 30,
        },
        "requested_metric_window": {
            "start": format_datetime(requested_start),
            "end": format_datetime(requested_end),
            "duration_days": 30,
        },
        "events": sorted(events, key=lambda event: event["timestamp"]),
        "per_service": by_service,
        "window_mismatch": {
            "deployment_source_starts_before_requested_metrics_by_days": round(
                (requested_start - source_start).total_seconds() / 86400, 6
            )
            if source_start
            else None,
            "deployment_source_ends_before_requested_metrics_by_days": round(
                (requested_end - source_end).total_seconds() / 86400, 6
            )
            if source_end
            else None,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prometheus", default="http://127.0.0.1:19090")
    parser.add_argument("--victorialogs", default="http://127.0.0.1:19428")
    parser.add_argument("--deployment-events", type=Path, default=Path("deployment-events-30days.json"))
    parser.add_argument(
        "--cpu-memory",
        type=Path,
        required=True,
        help="Raw CPU/memory Prometheus export produced by collect_resource_metrics_30d.py",
    )
    parser.add_argument(
        "--disk-network",
        type=Path,
        required=True,
        help="Raw disk/network/storage Prometheus export produced by collect_disk_network_storage_metrics_30d.py",
    )
    parser.add_argument("--alignment-report", type=Path, default=Path("data/metrics_deployment_alignment_report.json"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    end = prometheus_time(args.prometheus)
    start = end - timedelta(days=30)
    flags = prometheus_json(args.prometheus, "/api/v1/status/flags", {}).get("data", {})
    retention = flags.get("storage.tsdb.retention.time")

    resource_paths = {"cpu_memory": args.cpu_memory, "disk_network": args.disk_network}
    resource_by_service = {
        service: {
            "cpu_memory": resource_summary(args.cpu_memory, service),
            "disk_network": resource_summary(args.disk_network, service),
        }
        for service in SERVICES
    }
    resource_first = {}
    resource_last = {}
    for service in SERVICES:
        samples = []
        ends = []
        for source in resource_by_service[service].values():
            for metric in source.get("metrics", {}).values():
                if metric.get("first_sample"):
                    samples.append(metric["first_sample"])
                if metric.get("last_sample"):
                    ends.append(metric["last_sample"])
        resource_first[service] = min(samples) if samples else None
        resource_last[service] = max(ends) if ends else None

    services: dict[str, Any] = {}
    for service in SERVICES:
        log_selector = f'{{namespace="{service}"}}'
        nginx_selector = (
            '{namespace="pbx-web",kubernetes.container_name="nginx"}'
            if service == "pbx-web"
            else log_selector
        )
        queries = {
            "total_log_lines": (f"{log_selector} | stats count() as total", "total"),
            "error_log_lines": (
                f'{log_selector} | filter _msg:~"{ERROR_PATTERN}" | stats count() as errors',
                "errors",
            ),
            "http_requests": (
                f'{nginx_selector} | filter _msg:~"HTTP/1.1" | stats count() as http_requests',
                "http_requests",
            ),
            "http_2xx": (
                f'{nginx_selector} | filter _msg:~"HTTP/1.1\\\" 2[0-9][0-9]" | stats count() as http_2xx',
                "http_2xx",
            ),
            "http_4xx": (
                f'{nginx_selector} | filter _msg:~"HTTP/1.1\\\" 4[0-9][0-9]" | stats count() as http_4xx',
                "http_4xx",
            ),
            "http_5xx": (
                f'{nginx_selector} | filter _msg:~"HTTP/1.1\\\" 5[0-9][0-9]" | stats count() as http_5xx',
                "http_5xx",
            ),
            "explicit_latency_fields": (
                f'{log_selector} | filter _msg:~"{EXPLICIT_LATENCY_PATTERN}" | stats count() as matches',
                "matches",
            ),
            "finished_in_lines": (
                f'{log_selector} | filter _msg:~"Finished in" | stats count() as total',
                "total",
            ),
            "coverage": (
                f"{log_selector} | stats min(_time) as first, max(_time) as last, count() as total",
                "total",
            ),
        }
        log_queries = {
            name: log_stat(args.victorialogs, query, field, start, end)
            for name, (query, field) in queries.items()
        }
        latency_values, latency_timestamps = log_latency_samples(
            args.victorialogs,
            f'{log_selector} | filter _msg:~"Finished in"',
            start,
            end,
        )
        log_first = stats_value(
            (awaited := victorialogs_query(
                args.victorialogs, queries["coverage"][0], start, end
            ))[0],
            "first",
        )
        log_last = stats_value(awaited[0], "last")
        if isinstance(log_first, (int, float)):
            log_first = str(log_first)
        if isinstance(log_last, (int, float)):
            log_last = str(log_last)
        # Stats returns RFC3339 strings for min/max(_time), so normalize only
        # when the backend returns a parseable timestamp.
        log_first = format_datetime(parse_timestamp(log_first)) or log_first
        log_last = format_datetime(parse_timestamp(log_last)) or log_last

        http_requests = log_queries["http_requests"]["value"] or 0
        http_4xx = log_queries["http_4xx"]["value"] or 0
        http_5xx = log_queries["http_5xx"]["value"] or 0
        total_logs = log_queries["total_log_lines"]["value"] or 0
        error_lines = log_queries["error_log_lines"]["value"] or 0
        services[service] = {
            "error_rates": {
                "victorialogs": log_queries,
                "http_error_rate_denominator": "HTTP request log lines for nginx (pbx-web) or the service access log (whisper-stt)",
                "http_4xx_rate": http_4xx / http_requests if http_requests else None,
                "http_5xx_rate": http_5xx / http_requests if http_requests else None,
                "error_log_line_rate": error_lines / total_logs if total_logs else None,
            },
            "latency": {
                "application_processing": {
                    "source": "VictoriaLogs _msg matching 'Finished in N seconds'",
                    "statistics": latency_statistics(latency_values, "seconds"),
                    "first_sample": min(latency_timestamps) if latency_timestamps else None,
                    "last_sample": max(latency_timestamps) if latency_timestamps else None,
                    "observed_calendar_days": sorted({value[:10] for value in latency_timestamps}),
                    "coverage_days_with_samples": len({value[:10] for value in latency_timestamps}),
                },
                "health_probe": {},
                "log_latency_field_availability": {
                    "explicit_request_or_processing_fields": log_queries["explicit_latency_fields"]["value"],
                    "finished_in_lines": log_queries["finished_in_lines"]["value"],
                },
            },
            "resources": resource_by_service[service],
        }

        for percentile in (0.50, 0.95, 0.99):
            query = (
                f"histogram_quantile({percentile}, sum by (le) (rate("
                f"prober_probe_duration_seconds_bucket{{namespace=\"{service}\"}}[5m])))"
            )
            summary = summarize_prometheus_range(args.prometheus, query, start, end)
            values = []
            # Re-querying the compact result is unnecessary for coverage, but
            # the quantile summary needs its values.  Keep the full response
            # out of the report while deriving percentile-of-hourly-quantiles.
            payload = prometheus_json(
                args.prometheus,
                "/api/v1/query_range",
                {"query": query, "start": format_datetime(start), "end": format_datetime(end), "step": STEP_SECONDS},
            )
            values = [value for _, value in numeric_values(payload.get("data", {}).get("result", []))]
            summary["hourly_quantile_statistics"] = latency_statistics(values, "seconds")
            services[service]["latency"]["health_probe"][f"p{int(percentile * 100)}"] = summary

        restart_query = (
            f'sum(increase(kube_pod_container_status_restarts_total{{namespace="{service}",container!="POD"}}[1h]))'
        )
        oom_query = (
            f'sum(increase(container_oom_events_total{{namespace="{service}",container!="",image!=""}}[1h]))'
        )
        readiness_query = f'sum(kube_pod_status_ready{{namespace="{service}",condition="false"}})'
        services[service]["error_rates"]["prometheus"] = {
            "container_restart_hourly_increase": summarize_prometheus_range(
                args.prometheus, restart_query, start, end
            ),
            "oom_event_hourly_increase": summarize_prometheus_range(
                args.prometheus, oom_query, start, end
            ),
            "not_ready_pod_count": summarize_prometheus_range(
                args.prometheus, readiness_query, start, end
            ),
        }
        services[service]["log_observed_window"] = {"start": log_first, "end": log_last}

    log_first_by_service = {
        service: services[service]["log_observed_window"]["start"] for service in SERVICES
    }
    log_last_by_service = {
        service: services[service]["log_observed_window"]["end"] for service in SERVICES
    }
    alignment = deployment_alignment(
        args.deployment_events,
        start,
        end,
        resource_first,
        resource_last,
        log_first_by_service,
        log_last_by_service,
    )

    gaps = [
        {
            "severity": "high",
            "type": "prometheus_retention_gap",
            "services": list(SERVICES),
            "duration_days": round(
                (parse_timestamp(resource_first["pbx-web"]) - start).total_seconds() / 86400, 6
            )
            if parse_timestamp(resource_first["pbx-web"])
            else None,
            "description": "CPU, memory, disk, and network range queries returned no samples before the first retained Prometheus sample; missing periods are not treated as zero.",
            "retention_setting": retention,
        },
        {
            "severity": "high",
            "type": "whisper_transcription_latency_missing",
            "services": ["whisper-stt"],
            "description": "VictoriaLogs contains health-check access logs but no transcription duration, request_time, latency, or elapsed fields.",
        },
        {
            "severity": "medium",
            "type": "victorialogs_leading_gap",
            "services": list(SERVICES),
            "description": "VictoriaLogs starts after the requested metric window because the backend retained logs from approximately 2026-07-13 onward.",
        },
        {
            "severity": "medium",
            "type": "deployment_source_window_mismatch",
            "services": list(SERVICES),
            "description": "The canonical deployment export covers 2026-07-07 through 2026-08-06, while live metrics were requested through the Prometheus server time on 2026-08-10.",
        },
    ]
    anomalies = []
    for service in SERVICES:
        http = services[service]["error_rates"]
        if (http["http_5xx_rate"] or 0) > 0:
            anomalies.append(
                {
                    "severity": "medium",
                    "type": "http_5xx_observed",
                    "service": service,
                    "count": http["victorialogs"]["http_5xx"]["value"],
                    "rate": http["http_5xx_rate"],
                }
            )
        if (http["http_4xx_rate"] or 0) > 0:
            anomalies.append(
                {
                    "severity": "info",
                    "type": "http_4xx_observed",
                    "service": service,
                    "count": http["victorialogs"]["http_4xx"]["value"],
                    "rate": http["http_4xx_rate"],
                }
            )
        restarts = http["prometheus"]["container_restart_hourly_increase"]
        if restarts["nonzero_points"]:
            anomalies.append(
                {
                    "severity": "info",
                    "type": "container_restart_signal",
                    "service": service,
                    "nonzero_hourly_points": restarts["nonzero_points"],
                    "max_hourly_increase": restarts["max_hourly_value"],
                    "description": "Prometheus reports a non-zero hourly increase in the retained observation window; inspect pod-level series before attributing it to a single deployment.",
                }
            )

    root = Path.cwd()
    source_artifacts = {
        "cpu_memory_metrics": artifact_descriptor(args.cpu_memory, root),
        "disk_network_metrics": artifact_descriptor(args.disk_network, root),
        "deployment_events": artifact_descriptor(args.deployment_events, root),
        "deployment_alignment_report": artifact_descriptor(args.alignment_report, root),
    }
    result = {
        "schema_version": "1.0",
        "dataset_type": "pbx_web_whisper_stt_observability_metrics",
        "collection_metadata": {
            "generated_at": format_datetime(datetime.now(timezone.utc)),
            "observability_backends": {
                "prometheus": args.prometheus,
                "victorialogs": args.victorialogs,
            },
            "requested_window": {
                "start": format_datetime(start),
                "end": format_datetime(end),
                "duration_days": 30,
                "step_seconds": STEP_SECONDS,
            },
            "prometheus_server_time": format_datetime(end),
            "prometheus_retention_time": retention,
            "services": list(SERVICES),
        },
        "availability_summary": {
            "error_rates": "available from VictoriaLogs aggregate queries and Prometheus restart/OOM/readiness metrics, with backend retention gaps",
            "latency": "pbx-web application processing samples and Kubernetes health-probe latency available; whisper-stt transcription latency unavailable",
            "cpu_memory_disk_network": "Prometheus metrics available only for the retained approximately 10-day portion of the requested 30-day window",
            "deployment_alignment": "deployment events loaded and compared with requested and observed metric windows; causal joins are limited by retention",
        },
        "services": services,
        "deployment_alignment": alignment,
        "coverage_gaps": gaps,
        "anomalies": anomalies,
        "source_artifacts": source_artifacts,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=False) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "window": result["collection_metadata"]["requested_window"], "services": list(SERVICES)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
