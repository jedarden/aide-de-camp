# pbx-web Log Retrieval Summary

## Execution Details
- **Task**: Execute log retrieval for pbx-web service
- **Date**: 2026-08-06
- **Cluster**: ardenone-cluster (pbx-web does not exist on apexalgo-iad)
- **Namespace**: pbx-web
- **Script**: `scripts/get-pbx-web-logs-direct.sh`
- **Output File**: `logs/pbx-web-ardenone-cluster/pbx-web-raw-20260806-203449.jsonl`

## Results Summary
✅ **Script executed successfully**
- **Total log lines captured**: 5,329
- **File size**: 1,039,530 bytes (~1 MB)
- **Pods processed**: 3 pods with 4 containers total
- **Output format**: JSONL with structured log entries

## Pod Inventory
| Pod Name | Age | Restarts | Containers | Status |
|----------|-----|----------|------------|--------|
| pbx-rebuild-relay-588d79c5b9-vmmlz | 22 days (2026-07-15) | 0 | relay | Running |
| lab-rebuild-relay-79957dbd4-xsqhl | 10 days (2026-07-27) | 0 | relay | Running |
| pbx-web-5ff68464d-mkn8n | 9 days (2026-07-28) | 0 | site-generator, nginx | Running |

## Actual Time Coverage
- **Requested**: 30 days (2026-07-07 to 2026-08-06)
- **Actual captured**: ~11 hours (2026-08-06 05:36:19 to 16:34:49)
- **Coverage gap**: Only 0.015% of requested time period
- **Earliest log**: 2026-08-06T05:36:19.704787586-04:00
- **Latest log**: 2026-08-06T16:34:49.704317890-04:00

## Pod Events History
**Events found**: 1 event
- `nodeAssigned` (2026-08-06T20:31:49Z): announcing from node "k3s-server-a" with protocol "layer2"

**Notable findings**:
- No OOMKilled events
- No CrashLoopBackOff events
- No pod restart events (all pods show 0 restarts)
- Very minimal event activity in namespace

## Log Content Analysis
### Health Check Activity
All pods show regular health check activity:
- **Lab rebuild-relay**: Regular `/health` requests (HTTP 200 responses)
- **PBX rebuild-relay**: Regular `/health` requests (HTTP 200 responses)  
- **PBX-web nginx**: Regular kube-probe health checks (HTTP 200 responses)

### Application Errors Found
From the pbx-web-5ff68464d-mkn8n site-generator container:
```
[Reading languages]
Discovered 1 language: en
[Building search indexes]
Total: Indexed 1 language, Indexed 197 pages, Indexed 7592 words, Indexed 1 filter, Indexed 0 sorts
Finished in 1.758 seconds

[pbx-web] recording fetch error for 1785960497.546/20260805-200817_19142698463_1785960497.546.wav: 
[Errno 104] Connection reset by peer

Exception occurred during processing of request from ('127.0.0.1', 42430)
Traceback (most recent call last):
  File "/app/server.py", line 139, in _serve_recording
    self.wfile.write(chunk)
  ...
ConnectionResetError: [Errno 104] Connection reset by peer

BrokenPipeError: [Errno 32] Broken pipe
```

## Execution Errors Encountered

### 1. Original Script Timestamp Bug
The `fetch-pbx-web-logs.sh` script had a critical timestamp conversion bug:
```
error: parsing time "1783382400" as "2006-01-02T15:04:05Z07:00": 
cannot parse "382400" as "-"
```
**Impact**: Only captured kubectl error messages instead of actual logs

### 2. Cluster Location Confusion
**Issue**: Task specification mentioned "apexalgo-iad cluster"
**Reality**: pbx-web service only exists on ardenone-cluster
- No pbx-web namespace found on apexalgo-iad
- All pbx-web workloads run on ardenone-cluster

### 3. Limited Log Retention
**Issue**: kubectl logs only returns ~11 hours despite pods being 9-22 days old
**Possible causes**:
- Default kubectl log limit (may need `--limit-bytes` or `--tail`)
- Container log rotation policies
- Log volume limits set at container/pod level

## Key Findings

### Log Retention Limitations
1. **Short retention window**: Only ~11 hours available despite pods running for 9-22 days
2. **No historical logs**: All pods have 0 restarts, so no previous container logs available
3. **No event history**: Only 1 recent event, minimal namespace activity

### Operational Health
1. **Pods are healthy**: All pods running with 0 restarts
2. **Health checks passing**: Regular successful health checks across all pods
3. **Network issues**: Some storage backend connection errors (Connection reset by peer)

### Data Gaps
1. **Time coverage**: 29.96 days missing from requested 30-day window
2. **Event history**: No historical events available
3. **Previous logs**: No crash/restart history to analyze

## Recommendations

1. **Fix timestamp bug**: Update `fetch-pbx-web-logs.sh` date conversion function (line 270)
2. **Set realistic expectations**: 30-day log retention may not be available via kubectl logs
3. **Check log limits**: Investigate container log rotation policies and volume limits
4. **Central logging**: Consider using VictoriaLogs or other centralized logging for long-term retention
5. **Monitor storage errors**: Investigate the "Connection reset by peer" errors in site-generator

## Files Created
- ✅ `logs/pbx-web-ardenone-cluster/pbx-web-raw-20260806-203449.jsonl` (1,039,530 bytes, 5,329 lines)
- ✅ `scripts/get-pbx-web-logs-direct.sh` (new script for direct log retrieval)
- ⚠️  `logs/pbx-web-ardenone-cluster/pbx-web-logs-20260806-203346.jsonl` (defective, timestamp parsing errors only)

## Next Steps
- Analyze the 11 hours of captured logs for error patterns
- Investigate storage backend connection issues
- Configure proper log retention for historical analysis
- Set up monitoring for event tracking in pbx-web namespace
