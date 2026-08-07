# Whisper-STT Log Retrieval Command Documentation

**Task:** adc-q2q4h  
**Completion Date:** 2026-08-06  
**Status:** ✅ **COMPLETE AND VALIDATED**

---

## Summary

Successfully tested and validated the command to retrieve whisper-stt logs from the `whisper-openai` pod in the `whisper-stt` namespace on `ardenone-cluster`. The retrieval command is fully functional, supports multiple filtering options, and output can be reliably converted to JSONL format.

---

## Working Retrieval Commands

### 1. Basic Log Retrieval (Latest 100 Lines)

```bash
kubectl --server=http://traefik-ardenone-cluster:8001 logs \
  whisper-openai-68966786fb-jsb5d -n whisper-stt --tail=100
```

**Output:** Plain text FastAPI access logs (INFO level)

**Sample Output:**
```
INFO:     10.42.2.1:41250 - "GET /health HTTP/1.1" 200 OK
INFO:     10.42.2.1:57490 - "GET /health HTTP/1.1" 200 OK
INFO:     10.42.2.1:40808 - "GET /health HTTP/1.1" 200 OK
```

### 2. Time-Based Retrieval (Last 1 Hour)

```bash
kubectl --server=http://traefik-ardenone-cluster:8001 logs \
  whisper-openai-68966786fb-jsb5d -n whisper-stt --since=1h
```

**Output:** 481 log entries from the last hour (as of test time)

**Supported Time Formats:**
- `--since=1h` - Last 1 hour
- `--since=30m` - Last 30 minutes  
- `--since=24h` - Last 24 hours
- `--since-time=2026-08-06T00:00:00Z` - Since specific timestamp

### 3. Full Log Retrieval (All Available Logs)

```bash
kubectl --server=http://traefik-ardenone-cluster:8001 logs \
  whisper-openai-68966786fb-jsb5d -n whisper-stt
```

**Output:** 96,086 log lines (53 days of history as of 2026-08-06)

**Note:** This retrieves the entire log stream from the pod's start date (2026-06-14).

---

## Log Source Details

### Target Pod
- **Name:** `whisper-openai-68966786fb-jsb5d`
- **Namespace:** `whisper-stt`
- **Cluster:** `ardenone-cluster`
- **Container:** `whisper-openai` (defaulted from 2 containers)
- **Age:** 53 days (started 2026-06-14)
- **Image:** `fedirz/faster-whisper-server:latest-cpu`
- **Log Coverage:** 53 days total, 30 days for analysis window

### Alternative Pod (Not Recommended)
- **Name:** `whisper-stt-847fd8d7b9-v2rs5`
- **Status:** Running but produces NO stdout/stderr logs
- **Issue:** Worker process logs to internal storage, not container stdout
- **Coverage:** 0 days (log retrieval returns empty)

---

## Output Format Validation

### Plain Text Format (Default)

**Characteristics:**
- Line-oriented plain text
- FastAPI/Uvicorn INFO format
- HTTP access log style

**Sample Lines:**
```
INFO:     10.42.2.1:56188 - "GET /health HTTP/1.1" 200 OK
INFO:     10.42.2.1:49190 - "GET /health HTTP/1.1" 200 OK
INFO:     10.42.2.1:51996 - "GET /health HTTP/1.1" 200 OK
```

**Format Structure:**
`INFO: <IP>:<PORT> - "<METHOD> <PATH> <PROTOCOL>" <STATUS_CODE> <STATUS_TEXT>`

### JSONL-Convertible Format

**Conversion Test Results:** ✅ **SUCCESSFUL**

**Validated JSONL Schema:**
```json
{
  "timestamp": "2026-08-06T23:38:53Z",
  "pod_name": "whisper-openai-68966786fb-jsb5d",
  "namespace": "whisper-stt",
  "cluster": "ardenone-cluster",
  "container": "whisper-openai",
  "log_line": "INFO:     10.42.2.1:59306 - \"GET /health HTTP/1.1\" 200 OK",
  "source": "kubectl_logs",
  "collection_date": "2026-08-06"
}
```

**Test Results:**
- 5 test records successfully converted
- All fields properly escaped
- JSON parsing valid
- jq validates output

---

## JSONL Conversion Script

### Test Conversion Command

```bash
#!/bin/bash
# /tmp/test-jsonl-v2.sh

POD_NAME="whisper-openai-68966786fb-jsb5d"
NAMESPACE="whisper-stt"
CLUSTER="ardenone-cluster"
OUTPUT_FILE="/tmp/whisper-stt-test.jsonl"

# Get raw logs and convert to JSONL
kubectl --server=http://traefik-ardenone-cluster:8001 logs "$POD_NAME" -n "$NAMESPACE" --tail=5 2>&1 | grep -v "^Defaulted" | while IFS= read -r line; do
    timestamp=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
    
    cat <<JSON
{"timestamp":"$timestamp","pod_name":"$POD_NAME","namespace":"$NAMESPACE","cluster":"$CLUSTER","container":"whisper-openai","log_line":"$(echo "$line" | sed 's/"/\\"/g')","source":"kubectl_logs","collection_date":"$(date -u +"%Y-%m-%d")"}
JSON
done > "$OUTPUT_FILE"

echo "JSONL conversion complete"
echo "Records: $(wc -l < "$OUTPUT_FILE")"
```

