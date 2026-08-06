# Pod-Logs Structure Requirements Summary

## Task Overview
Extracted and analyzed all pod-logs structure requirements from parent bead adc-2zjyp and existing documentation to support downstream schema definition work (adc-663bz, adc-1i5hf, adc-164qp).

## Parent Bead Requirements (adc-2zjyp)

### Core Deliverables
- [x] List all files in pod-logs/ directory
- [x] Document file naming pattern for pod logs
- [x] Document file naming pattern for analysis files
- [x] Identify metadata availability (filename-derived vs file-content-derived)
- [x] Create pod-logs-structure.md summary document

## Required Fields Analysis

### 1. Pod Identification Fields

| Field | Source | Type | Example | Notes |
|-------|--------|------|---------|-------|
| `pod_name` | Filename + metadata | string | `pbx-web-5ff68464d-mkn8n` | Includes replica set hash |
| `namespace` | Directory structure | string | `pbx-web`, `whisper-stt` | Inferred from research directory |
| `pod_phase` | pods-list.jsonl | string | `Running`, `Pending`, `Failed` | Kubernetes pod phase |
| `restart_count` | pods-list.jsonl | integer | `0`, `1`, `3` | Pod restart counter |
| `creation_timestamp` | pods-list.jsonl | ISO 8601 | `2026-07-28T17:26:12Z` | Pod creation time |
| `deletion_timestamp` | pods-list.jsonl | ISO 8601 or null | `null` | Null if still running |
| `container_image` | pods-list.jsonl | string | `ronaldraygun/pbx-web:1.0.9` | Container image reference |
| `node_name` | pods-list.jsonl | string | `k3s-agent-minisforum` | Kubernetes node name |

### 2. Log File Fields

| Field | Source | Type | Example | Notes |
|-------|--------|------|---------|-------|
| `log_file_path` | Directory scan | string (relative path) | `research/pbx-web-30days/pod-logs/pod-pbx-web-5ff68464d-mkn8n-2026-08-06.log` | Relative to research root |
| `log_size_bytes` | File system | integer | `62900`, `4392661` | File size in bytes |
| `log_line_count` | Analysis file | integer | `2762` | Total lines analyzed |
| `collection_date` | Filename | ISO 8601 | `2026-08-06` | From log filename |
| `log_type` | Filename | string | `current`, `previous`, `stderr` | Log stream identifier |

### 3. Analysis File Fields

| Field | Source | Type | Example | Notes |
|-------|--------|------|---------|-------|
| `analysis_file_path` | Directory scan | string or null | `pod-pbx-web-5ff68464d-mkn8n-2026-08-06-analysis.json` | Null if missing |
| `analysis_date` | Analysis JSON | ISO 8601 | `2026-08-06T13:40:21.580554` | When analysis was run |

### 4. Pattern Detection Fields

Pattern categories from analysis files:
```json
{
  "startup": {"count": 0, "timestamps": [], "samples": []},
  "oom_kill": {"count": 0, "timestamps": [], "samples": []},
  "error": {"count": 42, "timestamps": ["1785277704", "unknown"], "samples": ["..."]},
  "performance": {"count": 0, "timestamps": [], "samples": []}
}
```

| Pattern | Count Field | Timestamps Array | Samples Array | Description |
|---------|-------------|------------------|---------------|-------------|
| `startup` | integer | string[] | string[] | Application startup events |
| `oom_kill` | integer | string[] | string[] | Out of memory kills |
| `error` | integer | string[] | string[] | Error messages |
| `performance` | integer | string[] | string[] | Performance issues |

### 5. Temporal Fields

From key_timestamps object:
```json
{
  "first_log_entry": "2026-07-28T17:26:15Z",
  "last_log_entry": "2026-08-06T12:30:45Z",
  "analysis_date": "2026-08-06T13:40:20.792334Z",
  "collection_date": "2026-08-06T00:00:00Z"
}
```

| Field | Type | Nullable | Description |
|-------|------|----------|-------------|
| `first_log_entry` | ISO 8601 | Yes | Earliest timestamp in log |
| `last_log_entry` | ISO 8601 | Yes | Latest timestamp in log |
| `analysis_date` | ISO 8601 | Yes | When analysis was performed |
| `collection_date` | ISO 8601 | No | Date log was collected |

## File Naming Patterns

### Log Files
**Pattern:** `{prefix}-{pod-name}-{date}-{suffix}.log`

**Components:**
- `prefix`: Application identifier (`pod`, `pbx-web`, `whisper-stt`)
- `pod-name`: Kubernetes pod name with replica set hash
- `date`: ISO date (YYYY-MM-DD)
- `suffix`: Optional stream identifier (`current`, `previous`, `stderr`)

**Examples:**
- `pod-pbx-web-5ff68464d-mkn8n-2026-08-06.log`
- `pod-whisper-openai-68966786fb-jsb5d-2026-08-06-current.log`
- `pbx-web-current-nginx.log`

### Analysis Files
**Pattern:** `{prefix}-{pod-name}-{date}-{suffix}-analysis.json`

