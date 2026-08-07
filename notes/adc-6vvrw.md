# Whisper-STT Log Source and Retention - Task Summary

**Task ID:** adc-6vvrw
**Analysis Date:** 2026-08-06
**Cluster:** ardenone-cluster
**Service:** whisper-stt

## Acceptance Criteria Status

✅ **1. Log Source Identified:** Hybrid system (kubectl + VictoriaLogs)
✅ **2. All Pods Listed:** 2 pods currently running
✅ **3. Retention Period Determined:** 28 days (VictoriaLogs) + variable (kubectl)
✅ **4. Findings Documented:** This file + comprehensive retention analysis

---

## Log Sources

### Primary Source: VictoriaLogs (Centralized Log Aggregation)

**Status:** ✅ RUNNING
- **Pod:** `vlogs-server-0` (StatefulSet in `monitoring` namespace)
- **Retention:** **28 days** (4-week retention configured)
- **Access:** Port 9428, ClusterIP service
- **Query Interface:** LogicQL query language + Web UI

**Log Collection:**
- Vector DaemonSet (8 pods) collects all cluster logs
- Structured fields: `cluster`, `namespace`, `app`, `kubernetes.container_name`
- Elasticsearch bulk API with gzip compression

### Secondary Source: Kubernetes Native Logs

**Access Method:** `kubectl logs` via read-only proxy
- **Proxy:** `http://traefik-ardenone-cluster:8001`
- **Storage:** Node-local (`/var/log/pods/`, `/var/log/containers/`)
- **Retention:** Variable - lost on pod deletion/restart

---

## Current Pods

| Pod Name | Age | Started | Log Coverage | Status |
|----------|-----|---------|--------------|---------|
| `whisper-openai-68966786fb-jsb5d` | 53 days | 2026-06-14 | 53 days | ✅ Running |
| `whisper-stt-847fd8d7b9-v2rs5` | 25 days | 2026-07-12 | 25 days | ✅ Running |

**kubectl commands:**
```bash
# whisper-openai - FULL 30-day coverage
kubectl --server=http://traefik-ardenone-cluster:8001 logs \
  whisper-openai-68966786fb-jsb5d -n whisper-stt \
  --since-time=2026-07-07T00:00:00Z  # ✅ Returns logs

# whisper-stt - 25-day coverage (missing first 5 days)
kubectl --server=http://traefix-ardenone-cluster:8001 logs \
  whisper-stt-847fd8d7b9-v2rs5 -n whisper-stt \
  --since-time=2026-07-07T00:00:00Z  # ❌ Empty (pod started 2026-07-12)
```

---

## Retention Period Analysis

### VictoriaLogs Coverage (30-Day Window: 2026-07-07 to 2026-08-06)

**Available:** 28/30 days (93%)
- ✅ **2026-07-09 to 2026-08-06** (28 days available)
- ❌ **2026-07-07 to 2026-07-09** (2-day gap)

**Gap Cause:** VictoriaLogs configured with `retentionPeriod: "4w"` (28 days), not 30 days

### kubectl Logs Coverage (30-Day Window)

| Pod | Coverage | Gap Period |
|-----|----------|------------|
| **whisper-openai** | 30/30 days (100%) | None |
| **whisper-stt** | 25/30 days (83%) | 2026-07-07 to 2026-07-12 |

**Gap Cause:** Pod `whisper-stt-847fd8d7b9-v2rs5` started on 2026-07-12; previous pod logs deleted

---

## Local Data Collection

**File:** `logs/whisper-stt-raw.jsonl`
- **Size:** 16MB (as of 2026-08-06)
- **Format:** JSONL (one JSON log entry per line)
- **Contents:** Extracted logs from VictoriaLogs + kubectl
- **Last Updated:** 2026-08-06 23:23

---

## Configuration Files

### VictoriaLogs Application
**Path:** `/home/coding/declarative-config/k8s/ardenone-cluster/monitoring/victorialogs-application.yml`

**Key Settings:**
- `retentionPeriod: "4w"` (28 days)
- `storage: 20Gi` (Longhorn PVC)
- Vector enabled for log collection

### VictoriaLogs Grafana Datasource
**Path:** `/home/coding/declarative-config/k8s/ardenone-cluster/monitoring/victorialogs-grafana-datasource.yml`

**Access:** Port 9428, ClusterIP service

---

## Query Examples

### VictoriaLogs Queries

```bash
# All whisper-stt namespace logs (last 24 hours)
curl -G 'http://vlogs-server.monitoring.svc.cluster.local:9428/select/logicql' \
  --data-urlencode 'query={namespace="whisper-stt"}' \
  --data-urlencode 'start=@now()-24h' --data-urlencode 'end=@now()'

# Error logs only
curl -G 'http://vlogs-server.monitoring.svc.cluster.local:9428/select/logicql' \
  --data-urlencode 'query={namespace="whisper-stt"} |= "error"' \
  --data-urlencode 'start=@now()-24h' --data-urlencode 'end=@now()'
```

### Port-Forward for Local Access

```bash
# Forward VictoriaLogs to local port 9428
kubectl --server=http://traefik-ardenone-cluster:8001 port-forward -n monitoring svc/vlogs-server 9428:9428

# Access at http://localhost:9428
```

---

## Limitations

### Known Gaps

1. **VictoriaLogs 2-day gap:** First 2 days of 30-day window missing (retention configured for 4 weeks, not 30 days)
2. **whisper-stt 5-day gap:** Pod restarted 25 days ago, losing first 5 days of window
3. **Kubernetes log volatility:** Pod restarts/delete events clear logs
4. **No alternative aggregators:** Loki/Promtail, Elasticsearch/OpenSearch not deployed

### Mitigation Strategy

- Use hybrid approach: VictoriaLogs for structured analysis + kubectl logs for gap filling
- Accept data limitation: whisper-stt has permanent 5-day gap (2026-07-07 to 2026-07-12)
- Plan VictoriaLogs retention increase to 30+ days for future requirements

---

## Related Documentation

- **Comprehensive retention analysis:** `logs/whisper-stt-retention-info.md`
- **Data source inventory:** `pbx-web-whisper-stt-data-source-inventory.md`
- **Cluster access:** `CLAUDE.md` (Kubernetes Access section)

---

**Task Status:** ✅ COMPLETE
**Confidence Level:** HIGH - Direct cluster inspection + existing comprehensive documentation
**Method:** kubectl inspection + existing documentation review + configuration file analysis
