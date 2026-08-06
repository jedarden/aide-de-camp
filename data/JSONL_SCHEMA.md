# Deployment Log JSONL Schema Documentation

## Overview
This document defines the JSONL (JSON Lines) schema used for storing deployment logs for pbx-web and whisper-stt services. Each file contains one JSON object per line, with consistent schemas based on log entry types.

## File Structure

### Log Files
- `data/pbx-web-logs.jsonl` - Deployment logs for pbx-web service
- `data/whisper-stt-logs.jsonl` - Deployment logs for whisper-stt service

### General JSONL Format
- **Format**: One valid JSON object per line
- **Line separator**: `\n` (newline)
- **Encoding**: UTF-8
- **Compression**: Optional gzip compression (`.jsonl.gz`)

## Common Fields (All Log Types)

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `log_type` | string | Yes | Type of log entry (determines schema) |
| `service` | string | Yes | Service name (`pbx-web`, `whisper-stt`) |
| `timestamp` | string (ISO 8601) | Conditional | Event timestamp (UTC) |
| `source` | string | Yes | Data collection source |

## Log Type Schemas

### 1. Metadata Entry
**Purpose**: File header with collection metadata
**Frequency**: First line in file

```json
{
  "log_type": "metadata",
  "service": "string",
  "collection_date": "YYYY-MM-DD",
  "period_days": number,
  "description": "string",
  "sources": ["array", "of", "sources"]
}
```

**Fields**:
- `collection_date` - Date when logs were collected (ISO 8601 date)
- `period_days` - Retention period in days (typically 30)
- `description` - Human-readable description
- `sources` - Array of data source types

### 2. Pod Log Entry
**Purpose**: References to individual pod log files

```json
{
  "log_type": "pod_log",
  "service": "string",
  "pod_name": "string",
  "log_file": "string",
  "file_path": "string",
  "file_size_bytes": number,
  "source": "kubectl_logs",
  "collected_date": "YYYY-MM-DD"
}
```

**Fields**:
- `pod_name` - Kubernetes pod name
- `log_file` - Base name of log file
- `file_path` - Full path to log file
- `file_size_bytes` - Size in bytes
- `collected_date` - Collection date (ISO 8601 date)

### 3. Replica Set Entry
**Purpose**: Historical replica set deployment information

```json
{
  "log_type": "replica_set",
  "service": "string",
  "replica_set_name": "string",
  "revision": number,
  "created": "YYYY-MM-DDTHH:MM:SSZ",
  "replicas": number,
  "ready_replicas": number or null,
  "image": "string",
  "source": "kubernetes_api"
}
```

**Fields**:
- `replica_set_name` - Kubernetes ReplicaSet name
- `revision` - Deployment revision number
- `created` - Creation timestamp (ISO 8601 datetime)
- `replicas` - Current replica count
- `ready_replicas` - Ready replica count (null if zero)
- `image` - Container image reference

### 4. Deployment Event Entry
**Purpose**: Deployment status and infrastructure events

```json
{
  "log_type": "deployment_event",
  "service": "string",
  "timestamp": "YYYY-MM-DDTHH:MM:SSZ",
  "event_type": "string",
  "deployment_name": string or null,
  "namespace": string or null,
  "replicas": number or null,
  "available_replicas": number or null,
  "ready_replicas": number or null,
  "revision": number or null,
  "image": string or null,
  "status": string or null,
  "source": "deployment_analysis"
}
```

**Event Types**:
- `collection_start` - Log collection started
- `collection_end` - Log collection completed
- `deployment_status` - Current deployment status
- `pod_status` - Pod phase/status
- `pvc_status` - Persistent volume claim status
- `health_check` - Health check results
- `resource_spec` - Resource specifications
- `infrastructure_check` - Infrastructure validation

### 5. Kubernetes Deployment Entry
**Purpose**: Historical deployment revision tracking

```json
{
  "log_type": "kubernetes_deployment",
  "service": "string",
  "timestamp": "YYYY-MM-DDTHH:MM:SSZ",
  "revision": number,
  "replica_set": "string",
  "image": "string",
  "status": "string",
  "source": "kubernetes_api"
}
```

**Fields**:
- `revision` - Deployment revision number
- `replica_set` - Associated ReplicaSet name
- `status` - Replica availability (e.g., "1/1", "0/0")

### 6. Kubernetes Event Entry
**Purpose**: Kubernetes events (warnings, errors, state changes)

```json
{
  "log_type": "kubernetes_event",
  "service": "string",
  "timestamp": "YYYY-MM-DDTHH:MM:SSZ",
  "event_type": "string",
  "reason": string or null,
  "message": "string",
  "source": "kubernetes_events"
}
```

**Event Types**:
- `replicaset_created` - New ReplicaSet created
- `pod_created` - Pod entered Pending phase
- `k8s_event_warning` - Kubernetes warning events
- `k8s_event_normal` - Kubernetes normal events

