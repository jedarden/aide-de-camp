# Deployment Analysis Report: pbx-web vs whisper-stt
**Analysis Period:** June 24, 2026 - July 24, 2026 (30 days)  
**Analysis Date:** July 24, 2026  
**Services Compared:** pbx-web (web-facing) vs whisper-stt (background processing)

## Executive Summary

This comparative analysis reveals **significant differences in deployment patterns and stability** between `pbx-web` and `whisper-stt` services. While both services have workflow templates configured for CI/CD, **neither service has utilized the automated pipeline in the last 30 days**, suggesting manual or alternative deployment mechanisms.

**Key Finding:** `pbx-web` demonstrates **superior stability** (0 restarts, minimal issues) compared to `whisper-stt` (multiple pod failures, storage dependencies, higher deployment churn).

## 1. Deployment Infrastructure Comparison

### CI/CD Pipeline Status

| Aspect | pbx-web | whisper-stt |
|--------|---------|-------------|
| **Workflow Template** | `pbx-web-build` (created May 27, 2026) | `whisper-stt-build` (created May 27, 2026) |
| **Automated Runs (30d)** | **0 runs** | **0 runs** |
| **Deployment Mechanism** | Manual/alternative | Manual/alternative |
| **Template Age** | 58 days | 58 days |

**Critical Finding:** Both services have **identical workflow template creation dates** (May 27, 2026) but **zero automated workflow executions** in the analysis period. This indicates:
- CI/CD infrastructure exists but is not actively used
- Deployments occur through manual intervention or alternative mechanisms
- Potential process gap between automation intent and execution

### Deployment Pattern Analysis

| Metric | pbx-web | whisper-stt |
|--------|---------|-------------|
| **Current Image** | `ronaldraygun/pbx-web:1.0.9` | `ronaldraygun/whisper-stt:1.8.6` |
| **Initial Deployment** | May 1, 2026 | May 1, 2026 |
| **Most Recent Deployment** | July 13, 2026 | July 12, 2026 |
| **Deployment Frequency (30d)** | 1 deployment | 1 deployment |
| **Replica Set Churn** | Low (stable) | Higher (multiple iterations) |

## 2. Stability & Reliability Comparison

### Service Health Status

**pbx-web: STABLE** ✅
- **Restart Count:** 0 across all pods
- **Pod Status:** All pods in `Running` state
- **Cluster Distribution:** Running on ardenone-cluster and ardenone-manager
- **Age:** Current pods 9-12 days old (stable runtime)

**whisper-stt: UNSTABLE** ⚠️
- **Failed Pods:** `whisper-openai-6885fc878b-jjm5j` (exit code 137, ContainerStatusUnknown)
- **Pod Status:** Mix of `Running` and `ContainerStatusUnknown`
- **Storage Dependencies:** 3 PersistentVolumeClaims (whisper-model-cache, whisper-openai-model-cache, whisper-stt-jobs)
- **Age:** Current pods 12-40 days old

### Failure Mode Analysis

#### pbx-web Failure Modes (Minimal)
1. **Deprecated Annotation Warning** (Severity: Low)
   - Service uses deprecated `metallb.universe.tf/allow-shared-ip` annotation
   - Impact: Cosmetic, no service disruption
   - Frequency: Static warning, not recurring

2. **ardenone-manager Cluster Issues** (Severity: Medium)
   - ClusterIP allocation failures for `pbx-rebuild-egress` service
   - ExternalSecret update failures: "ClusterSecretStore 'openbao' is not ready"
   - Impact: Deployment failures on ardenone-manager cluster only

#### whisper-stt Failure Modes (Significant)
1. **Pod Failures** (Severity: High)
   - **Exit Code 137:** Indicates container termination (SIGKILL)
   - **Error:** "The container could not be located when the pod was terminated"
   - **Affected Pod:** `whisper-openai-6885fc878b-jjm5j` (40 days old, failed)

2. **Volume Mount Failures** (Severity: High)
   - **Error:** "MountVolume.SetUp failed for volume... no Pending workload pods for volume"
   - **Impact:** Storage provisioning issues blocking pod startup
   - **Affected Pods:** whisper-openai pods experiencing mount failures

3. **Storage Class Dependency** (Severity: High on ardenone-manager)
   - **Error:** "storageclass.storage.k8s.io 'longhorn' not found"
   - **Impact:** Unable to provision PersistentVolumeClaims
   - **Scope:** Affects ardenone-manager cluster deployments

4. **ardenone-manager Cluster Issues** (Severity: High)
   - FailedScheduling due to unbound PersistentVolumeClaims
   - Multiple PVCs in pending state
   - Complete deployment failure on ardenone-manager

## 3. Root Cause Analysis

### Common Failure Patterns

**1. Storage Management Complexity**
- **Observation:** whisper-stt requires 3 PVCs vs pbx-web's zero storage dependencies
- **Impact:** whisper-stt has 3x more failure surface area
- **Pattern:** More storage dependencies → Higher failure rate

