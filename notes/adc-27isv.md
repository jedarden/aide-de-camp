# Deployment Frequency Metrics Analysis

**Task ID:** adc-27isv  
**Generated:** 2026-08-06  
**Services:** pbx-web vs whisper-stt  
**Cluster:** ardenone-cluster  
**Time Period:** 30 days (July 2026)

## Executive Summary

| Metric | pbx-web | whisper-stt | Comparison |
|--------|---------|-------------|------------|
| **Total Deployments** | 5 | 4 | pbx-web: +25% more |
| **Deployments Per Day** | 0.1667 | 0.1333 | pbx-web: 1.25x more frequent |
| **Mean Time Between Deployments (MTBD)** | 89.83 hours | 36.58 hours | whisper-stt: 2.45x faster |
| **Time Range Covered** | 14.97 days | 4.57 days | pbx-web: 3.3x longer span |

## Key Findings

### Deployment Frequency
- **pbx-web**: 0.1667 deployments per day (~1 deployment every 6 days)
- **whisper-stt**: 0.1333 deployments per day (~1 deployment every 7.5 days)
- **pbx-web is 25% more frequently deployed** than whisper-stt

### Deployment Velocity
- **pbx-web**: Average 89.83 hours (3.75 days) between consecutive deployments
- **whisper-stt**: Average 36.58 hours (1.5 days) between consecutive deployments
- **whisper-stt deploys 2.45x faster** once deployment activity starts

### Deployment Patterns
- **pbx-web**: More sporadic deployment pattern with longer gaps (up to 12.6 days between deployments)
- **whisper-stt**: More concentrated deployment activity (4 deployments within 4.57 days)

## Detailed Metrics by Service

### pbx-web Deployment Metrics
- **Total Deployments**: 5
- **Deployment Frequency**: 0.1667 per day
- **Mean Time Between Deployments**: 89.83 hours
- **Time Range**: 14.97 days (July 13-28, 2026)
- **First Deployment**: 2026-07-13T18:07:55+00:00
- **Last Deployment**: 2026-07-28T17:26:12+00:00
- **Deployment Success Rate**: 80% (4/5 successful, 1 rollback)

### pbx-web Deployment Intervals
| Interval | Hours | Days |
|----------|-------|------|
| Min | 0.17 | <0.01 |
| Max | 302.52 | 12.6 |
| Median | 28.31 | 1.18 |
| Mean | 89.83 | 3.74 |

### whisper-stt Deployment Metrics
- **Total Deployments**: 4
- **Deployment Frequency**: 0.1333 per day  
- **Mean Time Between Deployments**: 36.58 hours
- **Time Range**: 4.57 days (July 8-12, 2026)
- **First Deployment**: 2026-07-08T03:09:35+00:00
- **Last Deployment**: 2026-07-12T16:53:42+00:00
- **Current Version**: ronaldraygun/whisper-stt:1.8.6

### whisper-stt Deployment Intervals
| Interval | Hours | Days |
|----------|-------|------|
| Min | 0.11 | <0.01 |
| Max | 109.45 | 4.56 |
| Median | 0.18 | 0.01 |
| Mean | 36.58 | 1.52 |

## Operational Insights

### pbx-web Characteristics
- **Longer deployment tail**: Deployments spread over ~15 days
- **One significant gap**: 12.6-day gap between July 15-27 suggests intentional deployment pause
- **High success rate**: 80% of deployments completed successfully
- **One rollback**: First deployment was rolled back, followed by rapid re-deployment

### whisper-stt Characteristics  
- **Concentrated deployment activity**: 4 deployments within 4.57 days
- **Rapid iteration**: Multiple quick fixes (0.11 and 0.18 hour gaps)
- **Version progression**: 1.8.2 → 1.8.4 → 1.8.6 (bug fix releases)
- **Recent inactivity**: No deployments since July 12, 2026

## Comparative Analysis

### Deployment Frequency Comparison
- **pbx-web deploys 25% more frequently** (0.1667 vs 0.1333 per day)
- **whisper-stt has faster iteration** once deployment activity begins (36.58 vs 89.83 hours MTBD)

### Deployment Strategy Differences
- **pbx-web**: More steady, consistent deployment pattern over longer time span
- **whisper-stt**: Burst-oriented deployment pattern with concentrated fix cycles

### Risk Assessment
- **pbx-web**: Longer time between deployments may indicate more testing/stable releases
- **whisper-stt**: Rapid deployment cycles suggest active bug fixing but also higher deployment frequency during active periods

## Conclusions

1. **pbx-web has higher overall deployment frequency** (0.1667 vs 0.1333 per day)
2. **whisper-stt has faster deployment cycles** when active (36.58 vs 89.83 hours MTBD)
3. **Both services show distinct deployment patterns**: pbx-web is more consistent, whisper-stt is more burst-oriented
4. **Deployment activity appears seasonal**: Both services had clusters of activity followed by quiet periods

## Acceptance Criteria Status

✅ **pbx-web deployment frequency**: 0.1667 deployments per day  
✅ **whisper-stt deployment frequency**: 0.1333 deployments per day  
✅ **pbx-web mean time between deployments**: 89.83 hours  
✅ **whisper-stt mean time between deployments**: 36.58 hours  
✅ **Additional statistics**: min/max/median intervals calculated for both services

## Data Source
- Analysis based on validated deployment data from:
  - `/home/coding/aide-de-camp/pbx-web-deployment-data-30days.json`
  - `/home/coding/aide-de-camp/whisper-stt-deployment-data-30days.json`
- Full metrics available in: `/home/coding/aide-de-camp/research/deployment-frequency-metrics.json`
