#!/usr/bin/env python3
"""Collect CPU and memory usage for pbx-web and whisper-stt.

The collector asks Prometheus for the requested 30-day range.  Prometheus may
return only its retained portion of that range; the raw responses are kept so
that retention gaps are visible and independently auditable.  The CSV contains
one row per returned sample and the coverage JSON explains gaps in the union of
timestamps and in each returned pod series.
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
METRIC_QUERIES = {
    "cpu_usage": (
        'sum by (namespace,pod) (rate('
        'container_cpu_usage_seconds_total{namespace="{namespace}",'
        'container!="",container!="POD",image!=""}[5m]))'
    ),
    "memory_working_set": (
        'sum by (namespace,pod) ('
        'container_memory_working_set_bytes{namespace="{namespace}",'
        'container!="",container!="POD",image!=""})'
    ),
}


def utc_iso(seconds: float) -> str:
    return datetime.fromtimestamp(seconds, timezone.utc).isoformat().replace("+00:00", "Z")


def query_json(base_url: str, path: str, params: dict[str, Any]) -> dict[str, Any]:
    url = f"{base_url.rstrip('/')}{path}?{urllib.parse.urlencode(params)}"
    request = urllib.request.Request(url, headers={"User-Agent": "adc-resource-metrics/1"})
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            payload = json.load(response)
    except Exception as exc:  # pragma: no cover - exercised against the live endpoint
        raise RuntimeError(f"Prometheus request failed for {path}: {exc}") from exc
    if not isinstance(payload, dict) or payload.get("status") != "success":
        raise RuntimeError(f"Prometheus returned an unsuccessful response for {path}: {payload}")
    return payload


def server_time(base_url: str) -> float:
    payload = query_json(base_url, "/api/v1/query", {"query": "time()"})
    data = payload.get("data", {})
    result_type = data.get("resultType")
    result = data.get("result")
    if result_type == "scalar" and isinstance(result, list) and result:
        return float(result[0])
    if isinstance(result, list) and result and isinstance(result[0], dict):
        return float(result[0]["value"][0])
    raise RuntimeError(f"Prometheus time() returned an unexpected shape: {payload}")


def series_coverage(series: dict[str, Any], step: int) -> dict[str, Any]:
    values = series.get("values", [])
    timestamps = sorted(float(value[0]) for value in values if isinstance(value, list) and len(value) >= 2)
    gaps = [right - left for left, right in zip(timestamps, timestamps[1:])]
    large_gaps = [gap for gap in gaps if gap > step * 1.5]
    first = timestamps[0] if timestamps else None
    last = timestamps[-1] if timestamps else None
    expected_between = int(round((last - first) / step)) + 1 if first is not None and last is not None else 0
    return {
        "labels": series.get("metric", {}),
        "sample_points": len(timestamps),
        "first_sample": utc_iso(first) if first is not None else None,
        "last_sample": utc_iso(last) if last is not None else None,
        "coverage_days": round((last - first) / 86400, 6) if first is not None and last is not None else 0.0,
        "internal_gap_count": len(large_gaps),
        "max_interval_seconds": max(gaps) if gaps else None,
        "missing_intervals_between_first_and_last": max(0, expected_between - len(timestamps)),
    }


def coverage_report(
    *,
    service: str,
    metric: str,
    payload: dict[str, Any],
    requested_start: float,
    requested_end: float,
    step: int,
) -> dict[str, Any]:
    series = payload.get("data", {}).get("result", [])
    timestamps = sorted(
        {
            float(value[0])
            for item in series
            for value in item.get("values", [])
            if isinstance(value, list) and len(value) >= 2
        }
    )
    gaps = [right - left for left, right in zip(timestamps, timestamps[1:])]
    large_gaps = [gap for gap in gaps if gap > step * 1.5]
    first = timestamps[0] if timestamps else None
    last = timestamps[-1] if timestamps else None
    expected_requested = int(round((requested_end - requested_start) / step)) + 1
    expected_retained = int(round((last - first) / step)) + 1 if first is not None and last is not None else 0
    leading_seconds = max(0.0, first - requested_start) if first is not None else requested_end - requested_start
    trailing_seconds = max(0.0, requested_end - last) if last is not None else requested_end - requested_start
    pod_series = [series_coverage(item, step) for item in series]
    internal_gap_count = len(large_gaps)
    full_window = bool(
        first is not None
        and last is not None
        and leading_seconds <= step * 1.5
        and trailing_seconds <= step * 1.5
        and internal_gap_count == 0
    )
    significant_gaps: list[dict[str, Any]] = []
    if leading_seconds > step * 1.5:
        significant_gaps.append(
            {
                "type": "leading_retention_or_no_data_gap",
                "start": utc_iso(requested_start),
                "end": utc_iso(first) if first is not None else utc_iso(requested_end),
                "duration_days": round(leading_seconds / 86400, 6),
            }
        )
    if trailing_seconds > step * 1.5:
        significant_gaps.append(
            {
                "type": "trailing_query_gap",
                "start": utc_iso(last) if last is not None else utc_iso(requested_start),
                "end": utc_iso(requested_end),
                "duration_days": round(trailing_seconds / 86400, 6),
            }
        )
    if internal_gap_count:
        significant_gaps.append(
            {
                "type": "internal_timestamp_gaps",
                "count": internal_gap_count,
                "largest_gap_seconds": max(large_gaps),
            }
        )
    return {
        "service": service,
        "metric": metric,
        "requested_start": utc_iso(requested_start),
        "requested_end": utc_iso(requested_end),
        "first_sample": utc_iso(first) if first is not None else None,
        "last_sample": utc_iso(last) if last is not None else None,
        "requested_window_days": round((requested_end - requested_start) / 86400, 6),
        "returned_coverage_days": round((last - first) / 86400, 6) if first is not None and last is not None else 0.0,
        "expected_points_requested": expected_requested,
        "expected_points_between_first_and_last": expected_retained,
        "observed_timestamp_points": len(timestamps),
        "leading_gap_days": round(leading_seconds / 86400, 6),
        "trailing_gap_days": round(trailing_seconds / 86400, 6),
        "internal_gap_count": internal_gap_count,
        "internal_missing_intervals": max(0, expected_retained - len(timestamps)),
        "series_count": len(series),
        "series": pod_series,
        "full_requested_window": full_window,
        "status": "complete" if full_window else "incomplete",
        "significant_gaps": significant_gaps,
    }


def flattened_rows(service: str, metric: str, payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in payload.get("data", {}).get("result", []):
        labels = item.get("metric", {})
        for value in item.get("values", []):
            if not isinstance(value, list) or len(value) < 2:
                continue
            timestamp = float(value[0])
            numeric_value = float(value[1])
            row = {
                "service": service,
                "metric": metric,
                "namespace": labels.get("namespace", service),
                "pod": labels.get("pod", ""),
                "timestamp": utc_iso(timestamp),
                "timestamp_unix": timestamp,
                "value": numeric_value,
                "unit": "cores" if metric == "cpu_usage" else "bytes",
            }
            if metric == "cpu_usage":
                row["cpu_cores"] = numeric_value
                row["cpu_percent_of_one_core"] = numeric_value * 100.0
            else:
                row["memory_bytes"] = numeric_value
                row["memory_mib"] = numeric_value / (1024 * 1024)
            rows.append(row)
    return rows


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fields = [
        "service",
        "metric",
        "namespace",
        "pod",
        "timestamp",
        "timestamp_unix",
        "value",
        "unit",
        "cpu_cores",
        "cpu_percent_of_one_core",
        "memory_bytes",
        "memory_mib",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def collect(base_url: str, days: int, step: int) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    end = server_time(base_url)
    start = end - days * 86400
    flags = query_json(base_url, "/api/v1/status/flags", {}).get("data", {})
    raw: dict[str, Any] = {}
    coverage: dict[str, Any] = {}
    rows: list[dict[str, Any]] = []
    for service in SERVICES:
        raw[service] = {}
        coverage[service] = {}
        for metric, template in METRIC_QUERIES.items():
            # The PromQL label matcher contains literal braces, so replace
            # only the explicit namespace placeholder instead of using
            # str.format on the complete expression.
            query = template.replace("{namespace}", service)
            payload = query_json(
                base_url,
                "/api/v1/query_range",
                {"query": query, "start": str(start), "end": str(end), "step": str(step)},
            )
            raw[service][metric] = {"query": query, "response": payload}
            coverage[service][metric] = coverage_report(
                service=service,
                metric=metric,
                payload=payload,
                requested_start=start,
                requested_end=end,
                step=step,
            )
            rows.extend(flattened_rows(service, metric, payload))
    return {
        "collection_metadata": {
            "collected_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "prometheus_base_url": base_url,
            "prometheus_server_time": utc_iso(end),
            "prometheus_retention_time": flags.get("storage.tsdb.retention.time"),
            "requested_window_start": utc_iso(start),
            "requested_window_end": utc_iso(end),
            "requested_window_days": days,
            "step_seconds": step,
            "services": list(SERVICES),
            "queries": {
                "cpu_usage": "5-minute rate of container_cpu_usage_seconds_total, aggregated by pod",
                "memory_working_set": "container_memory_working_set_bytes, aggregated by pod",
            },
        },
        "coverage": coverage,
        "raw_queries": raw,
    }, rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=os.environ.get("METRICS_PROMETHEUS_URL", "http://127.0.0.1:19090"))
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--step", type=int, default=3600)
    parser.add_argument("--output-dir", type=Path, default=Path("data/resource_metrics"))
    args = parser.parse_args()
    if args.days <= 0 or args.step <= 0:
        parser.error("--days and --step must be positive")

    try:
        payload, rows = collect(args.base_url, args.days, args.step)
    except RuntimeError as exc:
        print(f"collect-resource-metrics: {exc}", file=sys.stderr)
        return 1

    args.output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    json_path = args.output_dir / f"resource-metrics-30d-{stamp}.json"
    csv_path = args.output_dir / f"resource-metrics-30d-{stamp}.csv"
    coverage_path = args.output_dir / f"resource-metrics-coverage-{stamp}.json"
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_csv(csv_path, rows)
    coverage_payload = {
        "generated_at": payload["collection_metadata"]["collected_at"],
        "collection_metadata": payload["collection_metadata"],
        "coverage": payload["coverage"],
        "assessment": {
            "all_metrics_full_requested_window": all(
                metric_report["full_requested_window"]
                for service_report in payload["coverage"].values()
                for metric_report in service_report.values()
            ),
            "total_significant_gap_records": sum(
                len(metric_report["significant_gaps"])
                for service_report in payload["coverage"].values()
                for metric_report in service_report.values()
            ),
            "interpretation": (
                "A missing leading interval is a retention/no-data gap; internal gaps are tested"
                " at the requested hourly resolution. The returned range is not called a full"
                " 30-day history unless both window edges and internal timestamps are covered."
            ),
        },
    }
    coverage_path.write_text(json.dumps(coverage_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"json": str(json_path), "csv": str(csv_path), "coverage": str(coverage_path), "rows": len(rows)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
