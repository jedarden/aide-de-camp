# Metric Types, Naming Conventions, and 30-Day Availability

**Verification date:** 2026-08-10
**Cluster:** `ardenone-cluster`
**Source:** Prometheus at `kube-prometheus-stack-arde-prometheus` in the
`monitoring` namespace

## Scope

The `pbx-web` and `whisper-stt` workloads do not expose application-owned
Prometheus `/metrics` endpoints. The metrics currently available under their
Kubernetes namespaces are infrastructure metrics collected from kubelet and
kube-state-metrics. Consequently, the service name is normally a label value,
not a prefix in the metric name.

The service selectors used in this document are:

```promql
{namespace="pbx-web"}
{namespace="whisper-stt"}
```

## Metric types

| Type | Meaning | Naming/shape convention | Observed in the service namespaces |
| --- | --- | --- | --- |
| Counter | A value that increases over time and resets when its process restarts. Use `rate()` or `increase()` for a time-based value. | Usually ends in `_total`; duration counters use a unit suffix before `_total`, such as `_seconds_total`. | Yes. Examples: `container_cpu_usage_seconds_total`, `container_network_receive_bytes_total`, and `kube_pod_container_status_restarts_total`. |
| Gauge | A value that can rise or fall and represents the current state or level. | Usually ends with a unit suffix such as `_bytes` or `_seconds`, or has no suffix for a state/info value. | Yes. Examples: `container_memory_working_set_bytes`, `kube_pod_info`, and `kube_pod_container_status_ready`. |
| Histogram | A distribution sampled into configured buckets. Use `histogram_quantile()` over the bucket series for a quantile. | One logical metric produces `<name>_bucket`, `<name>_count`, and `<name>_sum`. | Yes. Both namespaces expose `prober_probe_duration_seconds_bucket`, `prober_probe_duration_seconds_count`, and `prober_probe_duration_seconds_sum`. |
| Summary | A client-side distribution summary, commonly exposing quantiles plus `<name>_count` and `<name>_sum`. Summaries should not be aggregated across instances the same way histograms can be. | The base name is accompanied by quantile-labelled samples, plus `_count` and `_sum`. | No Summary family was returned by either service namespace selector during this verification. Summary metrics do exist elsewhere in the Prometheus installation, so Summary remains a supported platform type rather than an available service metric. |

The Prometheus metadata API reports the standard type names as lowercase
`counter`, `gauge`, `histogram`, and `summary`. Recording rules and histogram
component series may not have a separate metadata entry; their names still
follow the conventions above.

## Naming convention reference

### Common rules

- Use lowercase snake case for metric family names and label keys.
- Put the unit in the metric name: `_seconds`, `_bytes`, or another base unit.
- Use `_total` for cumulative counters.
- Use `_bucket`, `_count`, and `_sum` for histogram components.
- Kubernetes exporter families use the `kube_` prefix; container resource and
  runtime families use the `container_` prefix.
- Recording rules may use colons to separate the source expression and the
  aggregation, for example
  `namespace_cpu:kube_pod_container_resource_requests:sum`.
- Do not invent `pbx_web_` or `whisper_stt_` prefixes for the currently
  available data. Identify a service with its namespace and, when needed, its
  pod or container labels.

### Service selectors and labels

| Service | Required namespace selector | Typical pod label | Current workload containers |
| --- | --- | --- | --- |
| `pbx-web` | `namespace="pbx-web"` | `pod=~"pbx-web-.*"` (relay pods use their own deployment prefix) | `site-generator`, `nginx`, and relay containers |
| `whisper-stt` | `namespace="whisper-stt"` | `pod=~"whisper-(stt|openai)-.*"` | `whisper-stt`, `whisper-openai` |

Examples:

```promql
container_cpu_usage_seconds_total{namespace="pbx-web"}
kube_pod_container_status_restarts_total{namespace="whisper-stt"}
container_memory_working_set_bytes{namespace=~"pbx-web|whisper-stt"}
```

The `job` label identifies the collector, not the workload. The live query
returned `kubelet` and `kube-state-metrics` for these namespace selectors;
there was no separate application scrape job for either service.

## 30-day availability verification

The Prometheus clock at query time was **2026-08-10 10:20:23 UTC**. The
requested rolling window was therefore:

```text
2026-07-11 10:20:23 UTC through 2026-08-10 10:20:23 UTC
```

Prometheus reports `storage.tsdb.retention.time=10d`. I queried each namespace
with `query_range` at a one-hour step using `count({namespace="..."})`, which
tests whether any series for that service has a sample at each evaluation
time.

| Service | Requested period | First returned point | Last returned point | Hourly points / expected | Gaps within returned range | Full 30 days? |
| --- | --- | --- | --- | ---: | ---: | --- |
| `pbx-web` | 30 days | 2026-07-30 18:20:23 UTC | 2026-08-10 10:20:23 UTC | 257 / 257 | 0 | **No** |
| `whisper-stt` | 30 days | 2026-07-30 18:20:23 UTC | 2026-08-10 10:20:23 UTC | 257 / 257 | 0 | **No** |

The same first/last timestamps and continuous hourly result were observed for
representative `kube_pod_info`,
`container_cpu_usage_seconds_total`, and
`kube_pod_container_status_restarts_total` queries in both namespaces.

### Findings

- Neither service has Prometheus data for the beginning of the requested
  30-day period. The gap is approximately **2026-07-11 10:20 UTC through
  2026-07-30 18:20 UTC** (about 19 days 8 hours).
- There are **no one-hour gaps inside the retained interval** for either
  service at the verification resolution.
- This is a retention gap, not evidence that either service stopped running.
  Prometheus retains only 10 days, and the first returned sample can be older
  than exactly 10 days while the oldest retained TSDB block is being expired.
- The existing monitoring endpoint inventory also identifies VictoriaLogs as
  a separate log store with 28-day retention. That is shorter than 30 days and
  does not provide typed Prometheus metric families, so it cannot establish
  full 30-day metric availability for these services.

## Reproducible query pattern

Use the Prometheus API through the monitoring port-forward and set `start` and
`end` from the Prometheus `time()` result to avoid clock skew:

```promql
count({namespace="pbx-web"})
count({namespace="whisper-stt"})
```

Run each expression with `query_range`, `step=1h`, and a 30-day start/end
window. A complete retained interval has one result at every hourly evaluation
time. This check must still be repeated after any retention-policy change;
continuity in the current ten-day window does not retroactively restore the
missing historical samples.
