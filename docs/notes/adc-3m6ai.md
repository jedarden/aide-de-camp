# Deployment Frequency and Timing Metrics Calculation

## Task: adc-3m6ai
**Compute deployment frequency and timing metrics**

## Summary
Calculated deployment frequency and timing metrics for pbx-web and whisper-stt services using validated deployment data from child bead adc-3m6ah.

## Metrics Calculated

### pbx-web
- **Total Deployments**: 10
- **Time Range**: 2026-06-15 to 2026-07-28 (42.97 days)
- **Deployment Frequency**: 0.2327 deployments per day (1 deployment every 4.3 days)
- **Mean Time Between Deployments**: 4.77 days
- **Interval Range**: 612 seconds (10.2 minutes) to 1,565,047 seconds (18.1 days)

### whisper-stt
- **Total Deployments**: 11
- **Time Range**: 2026-06-24 to 2026-07-12 (17.83 days)
- **Deployment Frequency**: 0.6169 deployments per day (1 deployment every 1.62 days)
- **Mean Time Between Deployments**: 1.78 days
- **Interval Range**: 129 seconds (2.15 minutes) to 521,342 seconds (6.03 days)

## Key Findings

### Deployment Frequency Comparison
- **whisper-stt deploys 2.65x more frequently** than pbx-web (0.6169 vs 0.2327 deploys/day)
- pbx-web: ~1 deployment every 4.3 days
- whisper-stt: ~1 deployment every 1.6 days

### Deployment Pattern Insights
- **pbx-web** shows more stable, infrequent deployments with larger intervals
- **whisper-stt** shows rapid iteration with much shorter intervals between deployments
- whisper-stt's minimum interval of 2.15 minutes indicates rapid-fire deployments/rollbacks
- pbx-web's maximum interval of 18.1 days shows longer stable periods

## Files Created
1. `docs/research/deployment-data/calculate_frequency_metrics.py` - Python script for metric calculation
2. `docs/research/deployment-data/frequency-metrics.json` - Structured metrics output

## Acceptance Criteria
- ✅ pbx-web deployment frequency calculated: 0.2327 deploys/day
- ✅ whisper-stt deployment frequency calculated: 0.6169 deploys/day
- ✅ pbx-web mean time between deployments computed: 4.77 days
- ✅ whisper-stt mean time between deployments computed: 1.78 days
- ✅ Time ranges identified for both services
- ✅ Metrics stored in structured JSON format

## Implementation Notes
- Used validated deployment data from child bead adc-3m6ah
- pbx-web data: 10 deployments from `pbx-web-deployments.json`
- whisper-stt data: 11 deployments from `whisper-stt-deployment-data.json` (deployment_history array)
- Frequency formula: total_deployments / date_range_days
- Mean time between: (last_timestamp - first_timestamp) / (deployments - 1)
- Timestamps parsed from ISO 8601 format with UTC timezone handling
- Results include interval ranges showing min/max deployment gaps

## Next Steps
Metrics are now available for final synthesis and reporting in parent bead.
