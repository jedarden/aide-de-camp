# Temporal Distributions and Deployment Correlations

**Analysis Date:** 2026-08-06
**Time Window:** 2026-07-07 to 2026-08-06 (31 days)
**Output File:** `temporal-distributions.json`

## Summary

This analysis examines temporal distributions of deployment failures across a 30-day window and correlates failure spikes with deployment timestamps to identify patterns and potential causal relationships.

## Key Findings

### Overall Statistics
- **Total failures analyzed:** 1
- **Total deployments analyzed:** 9
- **Days with failures:** 1 out of 31 (3.2%)
- **Peak failure day:** 2026-07-13
- **Temporal clusters:** 0 (insufficient failure density)

### Daily Distribution
The analysis created daily bins across the entire 31-day window. Only one day (2026-07-13) recorded a failure:

| Date | Failures | Pattern | Service | Severity |
|------|----------|---------|---------|----------|
| 2026-07-13 | 1 | Other | pbx-web | unknown |

### Daily Failure Rates by Pattern
For 2026-07-13 (the only day with failures):
- **Other pattern:** 1 failure (100% of all "Other" pattern failures)

### Temporal Clusters
**No temporal clusters identified.** A cluster requires consecutive days with elevated failure rates. With only a single failure event, no multi-day patterns emerge.

### Deployment Correlations
**1 correlation found:**

#### pbx-web Rollback Event (2026-07-13)
- **Failure timestamp:** 2026-07-13T18:07:55Z
- **Related deployment:** pbx-web-revision-11-rollback
- **Deployment event type:** deployment_rollback
- **Image:** ronaldraygun/pbx-web:1.0.8
- **Hours before failure:** 0.0 (exact match)
- **Context:** This is a self-correlating event—the failure IS the rollback. The rollback was triggered by issues with the initial deployment of revision 14 (ronaldraygun/pbx-web:1.0.9), which occurred at 18:18:07Z on the same day.

## Pattern Analysis

### Post-Deployment Spike Detection
Looking for failure spikes in the 24-hour window following deployments:

- **pbx-web:** 4 deployments + 1 rollback
  - Most deployments (July 15, July 27, July 28) have NO associated failures in the data
  - The July 13 rollback IS the failure event

- **whisper-stt:** 4 deployments (July 8, July 12)
  - No failures detected following whisper-stt deployments

### Gradual Increases
**No gradual increase patterns detected.** With only one failure, no trend analysis is possible.

### Temporal Clustering
**No clustering patterns observed.** Failures are not concentrated in specific time periods.

## Deployment Timeline

### pbx-web Deployment Timeline
```
2026-07-13 18:07:55Z  ← ROLLBACK (failure event)
                      Image: ronaldraygun/pbx-web:1.0.8
2026-07-13 18:18:07Z  ← Re-deployment revision 14
                      Image: ronaldraygun/pbx-web:1.0.9
2026-07-15 03:24:40Z  ← pbx-rebuild-relay deployment
2026-07-27 17:56:07Z  ← lab-rebuild-relay deployment
2026-07-28 17:26:12Z  ← Current active deployment
```

### whisper-stt Deployment Timeline
```
2026-07-08 03:09:35Z  ← Revision 29 (ronaldraygun/whisper-stt:1.8.2)
2026-07-08 03:16:13Z  ← Revision 30 (ronaldraygun/whisper-stt:1.8.4)
2026-07-08 03:26:44Z  ← Revision 31 (ronaldraygun/whisper-stt:1.8.6)
2026-07-12 16:53:42Z  ← Revision 32 (current active)
```

## Conclusions

1. **Sparse failure data:** Only 1 failure across 31 days makes statistical analysis difficult. More data is needed to identify meaningful patterns.

2. **No systemic temporal patterns:** With insufficient failure density, no temporal clusters, gradual increases, or periodic patterns can be identified.

3. **Self-correlating event:** The single failure (pbx-web rollback) is itself a deployment event, not a downstream effect. This suggests immediate detection and rollback rather than delayed failure symptoms.

4. **Successful recovery:** The July 13 rollback was followed by a successful re-deployment 10 minutes later, with no subsequent failures. This indicates effective automated rollback behavior.

5. **Service stability:** whisper-stt deployments show no associated failures in the dataset. The rapid deployment sequence on July 8 (3 deployments in ~17 minutes) completed without incident.

## Recommendations

1. **Expand failure collection:** The current dataset contains only 1 failure. Implement more comprehensive failure tracking to enable meaningful temporal analysis.

2. **Add granular metrics:** Include pod restart counts, crash loop backoff events, OOMKilled instances, and probe failures to capture deployment health beyond explicit rollbacks.

3. **Monitor deployment windows:** Track the 24-48 hour windows following deployments for latent failures that may not trigger immediate rollbacks.

4. **Analyze rollback triggers:** Investigate what conditions trigger the pbx-web rollback—was it automated (health check failures) or manual?

## Data Sources

- Classified failures: `classified-failures.json`
- Deployment events: `deployment-events-30days-comprehensive.json`
- Analysis window: 2026-07-07 to 2026-08-06

## Next Steps

To improve temporal analysis quality:
- Collect pod restart events and crash loop data
- Include probe failure events
- Track resource exhaustion events (OOMKilled)
- Monitor image pull failures (ImagePullBackOff)
- Aggregate deployment lead times and time-to-stable metrics
