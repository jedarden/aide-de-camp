# ADC-1C8O: Recommendation — `exceptions.yaml` auto-approves kubectl mutations

> **OPS-GATED review note.** This bead requires a human decision. It does **not**
> modify any code or config. The recommendation below is for the human reviewer;
> the actual fix must come from a separate, non-OPS-GATED follow-up bead that
> authorizes a specific change.

## TL;DR recommendation

**Adopt Option B for the kubectl mutation entries:** remove the three `kubectl_*`
entries from `auto_approve.safe_mutations` so all cluster-mutation `action` intents
escalate to a NEEDLE bead, and add a guard so the escalate executor refuses to run
any write-type kubectl action even if a rule were re-added. Keep the
`auto_approve.read_only` section (logs/describe/get/argocd_get) — that section is
**not** in conflict. The `git_commit` / `git_push_feature_branch` entries under the
`project_slug == 'aide-de-camp'` rule are also **not** in conflict (repo writes, not
cluster mutations) and can stay.

Rationale in one line: the workspace `/home/coding/CLAUDE.md` GitOps policy explicitly
bans **all** live cluster mutations (`scale`, `delete`, `patch`, `restart`, …) "even
for one-off triage, emergencies," with no staging carve-out — so auto-approving those
exact mutations is non-compliant by construction, regardless of blast radius.

---

## What this audit verified (all bead claims confirmed)

1. **`config/exceptions.yaml` (lines 18–24)** — `auto_approve.safe_mutations` lists
   `kubectl_restart_deployment`, `kubectl_delete_pod`, `kubectl_scale_up` gated only
   by `environment == 'staging'`. Confirmed verbatim.

2. **`src/escalate/handler.py` (lines 287–372)** — `_execute_auto_approved()` routes
   `kubectl_delete_pod` to `_execute_delete_pod()` and other `kubectl_*` actions to
   `_execute_kubectl_command()`. When auto-approve hits, `escalate_intent()` (lines
   735–754) executes directly and marks the intent `resolved` — **no bead is created,
   no human review, no declarative-config/ArgoCD round-trip**. Confirmed.

3. **`docs/plan/plan.md` "Security Model" (lines 789–795)** — states:
   - "all cluster access via read-only kubectl proxies (same as existing tooling)"
   - "No cluster credentials stored by aide-de-camp; existing proxy infrastructure holds them"

   Confirmed. This is internally inconsistent with the auto-approve design elsewhere
   in the same repo.

4. **`/home/coding/CLAUDE.md` "Infrastructure"** — workspace-wide GitOps rule:
   "all cluster changes go through `jedarden/declarative-config`… this includes not
   just `kubectl apply/create` but ALSO any live mutation of a managed resource:
   `kubectl scale, delete, patch, edit, annotate, rollout restart`… even for one-off
   triage, emergencies, or 'temporary' fixes." **No staging exception is carved out.**
   This policy applies to every project on this host, including aide-de-camp.

5. **`notes/adc-5jl.md`** — a prior task already established that the read-only
   kubectl-proxy **cannot delete resources** and that an admin/write kubeconfig would
   be required for real execution; it also independently recommends going through
   ArgoCD rather than live deletion. Confirmed.

### Additional findings beyond the bead (important for the decision)

- **The write path is NOT currently wired to a write kubeconfig.** `grep` for
  `kubeconfig` / `--kubeconfig` / admin-kube across `src/escalate/` and `config/`
  returns nothing. `src/escalate/commands.py:160-166` builds the command as
  `kubectl --server <cluster_proxy> delete pod …`, where `cluster_proxy` is one of the
  read-only proxies in `config/registry.yaml` (`traefik-*:8001` /
  `kubectl-proxy-*:8001`). So today `_execute_delete_pod` would **fail** against a
  read-only proxy, exactly as adc-5jl found. The policy violation is therefore
  **latent** — it triggers the moment someone adds a write kubeconfig or points the
  proxy at a write-capable endpoint, which is the obvious next step to "make it work."

- **There is no real "staging" environment.** `environment` is caller-supplied
  metadata (`request.metadata.get("environment")`, handler.py:172) — not derived from
  the cluster. `config/registry.yaml:113` maps the alias `staging → options-pipeline`,
  and `options-pipeline` lives on **`apexalgo-iad`** (registry.yaml:14) — i.e. the
  production options data pipeline. So the `environment == 'staging'` gate can be
  satisfied for what is in practice the prod pipeline cluster. This substantially
  weakens any "staging-only, low blast radius" (Option A) argument: the label
  controls nothing infrastructural.

