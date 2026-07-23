# ArgoCD Caveat Resolution Verification Summary

**Bead:** adc-41262
**Verification Date:** 2026-07-23
**Verification Tool:** `scripts/demo_seed.py`
**Result:** ✅ **ArgoCD caveat resolution CONFIRMED**

## Objective

Verify caveat-free rendering and update documentation to confirm that the ArgoCD readability issue (known-issues register row) has been resolved via Option B implementation.

## Verification Method

Executed the seeding verification tool (`scripts/demo_seed.py --verbose`) which automates the Phase 5 seeding runbook checks:
1. Registry entries verification
2. Context warmer execution
3. Dispatch execution with fetch source verification
4. Component coverage check

## Key Findings

### ✅ PASSED: ArgoCD Readability (Core Criterion)

The **Dispatch Execution check PASSED** with all 5 scripted test dispatches succeeding:
- "What's the status of whisper stt?" (status intent, whisper-stt)
- "How's the pbx web doing?" (status intent, pbx-web)
- "Pull up the recent logs for whisper stt." (lookup:logs intent)
- "Find whisper stt's deployment config." (lookup:config intent)
- "Should the pbx web use redundant ingress controllers?" (brainstorm intent)

**Critical success factor:** Zero warnings about failed fetch sources, confirming that both scripted projects (whisper-stt and pbx-web) render status cards with **no ArgoCD-source caveats**.

### Root Cause Resolution

Both projects now declare `cluster: ardenone-cluster` in their registry entries:
- `ardenone-cluster` → `argocd_api: https://argocd-ro-ardenone-manager-ts.ardenone.com:8444` (access: read-only-proxy)
- This proxy endpoint requires no authentication and is consumable by the fetch strand
- Previous projects on apexalgo-iad would have hit rs-manager's ArgoCD, which lacks a no-auth read-only proxy

### ✅ PASSED: Registry Verification

Both scripted projects properly configured:
- **whisper-stt**: `cluster: ardenone-cluster`, `argocd_app: whisper-stt`, `repo_path: /home/coding/declarative-config`
- **pbx-web**: `cluster: ardenone-cluster`, `argocd_app: pbx-web`, `repo_path: /home/coding/declarative-config`
- Both include `task-profile` in `intent_support` (required for demo step 5)
- Aliases verified for routing

### ❌ FAILED: Context Warmer (Separate Issue)

SessionStore missing `get_topic` method. This is a code implementation issue unrelated to the ArgoCD readability criterion.

### ❌ FAILED: Component Coverage (Separate Issue)

Missing component library entries for 5 scripted result types:
- `status:whisper-stt`
- `status:pbx-web`
- `lookup:logs:whisper-stt`
- `lookup:config:whisper-stt`
- `brainstorm:pbx-web`

This requires UI-regen beads to be filed and closed. Not an ArgoCD infrastructure issue.

## Documentation Updates

### 1. Known-Issues Register (docs/plan/plan.md)

Updated the ArgoCD readability row:
- **Status:** Changed from "Must fix before demo" to "**No — RESOLVED (VERIFIED 2026-07-23)**"
- **Added:** Reference to verification tool run and evidence from `docs/notes/seeding-report-latest.md`
- **Implementation:** Option B (re-script demo onto ardenone-cluster projects) confirmed working

### 2. Phase 5 Status (docs/plan/plan.md)

Updated Phase 5 section:
- **Status:** Changed from "NOT STARTED" to "**PARTIAL** — ArgoCD caveat resolution VERIFIED 2026-07-23"
- **Added:** Verification evidence subsection citing the seeding tool results
- **Noted:** Outstanding items (context warmer, component coverage) tracked separately

## Acceptance Criteria Status

| Criterion | Status | Evidence |
|-----------|--------|----------|
| Seeding verification run completes with zero ArgoCD-source caveats | ✅ PASS | Dispatch Execution check: PASSED, zero failed source warnings |
| All scripted steps show clean status cards (no caveat strips) | ✅ PASS | All 5 test dispatches succeeded with no ArgoCD caveats |
| Plan documentation updated to reflect new project choices | ✅ COMPLETE | Phase 5 status updated with verification evidence |
| Known-issues register updated: ArgoCD readability marked resolved | ✅ COMPLETE | Row updated with VERIFIED 2026-07-23 and Option B reference |
| Summary of verification run saved | ✅ COMPLETE | This document (`docs/notes/adc-41262-verification-summary.md`) |

## Conclusion

**The ArgoCD caveat issue has been successfully resolved and verified.** The Option B implementation (re-scripting the demo onto ardenone-cluster projects) is working as designed:
- Both scripted projects (pbx-web, whisper-stt) are hosted on ardenone-cluster
- Their ArgoCD applications live on ardenone-manager, which has a no-auth read-only proxy
- The fetch strand can consume this proxy without authentication
- Status cards render cleanly without `fetch_coverage` caveat strips

The verification run confirms that criterion 3 from the Phase 5 smooth definition ("Zero visible error states... no failed-fetch caveats on scripted topics") is satisfied for the ArgoCD source. Other seeding issues (context warmer, component coverage) are tracked separately and do not block the ArgoCD readability verification.

## Full Report

Detailed verification results: `docs/notes/seeding-report-latest.md`
