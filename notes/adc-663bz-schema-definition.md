# Pod-Logs JSONL Schema Definition

## Schema Overview
**Version**: 1.0  
**Format**: JSON Lines (JSONL) - one JSON object per line  
**Purpose**: Index pod log files with metadata and analysis results  
**Parent Requirement**: adc-4q6sr (Extract and analyze pod-logs structure requirements)

**Total Fields**: 28 across 5 categories  
**Required Top-Level Fields**: All 28 (null allowed where specified)

---

## Schema Structure

### Root Object
```json
{
  "pod_identification": { /* 8 fields */ },
  "log_file_metadata": { /* 5 fields */ },
  "analysis_metadata": { /* 2 fields */ },
  "pattern_detection": { /* 4 pattern categories */ },
  "temporal_boundaries": { /* 4 fields */ }
}
```

---

## Field Definitions by Category

### 1. Pod Identification (`pod_identification`)

| Field | Type | Required | Nullable | Format/Constraints | Source | Example |
|-------|------|----------|----------|---------------------|--------|---------|
| `pod_name` | `string` | Yes | No | Non-empty, valid DNS subdomain | Filename + metadata | `"pbx-web-5ff68464d-mkn8n"` |
| `namespace` | `string` | Yes | No | Non-empty, valid Kubernetes namespace name | Directory structure | `"pbx-web"` or `"whisper-stt"` |
| `pod_phase` | `string` | Yes | Yes | Enum: `Pending`, `Running`, `Succeeded`, `Failed`, `Unknown` | pods-list.jsonl | `"Running"` |
| `restart_count` | `integer` | Yes | No | ≥ 0 | pods-list.jsonl | `0` or `3` |
| `creation_timestamp` | `string` | Yes | Yes | ISO 8601 UTC (Z suffix) | pods-list.jsonl | `"2026-07-28T17:26:12Z"` |
| `deletion_timestamp` | `string` | Yes | Yes | ISO 8601 UTC (Z suffix) or null | pods-list.jsonl | `null` or `"2026-08-06T10:00:00Z"` |
| `container_image` | `string` | Yes | Yes | Valid container image reference | pods-list.jsonl | `"ronaldraygun/pbx-web:1.0.9"` |
| `node_name` | `string` | Yes | Yes | Valid Kubernetes node name | pods-list.jsonl | `"k3s-agent-minisforum"` |

**Validation Rules:**
- `pod_name`: Must match regex `^[a-z0-9]([-a-z0-9]*[a-z0-9])?$` (DNS subdomain)
- `namespace`: Must match regex `^[a-z0-9]([-a-z0-9]*[a-z0-9])?$`
- `pod_phase`: Must be one of the 5 enum values
- `restart_count`: Must be non-negative integer
- `creation_timestamp`: Must parse as valid ISO 8601 datetime with Z suffix
- `deletion_timestamp`: If non-null, must parse as valid ISO 8601 datetime with Z suffix; must be ≥ creation_timestamp
- `container_image`: Must match `([^/]+/)?[^:]+(:[^:]+)?` format
- `node_name`: Non-empty string if provided

---

### 2. Log File Metadata (`log_file_metadata`)

| Field | Type | Required | Nullable | Format/Constraints | Source | Example |
|-------|------|----------|----------|---------------------|--------|---------|
| `log_file_path` | `string` | Yes | No | Relative path, POSIX format | Directory scan | `"research/pbx-web-30days/pod-logs/pod-pbx-web-5ff68464d-mkn8n-2026-08-06.log"` |
| `log_size_bytes` | `integer` | Yes | No | ≥ 0 | File system | `62900` or `4392661` |
| `log_line_count` | `integer` | Yes | Yes | ≥ 0 | Analysis file | `2762` |
| `collection_date` | `string` | Yes | No | ISO 8601 date (YYYY-MM-DD) | Filename | `"2026-08-06"` |
| `log_type` | `string` | Yes | Yes | Enum: `current`, `previous`, `stderr`, or null | Filename | `"current"` or `null` |

**Validation Rules:**
- `log_file_path`: Must be relative path (no leading `/`), must use forward slashes, must reference `.log` file
- `log_size_bytes`: Must be non-negative integer, can be 0 for empty files
- `log_line_count`: If non-null, must be non-negative integer; if 0, log file may be empty
- `collection_date`: Must match regex `^\d{4}-\d{2}-\d{2}$`, must be valid date
- `log_type`: Must be one of 4 enum values or null

