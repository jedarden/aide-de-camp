#!/usr/bin/env python3
"""Query the Prometheus and VictoriaLogs backends for workload metrics.

The ardenone cluster exposes Prometheus and VictoriaLogs as internal
ClusterIP services.  This module deliberately talks to their HTTP APIs over
an already-established port-forward; it never creates or mutates Kubernetes
resources.  ``config/metrics-query.json`` contains the verified service names
and the local port-forward commands.

The Prometheus API is also the API used by VictoriaMetrics, so the client only
depends on the Prometheus-compatible HTTP contract.  The current cluster uses
Prometheus for typed resource metrics and VictoriaLogs for log-based historical
queries; it does not expose a VictoriaMetrics service.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping
from urllib.parse import urljoin

import httpx

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG_PATH = REPOSITORY_ROOT / "config" / "metrics-query.json"
DEFAULT_NAMESPACES = ("pbx-web", "whisper-stt")
REQUIRED_LABELS = ("namespace", "pod", "container", "job")
EXPECTED_METRICS: tuple[tuple[str, str], ...] = (
    ("container_cpu_usage_seconds_total", "counter"),
    ("container_memory_working_set_bytes", "gauge"),
    ("kube_pod_container_status_restarts_total", "counter"),
    ("kube_pod_info", "gauge"),
    ("prober_probe_duration_seconds_bucket", "histogram"),
)


class MetricsQueryError(RuntimeError):
    """Raised when a metrics backend returns an unusable response."""


def _utc_timestamp(seconds: float | int | None) -> str | None:
    if seconds is None:
        return None
    return datetime.fromtimestamp(float(seconds), tz=timezone.utc).isoformat().replace(
        "+00:00", "Z"
    )


def _as_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _selector(namespace: str) -> str:
    return f'{{namespace="{namespace}"}}'


def _json_lines(body: str) -> list[dict[str, Any]]:
    """Decode VictoriaLogs' newline-delimited JSON response."""
    rows: list[dict[str, Any]] = []
    for line in body.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError as exc:
            raise MetricsQueryError(f"VictoriaLogs returned invalid JSON: {exc}") from exc
        if isinstance(item, dict):
            rows.append(item)
    return rows


def _request_json(
    client: httpx.Client,
    method: str,
    url: str,
    *,
    params: Any = None,
) -> dict[str, Any]:
    try:
        response = client.request(method, url, params=params)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise MetricsQueryError(f"HTTP request failed for {url}: {exc}") from exc
    try:
        payload = response.json()
    except ValueError as exc:
        raise MetricsQueryError(f"Backend returned non-JSON response for {url}") from exc
    if not isinstance(payload, dict):
        raise MetricsQueryError(f"Backend returned an unexpected JSON shape for {url}")
    return payload


@dataclass(frozen=True)
class Availability:
    """Coverage result for one backend and namespace."""

    backend: str
    namespace: str
    requested_start: str
    requested_end: str
    first_sample: str | None
    last_sample: str | None
    sample_points: int
    expected_points: int | None
    internal_gaps: int
    coverage_days: float
    data_available: bool
    full_requested_window: bool
    detail: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "backend": self.backend,
            "namespace": self.namespace,
            "requested_start": self.requested_start,
            "requested_end": self.requested_end,
            "first_sample": self.first_sample,
            "last_sample": self.last_sample,
            "sample_points": self.sample_points,
            "expected_points": self.expected_points,
            "internal_gaps": self.internal_gaps,
            "coverage_days": round(self.coverage_days, 3),
            "data_available": self.data_available,
            "full_requested_window": self.full_requested_window,
            "detail": self.detail,
        }


