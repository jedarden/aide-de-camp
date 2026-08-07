# Sample Log Files Catalog

Generated: 2026-08-07
Project: aide-de-camp

## Overview
This catalog contains 10 representative log files from the `logs/` directory, showcasing different formats, sizes, and source clusters.

## File Catalog

| # | File Name | Size | Type | Source Cluster | Notes |
|---|-----------|------|------|----------------|-------|
| 1 | `whisper-stt-raw.jsonl` | 2.8M | JSONL | whisper-stt | Main whisper-stt logs, structured data, actively updated |
| 2 | `pbx-web-victorialogs-raw.jsonl` | 75M | JSONL | pbx-web | Large file - victorialogs data, near 100MB threshold |
| 3 | `whisper-stt-30day.jsonl` | 209K | JSONL | whisper-stt | 30-day aggregated analysis data |
| 4 | `pbx-web-parsed.jsonl` | 324K | JSONL | pbx-web | Error logs with severity levels (error_type, message, severity, source) |
| 5 | `pbx-web-nginx.log` | 94K | LOG | pbx-web | nginx access/error logs |
| 6 | `whisper-openai-raw.log` | 5.4M | LOG | whisper-stt | OpenAI service interaction logs |
| 7 | `pbx-web-site-generator.log` | 62K | LOG | pbx-web | Site generator process logs |
| 8 | `whisper-stt-deployment-describe.txt` | 7.4K | TXT | whisper-stt | Kubernetes deployment descriptions |
| 9 | `pbx-web-pods-describe.txt` | 11K | TXT | pbx-web | Kubernetes pod descriptions |
| 10 | `whisper-stt-pod-raw.log` | 0B | LOG | whisper-stt | **EMPTY FILE** - placeholder file |

## Directory Structure

### Main Clusters
- **pbx-web**: Asterisk/phone system web interface logs
  - Clusters: apexalgo-iad, ardenone-cluster
  - Subdirectories: `pbx-web-1day/`, `pbx-web-30day/`, `pbx-web-apexalgo-iad/`, `pbx-web-ardenone-cluster/`
  
- **whisper-stt**: Speech-to-text service logs
  - OpenAI integration logs
  - Deployment and pod management logs

### File Type Distribution
- **JSONL**: Structured log data (JSON objects per line)
- **LOG**: Standard log format
- **TXT**: Descriptive/output text files
- **MD**: Documentation/analysis summaries

## Size Categories
- **Large (>5MB)**: 2 files (whisper-stt-raw.jsonl, whisper-openai-raw.log)
- **Medium (100KB-5MB)**: 5 files 
- **Small (<100KB)**: 3 files
- **Empty**: 1 file

## Notable Observations
1. **Near-threshold file**: `pbx-web-victorialogs-raw.jsonl` at 75MB should be monitored to avoid exceeding 100MB
2. **Empty files**: Several empty log files serve as placeholders or have been cleaned
3. **Active files**: `whisper-stt-raw.jsonl` and `pbx-web-parsed.jsonl` show recent modification times
4. **Structured data**: JSONL files contain machine-readable structured logs with timestamps, error types, and metadata

## Subdirectory Contents
- `pbx-web-30day/`: Contains ~8MB of 30-day historical logs
- `pbx-web-apexalgo-iad/`: Cluster-specific logs from apexalgo-iad
- `pbx-web-ardenone-cluster/`: Cluster-specific logs from ardenone-cluster (1MB total)
- `pbx-web-1day/`: Recent 1-day logs

## Usage Recommendations
1. Monitor large files approaching 100MB threshold
2. Clean up empty placeholder files if not needed
3. Consider archiving older 30-day logs to separate storage
4. Use JSONL files for automated analysis (structured data)
5. Cross-reference .md files for analysis summaries and limitations