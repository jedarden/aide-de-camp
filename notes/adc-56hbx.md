# Kubectl Context and Namespace Identification

## Summary

Investigated kubectl context and namespace for pod deletion operation. Identified authentication issues and access limitations.

## Current Configuration

### Active Context
- **Context name**: `apexalgo-iad-kalshi`
- **Cluster**: `iad-kalshi` (Rackspace Spot cluster in us-east-iad-1)
- **Namespace**: `default`
- **User**: `ngpc-user`

### Kubeconfig Files
- `~/.kube/iad-kalshi-admin.kubeconfig` (exists, but token appears expired)
- `~/.kube/iad-kalshi.kubeconfig` (exists, older version)

## Access Method Issues

### Direct Kubeconfig Status
❌ **Authentication failed** - Both kubeconfig files show:
```
error: You must be logged in to the server (Unauthorized)
```

The OIDC tokens in these kubeconfigs appear to be expired. According to CLAUDE.md, OIDC tokens for Rackspace Spot clusters expire every ~3 days and need to be regenerated from the Spot UI.

### Proxy Access Status
✅ **Proxy is accessible** - Read-only proxy at `http://kubectl-proxy-iad-kalshi:8001` works correctly

❌ **Permission denied** - Proxy access is **read-only**:
```bash
kubectl --server=http://kubectl-proxy-iad-kalshi:8001 auth can-i delete pods -n default
# Result: no
```

## Critical Finding

**iad-kalshi cluster cannot be used for pod deletion.** The cluster only provides:
- Read-only access via Tailscale proxy (recommended method)
- Admin access with expired tokens that require regeneration from Rackspace Spot UI

## Pod Deletion Requirements

For pod deletion operations, one of the following clusters with admin/write access must be used instead:

1. **apexalgo-iad** - Admin kubeconfig at `~/.kube/apexalgo-iad.kubeconfig` (cloudspace-admin OIDC token, may need refresh)
2. **ardenone-manager** - Admin kubeconfig at `~/.kube/ardenone-manager.kubeconfig` (cluster-admin access)
3. **rs-manager** - Admin kubeconfig at `~/.kube/rs-manager.kubeconfig` (cluster-admin access)
4. **iad-ci** - Admin kubeconfig at `~/.kube/iad-ci.kubeconfig` (cluster-admin access)

## Recommendations

1. **For immediate pod deletion**: Switch to a cluster with active admin access (likely `rs-manager` or `ardenone-manager`)
2. **For iad-kalshi admin access**: Regenerate the OIDC token from the Rackspace Spot UI and update the kubeconfig
3. **Verify target pod location**: Confirm which cluster actually hosts the pod that needs deletion before proceeding

## Next Steps

1. Identify which cluster hosts the target pod
2. Switch to that cluster's admin context: `kubectl --kubeconfig=/path/to/admin.kubeconfig`
3. Verify permissions: `kubectl auth can-i delete pods -n <namespace>`
4. Proceed with deletion only after confirming write access

## Cluster Reference (from CLAUDE.md)

| Cluster | Admin Access | Read-Only Proxy | Notes |
|---------|--------------|------------------|-------|
| iad-kalshi | OIDC token (expired) | `kubectl-proxy-iad-kalshi:8001` | Read-only via proxy |
| rs-manager | `~/.kube/rs-manager.kubeconfig` | `traefik-rs-manager:8001` | Manages iad-ci |
| ardenone-manager | `~/.kube/ardenone-manager.kubeconfig` | `traefik-ardenone-manager:8001` | ArgoCD host |
| apexalgo-iad | `~/.kube/apexalgo-iad.kubeconfig` | `traefik-apexalgo-iad:8001` | OIDC token expires ~3 days |
| iad-ci | `~/.kube/iad-ci.kubeconfig` | N/A | CI/CD cluster |
