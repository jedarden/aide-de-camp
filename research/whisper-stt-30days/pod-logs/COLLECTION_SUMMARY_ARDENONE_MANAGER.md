# Whisper-STT Pod Log Collection - ardenone-manager

**Collection Date:** 2026-08-06  
**Cluster:** ardenone-manager  
**Namespace:** whisper-stt  
**Analysis Period:** 2026-07-07 to 2026-08-06 (30 days)

## Executive Summary

⚠️ **NO RUNTIME LOGS AVAILABLE** - All whisper-stt pods on ardenone-manager have been stuck in **Pending** state for 25-53 days due to missing PVC storage class. The pods never started, so no runtime logs exist.

## Pods Identified

### 1. whisper-openai-68966786fb-tng29
- **Status:** Pending (never scheduled)
- **Age:** 53 days (created 2026-06-14)
- **Issue:** FailedScheduling - unbound PersistentVolumeClaims
- **Blocker:** PVC `whisper-openai-model-cache` references non-existent storage class "longhorn"
- **Events:** `0/1 nodes are available: pod has unbound immediate PersistentVolumeClaims`
- **Log File:** `pod-whisper-openai-68966786fb-tng29.log` (pod describe output, no runtime logs)

### 2. whisper-stt-847fd8d7b9-b8rsj  
- **Status:** Pending (never scheduled)
- **Age:** 25 days (created 2026-07-12)
- **Issue:** FailedScheduling - unbound PersistentVolumeClaims
- **Blocker:** PVCs `whisper-model-cache` and `whisper-stt-jobs` reference non-existent storage class "longhorn"
- **Events:** `0/1 nodes are available: pod has unbound immediate PersistentVolumeClaims`
- **Log File:** `pod-whisper-stt-847fd8d7b9-b8rsj.log` (pod describe output, no runtime logs)

### 3. svclb-whisper-stt-c02117d2-f72hg (Load Balancer)
- **Status:** Running (kube-system service load balancer)
- **Age:** 96 days (created 2026-05-01)
- **Purpose:** Layer 2 load balancer for whisper-stt service
- **Log File:** `pod-svclb-whisper-stt-c02117d2-f72hg.log` (iptables/setup logs only)

## Root Cause Analysis

### Storage Class Configuration Error

The PVCs reference a storage class `longhorn` that does not exist on ardenone-manager:

```
Warning  ProvisioningFailed  persistentvolumeclaim/whisper-model-cache  
storageclass.storage.k8s.io "longhorn" not found

Warning  ProvisioningFailed  persistentvolumeclaim/whisper-openai-model-cache  
storageclass.storage.k8s.io "longhorn" not found

Warning  ProvisioningFailed  persistentvolumeclaim/whisper-stt-jobs             
storageclass.storage.k8s.io "longhorn" not found
```

### Impact

- **No whisper-stt pods have ever run on ardenone-manager** during the 30-day analysis window
- All pods created during this period failed immediately with FailedScheduling
- Zero runtime logs available for analysis
- Service has been completely non-functional on this cluster

## Comparison to ardenone-cluster

There are extensive logs already collected from **ardenone-cluster** where the pods are actually running:

- `whisper-openai-68966786fb-jsb5d` - Running 53 days, 5.1 MB of logs
- `whisper-stt-847fd8d7b9-v2rs5` - Running 23 days (silent but healthy)

See existing collection summaries:
- `COLLECTION_SUMMARY.md` - ardenone-cluster collection
- `LOG_COLLECTION_FINAL_SUMMARY.md` - comprehensive ardenone-cluster analysis

## Log Coverage

### ardenone-manager (this collection)
- **Runtime logs:** 0 bytes (pods never started)
- **Pod describe output:** Available (showing configuration and errors)
- **Coverage:** 0 days (pods never scheduled)

### ardenone-cluster (previous collection)
- **Runtime logs:** 5.1 MB from whisper-openai pod
- **Coverage:** 53 days (exceeds 30-day window)

## Recommendations

### Immediate Actions

1. **Fix PVC storage class:** Update PVCs to use available storage class or create Longhorn storage class
2. **Delete stuck pods:** Remove pending pods and recreate after PVC fix
3. **Verify storage:** Ensure PVCs are bound before pod creation

### For Future Analysis

1. **Use ardenone-cluster logs:** The existing collection from ardenone-cluster has substantial runtime logs
2. **Monitor PVC binding:** Alert on PVC provisioning failures
3. **Cluster inventory:** Track which clusters have functional deployments

## Acceptance Criteria Status

✅ Identify pods during 30-day window - Completed (2 pods found, both Pending)  
❌ Collect runtime logs - Failed (pods never started, no logs available)  
✅ Store in pod-logs/ - Completed (pod describe outputs stored)  
❌ Capture startup sequences/OOM/errors - N/A (pods never ran)  
✅ Create index - Completed  

## Success Criteria

⚠️ **PARTIAL SUCCESS** - Identified pods but no runtime logs available due to PVC configuration error preventing pod startup.

---

**Generated:** 2026-08-06  
**Task Bead:** adc-1elyb  
**Confidence Level:** HIGH - Direct cluster inspection  
