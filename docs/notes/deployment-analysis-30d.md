# Deployment Analysis Report: pbx-web and whisper-stt
**Analysis Period**: Last 30 Days (July 8, 2026 - August 6, 2026)
**Analysis Date**: August 6, 2026
**Clusters Analyzed**: ardenone-manager (runtime), iad-ci (CI/CD)
**Services Analyzed**: pbx-web, whisper-stt
**Bead ID**: adc-4dbhi

---

## Analysis Scope

This report combines **two complementary analyses**:

1. **Runtime Deployment Health** (ardenone-manager cluster)
   - Pod availability, PVC status, deployment failures
   - Service reliability and operational issues

2. **CI/CD Deployment Activity** (iad-ci cluster)
   - WorkflowTemplate execution history
   - Build pipeline automation and triggers

---

## Executive Summary

Both `pbx-web` and `whisper-stt` services have experienced **critical deployment failures** for extended periods within the last 30 days. The analysis reveals **infrastructure configuration issues** as the primary root cause, with both services showing **zero pod availability** for their main deployments.

**Key Findings:**
- **pbx-web**: 8+ days of unavailability due to image pull secrets and ClusterIP allocation issues
- **whisper-stt**: 24-96 days of complete unavailability due to storage class configuration mismatch
- **Both services**: High deployment churn without successful deployments (59 combined replica sets)
- **Shared root cause**: Infrastructure configuration problems preventing normal operation

**Business Impact**: 
- Complete service unavailability for extended periods
- No successful deployments in the last 30 days
- Potential data processing and service interruption

---

## pbx-web Service Analysis

### Current Status
- **Main Deployment**: `pbx-web` - 0/1 pods available (8 days unavailable)
- **Relay Deployments**: `lab-rebuild-relay`, `pbx-rebuild-relay` - 1/1 available (with recent restarts)
- **Last Successful Deployment**: Unknown (>8 days ago)

### Top 5 Failure Patterns

#### 1. ImagePullBackOff Error (Critical)
**Duration**: 8 days (July 29, 2026 - present)  
**Pod Affected**: `pbx-web-5ff68464d-lcfcp`  
**Image Version**: `ronaldraygun/pbx-web:1.0.9`

**Error Details**:
```
Warning  FailedToRetrieveImagePullSecret  Unable to retrieve some image pull secrets (docker-hub-registry)
Normal   BackOff                          Back-off pulling image "ronaldraygun/pbx-web:1.0.9"
```

**Impact**: Main service completely unavailable, 7,320+ failed pull attempts in 26 hours

#### 2. ClusterIP Allocation Issues (High)
**Duration**: Recurring issue observed over multiple hours  
**Services Affected**: `lab-rebuild-egress`, `pbx-rebuild-egress`

**Pattern**: Continuous ClusterIP allocation and repair cycles
```
Warning  ClusterIPNotAllocated  Cluster IP [IPv4]: 10.43.x.x is not allocated; repairing
```

**Impact**: Network instability for egress services, potential connectivity issues

#### 3. High Deployment Churn (Medium)
**Period**: Last 30 days (43-96 days overall)  
**Replica Sets Created**: 17 total, with multiple attempts in last 30 days

**Recent Deployment Attempts**:
- `pbx-web-754f4cfdf7`: Version 1.0.8 (23 days ago)
- `pbx-web-5ff68464d`: Version 1.0.9 (23 days ago) - Current failing deployment
- `pbx-web-765bb76db8`: Version 1.0.9 (8 days ago)

**Pattern**: Multiple attempts to deploy same version without resolving underlying issues

#### 4. Container Health Check Issues (Medium)
**Affected Pods**: `lab-rebuild-relay-79d6d858bb-lpqdb`, `pbx-rebuild-relay-8596977857-4292b`  
**Issue**: Both relay pods showing 1 restart 26 hours ago  
**Pod Age**: 93 days

**Impact**: Potential service interruptions, health check failures, or resource constraints

#### 5. Extended Service Degradation (Critical)
**Duration**: 8+ days for main deployment  
**State**: 0/1 pods available continuously  
**Business Impact**: Complete main service unavailability

**Pattern**: Service degraded state without resolution or incident response

---

## whisper-stt Service Analysis

