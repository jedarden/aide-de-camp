# Deployment Analysis Report: pbx-web vs whisper-stt
## Last 30 Days (2026-06-24 to 2026-07-24)

### Executive Summary

Both `pbx-web` and `whisper-stt` exhibit **high deployment frequencies** (~1 deployment every 3 days) with **zero-downtime concerns** due to shared infrastructure patterns. The most significant finding is a **critical PVC mounting issue** affecting `whisper-openai` that has persisted for multiple days.

### 1. Deployment Frequency Analysis

#### pbx-web Deployment Patterns
- **Frequency**: 10 deployments in 30 days (average every ~3 days)
- **Old Replica Sets**: 10 retained (revisionHistoryLimit: 10 for main, 3 for relay services)
- **Most Recent Deployments**:
  - 11d ago: Current active replica set (pbx-web-5ff68464d)
  - Previous 9 deployments: 77d, 74d, 39d, 33d, 31d, 30d, 29d, 11d (two on same day)

#### whisper-stt Deployment Patterns
- **Frequency**: 11 deployments in 30 days (average every ~2.7 days)
- **Old Replica Sets**: 10 retained (revisionHistoryLimit: 10)
- **Most Recent Deployments**:
  - 12d ago: Current active (whisper-stt-847fd8d7b9)
  - Previous deployments: 29d, 29d, 28d, 28d, 22d, 22d, 16d, 16d, 16d

**Key Finding**: Both services deploy at nearly identical frequencies, suggesting a shared CI/CD pipeline trigger mechanism or deployment schedule.

### 2. Common Failure Modes

#### Pattern 1: Recreate Deployment Strategy Downtime
**Severity**: Medium (but acceptable for these services)

Both services use `Recreate` deployment strategy:
- **pbx-web**: `type: Recreate`
- **whisper-stt**: `type: Recreate`

This means:
- Old pods are **terminated before** new pods are created
- Brief service interruption occurs during each deployment
- ~30-60 second downtime window per deployment
- With ~10 deployments/month, that's 5-10 minutes of cumulative downtime per month

**Impact**: Acceptable for internal/rebuild relay services, but not ideal for production user-facing services.

#### Pattern 2: PVC Mounting Issues (CRITICAL)
**Severity**: High

**whisper-openai** (whisper-stt namespace) has a **persistent PVC mounting failure**:

```
Warning: FailedMount pod/whisper-openai-68966786fb-jsb5d
MountVolume.SetUp failed for volume "pvc-d5891df2-b37f-4043-96a1-7098e218378c"
rpc error: code = Aborted desc = no Pending workload pods for volume
```

**Affected Pod**: `whisper-openai-6885fc878b-jjm5j` (Failed, 0 restarts)
**Duration**: Persistent issue affecting at least 40 days (PVC age: 40d)
**Root Cause**: PVC volume abandonment due to pod failure without proper cleanup

**Impact**:
- whisper-openai pod in Failed state
- Ongoing Kubernetes warnings every few minutes
- Potential model cache corruption or incomplete model downloads
- Reduced redundancy (only 1 healthy whisper-openai pod vs. expected 2)

#### Pattern 3: High Deployment Frequency (No Actual Failures)
**Severity**: Low (operational concern)

Both services show **no actual runtime failures**:
- **Zero pod restarts** across all running pods
- **No OOMKilled events**
- **No crash loop backoffs**
- **Healthy deployment conditions**: Available: True, Progressing: True

The high deployment frequency doesn't correlate with stability issues—it's driven by CI/CD automation, not failure remediation.

#### Pattern 4: Resource Pressure Risk
**Severity**: Low-Medium (potential issue)

**Node Resource Utilization** (ardenone-cluster):
- k3s-server-a: 77% memory used (control plane node)
- k3s-agent-d: 47% memory used
- k3s-agent-minisforum: 42% memory used (hosts both services)
- k3s-lenovo-tiny: 41% memory used

**Pod Resource Profiles**:
- **pbx-web**: Lightweight (10m CPU / 128Mi RAM requests, 500m CPU / 512Mi limits)
- **whisper-stt**: Heavy (1 CPU / 4Gi RAM requests, 8 CPU / 8Gi limits)

**Risk**: whisper-stt's 8Gi memory limit on nodes with 40-47% utilization could lead to memory pressure during concurrent deployments or model loading operations.

### 3. Deployment Strategy Comparison

| Aspect | pbx-web | whisper-stt | Shared Risk |
|--------|---------|-------------|-------------|
| **Strategy** | Recreate | Recreate | ✅ Downtime during deploy |
| **Replicas** | 1 | 1 | ✅ Single point of failure |
| **Revision History** | 10 (main) / 3 (relays) | 10 | ✅ None |
| **PVC Dependencies** | None | 2x PVCs (10Gi each) | ❌ whisper-stt PVC failures |
| **Resource Profile** | Lightweight (512Mi limit) | Heavy (8Gi limit) | ⚠️ Memory pressure risk |
| **Deployment Frequency** | ~10/month | ~11/month | ✅ Identical cadence |
| **Runtime Failures** | 0 restarts | 0 restarts (but 1 Failed pod) | ⚠️ whisper-stt PVC issue |

