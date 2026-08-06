# Whisper-STT Deployment Events Analysis (30-Day Window)

**Generated:** 2026-08-06
**Cluster:** ardenone-manager
**Namespace:** whisper-stt
**Analysis Period:** 2026-07-07 to 2026-08-06 (30 days)

## Executive Summary

Both `whisper-stt` and `whisper-openai` deployments have been **non-functional for the entire 30-day analysis period** due to a critical infrastructure issue: the configured `longhorn` storage class does not exist on the cluster.

## Deployments Status

### whisper-stt
- **Current State:** 0/1 replicas available (FAILED)
- **Image:** ronaldraygun/whisper-stt:1.8.6
- **Resource Request:** 1 CPU / 4Gi RAM (limits: 8 CPU / 8Gi RAM)
- **Strategy:** Recreate (not rolling update)
- **Revision History:** 28 revisions total
- **Current ReplicaSet:** whisper-stt-847fd8d7b9 (24 days old)
- **Age:** Created 2026-05-01 (96 days ago)

### whisper-openai
- **Current State:** 0/1 replicas available (FAILED)
- **Image:** fedirz/faster-whisper-server:latest-cpu
- **Resource Request:** 1 CPU / 4Gi RAM (limits: 8 CPU / 8Gi RAM)
- **Strategy:** RollingUpdate
- **Revision History:** 24 revisions total
- **Current ReplicaSet:** whisper-openai-68966786fb (53 days old)
- **Age:** Created 2026-06-14 (53 days ago)

## Root Cause Analysis

### Primary Failure: Missing Storage Class

All three PVCs are stuck in `Pending` state:

| PVC Name | Status | Age | Storage Class | Error |
|----------|--------|-----|---------------|-------|
| whisper-model-cache | Pending | 84 days | longhorn | `storageclass.storage.k8s.io "longhorn" not found` |
| whisper-openai-model-cache | Pending | 53 days | longhorn | `storageclass.storage.k8s.io "longhorn" not found` |
| whisper-stt-jobs | Pending | 41 days | longhorn | `storageclass.storage.k8s.io "longhorn" not found` |

**Impact:** Pods cannot be scheduled because PVCs use `immediate` binding mode and remain unbound.

### Cascading Effects

1. **FailedScheduling warnings** every 15 minutes for both pods
2. **ProvisioningFailed errors** recurring continuously (logged as: "28s (x5941 over 24h)" for whisper-model-cache)
3. **ProgressDeadlineExceeded** conditions on both deployments
4. **No available replicas** despite 28+ rollout attempts

## 30-Day Event Timeline

### Recent Activity (Last 24 Hours)

- **16 minutes ago:** FailedScheduling warnings for both pods (unbound PVCs)
- **28 seconds ago:** ProvisioningFailed for all three PVCs (recurring every ~30 seconds)

### ReplicaSet Activity (30-Day Window)

**whisper-stt replica sets created in last 30 days:**
- whisper-stt-847fd8d7b9 (24d) - CURRENT
- whisper-stt-5dbff75cbd (29d)
- whisper-stt-5b8558f478 (29d)
- whisper-stt-6c497489fb (29d)
- Plus ~15 older replica sets from 29-43 days ago

**whisper-openai replica sets:** All 24 replica sets are exactly 53 days old (no new revisions in 30-day window)

## Deployment Health Metrics

| Metric | whisper-stt | whisper-openai |
|--------|-------------|----------------|
| Availability | 0% (0/1 pods) | 0% (0/1 pods) |
| Uptime (30d) | 0 days | 0 days |
| Restart Count | 0 (never ran) | 0 (never ran) |
| Rollout Attempts | 28 total, ~4 in 30d | 24 total, 0 in 30d |
| Progress Status | ProgressDeadlineExceeded | ProgressDeadlineExceeded |
| Conditions | MinimumReplicasUnavailable | MinimumReplicasUnavailable |

## Pod Details

### Current Pods

**whisper-stt-847fd8d7b9-b8rsj**
- Status: Pending
- Age: 24 days
- Restarts: 0
- Node: None (unschedulable)

**whisper-openai-68966786fb-tng29**
- Status: Pending
- Age: 53 days
- Restarts: 0
- Node: None (unschedulable)

### Pod Configuration

**whisper-stt:**
- Model: distil-large-v3
- Health checks: /health on port 8080
- Startup: 120s liveness delay, 60s readiness delay
- Volumes: model-cache, jobs-data (both PVCs failing)

**whisper-openai:**
- Model: large-v3-turbo
- Health checks: /health on port 8000
- Init container: model-download (patches faster-whisper for offline mode)
- Volume: model-cache PVC (failing)

## Infrastructure Context

**ArgoCD Integration:**
- Both deployments managed by ArgoCD (tracking-id annotations present)
- Auto-reload enabled via Reloader annotation
- GitOps sync likely failing silently due to storage class mismatch

**Storage Architecture Issue:**
- Deployments reference `longhorn` storage class
- Cluster storage classes available do NOT include `longhorn`
- Likely migrated away from Longhorn but deployment manifests not updated

## Recommendations

### Immediate Actions Required

1. **Fix PVC Storage Classes:**
   ```bash
   # Identify available storage classes
   kubectl get storageclass

   # Update PVCs to use correct storage class (likely "longhorn" needs to be replaced)
   # Options: migrate to existing storage class or reinstall Longhorn
   ```

2. **Update Deployment Manifests:**
   - Edit declarative-config to use correct storage class
   - Commit and push to trigger ArgoCD sync

3. **Consider PVC Data Migration:**
   - If existing data in PVCs, need migration strategy
   - If new deployments, can delete and recreate with correct storage class

### Long-term Improvements

1. **Storage Class Validation:** Add pre-commit hooks or CI checks to verify storage classes exist
2. **Alerting:** Configure alerts for PVC provisioning failures
3. **Documentation:** Document cluster storage architecture in runbooks
4. **GitOps Hygiene:** Review all ArgoCD-managed resources for similar issues

## Summary

The whisper-stt service has been completely down for at least 24 days (whisper-stt) and 53 days (whisper-openai) due to a missing storage class. This represents a critical infrastructure gap that has prevented any successful deployments despite 28+ rollout attempts. The fix requires updating PVC storage class specifications in the declarative-config repository.

**Estimated downtime:** 24-53 continuous days
**Business impact:** High - speech-to-text service completely unavailable
**Resolution path:** Update storage class → ArgoCD sync → PVC reprovision → deployment recovery

---

*Data source: kubectl queries to ardenone-manager cluster via proxy*
*Analysis generated by aide-de-camp automation*