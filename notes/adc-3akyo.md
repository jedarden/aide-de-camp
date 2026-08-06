# Deployment Pattern Analysis - PBX-Web vs Whisper-STT (Bead adc-3akyo)

## Task Completion Summary

Completed comprehensive 30-day deployment pattern analysis comparing pbx-web and whisper-stt services running on ardenone-cluster.

## Analysis Scope

### Input Datasets
- `docs/research/pbx-web-deployments-30d.json` - 30-day pbx-web deployment data
- `docs/research/whisper-stt-deployments-30d.json` - 30-day whisper-stt deployment data

### Output Artifacts
- `docs/research/deployment-analysis-30d.json` - Machine-readable detailed analysis
- `docs/research/deployment-analysis-30d.md` - Human-readable comprehensive report
- `docs/research/deployment_analysis_script.py` - Analysis automation script

## Key Findings

### Deployment Success Rates
- **PBX-Web:** 100% success rate (2 deployment events)
- **Whisper-STT:** 100% success rate (3 deployment events)
- **Both services:** Zero failed rollouts, zero rollbacks, zero crash loops, zero OOM kills

### Failure Patterns Identified (3 total)

#### PBX-Web (2 patterns)
1. **connection_reset_by_peer** (Severity: low, Count: 3)
   - Client disconnections during recording transfers
   - Minimal impact - expected behavior when clients cancel downloads

2. **broken_pipe_error** (Severity: low, Count: 3)
   - Broken pipe errors during client disconnects
   - Affected component: site-generator

#### Whisper-STT (1 pattern)
1. **burst_deployment** (Severity: info)
   - 2026-07-08: 3 deployments in 17 minutes (03:09:35Z to 03:26:44Z)
   - Indicates potential deployment process optimization opportunity

### Correlation Analysis (2 correlations detected)

1. **Strategy Correlation:** Both services use Recreate deployment strategy
2. **Cluster Correlation:** Both services run on ardenone-cluster

### Statistical Summary

#### Deployment Velocity
- PBX-Web: 14 revisions (lower velocity, stable codebase)
- Whisper-STT: 32 revisions (higher velocity, active development)

#### Operational Metrics
- Restarts per deployment: 0.00 for both services
- Rollback rate: 0 events for both services
- Deployment frequency: 5 events (pbx-web) vs 4 events (whisper-stt) in 30 days

#### Current Uptime
- PBX-Web: 9 days continuous
- Whisper-STT: 25 days continuous

### Timeline Analysis

#### PBX-Web Deployment Events (5)
- 2026-07-13T18:07:55Z: replicaset_created - pbx-web-754f4cfdf7 (Revision 11)
- 2026-07-13T18:18:07Z: replicaset_created - pbx-web-5ff68464d (Revision 14)
- 2026-07-15T03:24:40Z: replicaset_created - pbx-rebuild-relay-588d79c5b9 (Revision 5)
- 2026-07-27T17:56:07Z: replicaset_created - lab-rebuild-relay-79957dbd4 (Revision 2)
- 2026-07-28T17:05:51Z: replicaset_created - pbx-web-765bb76db8 (Revision 13)

#### Whisper-STT Deployment Events (4)
- 2026-07-08T03:09:35Z: replicaset_created - whisper-stt-5dbff75cbd (Revision 29)
- 2026-07-08T03:16:13Z: replicaset_created - whisper-stt-5b8558f478 (Revision 30)
- 2026-07-08T03:26:44Z: replicaset_created - whisper-stt-6c497489fb (Revision 31)
- 2026-07-12T16:53:42Z: replicaset_created - whisper-stt-847fd8d7b9 (Revision 32)

### Cross-Service Incident Correlation

**No cross-service failure correlations detected.** Services operate independently with no temporal failure propagation between them. The burst deployment pattern in whisper-stt (2026-07-08) did not precede or correlate with any pbx-web issues.

## Recommendations

### Operational
- Continue current Recreate deployment strategy for single-pod services
- Maintain current operational procedures - excellent stability demonstrated
- Zero incidents across both services indicates robust configuration

### Whisper-STT Specific
- **Investigate deployment burst pattern:** 3 deployments in 17 minutes on 2026-07-08
- Consider pre-deployment validation to prevent rapid-fire deployments
- Higher deployment velocity (32 vs 14 revisions) indicates active development
- Implement log aggregation for better operational visibility

### PBX-Web Specific
- **Monitor connection reset errors:** 6 errors in 30 days (3 connection reset, 3 broken pipe)
- Lower deployment velocity may indicate stable codebase or slower iteration
- Continue monitoring client disconnect patterns during recording transfers

## Conclusion

Both services demonstrate **excellent deployment stability** with:
- 100% deployment success rates
- Zero failures, rollbacks, or critical incidents
- Identical deployment strategies (Recreate)
- Shared cluster infrastructure (ardenone-cluster)

**Primary difference is deployment velocity:**
- Whisper-STT: Higher deployment frequency (32 revisions) with burst deployment pattern
- PBX-Web: Lower deployment frequency (14 revisions) with minor client disconnect errors

**Operational assessment:** No cross-service failure correlations detected, suggesting independent operation and resilience. Both services are production-ready with robust deployment configurations.

## Acceptance Criteria Status

✅ **Comparison Complete:** Direct metrics comparing both services side-by-side (comprehensive table included)
✅ **Patterns Identified:** 3 distinct failure patterns documented with evidence (2 pbx-web, 1 whisper-stt)
✅ **Correlations Checked:** Timeline analysis for cross-service incident correlation (2 correlations, 0 failure propagations)
✅ **Structured Output:** Analysis summary saved to both markdown and JSON formats containing:
  - Success rate percentages (both 100%)
  - Top failure types with counts (connection reset, broken pipe, burst deployment)
  - Timeline of correlated events (no failure correlations, 2 operational correlations)
  - Statistical summary (restarts per deployment, rollback rate, deployment frequency, revision velocity)

---

**Analysis Period:** 2026-07-07 to 2026-08-06 (30 days)
**Cluster:** ardenone-cluster
**Generated:** 2026-08-06T12:57:48Z
**Bead:** adc-3akyo
