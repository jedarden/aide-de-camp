# pbx-web vs whisper-stt: 30-Day Deployment Analysis

**Analysis Period:** Last 30 days (as of 2026-07-24)  
**Cluster:** ardenone-cluster  
**Analysis Type:** Comparative deployment patterns and failure modes

## Executive Summary

Over the last 30 days, `whisper-stt` has experienced significantly more deployment instability compared to `pbx-web`:

- **Deployment Frequency:** whisper-stt: 11 deployments | pbx-web: 4 deployments
- **Failure Patterns:** whisper-stt: Pod evictions | pbx-web: No failures
- **Resource Intensity:** whisper-stt: 8Gi memory | pbx-web: 512Mi memory
- **Root Cause:** Storage pressure and higher resource requirements

## Detailed Findings

### Deployment Frequency Analysis

#### whisper-stt
**Deployment timeline (last 30 days):**
- 11 deployment attempts (replicaSets created)
- Deployment ages: 29d, 28d, 22d, 16d, 11d (current)
- **Deployment rate:** ~2.75x higher than pbx-web

#### pbx-web  
**Deployment timeline (last 30 days):**
- 4 deployment attempts (replicaSets created)
- Deployment ages: 30d, 29d, 10d (current)
- **Deployment rate:** Baseline for comparison

### Resource Requirements Comparison

| Resource | whisper-stt | pbx-web | Ratio |
|----------|-------------|---------|-------|
| **Memory Limit** | 8Gi | 512Mi | 16:1 |
| **Memory Request** | 4Gi | 128Mi | 32:1 |
| **CPU Limit** | 8 cores | 500m | 16:1 |
| **CPU Request** | 1 core | 10m | 100:1 |

**Key Insight:** whisper-stt is significantly more resource-intensive, requiring 16-32x more memory than pbx-web.

### Failure Patterns

#### whisper-stt: Storage Pressure Evictions

**Primary Failure Mode:** Pod eviction due to ephemeral-storage shortage

```
Status: Failed
Reason: Evicted
Message: The node was low on resource: ephemeral-storage. 
Threshold quantity: 1631311281, available: 1137364Ki
```

**Affected Pod:** `whisper-openai-6885fc878b-jjm5j`
- **Node:** k3s-agent-c  
- **Failure Type:** Resource eviction (storage)
- **Recovery:** New pod `whisper-openai-68966786fb-jsb5d` created
- **Current Status:** Running with persistent FailedMount warnings

**Secondary Issue:** Persistent Volume Claim mount issues
```
FailedMount for volume "pvc-d5891df2-b37f-4043-96a1-7098e218378c": 
no Pending workload pods for volume to be mounted
```

#### pbx-web: No Failures Observed

- **Current pod:** `pbx-web-5ff68464d-97b8p`
- **Status:** Running, 0 restarts
- **Age:** 10 days stable
- **Resource Usage:** Well within limits (512Mi memory limit)

### Stability Comparison

| Metric | whisper-stt | pbx-web |
|--------|-------------|---------|
| **Pod Restarts** | 0 (but pod evictions) | 0 |
| **Pod Evictions** | Yes (storage pressure) | No |
| **Current Status** | Running with warnings | Running stable |
| **Age of Current Pod** | 11 days | 10 days |
| **Deployment Success Rate** | Lower (more attempts) | Higher |

### Root Cause Analysis

#### whisper-stt Instability Factors

1. **Storage Pressure**
   - Large model downloads consume significant ephemeral storage
   - HuggingFace cache for `large-v3-turbo` models
   - Model download init containers require substantial temporary storage

2. **High Resource Requirements**
   - 8Gi memory limit (vs 512Mi for pbx-web)
   - More likely to hit node resource constraints
   - Increased scheduling complexity

3. **Model Caching Complexity**
   - PVC-based model cache introduces mount dependencies
   - Init container pattern for model downloads adds deployment complexity
   - Symlink operations for gated models increase failure surface

#### pbx-web Stability Factors

1. **Lightweight Architecture**
   - Minimal resource requirements (512Mi memory)
   - Simple two-container design (site-generator + nginx)
   - No large file dependencies or model caching

2. **Lower Complexity**
   - No PVC dependencies
   - No init containers
   - Standard HTTP health checks

## Temporal Patterns

### Deployment Timing Analysis

**whisper-stt deployment clusters:**
- Heavy activity: 29d, 28d (multiple attempts within short window)
- Pattern suggests iterative fixes or retries
- Recent stabilization: 11d current pod

**pbx-web deployment pattern:**
- Stable intervals between deployments
- No evidence of crash-loop deployments
- Planned deployment pattern

## Infrastructure Correlations

### Node Resource Pressure

**Node k3s-agent-c** (whisper-stt eviction location):
- **Memory:** 109% overcommitted on limits
- **CPU:** 260% overcommitted on limits  
- **Storage:** 0% ephemeral-storage allocated (but high pressure)

**Node k3s-agent-minisforum** (current pbx-web location):
- Successfully hosts both pbx-web and whisper-stt workloads
- Better resource distribution

## Recommendations

### Immediate Actions

1. **Monitor ephemeral-storage usage** on k3s-agent-c
2. **Review PVC mounting strategy** for whisper-openai model cache
3. **Consider horizontal pod autoscaling** for whisper-stt to distribute load

### Long-term Improvements

1. **Optimize model storage strategy**
   - Pre-warm model cache on dedicated storage
   - Consider external model storage (S3/NFS)

2. **Resource optimization**
   - Review if 8Gi memory limit can be reduced
   - Implement resource quotas to prevent overcommitment

3. **Deployment automation**
   - Implement pre-flight storage checks
   - Add deployment readiness gates for PVC availability

## Conclusion

The 30-day analysis reveals a clear stability disparity between the two services:

- **whisper-stt** experiences deployment instability primarily due to storage pressure and high resource requirements
- **pbx-web** demonstrates stable deployment patterns with minimal resource footprint

The higher deployment frequency for whisper-stt (11 vs 4) correlates with its resource-intensive architecture and storage constraints, while pbx-web maintains consistent stability with its lightweight design.

**Key Takeaway:** Storage management is the critical differentiator - whisper-stt's model caching strategy creates deployment friction that pbx-web's simpler architecture avoids.

---

**Analysis Date:** 2026-07-24  
**Bead ID:** adc-23dyw  
**Cluster:** ardenone-cluster via Tailscale proxy