**Usage:**
```bash
chmod +x /tmp/test-jsonl-v2.sh
/tmp/test-jsonl-v2.sh
```

**Output:** `/tmp/whisper-stt-test.jsonl` with structured JSON records

---

## Acceptance Criteria Verification

### ✅ AC1: Working Command that Retrieves Logs

**Status:** COMPLETE
- Command validated with `--tail=100` (101 lines returned)
- Command validated with `--since=1h` (481 lines returned)
- Command validated without filters (96,086 lines returned)

### ✅ AC2: Command Tested on Small Sample

**Status:** COMPLETE
- Tested with `--tail=10`: 11 lines returned
- Tested with `--tail=100`: 101 lines returned
- Tested with `--since=1h`: 481 lines returned
- All tests successful

### ✅ AC3: Output Format Validated

**Status:** COMPLETE
- Plain text format: Valid FastAPI INFO logs
- JSONL conversion: Tested and working
- Output includes all required fields (timestamp, pod_name, log_line, etc.)
- Sample JSONL record validated with jq

### ✅ AC4: Command Documented in notes/

**Status:** COMPLETE
- This file: `/home/coding/aide-de-camp/notes/adc-q2q4h.md`
- Comprehensive documentation with examples
- Multiple retrieval methods documented
- JSONL conversion script included

---

## Log Content Analysis

### Log Patterns

The whisper-openai logs primarily contain:
- **HTTP health checks:** `GET /health HTTP/1.1" 200 OK`
- **Monitoring probes:** Periodic requests from `10.42.2.1` (kubelet/service mesh)
- **FastAPI access logs:** Uvicorn INFO level logging
- **Status codes:** All `200 OK` (no errors in sample)

### Log Density

Based on test results:
- **Recent (1 hour):** 481 log entries
- **Short sample (100 lines):** 100 entries
- **Full history:** 96,086 entries over 53 days
- **Average density:** ~1,814 entries/day (varies by probe frequency)

### Log Limitations

**Notable characteristics:**
- No error events visible (all 200 OK responses)
- No latency data included
- No request/response body logging
- Primarily health check spam
- whisper-stt main pod produces no logs to stdout

---

## Usage Examples

### Quick Health Check (Last 10 Lines)
```bash
kubectl --server=http://traefik-ardenone-cluster:8001 logs \
  whisper-openai-68966786fb-jsb5d -n whisper-stt --tail=10
```

### Recent Activity (Last Hour)
```bash
kubectl --server=http://traefik-ardenone-cluster:8001 logs \
  whisper-openai-68966786fb-jsb5d -n whisper-stt --since=1h
```

### JSONL Export (Test Sample)
```bash
/tmp/test-jsonl-v2.sh
cat /tmp/whisper-stt-test.jsonl | jq .
```

### Full 30-Day Export
```bash
kubectl --server=http://traefik-ardenone-cluster:8001 logs \
  whisper-openai-68966786fb-jsb5d -n whisper-stt \
  --since-time=2026-07-07T00:00:00Z > /tmp/whisper-stt-30d-raw.log
```

---

## Infrastructure Context

### Access Method
- **Protocol:** kubectl over HTTP proxy
- **Proxy URL:** `http://traefik-ardenone-cluster:8001`
- **Authentication:** Tailscale VPN (no tokens required)
- **Permissions:** Read-only pod logs

### Pod Information
```bash
kubectl --server=http://traefik-ardenone-cluster:8001 get pod \
  whisper-openai-68966786fb-jsb5d -n whisper-stt
```

**Current Pod Details:**
- Name: `whisper-openai-68966786fb-jsb5d`
- Ready: `1/1`
- Status: `Running`
- Restarts: `0`
- Age: `53d`

### Container Details
The pod has 2 containers (kubectl auto-selects the first):
1. `whisper-openai` (main container) - **Produces logs**
2. `model-download` (init container) - No logs in running state

---

## Related Documentation

- **Log Source Analysis:** See `logs/whisper-stt-retention-info.md`
- **Full 30-Day Gathering:** See `logs/whisper-stt-raw-gathering-summary.md`
- **Deployment Analysis:** See `logs/whisper-stt-deployment-info.md`
- **Data Limitations:** See `logs/whisper-stt-data-limitations-final.md`

---

## Conclusion

**Status:** ✅ **LOG RETRIEVAL COMMAND FULLY VALIDATED**

**Summary:**
- kubectl logs command working correctly
- Multiple filtering options tested and validated
- JSONL conversion tested and working
- Comprehensive documentation completed
- All acceptance criteria met

**Confidence Level:** **HIGH**
- Direct command execution on live cluster
- Multiple test sizes validated (10, 100, 1h)
- JSONL conversion validated with jq
- Output format documented

**Next Steps:**
1. Use validated command for full 30-day data gathering if needed
2. Apply JSONL conversion script to large-scale log retrieval
3. Integrate with analysis pipeline

---

**Generated:** 2026-08-06  
**Test Bead:** adc-q2q4h  
**Confidence:** **HIGH** - Direct testing on live cluster