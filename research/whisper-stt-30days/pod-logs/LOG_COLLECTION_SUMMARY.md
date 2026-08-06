# Log Collection Summary - whisper-stt 30-Day Analysis

**Date:** 2026-08-06  
**Cluster:** ardenone-cluster  
**Namespace:** whisper-stt  
**Strategy:** Collect all logs from 5 pods (2 current + 3 historical)

## Collection Results

### ✅ Successful Collections (2/5 pods)

#### 1. whisper-openai-68966786fb-jsb5d (CURRENT)
- **Status:** Running (created 2026-06-14, spans entire 30-day window)
- **Log Size:** ~5.0 MB
- **File:** `pod-whisper-openai-68966786fb-jsb5d-with-metadata.log`
- **Content:** Health check logs from faster-whisper-server
- **Metadata:** Timestamp, pod info, cluster info included

#### 2. whisper-stt-847fd8d7b9-v2rs5 (CURRENT)
- **Status:** Running (created 2026-07-12, recent deployment)
- **Log Size:** ~210 bytes (minimal recent activity)
- **File:** `pod-whisper-stt-847fd8d7b9-v2rs5-with-metadata.log`
- **Content:** Minimal log entries (pod may be idle)
- **Metadata:** Timestamp, pod info, cluster info included

### ❌ Expected Failures (3/5 historical pods)

#### 3. whisper-stt-5dbff75cbd-* (HISTORICAL)
- **Status:** ReplicaSet created 2026-07-08T03:09:35Z, pods deleted
- **Image:** ronaldraygun/whisper-stt:1.8.2
- **Result:** No logs available (pods deleted before log retention)
- **Reason:** Kubernetes does not retain logs for deleted pods

#### 4. whisper-stt-5b8558f478-* (HISTORICAL)
- **Status:** ReplicaSet created 2026-07-08T03:16:13Z, pods deleted
- **Image:** ronaldraygun/whisper-stt:1.8.4
- **Result:** No logs available (pods deleted before log retention)
- **Reason:** Kubernetes does not retain logs for deleted pods

#### 5. whisper-stt-6c497489fb-* (HISTORICAL)
- **Status:** ReplicaSet created 2026-07-08T03:26:44Z, pods deleted
- **Image:** ronaldraygun/whisper-stt:1.8.6
- **Result:** No logs available (pods deleted before log retention)
- **Reason:** Kubernetes does not retain logs for deleted pods

## Metadata Format

All successful log files include a standardized header:
```
# Log metadata
# Pod: <pod-name>
# Namespace: whisper-stt
# Cluster: ardenone-cluster
# Fetched at: <ISO-8601 timestamp>
# Previous logs flag: <status>
# ---
<log content>
```

## Collection Method

**Command Used:**
```bash
kubectl --server=http://traefik-ardenone-cluster:8001 logs <pod-name> -n whisper-stt
```

**Parameters:**
- Read-only proxy access (no kubeconfig tokens)
- Current logs only (no `--previous` flag for pods without restarts)
- Metadata prepended during collection
- Error handling for missing historical pods

## Key Findings

1. **Pod Coverage:** Only 2 of 5 pods had collectible logs
   - Current running pods: 100% success rate
   - Historical deleted pods: 0% success rate (expected)

2. **Log Retention:** Historical logs from deleted pods are not available
   - Deleted pods (2026-07-08) have no retained logs
   - Only currently running pods retain log history

3. **Data Quality:** 
   - `whisper-openai` pod has substantial logs (~5 MB of health checks)
   - `whisper-stt-847fd8d7b9-v2rs5` has minimal activity (may be idle)

## Acceptance Criteria Status

✅ For each pod in the sampling strategy, run kubectl logs commands  
✅ Use the correct kubectl context (ardenone-cluster via proxy)  
✅ Capture both stdout and stderr streams (captured via `2>&1`)  
✅ Handle timeouts and connection errors gracefully  
✅ Include metadata in log output (pod name, namespace, fetch timestamp)  
✅ Store logs in temporary location initially (stored in `pod-logs/` directory)

## Success Criteria Status

✅ **All target pods attempted:** 5/5 pods processed  
✅ **Error handling:** Failed fetches handled gracefully with error messages  
✅ **Metadata included:** All successful logs have standardized headers  
✅ **Storage organized:** Logs stored in structured directory with naming convention

## Next Steps

1. Analyze the collected logs from the 2 successful pods
2. Document any patterns or issues found in the log analysis
3. Consider implementing log aggregation for historical pod access in future deployments
