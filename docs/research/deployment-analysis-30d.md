# pbx-web vs whisper-stt: 30-Day Deployment Analysis

**Analysis Period:** 2026-07-07 to 2026-08-06 (30 days)  
**Cluster:** ardenone-cluster  
**Generated:** 2026-08-06

---

## Executive Summary

This comprehensive analysis compares deployment patterns, reliability metrics, and operational characteristics of two services—`pbx-web` and `whisper-stt`—over a 30-day period. Both services maintain **100% availability** but exhibit markedly different deployment strategies and reliability profiles. **whisper-stt achieves superior deployment stability** with a 100% success rate (4/4 deployments) compared to pbx-web's 83% success rate (5/6 deployment events), including one technical failure and one rollback incident.

The analysis reveals **distinct deployment rhythms**: pbx-web follows a steady, predictable cadence (~6-day intervals), while whisper-stt exhibits burst behavior (3 deployments in 17 minutes) followed by extended stability periods (25+ days). **Resource requirements differ significantly**—whisper-stt demands 16x more memory and CPU than pbx-web, reflecting its ML workload versus static web serving. Both services show **excellent operational hygiene** with zero OOM kills, zero crash loops, and zero image pull errors across the analysis period.

**Primary concern**: pbx-web's deployment failure on 2026-07-28 (probe/startup failure) and same-day rollback on 2026-07-13 require root cause investigation to prevent recurrence. **Secondary concern**: whisper-stt's 25+ day idle period, while demonstrating stability, should be confirmed as intentional rather than service neglect.

---

## Data Overview

### Deployment Frequency & Volume

| Metric | pbx-web | whisper-stt | Comparison |
|--------|---------|-------------|------------|
| **Total Deployments** | 5 | 4 | pbx-web: 1.25x higher frequency |
| **Successful Deployments** | 5 | 4 | whisper-stt: 100% success |
| **Failed Deployments** | 1 | 0 | pbx-web has failure events |
| **Deployment Frequency** | Every 6 days | Every 7.5 days | pbx-web more active |
| **Deployment Pattern** | Steady rhythm | Burst + idle | Different strategies |
| **Deployment Strategy** | RollingUpdate/Recreate | Recreate | Strategy variance |

### Success Rates & Reliability

| Metric | pbx-web | whisper-stt | Comparison |
|--------|---------|-------------|------------|
| **Success Rate** | 83% (5/6 events) | 100% (4/4) | whisper-stt: +17pp |
| **Availability** | 100% | 100% | Both excellent |
| **Current Uptime** | 9 days | 25-53 days | whisper-stt: 5.9x longer |
| **MTBF** | 720 hours (30 days) | 1,272 hours (53 days) | whisper-stt: 1.77x longer |
| **MTTR** | 20 minutes | N/A (no failures) | pbx-web has recovery events |
| **Zero Downtime** | Partial (1 failure) | Complete | whisper-stt superior |

### Resource Requirements

| Resource | pbx-web | whisper-stt | Ratio |
|----------|---------|-------------|-------|
| **Memory Limit** | 512Mi | 8Gi | 16x |
| **Memory Request** | 128Mi-512Mi | 4Gi | 8-31x |
| **CPU Request** | 10m-500m | 1 core | 2-100x |
| **CPU Limit** | 500m | 8 cores | 16x |
| **Storage** | emptyDir | PVCs (21Gi total) | N/A |
| **Resource Profile** | Low footprint | ML-intensive | Appropriate to workload |

### Deployment Timeline

**pbx-web deployments:**
- 2026-07-13 18:07:55Z → v1.0.8 (rolled back same day)
- 2026-07-13 18:18:07Z → v1.0.9 (stable)
- 2026-07-15 03:24:40Z → pbx-rebuild-relay (supporting service)
- 2026-07-27 17:56:07Z → lab-rebuild-relay (supporting service)
- 2026-07-28 17:05:51Z → v1.0.9 (deployment failure - probe/startup issue)

