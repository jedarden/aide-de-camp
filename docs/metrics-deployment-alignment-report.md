# Metrics/deployment temporal alignment report

Generated: `2026-08-10T13:48:40.031Z`<br>
Status: **validated_with_temporal_gaps**<br>
Category presence: **8/8** service/category checks<br>
Requested-window completeness: **0/8** categories<br>

## Scope and sources

The combined deployment event dataset is treated as canonical. CPU/memory and disk/network/storage are read from their separate Prometheus range exports. The aligned JSON is an index into those raw files; it does not replace their numeric samples.

| Source | Requested range | Step |
| --- | --- | ---: |
| CPU/memory | `2026-07-11T11:14:01.927Z` – `2026-08-10T11:14:01.927Z` | 3600 s |
| Disk/network | `2026-07-11T11:44:38.362Z` – `2026-08-10T11:44:38.362Z` | 3600 s |

## Coverage by service and category

| Service | Category | Present | Status | First sample | Last sample | Metrics present |
| --- | --- | :---: | --- | --- | --- | ---: |
| pbx-web | cpu | yes | partial | `2026-07-30T18:14:01.927Z` | `2026-08-10T11:14:01.927Z` | 1/1 |
| pbx-web | memory | yes | partial | `2026-07-30T18:14:01.927Z` | `2026-08-10T11:14:01.927Z` | 1/1 |
| pbx-web | disk | yes | partial | `2026-07-30T18:44:38.362Z` | `2026-08-10T11:44:38.362Z` | 4/4 |
| pbx-web | network | yes | partial | `2026-07-30T18:44:38.362Z` | `2026-08-10T11:44:38.362Z` | 4/4 |
| whisper-stt | cpu | yes | partial | `2026-07-30T18:14:01.927Z` | `2026-08-10T11:14:01.927Z` | 1/1 |
| whisper-stt | memory | yes | partial | `2026-07-30T18:14:01.927Z` | `2026-08-10T11:14:01.927Z` | 1/1 |
| whisper-stt | disk | yes | partial | `2026-07-30T18:44:38.362Z` | `2026-08-10T11:44:38.362Z` | 4/4 |
| whisper-stt | network | yes | partial | `2026-07-30T18:44:38.362Z` | `2026-08-10T11:44:38.362Z` | 4/4 |

Every requested category is present for both services (8/8 checks). None has complete 30-day coverage: the first observed sample is about 19.3 days after the requested start. Within the observed span, the returned hourly grids have no internal gaps.

## Deployment alignment

The canonical source contains 9 deployment events. There are 24 in-window event/category rows; 0 have a metric sample within half an hourly step. The remaining rows are indexed to the nearest sample but are outside the observed metric window, so they must not be interpreted as measurements at deployment time.

See `data/metrics_deployment_aligned.json` for one row per deployment event and category, including signed nearest-sample offsets.

## Gaps and anomalies

- **high — leading_metric_coverage_gap:** All four resource categories begin approximately 19.3 days after the requested 30-day window starts.
- **high — deployment_event_alignment_gap:** Deployment events in the metric request window have no metric sample within half the one-hour step because they precede the first observed sample.
- **medium — deployment_source_window_gap:** The combined deployment source ends before the metric request window ends.
- **medium — constant_zero_metric (pbx-web, disk):** All returned disk samples are zero; verify exporter/query coverage or confirm no disk I/O occurred.
- **medium — constant_zero_metric (pbx-web, disk):** All returned disk samples are zero; verify exporter/query coverage or confirm no disk I/O occurred.
- **medium — constant_zero_metric (pbx-web, disk):** All returned disk samples are zero; verify exporter/query coverage or confirm no disk I/O occurred.
- **medium — constant_zero_metric (pbx-web, disk):** All returned disk samples are zero; verify exporter/query coverage or confirm no disk I/O occurred.
- **info — high_rate_peak (pbx-web, network):** Maximum rate is at least 10x the median; inspect peak timestamps before interpreting as sustained behavior.
- **info — high_rate_peak (pbx-web, network):** Maximum rate is at least 10x the median; inspect peak timestamps before interpreting as sustained behavior.
- **info — mostly_zero_metric (whisper-stt, disk):** At least 95% of returned disk samples are zero; treat isolated activity as sparse.
- **info — mostly_zero_metric (whisper-stt, disk):** At least 95% of returned disk samples are zero; treat isolated activity as sparse.
- **info — mostly_zero_metric (whisper-stt, disk):** At least 95% of returned disk samples are zero; treat isolated activity as sparse.
- **info — mostly_zero_metric (whisper-stt, disk):** At least 95% of returned disk samples are zero; treat isolated activity as sparse.
- **info — high_rate_peak (whisper-stt, network):** Maximum rate is at least 10x the median; inspect peak timestamps before interpreting as sustained behavior.
- **info — high_rate_peak (whisper-stt, network):** Maximum rate is at least 10x the median; inspect peak timestamps before interpreting as sustained behavior.
- **high — leading_retention_or_no_data_gap (pbx-web, cpu):** The requested window starts before the first observed sample.
- **high — leading_retention_or_no_data_gap (pbx-web, memory):** The requested window starts before the first observed sample.
- **high — leading_retention_or_no_data_gap (pbx-web, disk):** The requested window starts before the first observed sample.
- **high — leading_retention_or_no_data_gap (pbx-web, network):** The requested window starts before the first observed sample.
- **high — leading_retention_or_no_data_gap (whisper-stt, cpu):** The requested window starts before the first observed sample.
- **high — leading_retention_or_no_data_gap (whisper-stt, memory):** The requested window starts before the first observed sample.
- **high — leading_retention_or_no_data_gap (whisper-stt, disk):** The requested window starts before the first observed sample.
- **high — leading_retention_or_no_data_gap (whisper-stt, network):** The requested window starts before the first observed sample.
- **medium — deployment_metric_window_mismatch:** Deployment history and metric collection use different time windows; the metric tail is not covered by the deployment source.
- **medium — cross_category_timestamp_grid_offset:** CPU/memory and disk/network exports do not share an exact timestamp grid.
- **medium — deployment_source_disagreement (whisper-stt):** A service-specific deployment export disagrees with the combined deployment event source; use the combined source for this report and investigate the narrower export.

Notable metric anomalies include all-zero PBX disk I/O, sparse mostly-zero Whisper disk I/O, large network-rate peaks relative to the median, and a 30m36.435s timestamp-grid offset between the CPU/memory and disk/network exports. These are documented as observations, not silently repaired.

## Validation result

| Check | Result |
| --- | --- |
| deployment_events_loaded | PASS |
| metric_sources_loaded | PASS |
| all_four_categories_present_for_both_services | PASS |
| metric_timestamps_parse | PASS |
| no_internal_gaps_in_observed_span | PASS |
| full_requested_window_coverage | GAP/FAIL |
| deployment_events_have_nearby_metric_samples | GAP/FAIL |

The dataset is structurally validated and ready for analysis with the documented coverage caveat. Missing periods are represented as gaps, never as zero-valued samples.
