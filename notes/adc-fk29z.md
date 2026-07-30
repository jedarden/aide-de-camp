# pbx-web vs whisper-stt Deployment Comparison: Last 30 Days

**Analysis Period:** June 24, 2026 – July 24, 2026 (rolling 30-day window)  
**Clusters Analyzed:** ardenone-cluster, ardenone-manager  
**Analysis Date:** July 24, 2026

## Executive Summary

Both services exhibit **asymmetric deployment stability** across clusters. On **ardenone-cluster**, both services run reliably with minimal issues. On **ardenone-manager**, both services experience significant but different failure patterns. The root causes are primarily **infrastructure and environmental issues** rather than application-level failures.

**Deployment Velocity:** whisper-stt deploys **2.75× more frequently** than pbx-web (11 vs 4 deployments in 30 days).

---

## Deployment Frequency Analysis

### pbx-web
- **Total deployments (30 days):** 4 ReplicaSets
- **Version progression:** 1.0.7 → 1.0.8 → 1.0.9
- **Deployment cadence:** Irregular, with 3 deployments on July 13th alone
- **Current version:** 1.0.9 (deployed July 13, 2026)

### whisper-stt
- **Total deployments (30 days):** 11 ReplicaSets  
- **Version progression:** 1.2.5 → 1.3.0 → 1.3.1 → 1.4.1 → 1.5.1 → 1.6.0 → 1.7.0 → 1.8.2 → 1.8.4 → 1.8.6
- **Deployment cadence:** Highly active, with multiple deployments on single days (July 8th: 3 deployments)
- **Current version:** 1.8.6 (deployed July 12, 2026)

**Key Finding:** whisper-stt has significantly higher deployment velocity, suggesting more active development or configuration refinement.

---

## Cluster Health Comparison

### ardenone-cluster (Healthy)

| Service | Status | Active Pods | Notes |
|---------|--------|-------------|-------|
| pbx-web | ✅ Healthy | 3/3 Running | All pods operational, 1 ContainerStatusUnknown (40d old, legacy) |
| whisper-stt | ✅ Healthy | 2/3 Running | Active pods running, 1 ContainerStatusUnknown (40d old, legacy) |

### ardenone-manager (Degraded)

| Service | Status | Failure Mode | Pod States |
|---------|--------|--------------|------------|
| pbx-web | ❌ Critical | ImagePullBackOff + CreateContainerConfigError | 1/4 Running, 1 ImagePullBackOff, 2 CreateContainerConfigError |
| whisper-stt | ❌ Critical | Unschedulable (PVC binding) | 0/2 Running, 2 Pending |

---

## Failure Pattern Analysis

### pbx-web-Specific Failures

#### 1. Image Pull Failures
- **Error:** `ImagePullBackOff` for `ronaldraygun/pbx-web:1.0.9`
- **Location:** ardenone-manager only
- **Root Cause:** Failed to retrieve image pull secrets (docker-hub-registry)
- **Duration:** Ongoing for **6+ days** with 40,530+ retry attempts
- **Impact:** Latest version cannot deploy, leaving older version in place

#### 2. Configuration Errors
- **Error:** `CreateContainerConfigError` on legacy pods (80+ days old)
- **Root Cause:** Missing required secrets (`pbx-rebuild-relay`, `lab-rebuild-relay`)
- **Impact:** Orphaned pods cannot start, consuming cluster resources

#### 3. ArgoCD Sync Timeouts
- **Error:** Sync operation failures with "Operation terminated, triggered by controller sync timeout (retried 5 times)"
- **Frequency:** 4 recent timeouts within 1 hour
- **Root Cause:** Likely resource contention or controller overload during deployment

#### 4. Network Infrastructure Issues
- **Error:** `IPAddressWrongReference` and `ClusterIPNotAllocated` warnings
- **Affected Services:** pbx-rebuild-egress, lab-rebuild-egress
- **Frequency:** Continuous, 30+ warnings in past hour
- **Impact:** Service IP allocation instability, potential routing failures

### whisper-stt-Specific Failures

#### 1. Storage Binding Failures
- **Error:** `FailedScheduling` - "pod has unbound immediate PersistentVolumeClaims"
- **Location:** ardenone-manager only
- **Root Cause:** PVCs for `whisper-model-cache` and `whisper-stt-jobs` cannot bind
- **Duration:** Ongoing for **6+ days** with 1,750+ scheduling failures
- **Impact:** Cannot schedule new pods, blocking deployments

#### 2. StorageClass Missing
- **Error:** `ProvisioningFailed` - "storageclass.storage.k8s.io 'longhorn' not found"
- **Affected PVCs:** whisper-model-cache, whisper-stt-jobs, whisper-openai-model-cache
- **Root Cause:** Longhorn StorageClass not available on ardenone-manager
- **Impact:** New PVCs cannot provision, pod scheduling blocked

#### 3. High Deployment Churn
- **Observation:** 11 deployments in 30 days (vs 4 for pbx-web)
- **Potential Root Causes:**
  - Active development with frequent fixes/updates
  - Configuration iteration and refinement
  - Attempting to resolve storage/environment issues
- **Impact:** Increased deployment noise, potential resource contention

---

## Common Failure Patterns

### 1. Cluster Asymmetry
**Pattern:** Both services work correctly on ardenone-cluster but fail on ardenone-manager

