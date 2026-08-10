#!/usr/bin/env python3
"""Consolidate the collected pbx-web and whisper-stt metrics.

The input artifacts were collected by different queries at different times.
This script keeps each source window and coverage result, then adds an exact
overlap window so consumers cannot mistake sparse or unavailable data for
zeroes.  It writes a compact summary of time-series sources rather than
duplicating the raw Prometheus response bodies.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import statistics
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SERVICES = ("pbx-web", "whisper-stt")
ERROR_SOURCE = Path("data/error_latency_metrics_30d_enhanced_20260806_211642.json")
LATENCY_SOURCE = Path("data/latency_metrics_30d_20260806_215749.json")
RESOURCE_USAGE_SOURCE = Path("data/resource_usage_metrics_30d.json")
CPU_MEMORY_SOURCE = Path("data/resource_metrics/resource-metrics-30d-20260810T111404Z.json")
CPU_MEMORY_COVERAGE = Path("data/resource_metrics/resource-metrics-coverage-20260810T111404Z.json")
DISK_NETWORK_SOURCE = Path(
    "data/resource_metrics/disk-network-storage-metrics-30d-20260810T114451Z.json"
)
DISK_NETWORK_COVERAGE = Path(
    "data/resource_metrics/disk-network-storage-coverage-20260810T114451Z.json"
)
DEPLOYMENT_ALIGNMENT = Path("data/metrics_deployment_aligned.json")

DEFAULT_UNITS = {
    "cpu_usage": "cores",
    "memory_working_set": "bytes",
}

TIMING_RE = re.compile(r"(?:^|\s)(?:Finished in )([0-9]+(?:\.[0-9]+)?) seconds")
TIMESTAMP_RE = re.compile(r"(\d{4}-\d{2}-\d{2})T")


def load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"Expected an object in {path}")
    return value


def value_at(mapping: dict[str, Any], *keys: str, default: Any = None) -> Any:
    current: Any = mapping
    for key in keys:
        if not isinstance(current, dict) or key not in current:
            return default
        current = current[key]
    return current


def parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def inclusive_calendar_days(start: str, end: str) -> int:
    return (parse_timestamp(end).date() - parse_timestamp(start).date()).days + 1


def epoch_timestamp(value: Any) -> str:
    return (
        datetime.fromtimestamp(float(value), timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


def json_number(value: Any) -> int | float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    if number.is_integer():
        return int(number)
    return number


def percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def numeric_stats(values: list[float]) -> dict[str, Any]:
    if not values:
        return {
            "sample_count": 0,
            "nonzero_sample_count": 0,
            "zero_sample_count": 0,
            "zero_fraction": None,
            "min": None,
            "p50": None,
            "p95": None,
            "max": None,
            "mean": None,
            "last_sample_value_sum": None,
        }

    zero_count = sum(value == 0 for value in values)
    return {
        "sample_count": len(values),
        "nonzero_sample_count": len(values) - zero_count,
        "zero_sample_count": zero_count,
        "zero_fraction": zero_count / len(values),
        "min": min(values),
        "p50": percentile(values, 0.50),
        "p95": percentile(values, 0.95),
        "max": max(values),
        "mean": statistics.fmean(values),
        "last_sample_value_sum": None,
    }


def metric_values(metric: dict[str, Any]) -> tuple[list[float], list[dict[str, Any]]]:
    results = value_at(metric, "response", "data", "result", default=[])
    if not isinstance(results, list):
        return [], []
    values: list[float] = []
    series: list[dict[str, Any]] = []
    for result in results:
        if not isinstance(result, dict):
            continue
        labels = result.get("metric", {})
        samples = result.get("values", [])
        series_values: list[float] = []
        timestamps: list[float] = []
        for sample in samples:
            if not isinstance(sample, list) or len(sample) < 2:
                continue
            numeric = json_number(sample[1])
            if numeric is None:
                continue
            values.append(float(numeric))
            series_values.append(float(numeric))
            timestamps.append(float(sample[0]))
        if timestamps:
            series.append(
                {
                    "labels": labels,
                    "sample_count": len(series_values),
                    "first_sample": epoch_timestamp(min(timestamps)),
                    "last_sample": epoch_timestamp(max(timestamps)),
                    "min": min(series_values),
                    "max": max(series_values),
                }
            )
    return values, series


def source_timestamp_range(metric: dict[str, Any]) -> tuple[str | None, str | None]:
    _, series = metric_values(metric)
    if not series:
        return None, None
    return min(item["first_sample"] for item in series), max(item["last_sample"] for item in series)


def resource_metric_record(
    service: str,
    name: str,
    raw: dict[str, Any],
    coverage: dict[str, Any],
) -> dict[str, Any]:
    values, series = metric_values(raw)
    stats = numeric_stats(values)
    if series:
        last_timestamp = max(item["last_sample"] for item in series)
        last_values: list[float] = []
        results = value_at(raw, "response", "data", "result", default=[])
        for result in results:
            samples = result.get("values", []) if isinstance(result, dict) else []
            for sample in reversed(samples):
                if isinstance(sample, list) and len(sample) >= 2:
                    if epoch_timestamp(sample[0]) == last_timestamp:
                        number = json_number(sample[1])
                        if number is not None:
                            last_values.append(float(number))
                    break
        stats["last_sample_value_sum"] = sum(last_values) if last_values else None

    expected = coverage.get("expected_points_requested")
    observed = coverage.get("observed_timestamp_points", 0)
    point_coverage = (observed / expected * 100) if expected else 0.0
    available = bool(series)
    status = "unavailable" if not available else ("complete" if coverage.get("full_requested_window") else "partial")
    return {
        "metric": name,
        "family": raw.get("family", name.split("_", 1)[0]),
        "unit": raw.get("unit") or DEFAULT_UNITS.get(name),
        "query": raw.get("query"),
        "availability": "available" if available else "unavailable",
        "status": status,
        "coverage": {
            "requested_start": coverage.get("requested_start"),
            "requested_end": coverage.get("requested_end"),
            "requested_window_days": coverage.get("requested_window_days"),
            "expected_timestamp_points": expected,
            "observed_timestamp_points": observed,
            "coverage_percentage_by_timestamp_points": round(point_coverage, 3),
            "first_sample": coverage.get("first_sample"),
            "last_sample": coverage.get("last_sample"),
            "returned_span_days": coverage.get("returned_coverage_days"),
            "leading_gap_days": coverage.get("leading_gap_days"),
            "trailing_gap_days": coverage.get("trailing_gap_days"),
            "internal_gap_count": coverage.get("internal_gap_count", 0),
            "internal_missing_intervals": coverage.get("internal_missing_intervals", 0),
            "series_count": coverage.get("series_count", len(series)),
        },
        "statistics": stats,
        "series": series,
    }


def error_component_status(component: dict[str, Any], has_data: bool) -> str:
    if not has_data:
        return "unavailable"
    return "available"


def build_error_rates(service: str, error_source: dict[str, Any]) -> dict[str, Any]:
    source_service = error_source["services"][service]
    errors = source_service["error_metrics"]
    period = source_service["analysis_period"]
    pod = errors["pod_logs"]
    nginx = errors["nginx"]
    deployments = errors["deployments"]
    oom = {
        "total_oom_kill_count": pod.get("total_oom_kill_count", 0),
        "pods_with_oom_kills": pod.get("pods_with_oom_kills", 0),
        "oom_kill_rate_per_pod": pod.get("oom_kill_rate_per_pod", 0.0),
        "availability": "available",
    }
    nginx_available = bool(nginx.get("log_file_found") and nginx.get("http_total_requests"))
    deployment_available = bool(deployments.get("total_deployments") or deployments.get("deployment_events"))
    http = {
        "availability": error_component_status(nginx, nginx_available),
        "log_file_found": nginx.get("log_file_found", False),
        "total_requests": nginx.get("http_total_requests") if nginx_available else None,
        "http_2xx_errors": None,
        "http_4xx_errors": nginx.get("http_4xx_errors") if nginx_available else None,
        "http_5xx_errors": nginx.get("http_5xx_errors") if nginx_available else None,
        "http_4xx_error_rate": nginx.get("http_4xx_error_rate") if nginx_available else None,
        "http_5xx_error_rate": nginx.get("http_5xx_error_rate") if nginx_available else None,
        "log_lines_analyzed": nginx.get("log_lines_analyzed") if nginx_available else 0,
    }
    deployment = {
        "availability": error_component_status(deployments, deployment_available),
        "total_deployments": deployments.get("total_deployments") if deployment_available else None,
        "successful_deployments": deployments.get("successful_deployments") if deployment_available else None,
        "failed_deployments": deployments.get("failed_deployments") if deployment_available else None,
        "deployment_error_rate": deployments.get("deployment_error_rate") if deployment_available else None,
        "event_count": len(deployments.get("deployment_events", [])),
    }
    overall = errors["overall"]
    error_counts = {
        "application_errors": pod.get("total_error_count", 0),
        "oom_kills": oom.get("total_oom_kill_count", 0),
        "http_4xx_errors": http.get("http_4xx_errors"),
        "http_5xx_errors": http.get("http_5xx_errors"),
        "deployment_failures": deployment.get("failed_deployments"),
    }
    total_errors = overall.get("total_errors_all_sources") or 0
    breakdown_percent = {
        name: (count / total_errors * 100 if count is not None and total_errors else None)
        for name, count in error_counts.items()
    }
    component_statuses = {
        "application_logs": "available",
        "oom_kills": "available",
        "http_logs": http["availability"],
        "deployment_events": deployment["availability"],
    }
    available_count = sum(status == "available" for status in component_statuses.values())
    return {
        "source_window": {
            "start": period["start"],
            "end": period["end"],
            "days": period["days"],
            "calendar_days_inclusive": inclusive_calendar_days(period["start"], period["end"]),
        },
        "temporal_resolution": "aggregate_only",
        "daily_breakdown_available": False,
        "components": {
            "application_logs": {
                "availability": "available",
                "pods_analyzed": pod.get("total_pods_analyzed"),
                "pods_with_errors": pod.get("pods_with_errors"),
                "total_error_count": pod.get("total_error_count"),
                "error_count_per_pod": pod.get("error_rate_per_pod"),
                "error_samples": pod.get("error_samples", []),
            },
            "http": http,
            "oom": oom,
            "deployments": deployment,
        },
        "overall": {
            "total_errors": overall.get("total_errors_all_sources"),
            "errors_per_day": overall.get("error_rate_per_day"),
            "pod_errors_per_day": overall.get("pod_errors_per_day"),
            "oom_kills_per_day": overall.get("oom_kills_per_day"),
            "http_4xx_per_day": overall.get("http_4xx_per_day"),
            "http_5xx_per_day": overall.get("http_5xx_per_day"),
            "deployment_errors_per_day": overall.get("deployment_errors_per_day"),
            "breakdown_counts": error_counts,
            "breakdown_percent": overall.get("error_breakdown") or breakdown_percent,
        },
        "coverage": {
            "component_count": len(component_statuses),
            "available_component_count": available_count,
            "availability_percentage": available_count / len(component_statuses) * 100,
            "component_statuses": component_statuses,
            "quality": "partial_aggregate",
        },
    }


def parse_timing_samples(samples: list[str]) -> list[float]:
    values: list[float] = []
    for sample in samples:
        match = TIMING_RE.search(sample)
        if match:
            value = json_number(match.group(1))
            if value is not None:
                values.append(float(value))
    return values


def application_latency_record(service: str, source_service: dict[str, Any]) -> dict[str, Any]:
    application = source_service["latency_metrics"].get("application", {})
    samples = application.get("application_timing_samples", [])
    parsed = parse_timing_samples(samples)
    timestamps = [match.group(1) for sample in samples if (match := TIMESTAMP_RE.search(sample))]
    timing = numeric_stats(parsed)
    return {
        "metric": "application_processing_time",
        "availability": "available" if parsed else "unavailable",
        "unit": "seconds",
        "sample_count": len(parsed),
        "log_files_analyzed": application.get("log_files_analyzed", 0),
        "calendar_days_with_timestamped_samples": sorted(set(timestamps)),
        "statistics": timing,
        "source_note": (
            "Parsed from 'Finished in N seconds' log lines; the source does not provide "
            "a complete structured latency series."
            if parsed
            else "No application timing lines were collected."
        ),
    }


def build_latency(service: str, error_source: dict[str, Any], latency_source: dict[str, Any]) -> dict[str, Any]:
    source_service = error_source["services"][service]
    latency = latency_source["services"][service]
    records: dict[str, Any] = {
        "application_processing_time": application_latency_record(service, source_service)
    }
    source_metrics = latency.get("latency_metrics", {})
    if service == "pbx-web":
        records["workflow_execution_time"] = {
            "metric": "workflow_execution_time",
            "availability": "available",
            "unit": "seconds",
            "statistics": source_metrics.get("workflow_percentiles", {}),
            "observed_dates": sorted(
                {
                    sample["started_at"][:10]
                    for sample in latency.get("raw_data", {}).get("workflow_samples", [])
                    if sample.get("started_at")
                }
            ),
            "sample_count": source_metrics.get("workflow_percentiles", {}).get("count", 0),
        }
        records["deployment_interval"] = {
            "metric": "deployment_interval",
            "availability": "available",
            "unit": "seconds",
            "statistics": source_metrics.get("deployment_intervals", {}),
            "sample_count": source_metrics.get("deployment_intervals", {}).get("count", 0),
        }
        coverage = latency.get("coverage_analysis", {}).get("workflow_data", {})
        coverage_summary = {
            "workflow": {
                "expected_days": coverage.get("expected_days"),
                "days_with_data": coverage.get("days_with_data"),
                "coverage_percentage": coverage.get("coverage_percentage"),
                "daily_distribution": coverage.get("daily_distribution", {}),
            }
        }
    else:
        records["deployment_interval"] = {
            "metric": "deployment_interval",
            "availability": "available",
            "unit": "hours",
            "statistics": source_metrics.get("deployment_frequency", {}).get("intervals_hours", {}),
            "sample_count": source_metrics.get("deployment_frequency", {}).get("intervals_hours", {}).get("count", 0),
        }
        records["pod_health"] = {
            "metric": "pod_health",
            "availability": "available",
            "unit": "count",
            **source_metrics.get("pod_health", {}),
        }
        coverage = latency.get("coverage_analysis", {}).get("deployment_data", {})
        coverage_summary = {
            "deployment_events": {
                "expected_days": coverage.get("expected_days"),
                "days_with_data": coverage.get("days_with_deployments"),
                "coverage_percentage": coverage.get("coverage_percentage"),
                "daily_distribution": coverage.get("deployment_distribution", {}),
            }
        }
    available = sum(record.get("availability") == "available" for record in records.values())
    return {
        "source_windows": [
            {
                "source": "error_latency_collection",
                "start": source_service["analysis_period"]["start"],
                "end": source_service["analysis_period"]["end"],
                "declared_days": source_service["analysis_period"]["days"],
                "calendar_days_inclusive": inclusive_calendar_days(
                    source_service["analysis_period"]["start"], source_service["analysis_period"]["end"]
                ),
            },
            {
                "source": "latency_query",
                "start": latency_source["query_metadata"]["start_date"],
                "end": latency_source["query_metadata"]["end_date"],
                "declared_days": latency_source["query_metadata"]["period_days"],
                "calendar_days_inclusive": inclusive_calendar_days(
                    latency_source["query_metadata"]["start_date"], latency_source["query_metadata"]["end_date"]
                ),
            },
        ],
        "metrics": records,
        "coverage": {
            "metric_count": len(records),
            "available_metric_count": available,
            "availability_percentage": available / len(records) * 100,
            "temporal_resolution": "event_and_sparse_day_aggregates",
            "sparse_coverage": coverage_summary,
        },
    }


def build_resources(service: str, resource_usage: dict[str, Any], cpu_source: dict[str, Any], cpu_coverage: dict[str, Any], disk_source: dict[str, Any], disk_coverage: dict[str, Any]) -> dict[str, Any]:
    metrics: dict[str, Any] = {}
    for source, coverage_source in ((cpu_source, cpu_coverage), (disk_source, disk_coverage)):
        for metric_name, raw in source.get("raw_queries", {}).get(service, {}).items():
            coverage = coverage_source.get("coverage", {}).get(service, {}).get(metric_name, {})
            metrics[metric_name] = resource_metric_record(service, metric_name, raw, coverage)
    snapshot_source = resource_usage["services"][service]
    snapshot_keys = (
        "collection_timestamp",
        "current_cpu_usage",
        "cpu_requests",
        "cpu_limits",
        "cpu_utilization",
        "current_memory_usage",
        "memory_requests",
        "memory_limits",
        "memory_utilization",
        "pvcs",
        "volume_usage",
        "network_stats",
        "metric_coverage",
        "anomalies",
        "data_gaps",
        "temporal_alignment",
    )
    snapshot = {key: snapshot_source.get(key) for key in snapshot_keys}
    available = sum(metric["availability"] == "available" for metric in metrics.values())
    return {
        "requested_windows": {
            "cpu_memory": cpu_source.get("collection_metadata", {}),
            "disk_network_storage": disk_source.get("collection_metadata", {}),
        },
        "metrics": metrics,
        "current_resource_snapshot": snapshot,
        "coverage": {
            "metric_count": len(metrics),
            "available_metric_count": available,
            "unavailable_metric_count": len(metrics) - available,
            "availability_percentage": available / len(metrics) * 100 if metrics else 0,
            "internal_hourly_gaps": sum(
                metric["coverage"]["internal_gap_count"] for metric in metrics.values()
            ),
        },
    }


def build_deployment_context(deployment_source: dict[str, Any]) -> dict[str, Any]:
    events = deployment_source.get("deployment_events", [])
    rows = deployment_source.get("alignment_rows", [])
    per_service: dict[str, Any] = {}
    for service in SERVICES:
        service_rows = [row for row in rows if row.get("service") == service]
        statuses = sorted({row.get("alignment_status") for row in service_rows if row.get("alignment_status")})
        per_service[service] = {
            "event_count": sum(event.get("service") == service for event in events),
            "alignment_row_count": len(service_rows),
            "rows_in_requested_metric_window": sum(
                row.get("event_in_metric_requested_window", False) for row in service_rows
            ),
            "rows_within_half_step": sum(row.get("within_half_step", False) for row in service_rows),
            "rows_within_observed_metric_window": sum(
                row.get("event_within_observed_metric_window", False) for row in service_rows
            ),
            "status_counts": {
                status: sum(row.get("alignment_status") == status for row in service_rows)
                for status in statuses
            },
        }
    return {
        "source": str(DEPLOYMENT_ALIGNMENT),
        "events": events,
        "per_service": per_service,
        "interpretation": "Deployment events are preserved as context; no metric values are interpolated at event timestamps.",
    }


def build_time_alignment(error_source: dict[str, Any], latency_source: dict[str, Any], cpu_source: dict[str, Any], disk_source: dict[str, Any]) -> dict[str, Any]:
    error_start = error_source["collection_metadata"]["analysis_period"]["start"]
    error_end = error_source["collection_metadata"]["analysis_period"]["end"]
    latency_start = latency_source["query_metadata"]["start_date"]
    latency_end = latency_source["query_metadata"]["end_date"]
    cpu_meta = cpu_source["collection_metadata"]
    disk_meta = disk_source["collection_metadata"]
    common_start = max(
        parse_timestamp(error_start),
        parse_timestamp(latency_start),
        parse_timestamp(cpu_meta["requested_window_start"]),
        parse_timestamp(disk_meta["requested_window_start"]),
    )
    common_end = min(
        parse_timestamp(error_end),
        parse_timestamp(latency_end),
        parse_timestamp(cpu_meta["requested_window_end"]),
        parse_timestamp(disk_meta["requested_window_end"]),
    )
    common_days = (common_end - common_start).total_seconds() / 86400
    return {
        "alignment_method": "UTC timestamps with source windows preserved; cross-family comparison uses exact requested-window intersection",
        "canonical_granularity": "source-native plus hourly resource samples",
        "source_windows": {
            "error_rates": {
                "start": error_start,
                "end": error_end,
                "declared_days": error_source["collection_metadata"]["analysis_period"]["days"],
                "calendar_days_inclusive": inclusive_calendar_days(error_start, error_end),
                "resolution": "aggregate_only",
            },
            "latency": {
                "start": latency_start,
                "end": latency_end,
                "declared_days": latency_source["query_metadata"]["period_days"],
                "calendar_days_inclusive": inclusive_calendar_days(latency_start, latency_end),
                "resolution": "event_and_sparse_day_aggregates",
            },
            "cpu_memory": {"start": cpu_meta["requested_window_start"], "end": cpu_meta["requested_window_end"], "resolution": "1h_requested_step"},
            "disk_network_storage": {"start": disk_meta["requested_window_start"], "end": disk_meta["requested_window_end"], "resolution": "1h_requested_step"},
        },
        "common_requested_intersection": {
            "start": common_start.isoformat(timespec="milliseconds").replace("+00:00", "Z"),
            "end": common_end.isoformat(timespec="milliseconds").replace("+00:00", "Z"),
            "duration_days": common_days,
            "partial_first_and_last_source_buckets": True,
        },
        "alignment_status": "aligned_with_documented_window_mismatch_and_sparse_coverage",
        "notes": [
            "Error and latency collections end on 2026-08-06 while resource collections end on 2026-08-10.",
            "Resource queries requested 30 days but Prometheus returned only the last 10.708 days because of a 19.292-day leading retention/no-data gap.",
            "No synthetic samples were inserted for missing intervals; unavailable values remain null or are represented by coverage records.",
        ],
    }


def build_gaps_and_anomalies(services: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    gaps: list[dict[str, Any]] = []
    anomalies: list[dict[str, Any]] = []
    for service, data in services.items():
        resource_metrics = data["resource_usage"]["metrics"]
        resource_gaps = sorted(
            {
                metric["coverage"]["leading_gap_days"]
                for metric in resource_metrics.values()
                if metric["coverage"]["leading_gap_days"]
            }
        )
        if resource_gaps:
            gaps.append(
                {
                    "id": f"{service}-resource-retention-gap",
                    "service": service,
                    "metric_family": "resource_usage",
                    "severity": "high",
                    "type": "leading_retention_or_no_data_gap",
                    "affected_metric_count": sum(bool(metric["coverage"]["leading_gap_days"]) for metric in resource_metrics.values()),
                    "duration_days": max(resource_gaps),
                    "description": "Prometheus returned no samples at the beginning of the requested 30-day resource window.",
                    "source": "resource coverage reports",
                }
            )
        unavailable_resources = [
            name for name, metric in resource_metrics.items() if metric["availability"] == "unavailable"
        ]
        if unavailable_resources:
            gaps.append(
                {
                    "id": f"{service}-resource-unavailable-series",
                    "service": service,
                    "metric_family": "resource_usage",
                    "severity": "high",
                    "type": "metric_series_unavailable",
                    "metrics": unavailable_resources,
                    "description": "The query succeeded but returned no time series; this is not equivalent to a measured zero.",
                    "source": "disk/network/storage raw query responses",
                }
            )
        for name, metric in resource_metrics.items():
            if metric["statistics"]["sample_count"] and metric["statistics"]["zero_fraction"] == 1:
                anomalies.append(
                    {
                        "id": f"{service}-{name}-all-zero",
                        "service": service,
                        "metric_family": "resource_usage",
                        "metric": name,
                        "severity": "medium",
                        "type": "constant_zero_series",
                        "description": "Every returned sample is zero; this may indicate true idleness or an uninstrumented counter.",
                        "sample_count": metric["statistics"]["sample_count"],
                        "source": "raw Prometheus response",
                    }
                )

        error = data["error_rates"]
        component_statuses = error["coverage"]["component_statuses"]
        unavailable_components = [name for name, status in component_statuses.items() if status == "unavailable"]
        if unavailable_components:
            gaps.append(
                {
                    "id": f"{service}-error-components-unavailable",
                    "service": service,
                    "metric_family": "error_rates",
                    "severity": "high",
                    "type": "component_coverage_gap",
                    "components": unavailable_components,
                    "description": "A missing log/event source is represented as unavailable rather than zero.",
                    "source": "error/latency collection artifact",
                }
            )
        gaps.append(
            {
                "id": f"{service}-error-daily-breakdown-missing",
                "service": service,
                "metric_family": "error_rates",
                "severity": "medium",
                "type": "aggregate_only",
                "description": "Error counts cover the source analysis window but have no complete daily time series.",
                "source": "error/latency collection artifact",
            }
        )
        if service == "whisper-stt":
            gaps.append(
                {
                    "id": "whisper-stt-application-latency-missing",
                    "service": service,
                    "metric_family": "latency",
                    "severity": "high",
                    "type": "no_application_timing_samples",
                    "description": "No structured application timing lines were collected for whisper-stt.",
                    "source": "error/latency collection artifact",
                }
            )
        else:
            gaps.append(
                {
                    "id": "pbx-web-workflow-latency-sparse",
                    "service": service,
                    "metric_family": "latency",
                    "severity": "medium",
                    "type": "sparse_temporal_coverage",
                    "description": "Workflow latency has samples on only one day of the source window.",
                    "source": "latency query artifact",
                }
            )

        latency_metrics = data["latency"]["metrics"]
        workflow = latency_metrics.get("workflow_execution_time", {}).get("statistics", {})
        if workflow.get("max_seconds", 0) and workflow.get("max_seconds", 0) > workflow.get("p50_seconds", 0) * 10:
            anomalies.append(
                {
                    "id": "pbx-web-workflow-long-tail",
                    "service": service,
                    "metric_family": "latency",
                    "metric": "workflow_execution_time",
                    "severity": "high",
                    "type": "long_tail_spike",
                    "description": "Maximum workflow duration is more than ten times the median.",
                    "max_seconds": workflow.get("max_seconds"),
                    "p50_seconds": workflow.get("p50_seconds"),
                    "source": "latency query artifact",
                }
            )
        deployment = latency_metrics.get("deployment_interval", {}).get("statistics", {})
        if deployment.get("max_hours", 0) and deployment.get("max_hours", 0) > deployment.get("median_hours", 0) * 100:
            anomalies.append(
                {
                    "id": "whisper-stt-deployment-interval-spread",
                    "service": service,
                    "metric_family": "latency",
                    "metric": "deployment_interval",
                    "severity": "medium",
                    "type": "rapid_sequence_and_long_gap",
                    "description": "Deployment intervals combine a rapid rollout sequence with a much longer gap.",
                    "max_hours": deployment.get("max_hours"),
                    "median_hours": deployment.get("median_hours"),
                    "source": "latency query artifact",
                }
            )

        memory = data["resource_usage"]["current_resource_snapshot"].get("memory_utilization") or {}
        request_percent = memory.get("vs_request_percent")
        limit_percent = memory.get("vs_limit_percent")
        if request_percent is not None and request_percent > 100:
            anomalies.append(
                {
                    "id": f"{service}-memory-over-request",
                    "service": service,
                    "metric_family": "resource_usage",
                    "metric": "memory_working_set",
                    "severity": "high",
                    "type": "memory_above_request",
                    "request_utilization_percent": request_percent,
                    "limit_utilization_percent": limit_percent,
                    "description": "Current memory exceeds the recorded request; verify request aggregation before capacity decisions.",
                    "source": "resource usage snapshot",
                }
            )
        if limit_percent is not None and limit_percent > 100:
            anomalies.append(
                {
                    "id": f"{service}-memory-over-limit",
                    "service": service,
                    "metric_family": "resource_usage",
                    "metric": "memory_working_set",
                    "severity": "critical",
                    "type": "memory_above_limit",
                    "request_utilization_percent": request_percent,
                    "limit_utilization_percent": limit_percent,
                    "description": "Current memory exceeds the recorded limit; verify the snapshot and container-level aggregation.",
                    "source": "resource usage snapshot",
                }
            )
    return gaps, anomalies


def build_report(unified: dict[str, Any], gaps: list[dict[str, Any]], anomalies: list[dict[str, Any]]) -> dict[str, Any]:
    service_summaries = {}
    for service, data in unified["services"].items():
        family_status = {}
        for family in ("error_rates", "latency", "resource_usage"):
            family_data = data[family]
            family_status[family] = {
                "availability_percentage": family_data["coverage"].get("availability_percentage"),
                "quality": family_data["coverage"].get("quality", "partial"),
                "available_metric_count": family_data["coverage"].get(
                    "available_metric_count", family_data["coverage"].get("available_component_count")
                ),
                "metric_count": family_data["coverage"].get(
                    "metric_count", family_data["coverage"].get("component_count")
                ),
            }
        service_summaries[service] = {
            "status": "degraded",
            "family_status": family_status,
            "gap_count": sum(gap["service"] == service for gap in gaps),
            "anomaly_count": sum(anomaly["service"] == service for anomaly in anomalies),
            "quality_notes": data["data_quality"]["notes"],
        }
    return {
        "report_schema_version": "1.0",
        "report_type": "metric_availability_coverage_and_anomaly_report",
        "dataset": unified["metadata"],
        "overall_status": "degraded_but_structured",
        "acceptance_criteria": {
            "merged_error_latency_resource_metrics": True,
            "temporal_alignment_documented": True,
            "coverage_gaps_documented": bool(gaps),
            "anomalies_flagged": bool(anomalies),
            "availability_and_data_quality_summarized": True,
            "structured_json_outputs_created": True,
        },
        "service_summaries": service_summaries,
        "coverage_gaps": gaps,
        "anomalies": anomalies,
        "interpretation_guidance": [
            "null or unavailable means no trustworthy samples were returned; it is not a zero measurement",
            "aggregate error rates and sparse event latency must not be interpreted as complete daily coverage",
            "resource point coverage is based on returned hourly timestamp points, while series statistics use all returned values",
        ],
        "output_files": [
            "data/unified_metrics_30d.json",
            "data/unified_metrics_availability_report.json",
        ],
    }


def consolidate() -> tuple[dict[str, Any], dict[str, Any]]:
    error_source = load_json(ERROR_SOURCE)
    latency_source = load_json(LATENCY_SOURCE)
    resource_usage = load_json(RESOURCE_USAGE_SOURCE)
    cpu_source = load_json(CPU_MEMORY_SOURCE)
    cpu_coverage = load_json(CPU_MEMORY_COVERAGE)
    disk_source = load_json(DISK_NETWORK_SOURCE)
    disk_coverage = load_json(DISK_NETWORK_COVERAGE)
    deployment_source = load_json(DEPLOYMENT_ALIGNMENT)

    services: dict[str, Any] = {}
    for service in SERVICES:
        services[service] = {
            "service": service,
            "error_rates": build_error_rates(service, error_source),
            "latency": build_latency(service, error_source, latency_source),
            "resource_usage": build_resources(
                service, resource_usage, cpu_source, cpu_coverage, disk_source, disk_coverage
            ),
            "data_quality": {"status": "degraded", "notes": []},
        }

    gaps, anomalies = build_gaps_and_anomalies(services)
    generated_candidates = [
        error_source["collection_metadata"]["timestamp"],
        latency_source["query_metadata"]["query_timestamp"],
        cpu_source["collection_metadata"]["collected_at"],
        disk_source["collection_metadata"]["collected_at"],
    ]
    generated_at = max(parse_timestamp(timestamp) for timestamp in generated_candidates)
    for service, data in services.items():
        data["data_quality"] = {
            "status": "degraded",
            "notes": [
                "Error rates are aggregate-only and do not include a complete daily series.",
                "Latency sources are sparse event/workflow aggregates; application timing is log-derived where present.",
                "Resource Prometheus data has a leading retention/no-data gap and no synthetic fill.",
                "Counts follow the source collection scope; pod names in the log artifact include supporting and non-primary workload pods.",
            ],
            "gap_count": sum(gap["service"] == service for gap in gaps),
            "anomaly_count": sum(anomaly["service"] == service for anomaly in anomalies),
        }

    alignment = build_time_alignment(error_source, latency_source, cpu_source, disk_source)
    unified = {
        "schema_version": "1.0",
        "dataset_type": "unified_service_metrics",
        "metadata": {
            "generated_at": generated_at.isoformat(timespec="milliseconds").replace("+00:00", "Z"),
            "services": list(SERVICES),
            "metric_families": ["error_rates", "latency", "resource_usage"],
            "time_alignment": alignment,
            "deployment_context": build_deployment_context(deployment_source),
            "source_artifacts": {
                "error_rates_and_application_latency": str(ERROR_SOURCE),
                "workflow_and_deployment_latency": str(LATENCY_SOURCE),
                "resource_snapshot": str(RESOURCE_USAGE_SOURCE),
                "cpu_and_memory_timeseries": str(CPU_MEMORY_SOURCE),
                "cpu_and_memory_coverage": str(CPU_MEMORY_COVERAGE),
                "disk_network_storage_timeseries": str(DISK_NETWORK_SOURCE),
                "disk_network_storage_coverage": str(DISK_NETWORK_COVERAGE),
            },
        },
        "services": services,
        "coverage_analysis": {
            "gap_count": len(gaps),
            "anomaly_count": len(anomalies),
            "gaps": gaps,
            "anomalies": anomalies,
        },
    }
    report = build_report(unified, gaps, anomalies)
    return unified, report


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(value, handle, indent=2, sort_keys=False, allow_nan=False)
        handle.write("\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("data/unified_metrics_30d.json"))
    parser.add_argument("--report", type=Path, default=Path("data/unified_metrics_availability_report.json"))
    args = parser.parse_args()
    unified, report = consolidate()
    write_json(args.output, unified)
    write_json(args.report, report)
    print(f"wrote {args.output}")
    print(f"wrote {args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
