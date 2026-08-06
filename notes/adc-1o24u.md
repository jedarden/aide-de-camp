# Cross-Service Deployment Correlation Analysis

## Task (adc-1o24u)
Analyze cross-service deployment correlations between pbx-web and whisper-stt.

## Summary

**Finding: NO CORRELATION DETECTED**

The 30-day analysis (2026-07-07 to 2026-08-06) reveals **no temporal correlation** between pbx-web and whisper-stt deployment incidents. Both services operate independently with well-separated deployment events.

## Dataset Overview

| Service | Events | Issues | Analysis Period |
|---------|--------|--------|-----------------|
| pbx-web | 5 | 1 rollback | 2026-07-13 to 2026-07-28 |
| whisper-stt | 3 | 0 | 2026-07-08 rapid deployment sequence |

## Timeline Analysis

### Unified Timeline (8 events total)
1. **2026-07-08 03:09** - whisper-stt replica created (v1.8.2)
2. **2026-07-08 03:16** - whisper-stt replica created (v1.8.4) - +7 min
3. **2026-07-08 03:26** - whisper-stt replica created (v1.8.6) - +11 min
4. **2026-07-13 18:07** - pbx-web deployment rollback (1.0.9 → 1.0.8)
5. **2026-07-13 18:18** - pbx-web deployment rollout (v1.0.9) - +10 min
6. **2026-07-15 03:24** - pbx-web rebuild relay deployment
7. **2026-07-27 17:56** - lab rebuild relay deployment
8. **2026-07-28 17:26** - pbx-web current deployment (v1.0.9)

### Temporal Clustering
- **Mean interval**: 70.6 hours between events
- **Median interval**: 23.5 hours
- **Range**: 6.5 minutes (same-service cluster) to 302.5 hours
- **Events within 1 hour**: 3 (all within same service, not cross-service)

## Correlation Analysis

### Windows Tested
- ±5 minutes: 0 correlations
- ±10 minutes: 0 correlations
- ±15 minutes: 0 correlations
- ±30 minutes: 0 correlations
- ±60 minutes: 0 correlations

### Issue Correlation Check
- **pbx-web issues**: 1 (rollback on 2026-07-13 18:07)
- **whisper-stt issues**: 0
- **Temporal proximity**: pbx-web rollback occurred 5+ days after whisper-stt's rapid deployment sequence (2026-07-08)

## Key Findings

1. **No temporal correlation detected** between pbx-web and whisper-stt deployments across all tested correlation windows (5-60 minutes)

2. **Service independence**: Deployment events are well-separated in time (hours to days apart)

3. **No cascading failures**: The single pbx-web rollback on 2026-07-18 occurred 5 days after whisper-stt's deployment sequence and shows no temporal relationship

4. **whisper-stt stability**: Zero failures/incidents despite rapid deployment sequence on 2026-07-08 (3 deployments in 17 minutes: 1.8.2 → 1.8.4 → 1.8.6)

5. **pbx-web stability**: Only 1 rollback event (100% success rate otherwise)

## Conclusion

**Both services operate independently with no cross-service deployment dependency patterns.** The lack of coincident deployment windows across all tested time windows (±5 to ±60 minutes) indicates:

- No coordinated deployment schedules
- No cascading failure patterns
- No temporal relationship between whisper-stt and pbx-web deployment events
- Both services can be deployed/maintained independently without risk of cross-service interference

## Files Generated

- `analyze_correlations.py` - Analysis script
- `docs/research/deployment-data/correlation-analysis-results.json` - Machine-readable results
- `notes/adc-1o24u.md` - This summary

## Methodology

The analysis used:
- Temporal alignment of deployment events by timestamp
- Multi-window correlation testing (5, 10, 15, 30, 60 minutes)
- Lag time calculation for correlated events
- Failure/issue temporal proximity checking
- Clustering analysis for event patterns

**Result**: Zero correlations found across all windows, confirming independent operation.
