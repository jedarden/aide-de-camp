# pbx-web vs whisper-stt: 30-Day Deployment Comparative Analysis

**Analysis Date:** 2026-07-24  
**Timeframe:** Last 30 days (2024-06-24 to 2024-07-24)  
**Clusters Analyzed:** ardenone-manager, ardenone-hub (timeout issues limited analysis)

## Executive Summary

Both `pbx-web` and `whisper-stt` services exhibit **critical deployment failures** persisting for 6+ days. The services share a common pattern: **infrastructure dependency failures** that prevent pods from reaching ready state. While the specific dependencies differ (image pull secrets vs. storage classes), both are manifestations of missing or misconfigured external infrastructure requirements.

## Cluster Locations

### ardenone-manager
- **pbx-web namespace:** 
  - `pbx-web` deployment (ronaldraygun/pbx-web:1.0.9)
  - `pbx-rebuild-relay` deployment (python:3-slim)
  - `lab-rebuild-relay` deployment (python:3-slim)
  
- **whisper-stt namespace:**
  - `whisper-stt` deployment (ronaldraygun/whisper-stt:1.8.6)
  - `whisper-openai` deployment
  - `utilities/whisper-transcription` deployment (119d old, outside 30-day window)

### ardenone-hub
- Both services deployed but API timeouts prevented detailed analysis
- Expected to mirror ardenone-manager failures

## Common Failure Patterns

### 1. Deployment Timeout Pattern
Both services exhibit identical deployment timeout conditions:

**pbx-web:**
```
Available: False
Progressing: False
Message: Deployment does not have minimum availability. ReplicaSet "pbx-web-5ff68464d" has timed out progressing.
```

**whisper-stt:**
```
Available: False
Progressing: False
Message: Deployment does not have minimum availability. ReplicaSet "whisper-stt-847fd8d7b9" has timed out progressing.
```

**Pattern:** ReplicaSet rollout timeout after 10+ minutes, indicating the deployment controller has given up waiting for pods to become ready.

### 2. Extended Duration of Failures
Both services have been in failed state for **6+ days**:
- **pbx-web:** Pod `pbx-web-5ff68464d-tzwwx` - 6 days 1 hour of ImagePullBackOff
- **whisper-stt:** Pod `whisper-stt-847fd8d7b9-b8rsj` - 6 days 1 hour of Pending state

**Pattern:** Extended-duration failures indicate either:
- Lack of monitoring/alerting
- Inability to automatically remediate
- Orphaned deployments with no active ownership

### 3. ReplicaSet Churn
Both services show multiple ReplicaSet creation attempts in the last 30 days:

**pbx-web:**
- `pbx-web-6d86477cdb` - 2024-06-25 (scaled to 0)
- `pbx-web-754f4cfdf7` - 2024-07-13 (scaled to 0)
- `pbx-web-5ff68464d` - 2024-07-13 (current, 0/1 ready)

**whisper-stt:** (14 ReplicaSets in 30 days)
- Multiple ReplicaSets created every 1-3 days
- All scaled to 0 after failing
- Current: `whisper-stt-847fd8d7b9` (created 2024-07-12, 0/1 ready)

**Pattern:** Deployment controller continuously creates new ReplicaSets when updates occur, but all fail due to the same infrastructure issue.

## Service-Specific Failure Modes

### pbx-web: Image Pull Secret Chain Failure

#### Primary Issue: ImagePullBackOff
**Pod:** `pbx-web-5ff68464d-tzwwx` (created 2024-07-13, age 10d)

**Event Pattern:**
```
Warning FailedToRetrieveImagePullSecret (x40391 over 6d1h): 
  Unable to retrieve some image pull secrets (docker-hub-registry); 
  attempting to pull the image may not succeed.

Normal BackOff (x38680 over 6d1h): 
  Back-off pulling image "ronaldraygun/pbx-web:1.0.9"
```

**Analysis:**
- **40,391+ failed attempts** to retrieve image pull secret over 6 days
- Secret `docker-hub-registry` is **referenced but does not exist** in the namespace
- No image pull secrets exist in `pbx-web` namespace
- Image requires authentication (private Docker Hub repository)

#### Secondary Issue: ExternalSecret Failure Chain
All ExternalSecrets in the namespace are failing:

