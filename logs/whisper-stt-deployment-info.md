# Whisper-STT Deployment Information

**Generated:** 2026-08-06  
**Cluster:** ardenone-cluster (via ardenone-manager proxy)  
**Access Method:** `kubectl --server=http://traefik-ardenone-manager:8001`

## Namespace

- **Name:** `whisper-stt`

## Deployments

### 1. whisper-stt
- **Deployment Name:** `whisper-stt`
- **Image:** `ronaldraygun/whisper-stt:1.8.6`
- **Container Port:** 8080/TCP
- **Replicas:** 0/1 READY (pods are Pending)
- **Age:** 97 days
- **Selector:** `app=whisper-stt`

**Resource Requests:**
- CPU: 1 core
- Memory: 4Gi

**Resource Limits:**
- CPU: 8 cores
- Memory: 8Gi

**Environment Variables:**
- `WHISPER_MODEL: distil-large-v3`
- Uses `whisper-stt-secret` for additional configuration

**PersistentVolumeClaims:**
- `whisper-model-cache` (mounted to `/root/.cache/huggingface`)
- `whisper-stt-jobs` (mounted to `/data`)

### 2. whisper-openai
- **Deployment Name:** `whisper-openai`
- **Image:** `fedirz/faster-whisper-server:latest-cpu`
- **Container Port:** 8000/TCP
- **Replicas:** 0/1 READY (pods are Pending)
- **Age:** 53 days
- **Selector:** `app=whisper-openai`

**Resource Requests:**
- CPU: 500m
- Memory: 512Mi

**Resource Limits:**
- CPU: 2 cores
- Memory: 2Gi

**Environment Variables:**
- `WHISPER__MODEL: large-v3-turbo`
- `WHISPER__INFERENCE_DEVICE: cpu`
- `HF_HOME: /root/.cache/huggingface`
- `HF_HUB_OFFLINE: 1`

**PersistentVolumeClaims:**
- `whisper-openai-model-cache` (mounted to `/root/.cache/huggingface`)

## Current Pod Status

### whisper-stt Pod
- **Name:** `whisper-stt-847fd8d7b9-b8rsj`
- **Status:** Pending
- **Age:** 25 days
- **Labels:** 
  - `app=whisper-stt`
  - `pod-template-hash=847fd8d7b9`

### whisper-openai Pod
- **Name:** `whisper-openai-68966786fb-tng29`
- **Status:** Pending
- **Age:** 53 days
- **Labels:**
  - `app=whisper-openai`
  - `pod-template-hash=68966786fb`

## Pod Scheduling Issue

Both pods are in **Pending** status due to unbound PersistentVolumeClaims:

```
0/1 nodes are available: pod has unbound immediate PersistentVolumeClaims.
preemption: 0/1 nodes are available: 1 Preemption is not helpful for scheduling.
```

### PersistentVolumeClaims Status

All PVCs are in **Pending** state with `longhorn` storage class:

| PVC Name | Status | Storage Class | Age |
|----------|--------|---------------|-----|
| `whisper-model-cache` | Pending | longhorn | 85 days |
| `whisper-openai-model-cache` | Pending | longhorn | 53 days |
| `whisper-stt-jobs` | Pending | longhorn | 42 days |

## kubectl Access Verification

✅ **Access verified** - kubectl commands successfully executed via proxy:
```bash
kubectl --server=http://traefik-ardenone-manager:8001
```

## Next Steps for Log Collection

Since both pods are in Pending state and have no running instances, **30-day deployment logs cannot be collected directly from these pods**. Options:

1. **Investigate PVC binding issue** - The Longhorn storage class may not have available volumes or the cluster may have storage capacity issues
2. **Check for historical logs** - If the pods were previously running, logs may exist in the logging infrastructure (VictoriaLogs or similar)
3. **Check ArgoCD managed state** - Review the deployment manifests in `declarative-config` to understand the expected configuration

## ArgoCD Management

The whisper-stt namespace is managed by ArgoCD via ardenone-manager. The manifests live in:
```
jedarden/declarative-config → k8s/ardenone-cluster/whisper-stt/
```
