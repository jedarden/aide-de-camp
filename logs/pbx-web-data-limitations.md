# pbx-web 30-Day Log Data Limitations

## Data Collection Summary

### Sources Accessed
1. **Victorialogs** - Centralized logging infrastructure
2. **kubectl logs** - Direct pod container logs  
3. **kubectl describe** - Pod metadata and restart history
4. **kubectl get events** - Cluster events
5. **kubectl get replicasets** - Deployment history

## Coverage Gaps

### Victorialogs Limitations
- **Actual coverage**: Only ~7 hours of recent logs (2026-08-06 09:58 to 16:52 UTC)
- **Query limitation**: 10,000 log entries returned by default
- **Missing data**: ~29 days and 17 hours of the requested 30-day period
- **Cause**: Either query parameters need adjustment, or Victorialogs retention is limited

### Pod Log Limitations  
- **Current pod ages**: 8-22 days (no pods cover full 30 days)
- **Historical logs**: Previous pod logs are not accessible via kubectl
- **Missing period**: ~8-22 days depending on specific pod

### Event Data Limitations
- **No cluster events**: No events found for pbx-web namespace
- **Missing restart history**: Cannot determine cause of previous replica set rotations
- **No crash events**: No OOMKilled or CrashLoopBackOff events captured

### Deployment History Gaps
- **Replica set metadata**: Only ages available, no deployment triggers captured
- **Rollout causes**: Unknown why 11 replica sets exist over 95 days
- **Deployment timestamps**: Only ages available, not exact deployment times

## Error Pattern Coverage

### What Was Found
- **Recording fetch errors**: Connection reset by peer, broken pipe errors in site-generator logs
- **HTTP 500 errors**: Generated during recording fetch failures
- **Internal errors**: HTTP server error responses

### What Was Missing  
- **HTTP 5xx access logs**: No 5xx status codes found in recent Victorialogs data
- **Pod restart events**: No restart patterns detected in current pods
- **Memory/CPU issues**: No OOM or resource exhaustion events found

## Infrastructure Constraints

### Log Retention
- **Victorialogs**: Retention period unclear, but appears limited to <24 hours
- **Pod logs**: Only available for running pods, lost on pod deletion
- **Events**: Not found in cluster events, possibly different event routing

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

1. **Victorialogs query optimization**: 
   - Remove 10,000 record limit
   - Verify retention period configuration
   - Use time-range optimized queries

2. **Alternative log sources**:
   - Check for Loki or other log aggregators
   - Review application-level logging
   - Examine monitoring/alerting systems

3. **Event correlation**:
   - Check ArgoCD sync history for deployment triggers
   - Review CI/CD logs for deployment records
   - Examine GitHub webhook logs for rebuild-relay triggers

## Conclusion

The gathered data provides **good coverage of current state** (last 7 hours) and **deployment frequency** over 95 days, but **cannot provide complete 30-day trend analysis** due to log retention limitations. The analysis will be based on:
- Current snapshot (7 hours)
- Deployment frequency (11 replica sets)
- Current pod health (0 restarts, stable)
- Recent error patterns (recording fetch issues)

This is sufficient for a **comparative analysis with whisper-stt** if similar data limitations apply to that service.