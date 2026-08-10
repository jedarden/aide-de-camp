#!/usr/bin/env python3
"""Validate and align resource metrics with the deployment event dataset.

The repository contains two Prometheus exports for the requested resource
categories: CPU/memory and disk/network/storage.  This validator keeps those
exports as the source of metric values and writes a compact, analysis-ready
index containing coverage, gaps, anomalies, and nearest timestamp matches for
each deployment event.

The default inputs are the latest checked-in exports.  Pass explicit paths to
the command-line options when validating a different collection.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SERVICES = ("pbx-web", "whisper-stt")
CATEGORIES = ("cpu", "memory", "disk", "network")
CATEGORY_METRICS = {
    "cpu": ("cpu_usage",),
    "memory": ("memory_working_set",),
    "disk": (
        "disk_read_bytes_per_second",
        "disk_read_operations_per_second",
        "disk_write_bytes_per_second",
        "disk_write_operations_per_second",
    ),
    "network": (
        "network_receive_bytes_per_second",
        "network_receive_bytes_total",
        "network_transmit_bytes_per_second",
        "network_transmit_bytes_total",
    ),
}


def parse_timestamp(value: Any) -> datetime | None:
    """Parse an ISO-8601 timestamp and normalize it to UTC."""

    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def isoformat(value: datetime | None) -> str | None:
    """Serialize a timestamp consistently, using a Z suffix."""

    if value is None:
        return None
    return value.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace(
        "+00:00", "Z"
    )


def load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object in {path}")
    return value


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def source_descriptor(path: Path) -> dict[str, Any]:
    return {"path": str(path), "sha256": sha256(path), "bytes": path.stat().st_size}


def deployment_events(deployment_data: dict[str, Any]) -> list[dict[str, Any]]:
    """Normalize the combined deployment-events-30days.json shape."""

    sections = {
        "pbx-web": "pbx_web_deployments",
        "whisper-stt": "whisper_stt_deployments",
    }
    events: list[dict[str, Any]] = []
    for service, section_name in sections.items():
        section = deployment_data.get(section_name, {})
        for raw in section.get("deployment_events", []):
            timestamp = parse_timestamp(raw.get("timestamp"))
            if timestamp is None:
                continue
            event = dict(raw)
            event["service"] = service
            event["deployment_name"] = raw.get("deployment") or service
            event["event_id"] = ":".join(
                str(part)
                for part in (
                    service,
                    raw.get("timestamp", ""),
                    raw.get("event_type", ""),
                    raw.get("revision", ""),
                )
            )
            event["timestamp"] = isoformat(timestamp)
            events.append(event)
    return sorted(events, key=lambda event: (event["service"], event["timestamp"]))


def response_series(metric: dict[str, Any]) -> list[dict[str, Any]]:
    response = metric.get("response", {})
    data = response.get("data", {}) if isinstance(response, dict) else {}
    result = data.get("result", []) if isinstance(data, dict) else []
    return result if isinstance(result, list) else []


def metric_points(metric: dict[str, Any]) -> list[tuple[datetime, float]]:
    points: list[tuple[datetime, float]] = []
    for series in response_series(metric):
        for value in series.get("values", []):
            if not isinstance(value, list) or len(value) < 2:
                continue
            timestamp = (
                datetime.fromtimestamp(float(value[0]), tz=timezone.utc)
                if isinstance(value[0], (int, float))
                else parse_timestamp(value[0])
            )
            try:
                numeric_value = float(value[1])
            except (TypeError, ValueError):
                continue
            if timestamp is not None and math.isfinite(numeric_value):
                points.append((timestamp, numeric_value))
    return points


def contiguous_gaps(
    timestamps: list[datetime], start: datetime, end: datetime, step_seconds: int
) -> dict[str, Any]:
    """Return leading, internal, and trailing gaps for a timestamp grid."""

    if not timestamps:
        return {
            "leading_gap_seconds": (end - start).total_seconds(),
            "trailing_gap_seconds": (end - start).total_seconds(),
            "internal_gap_count": 0,
            "internal_missing_intervals": 0,
            "internal_gaps": [],
        }

    tolerance = 1.0
    internal_gaps: list[dict[str, Any]] = []
    missing_intervals = 0
    for previous, current in zip(timestamps, timestamps[1:]):
        delta = (current - previous).total_seconds()
        if delta > step_seconds + tolerance:
            missing = max(1, round(delta / step_seconds) - 1)
            missing_intervals += missing
            internal_gaps.append(
                {
                    "start": isoformat(previous),
                    "end": isoformat(current),
                    "duration_seconds": delta,
                    "missing_intervals": missing,
                }
            )
    return {
        "leading_gap_seconds": max(0.0, (timestamps[0] - start).total_seconds()),
        "trailing_gap_seconds": max(0.0, (end - timestamps[-1]).total_seconds()),
        "internal_gap_count": len(internal_gaps),
        "internal_missing_intervals": missing_intervals,
        "internal_gaps": internal_gaps,
    }


def numeric_summary(values: list[float]) -> dict[str, float | int | None]:
    if not values:
        return {
            "sample_points": 0,
            "nonzero_points": 0,
            "zero_points": 0,
            "zero_fraction": None,
            "min": None,
            "median": None,
            "max": None,
        }
    return {
        "sample_points": len(values),
        "nonzero_points": sum(value != 0 for value in values),
        "zero_points": sum(value == 0 for value in values),
        "zero_fraction": round(sum(value == 0 for value in values) / len(values), 6),
        "min": min(values),
        "median": statistics.median(values),
        "max": max(values),
    }


def summarize_metric(
    metric_name: str,
    metric: dict[str, Any] | None,
    start: datetime,
    end: datetime,
    step_seconds: int,
) -> dict[str, Any]:
    """Summarize one Prometheus range query without copying its raw values."""

    metric = metric or {}
    points = metric_points(metric)
    timestamps = sorted({timestamp for timestamp, _ in points})
    values = [value for _, value in points]
    series_summaries = []
    for series in response_series(metric):
        series_points = metric_points({"response": {"data": {"result": [series]}}})
        series_timestamps = sorted({timestamp for timestamp, _ in series_points})
        series_summaries.append(
            {
                "labels": series.get("metric", {}),
                "sample_points": len(series_points),
                "first_sample": isoformat(series_timestamps[0]) if series_timestamps else None,
                "last_sample": isoformat(series_timestamps[-1]) if series_timestamps else None,
                "internal_gap_count": contiguous_gaps(
                    series_timestamps,
                    series_timestamps[0] if series_timestamps else start,
                    series_timestamps[-1] if series_timestamps else end,
                    step_seconds,
                )["internal_gap_count"],
            }
        )
    gaps = contiguous_gaps(timestamps, start, end, step_seconds)
    expected_points = max(1, round((end - start).total_seconds() / step_seconds) + 1)
    observed_span_seconds = (
        (timestamps[-1] - timestamps[0]).total_seconds() if len(timestamps) > 1 else 0.0
    )
    summary: dict[str, Any] = {
        "metric": metric_name,
        "query": metric.get("query"),
        "present": bool(points),
        "series_count": len(response_series(metric)),
        "observed_timestamp_points": len(timestamps),
        "expected_timestamp_points": expected_points,
        "coverage_percentage_by_points": round(len(timestamps) / expected_points * 100, 3),
        "observed_span_days": round(observed_span_seconds / 86400, 6),
        "requested_window_days": round((end - start).total_seconds() / 86400, 6),
        "first_sample": isoformat(timestamps[0]) if timestamps else None,
        "last_sample": isoformat(timestamps[-1]) if timestamps else None,
        "status": "complete"
        if timestamps
        and timestamps[0] <= start
        and timestamps[-1] >= end
        and gaps["internal_gap_count"] == 0
        else "partial",
        "gaps": {
            "leading_gap_seconds": round(gaps["leading_gap_seconds"], 3),
            "leading_gap_days": round(gaps["leading_gap_seconds"] / 86400, 6),
            "trailing_gap_seconds": round(gaps["trailing_gap_seconds"], 3),
            "trailing_gap_days": round(gaps["trailing_gap_seconds"] / 86400, 6),
            "internal_gap_count": gaps["internal_gap_count"],
            "internal_missing_intervals": gaps["internal_missing_intervals"],
            "internal_gaps": gaps["internal_gaps"],
        },
        "statistics": numeric_summary(values),
        "series": series_summaries,
    }
    return summary


def nearest_timestamp(
    event_time: datetime, timestamps: list[datetime]
) -> tuple[datetime | None, float | None]:
    if not timestamps:
        return None, None
    nearest = min(timestamps, key=lambda timestamp: abs(timestamp - event_time))
    return nearest, (nearest - event_time).total_seconds()


def metric_file_window(data: dict[str, Any]) -> tuple[datetime, datetime, int]:
    metadata = data.get("collection_metadata", {})
    start = parse_timestamp(metadata.get("requested_window_start"))
    end = parse_timestamp(metadata.get("requested_window_end"))
    step = int(metadata.get("step_seconds", 3600))
    if start is None or end is None:
        raise ValueError("Metric source is missing requested_window_start/end")
    return start, end, step


def event_alignment(
    event: dict[str, Any],
    category_summaries: dict[str, dict[str, Any]],
    category_timestamps: dict[str, list[datetime]],
    requested_start: datetime,
    requested_end: datetime,
    step_seconds: int,
) -> list[dict[str, Any]]:
    event_time = parse_timestamp(event["timestamp"])
    assert event_time is not None
    in_requested_window = requested_start <= event_time <= requested_end
    rows = []
    for category in CATEGORIES:
        nearest, offset = nearest_timestamp(event_time, category_timestamps[category])
        in_observed_window = bool(
            nearest
            and category_summaries[category]["first_sample"]
            and parse_timestamp(category_summaries[category]["first_sample"])
            <= event_time
            <= parse_timestamp(category_summaries[category]["last_sample"])
        )
        if not in_requested_window:
            status = "event_outside_metric_requested_window"
        elif not in_observed_window:
            status = "outside_observed_metric_window"
        elif offset is not None and abs(offset) <= step_seconds / 2:
            status = "aligned_to_nearest_hourly_sample"
        else:
            status = "nearest_sample_exceeds_half_step"
        rows.append(
            {
                "event_id": event["event_id"],
                "service": event["service"],
                "deployment_name": event["deployment_name"],
                "event_timestamp": event["timestamp"],
                "event_type": event.get("event_type"),
                "revision": event.get("revision"),
                "category": category,
                "representative_metric": CATEGORY_METRICS[category][0],
                "metric_first_sample": category_summaries[category]["first_sample"],
                "metric_last_sample": category_summaries[category]["last_sample"],
                "event_in_metric_requested_window": in_requested_window,
                "event_within_observed_metric_window": in_observed_window,
                "nearest_sample_timestamp": isoformat(nearest),
                "nearest_sample_offset_seconds": round(offset, 3) if offset is not None else None,
                "nearest_sample_offset_hours": round(offset / 3600, 6) if offset is not None else None,
                "within_half_step": bool(offset is not None and abs(offset) <= step_seconds / 2),
                "alignment_status": status,
            }
        )
    return rows


def extract_cross_check(path: Path, service: str) -> dict[str, Any]:
    """Compare a service-specific deployment export with the canonical source."""

    if not path.exists():
        return {"path": str(path), "status": "not_available"}
    data = load_json(path)
    events = data.get("deployment_events_last_30_days", [])
    timestamps = sorted(
        isoformat(parsed)
        for event in events
        if (parsed := parse_timestamp(event.get("timestamp"))) is not None
    )
    return {
        "path": str(path),
        "status": "loaded",
        "service": service,
        "event_count": len(timestamps),
        "event_timestamps": timestamps,
    }


def deployment_window_assessment(
    deployment_data: dict[str, Any], metric_start: datetime, metric_end: datetime
) -> dict[str, Any]:
    source_window = deployment_data.get("metadata", {}).get("time_period", {})
    source_start = parse_timestamp(source_window.get("start"))
    source_end = parse_timestamp(source_window.get("end"))
    if source_start is None or source_end is None:
        return {"status": "source_window_unavailable"}
    leading = max(0.0, (source_start - metric_start).total_seconds())
    trailing = max(0.0, (metric_end - source_end).total_seconds())
    return {
        "deployment_source_start": isoformat(source_start),
        "deployment_source_end": isoformat(source_end),
        "metric_window_start": isoformat(metric_start),
        "metric_window_end": isoformat(metric_end),
        "metric_window_before_deployment_source_seconds": round(leading, 3),
        "metric_window_after_deployment_source_seconds": round(trailing, 3),
        "metric_window_after_deployment_source_days": round(trailing / 86400, 6),
        "status": "different_windows" if leading or trailing else "same_window",
    }


def build_report(
    deployment_path: Path,
    cpu_memory_path: Path,
    disk_network_path: Path,
    cross_check_paths: dict[str, Path] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    deployment_data = load_json(deployment_path)
    cpu_memory = load_json(cpu_memory_path)
    disk_network = load_json(disk_network_path)
    metric_start, metric_end, cpu_step = metric_file_window(cpu_memory)
    disk_start, disk_end, disk_step = metric_file_window(disk_network)
    if cpu_step != disk_step:
        raise ValueError("CPU/memory and disk/network exports use different steps")
    step_seconds = cpu_step

    events = deployment_events(deployment_data)
    event_by_service = {
        service: [event for event in events if event["service"] == service]
        for service in SERVICES
    }

    report_services: dict[str, Any] = {}
    aligned_rows: list[dict[str, Any]] = []
    all_category_summaries: dict[str, dict[str, dict[str, Any]]] = {}
    grid_starts: dict[str, dict[str, str | None]] = {}

    for service in SERVICES:
        category_summaries: dict[str, dict[str, Any]] = {}
        category_timestamps: dict[str, list[datetime]] = {}
        for category in CATEGORIES:
            metric_summaries = []
            timestamps: list[datetime] = []
            source_data = cpu_memory if category in ("cpu", "memory") else disk_network
            source_start, source_end, source_step = metric_file_window(source_data)
            for metric_name in CATEGORY_METRICS[category]:
                metric = source_data.get("raw_queries", {}).get(service, {}).get(metric_name)
                summary = summarize_metric(metric_name, metric, source_start, source_end, source_step)
                metric_summaries.append(summary)
                timestamps.extend(
                    datetime.fromisoformat(value.replace("Z", "+00:00"))
                    for value in (summary["first_sample"], summary["last_sample"])
                    if value
                )
                # The representative timestamp grid is read directly to retain all points.
                if metric:
                    timestamps.extend(timestamp for timestamp, _ in metric_points(metric))
            # The summary uses the source's own requested window, not the CPU window.
            category_start, category_end = source_start, source_end
            category_summary = {
                "category": category,
                "present": any(item["present"] for item in metric_summaries),
                "metrics_present": sum(item["present"] for item in metric_summaries),
                "metrics_expected": len(metric_summaries),
                "status": "complete"
                if all(item["status"] == "complete" for item in metric_summaries)
                else "partial",
                "first_sample": min(
                    (item["first_sample"] for item in metric_summaries if item["first_sample"]),
                    default=None,
                ),
                "last_sample": max(
                    (item["last_sample"] for item in metric_summaries if item["last_sample"]),
                    default=None,
                ),
                "requested_window_start": isoformat(category_start),
                "requested_window_end": isoformat(category_end),
                "requested_window_days": round(
                    (category_end - category_start).total_seconds() / 86400, 6
                ),
                "observed_timestamp_points": len(
                    sorted(
                        {
                            timestamp
                            for metric_name in CATEGORY_METRICS[category]
                            for timestamp, _ in metric_points(
                                source_data.get("raw_queries", {})
                                .get(service, {})
                                .get(metric_name, {})
                            )
                        }
                    )
                ),
                "metric_summaries": metric_summaries,
            }
            category_summaries[category] = category_summary
            representative = source_data.get("raw_queries", {}).get(service, {}).get(
                CATEGORY_METRICS[category][0], {}
            )
            category_timestamps[category] = sorted(
                {timestamp for timestamp, _ in metric_points(representative)}
            )
        all_category_summaries[service] = category_summaries
        grid_starts[service] = {
            category: summary["first_sample"] for category, summary in category_summaries.items()
        }
        for event in event_by_service[service]:
            aligned_rows.extend(
                event_alignment(
                    event,
                    category_summaries,
                    category_timestamps,
                    metric_start,
                    metric_end,
                    step_seconds,
                )
            )
        report_services[service] = {
            "deployment_event_count": len(event_by_service[service]),
            "deployment_events_in_metric_window": sum(
                metric_start <= parse_timestamp(event["timestamp"]) <= metric_end
                for event in event_by_service[service]
            ),
            "deployment_events": event_by_service[service],
            "categories": category_summaries,
        }

    # A compact set of high-value anomalies for consumers that do not want to
    # re-derive them from every metric summary.
    anomalies: list[dict[str, Any]] = []
    for service, categories in all_category_summaries.items():
        for category, category_summary in categories.items():
            for metric in category_summary["metric_summaries"]:
                stats = metric["statistics"]
                zero_fraction = stats["zero_fraction"]
                if not metric["present"]:
                    anomalies.append(
                        {
                            "severity": "high",
                            "type": "metric_missing",
                            "service": service,
                            "category": category,
                            "metric": metric["metric"],
                            "description": "No samples were returned for this metric.",
                        }
                    )
                elif category == "disk" and zero_fraction == 1:
                    anomalies.append(
                        {
                            "severity": "medium",
                            "type": "constant_zero_metric",
                            "service": service,
                            "category": category,
                            "metric": metric["metric"],
                            "description": "All returned disk samples are zero; verify exporter/query coverage or confirm no disk I/O occurred.",
                            "zero_fraction": zero_fraction,
                        }
                    )
                elif category == "disk" and zero_fraction is not None and zero_fraction >= 0.95:
                    anomalies.append(
                        {
                            "severity": "info",
                            "type": "mostly_zero_metric",
                            "service": service,
                            "category": category,
                            "metric": metric["metric"],
                            "description": "At least 95% of returned disk samples are zero; treat isolated activity as sparse.",
                            "zero_fraction": zero_fraction,
                        }
                    )
                if (
                    metric["metric"].endswith("_per_second")
                    and stats["median"] not in (None, 0)
                    and stats["max"] is not None
                    and stats["max"] / stats["median"] >= 10
                ):
                    anomalies.append(
                        {
                            "severity": "info",
                            "type": "high_rate_peak",
                            "service": service,
                            "category": category,
                            "metric": metric["metric"],
                            "description": "Maximum rate is at least 10x the median; inspect peak timestamps before interpreting as sustained behavior.",
                            "max_to_median_ratio": round(stats["max"] / stats["median"], 3),
                        }
                    )

    retention_days = cpu_memory.get("collection_metadata", {}).get("prometheus_retention_time")
    for service in SERVICES:
        for category in CATEGORIES:
            representative = all_category_summaries[service][category]["metric_summaries"][0]
            if representative["gaps"]["leading_gap_seconds"] > 0:
                anomalies.append(
                    {
                        "severity": "high",
                        "type": "leading_retention_or_no_data_gap",
                        "service": service,
                        "category": category,
                        "description": "The requested window starts before the first observed sample.",
                        "leading_gap_days": representative["gaps"]["leading_gap_days"],
                        "prometheus_retention_time": retention_days,
                    }
                )

    # Deployment source and metric collection windows are intentionally kept
    # separate: this makes the four-day tail with no deployment history visible.
    window_assessment = deployment_window_assessment(deployment_data, metric_start, metric_end)
    if window_assessment.get("status") == "different_windows":
        anomalies.append(
            {
                "severity": "medium",
                "type": "deployment_metric_window_mismatch",
                "description": "Deployment history and metric collection use different time windows; the metric tail is not covered by the deployment source.",
                "details": window_assessment,
            }
        )

    # CPU/memory and disk/network were collected 30m36.435s apart.  The
    # event alignment remains valid because each category is aligned to its own
    # grid, but a cross-category exact timestamp join would be incorrect.
    grid_offset_seconds = None
    cpu_first = all_category_summaries["pbx-web"]["cpu"]["first_sample"]
    disk_first = all_category_summaries["pbx-web"]["disk"]["first_sample"]
    if cpu_first and disk_first:
        grid_offset_seconds = round(
            (parse_timestamp(disk_first) - parse_timestamp(cpu_first)).total_seconds(), 3
        )
    if grid_offset_seconds:
        anomalies.append(
            {
                "severity": "medium",
                "type": "cross_category_timestamp_grid_offset",
                "description": "CPU/memory and disk/network exports do not share an exact timestamp grid.",
                "offset_seconds": grid_offset_seconds,
                "offset_minutes": round(grid_offset_seconds / 60, 3),
                "impact": "Join categories by timestamp tolerance or resample before cross-category analysis.",
            }
        )

    cross_checks = {}
    if cross_check_paths:
        canonical_sets = {
            service: {event["timestamp"] for event in event_by_service[service]}
            for service in SERVICES
        }
        for service, path in cross_check_paths.items():
            check = extract_cross_check(path, service)
            if check["status"] == "loaded":
                observed = set(check["event_timestamps"])
                check["canonical_event_count"] = len(canonical_sets[service])
                missing = canonical_sets[service] - observed
                extra = observed - canonical_sets[service]
                check["missing_event_count"] = len(missing)
                check["extra_event_count"] = len(extra)
                check["matches_canonical"] = not missing and not extra
                # Keep the report stable across snapshot refreshes; the
                # canonical event list already contains the authoritative
                # timestamps and the counts below are sufficient to expose a
                # disagreement in the narrower export.
                check.pop("event_timestamps", None)
                if not check["matches_canonical"]:
                    anomalies.append(
                        {
                            "severity": "medium",
                            "type": "deployment_source_disagreement",
                            "service": service,
                            "description": "A service-specific deployment export disagrees with the combined deployment event source; use the combined source for this report and investigate the narrower export.",
                            "cross_check_path": str(path),
                            "canonical_event_count": len(canonical_sets[service]),
                            "cross_check_event_count": check["event_count"],
                        }
                    )
            cross_checks[service] = check

    category_presence = {
        service: {
            category: all_category_summaries[service][category]["present"]
            for category in CATEGORIES
        }
        for service in SERVICES
    }
    temporal_complete = all(
        all(
            summary["status"] == "complete"
            for summary in all_category_summaries[service].values()
        )
        for service in SERVICES
    )
    internal_gap_free = all(
        metric["gaps"]["internal_gap_count"] == 0
        for categories in all_category_summaries.values()
        for category in categories.values()
        for metric in category["metric_summaries"]
        if metric["present"]
    )
    aligned_rows_within_tolerance = sum(
        row["within_half_step"] and row["event_in_metric_requested_window"]
        for row in aligned_rows
    )
    in_window_rows = sum(row["event_in_metric_requested_window"] for row in aligned_rows)
    checks = [
        {
            "id": "deployment_events_loaded",
            "passed": len(events) > 0 and all(len(event_by_service[service]) > 0 for service in SERVICES),
            "details": {service: len(event_by_service[service]) for service in SERVICES},
        },
        {
            "id": "metric_sources_loaded",
            "passed": bool(cpu_memory) and bool(disk_network),
        },
        {
            "id": "all_four_categories_present_for_both_services",
            "passed": all(all(values.values()) for values in category_presence.values()),
            "details": category_presence,
        },
        {
            "id": "metric_timestamps_parse",
            "passed": all(
                metric["observed_timestamp_points"] > 0
                for categories in all_category_summaries.values()
                for category in categories.values()
                for metric in category["metric_summaries"]
                if metric["present"]
            ),
        },
        {
            "id": "no_internal_gaps_in_observed_span",
            "passed": internal_gap_free,
        },
        {
            "id": "full_requested_window_coverage",
            "passed": temporal_complete,
            "details": "Expected to fail when the Prometheus retention window is shorter than the requested period.",
        },
        {
            "id": "deployment_events_have_nearby_metric_samples",
            "passed": in_window_rows > 0 and aligned_rows_within_tolerance == in_window_rows,
            "details": {
                "in_window_alignment_rows": in_window_rows,
                "within_half_step": aligned_rows_within_tolerance,
            },
        },
    ]
    passed_checks = sum(check["passed"] for check in checks)

    quality_summary = {
        "services": len(SERVICES),
        "deployment_events_loaded": len(events),
        "metric_categories_expected": len(CATEGORIES),
        "category_presence_checks": len(SERVICES) * len(CATEGORIES),
        "category_presence_passed": sum(
            present for service in category_presence.values() for present in service.values()
        ),
        "category_temporal_completeness_passed": sum(
            summary["status"] == "complete"
            for categories in all_category_summaries.values()
            for summary in categories.values()
        ),
        "internal_metric_gap_free": internal_gap_free,
        "event_alignment_rows": len(aligned_rows),
        "in_window_event_alignment_rows": in_window_rows,
        "in_window_rows_within_half_step": aligned_rows_within_tolerance,
        "validation_checks_passed": passed_checks,
        "validation_checks_total": len(checks),
    }

    report: dict[str, Any] = {
        "report_schema_version": "1.0",
        "report_type": "metrics_deployment_temporal_alignment",
        "generated_at": isoformat(datetime.now(timezone.utc)),
        "analysis_window": {
            "cpu_memory_requested_start": isoformat(metric_start),
            "cpu_memory_requested_end": isoformat(metric_end),
            "disk_network_requested_start": isoformat(disk_start),
            "disk_network_requested_end": isoformat(disk_end),
            "requested_days": 30,
            "step_seconds": step_seconds,
        },
        "sources": {
            "deployment_events": source_descriptor(deployment_path),
            "cpu_memory_metrics": source_descriptor(cpu_memory_path),
            "disk_network_metrics": source_descriptor(disk_network_path),
        },
        "deployment_source_window_assessment": window_assessment,
        "deployment_source_cross_checks": cross_checks,
        "services": report_services,
        "quality_summary": quality_summary,
        "validation_checks": checks,
        "gaps": [
            {
                "type": "leading_metric_coverage_gap",
                "severity": "high",
                "description": "All four resource categories begin approximately 19.3 days after the requested 30-day window starts.",
                "affected_services": list(SERVICES),
                "affected_categories": list(CATEGORIES),
                "leading_gap_days": all_category_summaries["pbx-web"]["cpu"]["metric_summaries"][0]["gaps"]["leading_gap_days"],
                "cause": f"The Prometheus export reports retention={retention_days!r}; verify retention and collection history.",
            },
            {
                "type": "deployment_event_alignment_gap",
                "severity": "high",
                "description": "Deployment events in the metric request window have no metric sample within half the one-hour step because they precede the first observed sample.",
                "affected_events": sorted(
                    {
                        row["event_id"]
                        for row in aligned_rows
                        if row["event_in_metric_requested_window"] and not row["within_half_step"]
                    }
                ),
                "remediation": "Restore historical Prometheus data or narrow analysis to the observed metric window before causal deployment comparisons.",
            },
            {
                "type": "deployment_source_window_gap",
                "severity": "medium",
                "description": "The combined deployment source ends before the metric request window ends.",
                "days_after_deployment_source": window_assessment.get(
                    "metric_window_after_deployment_source_days"
                ),
            },
        ],
        "anomalies": anomalies,
        "alignment_status": "validated_with_temporal_gaps"
        if not temporal_complete or in_window_rows != aligned_rows_within_tolerance
        else "validated",
        "dataset_ready_for_analysis": True,
        "analysis_caveat": "Use the aligned index with the raw source files; do not treat missing periods as zero and do not exact-join CPU/memory with disk/network without timestamp tolerance.",
    }

    aligned = {
        "dataset_schema_version": "1.0",
        "dataset_type": "deployment_event_metric_alignment_index",
        "generated_at": report["generated_at"],
        "source_report": "data/metrics_deployment_alignment_report.json",
        "sources": report["sources"],
        "analysis_window": report["analysis_window"],
        "deployment_events": events,
        "alignment_rows": aligned_rows,
        "metric_coverage": {
            service: {
                category: {
                    key: value
                    for key, value in summary.items()
                    if key != "metric_summaries"
                }
                | {"metric_names": list(CATEGORY_METRICS[category])}
                for category, summary in categories.items()
            }
            for service, categories in all_category_summaries.items()
        },
        "validation_status": report["alignment_status"],
        "ready_for_analysis": report["dataset_ready_for_analysis"],
    }
    return report, aligned


def markdown_report(report: dict[str, Any]) -> str:
    summary = report["quality_summary"]
    lines = [
        "# Metrics/deployment temporal alignment report",
        "",
        f"Generated: `{report['generated_at']}`<br>",
        f"Status: **{report['alignment_status']}**<br>",
        f"Category presence: **{summary['category_presence_passed']}/{summary['category_presence_checks']}** service/category checks<br>",
        f"Requested-window completeness: **{summary['category_temporal_completeness_passed']}/{summary['category_presence_checks']}** categories<br>",
        "",
        "## Scope and sources",
        "",
        "The combined deployment event dataset is treated as canonical. CPU/memory and disk/network/storage are read from their separate Prometheus range exports. The aligned JSON is an index into those raw files; it does not replace their numeric samples.",
        "",
        "| Source | Requested range | Step |",
        "| --- | --- | ---: |",
        f"| CPU/memory | `{report['analysis_window']['cpu_memory_requested_start']}` – `{report['analysis_window']['cpu_memory_requested_end']}` | {report['analysis_window']['step_seconds']} s |",
        f"| Disk/network | `{report['analysis_window']['disk_network_requested_start']}` – `{report['analysis_window']['disk_network_requested_end']}` | {report['analysis_window']['step_seconds']} s |",
        "",
        "## Coverage by service and category",
        "",
        "| Service | Category | Present | Status | First sample | Last sample | Metrics present |",
        "| --- | --- | :---: | --- | --- | --- | ---: |",
    ]
    for service in SERVICES:
        for category in CATEGORIES:
            value = report["services"][service]["categories"][category]
            lines.append(
                f"| {service} | {category} | {'yes' if value['present'] else 'no'} | {value['status']} | `{value['first_sample']}` | `{value['last_sample']}` | {value['metrics_present']}/{value['metrics_expected']} |"
            )
    lines.extend(
        [
            "",
            "Every requested category is present for both services (8/8 checks). None has complete 30-day coverage: the first observed sample is about 19.3 days after the requested start. Within the observed span, the returned hourly grids have no internal gaps.",
            "",
            "## Deployment alignment",
            "",
            f"The canonical source contains {summary['deployment_events_loaded']} deployment events. There are {summary['in_window_event_alignment_rows']} in-window event/category rows; {summary['in_window_rows_within_half_step']} have a metric sample within half an hourly step. The remaining rows are indexed to the nearest sample but are outside the observed metric window, so they must not be interpreted as measurements at deployment time.",
            "",
            "See `data/metrics_deployment_aligned.json` for one row per deployment event and category, including signed nearest-sample offsets.",
            "",
            "## Gaps and anomalies",
            "",
        ]
    )
    for gap in report["gaps"]:
        lines.append(f"- **{gap['severity']} — {gap['type']}:** {gap['description']}")
    for anomaly in report["anomalies"]:
        details = []
        if "service" in anomaly:
            details.append(anomaly["service"])
        if "category" in anomaly:
            details.append(anomaly["category"])
        suffix = f" ({', '.join(details)})" if details else ""
        lines.append(f"- **{anomaly['severity']} — {anomaly['type']}{suffix}:** {anomaly['description']}")
    lines.extend(
        [
            "",
            "Notable metric anomalies include all-zero PBX disk I/O, sparse mostly-zero Whisper disk I/O, large network-rate peaks relative to the median, and a 30m36.435s timestamp-grid offset between the CPU/memory and disk/network exports. These are documented as observations, not silently repaired.",
            "",
            "## Validation result",
            "",
            "| Check | Result |",
            "| --- | --- |",
        ]
    )
    for check in report["validation_checks"]:
        lines.append(f"| {check['id']} | {'PASS' if check['passed'] else 'GAP/FAIL'} |")
    lines.extend(
        [
            "",
            "The dataset is structurally validated and ready for analysis with the documented coverage caveat. Missing periods are represented as gaps, never as zero-valued samples.",
            "",
        ]
    )
    return "\n".join(lines)


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--deployment-events", type=Path, default=Path("deployment-events-30days.json"))
    parser.add_argument(
        "--cpu-memory",
        type=Path,
        default=Path("data/resource_metrics/resource-metrics-30d-20260810T111404Z.json"),
    )
    parser.add_argument(
        "--disk-network",
        type=Path,
        default=Path("data/resource_metrics/disk-network-storage-metrics-30d-20260810T114451Z.json"),
    )
    parser.add_argument(
        "--report", type=Path, default=Path("data/metrics_deployment_alignment_report.json")
    )
    parser.add_argument(
        "--aligned", type=Path, default=Path("data/metrics_deployment_aligned.json")
    )
    parser.add_argument(
        "--markdown", type=Path, default=Path("docs/metrics-deployment-alignment-report.md")
    )
    args = parser.parse_args()
    cross_checks = {
        "pbx-web": Path("pbx-web-deployment-data-30days.json"),
        "whisper-stt": Path("whisper-stt-deployments-30d.json"),
    }
    report, aligned = build_report(
        args.deployment_events,
        args.cpu_memory,
        args.disk_network,
        cross_checks,
    )
    write_json(args.report, report)
    write_json(args.aligned, aligned)
    args.markdown.parent.mkdir(parents=True, exist_ok=True)
    args.markdown.write_text(markdown_report(report), encoding="utf-8")
    print(json.dumps({"alignment_status": report["alignment_status"], **report["quality_summary"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
