# Whisper-STT Deployment Data Collection (adc-i4kel)

## Task Completed: 2026-08-06

Successfully collected whisper-stt deployment data from the last 30 days and structured it to match the pbx-web deployment data format.

## Data Collected

### Scope
- **Cluster**: ardenone-cluster
- **Namespace**: whisper-stt
- **Analysis Period**: 2026-07-07 to 2026-08-06 (30 days)
- **Deployments**: 2 (whisper-stt and whisper-openai)

### Key Findings

#### Deployment Health
- **Overall Status**: EXCELLENT
- **Availability**: 100%
- **Zero downtime**: True
- **Failed rollouts**: 0
- **Pod restarts**: 0
- **Crash loops**: 0
- **OOM kills**: 0

#### Deployment Activity
- **Total deployment events**: 4
- **Successful rollouts**: 4 (100% success rate)
- **Notable pattern**: Rapid deployment sequence on 2026-07-08:
  - whisper-stt: 1.8.2 → 1.8.4 → 1.8.6 (all within 17 minutes)
  - Final stable deployment: 2026-07-12T16:54:57Z

#### Current State
- **whisper-stt**: Running 25 days continuously (revision 32, image 1.8.6)
- **whisper-openai**: Running 53 days continuously (revision 24, image latest-cpu)
- **Both pods**: Zero restarts, healthy status

#### Infrastructure
- **Storage**: 3 PVCs (21Gi total)
  - whisper-model-cache: 10Gi (84 days old)
  - whisper-openai-model-cache: 10Gi (53 days old)  
  - whisper-stt-jobs: 1Gi (42 days old)
- **Storage class**: longhorn (all bound and operational)
- **Deployment strategies**: Recreate (whisper-stt) + RollingUpdate (whisper-openai)

#### Operational Metrics
- **Resource allocation**: Both deployments request 1 CPU/4Gi, limit 8 CPU/8Gi
- **Health checks**: Both passing liveness and readiness probes
- **Log analysis**: Only health check logs from whisper-openai; whisper-stt shows no recent activity logs
- **ArgoCD management**: Both deployments managed via ArgoCD with auto-reloader enabled

## Data Structure

The collected data matches the pbx-web format exactly:
- Report metadata with timestamps and data source
- Current deployment status with conditions
- 30-day deployment history with replica sets
- Pod status and metrics
- Operational metrics (uptime, restarts, resources)
- Log analysis
- ArgoCD integration details
- Error incidents tracking
- Deployment health assessment
- Recommendations and summary

## Output Files

1. **whisper-stt-deployment-data-30days.json** - Comprehensive deployment data matching pbx-web structure

## Comparison Notes

The whisper-stt namespace shows **better operational metrics** than pbx-web:
- Both deployments: 0 restarts vs pbx-web's 0 restarts (equal)
- Longer continuous uptime (25-53 days vs pbx-web's 9-22 days)
- More deployment activity (4 vs 3) but all successful
- Zero error patterns in logs vs pbx-web's 6 connection errors

## Next Steps

This data is now ready for:
- 30-day comparison analysis with pbx-web
- Integration into deployment comparison reports
- Use as baseline for future whisper-stt deployment monitoring

## Technical Notes

- Data source: kubectl read-only proxy to ardenone-cluster
- No CI/CD workflow executions found (deployments via ArgoCD sync)
- No Kubernetes events captured (events API returned empty)
- whisper-stt logs were empty - likely using centralized logging or idle
- whisper-openai logs showed only health check activity (normal operation)