---

### 3. Analysis Metadata (`analysis_metadata`)

| Field | Type | Required | Nullable | Format/Constraints | Source | Example |
|-------|------|----------|----------|---------------------|--------|---------|
| `analysis_file_path` | `string` | Yes | Yes | Relative path, POSIX format, or null | Directory scan | `"pod-pbx-web-5ff68464d-mkn8n-2026-08-06-analysis.json"` or `null` |
| `analysis_date` | `string` | Yes | Yes | ISO 8601 datetime with microseconds, or null | Analysis JSON | `"2026-08-06T13:40:21.580554"` or `null` |

**Validation Rules:**
- `analysis_file_path`: If non-null, must be relative path, must reference `-analysis.json` file
- `analysis_date`: If non-null, must parse as valid ISO 8601 datetime with optional microseconds; must be ≥ collection_date + 00:00:00

---

### 4. Pattern Detection (`pattern_detection`)

**Structure**: Object with 4 pattern category keys, each containing 3 subfields

```json
{
  "pattern_detection": {
    "startup": {
      "count": 0,
      "timestamps": [],
      "samples": []
    },
    "oom_kill": {
      "count": 0,
      "timestamps": [],
      "samples": []
    },
    "error": {
      "count": 42,
      "timestamps": ["1785277704", "unknown"],
      "samples": ["Error: connection refused"]
    },
    "performance": {
      "count": 0,
      "timestamps": [],
      "samples": []
    }
  }
}
```

#### Pattern Category Schema

For each of the 4 pattern categories (`startup`, `oom_kill`, `error`, `performance`):

| Subfield | Type | Required | Nullable | Format/Constraints | Example |
|----------|------|----------|----------|---------------------|---------|
| `count` | `integer` | Yes | No | ≥ 0 | `42` |
| `timestamps` | `array[string]` | Yes | No | Each element: Unix epoch or `"unknown"` | `["1785277704", "unknown"]` |
| `samples` | `array[string]` | Yes | No | Each element: Non-empty string | `["Error: connection refused"]` |

**Validation Rules:**
- `count`: Must be non-negative integer
- `timestamps`: Must be array; all elements must be strings; valid values are Unix epoch integers (as strings) or `"unknown"`; array length must equal `count`
- `samples`: Must be array; all elements must be non-empty strings; array length must equal `count`
- Consistency: `count` === `timestamps.length` === `samples.length`
- Special case: If `count === 0`, arrays must be empty (`[]`)

**Pattern Categories (enumerated):**
1. `startup` - Application startup events
2. `oom_kill` - Out of memory kills
3. `error` - Error messages
4. `performance` - Performance issues

---

### 5. Temporal Boundaries (`temporal_boundaries`)

| Field | Type | Required | Nullable | Format/Constraints | Source | Example |
|-------|------|----------|----------|---------------------|--------|---------|
| `first_log_entry` | `string` | Yes | Yes | ISO 8601 UTC (Z suffix) or null | Analysis JSON | `"2026-07-28T17:26:15Z"` or `null` |
| `last_log_entry` | `string` | Yes | Yes | ISO 8601 UTC (Z suffix) or null | Analysis JSON | `"2026-08-06T12:30:45Z"` or `null` |
| `analysis_date` | `string` | Yes | Yes | ISO 8601 datetime with microseconds, or null | Analysis JSON | `"2026-08-06T13:40:20.792334Z"` or `null` |
| `collection_date` | `string` | Yes | No | ISO 8601 date (YYYY-MM-DD) | Filename | `"2026-08-06"` |

**Validation Rules:**
- `first_log_entry`: If non-null, must parse as valid ISO 8601 datetime with Z suffix
- `last_log_entry`: If non-null, must parse as valid ISO 8601 datetime with Z suffix; must be ≥ first_log_entry (if both non-null)
- `analysis_date`: If non-null, must parse as valid ISO 8601 datetime with optional microseconds
- `collection_date`: Must match regex `^\d{4}-\d{2}-\d{2}$`, must be valid date
- Temporal ordering: `first_log_entry` ≤ `last_log_entry` < `analysis_date` (when all non-null)
- Collection constraint: `collection_date` ≤ `analysis_date` (when both non-null)

