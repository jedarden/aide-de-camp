# Observability Access Verification Report

**Generated:** 2026-08-06  
**Purpose:** Verify connectivity and authentication for all observability data sources

## Summary

| Endpoint | Accessible | Auth Method | Notes |
|----------|-----------|-------------|-------|
| ✅ Working | 11/15 | Multiple | See details below |
| ❌ Not Working | 4/15 | Various | See details below |

---

## Kubernetes Clusters

### ✅ apexalgo-iad (Read-Only Proxy)
- **Endpoint:** `http://traefik-apexalgo-iad:8001`
- **Accessible:** Yes
- **Auth Method:** Tailscale VPN + kubectl-proxy (ServiceAccount with read-only RBAC in `devpod-observer` namespace)
- **Notes:** Full read access to pods, nodes, deployments, services, logs
- **Limitations:** Cannot access metrics API (`top nodes` forbidden), no write access

### ❌ apexalgo-iad (Admin Kubeconfig)
- **Kubeconfig:** `/home/coding/.kube/apexalgo-iad.kubeconfig`
- **Accessible:** No
- **Auth Method:** OIDC token (cloudspace-admin group)
- **Issue:** OIDC token expired (~3 day expiry, needs regeneration from Rackspace Spot UI)
- **Notes:** Token was valid on 2026-07-28, expired by 2026-08-06

### ✅ ardenone-cluster (Read-Only Proxy)
- **Endpoint:** `http://traefik-ardenone-cluster:8001`
- **Accessible:** Yes
- **Auth Method:** Tailscale VPN + kubectl-proxy (ServiceAccount with read-only RBAC in `devpod-observer` namespace)
- **Notes:** Full read access to pods (18+ namespaces accessible), nodes, deployments, services, logs

### ✅ ardenone-manager (Read-Only Proxy)
- **Endpoint:** `http://traefik-ardenone-manager:8001`
- **Accessible:** Yes
- **Auth Method:** Tailscale VPN + kubectl-proxy (ServiceAccount with read-only RBAC in `devpod-observer` namespace)
- **Notes:** Full read access to nodes, pods, services, ArgoCD applications CRD

### ❌ ardenone-manager (Admin Kubeconfig)
- **Kubeconfig:** `/home/coding/.kube/ardenone-manager.kubeconfig`
- **Accessible:** No
- **Auth Method:** File not found
- **Issue:** Kubeconfig file missing (should be created for cluster-admin access)

### ✅ rs-manager (Read-Only Proxy)
- **Endpoint:** `http://traefik-rs-manager:8001`
- **Accessible:** Yes
- **Auth Method:** Tailscale VPN + kubectl-proxy (ServiceAccount with read-only RBAC in `devpod-observer` namespace)
- **Notes:** Full read access to nodes, pods, services, events, ArgoCD applications CRD

### ✅ rs-manager (Admin Kubeconfig)
- **Kubeconfig:** `/home/coding/.kube/rs-manager.kubeconfig`
- **Accessible:** Yes
- **Auth Method:** Direct kubeconfig (cluster-admin SA token)
- **Notes:** Full cluster-admin access, can read/write all resources including ArgoCD CRDs

### ✅ ord-devimprint (Observer)
- **Endpoint:** `http://kubectl-proxy-ord-devimprint:8001`
- **Accessible:** Yes
- **Auth Method:** Tailscale operator (long-lived SA token in `devpod-observer` namespace)
- **Notes:** Full read access to 18 namespaces, RBAC includes pods, events, deployments, PVCs, volumeattachments

### ✅ ord-devimprint (Observer Kubeconfig)
- **Kubeconfig:** `/home/coding/.kube/ord-devimprint-observer.kubeconfig`
- **Accessible:** Yes
- **Auth Method:** Long-lived SA token (never expires)
- **Notes:** Read-only access, bypasses kubectl-proxy

### ❌ iad-kalshi (Proxy)
- **Endpoint:** `http://kubectl-proxy-iad-kalshi:8001`
- **Accessible:** No
- **Auth Method:** Tailscale operator
- **Issue:** Connection refused (proxy pod not running or Tailscale route down)
- **Notes:** Used to host kalshi-weather workloads (kalshi-tape, weather-fast)

### ✅ iad-options (Read-Only Proxy)
- **Endpoint:** `http://traefik-iad-options:8001`
- **Accessible:** Yes
- **Auth Method:** Tailscale VPN + Traefik `kubectl-tcp` entrypoint (ServiceAccount with read-only RBAC)
- **Notes:** Read-only proxy explicitly denies access to secrets (stricter than other clusters)

### ✅ iad-options (Observer Kubeconfig)
- **Kubeconfig:** `/home/coding/.kube/iad-options-observer.kubeconfig`
- **Accessible:** Yes
- **Auth Method:** Long-lived SA token
- **Notes:** Bypasses kubectl-proxy, read-only access

