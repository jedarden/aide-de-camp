# Pod-Logs Directory Structure Catalog

## Overview

This document catalogs the pod-logs directory structure within the aide-de-camp project. The pod-logs are organized under research subdirectories for two main applications: pbx-web and whisper-stt.

## Directory Locations

1. **pbx-web-30days**: `/home/coding/aide-de-camp/research/pbx-web-30days/pod-logs/`
2. **whisper-stt-30days**: `/home/coding/aide-de-camp/research/whisper-stt-30days/pod-logs/`

## Directory Statistics

| Directory | File Count | Total Size |
|-----------|------------|------------|
| pbx-web-30days/pod-logs | 21 files | 6.5 MB |
| whisper-stt-30days/pod-logs | 31 files | 11 MB |
| **Total** | **52 files** | **17.5 MB** |

## File Naming Patterns

### Log Files (*.log)

**Standard Pattern:** `{prefix}-{pod-name}-{date}-{suffix}.log`

**Components:**
- `prefix`: Application identifier (pod, pbx-web, whisper-stt, etc.)
- `pod-name`: Kubernetes pod name with replica set hash
- `date`: ISO date format (YYYY-MM-DD) when applicable
- `suffix`: Log stream identifier (current, previous, stderr)

**Examples:**
- `pod-pbx-web-5ff68464d-mkn8n-2026-08-06.log` - Standard pod log with date
- `pbx-web-5ff68464d-mkn8n-current.log` - Current log stream without date
- `pod-whisper-openai-68966786fb-jsb5d-2026-08-06-stderr.log` - Standard error stream
- `pbx-web-current-nginx.log` - Application-specific current log

### Analysis Files (*-analysis.json)

**Pattern:** `{log-file-name}-analysis.json`

These files contain structured JSON analysis results with:
- File metadata (path, name, analysis date)
- Pattern detection results (startup, oom_kill, error, performance)
- Timestamped samples of detected patterns
- Summary statistics

**Examples:**
- `pod-pbx-web-5ff68464d-mkn8n-2026-08-06-analysis.json`
- `pod-whisper-stt-847fd8d7b9-v2rs5-2026-08-06-current-analysis.json`

### Metadata Files

- `pods-list.jsonl` - JSON Lines format pod inventory (pbx-web only)
- `README.md` - Collection summary and context (whisper-stt only)
- `LOG_COLLECTION_SUMMARY.md` - Detailed collection reports (whisper-stt only)
- `TASK_COMPLETION_SUMMARY.md` - Task completion status (whisper-stt only)

## File Inventory

### pbx-web-30days/pod-logs (21 files)

**Pod Logs (with analysis):**
- `pod-pbx-web-5ff68464d-mkn8n-2026-08-06.log` + `*-analysis.json` (62,900 bytes)
- `pod-lab-rebuild-relay-79957dbd4-xsqhl-2026-08-06.log` + `*-analysis.json` (158,298 bytes)
- `pod-pbx-rebuild-relay-588d79c5b9-vmmlz-2026-08-06.log` + `*-analysis.json` (1,774,944 bytes)

**Application-specific Logs:**
- `pbx-web-current-nginx.log` (4,392,661 bytes)
- `pbx-web-current-site-generator.log` (162,229 bytes)
- `pbx-web-5ff68464d-mkn8n-current.log` + `*-previous.log`

**Cross-application Logs:**
- `whisper-stt-whisper-openai-68966786fb-tng29.log` + `*-analysis.json` (0 bytes)
- `whisper-stt-whisper-stt-847fd8d7b9-b8rsj.log` + `*-analysis.json` (0 bytes)

**Rebuild Relay Logs:**
- `pbx-web-lab-rebuild-relay-79d6d858bb-lpqdb.log` + `*-analysis.json` (24,500 bytes)
- `pbx-web-pbx-rebuild-relay-8596977857-4292b.log` + `*-analysis.json` (24,500 bytes)
- `pbx-web-pbx-web-5ff68464d-lcfcp.log` + `*-analysis.json` (146 bytes)

**Metadata:**
- `pods-list.jsonl` (721 bytes)

### whisper-stt-30days/pod-logs (31 files)

