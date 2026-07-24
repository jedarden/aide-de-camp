# whisper-stt Deployment Logs Analysis (Last 30 Days)

**Task ID:** adc-4sphu  
**Analysis Date:** 2026-07-24  
**Timeframe:** Last 30 days (2026-06-24 to 2026-07-24)  
**Cluster:** ardenone-manager  
**Namespace:** whisper-stt  

## Executive Summary

The whisper-stt service has been **completely non-functional** for the past 30 days due to a critical storage infrastructure failure. All pods remain in Pending state, unable to be scheduled due to unbound PersistentVolumeClaims. The deployment has been stuck in a timeout state since 2026-07-12.

## Current Status

### Deployments
- **whisper-stt deployment**: Age 84d, Image: `ronaldraygun/whisper-stt:1.8.6`
  - Status: 0/1 ready, unavailable
  - Condition: ProgressDeadlineExceeded (2026-07-12)
  - Revision: 28 (29th generation)
  
- **whisper-openai deployment**: Age 40d, Image: `fedirz/faster-whisper-server:latest-cpu`
  - Status: 0/1 ready, unavailable

### Pods
- **whisper-stt-847fd8d7b9-b8rsj**: Age 12d, Status: Pending
- **whisper-openai-68966786fb-tng29**: Age 40d, Status: Pending

## Deployment History (Last 30 Days)

### whisper-stt ReplicaSets Created
| ReplicaSet | Age | Image | Status |
|------------|-----|-------|--------|
| whisper-stt-847fd8d7b9 | 12d | ronaldraygun/whisper-stt:1.8.6 | 0/1 ready |
| whisper-stt-6c497489fb | 16d | ronaldraygun/whisper-stt:1.8.6 | 0/1 ready |
| whisper-stt-5b8558f478 | 16d | ronaldraygun/whisper-stt:1.8.4 | 0/1 ready |
| whisper-stt-5dbff75cbd | 16d | ronaldraygun/whisper-stt:1.8.2 | 0/1 ready |
| whisper-stt-6b96f4569c | 22d | ronaldraygun/whisper-stt:1.7.0 | 0/1 ready |
| whisper-stt-6464bdf67b | 23d | ronaldraygun/whisper-stt:1.6.0 | 0/1 ready |
| whisper-stt-5b884b75f4 | 28d | ronaldraygun/whisper-stt:1.5.1 | 0/1 ready |
| whisper-stt-78bbf5f57f | 28d | ronaldraygun/whisper-stt:1.4.1 | 0/1 ready |
| whisper-stt-558c7cf44 | 29d | ronaldraygun/whisper-stt:1.3.1 | 0/1 ready |
| whisper-stt-65fb7f8dd9 | 29d | ronaldraygun/whisper-stt:1.3.0 | 0/1 ready |

**Total whisper-stt ReplicaSets in last 30 days:** 10  
**Deployment churn rate:** New ReplicaSet every ~3 days  
**All failed with identical root cause:** Storage class "longhorn" not found

### whisper-openai ReplicaSets Created
- **21 ReplicaSets** created in last 40 days (all scaled to 0, all failed with same issue)
- All using various image tags of `fedirz/faster-whisper-server:latest-cpu`

## PersistentVolumeClaim Status

All PVCs are stuck in Pending state due to missing storage class:

| PVC Name | Age | Storage Class | Status | Requested Capacity | Events Count |
|----------|-----|---------------|--------|-------------------|--------------|
| whisper-model-cache | 72d | longhorn | Pending | 10Gi | 35,650+ |
| whisper-openai-model-cache | 40d | longhorn | Pending | 10Gi | 35,650+ |
| whisper-stt-jobs | 29d | longhorn | Pending | 1Gi | 35,650+ |

### Storage Class Mismatch
**Available Storage Classes on Cluster:**
- `local-path` (default) - rancher.io/local-path provisioner
- `nfs-synology` - cluster.local/synology-nfs provisioner

**Required by whisper-stt:**
- `longhorn` - **DOES NOT EXIST**

## Error Events Analysis

### Critical Events (Last 6 days)
**Event Frequency:** Every 75 seconds continuously

1. **FailedScheduling** - Both pods
   - Count: 1,780+ events over 6d4h (one every ~15 seconds)
   - Message: "0/1 nodes are available: pod has unbound immediate PersistentVolumeClaims. preemption: 0/1 nodes are available: 1 Preemption is not helpful for scheduling."

2. **ProvisioningFailed** - All 3 PVCs
   - Count: 35,650+ events per PVC over 6d4h
   - Message: "storageclass.storage.k8s.io 'longhorn' not found"
   - Total: ~106,950+ provisioning failure events

