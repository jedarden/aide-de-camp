# pbx-web Log Retrieval Summary

## Execution Details
- **Date**: 2026-08-06
- **Cluster**: ardenone-cluster (pbx-web namespace does not exist on apexalgo-iad)
- **Namespace**: pbx-web
- **Script**: fetch-pbx-web-logs.sh
- **Command**: `./scripts/fetch-pbx-web-logs.sh --cluster ardenone-cluster --namespace pbx-web --days 30 --include-history --format jsonl --output-dir logs/pbx-web-ardenone-cluster --verbose`

## Results
- **Status**: ✅ Script executed successfully
- **Pods Processed**: 3 pods
- **Output Format**: JSONL (logs/pbx-web-ardenone-cluster/pbx-web-logs-20260806-202715.jsonl)
- **File Size**: 2,496 bytes

## Pod Inventory
1. **pbx-rebuild-relay-588d79c5b9-vmmlz**
   - Age: 22 days (created 2026-07-15)
   - Restarts: 0
   - Container: relay
   - Status: Running

2. **lab-rebuild-relay-79957dbd4-xsqhl**
   - Age: 10 days (created 2026-07-27)
   - Restarts: 0
   - Container: relay
   - Status: Running

3. **pbx-web-5ff68464d-mkn8n**
   - Age: 9 days (created 2026-07-28)
   - Restarts: 0
   - Containers: site-generator, nginx
   - Status: Running

## Actual Time Coverage
- **Requested**: 30 days (2026-07-07 to 2026-08-06)
- **Actual**: 22 days (limited by oldest pod age: 2026-07-15)
- **Coverage Gap**: 8 days at start of period (2026-07-07 to 2026-07-15)

## Pod Events History
- **Events Found**: No events recorded in pbx-web namespace
- **Restart Events**: None (all pods showing 0 restarts)
- **OOMKilled Events**: None
- **CrashLoopBackOff**: None

## Log Content Issues
### Script Timestamp Parsing Error
The JSONL output contains timestamp parsing errors in the metadata:
```
error: parsing time "1783382400" as "2006-01-02T15:04:05Z07:00": cannot parse "382400" as "-"
```

This is a script bug in the date conversion function (line 270 in fetch-pbx-web-logs.sh). The `--since-time` parameter expects seconds but the conversion is incorrect.

### Application Log Content
Despite the metadata error, actual pod logs show:
- **Health checks**: Regular `/health` requests with 200 responses
- **Application errors**: BrokenPipeError and Connection reset by peer errors in site-generator
- **Recording fetch failures**: Storage backend connection issues

## Execution Errors Noted
1. **Timestamp parsing bug**: Script generates error messages in JSONL output but still captures logs
2. **No events available**: kubectl returns no events for pbx-web namespace
3. **No previous logs**: All pods have 0 restarts, so `--previous` flag returns no data

## Files Created
- `logs/pbx-web-ardenone-cluster/pbx-web-logs-20260806-202715.jsonl` - Main log output
- `logs/pbx-web-ardenone-cluster/fetch-summary-20260806-202715.json` - Execution metadata
- `logs/pbx-web-ardenone-cluster/retrieval-summary.md` - This summary document

## Recommendations
1. **Fix timestamp bug**: Update date conversion function in fetch-pbx-web-logs.sh
2. **Check event logging**: Investigate why no events are recorded in pbx-web namespace
3. **Monitor errors**: The BrokenPipeError and Connection reset errors suggest storage backend issues
4. **Extend retention**: Current 22-day coverage is limited by pod recreation schedule

## Next Steps
- Analyze the captured logs for error patterns and performance metrics
- Investigate storage backend connection issues
- Set up event monitoring for pbx-web namespace
