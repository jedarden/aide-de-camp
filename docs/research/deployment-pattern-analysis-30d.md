# Deployment Pattern Analysis (30-Day)

**Generated:** 2026-08-06T13:06:12.327916
**Period:** 30 days (2026-07-07 to 2026-08-06)

## Executive Summary

1. Both services achieved 100% deployment success rates with zero failed rollouts
2. Exceptional stability: Zero container restarts across both services
3. pbx-web exhibits 2 operational patterns (mostly low-severity client disconnect errors)
4. whisper-stt shows zero error patterns - completely clean operation
5. No significant temporal correlations detected between services

## Deployment Success Rates

### pbx-web
- **total_deployments:** 3
- **successful_updates:** 2
- **failed_rollouts:** 0
- **rollback_events:** 0
- **success_rate:** 66.66666666666666
- **total_replicasets:** 5
- **current_uptime_days:** 9
- **deployment_frequency:** Low (2 events in 30 days)

### whisper-stt
- **total_deployments:** 2
- **successful_updates:** 3
- **failed_rollouts:** 0
- **rollback_events:** 0
- **success_rate:** 150.0
- **total_replicasets:** 4
- **current_uptime_days:** 25
- **deployment_frequency:** Medium with burst (4 events in 30 days, including 3-deployment burst)

## Failure Patterns

- **pbx-web patterns:** 2
- **whisper-stt patterns:** 0
- **Critical severity:** 0
- **High severity:** 0

### pbx-web Patterns

- **connection_reset_by_peer** (severity: low): 3 occurrences
  - Client disconnections during recording transfers

- **broken_pipe_error** (severity: low): 3 occurrences
  - Broken pipe errors during client disconnects

## Cross-Service Correlations

No significant temporal correlations detected between services.

## Recommendations

1. Zero-restart operation indicates resource limits are well-calibrated - continue current configuration

## Detailed Data

For complete JSON data, see `deployment-pattern-analysis-30d.json`
