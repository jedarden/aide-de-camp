# adc-5q8ms: 30-Day Deployment Analysis - Summary

## Task Completed
Analyzed and compared deployment histories for `pbx-web` and `whisper-stt` over the last 30 days (2026-07-08 to 2026-08-06).

## Data Collection
- Queried ardenone-cluster via kubectl-proxy (read-only access)
- Examined Deployment, ReplicaSet, and Pod resources
- Checked Argo Workflows for CI/CD history
- Investigated ArgoCD application status

## Key Findings
- **Zero failures** in both services over 30 days
- **100% success rate** for all deployments
- **Zero rollbacks** required
- **Deployment frequency:** pbx-web (~9 days), whisper-stt (~15 days)
- **whisper-stt anomaly:** 3 deployments within 17 minutes on 2026-07-08 (versions 1.8.2 → 1.8.4 → 1.8.6)
- **WorkflowTemplates unused:** Both services have Argo WorkflowTemplates defined but zero executions recorded

## Deliverables
- Full analysis report: `docs/research/adc-5q8ms-30day-deployment-analysis.md`
- Summary document: `notes/adc-5q8ms.md` (this file)

## Recommendations
1. Investigate whisper-stt rapid deployment pattern on July 8
2. Clarify CI/CD path (activate WorkflowTemplates or remove unused ones)
3. Consider deployment frequency monitoring
4. Document deployment strategy

## Tools Used
- kubectl (via Tailscale proxy to ardenone-cluster)
- jq for JSON parsing
- ArgoCD read-only API
- Argo Workflows query

## Status
✅ Complete - All data gathered, analysis completed, report generated
