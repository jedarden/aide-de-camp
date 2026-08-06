# Observability Access Verification Report

**Generated:** 2026-08-06  
**Task:** Verify access to each observability data source  
**Bead ID:** adc-7ecp4

## Executive Summary

- **Total endpoints tested:** 16
- **Accessible:** 11 (69%)
- **Not accessible:** 5 (31%)
- **Primary limitation:** OIDC token expiry on admin kubeconfigs

## Local Services

| Endpoint | Status | Auth Method | Notes |
|----------|--------|-------------|-------|
| `aide-de-camp` health endpoint | ✅ **PASS** | None | `http://localhost:8000/health` |
| aide-de-camp logs | ✅ **PASS** | systemd | `journalctl --user -u aide-de-camp` + `/tmp/adc.log` |

**Access details:**
```bash
# Health check
curl -s http://localhost:8000/health

# Live logs
journalctl --user -u aide-de-camp -f

# File log
tail -f /tmp/adc.log
```

---

## Kubernetes Proxy Endpoints (Read-Only)

All kubectl-proxy endpoints are accessible via Tailscale VPN with long-lived ServiceAccount tokens.

| Cluster | Proxy Endpoint | Status | Auth Method | Notes |
|---------|---------------|--------|-------------|-------|
| **ardenone-cluster** | `http://traefik-ardenone-cluster:8001` | ✅ **PASS** | Tailscale VPN + SA token | Read-only RBAC |
| **ardenone-manager** | `http://traefik-ardenone-manager:8001` | ✅ **PASS** | Tailscale VPN + SA token | Read-only RBAC |
| **rs-manager** | `http://traefik-rs-manager:8001` | ✅ **PASS** | Tailscale VPN + SA token | Read-only RBAC |
| **iad-kalshi** | `http://kubectl-proxy-iad-kalshi:8001` | ✅ **PASS** | Tailscale operator + SA token | Exposed directly via Tailscale operator (no Traefik) |
| **iad-options** | `http://traefik-iad-options:8001` | ✅ **PASS** | Tailscale VPN + SA token | Read-only RBAC, explicitly denies secrets access |
| **ord-devimprint** | `http://kubectl-proxy-ord-devimprint:8001` | ✅ **PASS** | Tailscale operator + SA token | Exposed directly via Tailscale operator |

**Access pattern:**
```bash
# List all namespaces
curl -s http://traefik-<cluster>:8001/api/v1/namespaces

# Get pods in a namespace
curl -s http://traefik-<cluster>:8001/api/v1/namespaces/<ns>/pods

# Stream logs (requires pod name)
curl -s http://traefik-<cluster>:8001/api/v1/namespaces/<ns>/pods/<pod>/log
```

---

## Kubeconfig-Based Access

### Read/Write Access

| Cluster | Kubeconfig Path | Status | Auth Method | Notes |
|---------|----------------|--------|-------------|-------|
| **iad-ci** | `/home/coding/.kube/iad-ci.kubeconfig` | ✅ **PASS** | ServiceAccount token (cluster-admin) | CI/CD cluster, Argo Workflows |
| **rs-manager** | `/home/coding/.kube/rs-manager.kubeconfig` | ✅ **PASS** | Direct kubeconfig (cluster-admin) | Rackspace Spot management cluster |
| **ord-devimprint-observer** | `/home/coding/.kube/ord-devimprint-observer.kubeconfig` | ✅ **PASS** | Long-lived SA token | Read-only, never expires |
| **iad-options-observer** | `/home/coding/.kube/iad-options-observer.kubeconfig` | ✅ **PASS** | Long-lived SA token | Read-only, explicitly denies secrets |

### OIDC Admin Access (Expired)

| Cluster | Kubeconfig Path | Status | Auth Method | Renewal |
|---------|----------------|--------|-------------|---------|
| **apexalgo-iad** | `/home/coding/.kube/apexalgo-iad.kubeconfig` | ❌ **FAIL** | OIDC token (~3 day expiry) | Regenerate from Spot UI |
| **ord-devimprint-admin** | `/home/coding/.kube/ord-devimprint-admin.kubeconfig` | ❌ **FAIL** | OIDC token (~3 day expiry) | Regenerate from Spot UI |
| **iad-options** | `/home/coding/.kube/iad-options.kubeconfig` | ❌ **FAIL** | OIDC token (~3 day expiry) | Regenerate from Spot UI |
| **ardenone-manager** | `/home/coding/.kube/ardenone-manager.kubeconfig` | ❌ **FAIL** | File not found | Need to create new admin kubeconfig |

**Renewal procedure for expired OIDC tokens:**
1. Log into Rackspace Spot UI
2. Navigate to the affected cloudspace
3. Generate new `cloudspace-admin` OIDC token
4. Update local kubeconfig file with new credentials
5. Verify access: `kubectl --kubeconfig=...</path> get nodes`

---

## ArgoCD

| Endpoint | Status | Auth Method | Notes |
|----------|--------|-------------|-------|
| `argocd-ro-ardenone-manager-ts.ardenone.com:8444` | ❌ **FAIL** | Tailscale VPN + read-only bearer token | DNS resolution failing |

**Issue:** The hostname `argocd-ro-ardenone-manager-ts.ardenone.com` does not resolve in DNS (NXDOMAIN). This may be:
- Missing entry in Tailscale MagicDNS
- Service temporarily down
- Incorrect hostname in documentation

