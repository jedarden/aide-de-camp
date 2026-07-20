# ADC-24Z1: kubectl delete pod

## Task
Execute `kubectl delete pod` to remove a Kubernetes pod from the cluster.

## Outcome: INCOMPLETE — requires user input

`kubectl delete pod` is syntactically incomplete: it names **no pod** and **no cluster**.
It cannot be executed autonomously without guessing a destructive target, which this
environment's safety posture forbids. This is the **eighth** identical occurrence of this
auto-generated task — same conclusion every time:

- [[adc-5jl]] (`notes/adc-5jl-kubectl-delete-pod.md`) — 1st
- [[adc-26bb]] (`notes/adc-26bb.md`) — 2nd
- [[adc-1tes]] (`notes/adc-1tes.md`) — 3rd
- [[adc-1vr8]] (`notes/adc-1vr8.md`) — 4th
- [[adc-69sb]] (`notes/adc-69sb.md`) — 5th
- [[adc-39bw]] (`notes/adc-39bw.md`) — 6th
- [[adc-304j]] (`notes/adc-304j.md`) — 7th

The task generator is deterministically re-emitting this bare command whenever the escalate
intent matches `kubectl delete pod` but the source utterance carries no operand. Eight
recurrences makes it definitive that the durable fix is **upstream**: the escalate
parser/classifier should reject (or request) the missing operand before a bead is ever
created. The repo's own parser already *requires* a `<pod-name>` token
(`src/escalate/commands.py:92` `parse_delete_pod_utterance`, dispatched at
`src/escalate/handler.py`) — so the bare command would already fail to parse there. The
recurrence is happening *before* that gate.

### Why it cannot run as given

1. **No pod name or selector.** `kubectl delete pod` with no argument is a usage error;
   it needs a name (`my-pod-123`) or selector (`-l app=foo`). None was provided.

2. **No cluster / no default context.** `kubectl config current-context` returns
   `error: current-context is not set` (re-verified 2026-07-19). There is no ambient
   cluster in this shell — access is via explicit per-cluster flags (proxies or kubeconfig
   paths). The task names none. A bare `kubectl delete pod` falls back to
   `http://localhost:8080` and fails with `connection refused`.

3. **Most clusters are read-only.** Per `CLAUDE.md`, every kubectl-proxy endpoint
   (`traefik-*-manager`, `traefik-iad-options`, `kubectl-proxy-iad-kalshi`, …) carries
   read-only RBAC — they **cannot delete**. Only `ardenone-manager`, `rs-manager`, and
   `iad-ci` hold direct cluster-admin kubeconfigs, and of those only `iad-ci.kubeconfig`
   is actually present on disk in this shell. A blind delete would have to pick one.

4. **GitOps policy.** Cluster writes are supposed to flow through
   `jedarden/declarative-config` / ArgoCD, not direct `kubectl` mutations. (Pods are
   generally Deployment-owned and not GitOps-managed, so a direct delete is a legitimate
   *operational* action — but it still must be deliberately targeted, not guessed.)

5. **Destructive + reversible-via-recreation.** If the target belongs to a
   Deployment/ReplicaSet it simply respawns, making a guessed delete pointless *and*
   potentially disruptive. Confirming intent first is the right call.

### Environment facts (re-verified 2026-07-19)

- `kubectl config current-context` → `error: current-context is not set`
- `~/.kube/` kubeconfigs actually on disk: `iad-acb.kubeconfig`, `iad-ci.kubeconfig`
  (CLAUDE.md also references `ardenone-manager.kubeconfig` / `rs-manager.kubeconfig` /
  `iad-options.kubeconfig` — these are **not present on disk** in this shell)
- Escalate system implements `kubectl delete pod` as an escalate intent:
  - `src/escalate/commands.py:92` — `parse_delete_pod_utterance` (requires `<pod-name>`)
  - `src/escalate/commands.py:110` — pattern: `kubectl delete pod <pod-name> [-n <namespace>]`
  - `src/escalate/commands.py:132` — `execute_delete_pod`
  - `src/escalate/handler.py` — dispatch + `_execute_delete_pod`
  - A bare command is unparseable by that parser (no operand to extract).

### What's needed to proceed

The user must supply:
1. **Pod name** (or `-l <selector>`) — required
2. **Namespace** — if not the default for the chosen cluster
3. **Cluster / kubeconfig** — e.g. one of:
   - `~/.kube/iad-ci.kubeconfig` (cluster-admin, CI/CD) — present on disk
   - `ardenone-manager.kubeconfig` / `rs-manager.kubeconfig` (cluster-admin — not on disk
     here, would need to be provided)
   - a read-only proxy is *not* usable for delete

Once provided, the command is a one-liner:

```bash
kubectl --kubeconfig=<kubeconfig-path> delete pod <pod-name> -n <namespace>
```

## Resolution
Not executed. No pod was deleted. No cluster was mutated. Task left open for the user to
specify a target — same outcome as the seven prior identical beads.
