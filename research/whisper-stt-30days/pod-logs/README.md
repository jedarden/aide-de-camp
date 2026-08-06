# Whisper-STT Pod Logs Collection

## Collection Date
2026-08-06

## Source Cluster
ardenone-cluster (read-only kubectl-proxy)

## Pods Found
From `pod-inventory.jsonl`, 2 current pods were identified:

### 1. whisper-openai-68966786fb-jsb5d
- **Status**: Running (created 2026-06-14, 53 days ago)
- **Image**: docker.io/fedirz/faster-whisper-server:latest-cpu
- **Node**: k3s-lenovo-tiny
- **Restart Count**: 0
- **Logs Collected**: `pod-whisper-openai-68966786fb-jsb5d-2026-08-06.log` (89,585 lines, ~5.2MB)
- **Log Content**: Primarily health check traffic (`GET /health HTTP/1.1 200 OK`)
- **Previous Logs**: None (pod never restarted)

### 2. whisper-stt-847fd8d7b9-v2rs5
- **Status**: Running (created 2026-07-12, 24 days ago)
- **Image**: docker.io/ronaldraygun/whisper-stt:1.8.6
- **Node**: k3s-agent-minisforum
- **Restart Count**: 0
- **Logs Collected**: `pod-whisper-stt-847fd8d7b9-v2rs5-2026-08-06.log` (no output)
- **Log Content**: No stdout/stderr output detected
- **Previous Logs**: None (pod never restarted)

## Historical Pods
From `pod-inventory.jsonl`, 3 historical ReplicaSets were identified but pods no longer exist:
- whisper-stt-5dbff75cbd-* (v1.8.2) - 0/0 replicas, pods deleted
- whisper-stt-5b8558f478-* (v1.8.4) - 0/0 replicas, pods deleted
- whisper-stt-6c497489fb-* (v1.8.6) - 0/0 replicas, pods deleted

**Note**: Logs from deleted pods are not available via kubectl (they are garbage-collected after pod deletion).

## Sampling Strategy
Task specified: "Handle cases where pods are too many: sample representative pods (at least 10 samples)"

**Result**: Only 2 pods exist in the cluster, both were collected. No sampling was necessary.

## Log File Naming Convention
- Format: `pod-<pod-name>-<date>.log`
- Previous logs (if available): `pod-<pod-name>-<date>-previous.log`

## Summary
- **Pods with logs**: 1 of 2 (whisper-openai has substantial logs; whisper-stt has no output)
- **Total log data collected**: ~5.2MB (89K lines from whisper-openai)
- **30-day coverage**: whisper-openai ran through entire period; whisper-stt started 2026-07-12 (day 18 of 30-day window)
