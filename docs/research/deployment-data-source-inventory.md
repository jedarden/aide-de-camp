# PBX-Web & Whisper-STT Data Source Inventory

**Generated:** 2026-08-06  
**Cluster:** ardenone-cluster  
**Analysis Period:** 30 days (2026-07-08 to 2026-08-06)

---

## Quick Reference (Cheat Sheet)

### Kubernetes Access
```bash
# Read-only proxy access (recommended for queries)
kubectl --server=http://traefik-ardenone-cluster:8001 get <resource> -n <namespace>

# Direct kubeconfig (read/write)
kubectl --kubeconfig=/home/coding/.kube/ardenone-cluster.kubeconfig get <resource> -n <namespace>
```

### Namespaces
- **pbx-web:** `pbx-web`
- **whisper-stt:** `whisper-stt`

### Key Resources by Service

| Resource Type | pbx-web | whisper-stt |
|--------------|---------|-------------|
| Deployments | pbx-web | whisper-stt, whisper-openai |
| ReplicaSets | pbx-web-* | whisper-stt-*, whisper-openai-* |
| Pods | pbx-web-* | whisper-stt-*, whisper-openai-* |
| PVCs | (none) | whisper-model-cache, whisper-stt-jobs, whisper-openai-model-cache |
| Services | pbx-web, pbx-rebuild-relay | whisper-stt |
| ConfigMaps | pbx-web-nginx-conf | (none) |
| Secrets | pbx-web-auth, garage-pbx-creds | whisper-stt-secret |

### Common Query Patterns

```bash
# Get deployment status
kubectl --server=http://traefik-ardenone-cluster:8001 get deployment -n <namespace>

# Get replica sets (for deployment history)
kubectl --server=http://traefik-ardenone-cluster:8001 get replicasets -n <namespace> --sort-by=.metadata.creationTimestamp

# Get pod status with restarts
kubectl --server=http://traefik-ardenone-cluster:8001 get pods -n <namespace> -o wide

# Get recent events
kubectl --server=http://traefik-ardenone-cluster:8001 get events -n <namespace> --sort-by='.lastTimestamp'

# Get PVCs
kubectl --server=http://traefik-ardenone-cluster:8001 get pvc -n <namespace>

# Get deployment details
kubectl --server=http://traefik-ardenone-cluster:8001 get deployment <name> -n <namespace> -o yaml
```

---

## Service: pbx-web

### Namespace
`pbx-web`

### Kubernetes Resources

#### Deployments
- **Primary:** `pbx-web`
  - Strategy: Recreate
  - Replicas: 1
  - Image: `ronaldraygun/pbx-web:1.0.9`
  - Port: 9000 (rebuild endpoint)
  - Revision: 14
  - Age: Since 2026-05-01

- **Secondary:** 
  - `pbx-rebuild-relay` (Revision 5)
  - `lab-rebuild-relay` (Revision 2)

#### ReplicaSets (30-Day History)
Sample from research data:
```
pbx-web-754f4cfdf7   Revision 11   Created: 2026-07-13T18:07:55Z   Status: inactive
pbx-web-5ff68464d    Revision 14   Created: 2026-07-13T18:18:07Z   Status: active
pbx-web-765bb76db8   Revision 13   Created: 2026-07-28T17:05:51Z   Status: inactive
```

Query:
```bash
kubectl --server=http://traefik-ardenone-cluster:8001 get replicasets -n pbx-web \
  --sort-by=.metadata.creationTimestamp -o json
```

#### Pods
- Container: `site-generator` (Python Flask app)
- Sidecar: `nginx` (alpine)
- Resources: 
  - site-generator: 500m CPU, 512Mi memory (limit)
  - nginx: 100m CPU, 128Mi memory (limit)
- Probes: HTTP /health on port 9000

Query:
```bash
kubectl --server=http://traefik-ardenone-cluster:8001 get pods -n pbx-web -o wide
kubectl --server=http://traefik-ardenone-cluster:8001 get pods -n pbx-web -o json
```

#### Events
- **Recent Events:** Minimal (events JSON was empty in research)
- **Event Types:** Normal scaling, replicaset creation

Query:
```bash
kubectl --server=http://traefir-ardenone-cluster:8001 get events -n pbx-web --sort-by='.lastTimestamp'
```

### Storage & Data Sources

