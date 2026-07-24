# Deployment Patterns Analysis: pbx-web vs whisper-stt

**Analysis Period**: June 24, 2026 - July 24, 2026 (30 days)  
**Cluster**: ardenone-manager  
**Date Generated**: July 24, 2026  

---

## Executive Summary

Both `pbx-web` and `whisper-stt` services have experienced **complete deployment failures for 84 consecutive days**. Despite continuous deployment attempts with new versions and images, fundamental infrastructure blocking issues prevent any successful rollout. The failure patterns are distinct between the two services but share the common characteristic of being unresolved infrastructure configuration problems.

**Key Finding**: 100% of deployment attempts for both services have failed for over 2.5 months, with no successful deployments in the observation period.

---

## Service-Specific Analysis

### pbx-web Deployment Health

**Status**: 🔴 CRITICAL - 84 days continuous failure  
**Current Deployment**: pbx-web-5ff68464d (11 days old, ImagePullBackOff)  
**Deployment Attempt Rate**: 9 version releases (1.0.0 → 1.0.9)  
**Success Rate**: 0% (0/9 deployments successful)

#### Primary Failure Modes

1. **Secret Management Failure** (Critical)
   - **Impact**: Prevents container creation entirely
   - **Root Cause**: ExternalSecret resources stuck in `SecretSyncedError` state
   - **Error Pattern**: `ClusterSecretStore "openbao" is not ready`
   - **Affected Resources**: 
     - garage-pbx-creds
     - lab-rebuild-relay
     - pbx-rebuild-relay
     - pbx-web-auth

2. **Image Pull Authentication Issues** (Critical)
   - **Error**: `FailedToRetrieveImagePullSecret` - Unable to retrieve docker-hub-registry secret
   - **Current Pod Status**: pbx-web-5ff68464d-tzwwx in `ImagePullBackOff` state
   - **Restart Count**: 1 (6 days ago) - indicating repeated pull failures

3. **Relay Service Failures** (High)
   - **Status**: CreateContainerConfigError across all relay pods
   - **Age**: 80+ days of continuous failure
   - **Error**: Secret not found for lab-rebuild-relay and pbx-rebuild-relay

#### Deployment Timeline

| Date | Version | Age (Current) | Status | Failure Reason |
|------|---------|---------------|--------|-----------------|
| May 1 | latest | 84d | Failed | Initial deployment failure |
| Jul 15 | 1.0.8 | 11d | Failed | ImagePullBackOff |
| Jul 15 | 1.0.9 | 11d | Failed | ImagePullBackOff (current) |

#### Infrastructure Dependencies

- **Secret Store**: ExternalSecret operator with ClusterSecretStore "openbao"
- **Image Registry**: docker-hub-registry (authentication failing)
- **Pod Status**: 0/1 ready for 84 days

---

### whisper-stt Deployment Health

**Status**: 🔴 CRITICAL - 84 days continuous failure  
**Current Deployment**: whisper-stt-847fd8d7b9 (12 days old, Pending)  
**Deployment Attempt Rate**: 15+ replica sets with multiple image versions  
**Success Rate**: 0% (0/15+ deployments successful)

#### Primary Failure Modes

1. **Storage Class Configuration** (Critical)
   - **Error**: `storageclass.storage.k8s.io "longhorn" not found`
   - **Impact**: All PVCs stuck in `Pending` state, preventing pod scheduling
   - **Affected PVCs**:
     - whisper-model-cache (72 days pending)
     - whisper-openai-model-cache (40 days pending)
     - whisper-stt-jobs (29 days pending)

2. **Pod Scheduling Failures** (Critical)
   - **Error**: `FailedScheduling` - pod has unbound immediate PersistentVolumeClaims
   - **Root Cause**: PVCs cannot provision without valid storage class
   - **All Pods**: Stuck in `Pending` state

#### Deployment Variations

| Component | Image Versions | Deployment Count | Current Status |
|-----------|---------------|------------------|----------------|
| whisper-stt | 1.0.27 → 1.8.6 | 43 replica sets | All Pending |
| whisper-openai | Multiple images | 25+ replica sets | All Pending |

#### Infrastructure Dependencies

- **Required StorageClass**: "longhorn" (MISSING)
- **Available StorageClasses**: 
  - local-path (default)
  - nfs-synology
- **PVC Status**: 100% pending for 29-72 days

---

## Comparative Analysis

### Failure Pattern Comparison

| Aspect | pbx-web | whisper-stt |
|--------|---------|-------------|
| **Duration of Failure** | 84 days | 84 days |
| **Primary Blocker** | Secret management | Storage configuration |
| **Pod State** | ImagePullBackOff / ConfigError | Pending (PVC) |
| **Deployment Attempts** | 9 versions | 15+ versions |
| **Infrastructure Ready** | Partial (ClusterSecretStore down) | No (missing StorageClass) |
| **Resolution Path** | Fix ClusterSecretStore | Update PVC specs or add Longhorn |

### Shared Characteristics

1. **Chronic Infrastructure Issues**
   - Both failures stem from infrastructure configuration, not application code
   - Problems have persisted through multiple deployment attempts
   - Continuous deployment pipeline continues despite 0% success rate

2. **Extended Duration**
   - Both services have been completely non-functional for 84 days
   - No successful deployments in the 30-day observation period
   - Age analysis suggests problems began in early May 2026

