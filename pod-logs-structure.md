# Pod Logs Directory Structure

## Overview

The pod-logs directories contain Kubernetes pod logs and associated analysis files collected from various deployments. There are two main pod-logs directories in the research workspace:

- `/home/coding/aide-de-camp/research/pbx-web-30days/pod-logs` (21 files)
- `/home/coding/aide-de-camp/research/whisper-stt-30days/pod-logs` (27 files)

## Directory Layout

```
pod-logs/
├── Log files (*.log)
├── Analysis files (*-analysis.json)
├── Metadata files (pods-list.jsonl, README.md, etc.)
└── Summary documents (*.md)
```

## File Naming Patterns

### Log Files

**Pattern:** `{prefix}-{pod-name}-{date}-{suffix}.log`

**Components:**
- `prefix`: Application identifier or "pod"
- `pod-name`: Kubernetes pod name (includes replica set hash)
- `date`: ISO date format (YYYY-MM-DD)
- `suffix`: Optional log stream identifier (current, previous, stderr)

**Examples:**
- `pod-pbx-web-5ff68464d-mkn8n-2026-08-06.log` - Standard pod log
- `pod-whisper-openai-68966786fb-jsb5d-2026-08-06-current.log` - Current log stream
- `pod-whisper-openai-68966786fb-jsb5d-2026-08-06-previous.log` - Previous log stream (pod restart)
- `pod-whisper-openai-68966786fb-jsb5d-2026-08-06-stderr.log` - Standard error stream
- `pbx-web-current-nginx.log` - Current application-specific log

### Analysis Files

**Pattern:** `{prefix}-{pod-name}-{date}-{suffix}-analysis.json`

**Components:** Same as log files, with `-analysis.json` extension

**Examples:**
- `pod-pbx-web-5ff68464d-mkn8n-2026-08-06-analysis.json`
- `pod-whisper-stt-847fd8d7b9-v2rs5-2026-08-06-current-analysis.json`
- `pbx-web-pbx-rebuild-relay-8596977857-4292b-analysis.json`

### Metadata Files

- `pods-list.jsonl` - JSON Lines format with pod inventory
- `README.md` - Collection summary and context
- `LOG_COLLECTION_SUMMARY.md` - Detailed collection report
- `COLLECTION_SUMMARY.md` - Collection overview
- `TASK_COMPLETION_SUMMARY.md` - Task completion status

## Available Metadata

### From Filenames Only

- **Pod Name**: e.g., `pbx-web-5ff68464d-mkn8n`
  - Base application: `pbx-web`
  - Replica set hash: `5ff68464d`
  - Pod identifier: `mkn8n`
- **Date**: Collection date (YYYY-MM-DD format)
- **Log Type**: current, previous, stderr (when specified)
- **Source Application**: Prefix indicates source (pbx-web, whisper-stt, etc.)
- **File Type**: .log (raw logs), .json (analysis results)

### From File Contents

**Log Files (.log):**
- Raw stdout/stderr output from containers
- Application-specific logging
- Error messages and stack traces
- Performance metrics
- Health check results

**Analysis Files (*-analysis.json):**
```json
{
  "file": "/path/to/log/file",
  "file_name": "original-filename.log",
  "analysis_date": "ISO-timestamp",
  "total_lines": "number of lines analyzed",
  "patterns": {
    "startup": {"count": N, "timestamps": [], "samples": []},
    "oom_kill": {"count": N, "timestamps": [], "samples": []},
    "error": {"count": N, "timestamps": [], "samples": []},
    "performance": {"count": N, "timestamps": [], "samples": []}
  },
  "summary": [
    {"category": "error", "count": N, "first_occurrence": "timestamp", "last_occurrence": "timestamp"}
  ]
}
```

**Metadata Files (pods-list.jsonl):**
```json
{
  "name": "pod-name",
  "created": "ISO-timestamp",
  "started": "ISO-timestamp",
  "phase": "Running|Pending|Succeeded|Failed|Unknown",
  "restarts": "integer",
  "image": "container-image-reference",
  "nodeName": "kubernetes-node-name"
}
```

## Data Collection Strategy

### Time Coverage
- **pbx-web-30days**: 30-day collection window (2026-07-07 to 2026-08-06)
- **whisper-stt-30days**: 30-day collection window (2026-07-07 to 2026-08-06)

### Pod Sampling
- All current pods are collected
- Historical ReplicaSets identified but logs may not be available for deleted pods
- Previous logs collected when pods have restart history

### Log Streams
- **stdout**: Primary application output
- **stderr**: Error output (separate file when non-empty)
- **current**: Most recent log stream
- **previous**: Log from previous pod incarnation (after restart)

## File Size Characteristics

Typical file sizes observed:
- Small analysis files: ~600-2000 bytes
- Small log files: ~100-500 bytes (often empty or minimal output)
- Medium log files: ~20-160 KB (typical application logs)
- Large log files: ~1.7-5.3 MB (high-volume logging)

## Access Patterns

### For Research/Analysis
1. **Quick Overview**: Read analysis JSON files for pattern summaries
2. **Detailed Investigation**: Read corresponding log files for full context
3. **Pod Metadata**: Query pods-list.jsonl for pod inventory
4. **Collection Context**: Read README.md and summary documents

### For Data Processing
- **Batch Processing**: Iterate through `*-analysis.json` files for pattern aggregation
- **Log Mining**: Process `.log` files for detailed analysis
- **Metadata Join**: Use pods-list.jsonl to correlate logs with pod attributes

## Notes

- Log files use standard Kubernetes log output format
- Analysis files are generated programmatically and contain structured pattern detection results
- Empty log files are common (pods with no stdout/stderr output)
- Timestamp formats vary between Unix epoch and ISO formats
- Some log entries contain "unknown" timestamps when parsing failed
- File sizes vary widely based on application logging verbosity
