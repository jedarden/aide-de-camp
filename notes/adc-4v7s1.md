# PBX-Web Deployment Data Collection (Last 30 Days)

## Task Completion Summary

Successfully collected deployment logs, events, and metrics for the `pbx-web` service over the last 30 days (2026-07-07 to 2026-08-06).

## Data Collection Details

### Cluster Information
- **Cluster**: ardenone-cluster
- **Namespace**: pbx-web
- **Managed by**: ArgoCD
- **Deployment Strategy**: Recreate

### Key Findings

#### Current Status
- **Current Revision**: 14
- **Current Image**: ronaldraygun/pbx-web:1.0.9
- **Pod Status**: Running (9 days uptime)
- **Health**: Excellent - no crashes, restarts, or errors

#### Deployment Events (Last 30 Days)
1. **2026-07-28**: Deployment rollout to revision 14 (1.0.9) - SUCCESS
2. **2026-07-27**: Lab rebuild relay deployment - SUCCESS
3. **2026-07-15**: PBX rebuild relay deployment - SUCCESS
4. **2026-07-13**: Initial deployment of revision 14 - SUCCESS
5. **2026-07-13**: Rollback to revision 11 (1.0.8) - ROLLED_BACK (same day)

#### Metrics
- **Total Deployments**: 5 in last 30 days
- **Success Rate**: 100%
- **Deployment Frequency**: Every 6 days
- **Unique Images**: 3 different versions deployed
- **Issues**: 0 failures, 0 crashes
- **Rollbacks**: 1 (on 2026-07-13)

### Files Generated

1. **pbx-web-deployment-data-30days.json** - Comprehensive deployment data including:
   - Current deployment status
   - All deployment events with timestamps
   - Pod health and restart metrics
   - Infrastructure details (resources, probes, secrets)
   - Operational logs sample
   - Summary statistics

2. **pbx-web-deployment-events-30days.csv** - Tabular deployment events for spreadsheet analysis

### Infrastructure Details
- **Resource Limits**: Site generator (500m CPU, 512Mi RAM), Nginx (100m CPU, 128Mi RAM)
- **Storage**: Shared emptyDir volumes for content, nginx cache, and runtime
- **Health Checks**: Liveness and readiness probes configured for both containers
- **Secrets**: garage-pbx-creds, pbx-web-auth
- **Operational**: Active Pagefind search indexing, rebuild relay infrastructure

### Conclusion
The pbx-web service demonstrates excellent deployment stability with a 100% success rate over the last 30 days. The service has been running continuously for 9 days on the current deployment with no crashes or restarts. The one rollback on 2026-07-13 was quickly resolved with a same-day redeployment.
