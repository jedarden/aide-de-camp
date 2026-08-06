# Deployment Pattern Analysis: pbx-web vs whisper-stt
**Analysis Period:** Last 30 days (2026-07-07 to 2026-08-06)
**Generated:** 2026-08-06
**Bead:** adc-1orh1

## Executive Summary

**Critical Finding:** Both `pbx-web` and `whisper-stt` services have **broken CI/CD automation**. Despite active development with 13 commits in the last 30 days, neither service has been deployed via Argo Workflows since their workflow templates were created on 2026-05-27. The workflow templates exist but have never executed.

**Status: 🔴 Automation Failure - Manual intervention required**

---

## Methodology

### Data Sources
- **Argo Workflows (iad-ci cluster)**: Workflow execution history
- **GitHub (jedarden/nixos-asterisk)**: Git commit history and webhook configuration
- **Workflow Templates**: CI/CD pipeline definitions

### Analysis Approach
1. Extracted all workflows from iad-ci cluster
2. Cross-referenced with git commit history (last 30 days)
3. Analyzed GitHub webhook configuration
4. Compared against successfully building services (needle-ci, spaxel-build, acb-*)

---

## Findings

### 1. CI/CD Infrastructure Status

| Service | Workflow Template | Created | Runs (All-Time) | Last Run |
|---------|-------------------|---------|-----------------|----------|
| pbx-web | pbx-web-build | 2026-05-27 | **0** | Never |
| whisper-stt | whisper-stt-build | 2026-05-27 | **0** | Never |

**Comparison with working services:**
- `needle-ci`: 2 runs in last 30 days
- `spaxel-build`: 1 run in last 30 days  
- `acb-*`: 2 runs each in last 30 days
- `dashboard-site-build`: 2 runs in last 30 days

### 2. Development Activity (Last 30 Days)

#### pbx-web
- **Latest commit**: 2026-07-13 (24 days ago)
- **Current version**: 1.0.9
- **Recent commits**: 6 commits
- **Recent features**:
  - Copy-to-clipboard button for transcripts (1.0.8)
  - Timestamp inclusion when copying (1.0.9)
  - Faster transcript delivery (1.0.7)

#### whisper-stt
- **Latest commit**: 2026-07-08 (29 days ago)
- **Current version**: 1.8.6
- **Recent commits**: 7 commits
- **Recent features**:
  - Chunked upload for large files (1.8.0)
  - Upload progress bar (1.7.0)
  - Batching multiple files into one transcript (1.6.0)

### 3. Webhook Configuration

**GitHub Webhook:** `https://calls.ardenone.com/github-webhook`
- **Status**: Active
- **Events**: `push`
- **Repository**: jedarden/nixos-asterisk

**Issue:** Webhook exists but is not triggering `pbx-web-build` or `whisper-stt-build` workflows.

---

## Root Cause Analysis

### Primary Issue: Missing Workflow Trigger Configuration

The workflow templates exist but lack a triggering mechanism. Likely causes:

1. **No GitHub webhook configured for these specific services**
   - The webhook at `calls.ardenone.com/github-webhook` may only watch specific paths or branches
   - No path-based filtering rules for `pbx-web/*` and `whisper-stt/*`

2. **Workflow template mismatch**
   - Templates reference `jedarden/nixos-asterisk` repo
   - May require manual submission or different triggering mechanism

3. **Automated version bump but no build**
   - Git history shows `ci: auto-bump version to X.Y.Z` commits
   - These commits happen, suggesting the version script runs
   - But the Docker build step never executes

### Secondary Issue: No Deployment Monitoring

Neither service has been deployed since 2026-05-27, yet:
- Code continues to be committed
- Versions continue to be bumped
- No alerts or monitoring triggered

---

## Common Failure Patterns

### Pattern 1: "Zombie" CI/CD Templates
**Description:** Workflow templates exist but never execute.
**Affected:** Both pbx-web and whisper-stt
**Severity:** Critical - deployments are impossible without manual intervention

### Pattern 2: Partial Automation
**Description:** Version bumping works, but Docker builds fail silently.
**Evidence:** Git history shows successful version commits but zero workflow executions
**Impact:** Developers think CI/CD is working, but images never build

### Pattern 3: No Feedback Loop
**Description:** No alerts when deployments stop working.
**Duration:** ~70 days of silence (templates created 2026-05-27, now 2026-08-06)
**Risk:** Production runs stale code (1.0.9 for pbx-web, 1.8.6 for whisper-stt)

---

## Service-Specific Analysis

### pbx-web
**Current State:**
- Version 1.0.9 (deployed: unknown, likely 1.0.9 or older)
- Last commit: 24 days ago
- Recent pace: ~6 commits/month

**Deployment Pattern:**
- Expected: Deploy on every VERSION change
- Actual: Never deployed via CI/CD
- Gap: Unknown - no workflow execution history

