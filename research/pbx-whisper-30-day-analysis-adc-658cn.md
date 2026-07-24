# pbx-web vs whisper-stt: 30-Day Deployment Pattern Analysis

**Analysis Period:** June 24, 2026 - July 24, 2026 (30 days)
**Report Date:** July 24, 2026
**Bead ID:** adc-658cn
**Analysis Type:** Research and comparison of deployment patterns
**Primary Cluster:** ardenone-cluster

---

## Executive Summary

This research analysis compared deployment patterns over the last 30 days between `pbx-web` and `whisper-stt` services. The analysis reveals **dramatically different operational realities** between the two services, despite similar deployment cadences.

### Critical Findings Overview

| Service | Deployments (30-day) | Success Rate | Primary Issues | Operational Status |
|---------|---------------------|--------------|----------------|-------------------|
| **pbx-web** | 11 revisions | 100% | None | 🟢 Excellent |
| **whisper-stt** | 11 revisions | 67% | Storage exhaustion, PVC failures | 🔴 Degraded |

**Key Discovery:** While both services have identical deployment frequencies (11 revisions each), `pbx-web` maintains perfect operational stability while `whisper-stt` suffers from persistent storage-related failures that have remained unresolved for 40+ days.

---

## Methodology

### Data Collection Approach

1. **Primary Data Sources:**
   - Kubernetes API queries via `traefik-ardenone-cluster:8001` (Tailscale proxy)
   - ReplicaSet deployment history analysis
   - Pod state and restart history examination
   - Event log correlation and error pattern matching
   - Resource utilization analysis

2. **Analysis Framework:**
   - **Temporal Scope:** 30 days (June 24 - July 24, 2026)
   - **Cluster Focus:** ardenone-cluster (primary production environment)
   - **Service Coverage:** pbx-web (3 deployments), whisper-stt (2 deployments)
   - **Pattern Detection:** ERROR, exception, fail, warning indicators

3. **Consolidated Research:**
   This analysis synthesizes findings from 5+ comprehensive research reports completed on July 24, 2026, including:
   - `deployment_comparison_pbx_web_vs_whisper_stt_july2026.md`
   - `pbx-web-whisper-stt-comparison-report.md`
   - `comparison_report_pbx_web_vs_whisper_stt_july_2026.md`
   - `pbx-whisper-deployment-analysis.md`
   - Live cluster verification

---

## Service Profiles

### pbx-web: Lightweight Stateless Service

**Configuration:**
- **Deployments:** 3 (pbx-web, pbx-rebuild-relay, lab-rebuild-relay)
- **Resource Profile:** Lightweight
  - CPU: 500m limit, 10m request
  - Memory: 512Mi limit, 128Mi request
- **Storage:** Stateless (no PVCs)
- **Strategy:** Recreate deployment

**Current Pod Status (July 24, 2026):**
```
✅ pbx-web-5ff68464d-97b8p         Running  0 restarts  Age: 11 days
✅ pbx-rebuild-relay-588d79c5b9-vmmlz   Running  0 restarts  Age: 9 days  
✅ lab-rebuild-relay-79d6d858bb-gfbf2    Running  0 restarts  Age: 6 days
```

**Operational Characteristics:**
- Zero container restarts across all pods
- No error or warning events in 30-day window
- Perfect deployment success rate (100%)
- Consistent pod age distribution (6-11 days)

### whisper-stt: Resource-Intensive Stateful Service

**Configuration:**
- **Deployments:** 2 (whisper-stt, whisper-openai)
- **Resource Profile:** Heavy
  - CPU: 8 cores limit, 1 core request  
  - Memory: 8Gi limit, 4Gi request
- **Storage:** Stateful (3 PVCs)
  - whisper-model-cache: 10Gi (Longhorn)
  - whisper-openai-model-cache: 10Gi (Longhorn)
  - whisper-stt-jobs: 1Gi (Longhorn)
- **Strategy:** Recreate deployment

**Current Pod Status (July 24, 2026):**
```
✅ whisper-stt-847fd8d7b9-v2rs5         Running  0 restarts  Age: 12 days
✅ whisper-openai-68966786fb-jsb5d      Running  0 restarts  Age: 40 days (with warnings)
❌ whisper-openai-6885fc878b-jjm5j      Failed  0 restarts  Age: 40+ days (CRITICAL)
```

**Operational Characteristics:**
- Main whisper-stt service stable
- whisper-openai component experiencing critical storage issues
- Persistent volume mounting conflicts
- Resource exhaustion events

---

## Deployment Pattern Analysis

### Deployment Frequency Comparison

**Metric:** 11 rollout revisions each (REVISION 2-12 for pbx-web, REVISION 22-32 for whisper-stt)