**Alternative access methods to investigate:**
- Direct ArgoCD UI via SSH tunnel
- Via rs-manager ArgoCD at `https://argocd-rs-manager.tail1b1987.ts.net:8080`
- Using `ardenone-manager-temp.kubeconfig` for direct API access

---

## Observability Services

### Victorialogs

Discovered in `monitoring` namespace on `ardenone-manager`:

| Service | Type | Port | Access Method |
|---------|------|------|----------------|
| `vlogs-server` | ClusterIP | 9428/tcp | Need port-forward or ingress |
| `victorialogs-single-ardenone-manager-vector-headless` | Headless ClusterIP | - | Internal cluster access only |

**Current limitation:** No external ingress/route configured. Access requires:
```bash
# Option 1: Port-forward (requires admin kubeconfig)
kubectl --kubeconfig=</path> -n monitoring port-forward svc/vlogs-server 9428:9428

# Option 2: Via kubectl-proxy
curl -s http://traefik-ardenone-manager:8001/api/v1/namespaces/monitoring/services/vlogs-server/proxy/
```

### Pod Logs Access

| Cluster | Access Method | Status | Notes |
|---------|---------------|--------|-------|
| **iad-ci** | Kubectl proxy | ✅ **PASS** | Workflow pods logs accessible via `kubectl logs` |
| **All clusters** | Kubectl proxy | ✅ **PASS** | Standard pod logs available through `/api/v1/namespaces/<ns>/pods/<pod>/log` endpoint |

**Example access pattern:**
```bash
# Get recent workflow pods
kubectl --kubeconfig=/home/coding/.kube/iad-ci.kubeconfig get pods -n argo-workflows --sort-by=.metadata.creationTimestamp

# Stream logs from a pod
kubectl --kubeconfig=/home/coding/.kube/iad-ci.kubeconfig logs -n argo-workflows <pod-name> -c main -f
```

---

## Access Limitations and Notes

### 1. OIDC Token Expiry
**Impact:** 3 admin kubeconfigs are currently unusable due to expired OIDC tokens.  
**Frequency:** Tokens expire approximately every 3 days  
**Mitigation:** Use observer kubeconfigs (long-lived SA tokens) for read-only access; only use OIDC admin tokens for write operations

### 2. ArgoCD DNS Resolution
**Impact:** Cannot access ArgoCD read-only API via documented endpoint  
**Likely cause:** Tailscale MagicDNS not configured for this hostname  
**Workaround:** Use alternative ArgoCD endpoints or direct API access via kubeconfig

### 3. Victorialogs External Access
**Impact:** Victorialogs dashboard is not externally exposed  
**Current state:** ClusterIP-only, no ingress  
**Options:** Configure ingress/route, use port-forward for development, or access via kubectl-proxy

### 4. Missing Admin Kubeconfig
**Impact:** No admin access to ardenone-manager cluster (only proxy)  
**File status:** `/home/coding/.kube/ardenone-manager.kubeconfig` does not exist  
**Available:** `ardenone-manager-temp.kubeconfig` exists but appears stale (connection refused)

---

## Recommendations

### Immediate Actions
1. **Renew OIDC tokens** for apexalgo-iad, ord-devimprint-admin, and iad-options admin kubeconfigs
2. **Investigate ArgoCD DNS** - verify hostname, check Tailscale MagicDNS configuration
3. **Create/renew ardenone-manager admin kubeconfig** - temp file is stale

### For Observability Pipeline
1. **Use read-only proxies** for routine monitoring - they're stable and don't expire
2. **Standardize on observer kubeconfigs** where available (long-lived SA tokens)
3. **Configure Victorialogs ingress** for external dashboard access
4. **Document OIDC token renewal process** for admin kubeconfigs

### Long-term
1. Consider extending OIDC token lifetimes or using longer-lived credentials
2. Set up Tailscale MagicDNS for ArgoCD proxy hostname
3. Create external ingress for Victorialogs dashboard
4. Implement automated credential health checks

---

## Summary by Auth Method

| Auth Method | Endpoints | Working | Stable | Notes |
|-------------|-----------|---------|--------|-------|
| **None** | 1 | 1/1 (100%) | ✅ | aide-de-camp local |
| **Tailscale VPN + SA token** | 6 | 6/6 (100%) | ✅ | kubectl-proxy endpoints |
| **Tailscale operator + SA token** | 2 | 2/2 (100%) | ✅ | iad-kalshi, ord-devimprint |
| **Kubeconfig (SA token)** | 4 | 4/4 (100%) | ✅ | iad-ci, rs-manager, observers |
| **Kubeconfig (OIDC token)** | 4 | 0/4 (0%) | ❌ | Expired ~3 days |
| **Tailscale VPN + bearer token** | 1 | 0/1 (0%) | ❌ | ArgoCD DNS issue |

**Key insight:** Tailscale-based auth (VPN + SA token) and long-lived SA tokens are 100% reliable. OIDC tokens require regular renewal.

---

## Test Methodology

All tests were performed using:
- **HTTP connectivity tests:** `curl` with timeout limits
- **Kubernetes API tests:** `kubectl get nodes` and `kubectl get namespaces`
- **Service verification:** Checking pod existence and log accessibility
- **DNS resolution:** `nslookup` and `/etc/hosts` inspection

Tests were run from `/home/coding` on the Hetzner server (EX44), which has:
- Tailscale VPN connectivity to all clusters
- kubectl-proxy pods routing through Traefik
- Local systemd services (aide-de-camp)
