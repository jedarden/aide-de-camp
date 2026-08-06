# PBX-Web vs Whisper-STT Deployment Analysis (30-Day)

**Generated:** 2026-08-06T12:57:48.905088

## Executive Summary

### Service Comparison Metrics

| Metric | PBX-Web | Whisper-STT | Winner |
|--------|---------|-------------|--------|
| Success Rate | 100.0% | 100.0% | Tie |
| Total Deployments | 2 | 3 | Whisper-STT |
| Pod Restarts | 0 | 0 | Tie |
| Crash Loops | 0 | 0 | Tie |
| OOM Kills | 0 | 0 | Tie |
| Rollbacks | 0 | 0 | Tie |
| Revision Count | 14 | 32 | Whisper-STT |
| Current Uptime | 9 days continuous | 25 days continuous | Whisper-STT |
| Deployment Strategy | Recreate | Recreate | Tie |
| Log Errors | 6 | 6 | Whisper-STT |

### Key Findings

#### Deployment Stability
- **PBX-Web:** 100.0% success rate with 2 deployment events
- **Whisper-STT:** 100.0% success rate with 3 deployment events
- **Both services:** Zero failed rollouts, zero rollbacks, zero crash loops, zero OOM kills

#### Failure Patterns Identified

**PBX-Web Patterns:**
- **log_error_connection_reset_by_peer** (Severity: low): Client disconnections during recording transfers - Count: 3
- **log_error_broken_pipe_error** (Severity: low): Broken pipe errors during client disconnects - Count: 3

**Whisper-STT Patterns:**
- **burst_deployment** (Severity: info): 2026-07-08T03:09:35Z to 2026-07-08T03:26:44 (3 deployments in 17 minutes)

### Correlation Analysis

Cross-service correlations detected:

#### strategy_correlation
Both services use Recreate deployment strategy

#### cluster_correlation
Both services run on cluster: ardenone-cluster

### Statistical Summary

**Restarts per Deployment:**
- PBX-Web: 0.00
- Whisper-STT: 0.00

**Rollback Rate:**
- PBX-Web: 0 events
- Whisper-STT: 0 events

**Deployment Frequency (30-day):**
- PBX-Web: 5 events
- Whisper-STT: 4 events

**Revision Velocity:**
- PBX-Web: 14 revisions
- Whisper-STT: 32 revisions

### Timeline Analysis

**PBX-Web Deployment Events:**
- 2026-07-13T18:07:55Z: replicaset_created - pbx-web-754f4cfdf7 (Revision 11)
- 2026-07-13T18:18:07Z: replicaset_created - pbx-web-5ff68464d (Revision 14)
- 2026-07-15T03:24:40Z: replicaset_created - pbx-rebuild-relay-588d79c5b9 (Revision 5)
- 2026-07-27T17:56:07Z: replicaset_created - lab-rebuild-relay-79957dbd4 (Revision 2)
- 2026-07-28T17:05:51Z: replicaset_created - pbx-web-765bb76db8 (Revision 13)

**Whisper-STT Deployment Events:**
- 2026-07-08T03:09:35Z: replicaset_created - whisper-stt-5dbff75cbd (Revision 29)
- 2026-07-08T03:16:13Z: replicaset_created - whisper-stt-5b8558f478 (Revision 30)
- 2026-07-08T03:26:44Z: replicaset_created - whisper-stt-6c497489fb (Revision 31)
- 2026-07-12T16:53:42Z: replicaset_created - whisper-stt-847fd8d7b9 (Revision 32)

### Log Analysis

**PBX-Web:**
- Total log lines: 2761
- Errors detected: 6
- Error types: connection_reset_by_peer, broken_pipe_error

**Whisper-STT:**
- Total log lines: 0
- Errors detected: 0
- Error types: None

## Recommendations

### Operational
- Both services show excellent stability with 100% success rates
- Continue current Recreate deployment strategy for single-pod services
- Zero incidents across both services indicates robust configuration

### Whisper-STT Specific
- Investigate deployment burst pattern: 2026-07-08T03:09:35Z to 2026-07-08T03:26:44 (3 deployments in 17 minutes)
- Consider pre-deployment validation to prevent rapid-fire deployments
- Whisper-STT shows higher deployment velocity (32 vs 14 revisions)
- Consider log aggregation for better operational visibility

### PBX-Web Specific
- Monitor connection reset errors (6 errors in 30 days)
- Lower deployment velocity may indicate stable codebase or slower iteration
- Continue monitoring client disconnect patterns

## Conclusion

Both services demonstrate **excellent deployment stability** with:
- 100% deployment success rates
- Zero failures, rollbacks, or critical incidents
- Identical deployment strategies (Recreate)
- Shared cluster infrastructure

The primary difference is deployment velocity:
- **Whisper-STT:** Higher deployment frequency (32 revisions) with burst deployment pattern
- **PBX-Web:** Lower deployment frequency (14 revisions) with minor client disconnect errors

No cross-service failure correlations were detected, suggesting independent operation and resilience.
