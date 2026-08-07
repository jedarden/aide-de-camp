# Whisper-STT Event Extraction - Parsing Notes

## Summary
Extracted structured events from 97,399 log entries spanning 30 days (2026-07-10 to 2026-08-07).

## Results
**No significant events found.** All logs contain routine health check requests with 200 OK responses.

### Event Categories Searched
1. **HTTP 5xx errors** (500-599) - server errors, internal failures
2. **HTTP 4xx errors** (400-499) - client errors, bad requests
3. **Pod lifecycle events** - OOMKilled, CrashLoopBackOff, restarts
4. **Application exceptions** - Python exceptions, application failures
5. **Timeout events** - request timeouts, slow operations
6. **Latency issues** - slow requests, high latency patterns

## Parsing Methodology

### Event Classification Schema
```python
{
    "event_type": str,        # Event category (http_error, pod_oom_kill, etc.)
    "severity": str,          # error | warning | info
    "timestamp": str,         # ISO 8601 timestamp
    "pod_name": str,          # Kubernetes pod name
    "namespace": str,          # Kubernetes namespace
    "details": dict           # Event-specific details
}
```

### HTTP Status Extraction
Pattern: `INFO:     IP:PORT - "METHOD /path HTTP/1.1" STATUS STATUS_TEXT`

Extracts:
- Method (GET, POST, etc.)
- Path (/health, /transcribe, etc.)
- Status code (200, 500, etc.)
- Status text (OK, Internal Server Error, etc.)

### Error Pattern Detection
Regular expressions match:
- `OOMKilled` → pod_oom_kill
- `CrashLoopBackOff` → pod_crash_loop
- `exception` → application_exception
- `failed` → operation_failure
- `timeout` → timeout
- `Error from server` → kubernetes_error

### Latency Pattern Detection
Matches:
- `slow request`
- `high latency`
- `took \d+ms`
- `took \d+ seconds?`
- `latency.*\d+ms`

### Pod Lifecycle Pattern Detection
Matches:
- `pod started` → pod_started
- `pod stopped` → pod_stopped
- `pod restarted` → pod_restarted
- `container started` → container_started
- `container stopped` → container_stopped

## Log Characteristics

### Observed Log Patterns
All entries follow this structure:
```json
{
  "timestamp": "2026-07-10T13:39:33.767796087-04:00",
  "pod_name": "whisper-openai-68966786fb-jsb5d",
  "namespace": "whisper-stt",
  "log_message": "INFO:     10.42.2.1:43574 - \"GET /health HTTP/1.1\" 200 OK",
  "source": "kubectl"
}
```

### Log Content Distribution
- 97,399 total log entries
- 100% health check requests (GET /health)
- 100% successful responses (200 OK)
- 2 pods observed: whisper-openai-* and whisper-stt-*

### Limitations Noted
1. **No application-level logs** - Only HTTP access logs from Uvicorn/FastAPI
2. **No stderr output** - Only stdout captured
3. **No Python tracebacks** - Exception logs not present
4. **No startup/shutdown logs** - Pod lifecycle events not captured
5. **No latency metrics** - Response times not included in log format

## Comparison with pbx-web Approach
The whisper-stt logs are **simpler** than pbx-web logs:
- No multi-source aggregation (only kubectl logs)
- No VictoriaLogs integration
- No structured JSON within log_message field
- No nginx error logs or separate error streams

This means the extraction found fewer event types - only HTTP status codes could be reliably extracted, and all were successful.

## Parsing Challenges
None encountered. The log format is consistent and machine-parseable JSON.

## Output Files
- `logs/whisper-stt-events.jsonl` - Structured events (0 events found)
- `logs/whisper-stt-events-summary.json` - Aggregate statistics
- `extract_whisper_stt_events.py` - Extraction script
