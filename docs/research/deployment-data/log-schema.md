# Deployment Log Schema Definition

## Overview

This document defines the output schema for normalizing deployment logs from multiple services (pbx-web, whisper-stt) into a unified structure. The schema supports analysis across different log formats while preserving the semantic meaning of deployment events.

## Analysis Summary

### Raw Log Files Analyzed

1. **PBX-WEB 30-Day Logs** (`logs/pbx-web-30day.jsonl`)
   - 16 valid entries
   - Multiple heterogeneous entry types
   - No malformed entries
   - Contains: pod info, deployment metrics, error patterns, health metrics

2. **WHISPER-STT 30-Day Logs** (`logs/whisper-stt-30day.jsonl`)
   - 1,027 valid entries
   - Three distinct entry types
   - No malformed entries
   - Contains: HTTP access logs, pod restarts, deployment events

### Key Findings

- **Format Differences**: Services use completely different logging approaches
  - PBX-WEB: Structured metadata with varied entry types (pod_info, deployment_metric, error_info, health_metric)
  - WHISPER-STT: Event-based logging with type field (http_access, pod_restart, deployment)

- **Timestamp Coverage**: 
  - PBX-WEB: Limited timestamp presence (mostly metadata)
  - WHISPER-STT: Only 27/1027 entries have explicit timestamps (deployment/pod_restart types)

- **Data Quality**: Both files have 100% valid JSON, no malformed entries

## Common Output Schema

### Unified Entry Structure

All normalized entries will conform to this schema:

```json
{
  "timestamp": "ISO 8601 timestamp (UTC)",
  "service": "pbx-web | whisper-stt | other",
  "event_type": "deployment | pod_info | error | health_metric | http_access | pod_restart",
  "status": "success | failure | warning | unknown",
  "error_code": "string or null",
  "duration_ms": "number or null",
  "cluster": "string",
  "namespace": "string",
  "metadata": {
    "source_fields": {},
    "raw_entry_type": "original entry type from source"
  }
}
```

## Field Mapping by Service

### PBX-WEB Field Mappings

| Source Entry Type | Output Event Type | Field Mappings |
|-------------------|-------------------|----------------|
| **metadata** | `metadata` | `namespace`, `cluster`, `analysis_period` → `metadata.time_period`, `data_collection_timestamp` → `timestamp` |
| **pod_info** | `pod_info` | `pod_name`, `age_days`, `restart_count`, `image`, `containers`, `status` → `status`, `health_status` → `metadata.health_status` |
| **deployment_metric** | `deployment` | `metric_type: "deployment_history"`, `current_deployment_age_days` → `duration_ms`, `pbx_web_replica_sets`, `oldest_replica_set_age_days` |
| **error_info** | `error` | `error_type` → `error_code`, `error_pattern`, `severity`, `context` → `metadata.context` |
| **health_metric** | `health_metric` | `health_metric`, `value`, `status`, `time_period` → `metadata.time_period` |

**Special Transformations:**
- `age_days` → `duration_ms: age_days * 24 * 60 * 60 * 1000`
- `health_status: "All pods running with 0 restarts"` → `status: "success"`
- `severity: "intermittent"` → `status: "warning"`

### WHISPER-STT Field Mappings

| Source Entry Type | Output Event Type | Field Mappings |
|-------------------|-------------------|----------------|
| **http_access** | `http_access` | `ip`, `request`, `status_code`, `message`, `is_error` → `status: "failure" if true`, `raw_line` → `metadata.raw` |
| **pod_restart** | `pod_restart` | `pod_name`, `restart_count`, `timestamp` → `timestamp`, `type` → `metadata.raw_entry_type` |
| **deployment** | `deployment` | `replica_set_name`, `creation_timestamp` → `timestamp`, `replicas`, `timestamp` (collection time) → `metadata.collection_timestamp` |

