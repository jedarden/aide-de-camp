# Temporal Gap Analysis Report
**Generated:** 2026-08-07T04:18:54.762140
**Analysis Type:** Coverage and temporal gap detection

## Executive Summary

### pbx-web Dataset (using CSV deployment events)
- **Time Span:** 15.0 days
- **Total Records:** 5
- **Daily Coverage:** 26.7%
- **Data Quality:** DEGRADED
- **Gap Days:** 12

### whisper-stt Dataset (using CSV deployment events)
- **Time Span:** 28.5 days
- **Total Records:** 5
- **Daily Coverage:** 10.3%
- **Data Quality:** DEGRADED
- **Gap Days:** 26

## Data Sources Analyzed

### pbx-web Data Sources
- CSV deployment events: 5 records
- Metadata file: 0 records (metadata only)
- Parsed logs: 0 records
- Victoria logs: 0 records
- **Total combined:** 5 records

### whisper-stt Data Sources
- CSV deployment events: 5 records
- Main logs: 98252 records
- Victoria logs: 0 records
- **Total combined:** 98,257 records
## pbx-web Detailed Analysis

### Temporal Coverage
- **First Record:** 2026-07-13T18:07:55+00:00
- **Last Record:** 2026-07-28T17:26:12+00:00
- **Expected Days:** 15
- **Days with Data:** 4
- **Average Records/Day:** 1.25

### Detected Gaps (2)

| Start | End | Duration (days) | Severity |
|-------|-----|----------------|----------|
| 2026-07-14 | 2026-07-15 | 1 | MINOR |
| 2026-07-16 | 2026-07-27 | 11 | CRITICAL |
## whisper-stt Detailed Analysis

### Temporal Coverage
- **First Record:** 2026-06-14T04:11:57+00:00
- **Last Record:** 2026-07-12T16:53:42+00:00
- **Expected Days:** 29
- **Days with Data:** 3
- **Average Records/Day:** 1.67

### Detected Gaps (2)

| Start | End | Duration (days) | Severity |
|-------|-----|----------------|----------|
| 2026-06-15 | 2026-07-08 | 23 | CRITICAL |
| 2026-07-09 | 2026-07-12 | 3 | MAJOR |

## Severity Assessment

- **Total Gaps Detected:** 4
- **Critical Gaps (≥24hrs):** 2
- **Major Gaps (≥6hrs):** 1

## Anomalies Detected

### ⚠️ WARNING: pbx-web file size is suspiciously small (0.001 MB)
- Expected size for 30-day latency data should be significantly larger
- Indicates incomplete data collection or extraction issue

### ⚠️ WARNING: whisper-stt has unusually low record density (0.0 records/hour)
- May indicate log filtering, sampling, or collection issues
- Expected hourly count for health checks alone should be higher

## Recommendations

1. **URGENT:** Investigate critical gaps - check system availability, log collection failures
2. **HIGH:** Review major gaps for patterns (specific times, scheduled maintenance, etc.)
4. **Implement:** Continuous monitoring with gap detection alerts
5. **Archive:** Store raw data with redundant backups to prevent data loss
6. **Standardize:** Implement unified data collection across both services