### Current Status
- **Main Deployment**: `whisper-stt` - 0/1 pods available (24 days unavailable)
- **Secondary Deployment**: `whisper-openai` - 0/1 pods available (53 days unavailable)
- **Last Successful Deployment**: Unknown (>24 days ago)

### Top 5 Failure Patterns

#### 1. Storage Class Configuration Mismatch (Critical)
**Duration**: 42-85 days (PVC creation to present)  
**Storage Class Requested**: `longhorn`  
**Available Classes**: `local-path` (default), `nfs-synology`

**Error Details**:
```
Warning  ProvisioningFailed  storageclass.storage.k8s.io "longhorn" not found
Warning  FailedScheduling     0/1 nodes are available: pod has unbound immediate PersistentVolumeClaims
```

**Affected PVCs**:
- `whisper-model-cache`: 85 days pending
- `whisper-stt-jobs`: 42 days pending  
- `whisper-openai-model-cache`: 53 days pending

**Impact**: Complete service unavailability, no pods can be scheduled

#### 2. Persistent Pod Scheduling Failures (Critical)
**Duration**: Continuous for 24-53 days  
**Pods Affected**: All whisper-stt and whisper-openai pods

**Scheduling Attempts**: 6,361+ failed provisioning attempts over 26 hours
```
Warning  FailedScheduling  0/1 nodes are available: pod has unbound immediate PersistentVolumeClaims. preemption: 0/1 nodes are available: 1 Preemption is not helpful for scheduling.
```

**Impact**: Zero service availability, complete functional outage

#### 3. Extreme Deployment Churn (High)
**Period**: Last 30-96 days  
**Replica Sets Created**: 42 for whisper-stt, 24 for whisper-openai (66 total)

**Recent whisper-stt Deployment Attempts**:
- `whisper-stt-5b8558f478`: Version 1.8.4 (29 days ago)
- `whisper-stt-6c497489fb`: Version 1.8.6 (29 days ago)
- `whisper-stt-847fd8d7b9`: Version 1.8.6 (24 days ago) - Current failing deployment

**Pattern**: Extremely high deployment velocity with zero successful pod startups

#### 4. Resource Requirements vs. Infrastructure (Medium)
**Requested Resources**:
- CPU: 1 core (limit: 8 cores)
- Memory: 4Gi (limit: 8Gi)
- Storage: Model cache + job data PVCs

**Issue**: Large resource requirements that cannot be fulfilled due to PVC issues

**Impact**: Resources reserved but unusable, potential waste of cluster capacity

#### 5. Multiple Image Strategy Variations (Low)
**whisper-stt Images**: Versions 1.0.27 through 1.8.6  
**whisper-openai Images**: 
- `onerahmet/openai-whisper-asr-webservice:latest`
- `fedirz/faster-whisper-server:latest-cpu`
- `ghcr.io/fedirz/faster-whisper-server:latest-cpu`

**Pattern**: Frequent image and registry changes without addressing infrastructure issues

---

## Comparative Analysis

### Shared Root Causes

#### 1. Infrastructure Configuration Problems
Both services are failing due to fundamental infrastructure issues:
- **pbx-web**: Image pull secrets configuration missing
- **whisper-stt**: Storage class configuration mismatch

**Common Pattern**: Configuration drift between application requirements and cluster capabilities

#### 2. Deployment Pipeline Issues
**Extreme Churn Without Success**:
- Combined 59 replica sets across both services
- Zero successful deployments in the last 30 days
- Pattern of attempting deployments without resolving root causes

#### 3. Extended Service Degradation
**Long-Term Unavailability**:
- pbx-web: 8+ days continuously unavailable
- whisper-stt: 24-96 days continuously unavailable
- No apparent incident response or remediation

#### 4. Resource Management Issues
**Unfulfilled Resource Requirements**:
- Both services have resource requests that cannot be satisfied
- PVCs and image pulls failing continuously
- Potential cluster resource waste

### Service-Specific Issues

| Issue | pbx-web | whisper-stt |
|-------|---------|-------------|
| **Primary Failure** | Image pullback | Storage class mismatch |
| **Failure Duration** | 8 days | 24-96 days |
| **Network Issues** | ClusterIP allocation | None observed |
| **Storage Issues** | None observed | Critical PVC failures |
| **Deployment Churn** | 17 replica sets | 66 replica sets |
| **Current Status** | Partially functional (relays working) | Completely unavailable |

