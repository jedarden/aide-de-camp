# whisper-stt 30-Day Deployment Log Research

## Overview

This research directory contains collected and analyzed logs from the `whisper-stt` deployment on the `nixos-asterisk` cluster, covering the period from **2026-07-07 to 2026-08-06** (30 days). The goal is to analyze deployment patterns, failure modes, and operational characteristics to inform future deployment strategies.

## Time Range

- **Start Date:** 2026-07-07
- **End Date:** 2026-08-06
- **Duration:** 30 days

## Data Sources

### 1. Kubernetes Events
- **Source:** `nixos-asterisk` cluster
- **Namespace:** `whisper-stt` (or relevant namespace where the workload runs)
- **Collection Method:** `kubectl get events --sort-by=.metadata.creationTimestamp -n <namespace>`
- **Purpose:** Track pod lifecycle events, scaling events, image pull errors, OOMKills, and other cluster-level anomalies

### 2. Argo Workflow Logs
- **Source:** `iad-ci` cluster (Argo Workflows)
- **Namespace:** `argo-workflows`
- **Workflow Template:** `whisper-stt-build`
- **Collection Method:** `kubectl get workflows -n argo-workflows -l workflows.argoproj.io/workflow-template=whisper-stt-build`
- **Purpose:** Track CI/CD pipeline executions, build failures, deployment timings, and workflow success/failure rates

### 3. Pod Logs
- **Source:** `nixos-asterisk` cluster
- **Namespace:** `whisper-stt` (or relevant namespace)
- **Pod Selector:** `app.kubernetes.io/name=whisper-stt` (or actual label)
- **Collection Method:** `kubectl logs -n <namespace> -l <selector> --since-time=<timestamp>`
- **Purpose:** Application-level logging, startup sequence, runtime errors, request patterns, and resource utilization indicators

## Directory Structure

```
research/whisper-stt-30days/
├── README.md                           # This file
├── k8s-events.jsonl                   # Kubernetes events (one JSON object per line)
├── argo-workflows.jsonl                # Argo workflow records (one JSON object per line)
├── deployment-analysis.md              # Summary analysis and findings
├── pod-logs/                           # Collected pod logs by date
│   ├── 2026-07-07.log                  # Logs from 2026-07-07
│   ├── 2026-07-08.log                  # Logs from 2026-07-08
│   └── ...                             # One file per day
└── queries/                            # kubectl/AWS CLI queries used for collection
    ├── get-k8s-events.sh
    ├── get-argo-workflows.sh
    └── get-pod-logs.sh
```

## File Naming Conventions

### Kubernetes Events
- **Filename:** `k8s-events.jsonl`
- **Format:** JSONL (one JSON-encoded Kubernetes Event object per line)
- **Sorting:** Chronologically by `.lastTimestamp`

### Argo Workflow Records
- **Filename:** `argo-workflows.jsonl`
- **Format:** JSONL (one JSON-encoded Workflow object per line)
- **Fields included:** `metadata.name`, `metadata.creationTimestamp`, `status.phase`, `status.startedAt`, `status.finishedAt`, `status.message`, `spec.arguments`

### Pod Logs
- **Filename:** `YYYY-MM-DD.log` (e.g., `2026-07-07.log`)
- **Format:** Raw text logs from container stdout/stderr
- **Organization:** One file per calendar day

## Expected Data Schemas

### k8s-events.jsonl

Each line is a Kubernetes Event object with relevant fields:

```json
{
  "metadata": {
    "name": "whisper-stt-pod-abc123.12d3e456",
    "namespace": "whisper-stt",
    "creationTimestamp": "2026-07-07T10:30:00Z"
  },
  "involvedObject": {
    "kind": "Pod",
    "name": "whisper-stt-7d6f8c9b-x4k2m",
    "namespace": "whisper-stt"
  },
  "reason": "Started",
  "message": "Started container",
  "type": "Normal",
  "firstTimestamp": "2026-07-07T10:30:00Z",
  "lastTimestamp": "2026-07-07T10:30:00Z",
  "count": 1
}
```

### argo-workflows.jsonl

Each line is a Workflow object with relevant fields:

```json
{
  "metadata": {
    "name": "whisper-stt-build-xyz789",
    "namespace": "argo-workflows",
    "creationTimestamp": "2026-07-07T11:00:00Z"
  },
  "status": {
    "phase": "Succeeded",
    "startedAt": "2026-07-07T11:00:00Z",
    "finishedAt": "2026-07-07T11:15:23Z",
    "message": ""
  },
  "spec": {
    "arguments": {
      "parameters": [
        {"name": "git-revision", "value": "abc123def"}
      ]
    }
  }
}
```

### Pod Logs (YYYY-MM-DD.log)

Raw text output in the application's log format. Timestamps should be in ISO 8601 format or parseable by standard log parsers.

## Collection Queries

Example kubectl commands for data collection (stored in `queries/`):

```bash
# Get all events from the time range
kubectl get events --all-namespaces \
  --field-selector creationTimestamp'>=2026-07-07T00:00:00Z',creationTimestamp'<2026-08-07T00:00:00Z' \
  --sort-by=.lastTimestamp \
  -o json

# Get workflows from the template
kubectl get workflows -n argo-workflows \
  -l workflows.argoproj.io/workflow-template=whisper-stt-build \
  --field-selector creationTimestamp'>=2026-07-07T00:00:00Z',creationTimestamp'<2026-08-07T00:00:00Z' \
  -o json

# Get pod logs for a specific day
kubectl logs -n whisper-stt -l app.kubernetes.io/name=whisper-stt \
  --since-time=2026-07-07T00:00:00Z \
  --until-time=2026-07-08T00:00:00Z \
  --timestamps=true
```

## Research Questions

This data collection aims to answer:

1. **Deployment Frequency:** How often was whisper-stt deployed over the 30-day period?
2. **Success Rate:** What percentage of deployments succeeded on the first attempt?
3. **Failure Modes:** What are the common failure patterns (image pull errors, config validation, runtime crashes)?
4. **Deployment Duration:** What is the typical time from workflow start to pod ready?
5. **Rollback Frequency:** How often were deployments rolled back or pods restarted?
6. **Resource Issues:** Are there OOMKills, CPU throttling, or eviction events?
7. **Scaling Events:** Did the deployment trigger horizontal pod autoscaler events?
8. **Peak Activity:** What times of day show the most deployment activity?

## Analysis Output

Once data is collected, create `deployment-analysis.md` with:

1. Summary statistics (deployment count, success rate, mean duration)
2. Timeline visualization of deployments
3. Categorization of failure modes with counts
4. Notable anomalies or outliers
5. Recommendations for deployment process improvements

## Notes

- All timestamps should be in UTC
- The cluster to query depends on where whisper-stt is deployed (verify: `nixos-asterisk` or another)
- Ensure kubectl access is configured for the appropriate cluster
- For large datasets, consider pagination or time-windowed queries to avoid timeouts

## Related Documentation

- `docs/notes/whisper-stt.md` (if exists) - Application-specific notes
- `declarative-config/k8s/nixos-asterisk/` (if exists) - Kubernetes manifests
- CLAUDE.md - Cluster access and kubectl configuration details
