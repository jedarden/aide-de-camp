# whisper-stt Log Retention and Availability Analysis

**Analysis Date:** 2026-08-06  
**Analysis Period:** July 7, 2026 - August 6, 2026 (30 days)  
**Cluster:** ardenone-cluster  
**Service:** whisper-stt  
**Namespace:** whisper-stt

---

## Executive Summary

**Maximum Log Retention:** ~25-27 days (node-local logs only)  
**30-Day Coverage Available:** ✅ **YES** (90% coverage, 27 of 30 days)  
**Coverage Gaps:** 4-day gap (2026-07-06 to 2026-07-10)  
**Centralized Logging:** ❌ **NONE** (no VictoriaLogs/Loki integration)

---

## Current Log Availability Status

### ✅ Available Logs

**Current Running Pods:**
- **whisper-stt-847fd8d7b9-v2rs5:** Running since 2026-07-12T16:53:42Z (~25 days)
  - Log Coverage: 2026-07-12 to 2026-08-06
  - Log File: `pod-whisper-stt-847fd8d7b9-v2rs5-2026-08-06.log`
  - Status: Minimal activity (idle/low-traffic pod)

- **whisper-openai-68966786fb-jsb5d:** Running since 2026-06-14 (~53 days)
  - Log Coverage: 2026-07-10 to 2026-08-06 (~27 days)
  - Log File: `pod-whisper-openai-68966786fb-jsb5d-2026-08-06.log`
  - Status: Active health check logs (~6 requests/minute)
  - File Size: 8.4 MB (90,212 log entries)

**Coverage Timeline:**
```
30-Day Window (2026-07-06 to 2026-08-06)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  [GAP]  [███████████████████████████████████████████]
  4 days  ~27 days of available logs
  07-06   07-10 to 08-06
```

### ❌ Unavailable Logs

**Historical Pods (Deleted):**
- **whisper-stt-5dbff75cbd-*:** No logs available (pods deleted)
- **whisper-stt-5b8558f478-*:** No logs available (pods deleted)
- **whisper-stt-6c497489fb-*:** No logs available (pods deleted)

**Missing Period:**
- **2026-07-06 to 2026-07-10 (~4 days):** Not covered by current logs
  - Likely due to log rotation or pod restart
  - Node-local log retention limits

---

## Log Retention Policy Analysis

### Kubernetes Node-Local Log Retention

**Retention Mechanism:**
- **Storage:** Node-local file system (`/var/log/pods/`)
- **Rotation:** kubelet-controlled log rotation
- **Retention Period:** ~25-27 days maximum (based on available logs)

**Standard K3s/k3s-agent Settings:**
- **Rotation:** When logs reach 10MB or log file age threshold
- **Retention:** Limited by disk space and rotation policy
- **No Central Storage:** Logs lost when pods are deleted

**Limitations:**
1. **Pod Deletion:** Logs from deleted pods are immediately unavailable
2. **Node Eviction:** Pod movement to new node loses old logs
3. **Disk Space:** Older logs rotated out when space limits reached
4. **No Aggregation:** No centralized log collection or querying

---

## Centralized Logging Infrastructure

### Current Status: ❌ NO INTEGRATION

**Checked Systems:**
- ❌ **VictoriaLogs:** Not configured on ardenone-cluster
  - VictoriaLogs applications exist on other clusters (iad-ci, ord-devimprint)
  - Not deployed for ardenone-cluster workloads
- ❌ **Loki:** Not detected on ardenone-cluster
- ❌ **Vector:** No log collection daemonsets found
- ❌ **Fluent Bit/Fluentd:** Not deployed on ardenone-cluster
- ❌ **Elasticsearch/OpenSearch:** Not detected

**Implications:**
- No cross-cluster log correlation
- No historical log search beyond 30 days
- No centralized log analysis or alerting
- Logs are ephemeral and node-bound

---

## Retention Gaps and Limitations

### Gap 1: 4-Day Coverage Gap (2026-07-06 to 2026-07-10)

**Cause:** Likely kubelet log rotation or pod restart

