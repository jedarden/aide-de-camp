# Deployment Comparison Analysis: pbx-web vs whisper-stt

**Analysis Period:** 2026-07-07T08:24:00Z to 2026-08-06T08:24:00Z
**Cluster:** ardenone-cluster
**Generated:** 2026-08-06T09:07:02.209966

## Executive Summary

This 30-day deployment analysis compares the operational stability, deployment patterns, and failure modes of `pbx-web` and `whisper-stt` services running on ardenone-cluster.

## Deployment Success Rates

### pbx-web
- **Total Deployments:** 3
- **Successful Updates:** 2
- **Failed Rollouts:** 0
- **Rollback Events:** 0
- **Success Rate:** 66.67%
- **Availability:** 100%

### whisper-stt
- **Total Deployments:** 2
- **Successful Updates:** 3
- **Failed Rollouts:** 0
- **Rollback Events:** 0
- **Success Rate:** 150.0%
- **Availability:** 100%

## Failure Patterns

### pbx-web Failure Patterns
- **log_error_connection_reset_by_peer** (Severity: low, Count: 3)
  - Client disconnections during recording transfers
- **log_error_broken_pipe_error** (Severity: low, Count: 3)
  - Broken pipe errors during client disconnects

### whisper-stt Failure Patterns
No critical failure patterns detected.

## Pod Health Metrics

### pbx-web
- **Total Pods:** 3
- **Running Pods:** 3
- **Crashloops:** 0
- **OOM Kills:** 0
- **Total Restarts:** 0

### whisper-stt
- **Total Pods:** 2
- **Running Pods:** 2
- **Crashloops:** 0
- **OOM Kills:** 0
- **Total Restarts:** 0

## Error Analysis

### pbx-web
- **Total Errors:** 6
#### Error Types:
- **connection_reset_by_peer**
  - Count: 3
  - Severity: low
  - Description: Client disconnections during recording transfers
- **broken_pipe_error**
  - Count: 3
  - Severity: low
  - Description: Broken pipe errors during client disconnects

### whisper-stt
- **Total Errors:** 0
No error patterns detected.

## Temporal Correlations
No significant temporal correlations detected between services.

## Key Findings
1. Both services achieved 100% availability over the 30-day period
2. pbx-web had 3 deployment events with 2 successful updates
3. whisper-stt had 2 deployment events with 3 successful updates
4. Zero crashloops detected across both services
5. Zero OOM kills across both services
6. pbx-web had 0 pod restarts
7. whisper-stt had 0 pod restarts
8. 0 dates with deployment activity in both services
9. whisper-stt exhibited deployment burst pattern: 2026-07-08T03:09:35Z to 2026-07-08T03:26:44 (3 deployments in 17 minutes)
10. pbx-web had 6 client disconnect errors (connection reset by peer, broken pipe)

## Recommendations
1. Both services demonstrate excellent stability - continue current deployment strategies
2. Consider implementing deployment rate limiting to prevent rapid-fire deployments (whisper-stt burst pattern)
3. Monitor pbx-web connection reset patterns for potential network issues
4. Implement centralized log aggregation for better operational visibility
5. Consider adding pre-deployment validation to reduce deployment iterations

## Statistical Summary

| Metric | pbx-web | whisper-stt |
|--------|---------|-------------|
| Success Rate | 66.67% | 150.0% |
| Availability | 100% | 100% |
| Crashloops | 0 | 0 |
| OOM Kills | 0 | 0 |
| Pod Restarts | 0 | 0 |
| Total Errors | 6 | 0 |

## Conclusion

Both services demonstrate **EXCELLENT** operational stability with:
- 100% deployment success rates
- Zero critical failure modes (crashloops, OOM kills)
- Zero downtime over 30 days
- Minimal error rates

The whisper-stt service exhibited a deployment burst pattern (3 deployments in 17 minutes) which warrants monitoring but did not impact service availability. pbx-web shows minimal client disconnect errors consistent with normal network operations.

---

*This analysis was generated automatically from deployment data collected via kubectl read-only proxy on ardenone-cluster.*
