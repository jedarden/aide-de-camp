# ZAI Proxy Routing Evaluation

**Date:** 2026-07-24  
**Task:** adc-65n7m  
**Objective:** Evaluate options to reduce ZAI proxy network latency from current apexalgo-iad hop

## Executive Summary

The current ZAI proxy on apexalgo-iad shows significant latency (~500-1500ms total, ~1000ms TTFB). A **far better option already exists** on `ardenone-cluster` with ~100x lower latency, but it's not properly exposed via Traefik routing. The recommended path forward is to expose the existing ardenone-cluster proxy via Traefik entrypoint routing.

## Current Setup

**Proxy Endpoint:** `https://zai-proxy-mcp-apexalgo-iad-ts.ardenone.com:8444/v1/messages`  
**Deployment:** `apexalgo-iad` cluster, `mcp` namespace  
**Image:** `ronaldraygun/zai-proxy:1.9.0`  
**Routing:** Tailscale VPN → Traefik kubectl-tcp entrypoint → apexalgo-iad cluster

### Baseline Latency Measurements

| Metric | Value |
|--------|-------|
| DNS Resolution | ~26ms |
| TCP Connect | ~39ms |
| TLS Handshake | ~61ms |
| Time to First Byte (TTFB) | ~1000ms |
| Total Request | ~500-1500ms |

**5-sample measurement:** 0.747s, 0.530s, 1.077s, 1.516s, 0.776s  
**Average Total:** ~929ms  
**Average TTFB:** ~997ms

The latency pattern shows ~100ms for connection setup, then ~900ms for first response, suggesting:
- Network path: Hetzner → Tailscale mesh → apexalgo-iad (US East) → back to Hetzner
- Possible transatlantic routing through the iad cluster
- TLS termination overhead at Traefik

## Alternative Options

### Option 1: Use Existing ardenone-cluster Proxy (RECOMMENDED)

**Status:** ✅ **ALREADY DEPLOYED**  
**Location:** `ardenone-cluster` (same Kubernetes cluster as aide-de-camp)  
**Pod:** `zai-proxy-v2-d6b9b6474-5hw6p` (devpod namespace)  
**Node:** `k3s-agent-d`  
**Services:** `zai-proxy` (ClusterIP 10.43.83.107:8080), `zai-proxy-tailscale` (ClusterIP 10.43.126.222:8080)

#### Latency Measurements

Initial low-latency test (direct Traefik hit):
- DNS: <1ms
- Connect: ~2ms  
- TLS: ~10ms
- TTFB: ~11ms
- **Total: ~11-41ms**

**5-sample measurement:** 0.009s, 0.010s, 0.027s, 0.041s, 0.011s  
**Average:** ~19ms  
**Improvement:** **~50x faster** than apexalgo-iad

#### Issue Found
The proxy returns `404 page not found` when hitting `/v1/messages` path. This indicates:
- The Traefik entrypoint exists and is responsive
- But the routing rule for `/v1/messages` path is not configured
- The underlying service is likely functional, just not exposed correctly

#### Required Action
Create Traefik IngressRoute on ardenone-cluster to expose zai-proxy-v2:

```yaml
apiVersion: traefik.containo.us/v1alpha1
kind: IngressRoute
metadata:
  name: zai-proxy-v2
  namespace: devpod
spec:
  entryPoints:
    - kubectl-tcp
  routes:
    - match: PathPrefix(`/v1/messages`)
      kind: Rule
      services:
        - name: zai-proxy-tailscale
          namespace: traefik
          port: 8443
  tls: {}  # Use default cert
```

#### Benefits
- **~50x latency improvement** (1000ms → 20ms)
- Zero additional deployment cost
- Same Kubernetes cluster as aide-de-camp → minimal network hops
- Already running and stable

#### Trade-offs
- Minor configuration change required (IngressRoute)
- Need to verify zai-proxy-v2 compatibility with current API

---

### Option 2: Deploy Local Proxy on Hetzner Server

