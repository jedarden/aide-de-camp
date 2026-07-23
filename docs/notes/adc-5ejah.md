# Two ardenone-cluster Projects with Real State

*Documentation for bead adc-5ejah: Identify two ardenone-cluster projects with real state*

## Chosen Projects

### 1. whisper-stt

**Cluster:** ardenone-cluster
**Namespace:** whisper-stt
**ArgoCD App:** whisper-stt

**Pod State (verified 2026-07-23):**
- whisper-openai-68966786fb-jsb5d: ready=True, restarts=0 ✓
- whisper-stt-847fd8d7b9-v2rs5: ready=True, restarts=0 ✓
- whisper-openai-6885fc878b-jjm5j: ready=False (ContainerStatusUnknown)

**ArgoCD Application:**
- Manifest: `declarative-config/k8s/ardenone-cluster/whisper-stt/whisper-stt-application.yml`
- API endpoint: `https://argocd-ro-ardenone-manager-ts.ardenone.com:8444/api/v1/applications/whisper-stt`
- Access: read-only-proxy (consumable by fetch strand)

**Git History:**
- Repository: jedarden/declarative-config
- Path: k8s/ardenone-cluster/whisper-stt/
- Recent commits (last 3 months):
  - 0829ee7 fix(whisper-stt): prefer big-CPU nodes via soft nodeAffinity
  - 6fc620d feat(whisper-stt): deploy 1.8.6, route /jobs/{id} + /jobs/chunked/* off Google auth
  - eab3f7e feat(whisper-stt): deploy 1.8.4 (bearer-auth chunked upload endpoints)

**Associated Beads:**
- adc-4iq: Voice path scripted: /voice WS turn -> STT -> response + narration (fixture audio) - **closed**
- adc-4kz: STT fallback: whisper-stt path when Web Speech API is unavailable - **closed**
- Both beads reference whisper-stt on ardenone-cluster

---

### 2. pbx-web

**Cluster:** ardenone-cluster
**Namespace:** pbx-web
**ArgoCD App:** pbx-web

**Pod State (verified 2026-07-23):**
- pbx-web-5ff68464d-97b8p: ready=True, restarts=0 ✓
- pbx-rebuild-relay-588d79c5b9-vmmlz: ready=True, restarts=0 ✓
- lab-rebuild-relay-79d6d858bb-gfbf2: ready=True, restarts=0 ✓

**ArgoCD Application:**
- Manifest: `declarative-config/k8s/ardenone-cluster/pbx-web/application.yaml`
- API endpoint: `https://argocd-ro-ardenone-manager-ts.ardenone.com:8444/api/v1/applications/pbx-web`
- Access: read-only-proxy (consumable by fetch strand)

**Git History:**
- Repository: jedarden/declarative-config
- Path: k8s/ardenone-cluster/pbx-web/
- Recent commits (last 3 months):
  - 25c11c8 fix(pbx-web): force ESO resync + auto-restart on webhook secret rotation
  - 83af76c fix(pbx-web): migrate secrets to OpenBao/ExternalSecret
  - f20d55e feat(pbx-web): bump image to 1.0.9 (copy transcript now includes timestamps)

**Associated Beads:**
- adc-jr35: [Unravel] HUMAN: real-microphone voice turn + listen to narration + visual canvas check — Headless browser automation for canvas verification - **closed**
- adc-50m6: [Unravel] HUMAN: real-microphone voice turn + listen to narration + visual canvas check — Mock Web Speech API with pre-canned test utterances - **closed**
- adc-5zs: HUMAN: real-microphone voice turn + listen to narration + visual canvas check - **blocked**
- adc-1lig: [Unravel] HUMAN: real-microphone voice turn + listen to narration + visual canvas check — Audio output capture and programmatic verification - **closed**
- These beads relate to voice/telephony verification tasks that likely connect to pbx-web functionality

---

## Verification Notes

Both projects meet all acceptance criteria:
1. **Running pods**: Both namespaces have pods in ready state ✓
2. **ArgoCD apps**: Both have application manifests and are readable via the ardenone-manager read-only proxy ✓
3. **Git history**: Both have active development history in declarative-config ✓
4. **Associated beads**: Both have related beads documenting work and verification ✓

## ArgoCD Read-Only Proxy

The ardenone-manager read-only proxy is accessible at:
```
https://argocd-ro-ardenone-manager-ts.ardenone.com:8444
```

This proxy requires no authentication (injects a read-only bearer token) and is consumable by the fetch strand for both projects.

## Other Candidate Projects (Not Selected)

**botburrow:**
- Also meets all criteria (running pods, ArgoCD app, git history)
- Less clear bead association
- Could serve as a backup candidate

**Alternative Considered:**
- dockerhub-ratelimit-check (running in default namespace)
- No standalone ArgoCD app (likely managed by a parent ApplicationSet)
- Minimal git footprint
