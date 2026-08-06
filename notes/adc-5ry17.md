# Deployment Infrastructure for pbx-web and whisper-stt Services

## Summary
Both services are deployed on **ardenone-cluster** and accessible via the read-only kubectl proxy.

---

## pbx-web Service

### Deployment Details
- **Cluster:** ardenone-cluster
- **Namespace:** pbx-web
- **Deployment Name:** pbx-web
- **Containers:** 2 containers per pod
  - `site-generator`: Python service (ronaldraygun/pbx-web:1.0.9)
  - `nginx`: nginx:alpine

### Pod Status (as of 2026-08-06)
```
NAME                                 READY   STATUS    RESTARTS   AGE
pbx-web-5ff68464d-mkn8n              2/2     Running   0          9d
pbx-rebuild-relay-588d79c5b9-vmmlz   1/1     Running   0          22d
lab-rebuild-relay-79957dbd4-xsqhl    1/1     Running   0          10d
```

### Kubectl Access Patterns

**View logs from main deployment:**
```bash
# Site-generator container logs (Python service)
kubectl --server=http://traefik-ardenone-cluster:8001 logs -n pbx-web deployment/pbx-web -c site-generator

# Nginx container logs
kubectl --server=http://traefik-ardenone-cluster:8001 logs -n pbx-web deployment/pbx-web -c nginx

# Follow logs (live tail)
kubectl --server=http://traefik-ardenone-cluster:8001 logs -n pbx-web deployment/pbx-web -c site-generator -f
```

**View logs from rebuild relays:**
```bash
# Production rebuild relay
kubectl --server=http://traefik-ardenone-cluster:8001 logs -n pbx-web deployment/pbx-rebuild-relay

# Lab rebuild relay
kubectl --server=http://traefik-ardenone-cluster:8001 logs -n pbx-web deployment/lab-rebuild-relay
```

---

## whisper-stt Service

### Deployment Details
- **Cluster:** ardenone-cluster  
- **Namespace:** whisper-stt
- **Deployments:** 2 deployments
  1. **whisper-openai**: OpenAI-compatible endpoint (fedirz/faster-whisper-server:latest-cpu)
  2. **whisper-stt**: Asterisk-specific service

### Pod Status (as of 2026-08-06)
```
NAME                              READY   STATUS    RESTARTS   AGE
whisper-openai-68966786fb-jsb5d   1/1     Running   0          53d
whisper-stt-847fd8d7b9-v2rs5      1/1     Running   0          25d
```

### Kubectl Access Patterns

**View logs from whisper-openai (OpenAI-compatible endpoint):**
```bash
kubectl --server=http://traefik-ardenone-cluster:8001 logs -n whisper-stt deployment/whisper-openai

# Follow logs (live tail)
kubectl --server=http://traefik-ardenone-cluster:8001 logs -n whisper-stt deployment/whisper-openai -f
```

**View logs from whisper-stt (Asterisk-specific):**
```bash
kubectl --server=http://traefik-ardenone-cluster:8001 logs -n whisper-stt deployment/whisper-stt

# Follow logs (live tail)
kubectl --server=http://traefik-ardenone-cluster:8001 logs -n whisper-stt deployment/whisper-stt -f
```

---

## Access Credentials

### Kubectl Proxy (Read-Only)
- **Endpoint:** http://traefik-ardenone-cluster:8001
- **Access Level:** Read-only (can view pods, logs, etc.)
- **Authentication:** Tailscale VPN required

### Admin Access (if needed)
- **Kubeconfig:** /home/coding/.kube/ardenone-manager.kubeconfig
- **Access Level:** Full cluster-admin access
- **Usage:** `kubectl --kubeconfig=/home/coding/.kube/ardenone-manager.kubeconfig`

---

## Log Retention & Pod Notes

- **Pod Restart Patterns:** Both services show minimal restarts (0 restarts for all pods)
- **Log Retention:** Logs are available as long as pods are running; pod restarts will clear previous logs
- **Persistent Storage:** 
  - whisper-openai uses PVC for model cache (10Gi, Longhorn storage class)
  - pbx-web uses emptyDir volumes (cleared on pod restart)

---

## Deployment Manifests

### pbx-web
Located in: `~/declarative-config/k8s/ardenone-cluster/pbx-web/`
- pbx-web-deployment.yml
- pbx-web-service.yml
- pbx-web-configmap.yml
- pbx-rebuild-relay-deployment.yml

### whisper-stt  
Located in: `~/declarative-config/k8s/ardenone-cluster/whisper-stt/`
- whisper-openai-deployment.yml
- whisper-stt-jobs-pvc.yml
- Various auth and config manifests

---

## Verification Commands

**Quick health check:**
```bash
# Check both namespaces
kubectl --server=http://traefik-ardenone-cluster:8001 get pods -n pbx-web
kubectl --server=http://traefik-ardenone-cluster:8001 get pods -n whisper-stt

# Check deployments
kubectl --server=http://traefik-ardenone-cluster:8001 get deployments -n pbx-web
kubectl --server=http://traefik-ardenone-cluster:8001 get deployments -n whisper-stt
```