### 7. Pod Inventory Entry
**Purpose**: Current and historical pod tracking

```json
{
  "log_type": "pod_inventory",
  "service": "string",
  "timestamp": string or null,
  "pod_name": string or null,
  "namespace": "string",
  "status": "current" or "historical",
  "ready": string or null,
  "restart_count": number,
  "node": "string",
  "image": "string",
  "source": "pod_inventory"
}
```

**Fields**:
- `status` - `"current"` for active pods, `"historical"` for old pods
- `restart_count` - Container restart count
- `node` - Kubernetes node name

### 8. Argo Workflow Entry
**Purpose**: CI/CD workflow execution tracking

```json
{
  "log_type": "argo_workflow",
  "service": "string",
  "timestamp": string or null,
  "workflow_name": "string",
  "status": "string",
  "error_message": string or null,
  "source": "argo_workflows"
}
```

**Status Values**:
- `Succeeded` - Workflow completed successfully
- `Failed` - Workflow failed
- `Running` - Currently executing
- `not_found` - No executions found

## Data Sources

Log entries are collected from multiple sources:

| Source | Description | Log Types |
|--------|-------------|-----------|
| `kubectl_logs` | Pod logs via kubectl | `pod_log` |
| `kubernetes_api` | Kubernetes API queries | `replica_set`, `kubernetes_deployment` |
| `kubernetes_events` | Kubernetes event stream | `kubernetes_event` |
| `argo_workflows` | Argo Workflows API | `argo_workflow` |
| `deployment_analysis` | Deployment health checks | `deployment_event` |
| `pod_inventory` | Pod status queries | `pod_inventory` |

## Retention and Cleanup

- **Retention Period**: 30 days (configurable via `period_days`)
- **Collection Date**: UTC date of collection
- **Rotation**: New files created on each collection run
- **Archiving**: Historical files compressed with gzip

## Quality Checks

### Validation Rules
1. **Required Fields**: All entries must have `log_type` and `service`
2. **Timestamp Format**: ISO 8601 (YYYY-MM-DDTHH:MM:SSZ or YYYY-MM-DD)
3. **UTF-8 Encoding**: All text fields UTF-8 encoded
4. **JSON Validity**: Each line must be valid JSON
5. **No Empty Lines**: File should not contain empty lines

### Consistency Checks
- First line should be `log_type: "metadata"`
- `timestamp` values should be within collection period
- `service` should match filename
- `source` should match documented sources

## Usage Examples

### Reading JSONL Files (Python)
```python
import json

# Read line-by-line
with open('data/pbx-web-logs.jsonl', 'r') as f:
    for line in f:
        entry = json.loads(line)
        if entry['log_type'] == 'pod_log':
            print(f"Pod: {entry['pod_name']}, Size: {entry['file_size_bytes']}")

# Filter by log type
pod_logs = []
with open('data/pbx-web-logs.jsonl', 'r') as f:
    for line in f:
        entry = json.loads(line)
        if entry['log_type'] == 'pod_log':
            pod_logs.append(entry)
```

### Writing JSONL Files (Python)
```python
import json
from datetime import datetime

entries = [
    {
        "log_type": "metadata",
        "service": "pbx-web",
        "collection_date": "2026-08-06",
        "period_days": 30,
        "description": "Raw deployment logs for pbx-web service (last 30 days)",
        "sources": ["pod_logs", "replica_sets", "kubernetes_events"]
    },
    {
        "log_type": "pod_log",
        "service": "pbx-web",
        "pod_name": "pbx-web-5ff68464d-mkn8n",
        "log_file": "pbx-web-5ff68464d-mkn8n.log",
        "file_path": "/path/to/log",
        "file_size_bytes": 62900,
        "source": "kubectl_logs",
        "collected_date": "2026-08-06"
    }
]

with open('data/pbx-web-logs.jsonl', 'w') as f:
    for entry in entries:
        f.write(json.dumps(entry) + '\n')
```

### Query Examples (jq)
```bash
# Get all pod log entries
jq 'select(.log_type == "pod_log")' data/pbx-web-logs.jsonl

# Count entries by type
jq -r '.log_type' data/pbx-web-logs.jsonl | sort | uniq -c

# Get error events
jq 'select(.event_type == "k8s_event_warning")' data/whisper-stt-logs.jsonl
```

## Maintenance

### Adding New Log Types
1. Document schema in this file
2. Add to "Log Type Schemas" section
3. Update "Data Sources" table
4. Provide usage examples

### Schema Versioning
- Version: 1.0 (2026-08-06)
- Backwards compatibility maintained when possible
- Breaking changes documented with migration guide

## Future Enhancements

Potential additions to consider:
- Add `log_version` field for schema tracking
- Include `cluster` field for multi-cluster support
- Add `severity` field for filtering errors/warnings
- Include `tags` field for flexible categorization
- Add correlation IDs for multi-event tracking