3. **Multiple Deployment Attempts**
   - Both services received regular updates despite consistent failures
   - CI/CD pipeline continues to push new deployments
   - No automated rollback or failure detection mechanisms apparent

---

## Root Cause Analysis

### pbx-web Root Causes

**Primary Cause**: ExternalSecret operator unable to sync secrets from "openbao" ClusterSecretStore

**Contributing Factors**:
1. ClusterSecretStore "openbao" not ready or misconfigured
2. Docker registry authentication failing (image pull secrets)
3. No graceful degradation for missing secrets

**Dependency Chain**:
```
ExternalSecret → ClusterSecretStore (openbao) → Secret Sync → Pod Container Creation
                                    ↓ FAILURE
                              All downstream steps blocked
```

### whisper-stt Root Causes

**Primary Cause**: PVC specifications reference non-existent StorageClass "longhorn"

**Contributing Factors**:
1. Storage class "longhorn" was removed or never installed on ardenone-manager
2. No PVC update mechanism to use available storage classes
3. No storage class migration strategy

**Dependency Chain**:
```
PVC → StorageClass (longhorn) → Volume Provisioning → Pod Scheduling
            ↓ MISSING
                    All downstream steps blocked
```

---

## Trends and Observations

### Positive Trends
- None observed in the 30-day period

### Negative Trends

1. **Continuous Failure Without Intervention**
   - No infrastructure fixes applied during observation period
   - Deployments continue to fail without interruption
   - No apparent escalation or remediation efforts

2. **Resource Waste**
   - Multiple replica sets created despite guaranteed failure
   - CI/CD resources consumed on predictable failures
   - Cluster resources occupied by non-functional pods

3. **Lack of Monitoring Response**
   - No automated alerts detected in analysis
   - Failed deployments continue through normal pipeline
   - No manual intervention evident in event logs

4. **Service Absence Impact**
   - Both services completely unavailable for 84+ days
   - No backup or failover mechanisms observed
   - Dependencies/users impacted without resolution

---

## Statistical Context

### Deployment Statistics (30-Day Window)

| Metric | pbx-web | whisper-stt |
|--------|---------|-------------|
| **Total Deployment Attempts** | 9 | 15+ |
| **Successful Deployments** | 0 | 0 |
| **Success Rate** | 0% | 0% |
| **Days Non-Functional** | 84 | 84 |
| **Current Pod State** | ImagePullBackOff | Pending |
| **Ready Replicas** | 0/1 | 0/1 |
| **Available Replicas** | 0/1 | 0/1 |

### Resource Impact

- **Non-functional Replica Sets**: pbx-web (15), whisper-stt (68+)
- **Stuck PVCs**: 3 (whisper-stt)
- **Failed ExternalSecrets**: 4 (pbx-web)
- **Cluster Resources**: Consumed by non-functional workloads

---

## Recommendations

### Immediate Actions (Critical)

1. **pbx-web**:
   - Restore ClusterSecretStore "openbao" functionality
   - Verify and repair docker-hub-registry image pull secrets
   - Update ExternalSecret resources once ClusterSecretStore is ready
   - Consider secret migration if "openbao" is permanently unavailable

2. **whisper-stt**:
   - Update PVC specifications to use available StorageClass (nfs-synology or local-path)
   - Alternatively, install/restore Longhorn storage class if required
   - Delete and recreate PVCs after storage class resolution
   - Verify volume binding and data persistence requirements

### Medium-Term Improvements

1. **Infrastructure Validation**
   - Add pre-deployment checks for infrastructure dependencies
   - Implement storage class and secret store validation
   - Create dependency health checks in CI/CD pipeline

2. **Failure Detection & Response**
   - Configure alerts for chronic deployment failures
   - Implement automatic rollback on consistent failure patterns
   - Add monitoring for ExternalSecret and PVC status

3. **Deployment Pipeline Guards**
   - Block deployments when infrastructure dependencies are unhealthy
   - Add canary deployment validation
   - Implement progressive rollout with automated rollback

### Long-Term Architectural Considerations

1. **Secret Management Strategy**
   - Evaluate ExternalSecret operator configuration and reliability
   - Consider secret migration if "openbao" is deprecated
   - Implement secret rotation and backup mechanisms

2. **Storage Architecture**
   - Document storage class requirements per service
   - Implement storage class migration strategy
   - Evaluate PVC provisioning and backup requirements

3. **Service Availability**
   - Implement multi-cluster deployment for critical services
   - Add failover mechanisms for infrastructure dependencies
   - Consider service mesh for resilience

---

## Conclusion

The deployment patterns for `pbx-web` and `whisper-stt` reveal **chronic, unresolved infrastructure failures** that have rendered both services completely non-functional for 84 consecutive days. While the failure modes differ (secrets vs. storage), both share the characteristic of being infrastructure-level blockers that prevent any successful deployment despite continuous attempts.

The lack of intervention, continuous deployment pipeline operation without success checks, and extended duration of these failures indicate significant gaps in infrastructure monitoring, deployment validation, and operational response procedures.

**Resolution Priority**: CRITICAL - Both services require immediate infrastructure remediation before any application deployment can succeed.

---

*Report generated via automated Kubernetes deployment analysis*
*Cluster: ardenone-manager | Namespace: pbx-web, whisper-stt*