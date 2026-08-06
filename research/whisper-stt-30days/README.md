# Whisper-STT Pod Inventory - 30 Days

## Analysis Period
**2026-07-07 to 2026-08-06** (30-day window)

## Cluster
**ardenone-cluster** (`kubectl --server=http://traefik-ardenone-cluster:8001`)

## Namespace
**whisper-stt**

## Inventory Summary

### Current Pods (Running)
1. **whisper-openai-68966786fb-jsb5d**
   - Created: 2026-06-14T04:55:49Z
   - Phase: Running
   - Image: docker.io/fedirz/faster-whisper-server:latest-cpu
   - Node: k3s-lenovo-tiny
   - Note: Created before window, running through entire period

2. **whisper-stt-847fd8d7b9-v2rs5**
   - Created: 2026-07-12T16:53:42Z
   - Phase: Running
   - Image: docker.io/ronaldraygun/whisper-stt:1.8.6
   - Node: k3s-agent-minisforum
   - Note: Created during window, currently running

### Historical Pods (Created then Deleted)
3. **whisper-stt-5dbff75cbd-*** (ReplicaSet created 2026-07-08T03:09:35Z)
   - Image: ronaldraygun/whisper-stt:1.8.2
   - Note: ReplicaSet created during window, pods deleted (0/0 replicas)

4. **whisper-stt-5b8558f478-*** (ReplicaSet created 2026-07-08T03:16:13Z)
   - Image: ronaldraygun/whisper-stt:1.8.4
   - Note: ReplicaSet created during window, pods deleted (0/0 replicas)

5. **whisper-stt-6c497489fb-*** (ReplicaSet created 2026-07-08T03:26:44Z)
   - Image: ronaldraygun/whisper-stt:1.8.6
   - Note: ReplicaSet created during window, pods deleted (0/0 replicas)

## Notes

- **Historical pod limitation**: Kubernetes does not retain detailed metadata for deleted pods. Exact deletion timestamps and pod names (the random 5-character suffix) are not available after deletion.
- **ReplicaSet analysis**: For deleted pods, we reconstructed information from ReplicaSets, which show creation timestamps and images, but not individual pod lifecycle details.
- **Wildcard naming**: Historical entries use `-*` suffix pattern to indicate unknown individual pod names within that ReplicaSet.

## Files
- `pod-inventory.jsonl` - Machine-readable inventory (one JSON object per line)

## Query Used
```bash
kubectl --server=http://traefik-ardenone-cluster:8001 get pods -n whisper-stt
kubectl --server=http://traefik-ardenone-cluster:8001 get replicasets -n whisper-stt
```
