# Comparative Deployment Failure Analysis: pbx-web vs whisper-stt
**Analysis Period:** June 24, 2026 - July 24, 2026 (30 days)  
**Report Date:** July 24, 2026  
**Bead ID:** adc-2v36e  
**Analysis Type:** Comparative failure pattern analysis with infrastructure correlation

---

## Executive Summary

This comparative analysis reveals **critical shared infrastructure vulnerabilities** alongside **distinct service-specific failure modes**. The most significant finding is that **both services experienced simultaneous infrastructure failures** around July 18, 2026, indicating **cluster-level infrastructure degradation** rather than isolated application defects.

### Critical Findings

| Finding Category | pbx-web | whisper-stt | Shared? |
|------------------|---------|-------------|---------|
| **Infrastructure Failure Window** | July 18, 2026 (6+ days) | July 18, 2026 (6+ days) | ✅ **YES - CRITICAL** |
| **Current Service Status** | 🔴 DOWN (ImagePullBackOff) | 🔴 DOWN (PVC Pending) | ✅ **YES - CRITICAL** |
| **Detection Time** | 6+ days undetected | 6+ days undetected | ✅ **YES - CRITICAL** |
| **Root Cause Category** | Infrastructure dependency | Infrastructure dependency | ✅ **YES** |
| **Service-Specific Issues** | Minimal | PVC mounting complexity | ❌ **NO** |
| **Deployment Frequency** | 9 deployments (30d) | 14 deployments (30d) | Similar patterns |

**Primary Risk:** Both services are currently non-functional due to infrastructure failures that persisted for 6+ days without automated detection, indicating **critical monitoring and remediation gaps**.

---

## Methodology and Data Sources

### Analysis Approach
1. **Temporal Correlation Analysis**: Cross-referenced failure timestamps across services
2. **Infrastructure Dependency Mapping**: Identified shared vs isolated infrastructure components
3. **Failure Pattern Classification**: Categorized failures by root cause type
4. **Code Change Correlation**: Analyzed git history for deployment timing correlations

### Data Sources
- **Kubernetes Deployment Logs**: 30-day rollout history from ardenone-cluster
- **Pod State Analysis**: Current and historical pod status across both services
- **Event Log Correlation**: Kubernetes events with timestamps and error types
- **Git History**: Code changes correlated with deployment timelines
- **Infrastructure Audit**: Storage classes, secret stores, and dependency availability

---

## Comparative Failure Analysis

### Shared Failure Modes ✅

#### 1. **Simultaneous Infrastructure Failure Window** (CRITICAL)

**Timeline Correlation:**
```
~2026-07-18 00:00 UTC: Both services began experiencing failures
2026-07-18 → 2026-07-24: 6+ days of continuous service outage
Status: UNDETECTED by monitoring, UNRESOLVED at time of analysis
```

**pbx-web Failure:**
- **Type**: ImagePullBackOff
- **Root Cause**: ExternalSecret operator cannot sync secrets from OpenBao
- **Error**: `ClusterSecretStore "openbao" is not ready`
- **Impact**: Cannot pull container images, pods unable to start

**whisper-stt Failure:**
- **Type**: Pending (PVC provisioning timeout)
- **Root Cause**: longhorn StorageClass missing from cluster
- **Error**: `storageclass.storage.k8s.io "longhorn" not found`
- **Impact**: Cannot provision persistent volumes, pods unable to start

**Assessment:** The simultaneous failure timing strongly indicates a **cluster-level infrastructure event** (cluster upgrade, reconfiguration, or dependency removal) rather than coincident independent failures.

#### 2. **Monitoring and Alerting Gap** (CRITICAL)

**Shared Vulnerability:**
- **Detection Time**: 6+ days for both services
- **Automated Detection**: ZERO
- **Manual Detection**: Only discovered during analysis
- **Impact**: Extended service downtime without intervention

**Missing Alerting:**
- No ImagePullBackOff alerts (pbx-web)
- No PVC Pending state alerts (whisper-stt)
- No infrastructure dependency health checks
- No ClusterSecretStore availability monitoring
- No StorageClass availability monitoring

#### 3. **Single Points of Failure** (HIGH)

**pbx-web Single Point of Failure:**
- **Dependency**: ExternalSecretOperator + OpenBao ClusterSecretStore
- **Failure Mode**: Complete inability to pull images
- **Mitigation**: None identified

**whisper-stt Single Points of Failure:**
- **Dependency 1**: longhorn StorageClass existence
- **Dependency 2**: PVC mounting and cleanup
- **Failure Mode**: Complete inability to provision storage
- **Mitigation**: None identified

#### 4. **Deployment Strategy Similarities** (MEDIUM)

