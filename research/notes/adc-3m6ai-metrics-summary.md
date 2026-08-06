# Deployment Frequency and Timing Metrics Summary

**Analysis Date:** 2026-08-06  
**Bead:** adc-3m6ai  
**Task:** Compute deployment frequency and timing metrics

## Metrics Calculated

### whisper-stt
- **Total deployments:** 10
- **Time range:** 17.11 days (2026-06-25 to 2026-07-12)
- **Deployment frequency:** 0.5843 deploys/day (4.09/week, 17.53/month)
- **Mean time between deployments:** 45.64 hours (1.9 days)

### pbx-web
- **Total deployments:** 11  
- **Time range:** 81.93 days (2026-05-07 to 2026-07-28)
- **Deployment frequency:** 0.1343 deploys/day (0.94/week, 4.03/month)
- **Mean time between deployments:** 196.64 hours (8.19 days)

## Key Findings

1. **whisper-stt has significantly higher deployment frequency** than pbx-web (4.35x more frequent)
2. **whisper-stt deployments are clustered** in a much shorter time window (17 days vs 82 days)
3. **pbx-web has a more steady cadence** with ~8 days between deployments on average
4. **whisper-stt shows rapid iteration** with ~2 days between deployments on average

## Data Sources

- whisper-stt: `research/whisper-stt-30days/deployments-30days.json`
- pbx-web: `research/deployment-comparison-30days/k8s-data/pbx-web-replicasets-summary.json`

## Files Generated

- `research/adc-3m6ai-metrics.py` - Python calculation script
- `research/adc-3m6ai-metrics.json` - Structured metrics output
- `research/notes/adc-3m6ai-metrics-summary.md` - This summary

## Acceptance Criteria Status

✅ All acceptance criteria met:
1. pbx-web deployment frequency calculated
2. whisper-stt deployment frequency calculated  
3. pbx-web mean time between deployments computed
4. whisper-stt mean time between deployments computed
5. Time range identified for both services
6. Metrics stored for final output