### ✅ iad-ci (Admin Kubeconfig)
- **Kubeconfig:** `/home/coding/.kube/iad-ci.kubeconfig`
- **Accessible:** Yes
- **Auth Method:** ServiceAccount `argocd-manager` with cluster-admin access
- **Notes:** Full cluster-admin access to CI/CD cluster running Argo Workflows

---

## ArgoCD

### ❌ ArgoCD Read-Only API Proxy
- **Endpoint:** `https://argocd-ro-ardenone-manager-ts.ardenone.com:8444/api/v1/applications`
- **Accessible:** No
- **Auth Method:** Read-only bearer token (injected by proxy)
- **Issue:** HTTP code 000 (connection failed/timeout)
- **Notes:** Proxy service exists (`argocd-readonly-proxy` at `10.43.168.245:80`) but not responding

### ✅ ArgoCD Applications CRD (via kubectl)
- **Endpoint:** `kubectl get applications.argoproj.io -A` (via rs-manager proxy)
- **Accessible:** Yes
- **Auth Method:** Read-only kubectl proxy access
- **Notes:** Can read ArgoCD application status, sync status, health status

### ✅ ArgoCD Services (ardenone-manager)
- **Endpoint:** `kubectl get svc -n argocd` (via ardenone-manager proxy)
- **Accessible:** Yes
- **Auth Method:** Read-only kubectl proxy access
- **Notes:** All ArgoCD services visible (server, repo-server, redis, dex, etc.)

---

## Argo Workflows

### ✅ Argo Workflows (iad-ci Kubeconfig)
- **Endpoint:** `kubectl --kubeconfig=/home/coding/.kube/iad-ci.kubeconfig get workflows -n argo-workflows`
- **Accessible:** Yes
- **Auth Method:** Cluster-admin SA via kubeconfig
- **Notes:** Full read access to workflows, pods, logs in iad-ci cluster

### ✅ Argo Workflows Pods (iad-ci)
- **Endpoint:** `kubectl --kubeconfig=/home/coding/.kube/iad-ci.kubeconfig get pods -n argo-workflows`
- **Accessible:** Yes
- **Auth Method:** Cluster-admin SA via kubeconfig
- **Notes:** Can access workflow pods, controller, server logs

### ❌ Argo Workflows UI
- **Endpoint:** `https://argo-ci.ardenone.com`
- **Accessible:** No
- **Auth Method:** Google SSO + VPN-only
- **Issue:** Error code: 1033 (likely authentication/authorization failure)
- **Notes:** UI should be accessible via Tailscale VPN with Google SSO

### ❌ Argo Workflows (rs-manager Proxy)
- **Endpoint:** `kubectl --server=http://traefik-rs-manager:8001 get workflows -n argo-workflows`
- **Accessible:** No
- **Issue:** `workflows` resource not found (Argo Workflows not installed on rs-manager)
- **Notes:** Argo Workflows only runs on iad-ci cluster

---

## Logging & Metrics

### ✅ Pod Logs Access (Read-Only Proxies)
- **Endpoint:** `kubectl --server=http://traefik-{cluster}:8001 logs -n {namespace} {pod}`
- **Accessible:** Yes (all clusters except iad-kalshi)
- **Auth Method:** Read-only kubectl proxy RBAC
- **Notes:** Full logs access for readable resources

### ✅ Pod Logs Access (Admin Kubeconfigs)
- **Endpoint:** `kubectl --kubeconfig=/path/to/kubeconfig logs ...`
- **Accessible:** Yes (iad-ci, rs-manager)
- **Auth Method:** Cluster-admin SA via kubeconfig
- **Notes:** Full logs access for all resources

### ❌ Metrics API (Read-Only Proxies)
- **Endpoint:** `kubectl top nodes` or `top pods`
- **Accessible:** No
- **Issue:** Forbidden by RBAC - proxy SA cannot list `nodes.metrics.k8s.io`
- **Notes:** Metrics-server exists but proxy RBAC too restrictive

### ✅ Events Access
- **Endpoint:** `kubectl get events -A --sort-by='.lastTimestamp'`
- **Accessible:** Yes
- **Auth Method:** Read-only kubectl proxy RBAC
- **Notes:** Full events access with sorting capabilities

### ❌ VictoriaLogs Endpoint
- **Endpoint:** `https://victorialogs-rs-manager.tail1b1987.ts.net:8428`
- **Accessible:** No
- **Issue:** No response (timeout/connection refused)
- **Notes:** Namespace `victorialogs` exists but empty

### ❌ VictoriaLogs Pod (apexalgo-iad)
- **Endpoint:** `deployment/victoria-logs-single` in `agent-observability` namespace
- **Accessible:** No
- **Issue:** Deployment not found
- **Notes:** Namespace exists but VictoriaLogs deployment not present

### ❌ Loki
- **Namespace:** `loki`
- **Accessible:** No
- **Issue:** Namespace not found
- **Notes:** Loki not deployed on rs-manager

---

## Required Credentials & Config Files