**Impact:** 
- Missing deployment events during gap period
- Unknown error/failure data from this period
- Cannot verify service health during gap

### Gap 2: Historical Pod Logs Unavailable

**Cause:** Kubernetes deletes logs when pods are deleted

**Impact:**
- No historical analysis beyond current pod lifetime
- Lost logs from previous ReplicaSets (5dbff75cbd, 5b8558f478, 6c497489fb)
- Cannot investigate historical issues

### Gap 3: Node-Local Storage Only

**Cause:** No centralized log aggregation

**Impact:**
- Logs lost during node maintenance/upgrades
- No cross-cluster correlation
- No long-term retention beyond 30 days

---

## Alternative Log Sources

### ✅ Available Sources

1. **Current Pod Logs (kubectl logs)**
   - **Retention:** ~25-27 days maximum
   - **Access:** `kubectl logs <pod-name> -n whisper-stt`
   - **Coverage:** Current pod lifetime only

2. **Node File System (Direct Access)**
   - **Location:** `/var/log/pods/<namespace>_<pod-name>_<pod-uid>/<container>/`
   - **Retention:** Same as kubectl logs (subject to rotation)
   - **Access:** Requires SSH to k3s-agent nodes

3. **Research Directory (Archived Logs)**
   - **Location:** `research/whisper-stt-30days/pod-logs/`
   - **Coverage:** ~27 of 30 days (2026-07-10 to 2026-08-06)
   - **Files:** 
     - `pod-whisper-openai-68966786fb-jsb5d-2026-08-06.log` (8.4 MB)
     - `pod-whisper-stt-847fd8d7b9-v2rs5-2026-08-06.log` (210 bytes)

### ❌ Unavailable Sources

1. **VictoriaLogs:** Not configured for ardenone-cluster
2. **Loki/Elasticsearch:** Not deployed
3. **Cloud Logging:** No cloud provider integration
4. **External Forwarding:** No syslog or external log shipping

---

## Recommendations

### Immediate Actions

1. ✅ **Use Current Logs:** 30-day analysis is possible with ~90% coverage
   - Use archived logs in `research/whisper-stt-30days/pod-logs/`
   - Supplement with current `kubectl logs` for latest entries
   - Document the 4-day gap in any analysis

### Future Improvements

1. **Deploy Centralized Logging (HIGH PRIORITY)**
   - **Option A:** Deploy VictoriaLogs on ardenone-cluster
   - **Option B:** Implement Vector/Fluent Bit for log forwarding
   - **Benefit:** Historical log access, cross-cluster correlation, alerting

2. **Implement Log Streaming**
   - Forward logs to VictoriaLogs instance on rs-manager
   - Configure log retention policies (30+ days)
   - Enable log-based alerting and monitoring

3. **Add Log-Based Monitoring**
   - Alert on error patterns in logs
   - Detect service degradation from log analysis
   - Correlate logs across related services

### Long-Term Architecture

1. **Multi-Cluster Log Aggregation**
   - Centralize logs from all clusters to VictoriaLogs
   - Enable cross-cluster service analysis
   - Implement unified log retention policies

2. **Log-Based Metrics**
   - Extract metrics from logs (request rates, error rates)
   - Correlate with Prometheus metrics
   - Enhance observability

---

## Conclusion

**Current Status:** ✅ **30-DAY ANALYSIS POSSIBLE WITH LIMITATIONS**

**Key Findings:**
- ✅ **Available:** ~27 of 30 days (~90% coverage)
- ⚠️ **Gaps:** 4-day gap (2026-07-06 to 2026-07-10)
- ❌ **Centralized Logging:** None available
- ❌ **Historical Logs:** Limited to current pod lifetime

**Recommendation:** Proceed with 30-day analysis using archived logs and current `kubectl logs`, documenting the 4-day gap as a limitation. Plan for centralized logging deployment to improve future log retention and analysis capabilities.

---

**Generated:** 2026-08-06  
**Analysis Bead:** adc-6bmhm  
**Confidence Level:** **HIGH** - Direct cluster inspection + archived log analysis + infrastructure survey  
**Log Coverage:** ✅ **90%** (27 of 30 days available)