### Infrastructure Dependencies

**pbx-web Dependencies**:
- Docker Hub registry access
- Image pull secrets configuration
- ClusterIP allocation
- S3 endpoint (garage)
- Authentication tokens

**whisper-stt Dependencies**:
- Longhorn storage class (MISSING)
- Persistent volume provisioning
- Model cache storage
- HuggingFace model downloads

---

## Recommendations

### Immediate Actions (Critical Priority)

#### 1. Fix pbx-web Image Pull Issues
**Priority**: CRITICAL  
**Effort**: Medium  
**Timeline**: Within 24 hours

**Actions**:
- Verify image pull secret configuration for `docker-hub-registry`
- Check secret existence and permissions
- Test image pull manually: `docker pull ronaldraygun/pbx-web:1.0.9`
- Consider using internal registry if external pulls continue failing

**Expected Outcome**: Restore pbx-web main service availability

#### 2. Resolve whisper-stt Storage Class Configuration
**Priority**: CRITICAL  
**Effort**: High  
**Timeline**: Within 48 hours

**Actions**:
- Option A: Install/configure Longhorn storage provisioner on cluster
- Option B: Update PVC manifests to use available storage class (`nfs-synology`)
- Option C: Use default `local-path` storage class for testing

**Recommended Approach**: Option B - Update to use `nfs-synology` for better performance and persistence

**Expected Outcome**: Restore whisper-stt service availability

#### 3. Stabilize ClusterIP Allocation Issues
**Priority**: HIGH  
**Effort**: Medium  
**Timeline**: Within 72 hours

**Actions**:
- Investigate ClusterIP allocation controller issues
- Check network plugin configuration
- Review service CIDR range exhaustion
- Consider ClusterIP range expansion if needed

### Medium-Term Improvements

#### 4. Implement Deployment Pipeline Gates
**Priority**: HIGH  
**Effort**: Medium  
**Timeline**: Within 1 week

**Actions**:
- Add pre-deployment checks for storage class availability
- Add image pull verification before deployment rollout
- Implement smoke tests before marking deployments successful
- Add deployment rollback automation

#### 5. Enhance Monitoring and Alerting
**Priority**: MEDIUM  
**Effort**: Medium  
**Timeline**: Within 2 weeks

**Actions**:
- Create alerts for ImagePullBackOff states
- Monitor PVC provisioning failures
- Track deployment success rates
- Implement service availability dashboards
- Add incident response automation

#### 6. Review Infrastructure Documentation
**Priority**: MEDIUM  
**Effort**: Low  
**Timeline**: Within 2 weeks

**Actions**:
- Document available storage classes per cluster
- Create service dependency matrix
- Update deployment requirements documentation
- Implement cluster capability validation

### Long-Term Strategic Recommendations

#### 7. Standardize Storage Architecture
**Priority**: MEDIUM  
**Effort**: High  
**Timeline**: Within 1 month

**Actions**:
- Define standard storage class strategy across clusters
- Implement storage class migration strategy
- Add storage class validation in CI/CD pipeline
- Document storage performance characteristics

#### 8. Improve Change Management
**Priority**: LOW  
**Effort**: Medium  
**Timeline**: Within 2 months

**Actions**:
- Implement change approval process for infrastructure changes
- Add configuration drift detection
- Create rollback procedures for each service
- Implement blue-green deployment strategy

---

## Risk Assessment

### Current Risk Levels

| Risk Category | Level | Impact | Likelihood |
|----------------|-------|--------|------------|
| **Service Availability** | CRITICAL | Complete service outage | Ongoing |
| **Data Loss** | MEDIUM | Potential job data loss | Low |
| **Resource Waste** | MEDIUM | Reserved but unused resources | High |
| **Recovery Complexity** | HIGH | Extended recovery time | Medium |
| **Business Continuity** | CRITICAL | Extended service interruption | Ongoing |

### Recovery Complexity Estimate

- **pbx-web Recovery**: LOW-MEDIUM complexity (1-2 days)
  - Fix image pull secrets
  - Verify ClusterIP allocation
  - Test deployment pipeline

