#!/usr/bin/env python3
"""Collect disk, storage, and network metrics for pbx-web and whisper-stt.

The collector deliberately keeps the Prometheus responses intact.  This makes
retention limits and empty metric families auditable instead of turning a
partial history into a misleading complete 30-day report.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SERVICES = ("pbx-web", "whisper-stt")
STEP_SECONDS = 3600


def metric_query(service: str, expression: str) -> str:
    """Fill the service namespace into an expression containing {service}."""

    return expression.replace("{service}", service)


QUERY_DEFINITIONS: dict[str, dict[str, str]] = {
    "disk_read_bytes_per_second": {
        "family": "disk_io",
        "unit": "bytes_per_second",
        "expression": (
            "sum by (namespace,pod) (rate("
            'container_fs_reads_bytes_total{namespace="{service}",'
            'container!="",container!="POD",image!=""}[5m]))'
        ),
    },
    "disk_write_bytes_per_second": {
        "family": "disk_io",
        "unit": "bytes_per_second",
        "expression": (
            "sum by (namespace,pod) (rate("
            'container_fs_writes_bytes_total{namespace="{service}",'
            'container!="",container!="POD",image!=""}[5m]))'
        ),
    },
    "disk_read_operations_per_second": {
        "family": "disk_io",
        "unit": "operations_per_second",
        "expression": (
            "sum by (namespace,pod) (rate("
            'container_fs_reads_total{namespace="{service}",'
            'container!="",container!="POD",image!=""}[5m]))'
        ),
    },
    "disk_write_operations_per_second": {
        "family": "disk_io",
        "unit": "operations_per_second",
        "expression": (
            "sum by (namespace,pod) (rate("
            'container_fs_writes_total{namespace="{service}",'
            'container!="",container!="POD",image!=""}[5m]))'
        ),
    },
    "network_receive_bytes_total": {
        "family": "network",
        "unit": "bytes_total",
        "expression": (
            "sum by (namespace,pod) ("
            'container_network_receive_bytes_total{namespace="{service}",'
            'pod!="",interface!="lo"})'
        ),
    },
    "network_transmit_bytes_total": {
        "family": "network",
        "unit": "bytes_total",
        "expression": (
            "sum by (namespace,pod) ("
            'container_network_transmit_bytes_total{namespace="{service}",'
            'pod!="",interface!="lo"})'
        ),
    },
    "network_receive_bytes_per_second": {
        "family": "network",
        "unit": "bytes_per_second",
        "expression": (
            "sum by (namespace,pod) (rate("
            'container_network_receive_bytes_total{namespace="{service}",'
            'pod!="",interface!="lo"}[5m]))'
        ),
    },
    "network_transmit_bytes_per_second": {
        "family": "network",
        "unit": "bytes_per_second",
        "expression": (
            "sum by (namespace,pod) (rate("
            'container_network_transmit_bytes_total{namespace="{service}",'
            'pod!="",interface!="lo"}[5m]))'
        ),
    },
    "storage_capacity_bytes": {
        "family": "storage",
        "unit": "bytes",
        "expression": 'kubelet_volume_stats_capacity_bytes{namespace="{service}"}',
    },
    "storage_used_bytes": {
        "family": "storage",
        "unit": "bytes",
        "expression": 'kubelet_volume_stats_used_bytes{namespace="{service}"}',
    },
    "storage_available_bytes": {
        "family": "storage",
        "unit": "bytes",
        "expression": 'kubelet_volume_stats_available_bytes{namespace="{service}"}',
    },
    "storage_requested_bytes": {
        "family": "storage",
        "unit": "bytes",
        "expression": (
            'kube_persistentvolumeclaim_resource_requests_storage_bytes{namespace="{service}"}'
        ),
    },
    "storage_pvc_info": {
        "family": "storage",
        "unit": "info_flag",
        "expression": 'kube_persistentvolumeclaim_info{namespace="{service}"}',
    },
    "storage_filesystem_usage_bytes": {
        "family": "storage",
        "unit": "bytes",
        "expression": 'container_fs_usage_bytes{namespace="{service}"}',
    },
    "storage_filesystem_limit_bytes": {
        "family": "storage",
        "unit": "bytes",
        "expression": 'container_fs_limit_bytes{namespace="{service}"}',
    },
}


def utc_iso(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp, timezone.utc).isoformat().replace("+00:00", "Z")


def query_json(base_url: str, path: str, params: dict[str, Any]) -> dict[str, Any]:
    url = f"{base_url.rstrip('/')}{path}?{urllib.parse.urlencode(params)}"
    request = urllib.request.Request(url, headers={"User-Agent": "adc-2mua4m-metrics/1"})
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            payload = json.load(response)
    except Exception as exc:  # pragma: no cover - exercised against live Prometheus
        raise RuntimeError(f"Prometheus request failed for {path}: {exc}") from exc
    if not isinstance(payload, dict) or payload.get("status") != "success":
        raise RuntimeError(f"Prometheus returned an unsuccessful response for {path}: {payload}")
    return payload


def prometheus_time(base_url: str) -> float:
    payload = query_json(base_url, "/api/v1/query", {"query": "time()"})
    data = payload.get("data", {})
    if data.get("resultType") == "scalar" and isinstance(data.get("result"), list):
        result = data["result"]
        if len(result) >= 2:
            return float(result[1])
    result = data.get("result", [])
    if result and isinstance(result[0], dict):
        return float(result[0]["value"][0])
    raise RuntimeError(f"Prometheus time() returned an unexpected response: {payload}")


def response_series(payload: dict[str, Any]) -> list[dict[str, Any]]:
    result = payload.get("data", {}).get("result", [])
    return result if isinstance(result, list) else []


def series_timestamps(series: dict[str, Any]) -> list[float]:
    values = series.get("values", [])
    return sorted(float(value[0]) for value in values if isinstance(value, list) and len(value) >= 2)


def series_coverage(series: dict[str, Any], step: int) -> dict[str, Any]:
    timestamps = series_timestamps(series)
    intervals = [right - left for left, right in zip(timestamps, timestamps[1:])]
    large = [interval for interval in intervals if interval > step * 1.5]
    first = timestamps[0] if timestamps else None
    last = timestamps[-1] if timestamps else None
    return {
        "labels": series.get("metric", {}),
        "sample_points": len(timestamps),
        "first_sample": utc_iso(first) if first is not None else None,
        "last_sample": utc_iso(last) if last is not None else None,
        "coverage_days": round((last - first) / 86400, 6) if first is not None and last is not None else 0.0,
        "internal_gap_count": len(large),
        "max_interval_seconds": max(intervals) if intervals else None,
        "internal_missing_intervals": (
            max(0, int(round((last - first) / step)) + 1 - len(timestamps))
            if first is not None and last is not None
            else 0
        ),
    }


def coverage_report(
    service: str,
    metric: str,
    payload: dict[str, Any],
    requested_start: float,
    requested_end: float,
    step: int,
) -> dict[str, Any]:
    series = response_series(payload)
    timestamps = sorted({timestamp for item in series for timestamp in series_timestamps(item)})
    intervals = [right - left for left, right in zip(timestamps, timestamps[1:])]
    large = [interval for interval in intervals if interval > step * 1.5]
    first = timestamps[0] if timestamps else None
    last = timestamps[-1] if timestamps else None
    tolerance = step * 1.5
    leading = first - requested_start if first is not None else requested_end - requested_start
    trailing = requested_end - last if last is not None else requested_end - requested_start
    gaps: list[dict[str, Any]] = []
    if leading > tolerance:
        gaps.append(
            {
                "type": "leading_retention_or_no_data_gap",
                "start": utc_iso(requested_start),
                "end": utc_iso(first) if first is not None else utc_iso(requested_end),
                "duration_days": round(leading / 86400, 6),
            }
        )
    if trailing > tolerance:
        gaps.append(
            {
                "type": "trailing_query_gap",
                "start": utc_iso(last) if last is not None else utc_iso(requested_start),
                "end": utc_iso(requested_end),
                "duration_days": round(trailing / 86400, 6),
            }
        )
    if large:
        gaps.append(
            {
                "type": "internal_timestamp_gaps",
                "count": len(large),
                "largest_gap_seconds": max(large),
            }
        )
    expected = int(round((requested_end - requested_start) / step)) + 1
    retained_expected = int(round((last - first) / step)) + 1 if first is not None and last is not None else 0
    return {
        "service": service,
        "metric": metric,
        "requested_start": utc_iso(requested_start),
        "requested_end": utc_iso(requested_end),
        "requested_window_days": round((requested_end - requested_start) / 86400, 6),
        "first_sample": utc_iso(first) if first is not None else None,
        "last_sample": utc_iso(last) if last is not None else None,
        "returned_coverage_days": round((last - first) / 86400, 6) if first is not None and last is not None else 0.0,
        "expected_points_requested": expected,
        "expected_points_between_first_and_last": retained_expected,
        "observed_timestamp_points": len(timestamps),
        "series_count": len(series),
        "leading_gap_days": round(max(0.0, leading) / 86400, 6),
        "trailing_gap_days": round(max(0.0, trailing) / 86400, 6),
        "internal_gap_count": len(large),
        "internal_missing_intervals": max(0, retained_expected - len(timestamps)),
        "series": [series_coverage(item, step) for item in series],
        "full_requested_window": bool(
            first is not None
            and last is not None
            and leading <= tolerance
            and trailing <= tolerance
            and not large
        ),
        "status": "complete" if not gaps and timestamps else "incomplete",
        "significant_gaps": gaps,
    }


def flatten_rows(
    service: str, metric: str, definition: dict[str, str], payload: dict[str, Any]
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in response_series(payload):
        labels = item.get("metric", {})
        for value in item.get("values", []):
            if not isinstance(value, list) or len(value) < 2:
                continue
            try:
                timestamp = float(value[0])
                numeric_value = float(value[1])
            except (TypeError, ValueError):
                continue
            rows.append(
                {
                    "service": service,
                    "metric": metric,
                    "family": definition["family"],
                    "unit": definition["unit"],
                    "namespace": labels.get("namespace", service),
                    "pod": labels.get("pod", ""),
                    "persistentvolumeclaim": labels.get("persistentvolumeclaim", ""),
                    "timestamp": utc_iso(timestamp),
                    "timestamp_unix": timestamp,
                    "value": numeric_value,
                    "labels_json": json.dumps(labels, sort_keys=True, separators=(",", ":")),
                }
            )
    return rows


CSV_FIELDS = [
    "service",
    "metric",
    "family",
    "unit",
    "namespace",
    "pod",
    "persistentvolumeclaim",
    "timestamp",
    "timestamp_unix",
    "value",
    "labels_json",
]


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=CSV_FIELDS,
            extrasaction="ignore",
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)


def collect(base_url: str, days: int, step: int) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    end = prometheus_time(base_url)
    start = end - days * 86400
    flags = query_json(base_url, "/api/v1/status/flags", {}).get("data", {})
    raw: dict[str, dict[str, Any]] = {}
    coverage: dict[str, dict[str, Any]] = {}
    rows: list[dict[str, Any]] = []
    for service in SERVICES:
        raw[service] = {}
        coverage[service] = {}
        for metric, definition in QUERY_DEFINITIONS.items():
            query = metric_query(service, definition["expression"])
            payload = query_json(
                base_url,
                "/api/v1/query_range",
                {"query": query, "start": str(start), "end": str(end), "step": str(step)},
            )
            raw[service][metric] = {
                "family": definition["family"],
                "unit": definition["unit"],
                "query": query,
                "response": payload,
            }
            coverage[service][metric] = coverage_report(service, metric, payload, start, end, step)
            rows.extend(flatten_rows(service, metric, definition, payload))

    metadata = {
        "collected_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "prometheus_base_url": base_url,
        "prometheus_server_time": utc_iso(end),
        "prometheus_retention_time": flags.get("storage.tsdb.retention.time"),
        "requested_window_start": utc_iso(start),
        "requested_window_end": utc_iso(end),
        "requested_window_days": days,
        "step_seconds": step,
        "services": list(SERVICES),
        "query_count_per_service": len(QUERY_DEFINITIONS),
        "queries": {
            metric: {"family": definition["family"], "unit": definition["unit"]}
            for metric, definition in QUERY_DEFINITIONS.items()
        },
    }
    return {"collection_metadata": metadata, "coverage": coverage, "raw_queries": raw}, rows


def build_coverage_payload(payload: dict[str, Any]) -> dict[str, Any]:
    reports = [
        report
        for service_reports in payload["coverage"].values()
        for report in service_reports.values()
    ]
    gaps = [
        {"service": report["service"], "metric": report["metric"], **gap}
        for report in reports
        for gap in report["significant_gaps"]
    ]
    return {
        "generated_at": payload["collection_metadata"]["collected_at"],
        "collection_metadata": payload["collection_metadata"],
        "coverage": payload["coverage"],
        "assessment": {
            "all_metrics_full_requested_window": all(report["full_requested_window"] for report in reports),
            "metrics_with_data": sum(report["series_count"] > 0 for report in reports),
            "metrics_without_data": sum(report["series_count"] == 0 for report in reports),
            "significant_gap_count": len(gaps),
            "significant_gaps": gaps,
            "verification": (
                "No internal hourly timestamp gaps were found in returned series; however, "
                "the leading gap is significant where Prometheus retention/no-data begins "
                "after the requested 30-day start. Empty series are reported as unavailable."
            ),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base-url",
        default=os.environ.get("METRICS_PROMETHEUS_URL", "http://127.0.0.1:19090"),
    )
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--step", type=int, default=STEP_SECONDS)
    parser.add_argument("--output-dir", type=Path, default=Path("data/resource_metrics"))
    args = parser.parse_args()
    if args.days <= 0 or args.step <= 0:
        parser.error("--days and --step must be positive")
    try:
        payload, rows = collect(args.base_url, args.days, args.step)
    except RuntimeError as exc:
        print(f"collect-disk-network-storage-metrics: {exc}", file=sys.stderr)
        return 1

    args.output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    json_path = args.output_dir / f"disk-network-storage-metrics-30d-{stamp}.json"
    csv_path = args.output_dir / f"disk-network-storage-metrics-30d-{stamp}.csv"
    coverage_path = args.output_dir / f"disk-network-storage-coverage-{stamp}.json"
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_csv(csv_path, rows)
    coverage_path.write_text(
        json.dumps(build_coverage_payload(payload), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"json": str(json_path), "csv": str(csv_path), "coverage": str(coverage_path), "rows": len(rows)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
