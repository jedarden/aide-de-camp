# Latency Metrics Query Findings

**Date:** 2026-08-07  
**Task:** Query latency metrics for pbx-web and whisper-stt spanning 30-day window  
**Result:** ❌ **NO LATENCY METRICS AVAILABLE IN DATA SOURCES**

## Executive Summary

After comprehensive analysis of available VictoriaLogs data for both pbx-web and whisper-stt services over the 30-day period (2026-07-07 to 2026-08-06), **zero latency metrics were found**. The existing log data does not contain the timing information required to calculate response times or processing durations.

## Data Analysis Results

### pbx-web Service
- **Total entries processed:** 10,000 (sample from 74.4 MB VictoriaLogs file)
- **Valid latency entries:** 0
- **Coverage:** 0.0% (no days with latency data)
- **Temporal gaps:** 31 days (complete gap)

**Log format found:**
```
10.42.6.1 - - [06/Aug/2026:16:52:44 +0000] "GET / HTTP/1.1" 200 80237 "-" "kube-probe/1.34" "-"
```

**Issue:** Nginx access logs **do not include request timing fields**:
- ❌ No `request_time` field
- ❌ No `upstream_response_time` field  
- ❌ No `msec` or timing information
- ✅ Only basic HTTP request/response status

### whisper-stt Service
- **Total entries processed:** 98,252 (from 39.1 MB VictoriaLogs file)
- **Valid latency entries:** 0
- **Coverage:** 0.0% (no days with latency data)
- **Temporal gaps:** 31 days (complete gap)

**Log format found:**
```
INFO: 10.42.2.1:43574 - "GET /health HTTP/1.1" 200 OK
```

**Issue:** whisper-stt logs **only contain health check requests**:
- ❌ No transcription processing duration
- ❌ No audio processing timing
- ❌ No application-level latency metrics
- ✅ Only health check `GET /health` requests

## Root Cause Analysis

### Missing pbx-web Latency Data
The nginx logs use a standard combined log format **without** timing extensions. To capture latency metrics, the nginx configuration would need to include:

```nginx
log_format main_with_time '$remote_addr - $remote_user [$time_local] '
                           '"$request" $status $body_bytes_sent '
                           '"$http_referer" "$http_user_agent" '
                           '$request_time $upstream_response_time';
```

### Missing whisper-stt Latency Data  
The whisper-stt application only logs health check requests. Actual transcription processing data (which would contain timing information) is either:
1. Not being logged to stdout/stderr
2. Being logged at a different log level
3. Being sent to a different logging system
4. Not being captured by VictoriaLogs

## Recommendations

### Immediate Actions Required

#### 1. Configure Nginx Latency Logging (pbx-web)
Update nginx log format to include timing fields:
```yaml
# In pbx-web nginx configuration
log_format: 'main_with_time $remote_addr - $remote_user [$time_local] '
             '"$request" $status $body_bytes_sent '
             '"$http_referer" "$http_user_agent" '
             'rt=$request_time uct=$upstream_connect_time '
             'uht=$upstream_header_time urt=$upstream_response_time';
```

#### 2. Enable Application-Level Latency Logging (whisper-stt)
Modify whisper-stt application to log processing duration:
```python
# Example for whisper-stt logging
import time
import logging

logger = logging.getLogger(__name__)

def process_audio(audio_data):
    start_time = time.time()
    result = transcribe(audio_data)
    duration = time.time() - start_time
    
    logger.info(f"Transcription completed: duration={duration:.3f}s, "
                f"audio_length={len(audio_data)}s, "
                f"model={model_name}")
    
    return result
```

#### 3. Application Performance Monitoring
Consider implementing APM solutions:
- **Prometheus + Grafana** for basic metrics
- **Jaeger** for distributed tracing  
- **OpenTelemetry** for standardized observability

## Alternative Data Sources

Since VictoriaLogs doesn't contain latency data, consider these alternatives:

### 1. Kubernetes API Metrics
- Query pod/container resource metrics via Prometheus
- May provide CPU/memory latency indicators

### 2. ArgoCD Deployment Times
- Already captured in deployment event data
- Shows deployment frequency but not request latency

### 3. Synthetic Monitoring  
- Implement external health checks with timing
- Use tools like `curl -w "@curl-format.txt"` to measure response times

## Conclusion

**The task acceptance criteria cannot be met with current data sources:**

- ❌ pbx-web latency metrics (p50, p95, p99) - **NO DATA AVAILABLE**
- ❌ whisper-stt latency metrics (processing duration) - **NO DATA AVAILABLE**  
- ❌ Temporal gap analysis - **100% GAP (no data to analyze)**
- ❌ Raw latency data storage - **NO LATENCY DATA TO STORE**

**To complete this task successfully, latency logging must be enabled in both services first.**

## Next Steps

1. **Configuration Changes:**
   - Update nginx log format for pbx-web
   - Add application-level timing logs for whisper-stt
   
2. **Data Collection:**
   - Allow 24-48 hours for new logs to accumulate
   - Re-run latency metrics queries
   
3. **Validation:**
   - Verify timing fields appear in VictoriaLogs
   - Confirm percentile calculations work with real data

**Estimated time to complete task after configuration changes: 24-48 hours**