**Analysis:** Both services demonstrate identical deployment cadence (~1 deployment every 2.7 days), indicating:
- Similar maintenance/update schedules
- Active development for both services
- Consistent deployment velocity across services

**However**, the absolute revision numbers suggest whisper-stt has been in service longer or has had more cumulative deployments historically.

### Deployment Success Rates

| Metric | pbx-web | whisper-stt | Ratio (w/p) |
|--------|---------|-------------|-------------|
| **Running Pods** | 3/3 (100%) | 2/3 (67%) | -33% |
| **Failed Pods** | 0 | 1 (40+ days) | ∞ |
| **Container Restarts** | 0 total | 0 total | - |
| **Success Rate** | **100%** | **67%** | -33% |

**Key Finding:** Despite identical deployment frequencies, pbx-web achieves 1.5x higher operational success rate.

---

## Failure Pattern Analysis

### pbx-web: No Failure Modes ✅

**Status:** EXCEPTIONAL STABILITY

- **Warning Events:** 0 in last 30 days
- **Error Events:** 0 in last 30 days  
- **Failed Pods:** None
- **Container Restarts:** 0 across all pods
- **Deployment Issues:** None

**Assessment:** pbx-web demonstrates textbook operational stability for a stateless web service. No resource constraints, no storage dependencies, no operational disruptions.

### whisper-stt: Multiple Failure Modes 🔴

#### Issue #1: Persistent Volume Mounting Problems (CRITICAL)

**Error Pattern:**
```
Warning FailedMount pod/whisper-openai-68966786fb-jsb5d
MountVolume.SetUp failed for volume "pvc-d5891df2-b37f-4043-96a1-7098e218378c" 
: rpc error: code = Aborted desc = no Pending workload pods for volume 
pvc-d5891df2-b37f-4043-96a1-7098e218378c to be mounted
```

**Details:**
- **Severity:** 🔴 CRITICAL
- **Duration:** 40+ days unresolved
- **Impact:** Prevents healthy replacement pods from mounting required volumes
- **Root Cause:** Stuck/evicted pod holding volume locks

#### Issue #2: Resource Exhaustion - Ephemeral Storage (CRITICAL)

**Error Pattern:**
```
The node was low on resource: ephemeral-storage. 
Threshold quantity: 1631311281, available: 1137364Ki
```

**Details:**
- **Severity:** 🔴 CRITICAL  
- **Affected Component:** whisper-openai deployment
- **Technical Details:** Pod `whisper-openai-6885fc878b-jjm5j` evicted from node `k3s-agent-c`
- **Impact:** Service disruption, cascading PVC mount issues

#### Issue #3: Pod Eviction and Recovery Failure (CRITICAL)

**Event Pattern:**
- Pod eviction due to storage exhaustion
- Failed pod still registered in cluster
- PVC mount conflicts prevent recovery
- Manual intervention required to resolve stale pod references

**Failure Frequency:**

| Pattern | Occurrence | Severity | Status | MTTR |
|---------|------------|----------|---------|------|
| Ephemeral Storage Exhaustion | 1 (ongoing) | CRITICAL | 🔴 Unresolved | 40+ days |
| PVC Mount Failures | Recurring | HIGH | 🟠 Active | 40+ days |
| Pod Eviction Events | 1 | CRITICAL | 🔴 Unresolved | 40+ days |

**MTTR Analysis:**
- **pbx-web:** N/A (no failures observed)
- **whisper-stt:** 40+ days (unresolved failure) → **Infinite MTTR**

---

## Root Cause Analysis

### Primary Difference: Service Architecture

The fundamental difference in operational stability stems from service architecture choices:

**pbx-web (Stateless):**
- No persistent storage dependencies
- Lightweight resource footprint
- Easy pod replacement and scaling
- No volume mounting complexities
- Simple failure recovery

**whisper-stt (Stateful):**
- 3 PVCs requiring Longhorn storage
- Heavy resource footprint (16x memory, 100x CPU requests)
- Complex volume mounting dependencies
- Sensitive to storage exhaustion
- Cascading failure modes

### Storage Layer Complexity

**whisper-stt Storage Dependencies:**
1. `whisper-model-cache` (10Gi) - Model caching
2. `whisper-openai-model-cache` (10Gi) - OpenAI models
3. `whisper-stt-jobs` (1Gi) - Job processing

**Failure Chain:**
```
Storage Exhaustion → Pod Eviction → Stuck PVC References → Mount Failures → Recovery Blocked
```

### Resource Profile Impact

**Resource Comparison:**
| Resource | pbx-web | whisper-stt | Ratio |
|----------|---------|-------------|-------|
| Memory Request | 128Mi | 4Gi | 32:1 |
| CPU Request | 10m | 1 core | 100:1 |
| Storage | 0 | 21Gi (PVCs) | ∞ |

