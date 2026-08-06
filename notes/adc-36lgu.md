# PBX-Web Log Fetch Script Implementation

## Summary
Created and deployed a log fetch script for pbx-web service that retrieves the last 30 days of deployment logs.

## What Was Done

### 1. Script Creation (`scripts/fetch_pbx_web_logs.py`)
- Python script that fetches logs from all pods in the `pbx-web` namespace
- Uses kubectl proxy to ardenone-cluster (read-only access)
- Retrieves logs from current pods, deployment status, and replica set history
- Implements 30-day timestamp filtering using timezone-aware datetime comparison
- Outputs to JSONL format: `data/pbx-web-logs.jsonl`

### 2. Script Features
- **Structured logging**: Each log entry includes timestamp, pod_name, namespace, log_level, message, and service
- **Time filtering**: Filters entries to last 30 days using timezone-aware comparison (fixes datetime comparison bug)
- **Comprehensive coverage**: Fetches from all pods including:
  - `lab-rebuild-relay-79957dbd4-xsqhl`
  - `pbx-rebuild-relay-588d79c5b9-vmmlz`
  - `pbx-web-5ff68464d-mkn8n`
- **Deployment metadata**: Includes deployment and replica set events

### 3. Test Results
Successfully executed and tested:
- **Total entries collected**: 46,845
- **Entries within 30-day window**: 46,830 (99.97%)
- **Output file size**: 12MB
- **Date range**: 2026-07-13 to 2026-08-06
- **Pods covered**: 3 pods

### 4. Deployment Information
- **Cluster**: `ardenone-cluster`
- **Namespace**: `pbx-web`
- **Access**: Read-only kubectl proxy at `http://traefik-ardenone-cluster:8001`

## Acceptance Criteria Met
✅ Script exists at `scripts/fetch_pbx_web_logs.py`
✅ Script uses kubectl to fetch logs from correct cluster/namespace (ardenone-cluster/pbx-web)
✅ Script includes timestamp filtering for 30-day window
✅ Script outputs to `data/pbx-web-logs.jsonl`
✅ Script tested and runs without errors

## Usage
```bash
python3 scripts/fetch_pbx_web_logs.py
```

## Output Format
JSONL with one JSON object per line:
```json
{
  "timestamp": "2026-08-06T05:36:19.704787586-04:00",
  "pod_name": "lab-rebuild-relay-79957dbd4-xsqhl",
  "namespace": "pbx-web",
  "log_level": "INFO",
  "message": "...",
  "service": "pbx-web"
}
```

## Key Implementation Details
- **Timezone handling**: Fixed datetime comparison bug by using `datetime.now().astimezone()` for timezone-aware comparison
- **Error handling**: Graceful handling of unparseable timestamps (keeps entries rather than dropping them)
- **Modular design**: Reused pattern from existing `fetch_whisper_stt_logs.py` script for consistency
- **Executable**: Script is executable (`chmod +x`)

## Files Created/Modified
- `scripts/fetch_pbx_web_logs.py` (new)
- `data/pbx-web-logs.jsonl` (generated output)
- `notes/adc-36lgu.md` (this file)
