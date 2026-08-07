# Whisper-STT Log Retention and Availability

**Analysis Date:** 2026-08-06
**Analysis Period:** July 7, 2026 - August 6, 2026 (30 days)
**Cluster:** ardenone-cluster
**Service:** whisper-stt
**Namespace:** whisper-stt

---

## Executive Summary

**Maximum Log Retention:** 28 days via VictoriaLogs + variable via kubectl logs
**30-Day Coverage Available:** ⚠️ **PARTIAL** (28/30 days via VictoriaLogs, 30/30 for whisper-openai only)
**Retention Gap:** 2-day VictoriaLogs gap (2026-07-07 to 2026-07-09), 5-day gap for whisper-stt pod
**Centralized Logging:** ✅ **VictoriaLogs running** - 4-week retention period configured

---

## Log Sources and Infrastructure

### 1. VictoriaLogs (Centralized Log Aggregator)

**Status:** ✅ **RUNNING**

**Deployment Details:**
- **Pod:** `vlogs-server-0` (StatefulSet in `monitoring` namespace)
- **Retention Period:** **4 weeks (28 days)** - configured via `retentionPeriod: "4w"`
- **Storage:** 20Gi Longhorn PVC
- **Service:** ClusterIP on port 9428
- **Grafana Integration:** Datasource configured

**Log Collection Architecture:**
- **Vector DaemonSet** (8 pods running across cluster nodes)
- **Collection Scope:** All cluster-wide pod logs
- **Stream Fields:** `cluster`, `namespace`, `app`, `kubernetes.container_name`
- **Ingestion:** Elasticsearch bulk API with gzip compression

**Configuration File:** `/home/coding/declarative-config/k8s/ardenone-cluster/monitoring/victorialogs-application.yml`

**Retention Coverage:**
- **Available:** 2026-07-09 to 2026-08-06 (28 days)
- **Missing:** 2026-07-07 to 2026-07-09 (2-day gap)
- **Reason:** Retention configured for 4 weeks, not full 30 days

---

### 2. Kubernetes Native Logs (`kubectl logs`)

**Pod Status and Availability:**

| Pod | Age | Start Date | Log Coverage | 30-Day Window |
|-----|-----|------------|--------------|----------------|
| `whisper-openai-68966786fb-jsb5d` | 53 days | 2026-06-14 | 53 days | ✅ **100%** (full 30 days) |
| `whisper-stt-847fd8d7b9-v2rs5` | 25 days | 2026-07-12 | 25 days | ❌ **83%** (missing first 5 days) |

**Kubernetes Log Retention Policy:**
- **Storage:** Node-local (`/var/log/pods/`, `/var/log/containers/`)
- **Rotation:** Kubelet-controlled based on disk pressure and file size
- **No Fixed Retention:** Logs lost when pods are deleted/restarted
- **Node Changes:** Pod movement to new node loses old logs

**kubectl Log Access:**
```bash
# whisper-openai - FULL 30-day coverage available
kubectl --server=http://traefik-ardenone-cluster:8001 logs \
  whisper-openai-68966786fb-jsb5d -n whisper-stt \
  --since-time=2026-07-07T00:00:00Z  # ✅ Returns logs

# whisper-stt - ONLY 25 days available (missing first 5 days)
kubectl --server=http://traefik-ardenone-cluster:8001 logs \
  whisper-stt-847fd8d7b9-v2rs5 -n whisper-stt \
  --since-time=2026-07-07T00:00:00Z  # ❌ Empty (pod started 2026-07-12)
```

---

## 30-Day Coverage Analysis (2026-07-07 to 2026-08-06)

### Coverage Timeline

```
30-Day Window (2026-07-07 to 2026-08-06)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
VictoriaLogs:    [GAP]  [████████████████████████████████████]
                  2d               28 days
                  07-07   07-09 to 08-06

kubectl (whisper-openai):  [███████████████████████████████████████████]
                              53 days available (100% coverage)

kubectl (whisper-stt):              [██████████████████████████████████]
                                   25 days (83% coverage)
                                   07-12 to 08-06
```

### Summary Table

| Log Source | Coverage | Gap Period | Notes |
|------------|----------|------------|-------|
| **VictoriaLogs** | 28/30 days (93%) | 2026-07-07 to 2026-07-09 | Configured for 4-week retention |
| **kubectl (whisper-openai)** | 30/30 days (100%) | None | Pod has 53-day history |
| **kubectl (whisper-stt)** | 25/30 days (83%) | 2026-07-07 to 2026-07-12 | Pod restarted 5 days into window |

**Best Available Coverage for 30-Day Analysis:**
- **whisper-openai:** 100% via kubectl logs, 93% via VictoriaLogs
- **whisper-stt:** 83% via both sources (5-day gap from pod restart)

---

## Retention Gaps and Limitations

### Gap 1: VictoriaLogs 2-Day Retention Gap

**Period:** 2026-07-07 to 2026-07-09 (2 days)
**Cause:** VictoriaLogs configured with `retentionPeriod: "4w"` (28 days), not 30 days
**Impact:** First 2 days of 30-day window missing from centralized logs
**Mitigation:** Use kubectl logs from whisper-openai pod (has full 53-day history)

