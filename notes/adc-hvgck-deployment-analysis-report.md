# Comparative Deployment Analysis: pbx-web vs whisper-stt
**Last 30 Days (June 24 - July 24, 2026)**

## Executive Summary

This report analyzes deployment patterns and failure modes between `pbx-web` and `whisper-stt` services deployed on `ardenone-cluster`. Over the 30-day analysis period, **whisper-stt exhibited 3.7× higher deployment velocity** (11 deployments vs 3) and **3× more rapid deployment incidents** compared to pbx-web, indicating significantly different development and operational patterns.

### Key Findings
- **whisper-stt**: 11 deployments, 3 hotfix cascades (rapid fixes within 1 hour), active development pattern
- **pbx-web**: 3 deployments, 1 rapid deployment incident, stable mature service pattern
- **Both services** use Recreate deployment strategy, causing brief downtime during deployments
- **whisper-stt carries higher operational risk** due to resource intensity, PVC dependencies, and complex model loading

---

## Methodology

Data was collected from the `ardenone-cluster` Kubernetes cluster using:
- ReplicaSet history (last 30 days)
- Deployment configurations and strategies
- Kubernetes events and pod states
- Service characteristics (resources, storage, probes)

**Time Window**: June 24, 2026 - July 24, 2026 (rolling 30-day period)

---

## Deployment Pattern Analysis

### Deployment Velocity

| Metric | pbx-web | whisper-stt | Ratio |
|--------|---------|-------------|-------|
| Total deployments | 3 | 11 | **3.7×** |
| Deployment frequency | 1 per 10 days | 1 per 2.7 days | **3.7×** |
| Rapid deployments (<1hr apart) | 1 | 3 | **3×** |
| Current revision | 12 | 32 | 2.7× |

### pbx-web Deployment Timeline
```
2026-06-25  15:23:48  →  v1.0.7
2026-07-13  18:07:55  →  v1.0.8  (abandoned 10 min later)
2026-07-13  18:18:07  →  v1.0.9  (current)
```

**Pattern**: Stable, infrequent releases with one hotfix cascade (1.0.8 → 1.0.9 in 10.2 minutes).

### whisper-stt Deployment Timeline
```
2026-06-24  20:55:36  →  v1.2.5
2026-06-25  14:08:07  →  v1.3.0  →  v1.3.1 (2.1 min later)
2026-06-26  12:42:03  →  v1.4.1  →  v1.5.1 (4 hr later)
2026-07-01  19:46:33  →  v1.6.0
2026-07-02  02:20:33  →  v1.7.0
2026-07-08  03:09:35  →  v1.8.2  →  v1.8.4 (6.6 min)  →  v1.8.6 (10.5 min)
2026-07-12  16:53:42  →  v1.8.6  (current)
```

**Pattern**: Active development with frequent hotfix cascades, particularly on June 25 and July 8.

### Deployment Strategy Comparison

| Aspect | pbx-web | whisper-stt |
|--------|---------|-------------|
| **Strategy** | Recreate | Recreate |
| **Downtime** | Yes (pod termination before creation) | Yes |
| **Rollback capability** | Yes (via previous ReplicaSets) | Yes |
| **Zero-downtime** | No | No |

**Impact**: Both services experience brief service interruptions during deployments as the Recreate strategy terminates all pods before creating new ones.

---

## Service Characteristics

### pbx-web
```
Architecture:     Multi-container (site-generator + nginx sidecar)
Image:            ronaldraygun/pbx-web:1.0.9
Resource limits:  500m CPU, 512Mi RAM
Resource request: 10m CPU, 128Mi RAM
Storage:          EmptyDir (ephemeral, in-memory cache)
External deps:    Garage S3, authentication secrets
Probes:           Liveness (10s delay), Readiness (5s delay)
```

### whisper-stt
```
Architecture:     Single-container (Whisper STT service)
Image:            ronaldraygun/whisper-stt:1.8.6
Resource limits:  8 CPU, 8Gi RAM
Resource request: 1 CPU, 4Gi RAM
Storage:          PVCs (model-cache, jobs-data persistent)
External deps:    Hugging Face models, PVCs
Node affinity:    Prefers minisforum (weight 100), lenovo-tiny (90)
Probes:           Liveness (120s delay), Readiness (60s delay)
```

---

## Failure Pattern Analysis

### Shared Failure Modes (Both Services)

#### 1. Image Pull Failures
- **Configuration**: Both use `imagePullPolicy: Always`
- **Risk**: Docker Hub rate limiting, registry downtime, missing image tags
- **Mitigation**: Current - Pulls fresh images every restart; Could use `IfNotPresent` for stability

