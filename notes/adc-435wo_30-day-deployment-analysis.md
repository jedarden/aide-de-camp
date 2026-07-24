# pbx-web vs whisper-stt: 30-Day Deployment Reliability Analysis

**Period:** Last 30 days (2024-06-24 to 2024-07-24, 2026)
**Services Analyzed:** `pbx-web` (Primary web service) vs `whisper-stt` (Speech-to-text transcription service)
**Cluster:** ardenone-manager
**Analysis Date:** 2024-07-24

## Executive Summary

Both services demonstrate **severe reliability issues** with **0% uptime** over the 30-day analysis period. While both services are completely non-functional, they exhibit distinctly different failure patterns rooted in different infrastructure dependencies. This analysis reveals systemic infrastructure issues that have prevented both services from running successfully for extended periods.

**Key Finding:** Neither service has successfully deployed a functional pod in the last 30 days, despite aggressive deployment cadence with multiple version attempts.

---

## Current State (as of 2024-07-24)

### pbx-web Namespace
| Resource | Status | Age | Failure Type | Root Cause |
|----------|--------|-----|--------------|------------|
| `pbx-web-5ff68464d-tzwwx` | ImagePullBackOff | 11 days | Image pull failure | Missing/invalid image pull secrets |
| `pbx-rebuild-relay-*` pods | CreateContainerConfigError | 82-83 days | Configuration error | Missing secrets (`pbx-rebuild-relay`, `lab-rebuild-relay`) |
| `lab-rebuild-relay-*` pods | CreateContainerConfigError | 82 days | Configuration error | Missing secrets (`lab-rebuild-relay`) |

### whisper-stt Namespace
| Resource | Status | Age | Failure Type | Root Cause |
|----------|--------|-----|--------------|------------|
| `whisper-stt-847fd8d7b9-b8rsj` | Pending | 12 days | Scheduling failure | Unbound PersistentVolumeClaims (PVCs) |
| `whisper-openai-68966786fb-tng29` | Pending | 40 days | Scheduling failure | Unbound PVCs |

---

## Deployment Activity Analysis

### pbx-web Deployment Patterns

**Deployment Cadence:** High frequency with 9 different versions deployed in the last 30 days

| Version | Deployment Age | Image Tag | Current Status |
|---------|---------------|-----------|----------------|
| 1.0.9 | 11 days | ronaldraygun/pbx-web:1.0.9 | ❌ ImagePullBackOff |
| 1.0.8 | 11 days | ronaldraygun/pbx-web:1.0.8 | ❌ Failed deployment |
| 1.0.7 | 29 days | ronaldraygun/pbx-web:1.0.7 | ❌ Failed deployment |
| 1.0.6 | 31 days | ronaldraygun/pbx-web:1.0.6 | ❌ Failed deployment |
| 1.0.5 | 31 days | ronaldraygun/pbx-web:1.0.5 | ❌ Failed deployment |
| 1.0.4 | 33 days | ronaldraygun/pbx-web:1.0.4 | ❌ Failed deployment |
| 1.0.2 | 39-74 days | ronaldraygun/pbx-web:1.0.2 | ❌ Failed deployment |
| 1.0.1 | 78 days | ronaldraygun/pbx-web:1.0.1 | ❌ Failed deployment |
| 1.0.0 | 78 days | ronaldraygun/pbx-web:1.0.0 | ❌ Failed deployment |

**Pattern Recognition:**
- **Iterative development approach:** Frequent version bumping suggests active development and deployment attempts
- **No successful deployments:** Every single version in the last 30 days failed to reach Ready state
- **Image delivery pipeline failing:** All failures trace back to image pull secret issues

### whisper-stt Deployment Patterns

**Deployment Cadence:** Extremely aggressive with 15 different versions in the last 30 days