#### Volumes
- **www:** emptyDir (shared between containers)
- **nginx-conf:** ConfigMap `pbx-web-nginx-conf`
- **nginx-cache:** emptyDir (Memory, 16Mi limit)
- **nginx-run:** emptyDir (Memory, 8Mi limit)

#### External Storage
- **S3 Endpoint:** `http://garage.garage-operator.svc.cluster.local:3900`
- **Bucket:** `recordings`
- **Credentials:** Secret `garage-pbx-creds`

### Configuration

#### Environment Variables
```yaml
S3_ENDPOINT: http://garage.garage-operator.svc.cluster.local:3900
S3_BUCKET: recordings
S3_ACCESS_KEY: from secret `garage-pbx-creds`
S3_SECRET_KEY: from secret `garage-pbx-creds`
REBUILD_API_TOKEN: from secret `pbx-web-auth`
PYTHONUNBUFFERED: 1
```

#### ConfigMaps
- `pbx-web-nginx-conf`: Nginx configuration

#### Secrets
- `pbx-web-auth`: API token for rebuild endpoint
- `garage-pbx-creds`: S3 credentials

### Logging

#### Log Sources
- **Pod Logs:** Standard output from `site-generator` container
- **Log Volume:** 2,761 lines in 30-day sample
- **Error Patterns:**
  - `connection_reset_by_peer`: 3 occurrences (low severity)
  - `broken_pipe_error`: 3 occurrences (low severity)

Query:
```bash
# Get pod logs
kubectl --server=http://traefik-ardenone-cluster:8001 logs -n pbx-web --tail=100

# Get logs from specific container
kubectl --server=http://traefik-ardenone-cluster:8001 logs -n pbx-web -c site-generator --tail=100
```

#### Victorialogs
- **Integration:** Not configured for pbx-web
- **Status:** No logs in research data

### Network & Services

#### Services
- `pbx-web`: ClusterIP for main service
- `pbx-rebuild-relay`: Rebuild relay service

#### Endpoints
- **Rebuild API:** HTTP on port 9000
- **Web:** HTTP on port 80 (nginx sidecar)

### Container Registry

#### Image Sources
- **Primary:** `ronaldraygun/pbx-web:1.0.9`
- **Registry:** Docker Hub
- **Pull Policy:** Always
- **Image Pull Secret:** `docker-hub-registry`

### CI/CD Integration

#### Argo Workflows
- **Template:** `pbx-web-build`
- **Trigger:** Image tag push to declarative-config
- **Output:** New image pushed to `ronaldraygun/pbx-web`

#### ArgoCD
- **Application:** `pbx-web-ns-ardenone-cluster`
- **Repo:** `jedarden/declarative-config`
- **Path:** `k8s/ardenone-cluster/pbx-web/`
- **Tracking ID:** `pbx-web-ns-ardenone-cluster:apps/Deployment:pbx-web/pbx-web`

---

## Service: whisper-stt

### Namespace
`whisper-stt`

### Kubernetes Resources

#### Deployments
- **Primary:** `whisper-stt`
  - Strategy: Recreate
  - Replicas: 1
  - Image: `ronaldraygun/whisper-stt:1.8.6`
  - Port: 8080
  - Revision: 32
  - Node affinity: `k3s-agent-minisforum` (preferred)

- **Secondary:** `whisper-openai`
  - Image: `fedirz/faster-whisper-server:latest-cpu` (cached locally)
  - Model: `large-v3-turbo`
  - Port: 8000
  - Resources: 8 CPU, 8Gi memory (limit)

#### ReplicaSets (30-Day History)
Sample from research data:
```
whisper-stt-5dbff75cbd   Revision 29   Created: 2026-07-08T03:09:35Z   Status: inactive
whisper-stt-5b8558f478    Revision 30   Created: 2026-07-08T03:16:13Z   Status: inactive
whisper-stt-6c497489fb    Revision 31   Created: 2026-07-08T03:26:44Z   Status: inactive
whisper-stt-847fd8d7b9    Revision 32   Created: 2026-07-12T16:53:42Z   Status: active
```

**Burst Pattern Detected:** 3 deployments in 17 minutes on 2026-07-08

Query:
```bash
kubectl --server=http://traefik-ardenone-cluster:8001 get replicasets -n whisper-stt \
  --sort-by=.metadata.creationTimestamp -o json
```