### Deployment Conditions
**whisper-stt deployment:**
- **Available**: False since 2026-05-01
  - Reason: MinimumReplicasUnavailable
  - Message: "Deployment does not have minimum availability."
  
- **Progressing**: False since 2026-07-12
  - Reason: ProgressDeadlineExceeded
  - Message: "ReplicaSet whisper-stt-847fd8d7b9 has timed out progressing."

## Timeline of Failures

### June 2026
- **2026-06-14**: whisper-openai-model-cache PVC created (40d ago) - stuck in Pending
- **2026-06-25**: whisper-stt-jobs PVC created (29d ago) - stuck in Pending

### July 2026
- **2026-07-12**: whisper-stt ReplicaSet "whisper-stt-847fd8d7b9" created - still timeout
- **2026-07-12 to 2026-07-24**: Continuous FailedScheduling events (1,780+)
- **2026-07-24**: Analysis date - service still completely non-functional

## Root Cause Analysis

### Primary Issue: Storage Class Infrastructure Gap

**Root Cause Chain:**
1. whisper-stt deployment configuration expects storage class "longhorn"
2. Longhorn storage provisioner is **not installed** on ardenone-manager cluster
3. PVCs cannot be provisioned without the required storage class
4. Pods remain in Pending state, unable to be scheduled
5. Deployment controller gives up after 600-second progress deadline

**Impact:**
- whisper-stt workload is **100% non-functional** (0/1 pods ready)
- whisper-openai workload is **100% non-functional** (0/1 pods ready)
- 106,950+ provisioning failure events generated
- 1,780+ scheduling failures over 6 days

### Secondary Observations

**Deployment Strategy:**
- Uses `Recreate` strategy (not RollingUpdate)
- Image pull secrets required: `docker-hub-registry`
- Progress deadline: 600 seconds (10 minutes)

**Resource Requirements:**
- CPU: 1 request, 8 limit
- Memory: 4Gi request, 8Gi limit
- No resource constraints causing failures

**Node Affinity:**
- Preferred: k3s-agent-minisforum (weight 100)
- Fallback: k3s-lenovo-tiny (weight 90)
- Not causing scheduling failures (PVC issue is primary blocker)

## Data Quality Notes

### ArgoCD Access
- **Status**: ArgoCD read-only API at `https://argocd-ro-ardenone-manager-ts.ardenone.com:8444` returned no data
- **Impact**: Could not retrieve ArgoCD application synchronization history
- **Alternative**: Used kubectl annotations from ArgoCD tracking IDs

### Cluster Access
- **Method**: kubectl-proxy over Tailscale at `http://traefik-ardenone-manager:8001`
- **Permissions**: Read-only (devpod-observer namespace)
- **Coverage**: Successfully retrieved all Kubernetes objects

## Conclusions

1. **Complete Service Outage**: whisper-stt has been 100% unavailable for the entire 30-day analysis period

2. **Infrastructure Dependency Failure**: The service requires Longhorn storage which is not available in the cluster infrastructure

3. **Deployment Churn**: Despite all failures, the deployment controller continues creating new ReplicaSets (10 in 30 days) when image updates occur, all failing identically

4. **No Self-Recovery**: The system cannot self-recover from this infrastructure gap - manual intervention required to either:
   - Install Longhorn storage provisioner
   - Update PVCs to use available storage classes (`local-path` or `nfs-synology`)

5. **Silent Failure**: No apparent monitoring or alerting triggered for this critical infrastructure gap spanning 30+ days

## Recommendations

### Immediate Actions
1. **Fix storage class references** in whisper-stt PVCs to use `local-path` or `nfs-synology`
2. **Delete and recreate PVCs** with correct storage class
3. **Restart pods** once PVCs are bound

### Long-term Improvements
1. **Implement storage class validation** in deployment pipelines
2. **Add infrastructure dependency checks** before deployment
3. **Configure alerting** for PVC Pending state > 5 minutes
4. **Document storage requirements** for all services

---

**Analysis Methodology:**  
- Queried ardenone-manager cluster via kubectl-proxy over Tailscale  
- Analyzed deployment status, ReplicaSets, pods, PVCs, events, and storage classes  
- Focused on 30-day window from 2026-06-24 to 2026-07-24  
- Correlated error patterns with deployment timeline

**Data Sources:**
- `kubectl get deployments/replicasets/pods/pvc/events -n whisper-stt`
- `kubectl describe pod/pvc/deployment`
- `kubectl get storageclass`
- Kubernetes API JSON outputs