**whisper-openai Pod Logs:**
- `pod-whisper-openai-68966786fb-jsb5d-2026-06-14.log` + `*-analysis.json` (5,284,368 bytes)
- `pod-whisper-openai-68966786fb-jsb5d-2026-08-06.log` (99 bytes) + `*-current.log` (800 bytes) + `*-previous.log` (213 bytes) + `*-stderr.log` (29,000 bytes)
- All corresponding `*-analysis.json` files

**whisper-stt Pod Logs:**
- `pod-whisper-stt-847fd8d7b9-v2rs5-2026-07-12.log` + `*-analysis.json` (517 bytes)
- `pod-whisper-stt-847fd8d7b9-v2rs5-2026-08-06.log` (0 bytes) + `*-current.log` (0 bytes) + `*-previous.log` (124 bytes) + `*-stderr.log` (0 bytes)
- All corresponding `*-analysis.json` files

**Direct Access Logs:**
- `whisper-openai-68966786fb-jsb5d.log` (5,393,304 bytes)
- `whisper-stt-847fd8d7b9-v2rs5.log` (0 bytes)

**Documentation (5 files):**
- `README.md`
- `COLLECTION_SUMMARY.md`
- `LOG_COLLECTION_SUMMARY.md`
- `LOG_COLLECTION_SUMMARY_2026-08-06.md`
- `LOG_COVERAGE_VERIFICATION.md`
- `LOG_COLLECTION_FINAL_SUMMARY.md`
- `TASK_COMPLETION_SUMMARY.md`

## Log Stream Types

1. **stdout**: Standard output from containers (default when no suffix)
2. **stderr**: Error output (separate `-stderr.log` file when non-empty)
3. **current**: Most recent log stream (`-current.log` suffix)
4. **previous**: Previous log stream after pod restart (`-previous.log` suffix)

## Analysis File Structure

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

## Organizational Patterns

### By Application
- **pbx-web**: Primary telephony web interface
- **whisper-stt**: Speech-to-text processing service
- **whisper-openai**: OpenAI integration for speech processing

### By Container Type
- **Main application containers**: pbx-web, whisper-stt
- **Rebuild relay containers**: lab-rebuild-relay, pbx-rebuild-relay
- **Support containers**: nginx, site-generator

### By Time Period
- **30-day windows**: Both collections cover 2026-07-07 to 2026-08-06
- **Historical data**: Some files contain older data (e.g., 2026-06-14)

### By File Size
- **Empty files**: 0 bytes (common for quiet containers)
- **Small files**: <1KB (minimal logging)
- **Medium files**: 20-160 KB (typical application logs)
- **Large files**: >1 MB (high-volume logging, up to 5.3 MB)

## Data Collection Characteristics

### Coverage
- **Time window**: 30 days (2026-07-07 to 2026-08-06)
- **Pod sampling**: Current pods + historical ReplicaSets
- **Log streams**: stdout, stderr, current, previous (when available)

### Quality Notes
- Empty log files are common for containers with minimal output
- Timestamp formats vary (Unix epoch vs. ISO)
- Some log entries contain "unknown" timestamps when parsing failed
- File sizes vary widely based on application logging verbosity

## Access Patterns

### Quick Overview
Read `*-analysis.json` files for pattern summaries and statistics

### Detailed Investigation
Read corresponding `.log` files for full context and raw data

### Pod Metadata
Query `pods-list.jsonl` (pbx-web) or `README.md` (whisper-stt) for pod inventory

### Collection Context
Read summary documents (`LOG_COLLECTION_SUMMARY.md`, etc.) for collection methodology

## Conclusions

The pod-logs directory structure is well-organized with consistent naming conventions and comprehensive analysis coverage. The two main collections (pbx-web and whisper-stt) provide:
1. Complete 30-day log coverage for both applications
2. Automated pattern analysis via structured JSON files
3. Multiple log stream types (stdout, stderr, current, previous)
4. Cross-application logging (rebuild relays, support containers)
5. Comprehensive metadata and documentation

Total collection size is manageable at 17.5 MB with 52 files providing extensive logging coverage for reliability analysis and pattern detection.