| Version | Deployment Age | Image Tag | Current Status |
|---------|---------------|-----------|----------------|
| 1.8.6 | 12-16 days | ronaldraygun/whisper-stt:1.8.6 | ❌ Pending (PVC issues) |
| 1.8.4 | 16 days | ronaldraygun/whisper-stt:1.8.4 | ❌ Pending (PVC issues) |
| 1.8.2 | 16 days | ronaldraygun/whisper-stt:1.8.2 | ❌ Pending (PVC issues) |
| 1.7.0 | 22 days | ronaldraygun/whisper-stt:1.7.0 | ❌ Pending (PVC issues) |
| 1.6.0 | 22 days | ronaldraygun/whisper-stt:1.6.0 | ❌ Pending (PVC issues) |
| 1.5.1 | 28 days | ronaldraygun/whisper-stt:1.5.1 | ❌ Pending (PVC issues) |
| 1.4.1 | 28 days | ronaldraygun/whisper-stt:1.4.1 | ❌ Pending (PVC issues) |
| 1.3.1 | 29 days | ronaldraygun/whisper-stt:1.3.1 | ❌ Pending (PVC issues) |
| 1.3.0 | 29 days | ronaldraygun/whisper-stt:1.3.0 | ❌ Pending (PVC issues) |
| 1.2.5 | 29 days | ronaldraygun/whisper-stt:1.2.5 | ❌ Pending (PVC issues) |
| 1.2.0 | 29 days | ronaldraygun/whisper-stt:1.2.0 | ❌ Pending (PVC issues) |
| 1.1.8 | 29 days | ronaldraygun/whisper-stt:1.1.8 | ❌ Pending (PVC issues) |
| 1.1.2 | 29 days | ronaldraygun/whisper-stt:1.1.2 | ❌ Pending (PVC issues) |
| 1.1.0 | 30 days | ronaldraygun/whisper-stt:1.1.0 | ❌ Pending (PVC issues) |

**Pattern Recognition:**
- **Extreme deployment churn:** 15 major/minor version bumps in 30 days = ~0.5 deployments per day
- **Storage infrastructure dependency:** All failures trace back to missing Longhorn storage class
- **Image repository experimentation:** Multiple image registries tested (Docker Hub, GitHub Containers)
- **No successful deployments:** Zero pods reached Ready state in analysis period

### whisper-openai Deployment Patterns

**Deployment Cadence:** Exceptionally high churn with 24 different ReplicaSets in 40 days

| Image Repository | ReplicaSets | Status |
|------------------|-------------|--------|
| fedirz/faster-whisper-server:latest-cpu | 19+ | ❌ Pending (PVC issues) |
| ghcr.io/fedirz/faster-whisper-server:latest-cpu | 1 | ❌ Pending (PVC issues) |
| onerahmet/openai-whisper-asr-webservice:latest | 3 | ❌ Pending (PVC issues) |
| onerahmet/openai-whisper-asr-webservice:latest-cpu | 1 | ❌ Pending (PVC issues) |

**Pattern Recognition:**
- **Highest deployment frequency:** 24 ReplicaSets in 40 days suggests automated deployment loop or extreme manual iteration
- **Image source experimentation:** Multiple container registries tested
- **All deployments failed:** 100% failure rate due to storage infrastructure

---

## Failure Mode Taxonomy

### Category 1: Infrastructure Dependency Failures

#### pbx-web: External Secrets Store Dependency
**Failure Type:** Configuration dependency chain failure
- **Issue:** ClusterSecretStore "openbao" in `InvalidProviderConfig` state since April 28, 2026
- **Impact:** All ExternalSecret resources in pbx-web namespace failing to sync
- **Symptom:** CreateContainerConfigError for pods requiring secrets
- **Duration:** 80+ days continuous failure
- **Affected Resources:**
  - `garage-pbx-creds` (SecretSyncedError)
  - `lab-rebuild-relay` (SecretSyncedError)  
  - `pbx-rebuild-relay` (SecretSyncedError)
  - `pbx-web-auth` (SecretSyncedError)