**Note**: `analysis_date` appears in both `analysis_metadata` and `temporal_boundaries` for convenience and cross-referencing.

---

## Complete JSONL Schema Example

```json
{
  "pod_identification": {
    "pod_name": "pbx-web-5ff68464d-mkn8n",
    "namespace": "pbx-web",
    "pod_phase": "Running",
    "restart_count": 0,
    "creation_timestamp": "2026-07-28T17:26:12Z",
    "deletion_timestamp": null,
    "container_image": "ronaldraygun/pbx-web:1.0.9",
    "node_name": "k3s-agent-minisforum"
  },
  "log_file_metadata": {
    "log_file_path": "research/pbx-web-30days/pod-logs/pod-pbx-web-5ff68464d-mkn8n-2026-08-06.log",
    "log_size_bytes": 62900,
    "log_line_count": 2762,
    "collection_date": "2026-08-06",
    "log_type": "current"
  },
  "analysis_metadata": {
    "analysis_file_path": "pod-pbx-web-5ff68464d-mkn8n-2026-08-06-analysis.json",
    "analysis_date": "2026-08-06T13:40:21.580554"
  },
  "pattern_detection": {
    "startup": {
      "count": 0,
      "timestamps": [],
      "samples": []
    },
    "oom_kill": {
      "count": 0,
      "timestamps": [],
      "samples": []
    },
    "error": {
      "count": 42,
      "timestamps": ["1785277704", "unknown"],
      "samples": ["Error: connection refused", "Fatal: cannot connect to database"]
    },
    "performance": {
      "count": 0,
      "timestamps": [],
      "samples": []
    }
  },
  "temporal_boundaries": {
    "first_log_entry": "2026-07-28T17:26:15Z",
    "last_log_entry": "2026-08-06T12:30:45Z",
    "analysis_date": "2026-08-06T13:40:20.792334Z",
    "collection_date": "2026-08-06"
  }
}
```

---

## Edge Case Handling

### 1. Missing Analysis Files
```json
{
  "analysis_metadata": {
    "analysis_file_path": null,
    "analysis_date": null
  },
  "pattern_detection": {
    "startup": {"count": 0, "timestamps": [], "samples": []},
    "oom_kill": {"count": 0, "timestamps": [], "samples": []},
    "error": {"count": 0, "timestamps": [], "samples": []},
    "performance": {"count": 0, "timestamps": [], "samples": []}
  },
  "temporal_boundaries": {
    "first_log_entry": null,
    "last_log_entry": null,
    "analysis_date": null,
    "collection_date": "2026-08-06"
  }
}
```

### 2. Empty Log Files
```json
{
  "log_file_metadata": {
    "log_size_bytes": 0,
    "log_line_count": 0
  },
  "temporal_boundaries": {
    "first_log_entry": null,
    "last_log_entry": null
  }
}
```

### 3. Deleted/Terminated Pods
```json
{
  "pod_identification": {
    "pod_phase": "Failed",
    "deletion_timestamp": "2026-08-06T10:00:00Z"
  }
}
```

---

## Validation Summary

### Field Count by Type
- **Strings**: 13 fields (pod_name, namespace, pod_phase, container_image, node_name, log_file_path, collection_date, log_type, analysis_file_path, analysis_date, first_log_entry, last_log_entry, collection_date)
- **Integers**: 2 fields (restart_count, log_size_bytes, log_line_count)
- **Objects**: 3 root objects (pod_identification, log_file_metadata, analysis_metadata, pattern_detection, temporal_boundaries)
- **Arrays**: 8 arrays (4 timestamp arrays + 4 sample arrays)

### Required vs Optional
- **Required fields**: 28 (all top-level keys must be present)
- **Nullable fields**: 8 (pod_phase, deletion_timestamp, container_image, node_name, log_line_count, log_type, analysis_file_path, analysis_date, first_log_entry, last_log_entry)
- **Non-nullable fields**: 18 (pod_name, namespace, restart_count, log_file_path, log_size_bytes, collection_date, count fields, all array objects)