**Special Transformations:**
- `is_error: true` → `status: "failure"`
- `status_code: 200` → `status: "success"`
- `restart_count: 0` → `status: "success"`
- `replicas: 0` → `status: "failure"` (scaled-down deployment)

## Edge Cases and Handling

### Missing Fields

**PBX-WEB:**
- Most entries lack explicit timestamps
- Use derived timestamps from `age_days` or `analysis_period`
- For entries without time data: `timestamp: null`

**WHISPER-STT:**
- HTTP access logs (1000/1027 entries) lack explicit timestamps
- Use collection timestamp or leave null: `timestamp: null`
- Pod restart and deployment entries include timestamps

### Malformed Entries

- **Current state**: 0 malformed entries in both files
- **Handling strategy**: Skip malformed lines, log to error file, continue processing

### Inconsistent Data Patterns

**Status Codes:**
- HTTP logs: `status_code` (200, 500, etc.) → mapped to `status: "success|failure|warning"`
- Pod status: `status: "running|pending|failed"` → mapped to `status: "success|warning|failure"`

**Duration Representations:**
- PBX-WEB: `age_days`, `oldest_replica_set_age_days` → convert to `duration_ms`
- WHISPER-STT: No duration fields → `duration_ms: null`

**Error Patterns:**
- PBX-WEB: Structured error info with patterns
- WHISPER-STT: HTTP errors via status codes, inferred from `is_error`

## Data Type Definitions

```typescript
interface DeploymentLogEntry {
  timestamp: string | null;           // ISO 8601 UTC
  service: string;                     // Service name
  event_type: EventType;              // Enum: deployment, pod_info, error, health_metric, http_access, pod_restart
  status: EntryStatus;                 // Enum: success, failure, warning, unknown
  error_code: string | null;           // Error identifier or pattern
  duration_ms: number | null;          // Duration in milliseconds
  cluster: string;                      // Kubernetes cluster
  namespace: string;                   // Kubernetes namespace
  metadata: {
    source_fields: Record<string, any>;  // Original fields from source
    raw_entry_type: string;             // Original entry classification
    [key: string]: any;                 // Additional metadata
  };
}

type EventType = "deployment" | "pod_info" | "error" | "health_metric" | "http_access" | "pod_restart" | "metadata";
type EntryStatus = "success" | "failure" | "warning" | "unknown";
```

## Normalization Rules

### Status Normalization

| Source Field(s) | Output Status | Logic |
|----------------|---------------|-------|
| `is_error: true` | `failure` | Direct mapping |
| `status_code: 2xx` | `success` | HTTP success |
| `status_code: 5xx` | `failure` | HTTP server error |
| `status_code: 4xx` | `warning` | HTTP client error |
| `restart_count: 0` | `success` | No restarts |
| `restart_count: >0` | `warning` | Pod has restarted |
| `status: "running"` | `success` | Pod is healthy |
| `severity: "intermittent"` | `warning` | Intermittent error |
| `severity: "critical"` | `failure` | Critical error |

### Timestamp Normalization

1. **Explicit timestamps**: Use directly (convert to ISO 8601 if needed)
2. **Relative timestamps**: Calculate from reference time
   - `age_days: 8` → `timestamp: now() - (8 * 24h)`
3. **Missing timestamps**: Set to `null`, add to `metadata.timestamp_missing: true`

### Duration Normalization

- Convert all durations to milliseconds
- `days → ms`: `days * 24 * 60 * 60 * 1000`
- `hours → ms`: `hours * 60 * 60 * 1000`
- Preserve `null` when source has no duration data

## Implementation Notes

### Processing Order

1. **Load raw JSONL files** (service-specific)
2. **Detect entry type** (based on field presence or explicit `type` field)
3. **Apply field mappings** (per entry type)
4. **Normalize common fields** (timestamp, status, duration)
5. **Enrich with service metadata** (cluster, namespace defaults)
6. **Validate output schema** (type checking, required fields)
7. **Write normalized output** (unified JSONL)

### Validation Rules

