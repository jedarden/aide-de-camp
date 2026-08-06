# Pod Logs JSONL Schema

## Overview

This schema defines the structure for `pod-logs-index.jsonl`, which documents all collected pod logs and their analysis. Each line in the JSONL file represents one pod log entry with complete metadata.

**Schema Version:** 1.0  
**Format:** JSON Lines (JSONL) - one JSON object per line  
**Parent Bead:** adc-1i5hf (Document edge cases and validation scenarios)  
**Total Fields:** 28 across 5 categories  

---

## Schema Structure

### Root Object

```json
{
  "pod_identification": { /* 8 fields */ },
  "log_file_metadata": { /* 5 fields */ },
  "analysis_metadata": { /* 2 fields */ },
  "pattern_detection": { /* 4 pattern categories × 3 fields = 12 */ },
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
| `analysis_date` | `string` | Yes | Yes | ISO 8601 datetime with microseconds, or null | Analysis JSON | `"2026-08-06T13:40:21.580554Z"` or `null` |

**Validation Rules:**
- `analysis_file_path`: If non-null, must be relative path, must reference `-analysis.json` file
- `analysis_date`: If non-null, must parse as valid ISO 8601 datetime with optional microseconds; must be ≥ collection_date + 00:00:00

---

### 4. Pattern Detection (`pattern_detection`)

**Structure:** Object with 4 pattern category keys, each containing 3 subfields

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
      "samples": ["Error: connection refused", "Fatal: cannot connect to database"]
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
- **Consistency:** `count === timestamps.length === samples.length`
- **Special case:** If `count === 0`, arrays must be empty (`[]`)

**Pattern Categories:**
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
- **Temporal ordering:** `first_log_entry` ≤ `last_log_entry` < `analysis_date` (when all non-null)
- **Collection constraint:** `collection_date` ≤ `analysis_date` (when both non-null)

---

## Edge Cases and Handling

### 1. Missing Analysis Files

When no analysis file exists:
- Set `analysis_file_path` to `null`
- Set `analysis_date` to `null`
- Set all pattern counts to 0 with empty `timestamps` and `samples` arrays
- Set `first_log_entry` and `last_log_entry` to `null`

### 2. Empty Log Files

When log file size is 0 bytes:
- Set `log_size_bytes` to 0
- Set `log_line_count` to 0
- Set all pattern detections to default values (count 0, empty arrays)
- Set `first_log_entry` and `last_log_entry` to `null`

### 3. Deleted/Terminated Pods

When pod has been deleted:
- Set `pod_phase` to `"Failed"`, `"Succeeded"`, or `"Unknown"`
- Set `deletion_timestamp` to ISO 8601 timestamp
- `deletion_timestamp` must be ≥ `creation_timestamp`

### 4. Missing/Invalid Timestamps

When timestamps cannot be extracted:
- Set missing timestamps to `null` (NOT empty string)
- Preserve `count` values but set corresponding arrays to empty
- ISO 8601 timestamps must use UTC (Z suffix), not `+00:00`

### 5. Array Consistency Issues

Pattern detection arrays must satisfy:
- `count === timestamps.length === samples.length`
- If `count === 0`, arrays must be empty `[]`
- Arrays with `count > 0` must have exactly `count` elements

### 6. Null vs Empty vs Omitted Fields

- **Required fields:** All 28 leaf fields must be present
- **Nullable fields:** 10 fields may be `null` when data is unavailable
- **Empty arrays:** MUST be `[]`, not `null` or omitted
- **Zero values:** Allowed for numeric fields (`restart_count`, `log_size_bytes`, all pattern counts)

### 7. Unicode and Special Characters

- All strings must be valid UTF-8
- Unicode escapes (`\\uXXXX`) are allowed
- Control characters must be properly escaped
- Emoji and multi-byte characters preserved as-is
- RTL text (Arabic, Hebrew) preserved as-is

### 8. Cross-Field Constraint Violations

Temporal ordering must be preserved:
- `first_log_entry` ≤ `last_log_entry` (when both non-null)
- `last_log_entry` < `analysis_date` (when both non-null)
- `collection_date` ≤ `analysis_date` (when both non-null)
- `creation_timestamp` ≤ `deletion_timestamp` (when both non-null)

---

## Example JSONL Entries

### Example 1: Complete Entry with All Data

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
    "analysis_date": "2026-08-06T13:40:21.580554Z"
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
      "timestamps": ["1785277704", "1785277800"],
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

### Example 2: Entry with Missing Analysis File

```json
{
  "pod_identification": {
    "pod_name": "whisper-stt-847fd8d7b9-v2rs5",
    "namespace": "production",
    "pod_phase": "Running",
    "restart_count": 0,
    "creation_timestamp": "2026-08-01T10:30:00Z",
    "deletion_timestamp": null,
    "container_image": "ronaldraygun/whisper-stt:latest",
    "node_name": "k3s-agent-1"
  },
  "log_file_metadata": {
    "log_file_path": "research/whisper-stt-30days/pod-logs/pod-whisper-stt-847fd8d7b9-v2rs5-2026-08-06.log",
    "log_size_bytes": 1024,
    "log_line_count": null,
    "collection_date": "2026-08-06",
    "log_type": "current"
  },
  "analysis_metadata": {
    "analysis_file_path": null,
    "analysis_date": null
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
      "count": 0,
      "timestamps": [],
      "samples": []
    },
    "performance": {
      "count": 0,
      "timestamps": [],
      "samples": []
    }
  },
  "temporal_boundaries": {
    "first_log_entry": null,
    "last_log_entry": null,
    "analysis_date": null,
    "collection_date": "2026-08-06"
  }
}
```

### Example 3: Entry with Empty Log File

```json
{
  "pod_identification": {
    "pod_name": "lab-rebuild-relay-79957dbd4-xsqhl",
    "namespace": "default",
    "pod_phase": "Running",
    "restart_count": 0,
    "creation_timestamp": "2026-07-27T17:56:07Z",
    "deletion_timestamp": null,
    "container_image": "ronaldraygun/lab-rebuild-relay:1.0.0",
    "node_name": "k3s-agent-minisforum"
  },
  "log_file_metadata": {
    "log_file_path": "research/pbx-web-30days/pod-logs/pod-lab-rebuild-relay-79957dbd4-xsqhl-2026-08-06.log",
    "log_size_bytes": 0,
    "log_line_count": 0,
    "collection_date": "2026-08-06",
    "log_type": "current"
  },
  "analysis_metadata": {
    "analysis_file_path": "pod-lab-rebuild-relay-79957dbd4-xsqhl-2026-08-06-analysis.json",
    "analysis_date": "2026-08-06T13:40:21.100000Z"
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
      "count": 0,
      "timestamps": [],
      "samples": []
    },
    "performance": {
      "count": 0,
      "timestamps": [],
      "samples": []
    }
  },
  "temporal_boundaries": {
    "first_log_entry": null,
    "last_log_entry": null,
    "analysis_date": "2026-08-06T13:40:21.100000Z",
    "collection_date": "2026-08-06"
  }
}
```

### Example 4: Entry with Previous Log Stream (Pod Restart)

```json
{
  "pod_identification": {
    "pod_name": "whisper-stt-847fd8d7b9-v2rs5",
    "namespace": "production",
    "pod_phase": "Failed",
    "restart_count": 3,
    "creation_timestamp": "2026-07-25T08:00:00Z",
    "deletion_timestamp": "2026-08-06T12:00:00Z",
    "container_image": "ronaldraygun/whisper-stt:latest",
    "node_name": "k3s-agent-1"
  },
  "log_file_metadata": {
    "log_file_path": "research/whisper-stt-30days/pod-logs/pod-whisper-stt-847fd8d7b9-v2rs5-2026-08-06-previous.log",
    "log_size_bytes": 1500,
    "log_line_count": 45,
    "collection_date": "2026-08-06",
    "log_type": "previous"
  },
  "analysis_metadata": {
    "analysis_file_path": "pod-whisper-stt-847fd8d7b9-v2rs5-2026-08-06-previous-analysis.json",
    "analysis_date": "2026-08-06T13:40:23.600509Z"
  },
  "pattern_detection": {
    "startup": {
      "count": 1,
      "timestamps": ["1754768405"],
      "samples": ["Starting application..."]
    },
    "oom_kill": {
      "count": 1,
      "timestamps": ["1754772100"],
      "samples": ["Kill process due to OOM"]
    },
    "error": {
      "count": 0,
      "timestamps": [],
      "samples": []
    },
    "performance": {
      "count": 0,
      "timestamps": [],
      "samples": []
    }
  },
  "temporal_boundaries": {
    "first_log_entry": "2026-07-25T08:00:05Z",
    "last_log_entry": "2026-07-28T14:30:00Z",
    "analysis_date": "2026-08-06T13:40:23.600509Z",
    "collection_date": "2026-08-06"
  }
}
```

### Example 5: Entry with Unicode Characters in Error Messages

```json
{
  "pod_identification": {
    "pod_name": "pbx-web-5ff68464d-intl",
    "namespace": "pbx-web",
    "pod_phase": "Running",
    "restart_count": 0,
    "creation_timestamp": "2026-08-06T10:00:00Z",
    "deletion_timestamp": null,
    "container_image": "ronaldraygun/pbx-web:1.0.9",
    "node_name": "k3s-agent-minisforum"
  },
  "log_file_metadata": {
    "log_file_path": "research/pbx-web-30days/pod-logs/pod-pbx-web-5ff68464d-intl-2026-08-06.log",
    "log_size_bytes": 2500,
    "log_line_count": 110,
    "collection_date": "2026-08-06",
    "log_type": "current"
  },
  "analysis_metadata": {
    "analysis_file_path": "pod-pbx-web-5ff68464d-intl-2026-08-06-analysis.json",
    "analysis_date": "2026-08-06T13:40:25Z"
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
      "count": 3,
      "timestamps": ["1785277704", "1785277800", "1785277900"],
      "samples": ["Error: ❌ Connection failed 🔴", "错误：数据库连接失败", "خطأ: فشل الاتصال بقاعدة البيانات"]
    },
    "performance": {
      "count": 0,
      "timestamps": [],
      "samples": []
    }
  },
  "temporal_boundaries": {
    "first_log_entry": "2026-08-06T10:00:15Z",
    "last_log_entry": "2026-08-06T13:40:20Z",
    "analysis_date": "2026-08-06T13:40:25Z",
    "collection_date": "2026-08-06"
  }
}
```

### Example 6: Entry with "unknown" Timestamps

```json
{
  "pod_identification": {
    "pod_name": "whisper-openai-68966786fb-jsb5d",
    "namespace": "whisper-stt",
    "pod_phase": "Running",
    "restart_count": 1,
    "creation_timestamp": "2026-08-05T15:00:00Z",
    "deletion_timestamp": null,
    "container_image": "ronaldraygun/whisper-openai:latest",
    "node_name": "k3s-agent-2"
  },
  "log_file_metadata": {
    "log_file_path": "research/whisper-stt-30days/pod-logs/pod-whisper-openai-68966786fb-jsb5d-2026-08-06-stderr.log",
    "log_size_bytes": 3200,
    "log_line_count": 85,
    "collection_date": "2026-08-06",
    "log_type": "stderr"
  },
  "analysis_metadata": {
    "analysis_file_path": "pod-whisper-openai-68966786fb-jsb5d-2026-08-06-stderr-analysis.json",
    "analysis_date": "2026-08-06T13:40:30.250000Z"
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
      "count": 5,
      "timestamps": ["unknown", "unknown", "1785277704", "unknown", "1785277900"],
      "samples": ["Unparseable timestamp line", "Another bad timestamp", "Error with valid timestamp", "More unparseable data", "Final error"]
    },
    "performance": {
      "count": 2,
      "timestamps": ["1785277800", "1785277850"],
      "samples": ["Slow request: 5.2s", "Query timeout"]
    }
  },
  "temporal_boundaries": {
    "first_log_entry": "2026-08-05T15:00:10Z",
    "last_log_entry": "2026-08-06T12:30:00Z",
    "analysis_date": "2026-08-06T13:40:30.250000Z",
    "collection_date": "2026-08-06"
  }
}
```

### Example 7: Entry with Multiple Pattern Types

```json
{
  "pod_identification": {
    "pod_name": "pbx-web-5ff68464d-multi",
    "namespace": "pbx-web",
    "pod_phase": "Running",
    "restart_count": 2,
    "creation_timestamp": "2026-07-30T08:00:00Z",
    "deletion_timestamp": null,
    "container_image": "ronaldraygun/pbx-web:1.0.9",
    "node_name": "k3s-agent-minisforum"
  },
  "log_file_metadata": {
    "log_file_path": "research/pbx-web-30days/pod-logs/pod-pbx-web-5ff68464d-multi-2026-08-06.log",
    "log_size_bytes": 125000,
    "log_line_count": 5234,
    "collection_date": "2026-08-06",
    "log_type": "current"
  },
  "analysis_metadata": {
    "analysis_file_path": "pod-pbx-web-5ff68464d-multi-2026-08-06-analysis.json",
    "analysis_date": "2026-08-06T13:40:35.800000Z"
  },
  "pattern_detection": {
    "startup": {
      "count": 4,
      "timestamps": ["1754768400", "1754772000", "1754775600", "1754779200"],
      "samples": ["Application started", "Application started", "Application started", "Application started"]
    },
    "oom_kill": {
      "count": 3,
      "timestamps": ["1754772100", "1754775800", "1754779500"],
      "samples": ["Killed process", "Killed process", "Killed process"]
    },
    "error": {
      "count": 42,
      "timestamps": ["1754777704", "1754777800", "1754777900"],
      "samples": ["Error: connection refused", "Fatal: cannot connect to database", "Panic: runtime error"]
    },
    "performance": {
      "count": 8,
      "timestamps": ["1754778000", "1754778100"],
      "samples": ["Slow query: 5.2s", "Request timeout"]
    }
  },
  "temporal_boundaries": {
    "first_log_entry": "2026-07-30T08:00:15Z",
    "last_log_entry": "2026-08-06T13:40:30Z",
    "analysis_date": "2026-08-06T13:40:35.800000Z",
    "collection_date": "2026-08-06"
  }
}
```

### Example 8: Minimal Entry (Terminated Pod, No Analysis)

```json
{
  "pod_identification": {
    "pod_name": "old-pod-deleted-abc123",
    "namespace": "default",
    "pod_phase": "Succeeded",
    "restart_count": 0,
    "creation_timestamp": "2026-07-01T00:00:00Z",
    "deletion_timestamp": "2026-07-15T00:00:00Z",
    "container_image": null,
    "node_name": null
  },
  "log_file_metadata": {
    "log_file_path": "research/default-30days/pod-logs/pod-old-pod-deleted-abc123-2026-08-06.log",
    "log_size_bytes": 100,
    "log_line_count": null,
    "collection_date": "2026-08-06",
    "log_type": null
  },
  "analysis_metadata": {
    "analysis_file_path": null,
    "analysis_date": null
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
      "count": 0,
      "timestamps": [],
      "samples": []
    },
    "performance": {
      "count": 0,
      "timestamps": [],
      "samples": []
    }
  },
  "temporal_boundaries": {
    "first_log_entry": null,
    "last_log_entry": null,
    "analysis_date": null,
    "collection_date": "2026-08-06"
  }
}
```

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

This schema satisfies the requirements specified in parent bead **adc-1i5hf** (Document edge cases and validation scenarios):

| Parent Requirement | Schema Implementation | Section |
|-------------------|---------------------|---------|
| Edge case documentation | All edge cases documented with validation rules | Edge Cases section |
| Null handling strategy | 10 nullable fields explicitly defined | Field Definitions |
| Array consistency | `count === array.length` validation rule | Pattern Detection |
| Temporal ordering | Cross-field timestamp constraints | Validation Rules |
| Missing analysis files | Default pattern values + null metadata | Edge Case #1 |
| Empty log files | Zero bytes + null timestamps | Edge Case #2 |
| Unicode support | UTF-8 validation + emoji examples | Edge Case #7 |
| Cross-field constraints | Temporal ordering violations | Edge Case #10 |

---

## File Organization

The index expects a consistent directory structure:

```
research/
├── <service>-30days/
│   └── pod-logs/
│       ├── pod-<name>-<date>.log
│       ├── pod-<name>-<date>-analysis.json
│       └── pod-logs-index.jsonl
```

---

## Usage Notes

### Scanner Script Integration

The schema is designed to work with `scripts/scan-pod-logs.py`:
1. Scan pod-logs/ directory for .log and -analysis.json pairs
2. Extract metadata from filenames and file contents
3. Read analysis JSON for pattern detection results
4. Compute file sizes and validate paths
5. Output one JSON line per log entry following this schema

### Query Patterns

Common query patterns this schema supports:
- Find all logs with specific pattern: `jq 'select(.pattern_detection.error.count > 0)'`
- List logs by size: `jq 'sort_by(.log_file_metadata.log_size_bytes) | reverse'`
- Filter by namespace: `jq 'select(.pod_identification.namespace == "production")'`
- Time range queries: `jq 'select(.temporal_boundaries.first_log_entry >= "2026-07-01")'`
- Missing analysis detection: `jq 'select(.analysis_metadata.analysis_file_path == null)'`

---

## Version History

- **v1.0** (2026-08-06): Initial schema definition based on pod-logs structure analysis and parent bead adc-1i5hf requirements. Includes 28 fields across 5 categories, comprehensive edge case handling, and 8 example JSONL entries.