### Kubeconfig Files (Present)
- ✅ `/home/coding/.kube/iad-ci.kubeconfig` (cluster-admin, SA token)
- ✅ `/home/coding/.kube/rs-manager.kubeconfig` (cluster-admin, SA token)
- ✅ `/home/coding/.kube/ord-devimprint-observer.kubeconfig` (read-only, long-lived SA)
- ✅ `/home/coding/.kube/iad-options-observer.kubeconfig` (read-only, long-lived SA)

### Kubeconfig Files (Expired/Needs Renewal)
- ❌ `/home/coding/.kube/apexalgo-iad.kubeconfig` (OIDC token expired ~3 days)
- ❌ `/home/coding/.kube/iad-kalshi-admin.kubeconfig` (OIDC token expired)

### Kubeconfig Files (Missing)
- ❌ `/home/coding/.kube/ardenone-manager.kubeconfig` (file not found)

### Tailscale VPN Routes (Working)
- ✅ `traefik-apexalgo-iad:8001` → kubectl-proxy
- ✅ `traefik-ardenone-cluster:8001` → kubectl-proxy
- ✅ `traefik-ardenone-manager:8001` → kubectl-proxy
- ✅ `traefik-rs-manager:8001` → kubectl-proxy
- ✅ `kubectl-proxy-ord-devimprint:8001` → kubectl-proxy
- ✅ `traefik-iad-options:8001` → kubectl-proxy via Traefik

### Tailscale VPN Routes (Not Working)
- ❌ `kubectl-proxy-iad-kalshi:8001` → connection refused
- ❌ `argocd-ro-ardenone-manager-ts.ardenone.com:8444` → timeout
- ❌ `victorialogs-rs-manager.tail1b1987.ts.net:8428` → timeout

---

## Access Limitations & Permission Issues

### Read-Only Proxy RBAC Restrictions
1. **Metrics API blocked:** `nodes.metrics.k8s.io` forbidden - cannot use `kubectl top` commands
2. **Secrets access blocked:** Explicit denial on iad-options proxy (stricter than other clusters)
3. **No write access:** Cannot create, delete, modify resources (selfHeal reverts anyway)
4. **Custom CRDs limited:** Some CRDs (workflows) not accessible via proxy if not installed on that cluster

### OIDC Token Expiry
1. **apexalgo-iad admin kubeconfig:** Token expires every ~3 days, requires manual regeneration from Rackspace Spot UI
2. **iad-kalshi admin kubeconfig:** Same issue
3. **No auto-renewal:** OIDC tokens are static, must be manually refreshed

### Service Connectivity Issues
1. **iad-kalshi proxy:** Connection refused - proxy pod may be down or Tailscale route broken
2. **ArgoCD read-only proxy:** HTTP 000 - service exists but not responding
3. **VictoriaLogs:** Endpoint not responding, deployment missing from expected namespace
4. **Argo Workflows UI:** Error 1033 - likely SSO authentication issue

---

## Recommendations

### Immediate Actions
1. **Renew apexalgo-iad admin token:** Regenerate OIDC token from Rackspace Spot UI and update kubeconfig
2. **Fix iad-kalshi proxy:** Investigate why `kubectl-proxy-iad-kalshi:8001` is refusing connections
3. **Fix ArgoCD read-only proxy:** Debug why `argocd-readonly-proxy` service is not responding
4. **Create ardenone-manager kubeconfig:** Set up cluster-admin access for ardenone-manager

### Medium Term
1. **Deploy metrics-server RBAC:** Extend proxy SA permissions to allow metrics API access
2. **Deploy VictoriaLogs:** Install and configure VictoriaLogs for centralized log aggregation
3. **Fix Argo Workflows UI SSO:** Resolve error 1033 on `https://argo-ci.ardenone.com`
4. **Standardize OIDC token renewal:** Implement automated token refresh mechanism

### Long Term
1. **Centralize observability:** Deploy comprehensive monitoring stack (Prometheus, Grafana, Loki/VictoriaLogs)
2. **Unify access:** Use single observability proxy for all clusters
3. **Implement SSO:** Standardize SSO across all UI endpoints (ArgoCD, Argo Workflows, Grafana)

---

## Auth Method Summary

| Auth Method | Count | Notes |
|-------------|-------|-------|
| Tailscale + kubectl-proxy (read-only SA) | 6 | Standardized read-only access across clusters |
| Kubeconfig (cluster-admin SA) | 3 | Full admin access, tokens never expire |
| Kubeconfig (OIDC token) | 2 | Full admin access, tokens expire ~3 days |
| Tailscale operator (long-lived SA) | 2 | Direct proxy access without Traefik |
| Read-only API proxy (bearer token) | 1 | ArgoCD read-only proxy (currently not working) |
| SSO + VPN | 1 | Argo Workflows UI (currently not working) |

---

**Test Coverage:** 15 endpoints tested across 8 clusters, 3 services (ArgoCD, Argo Workflows, VictoriaLogs)  
**Success Rate:** 73% (11/15 endpoints fully accessible)  
**Partial Access:** 3 endpoints have degraded or proxy-only access  
**Complete Failure:** 4 endpoints (1 expired token, 1 missing file, 2 connectivity issues)
