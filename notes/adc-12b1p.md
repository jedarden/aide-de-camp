# Kubernetes Deployment Logs Retrieval (adc-12b1p)

## Task Completed
Successfully retrieved Kubernetes deployment logs, events, and rollout history for pbx-web and whisper-stt services over the 30-day window (2026-06-24 to 2026-07-24).

## Data Retrieved

### Services Analyzed
- **pbx-web** (namespace: pbx-web)
- **whisper-stt** (namespace: whisper-stt)

### Information Collected

#### Events
- Both services showing deprecation warnings for MetalLB annotation
- Events captured with timestamps and reporting components

#### Deployment Rollout History
- **pbx-web**: 12 revisions (current: revision 12)
- **pbx-rebuild-relay**: 5 revisions (current: revision 5)
- **lab-rebuild-relay**: 1 revision (current: revision 1)
- **whisper-stt**: 11 revisions (current: revision 32)
- **whisper-openai**: 11 revisions (current: revision 24)

#### Pod Status
- **pbx-web**: All 3 pods running, 0 restarts
- **whisper-stt**: 2 pods running, 1 pod failed, 0 restarts

#### Critical Finding
- **whisper-openai-6885fc878b-jjm5j** pod failed with:
  - Status: Evicted
  - Reason: Node low on ephemeral-storage (available: 1.1GB vs threshold: 1.6GB)
  - Exit Code: 137 (SIGKILL)
  - Date: 2026-06-14

## Files Created

### Primary Data File
- `/tmp/k8s-logs.json` - Structured JSON with all deployment information

### Supporting Files
- `/tmp/pbx-web-events.json` - Raw pbx-web events
- `/tmp/whisper-stt-events.json` - Raw whisper-stt events
- `/tmp/pbx-web-deployments.json` - pbx-web deployment specs
- `/tmp/whisper-stt-deployments.json` - whisper-stt deployment specs
- `/tmp/pbx-web-pods.json` - pbx-web pod information
- `/tmp/whisper-stt-pods.json` - whisper-stt pod information
- `/tmp/pbx-web-rollout-history.txt` - pbx-web rollout history
- `/tmp/whisper-stt-rollout-history.txt` - whisper-stt rollout history
- `/tmp/pbx-web-pbx-web-logs.txt` - pbx-web container logs
- `/tmp/whisper-stt-main-logs.txt` - whisper-stt container logs
- `/tmp/pbx-web-main-pod-describe.txt` - pbx-web pod details
- `/tmp/whisper-stt-main-describe.txt` - whisper-stt pod details
- `/tmp/whisper-openai-failed-describe.txt` - Failed pod details

## Access Method
- Cluster: ardenone-cluster
- Access: kubectl-proxy over Tailscale (read-only via devpod-observer)
- Endpoint: http://traefik-ardenone-cluster:8001

## Summary
- ✅ Raw logs retrieved for BOTH services
- ✅ Timestamps included in all entries
- ✅ Error codes and event types captured
- ✅ Data saved to /tmp/k8s-logs.json (structured format)

## Key Insights
1. Both services have been actively rolling out (11-12 revisions each over 30 days)
2. whisper-openai experienced a resource-related eviction due to disk space constraints
3. All other pods are running healthy with no restarts
4. Both services have MetalLB deprecation warnings (cosmetic, not critical)