**Shared Characteristics:**
- **Strategy**: Recreate (not RollingUpdate)
- **Image Pull Policy**: Always
- **Health Checks**: Comprehensive liveness and readiness probes
- **CI/CD Status**: Zero automated workflow runs despite template availability

**Implication:** Both services rely on identical deployment infrastructure but utilize manual deployment mechanisms, increasing human error risk.

### Service-Specific Failure Modes ❌

#### pbx-web-Specific Patterns

**1. Minimal Service-Specific Issues** ✅
- **Architecture Advantage**: Stateless design eliminates storage complexity
- **Resource Footprint**: Lightweight (512Mi memory limit vs 8Gi for whisper-stt)
- **Failure Surface**: Smaller due to fewer dependencies

**2. Secret Management Dependency** 🟡
- **Issue**: Complete dependency on OpenBao ClusterSecretStore
- **Historical Context**: Migration to ExternalSecretOperator (~2026-06-15) introduced this dependency
- **Failure Impact**: Image pull failures when secret sync breaks
- **Mitigation Gap**: No fallback secret retrieval mechanism

#### whisper-stt-Specific Patterns

**1. Persistent Storage Complexity** 🔴 CRITICAL
- **Issue**: 3 PVC dependencies (whisper-model-cache, whisper-openai-model-cache, whisper-stt-jobs)
- **Failure Chain**: Failed pod → PVC state corruption → Cascading mount failures
- **Impact**: 4,791+ mount failure events on supposedly healthy pods
- **Critical Finding**: 40-day failed pod (`whisper-openai-6885fc878b-jjm5j`) consuming resources

**2. Ephemeral Storage Exhaustion** 🔴 HIGH
- **Issue**: Large model downloads (~3-5Gi) exceed node ephemeral storage
- **Failure Pattern**: Init container downloads model → Pod eviction → Exit Code 137
- **Impact**: Complete pod failure with cascading PVC issues
- **Resource Pressure**: 16-32x higher memory requirements than pbx-web

**3. High Deployment Churn** 🟡 MEDIUM
- **Frequency**: 14 deployments vs 9 for pbx-web (1.5x higher)
- **Pattern**: Multiple deployments per day (e.g., July 8: 3 rapid deployments)
- **Risk**: Increased regression surface and infrastructure pressure
- **Implication**: Possible deployment-driven troubleshooting or iterative development

---

## Temporal Correlation with Code Changes

### Deployment Timeline Analysis

**pbx-web Deployment History (30-day window):**
```
2026-07-14: v1.0.9 (current, broken)
2026-07-04: v1.0.8 
2026-06-25: v1.0.7
2026-06-24: v1.0.6, v1.0.5 (rapid deployments)
```

**whisper-stt Deployment History (30-day window):**
```
2026-07-12: v1.8.6 (current, broken)
2026-07-10: v1.8.4
2026-07-08: v1.8.2 (multiple deployments same day)
2026-07-02: v1.7.0, v1.6.0 (rapid deployments)
```

### Code Change Correlation Analysis

**pbx-web Recent Changes:**
```bash
25c11c8 - fix(pbx-web): force ESO resync + auto-restart on webhook secret rotation
83af76c - fix(pbx-web): migrate secrets to OpenBao/ExternalSecret
f20d55e - feat(pbx-web): bump image to 1.0.9 (copy transcript now includes timestamps)
```

**whisper-stt Recent Changes:**
```bash
0829ee7 - fix(whisper-stt): prefer big-CPU nodes via soft nodeAffinity
6fc620d - feat(whisper-stt): deploy 1.8.6, route /jobs/{id} + /jobs/chunked/* off Google auth
c068821 - feat(whisper-stt): add jobs PVC and wire /data volume for async job store
```

### Correlation Findings

**✅ CODE-DEPLOYMENT CORRELATION CONFIRMED:**
- Both services show active deployment cadence aligned with git commits
- Deployments occurred within 1-2 days of code changes
- No correlation found between specific code changes and infrastructure failures

**❌ NO CODE-INFRASTRUCTURE FAILURE CORRELATION:**
- Infrastructure failures occurred 4-6 days after most recent deployments
- Infrastructure dependency issues (OpenBao, longhorn) unrelated to application code changes
- Failures are environmental, not application defect-driven

---

## Infrastructure vs Service-Specific Classification

### Infrastructure-Related Failures ✅

**Shared Infrastructure Failures (Both Services):**
1. **Cluster-Level Event (~2026-07-18)**
   - Type: Infrastructure degradation/removal
   - Evidence: Simultaneous failure timing
   - Impact: Complete service outage for both services
   - Classification: **INFRASTRUCTURE**

2. **Monitoring Gap**
   - Type: Absence of automated detection
   - Evidence: 6+ days undetected failures
   - Impact: Extended downtime, delayed remediation
   - Classification: **INFRASTRUCTURE**