**Examples:**
- `pod-pbx-web-5ff68464d-mkn8n-2026-08-06-analysis.json`
- `pod-whisper-stt-847fd8d7b9-v2rs5-2026-08-06-current-analysis.json`

### Metadata Files
- `pods-list.jsonl` - Pod inventory in JSON Lines format
- `README.md` - Collection context
- `*-SUMMARY.md` - Various collection summaries

## Directory Structure

```
research/
├── <service>-30days/
│   ├── README.md
│   ├── SUMMARY.md
│   ├── pod-logs/
│   │   ├── pod-<name>-<date>.log
│   │   ├── pod-<name>-<date>-analysis.json
│   │   ├── pods-list.jsonl
│   │   └── various-summary-docs.md
│   ├── argo-runs/
│   ├── k8s-events/
│   └── queries/
```

## Data Sources and Relationships

### Primary Data Sources
1. **Filenames** → pod_name, date, log_type, namespace (inferred)
2. **File system** → log_size_bytes, file existence
3. **pods-list.jsonl** → pod metadata, timestamps, phases
4. **Analysis JSON files** → pattern counts, samples, analysis metadata
5. **Log file contents** → raw timestamps, messages

### Field Derivation Chain
```
filename → pod_name, date, log_type
          ↓
pods-list.jsonl → creation_timestamp, deletion_timestamp, restart_count, pod_phase
                 ↓
analysis JSON → pattern counts, timestamps, samples
              ↓
file system → log_size_bytes, log_line_count
```

## Constraints and Validation Rules

### Temporal Constraints
- `first_log_entry` ≤ `last_log_entry` (when both non-null)
- `collection_date` ≥ `analysis_date` (when both non-null)
- Pattern timestamps must be within log entry range

### Type Constraints
- All integers must be non-negative
- ISO 8601 timestamps must use UTC (Z suffix)
- File paths must be relative to research root
- Arrays must be valid JSON structures

### Null Handling
- `deletion_timestamp` → null when pod still running
- `analysis_file_path` → null when no analysis exists
- `first_log_entry`/`last_log_entry` → null when log empty or timestamps unparsable
- `analysis_date` → null when analysis file missing
- Pattern arrays → empty when count = 0

### Array Constraints
- `detected_patterns` → array of pattern types with count > 0
- Pattern `timestamps` → array of timestamp strings (may contain "unknown")
- Pattern `samples` → array of sample log lines

## Edge Cases Identified

### 1. Missing Analysis Files
- Set `analysis_file_path` to `null`
- Set all pattern counts to 0 with empty arrays
- Set `analysis_date` to `null`

### 2. Empty Log Files
- Set `log_size_bytes` to actual size (may be 0)
- Set `log_line_count` to actual count
- Set temporal fields to `null`

### 3. Unparseable Timestamps
- Set timestamp fields to `null`
- Preserve pattern counts but leave arrays empty
- Use "unknown" string in some timestamp arrays

### 4. Namespace Inference
- Infer from parent directory structure
- Default to "default" if cannot determine
- Document inference method

### 5. Multiple Log Streams
- Handle `current`, `previous`, `stderr` suffixes
- Each stream gets separate index entry
- Link same pod metadata to all streams

## Schema Dependencies

This requirements analysis blocks:
- **adc-663bz**: Define JSONL schema field types and structure
- **adc-1i5hf**: Document edge cases and validation scenarios  
- **adc-164qp**: Write pod-logs-schema.md with examples

## Implementation Notes

### Collection Strategy
- 30-day collection window (2026-07-07 to 2026-08-06)
- Two primary collections: pbx-web-30days, whisper-stt-30days
- Current pods + historical ReplicaSets (when available)
- Previous logs collected when pods have restart history

### File Size Characteristics
- Analysis files: ~600-2000 bytes
- Small logs: ~100-500 bytes (often empty/minimal)
- Medium logs: ~20-160 KB (typical)
- Large logs: ~1.7-5.3 MB (high-volume)

### Access Patterns
- **Quick Overview**: Read analysis JSON files
- **Detailed Investigation**: Read corresponding log files
- **Pod Metadata**: Query pods-list.jsonl
- **Batch Processing**: Iterate through *-analysis.json files

## Summary

**Total Required Fields**: 28 fields across 5 categories

**Field Categories:**
1. Pod Identification (8 fields)
2. Log File Metadata (5 fields)
3. Analysis File Metadata (2 fields)
4. Pattern Detection (4 pattern categories × 3 subfields = 12)
5. Temporal Boundaries (4 fields)

**Key Constraints:**
- All top-level fields required (null allowed where specified)
- Strict temporal ordering requirements
- Type-specific validation rules
- Edge case handling for missing data

**Data Quality Notes:**
- Timestamps vary between Unix epoch and ISO formats
- Some log entries contain "unknown" timestamps
- Empty log files are common
- File sizes vary widely based on logging verbosity

This requirements summary provides the foundation for schema definition (adc-663bz) and subsequent documentation work.