### Gap 2: whisper-stt Pod Restart Gap

**Period:** 2026-07-07 to 2026-07-12 (5 days)
**Cause:** Pod `whisper-stt-847fd8d7b9-v2rs5` started on 2026-07-12
**Impact:** No logs available for whisper-stt during first 5 days of window
**Note:** Previous pod incarnations deleted - logs unrecoverable
**Status:** ⚠️ **Unavoidable data loss** - pod was not running during this period

### Gap 3: Kubernetes Native Log Limitations

**Issues:**
- **Pod restarts clear logs** - only current pod incarnation available
- **Node rotation loses logs** - local storage on node filesystem
- **No fixed retention** - depends on disk pressure and kubelet rotation
- **No centralized querying** - must know pod name and namespace

** victoriaLogs Advantages:**
- ✅ Centralized query across all pods/containers
- ✅ Structured log data with stream fields
- ✅ Survives pod restarts and node changes
- ✅ Web UI for ad-hoc queries

---

## Alternative Log Sources

### ✅ Available

1. **VictoriaLogs Web UI**
   - Port: 9428 (ClusterIP)
   - Query language for structured searches
   - 28-day retention

2. **Grafana Dashboards**
   - VictoriaLogs datasource configured
   - Same 28-day retention as direct VictoriaLogs access

3. **kubectl logs**
   - Direct access to container stdout/stderr
   - Variable retention based on pod age
   - whisper-openai: 53 days, whisper-stt: 25 days

### ❌ Not Available

1. **Loki/Promtail** - Not deployed in cluster
2. **Elasticsearch/OpenSearch** - Not detected
3. **Cloud logging services** - No cloud provider integration
4. **External log forwarding** - No syslog or external shipping

---

## Recommendations

### For Current 30-Day Analysis

1. **Use hybrid approach:**
   - Query VictoriaLogs for structured analysis (covers 28 days)
   - Fill 2-day VictoriaLogs gap with kubectl logs from whisper-openai
   - **Document limitation:** whisper-stt has no logs for 2026-07-07 to 2026-07-12 (5-day gap)

2. **Accept data limitation:**
   - whisper-stt logs are only available from 2026-07-12 onwards
   - Earlier logs are permanently lost due to pod restart/deletion
   - Analysis conclusions must account for this gap

### For Future Requirements

1. **Increase VictoriaLogs retention:**
   - Modify `retentionPeriod: "4w"` → `retentionPeriod: "30d"` or `"5w"`
   - Edit in: `/home/coding/declarative-config/k8s/ardenone-cluster/monitoring/victorialogs-application.yml`
   - Monitor PVC usage (20Gi current - may need expansion)

2. **Implement log export/archival:**
   - Set up periodic VictoriaLogs export to long-term storage
   - Implement cold storage retention policies (90+ days)
   - Enable compliance/audit trail capabilities

3. **Add log retention monitoring:**
   - Alert on VictoriaLogs storage utilization
   - Track pod restart events that affect log continuity
   - Monitor log ingestion rates and gaps

4. **Consider pod lifecycle management:**
   - Longer pod lifetimes reduce log gaps
   - Implement pod disruption budgets carefully
   - Document deployment schedules that may cause pod restarts

---

## Configuration Reference

### VictoriaLogs Application
**File:** `/home/coding/declarative-config/k8s/ardenone-cluster/monitoring/victorialogs-application.yml`
**Key Settings:**
- `retentionPeriod: "4w"` (28 days)
- `storage: 20Gi` (Longhorn PVC)
- Vector enabled for log collection

### VictoriaLogs Grafana Datasource
**File:** `/home/coding/declarative-config/k8s/ardenone-cluster/monitoring/victorialogs-grafana-datasource.yml`
**Access:** Port 9428, ClusterIP

---

## Conclusion

**Current Status:** ⚠️ **30-DAY ANALYSIS POSSIBLE WITH DOCUMENTED GAPS**

**Coverage Summary:**
- ✅ **VictoriaLogs:** 28/30 days (93%) - missing first 2 days
- ✅ **whisper-openai:** 30/30 days (100%) via kubectl logs
- ⚠️ **whisper-stt:** 25/30 days (83%) - missing first 5 days due to pod restart

**Key Findings:**
1. VictoriaLogs provides centralized aggregation with 28-day retention
2. 2-day retention gap from 4-week configuration (not 30 days)
3. whisper-stt pod restarted 25 days ago, causing 5-day gap
4. Kubernetes native logs have variable retention based on pod lifetime
5. No alternative log aggregators available

**Recommendation:** Proceed with 30-day analysis using available data, explicitly documenting the retention gaps. Plan VictoriaLogs retention increase to 30+ days and consider log archival for long-term requirements.

---

**Generated:** 2026-08-06
**Analysis Bead:** adc-6bmhm
**Confidence Level:** **HIGH** - Direct cluster inspection, VictoriaLogs configuration review, pod status verification
**Method:** kubectl inspection + declarative-config review + VictoriaLogs retention policy analysis