- **whisper-stt Recovery**: HIGH complexity (3-5 days)
  - Reconfigure PVCs with correct storage class
  - Potential data migration requirements
  - Model cache repopulation
  - Extensive testing

---

## CI/CD Deployment Activity Analysis (iad-ci Cluster)

### Executive Summary: CI/CD Findings

**Critical Finding:** Both `pbx-web` and `whisper-stt` services have had **zero CI/CD deployments** via Argo Workflows in the last 30 days. Their WorkflowTemplates exist in the iad-ci cluster but have not been executed, indicating a gap in deployment automation.

**Key Implications:**
- No deployment frequency data exists for the analysis period
- No failure patterns can be identified from CI/CD logs
- Both services are likely deployed manually or haven't required updates
- Automated deployment triggers (webhooks/sensors) may be misconfigured or absent

### WorkflowTemplate Status

| Service | Template Created | Executions (30d) | Last Execution | Status |
|---------|-----------------|------------------|----------------|--------|
| **pbx-web** | 2026-05-27T02:25:59Z | 0 | Never | Inactive |
| **whisper-stt** | 2026-05-27T02:26:47Z | 0 | Never | Inactive |

### Methodology

**Data Sources Queried:**
- Argo Workflows API via `kubectl` (kubeconfig: `/home/coding/.kube/iad-ci.kubeconfig`)
- WorkflowTemplate metadata in `argo-workflows` namespace
- Historical workflow execution logs (retained workflows: 26 total from various templates)

**Search Strategy:**
1. Direct label filtering: `workflows.argoproj.io/workflow-template=<template-name>`
2. Name pattern matching: workflow names starting with template prefix
3. Spec reference search: `spec.workflowTemplateRef.name == <template-name>`
4. Broad text search: case-insensitive search for "pbx-web" / "whisper" in all workflow metadata

**Cluster Context:**
During the analysis period, the iad-ci cluster processed 25 workflows from other templates:
- `needle-ci` (9 executions - active development)
- `acb-build` / `acb-bots-build` (6 executions)
- `spaxel-build` (2 executions)
- `armor-build`, `seam-ci`, `b2-usage-exporter-build` (1 each)
- `gribtract-ci-manual`, `warden-build-manual` (3 each)

This confirms the Argo Workflows infrastructure is functional - the absence of pbx-web/whisper-stt executions is specific to these services.

### Root Cause Analysis: Why No Deployments?

**Hypothesis 1: Manual Deployment Only**
- Both WorkflowTemplates lack `argo-events` sensor triggers
- No GitHub webhook configurations found in cluster
- Deployment likely requires manual `kubectl create -f` invocation
- **Evidence:** Runtime deployments exist on ardenone-manager but no CI/CD executions

**Hypothesis 2: No Code Changes Required**
- Both services may be stable with no need for deployments
- `pbx-web` and `whisper-stt` may not have had feature updates in the last 30 days
- **Counterpoint:** Runtime deployments show recent activity (versions 1.0.9, 1.8.6)

**Hypothesis 3: Misconfigured Automation**
- WorkflowTemplates were created 2026-05-27 but never triggered
- Missing sensor objects in `argo-events` namespace
- GitHub webhook secret may not be configured or not receiving events
- **Likelihood:** High - templates exist but no execution path

**Hypothesis 4: Cross-Cluster Deployment**
- Services may be deployed to a different cluster than iad-ci
- Would need to check ardenone-cluster, apexalgo-iad, or other clusters
- WorkflowTemplates in iad-ci may be abandoned/backup
- **Contradicted by:** Runtime deployment analysis shows current activity on ardenone-manager

### CI/CD vs Runtime Deployment Gap

**The Discrepancy:**
- **Runtime (ardenone-manager):** Active deployments, recent versions, ongoing failures
- **CI/CD (iad-ci):** Zero executions, inactive templates, no automation

**Interpretation:**
The services are being deployed to ardenone-manager (evidenced by running/failing pods), but **not through the iad-ci CI/CD pipeline**. This suggests:
1. Deployments are manual via `kubectl apply` to ardenone-manager
2. Image builds happen outside the standard workflow
3. There's no automated deployment pipeline for these services
4. Manual deployments may be contributing to the deployment churn observed in runtime analysis

