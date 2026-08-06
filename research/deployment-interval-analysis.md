# Deployment Interval Statistics Analysis

## Task: adc-1efr9
Compute additional deployment interval statistics and compare pbx-web and whisper-stt services.

## Overview

This analysis extends the Mean Time Between Deployments (MTBD) calculation to provide comprehensive interval statistics and side-by-side service comparison over a 30-day period.

## Key Findings

### Deployment Frequency
- **pbx-web**: 5 deployments (mean interval: 89.83 hours ≈ 3.7 days)
- **whisper-stt**: 4 deployments (mean interval: 36.58 hours ≈ 1.5 days)

**Insight**: whisper-stt deploys **2.5x more frequently** than pbx-web on average.

### Interval Statistics Comparison

| Metric | pbx-web | whisper-stt |
|--------|---------|-------------|
| **Min Interval** | 0.17 hours (10 min) | 0.11 hours (6 min) |
| **Max Interval** | 302.52 hours (12.6 days) | 109.45 hours (4.6 days) |
| **Median Interval** | 28.31 hours (1.2 days) | 0.18 hours (11 min) |
| **Mean Interval** | 89.83 hours (3.7 days) | 36.58 hours (1.5 days) |
| **Std Dev** | 142.47 hours | 63.11 hours |
| **Coefficient of Variation** | 1.59 | 1.73 |

### Consistency Analysis

**Most Consistent**: pbx-web (lower coefficient of variation)

The coefficient of variation (CV) measures relative variability:
- **pbx-web CV**: 1.59
- **whisper-stt CV**: 1.73

Despite having fewer deployments, pbx-web shows **more consistent** deployment timing when accounting for its longer mean interval.

### Variance Patterns

- **pbx-web**: Higher absolute variance (σ = 142.47h) but lower relative variance (CV = 1.59)
- **whisper-stt**: Lower absolute variance (σ = 63.11h) but higher relative variance (CV = 1.73)

This indicates that while whisper-stt has tighter absolute intervals, those intervals vary more relative to its mean deployment frequency.

### Range Analysis

- **pbx-web range**: 302.35 hours (12.6 days) between shortest and longest intervals
- **whisper-stt range**: 109.34 hours (4.6 days) between shortest and longest intervals

pbx-web shows much wider spread in deployment timing, suggesting more sporadic deployment patterns with occasional long gaps.

## Deployment Pattern Insights

### pbx-web Characteristics
- **Burst deployment pattern**: Shows clusters of rapid deployments (0.17h intervals) followed by long gaps (302.52h)
- **Sporadic cadence**: High standard deviation relative to mean indicates irregular scheduling
- **Possible triggers**: Deployments may be driven by specific issues or features rather than scheduled cadence

### whisper-stt Characteristics  
- **More active development**: Higher deployment frequency suggests more frequent updates
- **Tighter clustering**: Most deployments happen in quick succession (< 1 hour intervals)
- **One significant gap**: 109.45 hour gap dominates the interval distribution, skewing the mean

### Recommendations

1. **For pbx-web**:
   - Consider implementing regular deployment schedules to reduce variance
   - Investigate the cause of the 302-hour gap between deployments
   - The 10-minute rapid deployments suggest potential rollout issues that may benefit from batching

2. **For whisper-stt**:
   - The clustering pattern suggests batched feature releases
   - Consider spreading deployments more evenly to reduce deployment risk
   - Monitor the 109-hour gap pattern to understand if this represents a planned pause

## Technical Implementation

### Data Sources
- `pbx-web-deployment-data-30days.json` (5 deployment events)
- `whisper-stt-deployment-data-30days.json` (4 deployment events)

### Statistical Methods Used
1. **Interval Calculation**: Time differences between consecutive deployments
2. **Central Tendency**: Mean and median intervals
3. **Dispersion**: Standard deviation, interquartile range (IQR), coefficient of variation
4. **Comparative Analysis**: Side-by-side metrics and consistency ranking

### Files Generated
- `research/deployment-interval-statistics.json` - Complete statistical data
- `research/deployment-interval-comparison.txt` - Human-readable comparison table
- `calculate_deployment_interval_statistics.py` - Analysis script

## Conclusion

This analysis reveals distinct deployment patterns between the two services:

- **whisper-stt** is more actively developed with 2.5x higher deployment frequency
- **pbx-web** has more consistent timing relative to its mean, despite longer intervals
- Both services show high variance (CV > 1.5), suggesting irregular deployment cadence

The findings suggest opportunities to improve deployment predictability for both services through better scheduling and batch management.

---

*Generated: 2026-08-06*  
*Task: adc-1efr9*  
*Period: 30 days (2026-07-08 to 2026-07-28)*