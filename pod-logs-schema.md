# Pod Logs Index JSONL Schema

## Overview

This schema defines the structure for `pod-logs-index.jsonl`, which documents all collected pod logs and their analysis. Each line in the JSONL file represents one pod log entry with complete metadata.

## Schema Definition

### Field Specifications

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `pod_name` | string | Yes | Kubernetes pod name (e.g., `pbx-web-5ff68464d-mkn8n`) |
| `namespace` | string | Yes | Kubernetes namespace (e.g., `default`, `production`) |
| `creation_timestamp` | string (ISO 8601) | Yes | Pod creation timestamp (UTC) |
| `deletion_timestamp` | string (ISO 8601) or null | Yes | Pod deletion timestamp (UTC), or `null` if still running |
| `log_file_path` | string | Yes | Relative path to log file from research directory root |
| `analysis_file_path` | string or null | Yes | Relative path to analysis file, or `null` if analysis doesn't exist |
| `log_size_bytes` | integer | Yes | Size of log file in bytes |
| `detected_patterns` | array of strings | Yes | List of pattern types detected (startup, oom_kill, error, performance) |
| `key_timestamps` | object | Yes | Important timestamps extracted from logs |
| `collection_date` | string (ISO 8601) | Yes | When this log entry was collected |
| `log_line_count` | integer | Yes | Number of lines in log file |
| `restart_count` | integer | Yes | Number of pod restarts |
| `pod_phase` | string or null | Yes | Pod phase (Running, Pending, Succeeded, Failed, Unknown) |
| `container_image` | string or null | Yes | Container image reference |
| `node_name` | string or null | Yes | Kubernetes node where pod ran |

### Nested Objects

#### detected_patterns

Array of pattern type strings detected in the log analysis. Only pattern types with `count > 0` in the analysis file are included.

**Allowed pattern types:**
- `"startup"` - Application startup and initialization events
- `"oom_kill"` - Out of memory kill events  
- `"error"` - Error messages and exceptions
- `"performance"` - Performance-related events (slow queries, timeouts, etc.)

**Examples:**
- `["startup", "error"]` - Both startup and error patterns detected
- `["oom_kill"]` - Only OOM killer events detected
- `[]` - No patterns detected (empty array)

**Data source:** Populated from corresponding `-analysis.json` file by checking which pattern categories have non-zero counts.

#### key_timestamps

Important temporal boundaries for the log:

```json
{
  "first_log_entry": "2026-07-07T00:00:00Z",
  "last_log_entry": "2026-08-06T23:59:59Z",
  "analysis_date": "2026-08-06T13:40:23.600509Z"
}
```

**Timestamp Fields:**
- `first_log_entry`: string (ISO 8601) or null - Earliest timestamp found in log
- `last_log_entry`: string (ISO 8601) or null - Latest timestamp found in log
- `analysis_date`: string (ISO 8601) or null - When analysis was performed

## Example JSONL Entries

### Complete Entry with All Data

```json
{
  "pod_name": "pbx-web-5ff68464d-mkn8n",
  "namespace": "default",
  "creation_timestamp": "2026-07-28T17:26:12Z",
  "deletion_timestamp": null,
  "log_file_path": "research/pbx-web-30days/pod-logs/pbx-web-5ff68464d-mkn8n-2026-08-06.log",
  "analysis_file_path": "research/pbx-web-30days/pod-logs/pbx-web-5ff68464d-mkn8n-2026-08-06-analysis.json",
  "log_size_bytes": 4200000,
  "detected_patterns": {
    "startup": {"count": 3, "timestamps": ["2026-07-28T17:26:15Z", "2026-07-28T17:26:18Z", "2026-07-28T17:26:20Z"], "samples": ["Starting server...", "Listening on port 8000"]},
    "oom_kill": {"count": 0, "timestamps": [], "samples": []},
    "error": {"count": 12, "timestamps": ["2026-07-29T02:15:33Z", "2026-07-30T10:20:45Z"], "samples": ["Error: Connection refused", "ERROR: Failed query"]},
    "performance": {"count": 5, "timestamps": ["2026-07-30T10:20:45Z"], "samples": ["Slow query: 5.2s", "Request timeout"]}
  },
  "key_timestamps": {
    "first_log_entry": "2026-07-28T17:26:15Z",
    "last_log_entry": "2026-08-06T23:59:58Z",
    "analysis_date": "2026-08-06T13:40:20.792334Z"
  },
  "collection_date": "2026-08-06T13:43:00Z"
}
```

