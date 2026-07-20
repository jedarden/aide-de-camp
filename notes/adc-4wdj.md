# ADC-4WDJ: kubectl delete pod

## Task
Execute `kubectl delete pod` to remove a Kubernetes pod from the cluster.

## Outcome: INCOMPLETE — requires user input

`kubectl delete pod` is syntactically incomplete: it targets **no pod** and **no cluster**.
It cannot be executed autonomously without guessing a destructive target, which this
environment's safety posture forbids.

This is the **20th** overall occurrence of this auto-generated bare-command task, every one
reaching the identical conclusion:

- [[adc-5jl]] (`notes/adc-5jl-kubectl-delete-pod.md`) — 1st
- [[adc-26bb]] (`notes/adc-26bb.md`) — 2nd / 9th
- [[adc-1tes]] (`notes/adc-1tes.md`) — 3rd
- [[adc-1vr8]] (`notes/adc-1vr8.md`) — 4th
- [[adc-69sb]] (`notes/adc-69sb.md`) — 5th
- [[adc-39bw]] (`notes/adc-39bw.md`) — 6th
- [[adc-304j]] (`notes/adc-304j.md`) — 7th
- [[adc-24z1]] (`notes/adc-24z1.md`) — 8th
- [[adc-3nd2]] (`notes/adc-3nd2.md`) — 10th
- [[adc-1b0i]] (`notes/adc-1b0i.md`) — 11th
- [[adc-zf2h]] (`notes/adc-zf2h.md`) — 12th
- [[adc-8l28]] (`notes/adc-8l28.md`) — 13th
- [[adc-2yzh]] (`notes/adc-2yzh.md`) — 14th
- [[adc-3d40]] (`notes/adc-3d40.md`) — 15th
- [[adc-40n4]] (`notes/adc-40n4.md`) — 16th
- [[adc-2k2t]] (`notes/adc-2k2t.md`) — 17th
- [[adc-349y]] (`notes/adc-349y.md`) — 18th
- [[adc-5q0d]] (`notes/adc-5q0d.md`) — 19th
- this run — 20th

The task generator deterministically re-emits this bare command whenever the escalate
intent matches `kubectl delete pod` but the source utterance carries no operand. Twenty
recurrences make it definitive that the durable fix is **upstream**: the escalate
parser/classifier should reject (or request) the missing operand *before* a bead is ever
created. The repo's own parser already *requires* a `<pod-name>` token
(`src/escalate/commands.py:92` `parse_delete_pod_utterance`, error at `:117`) — so the bare
command would already fail to parse there. The recurrence is happening *before* that gate.

Additionally, the bead's own description flags the intent as `action`, not `task-profile`:
under the documented escalation strategy, immediate action intents should be executed in
the current session flow rather than escalated into a durable tracked bead. Either way,
the bare command is not actionable.

### Why it cannot run as given

1. **No pod name or selector.** `kubectl delete pod` with no argument is a no-op syntax
   error; it needs a name (`my-pod-123`) or selector (`-l app=foo`). None was provided.

2. **No cluster / no default context.** `kubectl config current-context` returns
   `error: current-context is not set`. There is no ambient cluster in this shell —
   access is via explicit per-cluster flags (proxies or kubeconfig paths). The task
   names none.

3. **Most clusters are read-only.** Per `CLAUDE.md`, every kubectl-proxy endpoint
   (`traefik-*-manager`, `traefik-iad-options`, `kubectl-proxy-iad-kalshi`, …) carries
   read-only RBAC — they **cannot delete**. Only `ardenone-manager`, `rs-manager`, and
   `iad-ci` have direct cluster-admin kubeconfigs. A blind delete would have to pick one
   of these.

4. **GitOps policy.** Cluster writes are supposed to flow through
   `jedarden/declarative-config` / ArgoCD, not direct `kubectl` mutations. (Pods are
   generally Deployment-owned and not GitOps-managed, so a direct delete is a legitimate
   *operational* action — but it still must be deliberately targeted, not guessed.)

5. **Destructive + reversible-via-recreation caveat.** If the target belongs to a
   Deployment/ReplicaSet it will simply respawn. That makes a guessed delete pointless
   *and* still potentially disruptive. Confirming intent first is the right call.

### Environment facts (re-verified 2026-07-20 on 20th occurrence)

- `kubectl config current-context` → `error: current-context is not set`
- `~/.kube/` kubeconfigs actually on disk: `iad-acb.kubeconfig`, `iad-ci.kubeconfig`
  (+ cache). CLAUDE.md also references `ardenone-manager.kubeconfig` /
  `rs-manager.kubeconfig` / `iad-options.kubeconfig` — **not present on disk** here.
- Escalate parser (`src/escalate/commands.py:92` `parse_delete_pod_utterance`) still
  requires a `<pod-name>` operand and raises `CommandExecutionError` with
  "Expected format: kubectl delete pod <pod-name> [-n <namespace>]" (message at `:117`);
  a bare `kubectl delete pod` would fail to parse there.

### What's needed to proceed

The user must supply:
1. **Pod name** (or `-l <selector>`) — required
2. **Namespace** — if not the default for the chosen cluster
3. **Cluster / kubeconfig** — e.g. one of:
   - `~/.kube/iad-ci.kubeconfig` (cluster-admin, CI/CD)
   - `ardenone-manager.kubeconfig` / `rs-manager.kubeconfig` (cluster-admin)
   - a read-only proxy is *not* usable for delete

Once provided, the command is a one-liner:

```bash
kubectl --kubeconfig=<kubeconfig-path> delete pod <pod-name> -n <namespace>
```

### Escalate-system note

The repo already implements `kubectl delete pod` as an *escalate* intent
(`src/escalate/commands.py` → `KubernetesCommandExecutor.execute_delete_pod`,
auto-approved only in staging, manual approval via bead in production — see adc-5jl).
A bare `kubectl delete pod` with no target does not map to that flow either, since the
executor requires a parsed pod name + project_slug.

## Resolution
Not executed. No pod was deleted. No cluster was mutated. Task left open for the user
to specify a target.
