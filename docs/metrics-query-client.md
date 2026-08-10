# Metrics query client

This repository now includes an installable `metrics-query` command backed by
`src/metrics_query_client.py`. It uses the Prometheus-compatible HTTP API for
typed resource metrics and the VictoriaLogs LogSQL API for historical log
coverage. No additional Python dependency is required beyond the existing
`httpx` dependency.

The verified cluster endpoints are configured in
[`config/metrics-query.json`](../config/metrics-query.json):

| Backend | Kubernetes service | Local URL | Purpose | Retention |
| --- | --- | --- | --- | ---: |
| Prometheus 3.10.0 | `monitoring/kube-prometheus-stack-arde-prometheus:9090` | `http://127.0.0.1:19090` | PromQL resource metrics | 10 days |
| VictoriaLogs | `monitoring/vlogs-server:9428` | `http://127.0.0.1:19428` | LogSQL historical evidence | 28 days |

The local ports are intentional: port 9090 is already used by another local
service in this environment. The configured port-forward commands are
read-only and are included in the JSON configuration.

## Install and connect

```bash
python3 -m pip install -e .

# Terminal 1
kubectl --server=http://traefik-ardenone-cluster:8001 port-forward \
  -n monitoring svc/kube-prometheus-stack-arde-prometheus 19090:9090

# Terminal 2
kubectl --server=http://traefik-ardenone-cluster:8001 port-forward \
  -n monitoring svc/vlogs-server 19428:9428

metrics-query --config config/metrics-query.json health
metrics-query --config config/metrics-query.json validate
metrics-query --config config/metrics-query.json availability
metrics-query --config config/metrics-query.json report \
  --output data/metrics-query-verification-$(date -u +%Y%m%d).json
```

The same commands work without installing the package by replacing
`metrics-query` with `python3 -m src.metrics_query_client`.

`health` checks `/-/healthy`, Prometheus build information and retention flags,
plus VictoriaLogs `/health`. `validate` discovers every Prometheus metric
family under each namespace selector, checks the required labels, and queries
metadata for representative families. `availability` uses a Prometheus
`query_range` at a one-hour step and a VictoriaLogs `stats min(_time),
max(_time)` query; an instant query is deliberately not treated as historical
coverage.

## Available metric families

The live verification on 2026-08-10 found 130 Prometheus metric families for
`pbx-web` and 150 for `whisper-stt`. The complete names and current series
counts are in
[`data/metrics-query-verification-20260810.json`](../data/metrics-query-verification-20260810.json),
under `validation.prometheus.<service>.metrics`.

The families common to both services include:

- Container resource families: `container_cpu_usage_seconds_total`,
  `container_memory_working_set_bytes`, `container_memory_usage_bytes`,
  `container_memory_cache`, `container_network_receive_bytes_total`,
  `container_network_transmit_bytes_total`, `container_fs_reads_bytes_total`,
  `container_fs_writes_bytes_total`, `container_oom_events_total`, and the
  container pressure, process, socket, thread, and start-time families.
- Kubernetes workload state: `kube_pod_info`, `kube_pod_container_info`,
  `kube_pod_container_resource_requests`,
  `kube_pod_container_resource_limits`,
  `kube_pod_container_status_ready`,
  `kube_pod_container_status_restarts_total`,
  `kube_pod_container_status_running`, `kube_pod_status_phase`,
  `kube_pod_status_reason`, and `kube_pod_owner`.
- Workload and service state: `kube_deployment_*`, `kube_replicaset_*`,
  `kube_service_*`, `kube_endpointslice_*`, `kube_configmap_*`, and
  `kube_secret_*` families.
- Probes and recording rules: `prober_probe_duration_seconds_bucket`,
  `prober_probe_duration_seconds_count`,
  `prober_probe_duration_seconds_sum`, `prober_probe_total`, and the
  `namespace_*` and `node_namespace_pod*` recording-rule families.

The current service-specific families are:

- `pbx-web`: `kube_networkpolicy_created`,
  `kube_networkpolicy_spec_egress_rules`, and
  `kube_networkpolicy_spec_ingress_rules`.
- `whisper-stt`: PVC/storage families including
  `kube_persistentvolumeclaim_*`, `kube_pod_init_container_*`,
  `kube_pod_spec_volumes_persistentvolumeclaims_*`,
  `kubelet_volume_stats_*`, and `pv_collector_bound_pvc_count`.

Both services expose the following labels in the namespace-scoped series:
`namespace`, `pod`, `container`, and `job`. The `job` label identifies the
collector (`kubelet` or `kube-state-metrics`), not the application. Neither
service currently exposes application-owned `/metrics` data or a ServiceMonitor;
these are Kubernetes infrastructure metrics selected with, for example:

```promql
container_cpu_usage_seconds_total{namespace="pbx-web"}
kube_pod_container_status_restarts_total{namespace="whisper-stt"}
container_memory_working_set_bytes{namespace=~"pbx-web|whisper-stt"}
```

## Types and naming conventions

Prometheus metadata reported the following types:

| Type | Naming convention | Examples |
| --- | --- | --- |
| Counter | Cumulative values normally end in `_total`; use `rate()` or `increase()`. | `container_cpu_usage_seconds_total`, `kube_pod_container_status_restarts_total` |
| Gauge | Current state or level, commonly with `_bytes` or `_seconds`. | `container_memory_working_set_bytes`, `kube_pod_info` |
| Histogram | A family is represented by `_bucket`, `_count`, and `_sum`; use `histogram_quantile()` over buckets. | `prober_probe_duration_seconds_bucket` |
| Summary | Quantile-labelled samples plus `_count` and `_sum`; no Summary family was returned for either service selector. | Not present in either service namespace |

Names use lowercase snake case. Units belong in the name (`_seconds`,
`_bytes`), cumulative counters use `_total`, and Kubernetes exporter families
use `kube_` while container runtime families use `container_`. Recording rules
use colons, for example
`namespace_cpu:kube_pod_container_resource_requests:sum`. Service names are
label values and namespace selectors, not invented `pbx_web_` or
`whisper_stt_` prefixes.

## 30-day verification result

The requested rolling period at verification time was 2026-07-11 through
2026-08-10 UTC.

| Service | Prometheus samples | Prometheus full 30d? | VictoriaLogs oldest log | VictoriaLogs full 30d? |
| --- | ---: | --- | --- | --- |
| `pbx-web` | 257 hourly points from 2026-07-30 18:31 UTC | No; 10-day retention | 2026-07-13 00:00 UTC | No; 28-day retention |
| `whisper-stt` | 257 hourly points from 2026-07-30 18:31 UTC | No; 10-day retention | 2026-07-13 00:00 UTC | No; 28-day retention |

Both backends are connected and both services have current data, but neither
backend provides a full 30-day history. Prometheus had no internal one-hour
gaps in its retained interval. VictoriaLogs provides log records rather than
typed metric families, so it cannot substitute for missing Prometheus metric
history. The authoritative raw query results and all discovered metric names
are preserved in the verification JSON linked above.