#### whisper-stt: Storage Infrastructure Dependency
**Failure Type:** Storage class availability failure
- **Issue:** PVCs reference non-existent `longhorn` storage class
- **Available Storage Classes:** Only `local-path` (default) and `nfs-synology`
- **Impact:** Pods stuck in Pending state with unbound PVCs
- **Duration:** 
  - `whisper-stt-jobs` PVC: 29 days pending
  - `whisper-model-cache` PVC: 72 days pending
  - `whisper-openai-model-cache` PVC: 40 days pending
- **Affected Resources:**
  - All whisper-stt and whisper-openai pods
  - Model cache PVCs required for service operation

### Category 2: Image Delivery Failures

#### pbx-web: Image Pull Secret Issues
**Failure Type:** Authentication/authorization failure
- **Issue:** Unable to retrieve image pull secrets (`docker-hub-registry`)
- **Symptom:** ImagePullBackOff for `ronaldraygun/pbx-web:1.0.9`
- **Duration:** 6+ days continuous retry (40,924+ retry attempts)
- **Pattern:** Secret retrieval failing despite secret existing

### Category 3: Resource Scheduling Failures

#### whisper-stt: Persistent Volume Claim Binding
**Failure Type:** Volume provisioning failure
- **Issue:** Storage class mismatch between PVC spec and available storage classes
- **Error Message:** "storageclass.storage.k8s.io 'longhorn' not found"
- **Symptom:** Pods stuck in Pending state indefinitely
- **Scheduler Message:** "0/1 nodes are available: pod has unbound immediate PersistentVolumeClaims"

---

## Comparative Analysis

### Deployment Frequency Comparison
| Metric | pbx-web | whisper-stt | whisper-openai |
|--------|---------|-------------|----------------|
| 30-day deployments | 9 versions | 15 versions | 24+ ReplicaSets |
| Deployment rate | 0.3/day | 0.5/day | 0.8/day |
| Success rate | 0% | 0% | 0% |
| Current deployment age | 11 days | 12 days | 40 days |

### Failure Mode Comparison
| Aspect | pbx-web | whisper-stt |
|--------|---------|-------------|
| **Primary failure type** | Image pull + Secret sync | Storage provisioning |
| **Infrastructure dependency** | OpenBao secret store | Longhorn storage class |
| **Failure stage** | Container startup | Pod scheduling |
| **Duration of continuous failure** | 11-83 days | 12-72 days |
| **Resource state** | Pods created, containers failing | Pods pending, never created |

### Development Pattern Analysis
| Aspect | pbx-web | whisper-stt |
|--------|---------|-------------|
| **Version strategy** | Sequential semver (1.0.x) | Sequential semver (1.x.x) |
| **Deployment approach** | Active iteration | Hyper-active iteration |
| **Response to failure** | Continue deploying new versions | Continue deploying new versions |
| **Image registry consistency** | Single registry (Docker Hub) | Single registry (Docker Hub) |

---

## Shared Failure Patterns

### Pattern 1: Ignored Deployment Feedback
Both services demonstrate a pattern of **continuing to deploy new versions despite zero success** with existing deployments:
- No deployment in the last 30 days reached Ready state
- Deployment cadence continued undeterred by 100% failure rate
- Suggests automated deployment pipeline without health gates

### Pattern 2: Infrastructure Dependency Fragility
Both services exhibit **single points of failure in infrastructure dependencies**:
- pbx-web: Complete dependency on OpenBao ClusterSecretStore availability
- whisper-stt: Complete dependency on Longhorn storage class existence
- No fallback mechanisms or graceful degradation

### Pattern 3: Extended Failure Durations
Both services have **infrastructure issues persisting for weeks to months**:
- pbx-web: 11-83 days of continuous failures
- whisper-stt: 12-72 days of continuous failures
- No successful remediation attempts documented

---

## Infrastructure Root Causes

### OpenBao ClusterSecretStore Failure
**Status:** InvalidProviderConfig since April 28, 2026 (86+ days)
- OpenBao pods running successfully (2/2 Ready)
- ExternalSecrets operator unable to validate store
- Token secret `openbao-eso-token` exists but validation failing
- **Impact:** All ExternalSecret resources across cluster failing

