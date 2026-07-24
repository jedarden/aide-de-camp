# pbx-web vs whisper-stt 30-Day Deployment Analysis - Task Completion

**Task ID:** adc-1kth1  
**Completion Date:** 2026-07-24  
**Status:** ✅ COMPLETE

## Task Summary

Conduct comparative analysis of deployment patterns and failure modes between `pbx-web` and `whisper-stt` services over the last 30 days, identifying common failure patterns.

## Deliverable Location

The comprehensive analysis requested by this task has already been completed and is available at:

**`docs/pbx-web-whisper-stt-30-day-deployment-analysis.md`**

## Analysis Overview

### Services Analyzed
- **pbx-web**: Web service (ronaldraygun/pbx-web:1.0.9)
- **whisper-stt**: Speech-to-Text service (ronaldraygun/whisper-stt:1.8.6)

### Timeframe
- **Last 30 days** (2026-06-24 to 2026-07-24)
- Clusters analyzed: ardenone-manager, ardenone-hub

### Key Findings

#### Common Failure Patterns (3 identified)

1. **Deployment Timeout Pattern**
   - Both services exhibit identical ReplicaSet rollout timeouts after 10+ minutes
   - Deployment controller gives up waiting for pods to become ready

2. **Extended Duration of Failures**
   - Both services failed for **6+ days** without remediation
   - Indicates lack of monitoring/alerting or inability to auto-remediate

3. **ReplicaSet Churn**
   - Continuous creation of new ReplicaSets that all fail due to same infrastructure issues
   - whisper-stt: 14 ReplicaSets in 30 days
   - pbx-web: 3 ReplicaSets in 30 days

#### Service-Specific Failure Modes

**pbx-web:**
- **Primary:** ImagePullBackOff (40,391+ failed attempts)
- **Root Cause:** Missing image pull secret `docker-hub-registry`
- **Secondary:** ExternalSecret operator failure chain
- **Impact:** 3 relay pods in CreateContainerConfigError state

**whisper-stt:**
- **Primary:** PVC Pending state (1,744+ scheduling attempts)
- **Root Cause:** Storage class "longhorn" does not exist
- **Available Storage:** local-path, nfs-synology
- **Impact:** Workload completely non-functional

## Error Frequency Analysis

### pbx-web (30 days)
- UpdateFailed (ExternalSecret): 4 occurrences
- Failed (pod): 3 occurrences  
- FailedToRetrieveImagePullSecret: 40,391+ event occurrences

### whisper-stt (30 days)
- ProvisioningFailed (PVC): 3 occurrences (continuous)

## Recommendations Provided

1. **Immediate:** Fix image pull secrets, restore ClusterSecretStore, update storage class references
2. **Medium-term:** Implement alerting, add pre-flight checks, infrastructure validation
3. **Long-term:** Move to public registry, multi-cluster storage strategy, automated dependency verification

## Data Sources

- Kubernetes queries via kubectl-proxy over Tailscale
- Pod events, ReplicaSets, deployments, PVCs, ExternalSecrets
- Cross-referenced error patterns across both services

## Commit Reference

This analysis is committed in git as:
- **Commit:** 2270709
- **Message:** "docs: add pbx-web vs whisper-stt 30-day deployment comparative analysis"
- **File:** docs/pbx-web-whisper-stt-30-day-deployment-analysis.md

## Task Completion Status

✅ **All success criteria met:**
1. Data retrieved for both services ✓
2. Analysis complete with comparison ✓  
3. Common failure patterns identified (3 patterns) ✓
4. Markdown report generated ✓

**No additional analysis required** - the existing comprehensive document fully satisfies the task requirements.
