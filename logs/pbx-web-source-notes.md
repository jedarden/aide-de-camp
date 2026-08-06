# pbx-web Log Aggregation Source and Retention

**Investigation Date:** 2026-08-06  
**Deployment:** apexalgo-iad cluster (redirected from ardenone-cluster)

## Log Aggregation System

**VictoriaLogs (Single Node)** - v1.36.1-scratch

### Infrastructure Details

- **Chart:** victoria-logs-single (Helm) v0.11.17
- **Location:** ardenone-cluster, `monitoring` namespace
- **Storage:** 20Gi Longhorn PVC (ReadWriteOnce)
- **Service:** victorialogs-single-ardenone-cluster-vector (ClusterIP :9428)

### Log Collection Method

**Vector DaemonSet** - Automatic Kubernetes log collection
- **Clusters collecting logs:** 
  - ardenone-cluster (primary)
  - apexalgo-iad (forwarded to ardenone-cluster)
- **Collection source:** `kubernetes_logs` - captures all pod stdout/stderr
- **Processing:** JSON parsing, cluster/app/namespace enrichment
- **Forwarding:** VictoriaLogs Elasticsearch bulk API (:9428/insert/elasticsearch)

### pbx-web Deployment

- **Cluster:** ardenone-cluster
- **Namespace:** pbx-web
- **Current Pod:** pbx-web-5ff68464d-mkn8n
- **Containers:**
  - site-generator: ronaldraygun/pbx-web:1.0.9
  - nginx: localhost:7439/nginx:alpine

## Retention Period

**Maximum Retention: 28 days (4 weeks)**

Configuration:
```yaml
retentionPeriod: "4w"
```

Set via VictoriaLogs values in `victorialogs-application.yml` under declarative-config.

## Log Query Capabilities

VictoriaLogs supports:
- Full-text search across log streams
- Filtering by cluster, namespace, app, container
- Time-based queries within retention window
- LogQL (VictoriaLogs Query Language) for complex queries

## Access Method

VictoriaLogs is accessible via:
- **Internal:** http://victorialogs-single-ardenone-cluster-vector.monitoring.svc.cluster.local:9428
- **Cross-cluster:** victorialogs service (ExternalName → ardenone-cluster-mesh.tailscale.svc.cluster.local:9428)
- **Web UI:** Available at VictoriaLogs HTTP endpoint (port 9428) - exposed via Tailscale mesh

## Limitations

1. **Fixed 28-day retention** - no extended archive tier configured
2. **20Gi storage limit** - circular log deletion when full
3. **No external log shipping** - logs remain within cluster infrastructure
4. **Log duplication** - Vector processes all container logs including sidecars

## Verification Commands

```bash
# Check VictoriaLogs retention
kubectl --server=http://traefik-ardenone-cluster:8001 get statefulsets -n monitoring

# View Vector log collection config
kubectl --server=http://traefik-ardenone-cluster:8001 get cm victorialogs-single-ardenone-cluster-vector -n monitoring -o yaml

# Check pbx-web logs via VictoriaLogs API
curl -s 'http://victorialogs-single-ardenone-cluster-vector.monitoring.svc.cluster.local:9428/select/logomic/query' \
  --data-urlencode 'query={namespace="pbx-web"}' | jq .
```

## Source Files

- **declarative-config:** `k8s/ardenone-cluster/monitoring/victorialogs-application.yml`
- **apexalgo-iad Vector config:** `monitoring` namespace ConfigMap `vector-config`
- **ardenone-cluster Vector config:** Embedded in VictoriaLogs application values