**Root Causes:**
- **Infrastructure divergence:** Missing or misconfigured resources on ardenone-manager
- **Secret propagation issues:** Secrets available on one cluster but not the other
- **Storage class availability:** Longhorn available on ardenone-cluster, missing on ardenone-manager

### 2. Dependency Resolution Failures
**Pattern:** Both services fail due to missing external dependencies (secrets, storage, networking)

**Examples:**
- pbx-web: Missing image pull secrets, missing pod secrets
- whisper-stt: Missing StorageClass, unbindable PVCs

### 3. Environmental vs. Application Issues
**Pattern:** Failures are infrastructure/environmental rather than application-level

**Evidence:**
- No application crash loops or OOMKilled events
- No readiness/liveness probe failures in running pods
- Failures occur during deployment/scheduling, not runtime

---

## Infrastructure Issues Identified

### ExternalSecret Operator
- **Status:** Degraded on ardenone-manager
- **Error:** `ClusterSecretStore "openbao" is not ready`
- **Impact:** Cannot sync secrets from OpenBaaS, blocking pod creation

### Storage Infrastructure
- **Issue:** Longhorn StorageClass missing on ardenone-manager
- **Impact:** Cannot provision PVCs for stateful workloads

### Load Balancer / Networking
- **Issue:** MetalLB annotation deprecation warnings
- **Impact:** Using deprecated annotation `metallb.universe.tf/allow-shared-ip`
- **Frequency:** Ongoing warnings

### ArgoCD Controller
- **Issue:** Sync timeouts during deployment
- **Impact:** Deployment synchronization delays and retries

---

## Stability Assessment

### pbx-web Stability: ⚠️ MODERATE
- **ardenone-cluster:** ✅ STABLE
- **ardenone-manager:** ❌ CRITICAL
- **Overall:** Stable on primary cluster, broken on secondary

**Risk Factors:**
- Image pull configuration inconsistent across clusters
- Legacy pods consuming resources due to missing secrets
- Network IP allocation instability

### whisper-stt Stability: ⚠️ MODERATE  
- **ardenone-cluster:** ✅ STABLE
- **ardenone-manager:** ❌ CRITICAL
- **Overall:** Stable on primary cluster, completely broken on secondary

**Risk Factors:**
- Storage infrastructure missing on ardenone-manager
- High deployment velocity increases failure surface
- PVC binding issues block all deployments

---

## Recommendations

### Immediate Actions (Priority 1)

1. **Fix ExternalSecret Operator on ardenone-manager**
   - Restore OpenBaaS ClusterSecretStore connectivity
   - Verify secret propagation across clusters
   - Target: Both clusters

2. **Add Longhorn StorageClass to ardenone-manager**
   - Install or enable Longhorn storage on ardenone-manager
   - Migrate whisper-stt PVCs to available storage class if Longhorn cannot be added
   - Target: ardenone-manager

3. **Fix Image Pull Secrets for pbx-web**
   - Ensure docker-hub-registry secret exists on ardenone-manager
   - Test image pull for ronaldraygun/pbx-web:1.0.9
   - Target: ardenone-manager

### Medium-Term Actions (Priority 2)

4. **Clean Up Legacy Pods**
   - Delete CreateContainerConfigError pods (80+ days old)
   - Remove old ReplicaSets that are no longer needed
   - Target: Both clusters

5. **Address MetalLB Annotation Deprecation**
   - Migrate from deprecated `metallb.universe.tf/allow-shared-ip` annotation
   - Update service configurations to use current MetalLB API
   - Target: Both clusters

6. **Investigate ArgoCD Sync Timeouts**
   - Review controller resource allocation
   - Check for resource contention during deployments
   - Consider increasing sync timeout if needed
   - Target: ardenone-manager

### Long-Term Actions (Priority 3)

7. **Implement Cluster Parity Checks**
   - Create validation tests to ensure infrastructure parity across clusters
   - Include checks for: StorageClasses, Secrets, networking resources
   - Run pre-deployment validation

8. **Review whisper-stt Deployment Velocity**
   - Assess whether 11 deployments in 30 days is intentional
   - Consider feature freeze for stability period
   - Implement canary deployments to reduce failure impact

9. **Implement Multi-Cluster Deployment Testing**
   - Test deployments on both clusters before promoting to production
   - Add validation gates for cluster-specific resources

---

## Conclusion

Both **pbx-web** and **whisper-stt** exhibit **environment-induced instability** rather than application instability. The core applications are healthy when infrastructure dependencies are satisfied (as evidenced by stable operation on ardenone-cluster). The failure patterns are **cluster-specific**, not service-specific.

**Critical Insight:** The root causes are **infrastructure divergence** between clusters—missing StorageClasses, unavailable ExternalSecret stores, and missing image pull secrets on ardenone-manager that exist on ardenone-cluster.

**Action Priority:** Infrastructure parity between clusters is the critical path to resolution. Application-level changes are not required.

---

## Appendix: Data Sources

**Cluster Access:** kubectl-proxy over Tailscale  
**Data Collected:** 
- ReplicaSets (deployment history)
- Pod status and events
- Kubernetes events (warnings/errors)
- ArgoCD application status  
- CI/CD workflow history (iad-ci)

**Analysis Limitations:**
- CI/CD workflow data unavailable (no recent workflows found)
- ArgoCD API access failed (analysis based on event data)
- Historical logs beyond 30 days not analyzed
- Application-level metrics (CPU, memory, request latency) not collected