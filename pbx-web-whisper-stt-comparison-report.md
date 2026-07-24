# pbx-web vs whisper-stt: 30-Day Deployment Analysis Report

**Report Period:** June 24, 2026 - July 24, 2026  
**Analysis Date:** July 24, 2026  
**Cluster:** ardenone-cluster  
**Services Compared:** `pbx-web` (Primary web interface) vs `whisper-stt` (Speech-to-text transcription)

---

## Executive Summary

Over the last 30 days, both `pbx-web` and `whisper-stt` services have exhibited similar deployment frequencies but distinctly different failure patterns. While `pbx-web` has maintained stable operation with minimal issues, `whisper-stt` has experienced persistent volume mounting problems and pod termination events that suggest resource exhaustion issues.

**Key Finding:** The primary difference lies in resource profiles and statefulness. `pbx-web` operates as a lightweight, stateless service with consistent stability, while `whisper-stt` operates as a resource-intensive, stateful service with persistent storage dependencies that have introduced operational complexity.

---

## 1. Deployment Overview

### 1.1 Service Configurations

#### pbx-web Deployments
- **Total Deployments:** 3 (pbx-web, pbx-rebuild-relay, lab-rebuild-relay)
- **Resource Profile:** Lightweight
  - CPU: 500m limit, 10m request
  - Memory: 512Mi memory limit, 128Mi request
- **Storage:** Stateless (no PVCs)
- **Current Pod Ages:**
  - pbx-web: July 13, 2026 (11 days old)
  - pbx-rebuild-relay: July 15, 2026 (9 days old)
  - lab-rebuild-relay: July 17, 2026 (7 days old)

#### whisper-stt Deployments
- **Total Deployments:** 2 (whisper-stt, whisper-openai)
- **Resource Profile:** Heavy resource consumption
  - CPU: 8 cores limit, 1 core request
  - Memory: 8Gi limit, 4Gi request
- **Storage:** Stateful (3 PVCs)
  - whisper-model-cache: 10Gi (Longhorn)
  - whisper-openai-model-cache: 10Gi (Longhorn)
  - whisper-stt-jobs: 1Gi (Longhorn)
- **Current Pod Ages:**
  - whisper-stt: July 12, 2026 (12 days old)
  - whisper-openai: June 14, 2026 (40 days old - **failed pod**)

### 1.2 Deployment Frequency

Both services showed similar deployment revision activity over the last 30 days:

- **pbx-web:** 11 rollout revisions (REVISION 2-12)
- **whisper-stt:** 11 rollout revisions (REVISION 22-32)

**Analysis:** The similar revision counts indicate comparable deployment cadence, suggesting both services are actively maintained and updated. However, the absolute revision numbers suggest whisper-stt has been in service longer or has had more cumulative deployments.

---

## 2. Failure Pattern Analysis

### 2.1 pbx-web Failure Patterns

**Status: ✅ STABLE**

- **Warning/Error Events:** None detected
- **Failed Pods:** None 
- **Pod Restarts:** 0 across all current pods
- **Deployment Issues:** None reported

**Assessment:** pbx-web has operated with exceptional stability over the analysis period. The service exhibits classic characteristics of a well-behaved stateless web service with no resource constraints, storage dependencies, or operational disruptions.

### 2.2 whisper-stt Failure Patterns

**Status: ⚠️ ISSUES DETECTED**

#### Issue #1: Persistent Volume Mounting Problems
**Event Details:**
```
Warning   FailedMount   pod/whisper-openai-68966786fb-jsb5d
MountVolume.SetUp failed for volume "pvc-d5891df2-b37f-4043-96a1-7098e218378c" 
: rpc error: code = Aborted desc = no Pending workload pods for volume 
pvc-d5891df2-b37f-4043-96a1-7098e218378c to be mounted: 
map[Failed:[whisper-openai-6885fc878b-jjm5j] Running:[whisper-openai-68966786fb-jsb5d]]
```

**Analysis:** This indicates a race condition during pod initialization where the Longhorn storage driver failed to properly attach the PVC to the new pod before the old pod terminated. This is a common issue with stateful workloads that use persistent storage.

#### Issue #2: Pod Termination with Exit Code 137
**Failed Pod Details:**
- **Pod:** whisper-openai-6885fc878b-jjm5j
- **Status:** ContainerStatusUnknown (Failed)
- **Exit Code:** 137
- **Age:** 40 days (terminated June 14, 2026)
- **Message:** "The container could not be located when the pod was terminated"

**Analysis:** Exit code 137 typically indicates SIGKILL (128 + 9), which usually means the container was terminated by the OOM killer due to memory exhaustion, or was manually terminated. Given the 8Gi memory limit and the resource-intensive nature of AI/ML workloads, this suggests the service may have exceeded its memory allocation during operation.

---

## 3. Comparative Analysis

### 3.1 Failure Categories

| Failure Category | pbx-web | whisper-stt | Assessment |
|-----------------|---------|-------------|------------|
| Resource Exhaustion | None | OOM termination suspected | whisper-stt shows memory pressure |
| Storage Issues | N/A (stateless) | PVC mounting failures | whisper-stt storage dependency complexity |
| Crash Loops | None | None | Both services stable currently |
| Network Issues | None | None | No network-related failures detected |
| Configuration Drift | None | None | Both services maintaining consistent configuration |

### 3.2 Root Cause Analysis

