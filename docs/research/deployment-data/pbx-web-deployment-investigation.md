# pbx-web Deployment Investigation (Last 30 Days)

## Task
Retrieve pbx-web deployment logs for the last 30 days (2026-07-07 to 2026-08-06).

## Methodology
1. Queried Argo Workflows in `iad-ci` cluster for `pbx-web-build` template runs
2. Searched for any workflows with "pbx" in the name (case-insensitive)
3. Verified the workflow template exists and examined its metadata
4. Checked all workflow templates to confirm pbx-web-build exists

## Findings

### Key Result: **No Deployment Runs Found**

- **Workflow template exists**: `pbx-web-build` was created on 2026-05-27
- **Zero workflow runs**: No recorded executions in the last 30 days
- **Zero workflow runs**: No recorded executions ever (in current workflow history)

### Implications
This finding suggests pbx-web is deployed through one of these mechanisms:
1. **Manual deployment** - Direct deployment without CI/CD automation
2. **Alternative CI/CD** - Deployed through a different system (GitHub Actions, GitLab CI, etc.)
3. **Different cluster** - Deployed directly to target cluster without iad-ci workflow
4. **No recent deployments** - The service has not been redeployed in the last 30 days

### Context
- pbx-web is part of the `nixos-asterisk` repository
- The workflow template was created 2+ months ago but never executed
- Other similar services (whisper-stt-build) also exist as templates but may have similar lack of runs

## Data Artifacts
- **Raw data**: `docs/research/deployment-data/pbx-web-deployments-30days.json`
- **Query**: `kubectl get workflows -n argo-workflows -l workflows.argoproj.io/workflow-template-ref-name=pbx-web-build`

## Next Steps (Optional)
1. Check nixos-asterisk repository for deployment patterns
2. Query the target cluster directly for deployment events
3. Check for alternative CI/CD configurations
4. Verify if pbx-web is actively maintained/deployed

## Related Tasks
- This task (adc-hveo4) was the initial data retrieval task
- Similar task exists for whisper-stt (see `whisper-stt-raw-workflows.json`)
