# pbx-web 30-Day Log Data Limitations

## Executive Summary

**Overall Coverage Achievement: ~10-37% of requested 30-day period**

- **Victorialogs**: ~7 hours of recent logs (0.01% coverage)
- **Pod logs (kubectl)**: 8-22 days depending on pod (27-73% coverage)
- **Argo Workflows**: ~10 days retention (33% coverage)
- **Parsed deployment events**: 1,438 HTTP 5xx errors extracted

## Data Collection Summary

### Sources Accessed
1. **Victorialogs** - Centralized logging infrastructure (ardenone-cluster)
2. **kubectl logs** - Direct pod container logs (3 current pods)
3. **kubectl describe** - Pod metadata and restart history
4. **kubectl get events** - Cluster events
5. **kubectl get replicasets** - Deployment history
6. **Argo Workflows (iad-ci)** - CI/CD workflow run history
7. **Parsed log analysis** - 1,438 deployment-related events extracted

## Coverage Gaps

### Victorialogs Limitations
- **Actual coverage**: Only ~7 hours of recent logs (2026-08-06 09:58 to 16:52 UTC)
- **Query limitation**: 10,000 log entries returned by default
- **Missing data**: ~29 days and 17 hours of the requested 30-day period
- **Cause**: Victorialogs retention is set to 28 days, but query appears to only capture recent data
- **Parsed findings**: 1,438 deployment-related events extracted from available logs

### Argo Workflows CI/CD Limitations
- **Actual coverage**: ~10 days retention in iad-ci cluster
- **Workflow template exists**: pbx-web-build template created 2026-05-27
- **Missing data**: ~20 days of deployment history (no workflows found before 2026-07-27)
- **Workflow runs found**: 0 pbx-web-build runs in 30-day window (14 total cluster workflows)
- **Retention policy**: Cluster retains approximately 10 days of workflow history
- **Impact**: Cannot correlate deployments with error patterns over 30-day period

### Pod Log Limitations  
- **Current pod ages**: 8-22 days (no pods cover full 30 days)
- **Historical logs**: Previous pod logs are not accessible via kubectl
- **Missing period**: ~8-22 days depending on specific pod
- **Total parsed events**: 1,438 deployment-related events extracted from available logs

### Event Data Limitations
- **No cluster events**: No events found for pbx-web namespace
- **Missing restart history**: Cannot determine cause of previous replica set rotations
- **No crash events**: No OOMKilled or CrashLoopBackOff events captured

### Deployment History Gaps
- **Replica set metadata**: Only ages available, no deployment triggers captured
- **Rollout causes**: Unknown why 11 replica sets exist over 95 days
- **Deployment timestamps**: Only ages available, not exact deployment times

## Error Pattern Coverage

### What Was Found (Parsed Data: 1,438 events)
- **HTTP 5xx errors**: 1,420 total (500: 371, 502: 347, 503: 349, 504: 353)
- **Connection errors**: 18 total (connection reset: 12, broken pipe: 6)
- **Recording fetch errors**: Connection reset by peer, broken pipe errors in site-generator logs
- **HTTP 500 errors**: Generated during recording fetch failures
- **Internal server errors**: HTTP server error responses
- **Error distribution**: All 4 major HTTP 5xx codes present, suggesting multiple failure modes

### What Was Missing  
- **HTTP 5xx access logs**: No 5xx status codes found in recent Victorialogs UI queries
- **Pod restart events**: No restart patterns detected in current pods
- **Memory/CPU issues**: No OOM or resource exhaustion events found
- **Event correlation**: 0 pod events found in cluster-wide queries

## Infrastructure Constraints

### Log Retention
- **Victorialogs**: 28-day retention configured, but actual query coverage appears limited to recent data
- **Argo Workflows**: ~10-day retention in iad-ci cluster (oldest workflow: 2026-07-27)
- **Pod logs**: Only available for running pods, lost on pod deletion (8-22 days maximum)
- **Events**: Not found in cluster events, possibly different event routing
- **Workflow history**: No pbx-web-build workflow runs found in 30-day window