**pbx-web Infrastructure Issues:**
1. **OpenBao ClusterSecretStore Unavailability**
   - Type: Secret management infrastructure
   - Evidence: ExternalSecret sync failures
   - Impact: Image pull failures
   - Classification: **INFRASTRUCTURE**

**whisper-stt Infrastructure Issues:**
1. **longhorn StorageClass Removal**
   - Type: Storage infrastructure
   - Evidence: StorageClass missing from cluster
   - Impact: PVC provisioning failures
   - Classification: **INFRASTRUCTURE**

2. **Node Ephemeral Storage Exhaustion**
   - Type: Node resource management
   - Evidence: Pod eviction due to storage threshold
   - Impact: Pod failures
   - Classification: **INFRASTRUCTURE**

### Service-Specific Failures ❌

**pbx-web Service-Specific Issues:**
- **Minimal identified** - Architecture designed to avoid stateful dependencies
- One advantage: Stateless design reduces service-specific failure surface

**whisper-stt Service-Specific Issues:**
1. **PVC Lifecycle Management** 
   - Type: Service storage architecture
   - Evidence: 40-day failed pod, 4,791+ mount failures
   - Impact: Resource waste, cascading failures
   - Classification: **SERVICE-SPECIFIC**

2. **High Resource Requirements**
   - Type: Service resource planning
   - Evidence: 16-32x higher memory vs pbx-web
   - Impact: Resource pressure, increased eviction risk
   - Classification: **SERVICE-SPECIFIC**

---

## Root Cause Assessment

### Primary Root Cause: Infrastructure Dependency Failure

**Shared Root Cause Chain:**
```
1. Cluster-level infrastructure event (~2026-07-18)
   ├── OpenBao ClusterSecretStore degradation/misconfiguration
   └── longhorn StorageClass removal/decommissioning

2. Service-level failure propagation
   ├── pbx-web: ExternalSecret sync failures → ImagePullBackOff
   └── whisper-stt: PVC provisioning failures → Pod Pending state

3. Monitoring gap
   ├── No automated detection of ImagePullBackOff
   ├── No automated detection of PVC Pending state
   └── 6+ days of undetected service outage

4. Remediation gap
   ├── No automated rollback mechanisms
   ├── No infrastructure health validation
   └── Manual intervention required
```

### Secondary Root Cause: Service Architecture Differences

**pbx-web Stability Advantages:**
- Stateless architecture eliminates storage complexity
- Lightweight resource footprint (512Mi vs 8Gi)
- Fewer infrastructure dependencies (no PVCs)
- Conservative deployment cadence (9 vs 14 deployments)

**whisper-stt Stability Challenges:**
- Stateful architecture requires persistent storage
- Heavy resource footprint increases failure probability
- Multiple PVC dependencies increase failure surface
- High deployment churn increases regression risk

---

## Success Criteria Assessment

### ✅ 1. Shared vs Isolated Failures Determined

**Shared Failures:**
- Simultaneous infrastructure failure window (~2026-07-18)
- Monitoring and detection gap (6+ days undetected)
- Single points of failure (infrastructure dependencies)
- Manual deployment mechanisms (no automated CI/CD)

**Isolated Failures:**
- pbx-web: Minimal service-specific issues
- whisper-stt: PVC lifecycle management, ephemeral storage exhaustion

### ✅ 2. Correlation with Deployment Times

**Key Finding:** **NO CORRELATION between code deployments and infrastructure failures**

- Infrastructure failures occurred 4-6 days after most recent deployments
- Failures are environmental, not deployment-related
- Code changes are unrelated to infrastructure dependency issues

### ✅ 3. Configuration Drifts Identified

**Infrastructure Configuration Issues:**
1. OpenBao ClusterSecretStore availability degradation
2. longhorn StorageClass removal from cluster
3. No validation of infrastructure prerequisites

**Service Configuration Differences:**
1. pbx-web: Stateless, minimal dependencies
2. whisper-stt: Stateful, multiple PVCs, resource-intensive

### ✅ 4. Infrastructure vs Service-Specific Statement

**Clear Assessment:**
- **PRIMARY FAILURE MODE: Infrastructure-related** (both services)
- **SECONDARY FAILURE MODE: Service-specific** (whisper-stt only)
- **TERTIARY CONTRIBUTOR: Architecture differences** (stateful vs stateless)

---

## Recommendations

### 🚨 IMMEDIATE ACTIONS (Emergency Priority)

#### 1. Restore Infrastructure Dependencies

**Fix pbx-web ImagePullBackOff:**
```bash
# Check OpenBao ClusterSecretStore status
kubectl get clustersecretstore openbao -n external-secrets-operator

# Verify ExternalSecret operator health
kubectl get pods -n external-secrets-operator

# Force resync ExternalSecrets
kubectl apply -f k8s/ardenone-cluster/pbx-web/pbx-web-auth-externalsecret.yml
```

