# Deployment Metadata - Data Sources Documentation

**Extraction Date:** 2026-08-06T12:09:09.955164

**Analysis Period:** 30_days (2026-07-07 to 2026-08-06)

## Data Sources

### Pbx-Web

- **Cluster:** ardenone-cluster
- **Namespace:** pbx-web
- **Raw Data Path:** `research/pbx-web-30days/deployments-30days.json`

### Whisper-Stt

- **Cluster:** ardenone-cluster
- **Namespace:** whisper-stt
- **Raw Data Path:** `research/whisper-stt-30days/deployments-30days.json`

## Query Methods

- **Kubectl Read Only:** `kubectl --server=http://traefik-ardenone-cluster:8001 get pods -n <namespace>`
- **Replicasets Query:** `kubectl --server=http://traefik-ardenone-cluster:8001 get replicasets -n <namespace>`
- **Events Query:** `kubectl --server=http://traefik-ardenone-cluster:8001 get events -n <namespace> --sort-by='.lastTimestamp'`

## Limitations

- Kubernetes does not retain detailed metadata for deleted pods
- Historical pod deletion timestamps are estimated from ReplicaSet data
- Deployment duration metrics require pod log analysis (not yet implemented)
- Container image pull times are not captured in current data collection

## Next Steps for Enhanced Collection

- Extract pod logs for deployment duration metrics
- Query Kubernetes events for ScalingReplicaSet and FailedCreate events
- Analyze Argo Workflows for build pipeline execution history
- Capture container image pull durations from pod events