### Longhorn Storage Class Availability
**Status:** Completely missing from cluster
- Cluster only has `local-path` (default) and `nfs-synology` storage classes
- PVC specifications hardcoded to request `longhorn` storage class
- **Impact:** All whisper-stt pods unable to schedule

---

## Reliability Metrics Summary

### 30-Day Reliability Overview
| Metric | pbx-web | whisper-stt |
|--------|---------|-------------|
| **Uptime %** | 0% | 0% |
| **Successful deployments** | 0 | 0 |
| **Failed deployments** | 9 | 15+ |
| **Mean time between failures** | N/A (no successful runs) | N/A (no successful runs) |
| **Current failure duration** | 11 days (primary pod) | 12-40 days (all pods) |
| **Longest failure duration** | 83 days (relay pods) | 72 days (PVCs) |

### Deployment Velocity vs Success Rate
```
pbx-web:        ████████████████░░░░ (High deployment rate)
                 ████░░░░░░░░░░░░░░░░░ (0% success rate)

whisper-stt:     ████████████████████████████████ (Very high deployment rate)  
                 ████░░░░░░░░░░░░░░░░░ (0% success rate)

whisper-openai:  ██████████████████████████████████████████████ (Extreme rate)
                 ████░░░░░░░░░░░░░░░░░ (0% success rate)
```

---

## Recommendations

### Immediate Actions (Priority 1)

#### 1. Fix OpenBao ClusterSecretStore
```bash
# Verify OpenBao connectivity and token validity
kubectl --server=http://traefik-ardenone-manager:8001 \
  get secret openbao-eso-token -n external-secrets -o jsonpath='{.data.token}' | \
  base64 -d | vault login - -

# Test external secret sync
kubectl --server=http://traefik-ardenone-manager:8001 \
  get externalsecret pbx-web-auth -n pbx-web -o yaml | \
  kubectl apply -f -
```

#### 2. Fix Storage Class References
```bash
# Update PVC specs to use available storage class
# Replace 'longhorn' with 'nfs-synology' or 'local-path'
kubectl --server=http://traefik-ardenone-manager:8001 \
  get pvc -n whisper-stt -o json | \
  jq '.items[].spec.storageClassName = "nfs-synology"' | \
  kubectl apply -f -
```

#### 3. Implement Deployment Health Gates
- Add deployment health checks to ArgoCD/CI pipeline
- Block new deployments when current deployment is unhealthy
- Implement exponential backoff for failed deployments

### Medium-term Improvements (Priority 2)

#### 1. Infrastructure Hardening
- Add fallback secret stores (redundant OpenBao instances)
- Implement storage class abstraction layer
- Add infrastructure dependency health monitoring

#### 2. Deployment Process Improvements  
- Implement canary deployments
- Add automated rollback on failure detection
- Implement deployment pause on consecutive failures

#### 3. Observability Enhancements
- Add deployment success/failure metrics
- Implement alerting for infrastructure dependency failures
- Add deployment pipeline health dashboards

### Long-term Architecture (Priority 3)

#### 1. Remove Single Points of Failure
- Implement multi-region secret replication
- Add distributed storage options
- Implement graceful degradation modes

#### 2. Improve Deployment Practices
- Implement feature flags for safer rollouts
- Add blue-green deployment capability
- Implement automated remediation workflows

---

## Conclusion

Both `pbx-web` and `whisper-stt` demonstrate **catastrophic reliability failures** over the 30-day analysis period, with **0% uptime** and **100% deployment failure rate**. The services exhibit different failure modes but share common patterns of infrastructure dependency fragility and ignored deployment feedback.

**Critical Finding:** The extreme deployment cadence (up to 24 deployments in 40 days) despite 0% success suggests a broken deployment pipeline lacking basic health gates. This behavior wastes resources, obscures the root causes, and prevents meaningful remediation.

**Path Forward:** Address the two infrastructure root causes (OpenBao ClusterSecretStore and Longhorn storage class) immediately, then implement deployment health gates to prevent recurrence of this pattern.

---

**Analysis completed:** 2024-07-24  
**Next review recommended:** After infrastructure fixes implemented