- **Tests pinning the current behavior** (the follow-up bead must update or remove
  these):
  - `tests/test_kubectl_delete_pod.py`
  - `tests/test_kubectl_delete_pod_integration.py`
  - `tests/test_exceptions_routing.py`

- **Not in conflict (leave as-is):**
  - `auto_approve.read_only` (`kubectl_logs`, `kubectl_describe`, `kubectl_get`,
    `git_status`, `git_log`, `argocd_get`) — read-only, consistent with both the plan
    Security Model and the GitOps policy.
  - The `project_slug == 'aide-de-camp'` rule's `git_commit` /
    `git_push_feature_branch` — repo writes, not cluster mutations. Workspace policy
    explicitly pre-approves reversible `git push`, so these are compliant.

---

## The three options (as framed by the bead)

### Option A — keep the mutation auto-approvals, update plan.md to document the exception
- **Pro:** single-user tool, convenience, fast triage loop.
- **Con:** directly contradicts the workspace GitOps rule, which is written to forbid
  exactly this ("even for one-off triage, emergencies"). Because "staging" is just a
  caller-supplied label that resolves to the prod-pipeline cluster, the "low blast
  radius" premise doesn't hold in practice. Documenting an exception in plan.md does
  not make the behavior compliant with `/home/coding/CLAUDE.md`; it just makes two
  docs disagree.
- **Verdict: not recommended.** It legalizes the conflict rather than resolving it.

### Option B — remove the kubectl mutation auto-approvals; always escalate cluster mutations to a bead ✅ recommended
- All `action`-type intents involving a cluster mutation (`kubectl_delete_pod`,
  `kubectl_restart_deployment`, `kubectl_scale_up`, and the `manual_approval` set)
  create a NEEDLE bead per the plan's documented Component 5 "Escalate Strand" flow.
  The bead (a human or Claude Code under a non-Ops-gated bead) then performs the
  change **through declarative-config + ArgoCD**, or via a write kubeconfig used by
  the worker — not by adc's own auto-approve executor.
- adc itself stays read-only exactly as plan.md claims.
- This is the only option fully consistent with both plan.md's Security Model **and**
  the workspace GitOps policy.
- **Implementation sketch for the follow-up bead** (do not act on this here):
  1. In `config/exceptions.yaml`, delete the `safe_mutations` block whose condition is
     `environment == 'staging'` (lines 19–24). Keep the `project_slug ==
     'aide-de-camp'` git block.
  2. In `src/escalate/handler.py`, make `_evaluate_auto_approve` return `False` for
     any `action` that starts with `kubectl_` and is not in `read_only` — defense in
     depth, so re-adding a config rule alone can't silently re-enable writes.
  3. In `src/escalate/commands.py`, either delete `execute_delete_pod` or convert it
     to an explicit refusal that returns an "escalate-to-bead / use declarative-config"
     result. (Currently it can only ever target a read-only proxy and fail; keeping it
     invites a future write-kubeconfig wiring.)
  4. Update / remove the three tests listed above.
  5. Optionally align plan.md so the Security Model and the escalate strand agree
     (no contradiction either way once B lands).

### Option C — auto-approve read-only only; mutations always escalate
- This is essentially **Option B as it applies to the mutation question**, while
  explicitly endorsing the existing `read_only` auto-approvals. Functionally B and C
  converge on the same outcome for the disputed `safe_mutations` kubectl entries; C
  just states the positive case for the read-only list more deliberately.
- **Also acceptable.** If the reviewer prefers to keep a crisp "read-only is fine,
  everything else escalates" line, C is the cleaner framing.

---

## Why B/C over A (the deciding points)

1. **The GitOps policy is categorical.** It names `kubectl scale/delete/patch/restart`
   by name and says "even for one-off triage, emergencies." Auto-approving those exact
   verbs is the precise pattern the policy exists to prevent.
2. **"Staging" is not a real boundary here.** The gate is caller-supplied metadata
   that resolves to the production pipeline cluster, so the blast-radius justification
   for A is unsound.
3. **The plan's own Security Model says read-only.** A keeps the code and rewrites the
   doc; B keeps the doc and trims the code. B is the smaller, safer change and removes
   a latent footgun (the half-wired write path in `commands.py`).
4. **The bead already established the write path doesn't work today** (adc-5jl). There
   is no working functionality being lost — only a non-functional, policy-violating
   design being removed.

---

## Requested follow-up

File a **normal (non-OPS-GATED) follow-up bead** that authorizes Option B
(equivalently C) and specifies the exact config/code/test changes from the sketch
above. Do not implement any of those changes under this (adc-1c8o) bead — it is
review-only.

## Files touched by this bead

- `notes/adc-1c8o.md` (this file) — recommendation only. **No code or config changes.**
