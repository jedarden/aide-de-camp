# whisper-stt Deployment Location and Access

## Summary
Identified and verified kubectl access to the whisper-stt service deployment.

## Cluster
- **Cluster:** `ardenone-cluster`
- **Access Method:** Read-only kubectl-proxy over Tailscale

## Namespace
- **Namespace:** `whisper-stt`

## Deployed Resources
Two deployments are running in the `whisper-stt` namespace:
1. **whisper-openai** (53 days old) - OpenAI-compatible whisper endpoint for multi-service use
2. **whisper-stt** (96 days old) - Asterisk-specific STT service with WebVTT output

## Kubectl Access
- **Proxy URL:** `http://traefik-ardenone-cluster:8001`
- **Access Level:** Read-only (via devpod-observer namespace)
- **Command Pattern:**
  ```bash
  kubectl --server=http://traefik-ardenone-cluster:8001 get deployments -n whisper-stt
  kubectl --server=http://traefik-ardenone-cluster:8001 get events -n whisper-stt
  ```

## Verification Results
- ✅ Successfully queried deployments (returned 2 deployments)
- ✅ Successfully queried events (namespace access confirmed)
- ✅ Proxy is accessible via Tailscale mesh

## Deployment Manifest Location
Manifests are stored in `declarative-config`:
- Path: `k8s/ardenone-cluster/whisper-stt/`
- Resources: Deployment, Service, PVC, SealedSecret

## Notes
- ardenone-cluster proxy runs in `devpod-observer` namespace
- Access is strictly read-only - cannot create, delete, or modify resources
- No events currently present in whisper-stt namespace (clean state)