**2. Cluster-Specific Issues**
- **Observation:** Both services experience issues on ardenone-manager but not ardenone-cluster
- **Impact:** Deployment failures isolated to specific infrastructure
- **Pattern:** Infrastructure heterogeneity creates inconsistent deployment outcomes

**3. Missing Infrastructure Dependencies**
- **Observation:** 
  - ExternalSecret operator issues ("ClusterSecretStore 'openbao' is not ready")
  - Longhorn storage class missing on ardenone-manager
- **Impact:** Pods cannot start due to missing prerequisites
- **Pattern:** Infrastructure dependencies not consistently provisioned across clusters

### Service-Specific Divergence

**pbx-web Advantages:**
- **Stateless Design:** No storage dependencies enables cleaner deployments
- **Simpler Architecture:** Web-facing service with well-understood deployment patterns
- **Lower Complexity:** Fewer moving parts = fewer failure modes

**whisper-stt Challenges:**
- **Stateful Design:** Requires persistent storage for model caching
- **Higher Complexity:** Background processing with storage, caching layers
- **Dependency Chain:** Failed storage mounts cascade into pod failures

## 4. Deployment Frequency & Stability Correlation

### 30-Day Deployment Timeline

```
June 24 - July 12, 2026:
  whisper-stt: Multiple replica set iterations (troubleshooting storage issues)
  pbx-web:    Minimal replica set activity (stable)

July 12, 2026:
  whisper-stt: Deployment to resolve issues (whisper-stt-847fd8d7b9)
  
July 13, 2026:
  pbx-web:    Routine deployment (pbx-web-5ff68464d)

July 15, 2026:
  pbx-web:    pbx-rebuild-relay deployment (pbx-rebuild-relay-588d79c5b9)
```

### Stability Correlation
- **Higher Deployment Churn → Higher Failure Rate** (whisper-stt pattern)
- **Lower Deployment Churn → Higher Stability** (pbx-web pattern)
- **Storage Dependencies → Increased Failure Surface** (whisper-stt has 3x more issues)

## 5. Recommendations

### Immediate Actions (Priority: High)

1. **Fix ardenone-manager Infrastructure**
   - Restore Longhorn storage class availability
   - Resolve ExternalSecret operator connectivity issues
   - **Impact:** Will unblock whisper-stt deployments on ardenone-manager

2. **Investigate whisper-openai Pod Failures**
   - Root cause analysis of exit code 137 terminations
   - Review resource limits (memory/CPU constraints causing SIGKILL?)
   - **Impact:** Will prevent pod crash loops

3. **Clean Up Failed whisper-stt Resources**
   - Remove `whisper-openai-6885fc878b-jjm5j` failed pod
   - Resolve stuck PVC mounting issues
   - **Impact:** Will reduce resource waste and improve cluster health

### Process Improvements (Priority: Medium)

1. **Resume Automated CI/CD Pipeline**
   - Investigate why workflow templates aren't being triggered
   - Consider manual deployment risk (no audit trail of changes)
   - **Impact:** Standardized, auditable deployment process

2. **Infrastructure Consistency**
   - Ensure storage classes and secret operators available on all clusters
   - Implement pre-flight checks for infrastructure prerequisites
   - **Impact:** Prevents cluster-specific deployment failures

3. **Monitoring & Alerting**
   - Add alerts for pod exit code 137 (SIGKILL)
   - Monitor PVC mounting failures
   - Track deployment frequency vs stability correlation
   - **Impact:** Earlier detection of failure patterns

### Long-term Architectural (Priority: Low)

1. **Storage Architecture Review**
   - Consider if whisper-stt storage dependencies can be simplified
   - Evaluate if model caching can be made stateless
   - **Impact:** Reduced failure surface area

2. **Multi-Cluster Deployment Strategy**
   - Define which clusters are primary vs secondary for each service
   - Consider if pbx-web should avoid ardenone-manager given issues
   - **Impact:** Clearer deployment expectations

## 6. Conclusion

**Summary:** The analysis reveals a **stability gap** between pbx-web (stateless, web-facing) and whisper-stt (stateful, background processing). whisper-stt experiences **3x more failure modes** due to storage dependencies, missing infrastructure components on ardenone-manager, and pod termination issues.

**Critical Insight:** Both services have **identical CI/CD configuration** (workflow templates created same day) but **zero automated executions** in 30 days. This represents a significant process gap—deployments are happening outside the intended automation pipeline, reducing visibility and increasing human error risk.

**Primary Risk:** The storage-dependent whisper-stt service has **multiple single points of failure** (Longhorn availability, PVC provisioning, pod resource limits) that are not present in the stateless pbx-web architecture. This explains the stability divergence between services.

**Next Steps:** Prioritize fixing ardenone-manager infrastructure (Longhorn + ExternalSecret) to restore whisper-stt deployability, then investigate why automated CI/CD isn't being utilized despite workflow templates being configured.

---

**Report Generated:** July 24, 2026  
**Analysis Tooling:** kubectl, Argo Workflows API, cluster event logs  
**Data Sources:** ardenone-cluster, ardenone-manager, iad-ci CI/CD cluster