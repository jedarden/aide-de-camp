# Log Collection Sampling Strategy
**Project:** whisper-stt 30-day log analysis  
**Analysis Date:** 2026-08-06  
**Decision:** COLLECT ALL LOGS (no sampling required)

## Inventory Summary

### Total Pod Count: 5 entries
- **Current pods:** 2 (running)
- **Historical pods:** 3 (ReplicaSets with deleted pods)

### Decision Criteria
✅ Pod count (5) ≤ 20 → **COLLECT ALL LOGS**

Since the total number of unique pod entries is only 5, well below the 20-pod threshold, we will collect logs from all pods rather than implementing a sampling strategy.

## Target Pods

### 1. whisper-openai-68966786fb-jsb5d (CURRENT)
- **Created:** 2026-06-14T04:55:49Z
- **Status:** Running
- **Image:** docker.io/fedirz/faster-whisper-server:latest-cpu
- **Node:** k3s-lenovo-tiny
- **Coverage:** FULL 30-DAY WINDOW (created before window, running through entire period)
- **Priority:** HIGH - spans entire analysis period

### 2. whisper-stt-847fd8d7b9-v2rs5 (CURRENT)
- **Created:** 2026-07-12T16:53:42Z
- **Status:** Running
- **Image:** docker.io/ronaldraygun/whisper-stt:1.8.6
- **Node:** k3s-agent-minisforum
- **Coverage:** Partial window (2026-07-12 to 2026-08-06, ~25 days)
- **Priority:** HIGH - current deployment, most recent activity

### 3. whisper-stt-5dbff75cbd-* (HISTORICAL)
- **Created:** 2026-07-08T03:09:35Z
- **Status:** Historical (ReplicaSet, pods deleted)
- **Image:** docker.io/ronaldraygun/whisper-stt:1.8.2
- **Coverage:** Short deployment (2026-07-08, ~7 minutes before next version)
- **Priority:** MEDIUM - may have logs if scraped before deletion

### 4. whisper-stt-5b8558f478-* (HISTORICAL)
- **Created:** 2026-07-08T03:16:13Z
- **Status:** Historical (ReplicaSet, pods deleted)
- **Image:** docker.io/ronaldraygun/whisper-stt:1.8.4
- **Coverage:** Short deployment (2026-07-08, ~10 minutes before next version)
- **Priority:** MEDIUM - may have logs if scraped before deletion

### 5. whisper-stt-6c497489fb-* (HISTORICAL)
- **Created:** 2026-07-08T03:26:44Z
- **Status:** Historical (ReplicaSet, pods deleted)
- **Image:** docker.io/ronaldraygun/whisper-stt:1.8.6
- **Coverage:** Short deployment (2026-07-08 to 2026-07-12, ~4 days)
- **Priority:** MEDIUM - may have logs if scraped before deletion

## Time Window Coverage

**Analysis Period:** 2026-07-06 to 2026-08-06 (30 days)

**Coverage Map:**
```
2026-07-06 ──────────────────────────────────────────── 2026-08-06
   ↓               [histories]              ↓
   │              ┌─┐┌─┐┌──────┐           │
   │              │h││h││  h   │           │
   │              └─┘└─┘└──────┘           │
   │                                        │
   └────────────────────────────────────────┴─────── whisper-openai-68966786fb-jsb5d (entire period)
                           ┌────────────────────────┴──── whisper-stt-6c497489fb-* (2026-07-08 to 07-12)
                                             ┌────────┴─────── whisper-stt-847fd8d7b9-v2rs5 (2026-07-12 to present)
```

**Key Coverage Notes:**
- `whisper-openai-68966786fb-jsb5d` provides complete coverage for the entire 30-day window
- `whisper-stt-847fd8d7b9-v2rs5` provides overlapping coverage for the last ~25 days
- Historical ReplicaSets from 2026-07-08 represent rapid deployments during a maintenance window (3 versions in ~17 minutes)
- All periods of the 30-day window are covered by at least one pod

## Collection Approach

### All Logs Collection
Since pod count is 5 (≤ 20), we will collect logs from all pods:

1. **Current pods (2)** - Collect via `kubectl logs` directly
2. **Historical pods (3)** - Attempt collection; logs may not exist if:
   - Pods were deleted before log scraping occurred
   - Log retention policy expired
   - Logs were not persisted to central logging

### Collection Commands
```bash
# Current pods
kubectl logs whisper-openai-68966786fb-jsb5d -n whisper-stt > pod-logs/pod-whisper-openai-68966786fb-jsb5d.log
kubectl logs whisper-stt-847fd8d7b9-v2rs5 -n whisper-stt > pod-logs/pod-whisper-stt-847fd8d7b9-v2rs5.log

# Historical pods (attempt collection - may return no logs)
kubectl logs whisper-stt-5dbff75cbd-* -n whisper-stt --all-containers=true > pod-logs/pod-whisper-stt-5dbff75cbd.log 2>/dev/null
kubectl logs whisper-stt-5b8558f478-* -n whisper-stt --all-containers=true > pod-logs/pod-whisper-stt-5b8558f478.log 2>/dev/null
kubectl logs whisper-stt-6c497489fb-* -n whisper-stt --all-containers=true > pod-logs/pod-whisper-stt-6c497489fb.log 2>/dev/null
```

## Success Criteria

✅ **Documented sampling strategy** showing which pods will be targeted and why  
✅ **All 5 pods identified** with creation timestamps and status  
✅ **Full time window coverage** confirmed (30 days covered)  
✅ **Collection approach defined** for both current and historical pods  
✅ **No sampling required** due to low pod count (≤ 20)

## Next Steps

1. Execute log collection for all 5 pods using commands above
2. Verify log files exist and contain data
3. Document any pods where log collection fails (expected for historical pods)
4. Proceed to log analysis phase with collected logs
