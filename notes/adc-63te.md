# Task Completion: adc-63te — Implement ArgoCD Readability Path (Option B)

**Date:** 2026-07-23
**Decision:** HUMAN bead adc-359d chose Option B — re-script demo onto ardenone-cluster projects

## Implementation Status: ✅ COMPLETE

### What Was Done

1. **Demo script re-scripted onto ardenone-cluster projects**
   - Selected projects: `pbx-web` and `whisper-stt`
   - Both hosted on ardenone-cluster (ArgoCD on ardenone-manager)
   - Both have real state: pods, ArgoCD apps, git history, beads

2. **Registry configured correctly** (`config/registry.yaml`)
   ```
   pbx-web:
     cluster: ardenone-cluster
     argocd_app: pbx-web
     repo_path: /home/coding/declarative-config

   whisper-stt:
     cluster: ardenone-cluster
     argocd_app: whisper-stt
     repo_path: /home/coding/declarative-config
   ```

3. **Clusters.yaml maps ardenone-cluster to read-only proxy** (`config/clusters.yaml`)
   ```
   ardenone-cluster:
     argocd_api: https://argocd-ro-ardenone-manager-ts.ardenone.com:8444
     access: read-only-proxy
   ```

4. **Phase 5 plan updated**
   - Demo script golden path now uses pbx-web and whisper-stt
   - All 6 scripted steps reference these projects
   - Known-issues register row updated to RESOLVED

### Verification Evidence

**Seeding tool run (2026-07-23T16:08:59):**
- ✅ Registry Verification: PASS
- ✅ Dispatch Execution: PASS — all 5 scripted test dispatches succeeded
- ✅ Zero ArgoCD-source caveats on every scripted step
- ❌ Context Warmer: FAIL (separate issue — SessionStore.get_topic missing)
- ❌ Component Coverage: FAIL (separate issue — 5 result types need UI-regen beads)

The ArgoCD readability is verified. The remaining FAILs are unrelated to this task:
- Context Warmer implementation is a separate Phase 3 deliverable
- Component Coverage requires UI-regen beads, separate from ArgoCD resolution

### Acceptance Criteria Met

✅ **"The seeding verification run shows zero ArgoCD-source caveats on every scripted step"**
   - Dispatch Execution check passed with all 5 dispatches succeeding
   - Zero warnings about failed ArgoCD sources

✅ **"Plan + known-issues register updated to match reality"**
   - Phase 5 demo script updated to use ardenone-cluster projects
   - Known-issues register row marked RESOLVED (VERIFIED 2026-07-23)
   - Detailed explanation of Option B implementation added

### Files Updated

- `docs/plan/plan.md` — Phase 5 section and known-issues register updated
- `config/registry.yaml` — pbx-web and whisper-stt entries configured
- `config/clusters.yaml` — ardenone-cluster mapping to read-only proxy
- `docs/notes/seeding-report-latest.md` — verification evidence captured

### Deferred Work (Option A)

Option A (provision rs-manager read-only proxy) remains the better end-state but is deferred post-launch per the HUMAN decision. This can be revisited after the public launch.
