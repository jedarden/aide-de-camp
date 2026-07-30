# Cluster Identification for pbx-web and whisper-stt

## Summary
Both pbx-web and whisper-stt services are hosted on **ardenone-cluster**.

## 30-Day Window
- **Start Date:** 2026-06-24
- **End Date:** 2026-07-24
- **Calculation:** Current date (2026-07-24) minus 30 days

## Service Details

### pbx-web
- **Cluster:** ardenone-cluster
- **Namespace:** pbx-web
- **Kubectl Access:** `kubectl --server=http://traefik-ardenone-cluster:8001 -n pbx-web get pods`
- **Access Type:** Read-only via kubectl-proxy

### whisper-stt
- **Cluster:** ardenone-cluster
- **Namespace:** whisper-stt  
- **Kubectl Access:** `kubectl --server=http://traefik-ardenone-cluster:8001 -n whisper-stt get pods`
- **Access Type:** Read-only via kubectl-proxy

## Cluster Access Method
- **Proxy Endpoint:** `http://traefik-ardenone-cluster:8001`
- **Routing:** Traefik kubectl-tcp entrypoint on Tailscale mesh
- **Auth:** Read-only (devpod-observer namespace with RBAC)

## Configuration Locations
- pbx-web: `~/declarative-config/k8s/ardenone-cluster/pbx-web/`
- whisper-stt: `~/declarative-config/k8s/ardenone-cluster/whisper-stt/`

## Next Steps
Use this cluster information to extract logs from both services for the 30-day window using kubectl logs commands with appropriate time filters.
