# Deployment Success Rate Calculation (adc-ricou)

## Task Completion Summary

Calculated deployment success/failure rates for pbx-web and whisper-stt services based on 30-day deployment data (2026-07-07 to 2026-08-06).

## Results

### pbx-web
- **Total deployments (30 days)**: 4
- **Successful deployments**: 4
- **Failed deployments**: 0
- **Success rate**: 100.0%
- **Failure rate**: 0.0%
- **Deployment Strategy**: RollingUpdate
- **Current Status**: healthy
- **Current Revision**: 14
- **Deployment Frequency**: low

### whisper-stt
- **Total deployments (30 days)**: 10
- **Successful deployments**: 10
- **Failed deployments**: 0
- **Success rate**: 100.0%
- **Failure rate**: 0.0%
- **Deployment Strategy**: Recreate
- **Current Status**: healthy
- **Current Revision**: 32
- **Deployment Frequency**: high

## Comparative Analysis

### Reliability
Both services demonstrate **excellent reliability** with identical 100% success rates over the 30-day analysis period. Neither service experienced any deployment failures.

### Deployment Activity
- **pbx-web**: 4 deployments (stable service with low deployment frequency)
- **whisper-stt**: 10 deployments (2.5x more active deployment cadence)
- **Difference**: whisper-stt had 6 more deployments than pbx-web

### Deployment Strategy Differences
- **pbx-web**: Uses RollingUpdate strategy, which provides zero-downtime deployments by gradually replacing pods
- **whisper-stt**: Uses Recreate strategy, which terminates all pods before creating new ones (brief downtime during deployments)

### Operational Profiles
- **pbx-web**: Low deployment frequency with safer RollingUpdate strategy - suggests production stability focus
- **whisper-stt**: High deployment frequency with Recreate strategy - suggests active development with tolerance for brief downtime

## Key Findings

1. **Perfect Reliability**: Both services achieved 100% deployment success rates, indicating:
   - Stable container images
   - Proper resource allocation
   - Correct deployment configurations
   - No infrastructure issues during deployments

2. **Different Operational Profiles**:
   - pbx-web is more stable (low deployment frequency) but uses safer RollingUpdate strategy
   - whisper-stt has higher deployment frequency but uses Recreate strategy (suggests it can tolerate brief downtime)

3. **Healthy Operations**: Both services currently show "healthy" status with all replicas ready and available

## Methodology

### Success Criteria
A deployment is considered successful if the deployment event shows `success: true` in the deployment events data. This indicates that:
- The ReplicaSet was successfully created
- Pods reached ready state
- No deployment failures or rollbacks occurred

### Data Sources
- **pbx-web**: `research/pbx-web-30days/deployments-30days.json`
- **whisper-stt**: `research/whisper-stt-30days/deployments-30days.json`
- **Analysis Period**: 2026-07-07 to 2026-08-06 (30 days)
- **Cluster**: ardenone-cluster

### Calculation Formula
```
success_rate = (success_count / total_count) * 100
failure_rate = (failure_count / total_count) * 100
```

## Files Generated
- `research/calculate_deployment_success_rates.py` - Analysis script for reproducibility
- `research/deployment_success_rates_30days.json` - Machine-readable results with detailed metrics

## Acceptance Criteria Status
✅ 1. pbx-web success rate computed: **100.0%**
✅ 2. pbx-web failure rate computed: **0.0%**
✅ 3. whisper-stt success rate computed: **100.0%**
✅ 4. whisper-stt failure rate computed: **0.0%**
✅ 5. Raw counts (success/failure) documented: **4/0 for pbx-web, 10/0 for whisper-stt**

## Conclusion
Both pbx-web and whisper-stt services demonstrate excellent deployment reliability with 100% success rates over the 30-day analysis period. The difference in deployment strategies (RollingUpdate vs Recreate) and frequencies (low vs high) reflects different operational requirements and development patterns between the services.

---
*Bead: adc-ricou*
*Date: 2026-08-06*
*Analysis completed using data from previous deployment analysis beads*
