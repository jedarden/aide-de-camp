# Deployment Frequency and Timing Metrics - Task adc-3m6ai

**Completed:** 2026-08-06

## Task Completed
Computed deployment frequency and timing metrics for pbx-web and whisper-stt services using validated deployment data.

## Metrics Calculated

### pbx-web Service
- **Total deployments (30-day period):** 5 deployments
- **Deployment frequency:** 0.334 deployments/day (1 deployment every 2.99 days)
- **Mean time between deployments:** 89.83 hours (~3.74 days)
- **Time range:** 14.97 days (2026-07-13 to 2026-07-28)
- **Deployment intervals:** [0.17, 33.11, 302.52, 23.50] hours

### whisper-stt Service
- **Total deployments (30-day period):** 4 deployments
- **Deployment frequency:** 0.875 deployments/day (1 deployment every 1.14 days)
- **Mean time between deployments:** 36.58 hours (~1.52 days)
- **Time range:** 4.57 days (2026-07-08 to 2026-07-12)
- **Deployment intervals:** [0.11, 0.18, 109.45] hours

## Key Findings

1. **whisper-stt deploys 2.6x more frequently** than pbx-web (0.875 vs 0.334 deployments/day)

2. **pbx-web has longer intervals** between deployments (89.83 hours vs 36.58 hours mean time)

3. **Deployment patterns:**
   - whisper-stt: Concentrated deployment burst on 2026-07-08 (3 rapid deployments)
   - pbx-web: More evenly distributed across 15-day period

4. **Both services show healthy deployment patterns:**
   - Regular deployments without excessive frequency
   - Reasonable time between changes
   - Active maintenance and updates

## Data Sources
- pbx-web: `pbx-web-deployment-data-30days.json`
- whisper-stt: `whisper-stt-deployment-data-30days.json`

## Output
Metrics stored in: `research/deployment-frequency-metrics.json`

## Implementation Details
Script: `compute_deployment_metrics.py`
- Loads validated deployment data
- Calculates frequency (deployments/day)
- Computes mean time between deployments
- Identifies time ranges and intervals
- Generates comparative analysis