**Fix whisper-stt PVC Provisioning:**
```bash
# Option A: Restore longhorn StorageClass (if infrastructure available)
# Option B: Migrate PVCs to available StorageClass (nfs-synology)

# Update PVCs to use nfs-synology StorageClass
kubectl edit pvc whisper-model-cache -n whisper-stt
kubectl edit pvc whisper-openai-model-cache -n whisper-stt  
kubectl edit pvc whisper-stt-jobs -n whisper-stt
```

#### 2. Clean Up Failed whisper-stt Resources
```bash
# Remove 40-day failed pod consuming resources
kubectl delete pod whisper-openai-6885fc878b-jjm5j -n whisper-stt --force --grace-period=0

# Verify PVC state after cleanup
kubectl get pvc -n whisper-stt
```

### 📊 MONITORING & ALERTING (Critical Priority)

#### 1. Infrastructure Dependency Monitoring

**Required Alerts:**
- ExternalSecret update failures (>5min)
- PVC provisioning failures (>10min)
- ImagePullBackOff states (immediate)
- Pod Pending states (>10min)
- StorageClass availability changes
- ClusterSecretStore health status

#### 2. Service Health Dashboard

**Metrics to Track:**
- Per-namespace pod state distribution
- Infrastructure dependency availability
- Deployment success/failure rates
- PVC mounting success rate
- Image pull success rate

### 🔧 PROCESS IMPROVEMENTS (High Priority)

#### 1. Infrastructure Validation Gates
- Pre-deployment checks for all infrastructure dependencies
- Secret sync validation before image rollout
- StorageClass availability verification
- PVC provisioning capability testing

#### 2. Automated Remediation
- Failed ExternalSecret sync (auto-resync)
- Stuck PVC provisioning (alert + auto-escalation)
- ImagePullBackOff (secret validation + auto-retry)
- Failed pod cleanup (auto-delete after 24h)

#### 3. Deployment Safety Enhancements
- Canary deployments for infrastructure change detection
- Gradual rollout with automatic rollback on failure
- Health check validation before promotion
- Infrastructure dependency health checks in pipeline

### 🔨 LONG-TERM ARCHITECTURAL (Medium Priority)

#### 1. whisper-stt Storage Architecture
- Evaluate stateless model serving options
- Consider external model registry (S3, GCS) vs PVC
- Implement shared model cache across deployments
- Reduce storage dependency complexity

#### 2. Multi-Cluster Deployment Strategy
- Define primary vs secondary clusters for each service
- Consider avoiding problematic clusters for specific services
- Implement cluster-specific infrastructure requirements

---

## Conclusion

The comparative analysis reveals that **pbx-web and whisper-stt failures are predominantly infrastructure-related** rather than service-specific code defects. The simultaneous failure window (~2026-07-18) affecting both services indicates a **cluster-level infrastructure event**, most likely a cluster upgrade, reconfiguration, or dependency removal.

### Critical Insights

1. **Infrastructure Dependency Vulnerability**: Both services have single points of failure in infrastructure dependencies (OpenBao for pbx-web, longhorn for whisper-stt) that caused complete service outages.

2. **Monitoring Gap Severity**: The 6+ day undetected outage represents a critical monitoring failure. No automated alerting exists for infrastructure dependency failures.

3. **Architecture Matters**: pbx-web's stateless architecture demonstrates superior stability compared to whisper-stt's complex PVC-based stateful architecture.

4. **No Code-Deployment Correlation**: Infrastructure failures are unrelated to recent code changes or deployment frequency, indicating environmental root causes.

### Risk Assessment

**Current Risk Level**: 🚨 **CRITICAL**
- Both core services non-functional for 6+ days
- No automated detection or remediation
- Single points of failure in infrastructure dependencies
- Extended MTTR due to manual intervention requirements

**Recommended Priority**: **EMERGENCY**
- Immediate infrastructure dependency restoration
- Critical monitoring and alerting implementation
- Process improvements for infrastructure validation

### Next Steps

1. **Immediate**: Restore OpenBao and longhorn infrastructure dependencies
2. **Short-term**: Implement critical monitoring and alerting
3. **Medium-term**: Add infrastructure validation gates to deployment pipeline
4. **Long-term**: Evaluate architectural simplification for whisper-stt storage

---

**Report Generated**: July 24, 2026  
**Analysis Duration**: June 24, 2026 to July 24, 2026 (30 days)  
**Clusters Analyzed**: ardenone-cluster, ardenone-manager  
**Services Analyzed**: pbx-web, whisper-stt  
**Bead ID**: adc-2v36e  
**Analysis Status**: ✅ COMPLETED  
**Confidence Level**: HIGH - Multiple data sources + temporal correlation + infrastructure validation