#### Pods
- **whisper-stt-847fd8d7b9-v2rs5:** Running on `k3s-agent-minisforum`
  - Resources: 8 CPU, 8Gi memory (limit)
  - Requests: 1 CPU, 4Gi memory
  - Uptime: Since 2026-07-12
  - Restarts: 0

- **whisper-openai-68966786fb-jsb5d:** Running on `k3s-lenovo-tiny`
  - Init container: `model-download` (downloads HuggingFace models)
  - Model cache PVC: `whisper-openai-model-cache`

Query:
```bash
kubectl --server=http://traefik-ardenone-cluster:8001 get pods -n whisper-stt -o wide
kubectl --server=http://traefik-ardenone-cluster:8001 get pods -n whisper-stt -o json
```

#### Events
- **Recent Events:** No warning events detected
- **Normal Operations:** Replicaset creation, pod scheduling

Query:
```bash
kubectl --server=http://traefik-ardenone-cluster:8001 get events -n whisper-stt --sort-by='.lastTimestamp'
```

### Storage & Data Sources

#### Persistent Volume Claims
- **whisper-model-cache:** HuggingFace model storage
- **whisper-stt-jobs:** Job data storage
- **whisper-openai-model-cache:** OpenAI Whisper model cache

#### Volumes
- **model-cache:** PVC `whisper-model-cache` (mounted at `/root/.cache/huggingface`)
- **jobs-data:** PVC `whisper-stt-jobs` (mounted at `/data`)

#### External Storage
- **HuggingFace Models:** Cached locally in PVCs
- **Model Sources:**
  - `deepdml/faster-whisper-large-v3-turbo-ct2`
  - `Systran/faster-whisper-large-v3-turbo` (symlinked)

### Configuration

#### Environment Variables
```yaml
POD: fieldRef (metadata.name)
NAMESPACE: fieldRef (metadata.namespace)
WHISPER_MODEL: distil-large-v3
# Additional variables from secret `whisper-stt-secret`
```

#### Secrets
- `whisper-stt-secret`: Configuration secrets

### Logging

#### Log Sources
- **Pod Logs:** Standard output from `whisper-stt` container
- **Log Volume:** No logs collected in research (0 lines)
- **Error Patterns:** None detected

Query:
```bash
# Get pod logs
kubectl --server=http://traefik-ardenone-cluster:8001 logs -n whisper-stt --tail=100

# Get logs from specific pod
kubectl --server=http://traefik-ardenone-cluster:8001 logs -n whisper-stt whisper-stt-847fd8d7b9-v2rs5 --tail=100
```

#### Victorialogs
- **Integration:** Configured but no data in research
- **Status:** Empty logs in JSONL file

### Network & Services

#### Services
- `whisper-stt`: ClusterIP for STT API

#### Endpoints
- **Health Check:** HTTP `/health` on port 8080
- **STT API:** HTTP on port 8080

#### Init Container
- **model-download:** Pre-loads HuggingFace models before main container starts
- **Resources:** 2 CPU, 2Gi memory (limit)
- **Cache Location:** `/root/.cache/huggingface`

### Container Registry

#### Image Sources
- **Primary:** `ronaldraygun/whisper-stt:1.8.6`
- **Secondary:** `fedirz/faster-whisper-server:latest-cpu` (cached via kuik)
- **Registry:** Docker Hub
- **Pull Policy:** Always (whisper-stt), IfNotPresent (whisper-openai)
- **Image Pull Secret:** `docker-hub-registry`

#### Local Cache
- **kuik.enix.io:** Image caching for faster pulls
- **Cached Images:** `fedirz/faster-whisper-server:latest-cpu`

### CI/CD Integration

#### Argo Workflows
- **Template:** `whisper-stt-build`
- **Trigger:** Image tag push to declarative-config
- **Output:** New image pushed to `ronaldraygun/whisper-stt`

#### ArgoCD
- **Application:** `whisper-stt-ns-ardenone-cluster`
- **Repo:** `jedarden/declarative-config`
- **Path:** `k8s/ardenone-cluster/whisper-stt/`

---

## Shared Infrastructure

### Cluster Information
- **Name:** ardenone-cluster
- **Type:** K3s
- **Access:** Tailscale VPN
- **Proxy:** `http://traefik-ardenone-cluster:8001` (read-only)
- **Nodes:**
  - `k3s-agent-minisforum` (primary for whisper-stt)
  - `k3s-lenovo-tiny` (primary for whisper-openai)

