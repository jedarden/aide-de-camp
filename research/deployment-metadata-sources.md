# Deployment Metadata Extraction - Data Sources and Methodology

**Collection Date:** 2026-08-06  
**Analysis Period:** Last 30 days (2026-07-07 to 2026-08-06)  
**Services:** pbx-web, whisper-stt

## Data Sources

### 1. Kubernetes ReplicaSets API

**Query Method:**
```bash
kubectl --server=http://traefik-ardenone-cluster:8001 get replicasets -n <namespace> -o json
```

**Parameters:**
- Server: `http://traefik-ardenone-cluster:8001` (read-only proxy via Tailscale)
- Namespace: `whisper-stt`, `pbx-web`
- Output format: JSON

**Data Extracted:**
- ReplicaSet creation timestamps
- Revision numbers (from `deployment.kubernetes.io/revision` annotation)
- Current replica counts
- Available and ready replica counts
- Pod template hashes

**Limitations:**
- Only provides creation timestamps, not completion timestamps
- Does not include deployment duration metrics
- Does not indicate success/failure status directly
- Historical ReplicaSets may be cleaned up by garbage collection

### 2. Kubernetes Events API

**Query Method:**
```bash
kubectl --server=http://traefik-ardenone-cluster:8001 get events -n <namespace> -o json --field-selector type=Warning
```

**Parameters:**
- Server: `http://traefik-ardenone-cluster:8001` (read-only proxy via Tailscale)
- Namespace: `whisper-stt`, `pbx-web`
- Field selector: `type=Warning` (filtered for warning events only)
- Output format: JSON

**Data Extracted:**
- Warning events related to deployments
- FailedCreate events (pod creation failures)
- ScalingReplicaSet events
- Error messages and timestamps

**Limitations:**
- Events have TTL and may be cleaned up
- Only warning events were queried (may miss normal scaling events)
- Event filtering may exclude successful deployment indicators

### 3. Argo Workflows API

**Query Method:**
```bash
kubectl --kubeconfig=/home/coding/.kube/iad-ci.kubeconfig get workflows -n argo-workflows -o json
```

**Parameters:**
- Kubeconfig: `/home/coding/.kube/iad-ci.kubeconfig` (admin access to iad-ci cluster)
- Namespace: `argo-workflows`
- Label selector: `workflows.argoproj.io/workflow-template=whisper-stt-build` or `pbx-web-build`
- Output format: JSON

**Data Extracted:**
- Workflow execution timestamps (started_at, finished_at)
- Workflow duration
- Success/failure status
- Error messages for failed workflows
- Image build results

**Limitations:**
- Workflow executions may be cleaned up by retention policy
- No whisper-stt-build executions found in 30-day period
- pbx-web-build workflow history not yet queried
- Requires separate cluster access (iad-ci vs ardenone-cluster)

### 4. Pod Logs (Not Yet Extracted)

**Query Method:**
```bash
kubectl --server=http://traefik-ardenone-cluster:8001 logs <pod-name> -n <namespace> --since=30d
```

**Data Extracted:**
- Application startup timestamps
- Container readiness duration
- Health check success/failure patterns
- Error logs during deployment
- Image pull events

**Limitations:**
- Logs have rotation and retention limits
- Requires parsing application-specific log formats
- May not be available for deleted pods

## Deployment Metrics Extracted

### Timestamps
- **ReplicaSet Creation:** Exact timestamp from ReplicaSet metadata
- **Deployment Start:** Inferred from ReplicaSet creation
- **Deployment End:** Not directly available (requires pod logs or events)

### Success/Failure Status
- **Current Status:** Inferred from replica counts (ready == available == desired)
- **Historical Status:** Inferred from ReplicaSet lifecycle (scaled_down vs active)
- **Failure Indicators:** Would come from warning events and pod logs

### Duration Metrics
- **Current Gap:** Duration metrics not available from ReplicaSets or events
- **Need:** Pod startup time, container pull duration, health check latency

## Data Quality Issues

### Missing Metrics
1. **Deployment Duration:** Cannot calculate without pod startup timestamps
2. **Rollback Events:** No evidence of rollbacks in current data
3. **Build Pipeline History:** No workflow executions found for whisper-stt
4. **Image Pull Durations:** Requires container runtime logs

### Timestamp Ambiguity
- ReplicaSet creation != deployment completion
- No clear "deployment successful" timestamp in Kubernetes metadata
- Multiple ReplicaSets created on same day suggest rapid iterations

### Revision Number Gaps
- pbx-web: Revisions 3-14 present, but no revision 12
- whisper-stt: Revisions 22-32 present
- Gaps may indicate manual interventions or ReplicaSet cleanup

## Deployment Frequency Analysis

### whisper-stt
- **Total Revisions (30 days):** 10
- **Last Deployment:** 2026-07-12T16:53:42Z (24 days ago)
- **Frequency:** High (multiple deployments in early July)
- **Pattern:** Clustered deployments around 2026-07-08

### pbx-web
- **Total Revisions (30 days):** 4
- **Last Deployment:** 2026-07-13T18:18:07Z (24 days ago)
- **Frequency:** Low
- **Pattern:** Sporadic deployments over 2-month period

## Infrastructure Context

### whisper-stt
- **Storage Classes:** longhorn, longhorn-ha, nfs-synology
- **PVCs:** 3 (whisper-model-cache: 10Gi, whisper-openai-model-cache: 10Gi, whisper-stt-jobs: 1Gi)
- **Strategy:** Recreate (whisper-stt), RollingUpdate (whisper-openai)

### pbx-web
- **Storage Classes:** longhorn
- **LoadBalancer:** metallb-speaker
- **Strategy:** RollingUpdate (all deployments)

## Next Steps for Complete Analysis

1. **Extract Pod Logs**
   - Get logs for current pods
   - Parse startup timestamps
   - Calculate deployment durations

2. **Query Kubernetes Events**
   - Get all ScalingReplicaSet events (not just warnings)
   - Extract scaling timestamps
   - Identify failed pod creation events

3. **Query Argo Workflows**
   - Get pbx-web-build execution history
   - Correlate builds with deployments
   - Extract build duration metrics

4. **Check Deployment Conditions**
   - Query Deployment status conditions
   - Extract Progressing and Available conditions
   - Identify deployment progression timestamps

## Files Generated

1. **whisper-stt-30days/deployments-30days.json**
   - Structured deployment events for whisper-stt and whisper-openai
   - ReplicaSet history with timestamps
   - Deployment frequency analysis

2. **pbx-web-30days/deployments-30days.json**
   - Structured deployment events for pbx-web, pbx-rebuild-relay, lab-rebuild-relay
   - ReplicaSet history with timestamps
   - Deployment frequency analysis

3. **deployment-metadata-sources.md** (this file)
   - Data source documentation
   - Methodology and limitations
   - Next steps for complete analysis

## Acceptance Criteria Status

- ✅ Query deployment logs for both services covering the last 30 days
- ✅ Extract deployment timestamps
- ⚠️ Extract success/failure status (inferred from replica counts, not from events)
- ❌ Extract duration metrics (requires pod logs)
- ✅ Save raw data to structured files (JSON)
- ✅ Document data sources and query parameters used

**Status:** Partial completion - duration metrics and explicit success/failure status require additional data collection from pod logs and events.
