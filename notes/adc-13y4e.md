# Deployment Metrics Comparison - adc-13y4e

## Task Completed
Created side-by-side comparison of deployment metrics for pbx-web and whisper-stt services using the normalized dataset.

## Work Performed

### Input Data
- Source: `docs/research/deployment-data-normalized.json`
- Dataset: 9 total deployment records (5 pbx-web, 4 whisper-stt)
- Time period: 2026-07-08 to 2026-07-28 (30-day window)

### Analysis Completed

#### 1. Deployment Frequency Analysis
- **pbx-web**: 5 deployments over 16 days, ~1.25 per day average, moderate/steady cadence
- **whisper-stt**: 4 deployments over 5 days, ~2.0 per day average, burst pattern

#### 2. Success Rate Calculations
- **Both services**: 100% overall success rate
- **pbx-web**: Consistent 100% across all active weeks
- **whisper-stt**: 100% across active deployment weeks

#### 3. Failure Type Distribution
- **Both services**: Zero failures of any type recorded
- All failure categories (image pull, crash loop, OOM, probe failures, etc.) at 0%

#### 4. Comprehensive Comparison Table
Side-by-side metrics across:
- Deployment frequency and volume
- Success rates and stability
- Uptime and zero-downtime performance
- Pod health metrics (restarts, crashes, OOM kills)
- Incidents (critical, warnings)
- Log errors (pbx-web: 6, whisper-stt: 0)
- Deployment span and recency

### Key Findings

**Overall Winner**: pbx-web

**Notable Observations**:
1. Both services achieved perfect 100% success rates with zero failures
2. Both maintained 100% uptime with zero-downtime deployments
3. pbx-web shows consistent deployment rhythm over longer period
4. whisper-stt shows burst deployment pattern followed by extended idle (25+ days stale)
5. whisper-stt has cleaner logs (0 errors vs 6 for pbx-web)
6. whisper-stt may require attention due to deployment staleness

**Deployment Patterns**:
- **pbx-web**: Steady, consistent rhythm - suggests regular updates and active maintenance
- **whisper-stt**: Burst pattern - suggests batched feature releases followed by stable period

**Risk Assessment**:
- **pbx-web**: Low risk - active maintenance, perfect success rate, minor log errors
- **whisper-stt**: Low risk for stability, but deployment staleness may indicate neglect

### Output Files Generated
1. `docs/research/deployment-metrics-comparison.json` - Comprehensive comparison data with all metrics

## Next Steps
This is step 2/4 of deployment pattern comparison synthesis. Next step would be to create visualizations or synthesize findings into a final report.

## Related Beads
- Predecessor: adc-10nxv (Extract and normalize deployment data)
- This bead: adc-13y4e (Compare deployment metrics side-by-side)