### ArgoCD
- **URL:** `https://argocd-ro-ardenone-manager-ts.ardenone.com:8444`
- **Read-Only API:** No authentication required (via proxy)
- **Applications:**
  - `pbx-web-ns-ardenone-cluster`
  - `whisper-stt-ns-ardenone-cluster`

### Monitoring & Observability

#### Victorialogs
- **Status:** Partially configured
- **Data:** No logs collected in research period
- **Query:** Not accessible via standard kubectl

#### Health Checks
- **pbx-web:** HTTP `/health` on port 9000
- **whisper-stt:** HTTP `/health` on port 8080

---

## Data Collection Patterns

### 30-Day Deployment Data Collection

#### Query Pattern
```bash
# ReplicaSets (deployment history)
kubectl --server=http://traefik-ardenone-cluster:8001 get replicasets -n <namespace> \
  --sort-by=.metadata.creationTimestamp \
  -o json > research/<service>-deployments-30days/replicasets.json

# Events
kubectl --server=http://traefik-ardenone-cluster:8001 get events -n <namespace> \
  --sort-by='.lastTimestamp' \
  -o json > research/<service>-deployments-30days/events.json

# Current pods
kubectl --server=http://traefik-ardenone-cluster:8001 get pods -n <namespace> \
  -o json > research/<service>-deployments-30days/pods.json

# Deployment status
kubectl --server=http://traefik-ardenone-cluster:8001 get deployment <deployment> -n <namespace> \
  -o json > research/<service>-deployments-30days/deployment.json
```

#### Data Processing Pipeline
1. **Raw Collection:** kubectl → JSON
2. **Filtering:** 30-day window based on timestamps
3. **Normalization:** Standardize field names
4. **Analysis:** Success rates, failure patterns, timelines
5. **Validation:** Schema validation (see `tests/unit/test_deployment_data_validation.py`)

### Log Collection Patterns

#### Pod Logs
```bash
# Current logs
kubectl --server=http://traefik-ardenone-cluster:8001 logs -n <namespace> --tail=1000

# Previous container logs (if restart occurred)
kubectl --server=http://traefik-ardenone-cluster:8001 logs -n <namespace> --previous

# Follow logs (streaming)
kubectl --server=http://traefik-ardenone-cluster:8001 logs -n <namespace> -f
```

#### Victorialogs
- **Format:** JSONL (one JSON object per line)
- **Query:** Not documented in research
- **Status:** Empty logs in research data

---

## Gaps & Missing Data Sources

### Known Gaps

1. **Victorialogs Integration**
   - **Status:** Configured but not returning data
   - **Impact:** No centralized log aggregation
   - **Recommended:** Investigate VictoriaLogs query syntax and API access

2. **Events Data Quality**
   - **Issue:** pbx-web events JSON was empty
   - **Impact:** Missing event-based failure detection
   - **Recommended:** Verify event collection permissions and time windows

3. **Whisper-STT Logs**
   - **Issue:** 0 log lines collected in research
   - **Impact:** Unable to detect whisper-stt error patterns
   - **Recommended:** Verify pod log retention and streaming

4. **Metrics Integration**
   - **Status:** No Prometheus/metrics scraping documented
   - **Impact:** No real-time performance metrics
   - **Recommended:** Add ServiceMonitors for scrape targets

5. **Argo Workflows Data**
   - **Status:** Build workflows referenced but not analyzed
   - **Impact:** Missing CI/CD success/failure rates
   - **Recommended:** Query Argo Workflow API for build history

6. **Network Policies**
   - **Status:** No network policy data collected
   - **Impact:** Unknown network access patterns
   - **Recommended:** Document NetworkPolicy resources if present

7. **Resource Usage Trends**
   - **Status:** Only snapshot data, no time series
   - **Impact:** No capacity planning visibility
   - **Recommended:** Set up metrics collection for CPU/memory usage

### Missing Data Sources

| Data Type | Status | Priority |
|-----------|--------|----------|
| Victorialogs query results | Not collected | High |
| Whisper-STT pod logs | Empty | High |
| Event streaming data | Incomplete | Medium |
| Argo Workflow history | Not queried | Medium |
| Prometheus metrics | Not configured | Medium |
| Network policy rules | Not documented | Low |
| PVC usage statistics | Not collected | Low |
| Node resource utilization | Not collected | Medium |

