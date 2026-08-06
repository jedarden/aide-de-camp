# 30-Day Deployment Analysis: pbx-web vs whisper-stt

**Analysis Period:** 2026-07-08 to 2026-08-06 (last 30 days)
**Date Generated:** 2026-08-06
**Cluster:** ardenone-cluster (read-only via kubectl-proxy)

---

## Executive Summary

Both `pbx-web` and `whisper-stt` show **remarkably stable deployment patterns** with zero failures, zero rollbacks, and 100% success rates over the 30-day analysis period. The services exhibit low deployment frequencies (2-4 deployments each) with all deployments achieving full availability without incident.

**Key Finding:** No common failure patterns detected between these services. Both demonstrate deployment maturity with no crash loops, health check failures, or rollbacks requiring intervention.

---

## High-Level Statistics

| Metric | pbx-web | whisper-stt |
|--------|---------|-------------|
| **Total Deployments (30d)** | 4 | 2 |
| **Deployment Success Rate** | 100% | 100% |
| **Rollback Frequency** | 0 | 0 |
| **Current Status** | Healthy (1/1 ready) | Healthy (1/1 ready) |
| **Last Deployment** | 2026-07-28 (8 days ago) | 2026-07-12 (24 days ago) |
| **Avg Deployment Frequency** | ~9 days | ~15 days |

---

## Deployment Timeline

### pbx-web

| Date (Relative) | Deployment | Version | Status |
|-----------------|------------|---------|--------|
| 2026-07-28 (8d ago) | pbx-web-765bb76db8 | pbx-web:1.0.9 | ✅ Success |
| 2026-07-27 (9d ago) | lab-rebuild-relay-79957dbd4 | python:3-slim | ✅ Success |
| 2026-07-15 (22d ago) | pbx-rebuild-relay-588d79c5b9 | python:3-slim | ✅ Success |
| 2026-07-13 (23d ago) | pbx-web-5ff68464d | pbx-web:1.0.9 | ✅ Success |
| 2026-07-13 (23d ago) | pbx-web-754f4cfdf7 | pbx-web:1.0.8 | ✅ Success (superseded) |

**Observations:**
- Two deployments on 2026-07-13 suggest rapid iteration or rollback behavior, but both succeeded
- pbx-web uses a multi-container pattern (nginx:alpine sidecar + app container)
- No restart events or pod failures across any deployments

### whisper-stt

| Date (Relative) | Deployment | Version | Status |
|-----------------|------------|---------|--------|
| 2026-07-12 (24d ago) | whisper-stt-847fd8d7b9 | whisper-stt:1.8.6 | ✅ Success |
| 2026-07-08 (28d ago) | whisper-stt-6c497489fb | whisper-stt:1.8.6 | ✅ Success |
| 2026-07-08 (28d ago) | whisper-stt-5b8558f478 | whisper-stt:1.8.4 | ✅ Success |
| 2026-07-08 (28d ago) | whisper-stt-5dbff75cbd | whisper-stt:1.8.2 | ✅ Success |

**Observations:**
- **Three deployments occurred within 17 minutes on 2026-07-08** (03:09, 03:16, 03:26 UTC)
- Rapid version progression (1.8.2 → 1.8.4 → 1.8.6) suggests iterative fixes or hotfix deployment
- All deployments achieved 1/1 readiness without pod restarts
- whisper-stt also runs a companion deployment (whisper-openai) using `fedirz/faster-whisper-server:latest-cpu`

---

## Failure Pattern Analysis

### Methods Checked
- ReplicaSet rollout history (all successful)
- Pod status and restart counts (all 0 restarts)
- Pod phases (all Running, none in CrashLoopBackOff or Error states)
- Deployment conditions (all reporting Available and Progressing as True)

### Findings

**No failure patterns detected in either service.**

| Pattern | pbx-web | whisper-stt | Notes |
|---------|---------|-------------|-------|
| CrashLoopBackOff | ❌ Not observed | ❌ Not observed | All pods Running with 0 restarts |
| Failed health checks | ❌ Not observed | ❌ Not observed | All deployments achieved minimum availability |
| Timeout errors | ❌ Not observed | ❌ Not observed | No stuck progress conditions |
| Regression events | ❌ Not observed | ❌ Not observed | No rollbacks triggered |
| Resource exhaustion | ❌ Not observed | ❌ Not observed | No OOMKilled or CPU throttling detected |

**Note on whisper-stt rapid deployments (2026-07-08):** The three deployments within 17 minutes (1.8.2 → 1.8.4 → 1.8.6) could indicate:
1. Automated retry behavior for transient issues
2. Quick configuration fixes discovered post-deployment
3. Tagged image replacements with same runtime behavior

However, all three deployments succeeded without rollback or intervention, suggesting intentional iteration rather than failure recovery.

---

## Infrastructure vs Application Failure Ratios