#### 2. Recreate Strategy Downtime
- **Configuration**: Both use `Recreate` (not `RollingUpdate`)
- **Risk**: Brief service interruption during every deployment
- **Impact**: All traffic drops until new pod passes readiness probes
- **Evidence**: No pod overlap observed during deployments
- **Mitigation**: Consider `RollingUpdate` if application supports zero-downtime deployments

#### 3. Secret/Config Dependencies
- **pbx-web secrets**: `garage-pbx-creds`, `pbx-web-auth`
- **whisper-stt secrets**: `whisper-stt-secret`
- **Risk**: Secret rotation failures, missing keys, misconfiguration
- **Mitigation**: Both use Stakater Reloader for automatic secret-based reloads

#### 4. HTTP Probe Timeout Failures
- **Configuration**: Both use HTTP health check probes (1-5s timeouts)
- **Risk**: Application hangs, deadlocks, slow initialization
- **Mitigation**: Configured with `failureThreshold: 3` before restart

### pbx-web Unique Failure Modes

#### 1. Multi-Container Coordination
- **Risk**: One container fails while other succeeds
- **Evidence**: Pod shows `2/2` Ready status (both containers required)
- **Failure scenario**: nginx passes readiness but site-generator fails

#### 2. EmptyDir Memory Exhaustion
- **Configuration**: `nginx-cache` (16Mi memory-backed), `nginx-run` (8Mi)
- **Risk**: Cache overflow under high load → OOM killed
- **Mitigation**: Size limits prevent unbounded growth

#### 3. Sidecar Startup Race Condition
- **Configuration**: nginx (3s readiness delay) vs site-generator (5s)
- **Risk**: nginx probes before content is generated by site-generator
- **Evidence**: Delay stagger mitigates this (nginx waits 3s, generator 5s)

#### 4. S3/Garage Dependency
- **Configuration**: Stores recordings in Garage S3-compatible storage
- **Risk**: Garage service downtime, network issues
- **Mitigation**: None currently; could add Garage connectivity checks

### whisper-stt Unique Failure Modes

#### 1. High Resource Pressure ⚠️
- **Configuration**: 8 CPU, 8Gi RAM limits (4Gi requested)
- **Risk**: Node saturation, CPU throttling, OOM kills
- **Evidence**: 120s liveness delay suggests slow initialization due to resource contention
- **Mitigation**: Consider resource quotas or cluster autoscaling

#### 2. PVC Mount Failures ⚠️
- **Configuration**: Two PVCs - `model-cache`, `jobs-data`
- **Risk**: Volume provisioning delays, mount timeouts, storage backend issues
- **Evidence**: FailedMount event observed for `whisper-openai` deployment (same namespace):
  ```
  MountVolume.SetUp failed for volume "pvc-d5891df2-b37f-4043-96a1-7098e218378c":
  rpc error: code = Aborted desc = no Pending workload pods for volume
  ```
- **Mitigation**: Add PVC health monitoring and alerting

#### 3. Node Affinity Constraints
- **Configuration**: Prefers specific nodes (minisforum, lenovo-tiny)
- **Risk**: Preferred nodes unavailable → longer scheduling delays, suboptimal placement
- **Evidence**: Weighted affinity (100, 90) is soft requirement but adds scheduling complexity
- **Mitigation**: Monitor node availability and pod scheduling times

#### 4. Model Download Latency ⚠️
- **Configuration**: Hugging Face `distil-large-v3` model cached in PVC
- **Risk**: Model not in cache → multi-minute download during startup
- **Evidence**: 60s readiness delay, 120s liveness delay (very high!)
- **Failure scenario**: Cache cleared → new pod downloads model → probes timeout → restart loop
- **Mitigation**: Ensure PVC model-cache is persistent and pre-warmed

#### 5. Large Startup Time
- **Configuration**: 120s initialDelaySeconds for liveness probe
- **Risk**: Application genuinely slow (model loading) vs stuck (deadlock)
- **Evidence**: Unusually long liveness delay compared to pbx-web (10s)
- **Mitigation**: Consider startup probes (alpha feature) for better slow-startup handling

---

## Risk Assessment

### Higher Risk: whisper-stt

| Risk Factor | Severity | Evidence |
|-------------|----------|----------|
| Resource exhaustion | **High** | 8 CPU / 8Gi RAM limits can saturate nodes |
| PVC mount failures | **High** | FailedMount events observed in namespace |
| Model loading complexity | **Medium** | 120s startup delay suggests initialization issues |
| High deployment velocity | **Medium** | 11 deployments = 11× failure opportunities |
| Node affinity constraints | **Low** | Soft affinity, but adds scheduling complexity |

### Lower Risk: pbx-web