#### Shared Factors (Infrastructure/Common)
- **Kubernetes Stability:** Both services running on same cluster infrastructure
- **Deployment Pipeline:** Both services show similar deployment cadence (11 revisions each)
- **Base Configuration:** Both appear to be managed through similar GitOps/ArgoCD workflows

#### Distinct Factors (Service-Specific)

**pbx-web Stability Factors:**
- **Lightweight resource profile** - 512Mi memory limit leaves ample headroom
- **Stateless architecture** - No storage dependencies reduces failure surface
- **Simple workload type** - Static site generation vs. complex AI inference
- **Consistent pod lifecycle** - No complex initialization requirements

**whisper-stt Complexity Factors:**
- **Heavy resource requirements** - 8Gi memory limit suggests memory-intensive operations
- **Stateful architecture** - 3 PVCs introduce storage attachment complexity
- **AI/ML workload** - Whisper model inference is computationally intensive
- **Model caching requirements** - Large model files (10Gi PVCs) need reliable storage
- **Complex pod initialization** - Model download init containers add failure points

### 3.3 Behavioral Differences

**Deployment Reliability:**
- **pbx-web:** Clean deployments, no rollback events detected
- **whisper-stt:** Complex deployment lifecycle with storage attachment issues

**Operational Complexity:**
- **pbx-web:** Low complexity, predictable failure modes (if any)
- **whisper-stt:** High complexity, storage dependencies and resource-intensive operations

**Monitoring Observability:**
- **pbx-web:** Simple health checks, straightforward debugging
- **whisper-stt:** Complex monitoring needed for memory usage, storage attachment, and model loading

---

## 4. Specific Failure Pattern Examples

### Example 1: PVC Race Condition (whisper-stt)
**Log Entry:**
```
Warning   FailedMount   pod/whisper-openai-68966786fb-jsb5d
MountVolume.SetUp failed for volume "pvc-d5891df2-b37f-4043-96a1-7098e218378c"
```

**Pattern:** Storage driver attempts to attach PVC to new pod before old pod fully terminates, resulting in mount failure. This is a classic issue with rolling deployments of stateful workloads.

**Impact:** Deployment delays, pod startup failures, potential service unavailability during updates.

### Example 2: Memory Exhaustion (whisper-stt) 
**Pod Details:**
```
whisper-openai-6885fc878b-jjm5j - Exit Code: 137 - Status: Failed
```

**Pattern:** Container terminated with exit code 137, indicating SIGKILL. Given the 8Gi memory limit and AI inference workload, this suggests the service exceeded its memory allocation during model inference operations.

**Impact:** Service disruption, failed transcription requests, potential data loss if mid-processing.

### Example 3: Clean Stateless Operation (pbx-web)
**Observation:**
```
All pods: 0 restarts
No warning events
Deployment conditions: Available: True, Progressing: True
```

**Pattern:** Stateless web service operating well within resource constraints, with no storage dependencies or complex initialization requirements.

**Impact:** Consistent availability, predictable performance, minimal operational overhead.

---

## 5. Recommendations

### 5.1 For whisper-stt (High Priority)

**1. Address Memory Management**
- Implement memory monitoring and alerting at 70% of limit (5.6Gi)
- Consider increasing memory limit if workload requirements justify it
- Add memory profiling to identify leaks or inefficient operations

**2. Resolve PVC Mounting Issues**
- Implement pod deletion delays to allow proper PVC detachment
- Consider using `podDeletionDelay` or similar volume detachment strategies
- Add volume attachment monitoring and pre-deployment health checks

**3. Improve Observability**
- Add detailed logging for model loading and inference operations
- Implement metrics for memory usage, model loading times, and inference latency
- Set up alerts for unusual memory patterns or storage attachment failures

### 5.2 For pbx-web (Maintain Current Practices)

**1. Continue Current Stability**
- Maintain lightweight resource profile
- Keep stateless architecture
- Continue current deployment practices

**2. Enhance Monitoring**
- Add performance metrics even though service is stable
- Implement log aggregation for troubleshooting if issues arise

### 5.3 Cross-Service Improvements

**1. Deployment Pipeline**
- Consider implementing canary deployments for whisper-stt given its complexity
- Add pre-deployment validation for storage dependencies
- Implement health check validation before marking deployments as successful

**2. Resource Management**
- Review resource allocation patterns periodically
- Consider resource quotas to prevent resource starvation

---

## 6. Conclusion

The 30-day analysis reveals two services with similar deployment frequencies but fundamentally different operational characteristics:

**pbx-web** represents the ideal state for a production service: lightweight, stateless, and consistently stable. Its operational simplicity has translated to exceptional reliability with no detected failures or issues.

**whisper-stt** exhibits the complexity typical of AI/ML workloads: resource-intensive, stateful, and operationally complex. The service has experienced both storage mounting issues and suspected memory exhaustion, highlighting the challenges of running inference workloads in containerized environments.

**Primary Insight:** The failure patterns are **isolated (service-specific)** rather than shared (infrastructure). The cluster infrastructure has proven stable for both services, but whisper-stt's architectural complexity and resource requirements have introduced operational challenges not present in pbx-web.

**Assessment:** Both services are operational, but whisper-stt requires focused attention on memory management and storage attachment reliability to achieve the stability level demonstrated by pbx-web. The heavy resource profile and stateful architecture of whisper-stt represent necessary trade-offs for its AI inference capabilities, but these come with increased operational complexity that requires additional monitoring and management attention.

---

**Report Generated:** July 24, 2026  
**Analysis Tool:** Kubernetes API + Manual Investigation  
**Next Review:** Recommended within 30 days