# ZAI Proxy Deployment Alternatives Research

**Date:** 2026-07-24  
**Task:** adc-3l20u  
**Status:** Research complete — no implementation changes

## Current Deployment

### Location
- **Cluster:** apexalgo-iad (Rackspace Spot, us-east-iad-1)
- **Namespace:** mcp
- **Endpoint:** `https://zai-proxy-mcp-apexalgo-iad-ts.ardenone.com:8444/v1/messages`
- **Image:** `ronaldraygun/zai-proxy:1.9.0`
- **Resources:** 10m-100m CPU, 32Mi-64Mi RAM
- **Ingress:** Traefik IngressRoute on "vpn" entrypoint

### Network Path (Current)
```
lab (Hetzner EX44, aide-de-camp host)
  → Tailscale VPN (100.81.129.38)
  → apexalgo-iad Tailscale ingress
  → zai-proxy pod (10.20.208.233)
  → ZAI API (upstream)
```

### Baseline Latency
- **Lab → apexalgo-iad proxy:** ~333ms (via Tailscale VPN + public internet)
- **Lab → ardenone-manager node:** ~0.3ms (same LAN)

---

## Deployment Alternatives

### Option 1: Local Deployment on lab

#### Feasibility: **HIGH**

**Description:** Run zai-proxy as a Docker container directly on the Hetzner server (lab).

**Pros:**
- **Minimal latency:** Zero network hops to proxy (localhost)
- **Simplest architecture:** No Kubernetes overhead for this service
- **Easy development:** Can test proxy changes quickly
- **Resource isolation:** Runs alongside aide-de-camp on same host

**Cons:**
- **Management burden:** No ArgoCD sync, manual deployment
- **Monitoring gap:** Not integrated with existing Prometheus/Grafana stack
- **Secrets management:** ZAI_API_KEY must be managed outside sealed-secrets
- **Single point of failure:** No pod replication/restart automation

**Network path:**
```
lab (aide-de-camp) → localhost:8080 → ZAI API
```

**Implementation:**
```bash
# Run via Docker
docker run -d \
  -p 8080:8080 \
  -e ZAI_API_KEY="$ZAI_API_KEY" \
  -e MAX_WORKERS=100 \
  -e RATE_LIMIT_INITIAL=8 \
  -e RATE_LIMIT_MAX=40 \
  -e TOKEN_COUNTING_ENABLED=true \
  -e TOKENIZER_MODEL=glm-4 \
  --name zai-proxy \
  ronaldraygun/zai-proxy:1.9.0
```

**Service file (systemd):**
```ini
[Unit]
Description=ZAI Proxy
After=network.target

[Service]
Type=simple
ExecStart=/home/coding/.nix-profile/bin/docker run --rm -p 8080:8080 \
  -e ZAI_API_KEY=${ZAI_API_KEY} \
  -e MAX_WORKERS=100 \
  -e RATE_LIMIT_INITIAL=8 \
  -e RATE_LIMIT_MAX=40 \
  -e TOKEN_COUNTING_ENABLED=true \
  -e TOKENIZER_MODEL=glm-4 \
  ronaldraygun/zai-proxy:1.9.0
Restart=always

[Install]
WantedBy=multi-user.target
```

---

### Option 2: ardenone-manager Cluster (Same LAN)

#### Feasibility: **HIGH**

**Description:** Deploy zai-proxy to ardenone-manager cluster (k3s on same Hetnzer server).

**Pros:**
- **Excellent latency:** ~0.3ms over LAN (1000× faster than current)
- **ArgoCD integration:** Declarative deployment, auto-sync
- **Monitoring integration:** Existing Prometheus/Grafana stack
- **Secrets management:** SealedSecrets support
- **Resilience:** Pod restart via k3s, health checks
- **VPN exposure:** Already has Traefik with "vpn" entrypoint

**Cons:**
- **Cluster resource usage:** Adds to k3s control plane load (minimal for this pod)
- **Namespace creation:** Need to create mcp namespace or use existing

**Network path:**
```
lab (aide-de-camp)
  → LAN (10.20.23.202 → 10.20.23.100)
  → ardenone-manager Traefik (VPN entrypoint)
  → zai-proxy pod
  → ZAI API
```

**Implementation:**
- Copy existing config from apexalgo-iad
- Create mcp namespace on ardenone-manager
- Deploy zai-proxy.yml + zai-proxy-vpn-ingressroute.yml
- Use existing zai-api-key secret or create new

**Latency estimate:** ~1-2ms total (LAN + Traefik + proxy overhead)

---

### Option 3: apexalgo-iad Cluster (Status Quo)

#### Feasibility: **CURRENT STATE**

**Description:** Continue running on apexalgo-iad.

**Pros:**
- **Already deployed:** Zero migration effort
- **MCP namespace:** Co-located with other MCP tools
- **Mature setup:** Monitoring, dashboards, HPA configured

**Cons:**
- **High latency:** ~333ms via Tailscale + public internet
- **Dependency:** Relies on external Rackspace Spot cluster
- **Network complexity:** Multi-hop VPN path

**When to keep:** If latency is not a critical concern for aide-de-camp use cases.

---

### Option 4: rs-manager Cluster

#### Feasibility: **MEDIUM**

**Description:** Deploy to rs-manager (Rackspace Spot, us-east-iad-1).