---

## Access Methods Summary

### Read-Only Access (Recommended)
```bash
# Kubernetes API (via proxy)
kubectl --server=http://traefik-ardenone-cluster:8001

# ArgoCD API (read-only)
curl -sk https://argocd-ro-ardenone-manager-ts.ardenone.com:8444/api/v1/applications
```

### Read-Write Access (Use with Caution)
```bash
# Direct kubeconfig
kubectl --kubeconfig=/home/coding/.kube/ardenone-cluster.kubeconfig

# WARNING: Never mutate ArgoCD-managed resources with kubectl
# All changes must go through declarative-config repo
```

### Automated Access
```python
# Python kubernetes client
from kubernetes import client, config

# Load kubeconfig
config.load_kube_config(config_file='/home/coding/.kube/ardenone-cluster.kubeconfig')

# Or use proxy
configuration = client.Configuration()
configuration.host = "http://traefik-ardenone-cluster:8001"
configuration.verify_ssl = False

api_instance = client.AppsV1Api(api_client=client.ApiClient(configuration))
```

---

## Validation & Schema

### Data Validation
All deployment data should be validated against the schema in `tests/unit/test_deployment_data_validation.py`:

```python
from src.validation.deployment_data import validate_deployment_data

# Validate deployment record
is_valid, error = validate_deployment_data(deployment_record)
if not is_valid:
    print(f"Validation error: {error}")
```

### Required Fields
- `service`: Service name (string)
- `period_days`: Analysis period in days (int)
- `total_deployments`: Total deployment count (int)
- `successful_deployments`: Successful deployment count (int)
- `failed_deployments`: Failed deployment count (int)
- `success_rate`: Success percentage (float)
- `failure_rate`: Failure percentage (float)
- `deployment_frequency_per_day`: Deployments per day (float)
- `mean_time_between_deployments_hours`: MTBD in hours (float)
- `deployment_names`: List of deployment names (list)
- `first_deployment`: ISO 8601 timestamp (string)
- `last_deployment`: ISO 8601 timestamp (string)

---

## References

### Related Documents
- `docs/research/deployment-analysis-30d.md` - 30-day comparative analysis
- `docs/research/deployment-analysis-30d.json` - Analysis data (JSON)
- `tests/unit/test_deployment_data_validation.py` - Data validation tests
- `docs/research/deployment_analysis_script.py` - Analysis automation script

### Research Directories
- `research/pbx-web-deployments-30days/` - Raw pbx-web data
- `research/whisper-stt-30days/` - Raw whisper-stt data
- `logs/` - Pod logs and Victorialogs data

### External References
- ArgoCD API: `https://argocd-ro-ardenone-manager-ts.ardenone.com:8444/api/v1/`
- Cluster Docs: `/home/coding/CLAUDE.md` (Kubernetes access section)

---

## Appendix: Query Examples

### Deployment Velocity Analysis
```bash
# Get all replica sets with creation timestamps
kubectl --server=http://traefik-ardenone-cluster:8001 get replicasets -n pbx-web \
  -o jsonpath='{range .items[*]}{.metadata.creationTimestamp}{"\t"}{.metadata.name}{"\t"}{.metadata.annotations.deployment\.kubernetes\.io/revision}{"\n"}{end}' | \
  sort
```

### Pod Restart Analysis
```bash
# Get pod restart counts
kubectl --server=http://traefik-ardenone-cluster:8001 get pods -n whisper-stt \
  -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.status.containerStatuses[0].restartCount}{"\n"}{end}'
```

### Event Timeline
```bash
# Get events with timestamps
kubectl --server=http://traefik-ardenone-cluster:8001 get events -n pbx-web \
  -o jsonpath='{range .items[*]}{.lastTimestamp}{"\t"}{.type}{"\t"}{.reason}{"\t"}{.message}{"\n"}{end}' | \
  sort -r
```

### PVC Usage
```bash
# Get PVC capacity and usage
kubectl --server=http://traefik-ardenone-cluster:8001 get pvc -n whisper-stt \
  -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.status.capacity.storage}{"\t"}{.status.phase}{"\n"}{end}'
```

---

**Document Version:** 1.0  
**Last Updated:** 2026-08-06  
**Maintained By:** aide-de-camp automation