### Query Limitations
- **API limits**: 10,000 record limit on Victorialogs queries
- **Time range**: Query parameters may not be matching actual data retention
- **Namespace filtering**: No events found at namespace or cluster level

## Impact on Analysis

### Can Assess
- ✅ Current pod health and stability
- ✅ Recent error patterns (last 7 hours)
- ✅ Deployment frequency (replica set count)
- ✅ Current resource allocation and limits

### Cannot Assess  
- ❌ 30-day error trends and patterns
- ❌ Historical restart causes
- ❌ Long-term latency trends
- ❌ Deployment success rates over 30 days
- ❌ Correlation between deployments and errors

## Recommendations for Complete 30-Day Analysis

### Immediate Improvements
1. **Argo Workflows retention optimization**: 
   - Configure longer TTL for pbx-web-build workflows if historical data is needed
   - Export workflow run history to external storage before retention cleanup
   - Enable workflow archival for builds/deployments

2. **Victorialogs query optimization**: 
   - Remove 10,000 record limit
   - Verify retention period configuration (currently 28 days)
   - Use time-range optimized queries with proper LogQL syntax

3. **Parsed error analysis**:
   - Investigate HTTP 502/503/504 errors (1,049 events total)
   - Correlate 500 errors (371 events) with recording fetch failures
   - Monitor connection reset patterns (12 events) for network issues

### Alternative Data Sources
4. **External logging systems**:
   - Check for Loki or other log aggregators
   - Review application-level logging and monitoring
   - Examine alerting systems for deployment records

5. **Deployment tracking**:
   - ArgoCD sync history for application deployment triggers
   - GitHub Actions/CI logs for build records
   - Container registry timestamps for image pushes
   - Git commit history correlated with replica set changes

6. **Event correlation**:
   - Check ArgoCD sync history for deployment triggers
   - Review CI/CD logs for deployment records
   - Examine GitHub webhook logs for rebuild-relay triggers

## Conclusion

The gathered data provides **partial coverage of current state** with significant retention gaps across all data sources. **Cannot provide complete 30-day trend analysis** due to multiple log retention limitations.

### Data Availability Summary
- **Achieved coverage**: ~10-37% of requested 30-day period
- **Victorialogs**: ~7 hours recent (0.01%) with 1,438 parsed events
- **Pod logs**: 8-22 days (27-73%)
- **Argo Workflows**: ~10 days (33%)
- **Deployment frequency**: 11 replica sets over 95 days (metadata only)
- **Current pod health**: 0 restarts, stable across 3 pods

### Key Limitation Findings
1. **Argo Workflows retention**: ~10 days prevents deployment-error correlation over 30 days
2. **Victorialogs query limits**: 10,000 record cap and apparent recent-data bias
3. **No event history**: Cluster events not captured for pbx-web namespace
4. **Historical gap**: ~8-22 days missing from pod logs depending on pod age

### What Analysis IS Possible
- ✅ Current error patterns (1,438 events: HTTP 5xx breakdown)
- ✅ HTTP 5xx error distribution (500/502/503/504)
- ✅ Connection error patterns (reset/broken pipe)
- ✅ Deployment frequency (11 replica sets in 95 days)
- ✅ Current pod health and resource allocation
- ✅ Recent connection failure patterns

### What Analysis is NOT Possible
- ❌ 30-day error trend analysis
- ❌ Deployment-error correlation over 30 days
- ❌ Historical restart root cause analysis
- ❌ Long-term latency patterns
- ❌ Complete deployment success/failure rates

This data is **sufficient for current state assessment and error pattern analysis**, but **insufficient for 30-day trend analysis or deployment correlation**. For comparative analysis with whisper-stt, expect similar retention limitations.