| Risk Factor | Severity | Evidence |
|-------------|----------|----------|
| Multi-container coordination | **Low** | Both containers healthy (2/2 Ready) |
| EmptyDir memory limits | **Low** | Size limits prevent overflow |
| S3/Garage dependency | **Low** | No failures observed |
| Stable deployment cadence | **Positive** | 3 deployments = fewer failure opportunities |

---

## Recommendations

### For whisper-stt (High Priority)

1. **Add Resource Alerts** 🚨
   - Monitor CPU/memory usage approaching 80% of limits
   - Alert on OOMKilled events or throttling
   - Consider vertical pod autoscaling for production

2. **PVC Health Monitoring** 🚨
   - Alert on FailedMount events immediately
   - Monitor PVC capacity and health
   - Implement pre-flight checks for volume availability

3. **Optimize Model Loading** 🔧
   - Investigate reducing 120s startup delay (is model loading or resource contention?)
   - Consider pre-warming model cache PVC
   - Add progress metrics during model loading

4. **Consider RollingUpdate** 🔄
   - Evaluate if application supports zero-downtime deployments
   - Would eliminate deployment downtime (currently 60-120s per deployment)
   - Test in non-production first

5. **Add PreStop Hooks** 🛡️
   - Graceful shutdown for model cleanup
   - Prevents resource leaks during pod termination
   - Allows clean model unload

### For pbx-web (Medium Priority)

1. **Monitor EmptyDir Usage** 📊
   - Add metrics for nginx-cache and nginx-run utilization
   - Alert approaching 16Mi/8Mi limits
   - Consider sizing adjustments if traffic grows

2. **Add S3 Connectivity Checks** 🔍
   - Implement health check for Garage S3 availability
   - Alert on connection failures or timeouts
   - Consider fallback behavior if Garage unavailable

3. **Investigate Rapid Deployment** 🔬
   - 1.0.8 → 1.0.9 in 10.2 minutes suggests post-deployment issue
   - Review logs for that deployment to understand trigger
   - Consider adding smoke tests to prevent similar hotfixes

4. **Evaluate RollingUpdate** 🔄
   - Assess if nginx sidecar can support graceful drain
   - Would eliminate deployment downtime
   - Test in non-production environment

### For Both Services (Low Priority)

1. **Standardize Probe Timeouts** ⏱️
   - Align on best practices (pbx-web: 5s, whisper-stt: 1s)
   - Document rationale for different timeouts
   - Consider using startup probes for slow-startup services

2. **Add Deployment Annotations** 📝
   - Track deployment reasons, ticket links, or commit SHAs
   - Example: `deployment.kubernetes.io/reason: "Fix ADC-12345"`
   - Enables better deployment history analysis

3. **Review Image Pull Policy** 🐳
   - Consider `imagePullPolicy: IfNotPresent` for stability
   - Reduces dependency on Docker Hub availability
   - Change image tag when content actually changes

---

## Appendix: Data Collection Details

### Cluster Information
- **Cluster**: ardenone-cluster
- **Access**: Read-only via kubectl-proxy (Tailscale)
- **Namespaces**: pbx-web, whisper-stt

### Commands Used
```bash
# ReplicaSet history
kubectl --server=http://traefik-ardenone-cluster:8001 get replicasets -n <namespace> -l app=<app> --sort-by=.metadata.creationTimestamp

# Deployment details
kubectl --server=http://traefik-ardenone-cluster:8001 describe deployment <name> -n <namespace>

# Events
kubectl --server=http://traefik-ardenone-cluster:8001 get events -n <namespace> --sort-by='.lastTimestamp'

# Pod history
kubectl --server=http://traefik-ardenone-cluster:8001 get pods -n <namespace> -l app=<app> --sort-by='.metadata.creationTimestamp'
```

### Analysis Scripts
Python scripts used for deployment velocity and rapid deployment pattern analysis are available in `/tmp/analyze_deployments.py` and `/tmp/analyze_replicasets.py`.

---

## Conclusion

The 30-day analysis reveals **significantly different operational profiles** between pbx-web and whisper-stt. pbx-web operates as a stable, mature service with infrequent deployments and lower risk factors. whisper-stt exhibits high deployment velocity with frequent hotfix cascades, suggesting active development but also higher operational risk due to resource intensity, PVC dependencies, and complex model loading.

**Key recommendation**: Focus monitoring and operational improvements on whisper-stt, particularly around resource usage, PVC health, and deployment stability, while maintaining pbx-web's current stable patterns.

---

**Report Generated**: 2026-07-24
**Analysis Period**: 2026-06-24 to 2026-07-24 (30 days)
**Cluster**: ardenone-cluster
**Services Analyzed**: pbx-web, whisper-stt
