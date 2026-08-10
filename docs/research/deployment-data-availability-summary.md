# Deployment and metrics data availability

Generated 2026-08-10 from the consolidated Kubernetes, VictoriaLogs, and Prometheus exports. JSON is the canonical interchange format for this dataset; the detailed source exports remain available in the repository for analyses that need the hourly samples or original query responses.

## Windows and outputs

The deployment and log-analysis source was collected for `2026-07-07T00:00:00Z` through `2026-08-06T23:59:59Z` and is a 30-day declared window. The live resource-metrics request was collected separately for `2026-07-11T14:07:53Z` through `2026-08-10T14:07:53Z`. These windows are documented separately rather than being silently combined.

Final files:

- [pbx-web-deployments-30d.json](pbx-web-deployments-30d.json)
- [whisper-stt-deployments-30d.json](whisper-stt-deployments-30d.json)
- [pbx-web-metrics-30d.json](pbx-web-metrics-30d.json)
- [whisper-stt-metrics-30d.json](whisper-stt-metrics-30d.json)

## Availability by service

| Service | Deployment events | Error/request data | Latency data | CPU/memory/disk/network | Storage |
| --- | --- | --- | --- | --- | --- |
| `pbx-web` | 5 events in the deployment source: 4 successful rollouts and 1 rollback | 1,006,771 log lines; 340,521 HTTP requests; 312 4xx and 1 5xx | 175 application-processing samples on 13 calendar days; health probes retained for 10.08 days | 10 metric groups returned hourly samples for 10.08 days of the requested 30 | No storage series returned |
| `whisper-stt` | 4 successful rollout events; 1 falls inside the current resource-metric window | 109,949 HTTP requests, all 2xx; 0 error log lines | No application transcription-timing samples; health probes retained for 10.08 days | 15 metric groups returned hourly samples for 10.08 days of the requested 30 | 5 storage groups returned samples; filesystem limit and usage were unavailable |

Deployment records include supporting workloads (`pbx-rebuild-relay`, `lab-rebuild-relay`) under the `pbx-web` namespace. The July 28 `pbx-web` record reuses revision 14 and its ReplicaSet, so it should be treated as a rollout/restart event rather than a new image revision.

## Coverage gaps in the 30-day window

- Prometheus retention is 10 days. Resource data begins at approximately `2026-07-31T12:07:53Z`, leaving a leading gap of `19.916667` days in the requested window for both services. Missing samples are not represented as zeroes.
- VictoriaLogs begins at approximately `2026-07-13T00:00Z`, leaving a leading log gap after the resource window starts. Its error counts are aggregate queries, not complete daily time series.
- The deployment/log source ends on August 6, while the resource request ends on August 10. The common source intersection is therefore shorter than 30 days; no deployment events are available for the August 7–10 tail.
- `whisper-stt` has no structured application timing fields (`request_time`, `duration`, `latency`, `elapsed`, or equivalent), so transcription latency cannot be calculated.
- Storage metric availability differs by service: all seven requested storage series are unavailable for `pbx-web`; two filesystem series are unavailable for `whisper-stt`.
- No workflow execution records were found for the service build pipelines in the source window, so commit-to-deploy lead time is unavailable.

## Data quality notes

- All four final JSON files parse as valid JSON and use UTC timestamps. Each metrics file records its requested window, observed window, source artifact paths, counts, rates, and coverage status.
- The deployment event list uses the combined aligned source (`data/metrics_deployment_aligned.json`) so the two service files have consistent event identity and outcome fields. The older service-specific exports contain conflicting counts and should not override the consolidated lists.
- A zero-valued metric and an unavailable metric are kept distinct. In particular, constant-zero disk-read series may represent true idleness or exporter/query limitations and should be investigated before being interpreted as capacity headroom.
- `pbx-web` has one observed HTTP 5xx and a small 4xx count. `whisper-stt` has no observed HTTP or log errors, but its retained Prometheus data includes one non-zero hourly restart signal and non-zero not-ready-pod observations; these signals are not extrapolated to the missing first 19.9 days.
- Deployment-to-metric joins are contextual only. No metric values were interpolated at deployment timestamps, and deployment events do not overlap the retained Prometheus observations.

Detailed hourly resource samples, query metadata, coverage records, anomalies, and the combined availability report are in [data/pbx-web-whisper-stt-metrics-30d-20260810.json](../../data/pbx-web-whisper-stt-metrics-30d-20260810.json), [data/unified_metrics_30d.json](../../data/unified_metrics_30d.json), and [data/unified_metrics_availability_report.json](../../data/unified_metrics_availability_report.json).

## Integrity checks

The final validation checks confirm that all four JSON datasets parse successfully, both deployment datasets have non-empty event lists, event counts match the declared summaries, timestamps are ordered within each event list, and all declared metric counts and coverage values are non-negative. The documented gaps mean the data is suitable for analysis with caveats, not a complete 30-calendar-day time series.