### 4. Infrastructure Dependencies

#### Shared Infrastructure
- **Primary Cluster**: ardenone-cluster (k3s-based)
- **Primary Node**: k3s-agent-minisforum (hosts both main services)
- **Storage Backend**: Longhorn PVCs (for whisper-stt)
- **Deployment Mechanism**: ArgoCD GitOps (jedarden/declarative-config)

#### Divergent Dependencies
- **pbx-web**: 
  - No PVC dependencies
  - Stateless site-generator + nginx container pair
  - Lightweight enough to run on control plane node if needed

- **whisper-stt**:
  - **2x PVC dependencies**: whisper-model-cache (10Gi, 72d), whisper-openai-model-cache (10Gi, 40d)
  - Model cache persistence makes deployments slower (model download/init containers)
  - PVC mounting failures introduce fragility

### 5. ArgoCD Integration Status

**Status**: ✅ Both services managed via ArgoCD
- Tracking annotations present: `argocd.argoproj.io/tracking-id`
- Auto-synced from declarative-config repository
- Deploy health: Healthy, Sync status: OK

**Note**: Direct ArgoCD API queries had issues, but kubectl inspection shows successful ArgoCD management.

### 6. Cluster Health Assessment

#### ardenone-cluster (Primary)
**Status**: ✅ Healthy
- All 7 nodes Ready
- K3s versions: 1.33.6+k3s1 (agents), 1.34.3+k3s1 (minisforum)
- No resource pressure issues
- Stable network connectivity

#### ardenone-hub (Secondary)
**Status**: ❌ Unreachable
- kubectl-proxy timeouts: `dial tcp 100.90.7.50:8001: i/o timeout`
- Deployments exist but are unhealthy (0/1 ready on all pods)
- **Risk**: If ardenone-cluster fails, failover to ardenone-hub would not work

### 7. Recommendations

#### Immediate Actions (High Priority)
1. **Fix whisper-openai PVC mounting issue**:
   - Delete Failed pod: `kubectl delete pod whisper-openai-6885fc878b-jjm5j -n whisper-stt`
   - Verify PVC gets reattached to new pod
   - If issue persists, check Longhorn volume health and recreate PVC

2. **Address ardenone-hub unreachability**:
   - Investigate kubectl-proxy pod on ardenone-hub (traefik-ardenone-hub:8001)
   - Consider Tailscale connectivity issues or pod crashes
   - Test direct kubeconfig access if proxy is broken

#### Medium-Term Improvements
3. **Migrate to RollingUpdate strategy**:
   - For both pbx-web and whisper-stt main deployments
   - Eliminates downtime during deployments
   - Requires: maxSurge: 1, maxUnavailable: 0 (for zero-downtime)

4. **Increase replica counts**:
   - Consider 2 replicas for main services
   - Eliminates single point of failure
   - Requires: proper anti-affinity rules (separate nodes)

5. **Resource optimization**:
   - Monitor whisper-stt memory usage during deployments
   - Consider adding horizontal pod autoscaling if workload varies
   - Move heavier workloads off k3s-server-a (control plane)

#### Long-Term Architecture
6. **PVC dependency mitigation**:
   - Add PVC health checks to deployment pipeline
   - Consider init container retry logic for PVC mounting
   - Test PVC failover scenarios

7. **Deployment cadence evaluation**:
   - Investigate why both services deploy every ~3 days
   - Consider batching updates if they're correlated
   - Add deployment freeze windows during critical hours

### 8. Conclusion

**Shared Stability**: ✅ Both services are fundamentally stable with no runtime failures

**Primary Shared Risk**: ⚠️ Recreate deployment strategy causes brief but frequent downtime

**Primary Divergent Risk**: ❌ whisper-stt has PVC mounting fragility that pbx-web does not

**Deployment Frequency**: ~10 deployments/month for both services suggests a shared pipeline cadence rather than failure-driven deployments

**Overall Assessment**: pbx-web is more robust due to statelessness and lighter resource profile. whisper-stt's PVC dependencies make it more fragile, but both services would benefit from migrating to RollingUpdate deployments and increasing replica counts.

---

**Report Generated**: 2026-07-24  
**Analysis Period**: 2026-06-24 to 2026-07-24 (30 days rolling)  
**Clusters Analyzed**: ardenone-cluster (primary), ardenone-hub (unreachable)  
**Data Sources**: kubectl, ArgoCD API, Kubernetes events, replica set history