### Type-Specific Constraints
- **ISO 8601 timestamps**: Must use UTC (Z suffix), except `analysis_date` allows microseconds
- **Integers**: Must be non-negative (≥ 0)
- **Arrays**: Must have consistent lengths with corresponding count fields
- **Strings**: Non-empty unless explicitly nullable
- **Enums**: `pod_phase` (5 values), `log_type` (4 values + null)

---

## Schema Validation Rules

### Cross-Field Constraints

1. **Temporal Ordering**
   - `first_log_entry` ≤ `last_log_entry` (when both non-null)
   - `last_log_entry` < `analysis_date` (when both non-null)
   - `collection_date` ≤ `analysis_date` (when both non-null)
   - `creation_timestamp` ≤ `deletion_timestamp` (when both non-null)

2. **Array Length Consistency**
   - For each pattern category: `count === timestamps.length === samples.length`
   - If `count === 0`, arrays must be empty (`[]`)

3. **File Path References**
   - `log_file_path` must reference existing `.log` file
   - `analysis_file_path` (if non-null) must reference existing `-analysis.json` file
   - Paths must be relative to research root directory

4. **Namespace Consistency**
   - `namespace` must match directory structure (e.g., `pbx-web-30days/pod-logs/` → namespace = `pbx-web`)

### Type Validation Rules

1. **Timestamp Formats**
   ```regex
   ISO 8601 with Z: ^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$
   ISO 8601 with microseconds: ^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z$
   Date only: ^\d{4}-\d{2}-\d{2}$
   ```

2. **Kubernetes Identifiers**
   ```regex
   DNS subdomain: ^[a-z0-9]([-a-z0-9]*[a-z0-9])?$
   ```

3. **Container Image References**
   ```regex
   ^([^/]+/)?[^:]+(:[^:]+)?$
   ```

---

## Mapping to Parent Bead Requirements

### Parent Bead: adc-4q6sr
This schema directly implements the requirements extracted from adc-4q6sr:

| adc-4q6sr Requirement | Schema Field(s) | Category |
|------------------------|-----------------|----------|
| Pod identification fields | `pod_identification.*` | Pod Identification (8 fields) |
| Log file fields | `log_file_metadata.*` | Log File Metadata (5 fields) |
| Analysis file fields | `analysis_metadata.*` | Analysis Metadata (2 fields) |
| Pattern detection fields | `pattern_detection.*` | Pattern Detection (4 categories × 3 = 12) |
| Temporal fields | `temporal_boundaries.*` | Temporal Boundaries (4 fields) |
| File naming pattern constraints | `log_file_path`, `collection_date`, `log_type` | Log File Metadata |
| Temporal ordering constraints | Cross-field validation rules | All |
| Null handling strategy | Nullable field specifications | All |
| Array constraints | `pattern_detection.*.timestamps`, `samples` | Pattern Detection |

---

## Usage Notes

### Reading the JSONL
```bash
# Read all entries
jq -c '.' pod-logs-index.jsonl | while read -r entry; do
  echo "$entry" | jq '.pod_identification.pod_name'
done

# Query by pod name
grep '"pbx-web-5ff68464d-mkn8n"' pod-logs-index.jsonl | jq .

# Find pods with errors
jq 'select(.pattern_detection.error.count > 0)' pod-logs-index.jsonl
```

### Writing the JSONL
```python
import json
from datetime import datetime

entry = {
    "pod_identification": {...},
    "log_file_metadata": {...},
    "analysis_metadata": {...},
    "pattern_detection": {...},
    "temporal_boundaries": {...}
}

with open('pod-logs-index.jsonl', 'a') as f:
    f.write(json.dumps(entry) + '\n')
```

### Validation
```python
import jsonschema

schema = {  # The schema defined in this document
    "$schema": "http://json-schema.org/draft-07/schema#",
    "type": "object",
    "required": ["pod_identification", "log_file_metadata", ...],
    "properties": {...}
}

jsonschema.validate(entry, schema)
```

---

## Dependencies

This schema definition is used by:
- **adc-1i5hf**: Document edge cases and validation scenarios
- **adc-164qp**: Write pod-logs-schema.md with examples

---

## Schema Version History
- **v1.0** (2026-08-06): Initial schema definition based on adc-4q6sr requirements extraction