### whisper-stt  
**Current State:**
- Version 1.8.6 (deployed: unknown, likely 1.8.6 or older)
- Last commit: 29 days ago
- Recent pace: ~7 commits/month

**Deployment Pattern:**
- Expected: Deploy on every VERSION change
- Actual: Never deployed via CI/CD
- Gap: Unknown - no workflow execution history

### Similarities
- Both services share the same monorepo (nixos-asterisk)
- Both have workflow templates created same day (2026-05-27)
- Both have zero workflow executions
- Both use same build pattern (Kaniko → Docker Hub)
- Both have auto-version bumping working

### Differences
- **Development velocity**: whisper-stt (7 commits) > pbx-web (6 commits)
- **Version cadence**: whisper-stt (1.8.x) faster than pbx-web (1.0.x)
- **Feature complexity**: whisper-stt (chunked uploads, batch processing) > pbx-web (UI features)

---

## Comparison with Working Services

### Services with Successful CI/CD

| Service | Runs (30d) | Template | Trigger Type |
|---------|-----------|----------|--------------|
| needle-ci | 2 | needle-ci | Manual/auto |
| spaxel-build | 1 | spaxel-build | Manual/auto |
| acb-build | 2 | acb-build | Auto |

**Key Differences:**
- Working services have webhook or cron triggers
- Working services run in different repositories
- Working services have successful execution history

---

## Timeline

```
2026-05-27: pbx-web-build and whisper-stt-build workflow templates created
2026-05-27 - 2026-07-08: Development continues, no builds triggered
2026-07-08: Latest whisper-stt commit (v1.8.6)
2026-07-13: Latest pbx-web commit (v1.0.9)
2026-08-06: Analysis performed - 0 workflow runs for both services
```

**Duration of failure:** ~70 days

---

## Actionable Recommendations

### Immediate Actions (Critical)

1. **Fix webhook trigger configuration**
   - Configure GitHub webhook to trigger on `pbx-web/*` and `whisper-stt/*` changes
   - Test webhook delivery to Argo Workflow events
   - Verify workflow template submission succeeds

2. **Manual deployment catch-up**
   - Manually trigger `pbx-web-build` workflow for version 1.0.9
   - Manually trigger `whisper-stt-build` workflow for version 1.8.6
   - Verify images build and deploy successfully

3. **Verify production versions**
   - Check running pods: Are they running current code?
   - If not, emergency deployment required

### Medium-term Actions (Important)

4. **Add deployment monitoring**
   - Alert on workflow failures > 1 hour
   - Alert on zero deployments in 7 days
   - Dashboard showing last deployment time per service

5. **CI/CD health checks**
   - Regular audits of workflow execution history
   - Automated testing of webhook triggers
   - Version drift detection (git version vs running version)

6. **Documentation**
   - Document triggering mechanism for each workflow
   - Add troubleshooting guide for failed workflows
   - Runbook for manual workflow submission

### Long-term Actions (Enhancement)

7. **Unified CI/CD pattern**
   - Standardize webhook configuration across all services
   - Use gitops pattern for workflow template triggers
   - Consider GitHub Actions → Argo workflow bridge

8. **Observability**
   - Grafana dashboard for CI/CD health
   - Prometheus metrics for workflow success rates
   - Alerting on deployment anomalies

---

## Conclusion

The analysis reveals a **critical CI/CD automation failure** affecting both `pbx-web` and `whisper-stt` services. Despite active development with 13 commits in the last 30 days, neither service has been deployed via Argo Workflows in ~70 days.

**Key takeaways:**
1. Workflow templates exist but are not triggered by webhooks
2. Development continues (version bumps, features) but deployment is broken
3. No monitoring or alerting caught this 70-day outage
4. Manual intervention required to restore automation

**Risk assessment:**
- **Current risk**: HIGH - Production may run stale code
- **Data loss**: None (git history intact)
- **Recovery effort**: Medium (configure webhook, manual deployments)
- **Prevention**: Low (add monitoring)

**Immediate priority:** Fix webhook triggers and deploy latest versions.

---

## Appendix: Data Collection Commands

```bash
# Check workflow execution history
kubectl --kubeconfig=/home/coding/.kube/iad-ci.kubeconfig \
  get workflows -n argo-workflows \
  -l workflows.argoproj.io/workflow-template-invoke=pbx-web-build

# Check git commit history
git log --all --format="%ai|%H|%s" -- pbx-web/ | head -20

# Check webhook configuration
gh api repos/jedarden/nixos-asterisk/hooks

# Manual workflow submission
kubectl --kubeconfig=/home/coding/.kube/iad-ci.kubeconfig create -f - <<EOF
apiVersion: argoproj.io/v1alpha1
kind: Workflow
metadata:
  generateName: pbx-web-build-manual-
  namespace: argo-workflows
spec:
  workflowTemplateRef:
    name: pbx-web-build
EOF
```

---

**Report completed:** 2026-08-06
**Next review:** After webhook fix and manual deployments