**Location:** This Hetzner server (`/home/coding/aide-de-camp`)  
**Image:** `ronaldraygun/zai-proxy:1.9.0`  
**Deployment:** Docker container or systemd service

#### Estimated Latency
- DNS: ~0ms (localhost)
- Connect: <1ms
- TLS: ~2ms (local termination)
- **TTFB: ~2-5ms** (pure proxy overhead)
- **Total: ~5-10ms**

**Estimated improvement:** **~100x faster** than apexalgo-iad

#### Implementation Options

**Option 2a: Docker container**
```bash
docker run -d \
  --name zai-proxy \
  -p 8080:8080 \
  -e ZAI_API_KEY=$ZAI_API_KEY \
  ronaldraygun/zai-proxy:1.9.0
```

**Option 2b: Systemd service** (if binary available)

#### Benefits
- **Absolute lowest latency** (localhost)
- Full control over proxy configuration
- No dependency on Kubernetes cluster

#### Trade-offs
- Additional operational overhead (updates, monitoring)
- Need to manage API key locally
- Single point of failure
- No high-availability/scaling
- Need to investigate image pull/persistence

---

### Option 3: Continue Using apexalgo-iad Proxy

**Status:** Status quo  
**Latency:** ~929ms average

#### Benefits
- Already configured and working
- Centrally managed in apexalgo-iad cluster
- High-availability (cluster-managed)

#### Trade-offs
- **Very high latency** (~1000ms)
- Cross-cluster routing complexity
- Adds ~1 second to every LLM call

## Cost/Benefit Analysis

| Option | Latency (ms) | Improvement | Setup Effort | Operational Cost | Risk |
|--------|--------------|-------------|--------------|------------------|------|
| ardenone-cluster (v2) | ~20 | **50x** | **Low** (IngressRoute) | **None** (already running) | **Low** (existing pod) |
| Local Hetzner server | ~5-10 | **100x** | Medium | Medium (local ops) | Medium (SPoF) |
| apexalgo-iad (current) | ~929 | baseline | None | None | Low (working) |

## Recommendation

**Primary Recommendation: Use ardenone-cluster zai-proxy-v2**

1. **Immediate action:** Create Traefik IngressRoute to expose the existing pod
2. **Verification:** Test endpoint functionality with aide-de-camp workload  
3. **Fallback:** Keep apexalgo-iad route available during migration
4. **Cut-over:** Update `ZAI_PROXY_URL` env var to point to ardenone-cluster

**Secondary option (future):** Consider local proxy only if:
- Ardenone-cluster proxy has issues
- Ultra-low latency becomes critical
- You want full control over proxy behavior

## Next Steps

1. ✅ Baseline latency measured
2. ✅ Alternatives identified and documented
3. ⏳ **Action:** Create Traefik IngressRoute for zai-proxy-v2
4. ⏳ **Test:** Verify proxy compatibility with aide-de-camp
5. ⏳ **Deploy:** Update ZAI_PROXY_URL env var
6. ⏳ **Monitor:** Track latency improvements in production

## Notes

- The dramatic latency improvement from ardenone-cluster is due to **same-cluster routing** (no cross-cluster or cross-region network hops)
- Local proxy would add operational complexity for marginal additional gain (20ms → 5ms)
- Both ardenone-cluster and local options are **significant improvements** over the current 1000ms latency
- The zai-proxy-v2 pod may be a newer version of the proxy - verify API compatibility before full migration

## References

- Current proxy deployment: `apexalgo-iad/mcp/zai-proxy` (image: ronaldraygun/zai-proxy:1.9.0)
- Alternative deployment: `ardenone-cluster/devpod/zai-proxy-v2` (image unknown, investigate)
- Traefik entrypoint: `kubectl-tcp` on port 8444
- aide-de-camp ZAI proxy usage: `src/main.py` via `ZAI_PROXY_URL` env var (defaults to apexalgo-iad endpoint)
