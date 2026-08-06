# whisper-stt Deployment Events - Last 30 Days

## Task Summary
Successfully retrieved deployment events for whisper-stt from ardenone-cluster over the 30-day period from 2026-07-07 to 2026-08-06.

## Deployment Location
- **Cluster**: ardenone-cluster
- **Namespace**: whisper-stt
- **Access**: kubectl proxy via `http://traefik-ardenone-cluster:8001`

## Key Findings

### Current Status (as of 2026-08-06)
- **Active ReplicaSet**: whisper-stt-847fd8d7b9
- **Revision**: 32
- **Image**: ronaldraygun/whisper-stt:1.8.6
- **Pod**: whisper-stt-847fd8d7b9-v2rs5
- **Status**: Running, 0 restarts, fully ready

### Deployment Events in 30-Day Window

1. **July 8, 2026 - Rapid Rollout Sequence**
   - 03:09:35Z - Revision 29: Version 1.8.2 deployed
   - 03:16:13Z - Revision 30: Version 1.8.4 deployed (7 minutes later)
   - 03:26:44Z - Revision 31: Version 1.8.6 deployed (10 minutes later)

2. **July 12, 2026 - Current Deployment**
   - 16:53:42Z - Revision 32: Version 1.8.6 (current)

### Event Types Captured
- ✅ Deployment rollouts
- ✅ Version progression (1.8.2 → 1.8.4 → 1.8.6)
- ✅ ReplicaSet creation timestamps
- ✅ Pod status and health
- ✅ Image tags and revisions
- ✅ Rapid deployment sequence (3 deployments in 17 minutes on July 8)

### Data Files Generated
- `/tmp/whisper-stt-deployment-events-30d.json` - Structured deployment events
- `/tmp/whisper-stt-replicasets-raw.yaml` - Full ReplicaSet details (2,884 lines)

## Additional Observations
- **Deployment Strategy**: Recreate (not RollingUpdate)
- **Near-boundary event**: Revision 28 (v1.7.0) on July 2, just outside 30-day window
- **No failures**: 0 failed pods, 0 restarts in 30-day period
- **Separate deployment**: whisper-openai also running (fedirz/faster-whisper-server:latest-cpu) but not updated in this period

## Query Method
Used kubectl commands via proxy to query:
- ReplicaSets with timestamps and image tags
- Pod status and restart counts  
- Deployment rollout history
- Current active ReplicaSet

The data shows active deployment management with version updates progressing through the 1.8.x series in early July, with stable operation since July 12.