```
ClusterSecretStore "openbao" is not ready (Ready: False - unable to validate store)

ExternalSecrets:
  - pbx-web-auth: Ready=False - could not get secret data from provider
  - pbx-rebuild-relay: Ready=False - could not get secret data from provider
  - lab-rebuild-relay: Ready=False - could not get secret data from provider
  - garage-pbx-creds: Ready=False - could not get secret data from provider
```

**Impact:**
- **3 relay pods** are in CreateContainerConfigError state:
  - `pbx-rebuild-relay-8596977857-4292b` - 80d old
  - `pbx-rebuild-relay-5d6975d68d-czrdg` - 80d old  
  - `lab-rebuild-relay-79d6d858bb-lpqdb` - 80d old
  
- Error: `Error: secret "pbx-rebuild-relay" not found` (and similar for lab-rebuild-relay)

**Root Cause Chain:**
1. ClusterSecretStore `openbao` is not ready/unable to validate
2. ExternalSecret operator cannot fetch secrets from provider
3. Target secrets (pbx-rebuild-relay, lab-rebuild-relay, etc.) are never created
4. Pods that require these secrets fail at container creation

#### Additional: ClusterIP Allocation Failures
Multiple services showing repeated ClusterIP allocation failures:
```
Warning ClusterIPNotAllocated (every few minutes):
  service/pbx-rebuild-egress: Cluster IP [IPv4]: 10.43.164.28 is not allocated; repairing
  service/lab-rebuild-egress: Cluster IP [IPv4]: 10.43.245.205 is not allocated; repairing
  service/pbx-rebuild-egress: Cluster IP [IPv4]: 10.43.241.249 is not allocated; repairing
```

**Pattern:** Indicates network plugin or IPAM issues, though auto-repair is occurring.

---

### whisper-stt: Storage Class Dependency Failure

#### Primary Issue: PersistentVolumeClaim Pending State
**Pods:**
- `whisper-stt-847fd8d7b9-b8rsj` (created 2024-07-12, age 12d) - Pending
- `whisper-openai-68966786fb-tng29` (created 40d ago) - Pending

**Event Pattern:**
```
Warning FailedScheduling (x1744 over 6d1h): 
  0/1 nodes are available: pod has unbound immediate PersistentVolumeClaims. 
  Preemption is not helpful for scheduling.

Warning ProvisioningFailed (continuous):
  storageclass.storage.k8s.io "longhorn" not found
```

**Analysis:**
- PVCs are stuck in Pending state because storage class "longhorn" does not exist
- Available storage classes on cluster: `local-path` (default), `nfs-synology`
- PVCs reference non-existent storage class: `longhorn`

**Affected PVCs:**
```
NAME                         STATUS    STORAGECLASS   AGE
whisper-model-cache          Pending   longhorn      72d
whisper-openai-model-cache   Pending   longhorn      40d
whisper-stt-jobs             Pending   longhorn      29d
```

**Impact:**
- Pods cannot be scheduled without bound PVCs
- 1,744+ scheduling attempts over 6 days (one every ~15 seconds)
- whisper-stt workload is completely non-functional

#### Root Cause:
Storage class mismatch between deployment configuration and available infrastructure:
- Deployment configuration expects `longhorn` storage class
- Cluster only has `local-path` and `nfs-synology` available
- Longhorn storage provisioning is either not installed or disabled

## Infrastructure Dependencies Summary

| Dependency Type | pbx-web | whisper-stt | Status |
|----------------|----------|-------------|--------|
| Image Pull Secrets | docker-hub-registry (missing) | N/A (public images) | ❌ pbx-web |
| External Secrets | openbao ClusterSecretStore (not ready) | N/A | ❌ pbx-web |
| Storage Class | N/A (no PVCs) | longhorn (does not exist) | ❌ whisper-stt |
| Network Plugin | ClusterIP allocation issues (auto-repairing) | No issues observed | ⚠️ pbx-web |

## Error Frequency Analysis

### pbx-web Error Events (Last 30 Days)
| Error Type | Count | Pattern |
|------------|-------|---------|
| UpdateFailed (ExternalSecret) | 4 | Continuous from openbao failures |
| Failed (pod) | 3 | Secret not found errors |
| FailedToRetrieveImagePullSecret | 1 | 40,391+ occurrences in events |

### whisper-stt Error Events (Last 30 Days)
| Error Type | Count | Pattern |
|------------|-------|---------|
| ProvisioningFailed (PVC) | 3 | Continuous from missing storage class |