**Pros:**
- **ArgoCD integration:** Declarative deployment
- **Same region as apexalgo-iad:** Consistent with existing pattern
- **Traefik available:** Has ingress capability

**Cons:**
- **No latency improvement:** Still public internet hop (~300ms)
- **Cluster already busy:** CI/CD cluster, adds another workload
- **No zai-api-key secret:** Would need to create

**Verdict:** Not recommended — no benefit over apexalgo-iad.

---

### Option 5: iad-options Cluster

#### Feasibility: **MEDIUM**

**Description:** Deploy to iad-options (Rackspace Spot, us-east-iad-1).

**Pros:**
- **Newer cluster:** Clean slate for deployment
- **ArgoCD integration:** Declarative deployment

**Cons:**
- **No latency improvement:** Still public internet hop (~300ms)
- **No zai-api-key secret:** Would need to create
- **No Traefik VPN:** Would need to configure ingress

**Verdict:** Not recommended — no benefit over apexalgo-iad.

---

## Recommendation

### Primary: **ardenone-manager (Option 2)**

**Rationale:**
1. **Massive latency reduction:** 333ms → 1-2ms (99% improvement)
2. **Operational excellence:** ArgoCD, monitoring, health checks
3. **Same LAN:** Eliminates public internet dependency
4. **Low risk:** Small pod (32Mi-64Mi), well-tested image

### Secondary: **Local Docker (Option 1)**

**Use when:**
- Testing proxy changes quickly
- Development environment
- Temporary fallback during cluster migration

### Not Recommended: **apexalgo-iad status quo (Option 3)**

Only keep if:
- Latency is not a concern
- Migration effort is unacceptable

---

## Network Path Comparison

| Option | Hops | Path | Latency |
|--------|------|------|---------|
| Local (Docker) | 1 | localhost → ZAI API | <1ms |
| ardenone-manager | 3 | lab → LAN → Traefik → pod → ZAI API | ~1-2ms |
| apexalgo-iad (current) | 5+ | lab → Tailscale → public internet → VPN → Traefik → pod → ZAI API | ~333ms |
| rs-manager | 5+ | Same as apexalgo-iad | ~300ms |
| iad-options | 5+ | Same as apexalgo-iad | ~300ms |

---

## Migration Path (ardenone-manager)

### Phase 1: Prep
```bash
# Create namespace on ardenone-manager
kubectl --kubeconfig=/home/coding/.kube/ardenone-manager.kubeconfig \
  create namespace mcp

# Copy secret (or create new sealed secret)
kubectl --server=http://traefik-ardenone-manager:8001 \
  get secret zai-api-key -n mcp -o yaml \
  --context=apexalgo-iad > /tmp/zai-api-key.yaml
```

### Phase 2: Deploy
```bash
# Apply to declarative-config
cp ~/declarative-config/k8s/apexalgo-iad/mcp/zai-proxy.yml \
   ~/declarative-config/k8s/ardenone-cluster/mcp/zai-proxy.yml

cp ~/declarative-config/k8s/apexalgo-iad/mcp/zai-proxy-vpn-ingressroute.yml \
   ~/declarative-config/k8s/ardenone-cluster/mcp/zai-proxy-vpn-ingressroute.yml

# Update hostname in ingressroute
# OLD: zai-proxy-mcp-apexalgo-iad-ts.ardenone.com
# NEW: zai-proxy-mcp-ardenone-manager-ts.ardenone.com
```

### Phase 3: Validate
```bash
# Health check
curl -sk https://zai-proxy-mcp-ardenone-manager-ts.ardenone.com:8444/health

# Compare latency
time curl -sk https://zai-proxy-mcp-ardenone-manager-ts.ardenone.com:8444/health
```

### Phase 4: Switch aide-de-camp
```bash
# Update env var or .env
ZAI_PROXY_URL=https://zai-proxy-mcp-ardenone-manager-ts.ardenone.com:8444/v1/messages

# Restart aide-de-camp
kill -2 $(ps aux | grep "uvicorn src.main" | grep -v grep | awk '{print $2}')
nohup .venv/bin/python -m uvicorn src.main:app --host 0.0.0.0 --port 8000 > /tmp/adc.log 2>&1 &
```

---

## Risk Assessment

| Option | Migration Risk | Operational Risk | Rollback |
|--------|---------------|------------------|----------|
| Local Docker | Low | Medium (manual ops) | Trivial |
| ardenone-manager | Medium | Low | Easy (kubectl) |
| apexalgo-iad (stay) | None | Medium (external cluster) | N/A |

---

## Notes

- ardenone-manager already runs Traefik with "vpn" entrypoint
- Existing VPN wildcard TLS cert can be reused
- ardenone-cluster has existing zai-proxy configs (scaled to 0, but can be updated)
- All clusters except ardenone-manager are Rackspace Spot (external)
- ardenone-manager is k3s on same physical server as aide-de-camp

---

## Next Steps (If Approved)

1. Create mcp namespace on ardenone-manager
2. Copy zai-api-key secret (or create new sealed secret)
3. Add zai-proxy manifests to declarative-config for ardenone-cluster/mcp
4. Deploy via ArgoCD (ardenone-manager syncs from declarative-config)
5. Validate health and latency
6. Update aide-de-camp ZAI_PROXY_URL
7. Monitor for 24h, then decommission apexalgo-iad deployment
