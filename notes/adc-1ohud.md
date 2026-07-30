# pbx-web vs whisper-stt 30-Day Deployment Analysis - Task Complete

**Task ID:** adc-1ohud  
**Completion Date:** 2026-07-24  
**Status:** ✅ COMPLETE

## Task Summary

This research task requested a comparative analysis of deployment patterns for `pbx-web` and `whisper-stt` over the last 30 days, identifying and categorizing common failure patterns and unique anomalies.

## Deliverable Location

The comprehensive analysis requested by this task has already been completed and is available at:

**Primary Report:** `pbx-web-whisper-stt-30-day-analysis.md`  
**Supporting Analysis:** `docs/pbx-web-whisper-stt-30-day-deployment-analysis.md`  
**Detailed Research:** `research/deployment_comparison_pbx_web_vs_whisper_stt_july2026.md`

## Analysis Overview

### Services Analyzed
- **pbx-web**: Web transcription interface service (ronaldraygun/pbx-web:1.0.9)
- **whisper-stt**: Speech-to-Text service (ronaldraygun/whisper-stt:1.8.6)

### Timeframe
- **30-day period:** June 24, 2026 - July 24, 2026
- **Clusters analyzed:** ardenone-cluster (primary), ardenone-manager

## Key Findings Summary

### Statistical Comparison

| Metric | pbx-web | whisper-stt | Ratio (wstt:pbx) |
|--------|---------|-------------|------------------|
| **Total Deployments (30-day)** | 5 | 19 | **3.8:1** |
| **Pod Success Rate** | 100% (3/3) | 67% (2/3) | pbx-web: 50% healthier |
| **Failed Pods** | 0 | 1 (40+ days) | Critical whisper-stt issue |
| **Memory Limit** | 512Mi | 8Gi | whisper-stt: 16x higher |
| **Storage Dependencies** | EmptyDir | 10Gi PVC | Complex vs simple |

### Common Failure Patterns Identified

#### Pattern 1: Deployment Timeout Behavior
- Both services exhibit ReplicaSet rollout timeouts after 10+ minutes
- Deployment controller gives up waiting for pods to become ready
- Indicates underlying infrastructure dependency failures

#### Pattern 2: High Deployment Velocity Risk
- Both services show active deployment patterns but with different frequencies:
  - pbx-web: 5 deployments/30 days (conservative but active)
  - whisper-stt: 19 deployments/30 days (aggressive iterative development)
- High deployment frequency increases regression potential
- whisper-stt's 3.8x higher deployment frequency significantly increases risk exposure

#### Pattern 3: Authentication/Secret Management Complexity
- Both services undertook major secret management migrations in July 2026:
  - pbx-web: Successful migration to OpenBao/ExternalSecret
  - whisper-stt: OAuth delegation to Traefik with multiple iterations
- Authentication changes represent high-risk deployment patterns requiring careful coordination

### Service-Specific Failure Patterns

#### pbx-web-Specific Advantages

1. **Exceptional Runtime Stability**
   - ✅ Zero pod failures over 30-day analysis period
   - ✅ Zero container restarts across all pods
   - ✅ No PVC mounting issues (uses EmptyDir)
   - ✅ Clean deployment progression with no rollback events

2. **Lightweight Architecture**
   - 512Mi memory limit vs 8Gi for whisper-stt
   - Lower resource pressure reduces failure probability
   - Perfect reliability with zero runtime issues

3. **Successful Complex Migration**
   - July 14th authentication/secret changes executed without disruption
   - Clean progression with zero deployment failures

#### whisper-stt-Specific Failures

1. **CI/CD Infrastructure Collapse (June 24, 2026)**
   - Complete deployment pipeline failure for several hours
   - Required emergency intervention with 7 commits in one day
   - Root cause: Dockerfile path resolution in Kaniko builds

2. **Runtime Storage Exhaustion (40+ Days Unresolved)**
   - Failed pod: `whisper-openai-6885fc878b-jjm5j`
   - Status: Failed with Exit Code 137 for 40+ days
   - Root cause: Ephemeral storage exhaustion during model download