class PrometheusClient:
    """Small Prometheus-compatible API client for typed resource metrics."""

    def __init__(
        self,
        base_url: str,
        *,
        timeout: float = 30.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/") + "/"
        self._client = httpx.Client(timeout=timeout, transport=transport)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "PrometheusClient":
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()

    def _get(self, path: str, params: Any = None) -> dict[str, Any]:
        payload = _request_json(self._client, "GET", urljoin(self.base_url, path.lstrip("/")), params=params)
        if payload.get("status") != "success":
            error = payload.get("error") or payload.get("errorType") or "unknown API error"
            raise MetricsQueryError(f"Prometheus query failed: {error}")
        return payload

    def health(self) -> dict[str, Any]:
        """Return health and build information from Prometheus."""
        try:
            response = self._client.get(urljoin(self.base_url, "-/healthy"))
            response.raise_for_status()
            build = self._get("/api/v1/status/buildinfo")["data"]
            flags = self._get("/api/v1/status/flags")["data"]
            return {
                "backend": "prometheus",
                "ok": True,
                "health": response.text.strip(),
                "version": build.get("version"),
                "retention_time": flags.get("storage.tsdb.retention.time"),
                "base_url": self.base_url.rstrip("/"),
            }
        except (httpx.HTTPError, MetricsQueryError) as exc:
            return {
                "backend": "prometheus",
                "ok": False,
                "base_url": self.base_url.rstrip("/"),
                "error": str(exc),
            }

    def instant_query(self, query: str, *, timestamp: float | None = None) -> dict[str, Any]:
        params: list[tuple[str, str]] = [("query", query)]
        if timestamp is not None:
            params.append(("time", str(timestamp)))
        return self._get("/api/v1/query", params=params)

    def range_query(self, query: str, start: float, end: float, step: int) -> dict[str, Any]:
        return self._get(
            "/api/v1/query_range",
            params={"query": query, "start": str(start), "end": str(end), "step": str(step)},
        )

    def server_time(self) -> float:
        result = self.instant_query("time()")["data"]["result"]
        # Prometheus returns time() as a scalar [timestamp, value], while some
        # compatible backends return a one-series vector.
        if isinstance(result, list) and len(result) == 2 and _as_float(result[0]) is not None:
            return float(result[0])
        if isinstance(result, list) and result and isinstance(result[0], dict):
            return float(result[0]["value"][0])
        raise MetricsQueryError("Prometheus time() returned an unexpected shape")

    def metric_counts(self, namespace: str) -> dict[str, int]:
        query = f"count by (__name__) ({_selector(namespace)})"
        results = self.instant_query(query)["data"]["result"]
        return {
            item["metric"]["__name__"]: int(float(item["value"][1]))
            for item in results
            if item.get("metric", {}).get("__name__")
        }

    def label_names(self, namespace: str) -> list[str]:
        payload = self._get("/api/v1/labels", params=[("match[]", _selector(namespace))])
        return sorted(str(label) for label in payload["data"])

    def metadata(self, metric_name: str) -> list[dict[str, Any]]:
        return list(self._get("/api/v1/metadata", params={"metric": metric_name})["data"].get(metric_name, []))

    def inventory(self, namespace: str) -> dict[str, Any]:
        counts = self.metric_counts(namespace)
        labels = self.label_names(namespace)
        expected: list[dict[str, Any]] = []
        for metric_name, expected_type in EXPECTED_METRICS:
            present = metric_name in counts
            metadata = self.metadata(metric_name) if present else []
            observed_type = metadata[0].get("type") if metadata else None
            if observed_type is None and metric_name.endswith("_bucket"):
                observed_type = "histogram (bucket series; metadata is on the base family)"
            expected.append(
                {
                    "name": metric_name,
                    "expected_type": expected_type,
                    "observed_type": observed_type,
                    "series_count": counts.get(metric_name, 0),
                    "available": present,
                    "metadata": metadata,
                }
            )
        label_checks = {
            label: {"available": label in labels, "observed": label in labels}
            for label in REQUIRED_LABELS
        }
        return {
            "namespace": namespace,
            "selector": _selector(namespace),
            "metric_family_count": len(counts),
            "metrics": sorted(
                [{"name": name, "series_count": count} for name, count in counts.items()],
                key=lambda item: item["name"],
            ),
            "label_names": labels,
            "required_labels": label_checks,
            "expected_metrics": expected,
            "all_expected_metrics_available": all(item["available"] for item in expected),
            "all_required_labels_available": all(item["available"] for item in label_checks.values()),
        }

    def availability(self, namespace: str, *, days: int = 30, step: int = 3600) -> Availability:
        end = self.server_time()
        start = end - days * 86400
        payload = self.range_query(f"count({_selector(namespace)})", start, end, step)
        series = payload["data"].get("result", [])
        values = series[0].get("values", []) if series else []
        timestamps = [float(value[0]) for value in values if len(value) >= 2]
        first = timestamps[0] if timestamps else None
        last = timestamps[-1] if timestamps else None
        internal_gaps = sum(
            1 for left, right in zip(timestamps, timestamps[1:]) if right - left > step * 1.5
        )
        expected_points = math.floor((end - start) / step) + 1
        full_window = bool(
            first is not None
            and last is not None
            and first <= start + step
            and last >= end - step
            and internal_gaps == 0
        )
        coverage_days = ((last - first) / 86400) if first is not None and last is not None else 0.0
        return Availability(
            backend="prometheus",
            namespace=namespace,
            requested_start=_utc_timestamp(start) or "",
            requested_end=_utc_timestamp(end) or "",
            first_sample=_utc_timestamp(first),
            last_sample=_utc_timestamp(last),
            sample_points=len(timestamps),
            expected_points=expected_points,
            internal_gaps=internal_gaps,
            coverage_days=coverage_days,
            data_available=bool(timestamps),
            full_requested_window=full_window,
            detail="Prometheus retention is reported by /api/v1/status/flags.",
        )


class VictoriaLogsClient:
    """Client for VictoriaLogs health, raw log, and coverage queries."""

    def __init__(
        self,
        base_url: str,
        *,
        query_path: str = "/select/logsql/query",
        timeout: float = 120.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/") + "/"
        self.query_path = query_path
        self._client = httpx.Client(timeout=timeout, transport=transport)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "VictoriaLogsClient":
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()

    def health(self) -> dict[str, Any]:
        try:
            response = self._client.get(urljoin(self.base_url, "health"))
            response.raise_for_status()
            return {
                "backend": "victorialogs",
                "ok": True,
                "health": response.text.strip(),
                "base_url": self.base_url.rstrip("/"),
            }
        except httpx.HTTPError as exc:
            return {
                "backend": "victorialogs",
                "ok": False,
                "base_url": self.base_url.rstrip("/"),
                "error": str(exc),
            }

    def query(self, query: str, *, start: str | None = None, end: str | None = None) -> list[dict[str, Any]]:
        params: dict[str, str] = {"query": query}
        if start:
            params["start"] = start
        if end:
            params["end"] = end
        try:
            response = self._client.get(urljoin(self.base_url, self.query_path.lstrip("/")), params=params)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise MetricsQueryError(f"VictoriaLogs query failed: {exc}") from exc
        return _json_lines(response.text)

    def availability(self, namespace: str, *, start: str, end: str) -> dict[str, Any]:
        query = (
            f'{_selector(namespace)} | stats count() as count, '
            "min(_time) as oldest, max(_time) as newest"
        )
        rows = self.query(query, start=start, end=end)
        row = rows[0] if rows else {}
        oldest = row.get("oldest")
        newest = row.get("newest")
        oldest_dt = _parse_datetime(oldest)
        newest_dt = _parse_datetime(newest)
        start_dt = _parse_datetime(start)
        end_dt = _parse_datetime(end)
        coverage_days = (
            (newest_dt - oldest_dt).total_seconds() / 86400
            if oldest_dt and newest_dt
            else 0.0
        )
        return {
            "backend": "victorialogs",
            "namespace": namespace,
            "requested_start": start,
            "requested_end": end,
            "first_sample": oldest,
            "last_sample": newest,
            "log_count": int(row["count"]) if str(row.get("count", "")).isdigit() else 0,
            "coverage_days": round(coverage_days, 3),
            "data_available": bool(row),
            "full_requested_window": bool(
                oldest_dt and newest_dt and start_dt and end_dt and oldest_dt <= start_dt and newest_dt >= end_dt
            ),
            "detail": "VictoriaLogs returns log records, not typed Prometheus metric families.",
        }


def _parse_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


class MetricsQueryClient:
    """Configured facade for both backends and both service namespaces."""

    def __init__(self, config: Mapping[str, Any]) -> None:
        self.config = config
        prometheus = config["prometheus"]
        victorialogs = config["victorialogs"]
        self.prometheus = PrometheusClient(prometheus["base_url"])
        self.victorialogs = VictoriaLogsClient(
            victorialogs["base_url"], query_path=victorialogs.get("query_path", "/select/logsql/query")
        )
        self.namespaces = tuple(
            service["namespace"] for service in config.get("services", {}).values()
        ) or DEFAULT_NAMESPACES

    def close(self) -> None:
        self.prometheus.close()
        self.victorialogs.close()

    def __enter__(self) -> "MetricsQueryClient":
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()

    def health(self) -> dict[str, Any]:
        return {
            "cluster": self.config.get("cluster"),
            "prometheus": self.prometheus.health(),
            "victorialogs": self.victorialogs.health(),
        }

    def validate(self) -> dict[str, Any]:
        return {
            "prometheus": {
                namespace: self.prometheus.inventory(namespace) for namespace in self.namespaces
            }
        }

    def availability(self, *, days: int | None = None, step: int | None = None) -> dict[str, Any]:
        availability_config = self.config.get("availability", {})
        days = days or int(availability_config.get("days", 30))
        step = step or int(availability_config.get("step_seconds", 3600))
        end = self.prometheus.server_time()
        start = end - days * 86400
        start_iso = _utc_timestamp(start) or ""
        end_iso = _utc_timestamp(end) or ""
        return {
            "days_requested": days,
            "step_seconds": step,
            "prometheus": {
                namespace: self.prometheus.availability(namespace, days=days, step=step).as_dict()
                for namespace in self.namespaces
            },
            "victorialogs": {
                namespace: self.victorialogs.availability(namespace, start=start_iso, end=end_iso)
                for namespace in self.namespaces
            },
        }

    def report(self, *, days: int | None = None, step: int | None = None) -> dict[str, Any]:
        return {
            "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "config": {
                "cluster": self.config.get("cluster"),
                "prometheus_url": self.config["prometheus"]["base_url"],
                "victorialogs_url": self.config["victorialogs"]["base_url"],
            },
            "health": self.health(),
            "validation": self.validate(),
            "availability": self.availability(days=days, step=step),
        }


def load_config(path: str | Path = DEFAULT_CONFIG_PATH) -> dict[str, Any]:
    with Path(path).open(encoding="utf-8") as handle:
        config = json.load(handle)
    if not isinstance(config, dict):
        raise ValueError(f"Metrics configuration must be a JSON object: {path}")
    for backend in ("prometheus", "victorialogs"):
        if not config.get(backend, {}).get("base_url"):
            raise ValueError(f"Missing {backend}.base_url in {path}")
    return config


def _write_or_print(payload: Mapping[str, Any], output: str | None) -> None:
    rendered = json.dumps(payload, indent=2, sort_keys=True)
    if output:
        Path(output).write_text(rendered + "\n", encoding="utf-8")
    else:
        print(rendered)


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=os.environ.get("METRICS_QUERY_CONFIG", str(DEFAULT_CONFIG_PATH)))
    parser.add_argument("--output", help="Write JSON to this path instead of stdout")
    parser.add_argument("command", choices=("health", "validate", "availability", "report"))
    parser.add_argument("--days", type=int, default=None)
    parser.add_argument("--step", type=int, default=None, help="Prometheus range-query step in seconds")
    args = parser.parse_args(list(argv) if argv is not None else None)

    try:
        with MetricsQueryClient(load_config(args.config)) as client:
            if args.command == "health":
                payload = client.health()
            elif args.command == "validate":
                payload = client.validate()
            elif args.command == "availability":
                payload = client.availability(days=args.days, step=args.step)
            else:
                payload = client.report(days=args.days, step=args.step)
        _write_or_print(payload, args.output)
    except (OSError, ValueError, MetricsQueryError) as exc:
        print(f"metrics-query: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