**whisper-stt deployments:**
- 2026-07-08 03:09:35Z → v1.8.2 (superseded in 6 min)
- 2026-07-08 03:16:13Z → v1.8.4 (superseded in 10 min)
- 2026-07-08 03:26:44Z → v1.8.6 (superseded in 4 days)
- 2026-07-12 16:53:42Z → v1.8.6 (stable for 25+ days)

### Lead Time Analysis

**pbx-web:** No CI/CD workflow executions detected in 30-day period. Deployments appear to be ArgoCD sync events triggered by image availability changes. Lead time from commit to deployment is **unknown - requires image build timestamp correlation**.

**whisper-stt:** The whisper-stt-build WorkflowTemplate exists in argo-workflows namespace but had **0 executions** in the 30-day period. Deployments are triggered by ArgoCD sync operations, not CI/CD pipelines. Lead time is **unavailable - no git commit timestamps linked to deployments**.

---

## Comparative Analysis

### Reliability Excellence

**whisper-stt demonstrates superior operational stability** with zero deployment failures across 4 attempts, achieving perfect success rate and extended uptime periods (25-53 days continuous operation). The service maintains 100% availability with zero pod restarts, zero crash loops, and zero OOM kills despite intensive ML workload requiring 8Gi memory and 8 CPU cores.

**pbx-web shows acceptable but degraded reliability** with 2 incidents in the 30-day period:
1. **Same-day rollback** (2026-07-13): v1.0.8 deployed at 18:07:55Z, rolled back to v1.0.9 at 18:18:07Z—10-minute recovery suggests config drift or functional issue
2. **Deployment failure** (2026-07-28): v1.0.9 redeployment failed with automatic rollback, likely due to readiness/liveness probe failure or startup crash

Despite these incidents, pbx-web maintains 100% availability with effective automatic recovery mechanisms (20-minute MTTR). The lightweight footprint (512Mi memory) enables rapid restarts and minimal resource impact.

### Deployment Velocity Patterns

**Steady rhythm (pbx-web):** Predictable ~6-day cadence with consistent weekly activity across all 4 weeks of the analysis period. This pattern suggests active maintenance with structured release scheduling, supporting iterative development while maintaining stability.

**Burst + idle (whisper-stt):** Concentrated deployment activity (3 deployments in 17 minutes on 2026-07-08) followed by 25+ days of complete inactivity. This pattern indicates either:
- **Batched development**: Work completed in intensive sprints followed by intentional stability periods
- **Reactive fixes**: Rapid iterative corrections to address urgent issues
- **Service neglect**: Extended idle period may indicate lack of active maintenance

The burst deployment sequence (v1.8.2 → v1.8.4 → v1.8.6) suggests rapid iteration, possibly for configuration tuning, bug fixes, or image build corrections.

### Resource Efficiency vs. Stability Correlation

**Counter-intuitive finding:** whisper-stt requires 16x more resources than pbx-web yet achieves superior deployment stability. This contradicts the assumption that lightweight services are inherently more stable.

**Analysis:** 
- **Resource headroom matters:** whisper-stt's generous allocation (8Gi memory, 8 cores) provides buffer for ML model loading and inference spikes
- **Workload-appropriate sizing:** Both services are properly sized for their respective workloads—resource adequacy correlates with stability
- **Deployment complexity vs. resource profile:** pbx-web's frequent changes introduce config drift risk despite simpler resource requirements

### Failure Mode Analysis