- **Required fields**: `service`, `event_type`, `status`
- **Optional fields**: `timestamp`, `error_code`, `duration_ms`, `cluster`, `namespace`, `metadata`
- **Type enforcement**: Strict type checking on output schema
- **Enum validation**: `event_type` and `status` must match defined enums

## Usage Examples

### Example PBX-WEB Normalization

**Input:**
```json
{
  "pod_name": "pbx-web-5ff68464d-mkn8n",
  "age_days": 8,
  "restart_count": 0,
  "image": "ronaldraygun/pbx-web:1.0.9",
  "status": "running",
  "health_status": "All pods running with 0 restarts"
}
```

**Output:**
```json
{
  "timestamp": "2026-07-29T00:00:00Z",
  "service": "pbx-web",
  "event_type": "pod_info",
  "status": "success",
  "error_code": null,
  "duration_ms": 691200000,
  "cluster": "ardenone-cluster",
  "namespace": "pbx-web",
  "metadata": {
    "source_fields": {
      "pod_name": "pbx-web-5ff68464d-mkn8n",
      "restart_count": 0,
      "image": "ronaldraygun/pbx-web:1.0.9",
      "health_status": "All pods running with 0 restarts"
    },
    "raw_entry_type": "pod_info"
  }
}
```

### Example WHISPER-STT Normalization

**Input:**
```json
{
  "type": "deployment",
  "replica_set_name": "whisper-openai-55bb9fb46f",
  "creation_timestamp": "2026-06-14T04:11:57Z",
  "replicas": 0,
  "timestamp": "2026-06-14T04:11:57Z"
}
```

**Output:**
```json
{
  "timestamp": "2026-06-14T04:11:57Z",
  "service": "whisper-stt",
  "event_type": "deployment",
  "status": "failure",
  "error_code": "scaled_down",
  "duration_ms": null,
  "cluster": "ardenone-cluster",
  "namespace": "whisper-stt",
  "metadata": {
    "source_fields": {
      "replica_set_name": "whisper-openai-55bb9fb46f",
      "replicas": 0,
      "creation_timestamp": "2026-06-14T04:11:57Z"
    },
    "raw_entry_type": "deployment"
  }
}
```

## Limitations and Considerations

### Data Limitations

1. **Timestamp Coverage**: Limited in HTTP access logs (whisper-stt)
2. **Duration Data**: Not consistently available across services
3. **Cluster/Namespace**: Inferred from context, not explicit in all entries

### Processing Limitations

1. **Service-Specific Logic**: Each service requires custom field mapping
2. **Status Inference**: Some statuses inferred from heuristics, not explicit
3. **Timestamp Derivation**: Relative timestamps depend on processing time

### Future Considerations

1. **Schema Evolution**: May need to extend for additional services
2. **Error Classification**: Could add error taxonomy for deeper analysis
3. **Performance**: Large files (whisper-stt with 78MB victorialogs) need streaming processing

## Appendix: Field Inventory

### PBX-WEB Field Inventory

**All unique fields (31 total):**
```
age_days, analysis_period, available, cluster, containers, context, 
crashloopbackoff_events, current_deployment_age_days, data_collection_timestamp, 
data_limitation_summary, data_sources, deployment_frequency, duration_hours, end, 
entries, error_pattern, error_type, frequency, health_metric, health_status, image, 
latency_indicator, limitation, log_coverage, metric_type, namespace, 
oldest_replica_set_age_days, oomkilled_events, pbx_web_replica_sets, period, 
pod_name, restart_count, severity, start, status, status_code, time_period, value
```

### WHISPER-STT Field Inventory

**All unique fields (7 total):**
```
ip, is_error, message, raw_line, request, status_code, type, 
pod_name, restart_count, timestamp, replica_set_name, creation_timestamp, replicas
```

---

**Document Version:** 1.0  
**Last Updated:** 2026-08-06  
**Author:** aide-de-camp analysis automation  
**Purpose:** Schema definition for deployment log normalization across pbx-web and whisper-stt services