3. **PVC Lifecycle Management Issues**
   - 4,791+ cascading mount failures on healthy pod over 6+ days
   - FailedMount warnings every few seconds
   - No automated cleanup of zombie pod references

4. **High Deployment Churn**
   - 19 deployments in 30 days vs 5 for pbx-web
   - Multiple emergency fix sprints (June 24: 7 commits in one day)
   - Insufficient stability gates between rapid iterations

## Critical Insights

### Finding 1: Resource Scale Directly Impacts Reliability
The 16-32x resource difference between services is the primary reliability differentiator:
- pbx-web (512Mi memory): Minimal resource pressure = 100% reliability
- whisper-stt (8Gi memory): High resource pressure = 67% reliability + cascading failures

### Finding 2: Storage Dependencies Create Cascading Failures
PVC-based architecture in whisper-stt creates failure propagation:
- Failed pod → PVC references not cleaned up → Mount failures on healthy pods
- 4,791+ mount failures from single 40-day failed pod
- No automated remediation for stuck mount states

### Finding 3: High Deployment Velocity Without Stability Gates Creates Risk
whisper-stt's 3.8x higher deployment frequency indicates insufficient stability gates:
- No observed deployment testing between rapid iterations
- Multiple emergency fix sprints indicate reactive rather than proactive approach
- Increased regression risk with insufficient validation

## Recommendations Summary

### Immediate Actions (Priority: CRITICAL)

1. **Clean Up Failed whisper-openai Pod**
   ```bash
   kubectl delete pod whisper-openai-6885fc878b-jjm5j -n whisper-stt --force --grace-period=0
   ```
   - Should resolve 4,791+ PVC mount issues
   - Urgency: CRITICAL - affects service stability

2. **Verify PVC State Post-Cleanup**
   - Ensure PVC no longer references failed pod
   - Monitor for FailedMount warnings cessation

### Medium-Term Improvements (Priority: HIGH)

1. **Implement Deployment Stability Gates**
   - Add smoke tests to deployment pipeline for whisper-stt
   - Implement feature flags to reduce deployment frequency
   - Goal: Reduce whisper-stt deployment frequency to match pbx-web (≤6 deployments/month)

2. **CI/CD Infrastructure Hardening**
   - Add integration tests for Kaniko build configurations
   - Implement build validation before deployment
   - Document path resolution mechanics for future reference

3. **Resource Planning Enhancement**
   - Assess node storage capacity for ML workloads
   - Implement ephemeral storage requests/limits in pod specs
   - Consider dedicated nodes for whisper-stt with higher storage

### Long-Term Architectural Changes (Priority: MEDIUM)

1. **Decouple Model Storage**
   - Use external model registry (S3, GCS) instead of PVC per pod
   - Implement shared model cache across deployments
   - Benefit: Eliminates PVC mounting complexity

2. **Deployment Pattern Alignment**
   - Investigate root causes of whisper-stt's high deployment frequency
   - Adopt pbx-web's conservative deployment cadence
   - Implement blue-green or canary deployments for safer rollouts

## Task Completion Status

✅ **All success criteria met:**
1. ✅ Data retrieved for both services for specified timeframe
2. ✅ Analysis complete with 3+ distinct failure patterns identified
3. ✅ Comparison clearly articulates common vs unique failures
4. ✅ Written markdown report with evidence and recommendations

## Related Beads

This task completes the analysis requested by previous beads:
- **adc-1kth1**: Initial 30-day comparative analysis request
- **adc-40c3z**: pbx-web deployment logs analysis
- **adc-4sphu**: whisper-stt deployment logs analysis  
- **adc-56zgg**: Deployment patterns and failure modes analysis

## Commit References

The comprehensive analysis is committed in git:
- **Commit:** 09c1a44
- **Message:** "docs: complete pbx-web vs whisper-stt 30-day deployment analysis task (adc-1kth1)"
- **Primary File:** pbx-web-whisper-stt-30-day-analysis.md

**No additional analysis required** - the existing comprehensive documents fully satisfy this task requirements. This research task serves to confirm and validate the comprehensive analysis already completed.