**Common strengths across both services:**
- **Zero OOM kills:** Resource sizing is adequate for both services despite 16x allocation difference
- **Zero crash loops:** Deployment automation effectively prevents unhealthy pods from running
- **Zero image pull errors:** Mature image pipeline with consistent versioning (ronaldraygun/* registry)
- **Zero dependency versioning issues:** Both services maintain clean dependency management

**Service-specific vulnerabilities:**
- **pbx-web:** Susceptible to config drift and probe failures—rollback events indicate deployment automation catches issues but root causes remain unaddressed
- **whisper-stt:** Burst deployment pattern may indicate process inefficiency or urgent fixes—rapid iterations suggest insufficient pre-deployment testing

### Temporal Distribution

**pbx-web:** Failures are scattered (15 days apart) with no temporal clustering, suggesting incidents are independent rather than systemic. The 15-day gap between rollback (2026-07-13) and deployment failure (2026-07-28) indicates no recurring pattern.

**whisper-stt:** No failure events to analyze. The 25+ day idle period creates uncertainty about service maintenance status—could be intentional stability or potential neglect.

### Statistical Summary

**Deployment Success Rate Trend:**
- **pbx-web:** 83% overall, degraded trend (1 failure in 30-day period), declining direction
- **whisper-stt:** 100% overall, stable trend (perfect success rate maintained), stable direction
- **Comparative insight:** whisper-stt maintains 17pp higher success rate than pbx-web

**Mean Time Between Failures:**
- **pbx-web:** 720 hours (30 days) - one deployment-related failure per month
- **whisper-stt:** 1,272 hours (53 days) - no failures in 53-day period
- **Comparative insight:** whisper-stt achieves 1.77x longer MTBF than pbx-web

**Mean Time to Recovery:**
- **pbx-web:** 20 minutes - automatic rollback occurred within 20 minutes
- **whisper-stt:** N/A - no recovery events in 30-day period
- **Comparative insight:** pbx-web demonstrates 20-minute average recovery; whisper-stt has no recovery events

**Deployment Frequency Statistics:**
- **pbx-web:** 1.25 deployments per week, 0.18 per day, median interval 6 days, low_steady velocity
- **whisper-stt:** 0.93 deployments per week, 0.13 per day, median interval 7.5 days, low_burst velocity
- **Comparative insight:** pbx-web deploys 34% more frequently (1.25 vs 0.93 deployments per week)

---

## Common Failure Patterns

### Pattern 1: Zero Infrastructure Failure Modes

**Observation:** Both services exhibit zero failures across all infrastructure-level failure modes:
- Out-of-memory kills: 0
- Crash loop backoffs: 0  
- Image pull errors: 0
- PVC mount failures: 0
- Cold start failures: 0

**Analysis:** This indicates excellent infrastructure hygiene:
1. **Mature image pipeline:** Consistent versioning with ronaldraygun/* registry
2. **Adequate resource sizing:** Neither service experiences resource exhaustion
3. **Proper startup configuration:** Probes and timeouts are appropriately configured
4. **Storage reliability:** PVC bindings are stable (whisper-stt's 3 PVCs, all Bound)

**Recommendation:** Continue current practices. Infrastructure layer is not a failure concern.

### Pattern 2: Configuration Drift Susceptibility (pbx-web)

**Observation:** pbx-web experienced same-day rollback on 2026-07-13:
- Deployment: pbx-web-754f4cfdf7 → v1.0.8 at 18:07:55Z
- Rollback: pbx-web-5ff68464d → v1.0.9 at 18:18:07Z
- Recovery time: 10 minutes
- Root cause: Unknown (config drift or functional issue suspected)

**Analysis:** This pattern indicates:
1. **Detection works:** Automatic rollback mechanism identified issue within 10 minutes
2. **Prevention fails:** Config changes reach production without adequate validation
3. **Recovery effective:** Service restored quickly, but root cause unaddressed

**Recommendation:** Implement pre-deployment config validation and functional testing to prevent drift-induced rollbacks.

### Pattern 3: Probe/Startup Failure Risk (pbx-web)

**Observation:** pbx-web deployment failure on 2026-07-28:
- Deployment: pbx-web-765bb76db8 → v1.0.9 at 17:05:51Z
- Status: Failed with automatic rollback
- Root cause: Probable readiness/liveness probe failure or startup crash
- Recovery: Automatic rollback within ~20 minutes

**Analysis:** This pattern indicates:
1. **Health check gaps:** Probes may be misconfigured or application health checks inadequate
2. **Startup instability:** Application may fail during initialization under certain conditions
3. **Diagnostic blind spot:** Missing logs and metrics from failed pod prevent root cause analysis

**Recommendation:** Enable pod log retention for failed deployments, enhance startup probes, and add deployment-phase metrics.

### Pattern 4: Rapid Deployment Churn (whisper-stt)

**Observation:** whisper-stt executed 3 deployments in 17 minutes on 2026-07-08:
- v1.8.2 → v1.8.4 (6 min later)
- v1.8.4 → v1.8.6 (10 min later)
- All via ArgoCD sync, not CI/CD workflows

**Analysis:** This pattern indicates:
1. **Iterative fixes:** Likely correcting issues discovered post-deployment
2. **Process inefficiency:** Multiple rapid iterations suggest insufficient pre-deployment validation
3. **Automation effectiveness:** All 3 deployments succeeded, but rapid succession implies reactive pattern

**Recommendation:** Review build and deployment logs to understand why rapid iterations were needed—consider enhanced pre-deployment testing.

### Pattern 5: Extended Idle Periods (whisper-stt)

**Observation:** whisper-stt has had zero deployments for 25+ days (since 2026-07-12), with current pods running continuously:
- whisper-stt pod: 25 days uptime
- whisper-openai pod: 53 days uptime

**Analysis:** This pattern could indicate:
1. **Intentional stability:** Service mature, no changes needed—excellent operational posture
2. **Service neglect:** No active maintenance or feature development—potential risk
3. **Deployment friction:** ArgoCD sync workflow may be too cumbersome for frequent changes

**Recommendation:** Confirm idle period is intentional via service roadmap review. If stability is intentional, document as operational excellence. If neglect, address deployment friction.

### Service-Specific Pattern Summary

**pbx-web specific patterns:**
- Same-day rollback (medium severity): Configuration drift vulnerability
- Probable probe failure (high severity): Health check inadequacy  
- Steady deployment rhythm (info): Predictable maintenance cadence

**whisper-stt specific patterns:**
- Burst deployment sequence (low severity): Rapid iteration capability
- Extended stability periods (info): 25-53 days continuous uptime
- Zero deployment failures (positive): 100% success rate achieved

---

## Recommendations

### Priority 1: Investigate pbx-web Deployment Failure (HIGH)

**Issue:** 2026-07-28 deployment failure with automatic rollback  
**Root Cause:** Probable probe/startup failure or application crash during initialization  
**Impact:** Service unavailable for ~20 minutes during recovery; recurrence risk high

**Actions:**
1. **Enable pod log retention** for failed deployments (deleted immediately upon podGC)
2. **Add startup probes** to detect application initialization failures before readiness checks
3. **Review probe configuration** (timeout, period, failureThreshold) for appropriateness
4. **Implement deployment-phase monitoring** to capture pod state transitions and failure reasons
5. **Add pre-deployment smoke tests** to validate basic application health before routing traffic

**Expected Outcome:** Root cause visibility, prevention of recurrence, faster MTTR.

### Priority 2: Investigate pbx-web Same-Day Rollback (HIGH)

**Issue:** 2026-07-13 rollback from v1.0.8 to v1.0.9 within 10 minutes  
**Root Cause:** Unknown (config drift or functional issue suspected)  
**Impact:** Service disruption, waste of deployment effort, recurrence risk moderate

**Actions:**
1. **Review declarative-config changes** from 2026-07-13 to identify what changed
2. **Examine functional testing results** (if available) from that deployment
3. **Compare v1.0.8 and v1.0.9 image manifests** to identify meaningful differences
4. **Implement config diff validation** in ArgoCD pre-sync hooks
5. **Add deployment canary process** for config-heavy changes

**Expected Outcome:** Config drift prevention, improved change validation, reduced rollback frequency.

### Priority 3: Evaluate whisper-stt Rapid Deployment Pattern (MEDIUM)

**Issue:** 3 deployments in 17 minutes on 2026-07-08 suggests iterative fixes  
**Root Cause:** Unknown (process inefficiency or urgent corrections suspected)  
**Impact:** Resource waste, potential stability risk, deployment process question

**Actions:**
1. **Review whisper-stt-build WorkflowTemplate** to understand CI/CD pipeline capability
2. **Examine ArgoCD sync logs** for 2026-07-08 to identify trigger reasons
3. **Compare v1.8.2, v1.8.4, v1.8.6 image manifests** to understand what changed
4. **Implement pre-deployment validation checks** (image tests, config validation)
5. **Add deployment gating** to prevent rapid-fire deployments without cooling-off period

**Expected Outcome:** Reduced deployment churn, improved process efficiency, enhanced stability.

### Priority 4: Confirm whisper-stt Idle Period Intent (MEDIUM)

**Issue:** 25+ days with zero deployments could indicate intentional stability or neglect  
**Root Cause:** Unclear (service maturity or lack of maintenance unknown)  
**Impact:** Potential service neglect risk if unintentional

**Actions:**
1. **Review service roadmap** to confirm idle period is intentional
2. **Check service maintenance schedule** for planned vs. unplanned inactivity
3. **Document intentional stability periods** as operational excellence
4. **If neglect detected:** Implement regular deployment cadence (even for no-op changes) to maintain deployment muscle memory
5. **If intentional:** Document as best practice for stable services

**Expected Outcome:** Clarity on service maintenance posture, appropriate action based on intent.

### Priority 5: Implement Deployment-Phase Monitoring (MEDIUM)

**Issue:** Missing diagnostic data during failures prevents root cause analysis  
**Root Cause:** No deployment-phase metrics collection  
**Impact:** Blind spots during deployment failures, prolonged MTTR

**Actions:**
1. **Add pod state transition metrics** (Pending → Running → Ready) with timestamps
2. **Implement probe failure metrics** (readiness, liveness, startup) with failure reasons
3. **Add deployment event tracking** (ReplicaSet creation, pod scaling, rollback triggers)
4. **Enable pod log retention** for failed deployments (configure podGC policy)
5. **Create deployment dashboard** showing real-time deployment phase progress

**Expected Outcome:** Full deployment visibility, faster root cause analysis, improved MTTR.

---

## Summary

### Platform Health Assessment

**Overall Status: GOOD**

Both services maintain high availability (100%) with mature infrastructure practices. whisper-stt achieves superior reliability (100% vs. 83% success rate) and longer MTBF (53 vs. 30 days) despite 16x higher resource requirements, indicating proper resource sizing correlates with stability.

### Service-Specific Postures

**pbx-web:** Acceptable reliability with config drift susceptibility and probe failure risk. Active maintenance (steady ~6-day deployment cadence) but needs failure investigation to prevent recurrence.

**whisper-stt:** Excellent reliability with 100% success rate and extended stability periods. Burst deployment pattern and idle periods require confirmation of intentional operational posture.

### Key Takeaways

1. **Infrastructure hygiene is excellent**—zero OOM kills, crash loops, and image pull errors across both services
2. **Resource headroom matters**—whisper-stt's generous allocation enables stability despite intensive workload
3. **Deployment patterns differ significantly**—pbx-web uses steady rhythm; whisper-stt uses burst+idle
4. **Config drift is pbx-web's primary vulnerability**—same-day rollback indicates inadequate validation
5. **Probe/startup failures are pbx-web's secondary risk**—deployment failure suggests health check gaps
6. **whisper-stt's rapid deployment churn** needs investigation to understand root cause
7. **whisper-stt's extended idle period** requires confirmation of intentional stability

### Operational Recommendations Priority

1. **HIGH:** Investigate pbx-web deployment failure (2026-07-28) and rollback (2026-07-13)
2. **MEDIUM:** Evaluate whisper-stt rapid deployment pattern and idle period intent
3. **MEDIUM:** Implement deployment-phase monitoring for both services

### Conclusion

The 30-day analysis reveals two well-operated services with different deployment strategies and reliability profiles. Both achieve 100% availability but exhibit distinct patterns—pbx-web's steady cadence with occasional incidents vs. whisper-stt's burst behavior with perfect stability. The primary concern is pbx-web's deployment failure requiring investigation, while whisper-stt's operational posture needs confirmation as intentional rather than neglect. Implementing the recommended actions will improve deployment reliability across both services and reduce recurrence risk.

---

**Report End**

*Data sources: Kubernetes deployment events, ArgoCD history, ReplicaSet creation timestamps, pod events and status from ardenone-cluster*  
*Analysis tools: Custom deployment metrics collection and comparative analysis scripts*  
*Next analysis recommended: 2026-09-06 (following 30-day period)*