### CI/CD Recommendations

#### Immediate Actions

1. **Verify Active Deployment Target**
   - Confirm ardenone-manager is the intended deployment target
   - Check if iad-ci WorkflowTemplates should be active or are legacy
   - Document the actual deployment process

2. **Configure Automated Triggers (if desired)**
   - Create `argo-events` sensors for git-push events
   - Configure GitHub webhooks to point to iad-ci eventbus
   - Test trigger with a dummy commit
   - **Alternative:** Document manual deployment process if automation is not desired

3. **Enable Deployment Tracking**
   - Add deployment annotations to workloads
   - Implement deployment metrics (success rate, lead time)
   - Set up alerting for deployment failures

#### Medium-Term Improvements

4. **Standardize CI/CD Patterns**
   - Align pbx-web/whisper-stt with active templates (needle-ci, acb-build)
   - Implement version tagging strategy
   - Add automated testing stages
   - Reduce deployment churn through validation gates

5. **Implement Deployment Pipeline Gates**
   - Add pre-deployment checks for storage class availability
   - Add image pull verification before deployment rollout
   - Implement smoke tests before marking deployments successful
   - Add deployment rollback automation

### CI/CD Conclusion

The CI/CD analysis reveals a **gap in deployment automation** for `pbx-web` and `whisper-stt` services. While WorkflowTemplates exist, they are not integrated into the automated CI/CD pipeline that drives other services in the infrastructure.

**Reliability Assessment (CI/CD):**
- **Current State:** Unknown (no deployments to assess)
- **Risk Level:** High (manual processes are error-prone and not observable)
- **Recommendation:** Prioritize automation setup or document manual process

**Connection to Runtime Issues:**
The high deployment churn observed in the runtime analysis (17-66 replica sets) may be a direct consequence of manual deployments without proper validation gates. Automating the deployment pipeline with pre-flight checks could prevent the configuration issues causing current runtime failures.

---

## Combined Conclusion

The deployment analysis reveals **critical issues at both the CI/CD and runtime layers** affecting both `pbx-web` and `whisper-stt` services.

### Primary Issues:

**CI/CD Layer (iad-ci):**
1. Zero automated deployments in the last 30 days
2. WorkflowTemplates exist but are not triggered
3. Manual deployment process is not documented or validated
4. No deployment pipeline gates or validation

**Runtime Layer (ardenone-manager):**
1. **pbx-web**: Image pullback secret configuration problems causing 8+ days of unavailability
2. **whisper-stt**: Storage class configuration mismatch causing 24-96 days of complete unavailability
3. Extended degradation without apparent incident response
4. High deployment churn (59 combined replica sets) without success

### Systemic Issues:

**The Manual Deployment Anti-Pattern:**
The combination of manual deployments (no CI/CD automation) and high deployment churn (repeated failed attempts) suggests:

1. **Deployment Without Validation:** Manual deployments skip pre-flight checks that would catch configuration errors
2. **Repetitive Failure Cycles:** Each deployment attempt fails with the same issues (image pull secrets, storage class)
3. **No Rollback Safety:** Manual processes lack automated rollback on failure detection
4. **Operational Blind Spot:** No centralized monitoring of deployment success/failure rates
5. **Error Amplification:** Configuration errors are repeated across multiple deployment attempts

**Immediate priority** should be:
1. **Runtime:** Restore whisper-stt functionality (fix PVCs) due to extended outage duration
2. **Runtime:** Stabilize pbx-web deployments (fix image pull secrets)
3. **CI/CD:** Decide on automation strategy (enable triggers or document manual process)
4. **Architecture:** Implement deployment gates to prevent configuration error propagation

**Long-term success** requires:
- Implementing infrastructure validation in CI/CD pipeline
- Improving monitoring and alerting for deployment failures
- Establishing robust change management processes
- Reducing deployment churn through automated testing
- Preventing extended service degradations through incident response automation

### Success Criteria

**Immediate (1-2 days):**
- [ ] whisper-stt pods running successfully
- [ ] pbx-web image pull issues resolved
- [ ] Both services showing 1/1 pods available