## Timeline Analysis

### June 2024
- **2024-06-24:** Both services likely functioning (ReplicaSets from this period)
- **2024-06-25:** New ReplicaSets created for both services

### July 2024
- **2024-07-01 to 2024-07-08:** Multiple whisper-stt ReplicaSets created (deployment churn)
- **2024-07-12:** whisper-stt pod `whisper-stt-847fd8d7b9-b8rsj` created (still Pending)
- **2024-07-13:** pbx-web pod `pbx-web-5ff68464d-tzwwx` created (still ImagePullBackOff)
- **2024-07-24:** Analysis date - both services still failing

**Inference:** Failures began ~2024-07-12/13 and have persisted for 11-12 days without remediation.

## Recommendations

### Immediate Actions (Priority 1)

1. **Fix pbx-web image pull secret:**
   ```bash
   # Create the missing docker-hub-registry secret
   kubectl --server=http://traefik-ardenone-manager:8001 create secret docker-registry docker-hub-registry \
     --docker-server=https://index.docker.io/v1/ \
     --docker-username=<username> \
     --docker-password=<password> \
     --docker-email=<email> \
     -n pbx-web
   ```

2. **Fix or restore openbao ClusterSecretStore:**
   - Verify openbao pod is running: `kubectl get pods -n external-secrets`
   - Check ClusterSecretStore status
   - Validate authentication credentials
   - Restart external-secrets operator if needed

3. **Fix whisper-stt storage class references:**
   - Update PVCs to use `local-path` or `nfs-synology` storage class
   - OR install Longhorn storage provisioner if required
   - Delete and recreate PVCs with correct storage class

### Medium-Term Improvements (Priority 2)

1. **Implement alerting:**
   - Alert on ImagePullBackOff > 5 minutes
   - Alert on PVC Pending > 10 minutes
   - Alert on ExternalSecret failures
   - Alert on deployment availability < 100%

2. **Add pre-flight checks:**
   - Validate image pull secrets exist before deployment
   - Validate storage classes exist before PVC creation
   - Validate ClusterSecretStore readiness before ExternalSecret creation

3. **Infrastructure as Code validation:**
   - Add kubeconform/kubectl-validate checks to CI/CD
   - Validate all dependencies exist before applying manifests

4. **Documentation:**
   - Document required infrastructure dependencies for each service
   - Create runbooks for common failure modes
   - Assign ownership for each deployment

### Long-Term Architectural Changes (Priority 3)

1. **Move to public container registry:**
   - Eliminates image pull secret requirement for pbx-web
   - Reduces operational overhead

2. **Implement multi-cluster storage strategy:**
   - Ensure consistent storage classes across all clusters
   - Consider cloud-native storage options

3. **Automated dependency verification:**
   - OPA/Gatekeeper policies to require secret existence before deployment
   - Admission webhook to validate storage class availability

## Conclusion

Both `pbx-web` and `whisper-stt` are **completely non-functional** due to infrastructure dependency failures that have persisted for **11-12 days**. While the specific failure modes differ (image authentication vs. storage provisioning), both stem from **missing or misconfigured external infrastructure dependencies** that are not validated at deployment time.

The frequency of ReplicaSet creation attempts (14 for whisper-stt in 30 days) and repeated event patterns (40,391+ image pull failures) indicate these failures are **self-perpetuating** - the deployment controller continuously retries but cannot succeed without human intervention to fix the underlying infrastructure gaps.

**Critical Gap:** No automated monitoring or alerting caught these failures, suggesting the need for better operational visibility and automated remediation for infrastructure dependency failures.

---

**Analysis Methodology:**  
- Queried ardenone-manager and ardenone-hub clusters via kubectl-proxy over Tailscale  
- Analyzed pod events, ReplicaSets, deployments, PVCs, and ExternalSecrets  
- Focused on 30-day window from 2024-06-24 to 2024-07-24  
- Cross-referenced error patterns across both services to identify common failure modes

**Data Sources:**
- `kubectl get pods --sort-by=.metadata.creationTimestamp`
- `kubectl get events --sort-by=.lastTimestamp`
- `kubectl get replicasets`
- `kubectl describe pod/deployment`
- `kubectl get pvc/storageclass/externalsecret/clustersecretstore`
