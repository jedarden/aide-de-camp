# Deployment History Data Collection - Findings Summary

## Investigation Date: 2026-08-06

## Services Analyzed
- `pbx-web` (part of nixos-asterisk repo)
- `whisper-stt` (part of nixos-asterisk repo)

## Argo Workflows Status

### Workflow Templates Exist
Both services have properly configured workflow templates in the `iad-ci` cluster:

- **pbx-web-build**: Builds `ronaldraygun/pbx-web:{version}` images
- **whisper-stt-build**: Builds `ronaldraygun/whisper-stt:{version}` images

Template configurations show:
- Source: `jedarden/nixos-asterisk` repository
- Build process: Kaniko with version resolution
- Image destinations: Docker Hub with version tags

### Actual Workflow Runs: NONE
**Critical Finding**: There are **zero** workflow executions for both templates in the Argo Workflows retention period.

Query results:
```bash
kubectl get workflows -n argo-workflows \
  -l workflows.argoproj.io/workflow-template=pbx-web-build
# Result: No resources found

kubectl get workflows -n argo-workflows \
  -l workflows.argoproj.io/workflow-template=whisper-stt-build
# Result: No resources found
```

### Retention Policy Observations
The oldest workflows still retained are ~10 days old, suggesting:
- Argo Workflows retention policy: ~10 days for completed workflows
- No workflow runs have occurred for these services in at least the last 10 days

## Git Repository Evidence

Despite no CI/CD executions, VERSION files have been updated in the repository:

### pbx-web VERSION History (Last 30 Days)
```
3946d12d 2026-07-13 14:14:09 -0400 chore(pbx-web): bump VERSION to 1.0.9
83343f17 2026-07-13 18:03:32 +0000 ci: auto-bump version to 1.0.8
```
- Current VERSION: `1.0.9`
- 2 version bumps in July 2026

### whisper-stt VERSION History (Last 30 Days)
```
4b83578c 2026-07-08 03:21:24 +0000 ci: auto-bump version to 1.8.6
f6046b53 2026-07-07 23:20:50 -0400 fix(whisper-stt): bearer-auth GET/DELETE /jobs/{id} too (1.8.5)
7699f69f 2026-07-08 03:13:39 +0000 ci: auto-bump version to 1.8.4
edba1301 2026-07-07 23:13:16 -0400 fix(whisper-stt): bearer-auth the chunked upload endpoints (1.8.3)
50ce4c81 2026-07-08 03:04:30 +0000 ci: auto-bump version to 1.8.2
16b8a98e 2026-07-08 01:32:36 +0000 ci: auto-bump version to 1.8.1
3908a26c 2026-07-07 21:32:13 -0400 feat(whisper-stt): add chunked upload for large files (1.8.0)
```
- Current VERSION: `1.8.6`
- 8 version bumps between July 7-8, 2026

## Analysis

### Discrepancy: CI Infrastructure vs. Execution
The workflow templates are configured but **never triggered**. This suggests:

1. **Manual deployment process**: VERSION bumps are done manually/automatically via git commits, but the actual image builds don't go through Argo Workflows
2. **Alternative CI pipeline**: These services might be built through a different mechanism (e.g., `container-build` template, GitHub Actions, manual docker build)
3. **Missing webhook triggers**: The workflow templates may not be connected to GitHub webhooks despite VERSION changes

### Image Availability
Without workflow execution logs, we cannot determine:
- Which image tags were actually built
- Whether the tagged images exist on Docker Hub
- Deployment timestamps beyond git commit times
- Build success/failure status

## Conclusion

**Cannot retrieve deployment history data for the last 30 days as requested.**

The CI/CD infrastructure (Argo Workflows) exists but shows **zero execution history** for both services in the retention period. While VERSION files have been updated in git, the corresponding Docker image builds and deployments are not captured in the Argo Workflows system.

### Recommendations
1. Investigate whether these services use a different build mechanism
2. Check GitHub webhooks are properly configured for these workflow templates
3. Verify if manual docker builds are being performed instead of automated CI/CD
4. Consider triggering workflow executions to populate deployment history

## Data Files
- `pbx-web-deployments.json` - Empty (no workflow runs found)
- `whisper-stt-deployments.json` - Empty (no workflow runs found)