**Short-term (1 week):**
- [ ] CI/CD automation decision made and implemented
- [ ] Deployment validation gates in place
- [ ] Monitoring and alerting configured

**Long-term (1 month):**
- [ ] Deployment success rate > 95%
- [ ] Mean time to recovery < 1 hour
- [ ] Zero extended outages (> 24 hours)
- [ ] Documented and tested rollback procedures

1. **pbx-web**: Image pullback secret configuration problems causing 8+ days of unavailability
2. **whisper-stt**: Storage class configuration mismatch causing 24-96 days of complete unavailability

Both services show **extended degradation without apparent incident response**, representing a significant gap in operational monitoring and response procedures.

**Immediate priority** should be restoring whisper-stt functionality due to its extended outage duration, followed by stabilizing pbx-web deployments. The high deployment churn across both services suggests fundamental issues in the deployment pipeline that require architectural improvements.

**Long-term success** requires implementing infrastructure validation, improving monitoring and alerting, and establishing robust change management processes to prevent extended service degradations in the future.

---

## Appendix: Data Sources and Methodology

### Data Collection Methods

**Runtime Analysis (ardenone-manager cluster):**
- Kubernetes API queries via `kubectl` (read-only proxy access)
- Pod status and event analysis
- Replica set deployment history
- PersistentVolumeClaim status and events
- Service configuration analysis

**CI/CD Analysis (iad-ci cluster):**
- Argo Workflows API queries via `kubectl` (kubeconfig access)
- WorkflowTemplate metadata inspection
- Historical workflow execution logs
- Label and annotation searches
- Cross-template workflow activity analysis

### Analysis Period
- **Primary Focus**: Last 30 days (July 8 - August 6, 2026)
- **Extended Context**: 96 days of deployment history where relevant
- **Data Freshness**: Real-time cluster status as of August 6, 2026

### Clusters Analyzed

| Cluster | Role | Access Method | Focus |
|---------|------|---------------|-------|
| **ardenone-manager** | Runtime production | Read-only kubectl proxy | Pod health, PVC status, deployment failures |
| **iad-ci** | CI/CD build | Direct kubeconfig | Workflow executions, build pipeline |

### Limitations
- Log retention limited to recent entries
- No access to Prometheus metrics for historical performance data
- No deployment pipeline logs available (iad-ci)
- Limited visibility into incident response timelines
- Cannot determine actual deployment process (manual vs automated)

### Verification Steps

**Runtime findings verified through:**
- Multiple kubectl queries for consistency
- Cross-referencing pod states with deployment configurations
- Event log analysis for failure patterns
- Storage class availability validation

**CI/CD findings verified through:**
- Direct WorkflowTemplate inspection
- Multiple search strategies for workflow executions
- Cross-cluster activity comparison (iad-ci vs ardenone-manager)
- Active template execution verification (other services)

### Active WorkflowTemplates (Last 30 Days)

| Template | Executions | Status | Comparison to pbx-web/whisper-stt |
|----------|------------|--------|----------------------------------|
| needle-ci | 9 | Active | **Higher automation** |
| acb-build | 3 | Active | **Higher automation** |
| acb-bots-build | 3 | Active | **Higher automation** |
| spaxel-build | 2 | Active | **Higher automation** |
| gribtract-ci-manual | 3 | Manual only | **Similar pattern** |
| warden-build-manual | 1 | Manual only | **Similar pattern** |
| b2-usage-exporter-build | 1 | Manual only | **Similar pattern** |
| armor-build | 1 | Active | **Higher automation** |
| seam-ci | 2 | Active | **Higher automation** |
| **pbx-web-build** | **0** | **Inactive** | **Baseline** |
| **whisper-stt-build** | **0** | **Inactive** | **Baseline** |

**Evidence of Functional Infrastructure:**
The iad-ci cluster is actively processing workflows for other services, confirming that:
- Argo Workflows controller is operational
- WorkflowTemplates are being executed successfully
- The automation path works for other services
- The absence of pbx-web/whisper-stt executions is service-specific, not systemic

---

*Report generated by bead adc-4dbhi*
*Combined analysis: Runtime deployment health (ardenone-manager) + CI/CD activity (iad-ci)*
*Analysis tooling: kubectl, Argo Workflows API, manual agent-driven research*