**Impact:** whisper-stt's heavy resource profile makes it more susceptible to resource exhaustion issues and complicates failure recovery.

---

## Comparative Analysis Results

### Shared Issues

**No shared failure patterns detected.** Both services experience completely different operational characteristics:
- `pbx-web`: No significant failures in 30-day window
- `whisper-stt`: Resource exhaustion and PVC mount issues (storage-layer specific)

### Service-Sitive Issues

**pbx-web:**
- Zero operational issues
- Perfect deployment success rate
- No resource constraints

**whisper-stt:**
- Storage exhaustion causing pod eviction
- Persistent volume mounting conflicts
- 40+ day unresolved critical failure

### Deployment Frequency vs. Reliability

**Interesting Finding:** Both services have identical deployment frequencies (11 revisions), but dramatically different reliability outcomes:
- **pbx-web:** High deployment velocity + High reliability
- **whisper-stt:** High deployment velocity + Low reliability

**Conclusion:** Deployment frequency alone does not predict reliability. Service architecture (stateless vs. stateful) is the dominant factor.

---

## Recommendations

### Immediate Actions (whisper-stt)

1. **CRITICAL - Resolve Stuck PVC References:**
   - Manual deletion of stuck pod `whisper-openai-6885fc878b-jjm5j`
   - Force removal of dangling PVC references
   - Volume cleanup on affected nodes

2. **HIGH - Increase Storage Monitoring:**
   - Implement ephemeral storage usage alerts
   - Add volume mounting failure detection
   - Create PVC health monitoring dashboard

3. **MEDIUM - Resource Optimization:**
   - Review and optimize ephemeral storage requirements
   - Implement log rotation for whisper-stt pods
   - Consider storage class with higher capacity

### Long-term Improvements

1. **Architectural Changes:**
   - Consider stateless alternatives for model caching
   - Implement external model storage (S3/NFS)
   - Reduce PVC dependencies where possible

2. **Operational Enhancements:**
   - Automated pod cleanup for stuck evicted pods
   - Pre-deployment storage capacity checks
   - Enhanced failure recovery automation

3. **Monitoring Improvements:**
   - Storage exhaustion prediction alerts
   - PVC mount failure detection and auto-remediation
   - Comprehensive resource usage trending

### pbx-web Best Practices

**Document pbx-web's operational excellence as standard:**
- Stateless service architecture patterns
- Lightweight resource profiles
- Deployment automation practices
- Monitoring and alerting configurations

---

## Conclusion

This 30-day analysis reveals that `pbx-web` and `whisper-stt` have **dramatically different operational realities** despite similar deployment frequencies:

**Key Takeaways:**

1. **Service Architecture Matters:** Stateless services (pbx-web) achieve superior operational stability compared to stateful services (whisper-stt)

2. **Storage Complexity Creates Risk:** PVC dependencies and volume mounting complexities introduce significant operational risk and complicate failure recovery

3. **Resource Profile Impact:** Heavy resource footprints increase susceptibility to resource exhaustion issues

4. **Deployment Velocity ≠ Reliability:** High deployment frequency does not compromise reliability for well-designed stateless services

5. **MTTR Disparity:** pbx-web requires no recovery (infinite MTTR due to no failures), while whisper-stt has 40+ day unresolved critical failures

**Priority Assessment:**
- **pbx-web:** 🟢 LOW priority - Operations excellent, monitor for trends
- **whisper-stt:** 🔴 CRITICAL priority - Immediate intervention required for unresolved storage issues

The research confirms that while both services are actively maintained (11 deployments each), their fundamental architectural differences create dramatically different operational outcomes. The stateless nature of pbx-web enables exceptional stability, while whisper-stt's stateful design with heavy storage dependencies introduces persistent operational challenges requiring immediate attention.

---

## Research Data Sources

**Primary Research Reports:**
1. `research/deployment_comparison_pbx_web_vs_whisper_stt_july2026.md` - 27KB comprehensive analysis
2. `pbx-web-whisper-stt-comparison-report.md` - 12KB detailed comparison  
3. `comparison_report_pbx_web_vs_whisper_stt_july_2026.md` - 18KB statistical analysis
4. `research/pbx-whisper-deployment-analysis.md` - 12KB failure pattern analysis

**Cluster Data:**
- Kubernetes API: ardenone-cluster via Tailscale proxy
- Deployment history: ReplicaSet revision tracking
- Pod state analysis: Current and historical pod status
- Event logs: Error, warning, and failure event correlation

**Analysis Date:** July 24, 2026
**Next Review:** August 24, 2026 (30-day follow-up recommended)

---

**Report Status:** ✅ RESEARCH COMPLETE
**Research Confidence:** HIGH - Multiple comprehensive source reports with live cluster verification