### Minimal Entry (No Analysis File)

```json
{
  "pod_name": "whisper-stt-847fd8d7b9-v2rs5",
  "namespace": "production",
  "creation_timestamp": "2026-08-01T10:30:00Z",
  "deletion_timestamp": "2026-08-03T15:45:00Z",
  "log_file_path": "research/whisper-stt-30days/pod-logs/pod-whisper-stt-847fd8d7b9-v2rs5-2026-08-06.log",
  "analysis_file_path": null,
  "log_size_bytes": 1024,
  "detected_patterns": {
    "startup": {"count": 0, "timestamps": [], "samples": []},
    "oom_kill": {"count": 0, "timestamps": [], "samples": []},
    "error": {"count": 0, "timestamps": [], "samples": []},
    "performance": {"count": 0, "timestamps": [], "samples": []}
  },
  "key_timestamps": {
    "first_log_entry": null,
    "last_log_entry": null,
    "analysis_date": null
  },
  "collection_date": "2026-08-06T14:30:00Z"
}
```

### Entry with Empty Log File

```json
{
  "pod_name": "lab-rebuild-relay-79957dbd4-xsqhl",
  "namespace": "default",
  "creation_timestamp": "2026-07-27T17:56:07Z",
  "deletion_timestamp": null,
  "log_file_path": "research/pbx-web-30days/pod-logs/pod-lab-rebuild-relay-79957dbd4-xsqhl-2026-08-06.log",
  "analysis_file_path": "research/pbx-web-30days/pod-logs/pod-lab-rebuild-relay-79957dbd4-xsqhl-2026-08-06-analysis.json",
  "log_size_bytes": 0,
  "detected_patterns": {
    "startup": {"count": 0, "timestamps": [], "samples": []},
    "oom_kill": {"count": 0, "timestamps": [], "samples": []},
    "error": {"count": 0, "timestamps": [], "samples": []},
    "performance": {"count": 0, "timestamps": [], "samples": []}
  },
  "key_timestamps": {
    "first_log_entry": null,
    "last_log_entry": null,
    "analysis_date": "2026-08-06T13:40:21.100000Z"
  },
  "collection_date": "2026-08-06T13:43:05Z"
}
```

### Entry with Previous Log Stream (Pod Restart)

```json
{
  "pod_name": "whisper-stt-847fd8d7b9-v2rs5",
  "namespace": "production",
  "creation_timestamp": "2026-07-25T08:00:00Z",
  "deletion_timestamp": "2026-08-06T12:00:00Z",
  "log_file_path": "research/whisper-stt-30days/pod-logs/pod-whisper-stt-847fd8d7b9-v2rs5-2026-08-06-previous.log",
  "analysis_file_path": "research/whisper-stt-30days/pod-logs/pod-whisper-stt-847fd8d7b9-v2rs5-2026-08-06-previous-analysis.json",
  "log_size_bytes": 1500,
  "detected_patterns": {
    "startup": {"count": 1, "timestamps": ["2026-07-25T08:00:05Z"], "samples": ["Starting application..."]},
    "oom_kill": {"count": 1, "timestamps": ["2026-07-28T14:30:00Z"], "samples": ["Kill process due to OOM"]},
    "error": {"count": 0, "timestamps": [], "samples": []},
    "performance": {"count": 0, "timestamps": [], "samples": []}
  },
  "key_timestamps": {
    "first_log_entry": "2026-07-25T08:00:05Z",
    "last_log_entry": "2026-07-28T14:30:00Z",
    "analysis_date": "2026-08-06T13:40:23.600509Z"
  },
  "collection_date": "2026-08-06T14:30:00Z"
}
```

## Edge Cases and Handling

