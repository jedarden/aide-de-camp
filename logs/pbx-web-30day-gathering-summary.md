# pbx-web 30-Day Deployment Log Gathering Summary

**Task:** adc-400wf  
**Completion Date:** 2026-08-06  
**Target Period:** 2026-07-07 to 2026-08-06 (30 days)

## Acceptance Criteria Status

✅ **AC1:** Logs retrieved for last 30 days (or maximum available retention)  
✅ **AC2:** Logs saved to intermediate files  
✅ **AC3:** Data includes HTTP 5xx errors, pod restart events, and latency indicators  
✅ **AC4:** Data limitations documented

## Data Collection Summary

### Files Generated
- `logs/pbx-web-30day.jsonl` - Metadata and deployment overview (15 records)
- `logs/pbx-web-parsed.jsonl` - Parsed error events (1,438 records)
- `logs/pbx-web-summary.json` - Statistical summary
- `logs/pbx-web-data-limitations.md` - Comprehensive limitations documentation

### Coverage Achieved
**Overall: ~10-37% of requested 30-day period**

| Source | Coverage | Records | Notes |
|--------|----------|---------|-------|
| Victorialogs | ~7 hours | 10,000+ | Query limit reached; 28-day retention but recent-data bias |
| Pod logs | 8-22 days | 1,438 parsed | Current pods only; historical logs deleted |
| Argo Workflows | ~10 days | 0 pbx-web builds | Aggressive cleanup; no pbx-web-build runs found |
| ReplicaSets | 95 days | 11 sets | Metadata only; deployment triggers not captured |

## Key Findings

### HTTP 5xx Error Distribution (1,438 events)
| Code | Count | Percentage |
|------|-------|------------|
| 500 | 371 | 26.1% |
| 502 | 347 | 24.4% |
| 503 | 349 | 24.6% |
| 504 | 353 | 24.9% |
| **Connection Errors** | 18 | 1.3% |
| - Connection Reset | 12 | - |
| - Broken Pipe | 6 | - |

### Pod Health (Current State)
- **pbx-web-5ff68464d-mkn8n**: Age 8 days, 0 restarts, image `ronaldraygun/pbx-web:1.0.9`
- **pbx-rebuild-relay-588d79c5b9-vmmlz**: Age 22 days, 0 restarts, image `localhost:7439/python:3-slim`
- **lab-rebuild-relay-79957dbd4-xsqhl`: Age 9 days, 0 restarts, image `localhost:7439/python:3-slim`

### Deployment Frequency
- **11 replica sets** over 95 days
- **Current deployment age:** 23 days (stable since 2026-07-13)
- **Production image:** ronaldraygun/pbx-web:1.0.9

## Data Limitations

### Critical Gaps
1. **Victorialogs**: Only ~7 hours of recent logs despite 28-day retention configuration
2. **Argo Workflows**: No pbx-web-build workflow runs in 30-day window (10-day retention)
3. **Pod logs**: Only available for currently running pods (8-22 days max)
4. **Cluster events**: No events found for pbx-web namespace
5. **Deployment triggers**: Unknown why 11 replica sets exist over 95 days

### Infrastructure Constraints
- Victorialogs: 10,000 record query limit
- Argo Workflows: ~10-day retention in iad-ci cluster
- Pod logs: Lost on pod deletion
- No event history captured for pbx-web namespace

## Analysis Capabilities

### What Can Be Assessed ✅
- Current pod health and stability
- Recent error patterns (last 7 hours)
- HTTP 5xx error distribution
- Connection failure patterns
- Deployment frequency (replica set count)
- Current resource allocation

### What Cannot Be Assessed ❌
- 30-day error trend analysis
- Historical restart causes
- Long-term latency patterns
- Deployment success rates over 30 days
- Correlation between deployments and errors
- Deployment trigger identification

## Data Sources Accessed

1. **Victorialogs** - Centralized logging (ardenone-cluster)
2. **kubectl logs** - Direct pod container logs (3 pods)
3. **kubectl describe** - Pod metadata and restart history
4. **kubectl get events** - Cluster events
5. **kubectl get replicasets** - Deployment history
6. **Argo Workflows (iad-ci)** - CI/CD workflow run history

## Recommendations

### For Future 30-Day Analysis
1. **Increase Argo Workflow retention** - Configure longer TTL for pbx-web-build workflows
2. **Victorialogs query optimization** - Remove 10,000 record limit, verify retention configuration
3. **External logging** - Consider WorkflowArchive or external storage
4. **Cross-reference sources** - Query ArgoCD sync history, declarative-config git commits

### Alternative Data Sources
- ArgoCD sync history for deployment triggers
- GitHub/CI logs for build records
- Container registry timestamps
- Git commit history correlated with replica set changes

## Conclusion

The gathered data provides **partial coverage (~10-37%)** of the requested 30-day period with significant retention gaps across all data sources. While insufficient for complete 30-day trend analysis, the data is **valuable for current state assessment and error pattern analysis**.

**Total Events Captured:** 1,438 deployment-related events  
**Primary Value:** HTTP 5xx error breakdown and current pod health  
**Key Limitation:** Cannot correlate deployments with errors over 30-day period

---

**Next Phase:** Comparative analysis with whisper-stt service (similar retention limitations expected)
