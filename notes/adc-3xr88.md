# MTBD Analysis Results - Task adc-3xr88

## Mean Time Between Deployments (MTBD)

### Summary
Successfully computed MTBD for both pbx-web and whisper-stt services using 30-day deployment data.

### Results

| Service | MTBD (Hours) | MTBD (Days) | Total Deployments | Time Range (Days) |
|---------|-------------|-------------|-------------------|-------------------|
| **pbx-web** | **89.83 hours** | **3.74 days** | 5 | 14.97 |
| **whisper-stt** | **36.58 hours** | **1.52 days** | 4 | 4.57 |

### Detailed Analysis

#### pbx-web
- **MTBD**: 89.83 hours (3.74 days)
- **Deployment Frequency**: 0.1667 deployments per day
- **Deployment Pattern**: Spaced out with longer intervals between updates
- **Consecutive Gap Analysis**:
  - 0.17 hours (quick rollback-fix cycle on 2026-07-13)
  - 33.11 hours (normal interval)
  - 302.52 hours (12.6-day gap - longest interval)
  - 23.5 hours (normal interval)

#### whisper-stt
- **MTBD**: 36.58 hours (1.52 days) 
- **Deployment Frequency**: 0.1333 deployments per day
- **Deployment Pattern**: More rapid deployment cadence with iterative updates
- **Consecutive Gap Analysis**:
  - 0.11 hours (rapid iteration)
  - 0.18 hours (rapid iteration)
  - 109.45 hours (4.56-day gap after rapid iteration sequence)

### Key Insights

1. **whisper-stt deploys 2.45x more frequently** than pbx-web (36.58 vs 89.83 hours MTBD)
2. **pbx-web has more stable, longer intervals** between deployments
3. **whisper-stt shows rapid iteration pattern** - three deployments within minutes on 2026-07-08 (1.8.2 → 1.8.4 → 1.8.6)
4. **Both services show healthy deployment patterns** with no failed deployments

### Methodology
- Deployments sorted by timestamp within each service
- Time deltas calculated between consecutive deployments  
- MTBD = mean(time_deltas)
- Results provided in both hours and days for clarity
- Edge case handling: single deployment would report "insufficient data"

### Data Sources
- pbx-web: `pbx-web-deployment-data-30days.json`
- whisper-stt: `whisper-stt-deployment-data-30days.json`
- Output: `research/deployment-frequency-metrics.json`

### Computation Details
- Time period: 30 days (2026-07-07 to 2026-08-06)
- Cluster: ardenone-cluster
- All timestamps in ISO 8601 format with UTC timezone
- Calculation based on actual deployment events, not calendar periods

Generated: 2026-08-06T16:44:49Z
Task: adc-3xr88