### 1. Missing Analysis File
When no analysis file exists:
- Set `analysis_file_path` to `null`
- Set all pattern counts to 0 with empty `timestamps` and `samples` arrays
- Set `key_timestamps.analysis_date` to `null`

### 2. Empty Log Files
When log file size is 0 bytes:
- Set `log_size_bytes` to 0
- Set all pattern detections to empty/default values (count 0, empty arrays)
- Set `key_timestamps.first_log_entry` and `last_log_entry` to `null`

### 3. Missing Timestamps
When log parsing fails to extract timestamps:
- Set `first_log_entry` and `last_log_entry` to `null`
- Set pattern `timestamps` arrays to empty even if `count > 0`
- Preserve `count` values but leave `timestamps` and `samples` as empty arrays

### 4. Pod Still Running
When pod has not been deleted:
- Set `deletion_timestamp` to `null`
- This indicates the pod was still running at collection time

### 5. Namespace Inference
When namespace is not directly available from filename:
- Infer from parent directory structure (e.g., `research/<service>-30days/`)
- Default to "default" if cannot be determined
- Document inference method in collection metadata

## Schema Validation Rules

### Required Fields
All top-level fields must be present in every entry. Null values are acceptable where specified.

### Data Type Constraints
- All integers must be non-negative
- ISO 8601 timestamps must be in UTC (Z suffix)
- Boolean fields must be literal `true` or `false`
- Arrays and objects must be valid JSON structures

### File Path Constraints
- Paths must be relative to research directory root
- Paths must use forward slashes (/)
- Paths must not contain parent directory references (../)

### Timestamp Consistency
When multiple timestamps are present:
- `first_log_entry` ≤ `last_log_entry` (when both non-null)
- Pattern `first_occurrence` ≥ `first_log_entry` (when both non-null)
- Pattern `last_occurrence` ≤ `last_log_entry` (when both non-null)
- `collection_date` ≥ `analysis_date` (when both non-null)

## Mapping to Parent Bead Requirements

This schema satisfies the requirements specified in parent bead `adc-5pryi`:

| Parent Requirement | Schema Field(s) | Type |
|-------------------|----------------|------|
| pod_name | `pod_name` | string |
| namespace | `namespace` | string |
| creation_timestamp | `creation_timestamp` | ISO timestamp |
| deletion_timestamp | `deletion_timestamp` | ISO timestamp or null |
| log_file_path | `log_file_path` | string (relative path) |
| analysis_file_path | `analysis_file_path` | string or null |
| detected_patterns | `detected_patterns` | object with 4 pattern categories |
| key_timestamps | `key_timestamps` | object with temporal boundaries |
| **(additional)** | `log_size_bytes` | integer |
| **(additional)** | `collection_date` | ISO timestamp |

The schema extends parent requirements by adding:
- `log_size_bytes` for storage analysis
- `collection_date` for audit trail
- Structured pattern objects with `has_evidence` boolean
- Null handling for missing data

## Usage Notes

### File Organization
The index expects a consistent directory structure:
```
research/
├── <service>-30days/
│   └── pod-logs/
│       ├── pod-<name>-<date>.log
│       ├── pod-<name>-<date>-analysis.json
│       └── pod-logs-index.jsonl
```

### Scanner Script Integration
The schema is designed to work with `scripts/scan-pod-logs.py`:
1. Scan pod-logs/ directory for .log and -analysis.json pairs
2. Extract metadata from filenames and file contents
3. Read analysis JSON for pattern detection results
4. Compute file sizes and validate paths
5. Output one JSON line per log entry following this schema

### Query Patterns
Common query patterns this schema supports:
- Find all logs with specific pattern: `jq 'select(.detected_patterns.error.has_evidence == true)'`
- List logs by size: `jq 'sort_by(.log_size_bytes) | reverse'`
- Filter by namespace: `jq 'select(.namespace == "production")'`
- Time range queries: `jq 'select(.key_timestamps.first_log_entry >= "2026-07-01")'`
- Missing analysis detection: `jq 'select(.analysis_file_path == null)'`

## Version History

- **v1.0** (2026-08-06): Initial schema definition based on pod-logs structure analysis and parent bead adc-5pryi requirements