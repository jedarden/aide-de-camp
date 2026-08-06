# Task adc-3nxqu: Deployment History Data Collection - Findings

## Task Objective
Collect the last 30 days of deployment history for `pbx-web` and `whisper-stt` from CI/CD pipeline logs (Argo Workflows).

## Key Finding: No CI/CD Workflow Runs Exist

**Critical Issue**: There are **ZERO** Argo Workflow runs for `pbx-web-build` and `whisper-stt-build` templates in the iad-ci cluster.

### Verified Facts
- Workflow templates exist: `pbx-web-build` and `whisper-stt-build` (created 2026-05-27)
- No workflow executions have occurred for these templates
- Checked all workflows in argo-workflows namespace - none reference these templates
- Other services (needle-ci, seam-ci, armor-build, etc.) have recent runs, but not pbx-web or whisper-stt

### Implication
These services have **not been built through the CI/CD pipeline** in the last 30 days (or ever). The images may have been:
1. Built manually outside the pipeline
2. Deployed from existing images without rebuilds
3. Using the CI/CD pipeline but workflow runs were cleaned up (unlikely given TTL settings)

## Alternative Data Sources

### 1. Git Commit Logs (declarative-config)
Location: `data/pbx-web-logs.jsonl` and `data/whisper-stt-logs.jsonl`

These track git commits that modified deployment manifests:
- pbx-web: 10 commits from 2026-07-13 to 2026-08-04 (22 days)
- whisper-stt: 7 commits from 2026-07-07 to 2026-08-04 (28 days)

**Limitations**: These track configuration changes, not actual image builds or deployments.

### 2. Kubernetes Deployment Events
Location: `docs/research/deployment-data/pbx-web-deployments.json` and `whisper-stt-deployments.json`

These track ReplicaSet creation events (actual deployments):
- pbx-web: 5 deployments from 2026-07-13 to 2026-07-28 (15 days coverage)
- whisper-stt: 5 deployments from 2026-06-14 to 2026-07-12 (out of 30-day window)

**Limitations**: Incomplete coverage - whisper-stt's latest deployment is 25 days old.

### 3. Container Registry
Could query Docker Hub for `ronaldraygun/pbx-web` and `ronaldraygun/whisper-stt` image tags and build timestamps.

## Recommendation

Since the task acceptance criteria specifically requires querying "CI/CD logs (Argo Workflows)", and these logs do not exist, the task **cannot be completed as specified**.

**Alternative approaches**:
1. Document that CI/CD logs don't exist and provide the git commit logs as proxy data
2. Extract Kubernetes deployment events to fill the 30-day window
3. Query container registry for image build history

## Next Steps

The task should be updated to:
1. Acknowledge that CI/CD workflow logs don't exist for these services
2. Specify an alternative acceptable data source (git commits, Kubernetes events, or container registry)
3. Or trigger a CI/CD build for these services to generate the workflow logs