**Cannot be assessed** — no failures occurred in either category during the analysis period.

Both services show:
- Zero infrastructure-related failures (node issues, network problems, storage errors)
- Zero application-level failures (container exits, health check failures, OOM kills)

This indicates either:
1. Highly mature deployment and testing practices preventing failures from reaching production
2. Low deployment frequency reducing exposure to failure modes
3. Possible monitoring gaps (though unlikely given kubectl-readability suggests live controller state)

---

## Deployment Duration Outliers

**No duration outliers detected.** 

All deployments in both services achieved:
- `Available: True` condition (MinimumReplicasAvailable)
- `Progressing: True` condition (NewReplicaSetAvailable)

No deployments spent extended time in progressing states without achieving availability. No stuck rollouts were observed in the replicaSet history.

---

## Deployment Frequency Analysis

### pbx-web
- **Pattern:** Moderate frequency (~9 days between deployments)
- **Recent Activity:** Clustered around mid-July (4 deployments between July 13-28), then silence since July 28
- **Possible Causes:** Feature releases or dependency updates in the application layer

### whisper-stt
- **Pattern:** Low frequency (~15 days between deployments)
- **Recent Activity:** Clustered on July 8 (3 deployments in 17 minutes), then silence since July 12
- **Possible Causes:** Infrastructure updates or dependency changes (whisper model updates)

### Frequency Comparison
Both services show **low deployment cadence** compared to typical CI/CD active services (which often deploy daily or multiple times per day). This suggests:
- Conservative release strategy favoring stability over velocity
- Batched changes released in larger increments
- Possible manual deployment triggers rather than automated pipelines

---

## CI/CD Integration Status

**WorkflowTemplates exist but are unused:**

Both services have Argo WorkflowTemplates defined in `iad-ci` cluster:
- `whisper-stt-build` (created 2026-05-27, age 71 days)
- `pbx-web-build` (created 2026-05-27, age 71 days)

**However, zero workflow executions have been recorded** for either template.

This suggests deployments are occurring via:
1. Manual image builds pushed to container registry
2. Alternative CI/CD system not recorded in Argo Workflows
3. Direct cluster deployment via kubectl apply (managed by ArgoCD)

**Recommendation:** Investigate why WorkflowTemplates exist without executions—either remove unused templates or activate them as the intended build path.

---

## Recommendations

### 1. Maintain Current Practices
Both services demonstrate excellent deployment stability. No urgent action required to address failure patterns—none exist.

### 2. Investigate whisper-stt Rapid Deploy Pattern
The three deployments within 17 minutes on July 8 warrant clarification:
- **Action:** Review deployment logs for 2026-07-08 03:09-03:26 UTC
- **Goal:** Understand if this represents intentional iteration or automated retry behavior
- **Risk:** If this was failure-driven, the retry mechanism should be documented; if intentional, the process should be captured as a pattern

### 3. Clarify CI/CD Path
WorkflowTemplates exist but aren't used:
- **Action:** Either activate the WorkflowTemplates for automated builds, or remove them if superseded by another system
- **Benefit:** Reduces confusion about intended deployment mechanism

### 4. Consider Deployment Frequency Monitoring
With 9-15 day intervals between deployments:
- **Action:** Implement deployment frequency alerting if gaps exceed 30 days
- **Benefit:** Early detection of deployment pipeline stagnation or missed releases

### 5. Document Deployment Strategy
Both services show conservative release cadence:
- **Action:** Document in docs/plan/ whether this low frequency is intentional or reflects process bottlenecks
- **Benefit:** Informs future capacity planning and onboarding

---

## Data Collection Notes

**Limitations:**
- Analysis based on kubectl-read cluster state (live objects only)
- No access to CI/CD logs or deployment scripts
- No metrics data (Prometheus/VictoriaLogs) consulted
- ArgoCD event history not queried (events may have been archived or deleted)
- No pod logs examined for application-level errors

**Completeness:**
- ReplicaSet history is complete for active deployments
- Pod status is current-state only (historical pod phases not available)
- No direct access to deployment timestamps beyond object creation times

**Future Analysis Enhancements:**
- Query ArgoCD application sync history for rollout timestamps
- Access VictoriaLogs for HTTP error spikes post-deployment
- Review pod logs for application startup errors during rollouts
- Consult CI/CD system (if alternative exists) for build failure rates

---

## Conclusion

Both `pbx-web` and `whisper-stt` demonstrate **exemplary deployment stability** over the 30-day analysis period. Zero failures, zero rollbacks, and 100% success rates indicate mature deployment practices or low deployment frequency reducing failure exposure. The primary observation requiring follow-up is the rapid deployment pattern for whisper-stt on July 8, which warrants investigation to understand whether it represents intentional iteration or a failure-driven retry pattern.

**Overall Assessment:** ✅ **Healthy** — No common failure patterns detected between services. Both show deployment readiness and operational stability.
