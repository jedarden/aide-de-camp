# Deployment Locations for pbx-web and whisper-stt

## pbx-web
- **Cluster:** ardenone-manager
- **Namespace:** pbx-web
- **Deployments:**
  - pbx-web (main service)
  - lab-rebuild-relay
  - pbx-rebuild-relay

## whisper-stt
- **Cluster:** ardenone-manager
- **Namespace:** whisper-stt
- **Deployments:**
  - whisper-stt (main service)
  - whisper-openai

## Verification
Both services were also found in rs-manager cluster but with 0/1 replicas (not running).

## Discovery Method
Used kubectl via Tailscale proxy endpoints:
```bash
kubectl --server=http://traefik-ardenone-manager:8001 get deployments -A | grep -E "(pbx-web|whisper-stt)"
```

## Date
2026-08-06
