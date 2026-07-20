# ADC-1TES: kubectl delete pod

## Task
Execute `kubectl delete pod` to remove a Kubernetes pod from the cluster.

## Outcome: INCOMPLETE — requires user input

`kubectl delete pod` is syntactically incomplete: it names **no pod** and **no cluster**.
It cannot be executed autonomously without guessing a destructive target, which this
environment's safety posture forbids. This is the **third** identical occurrence of this
auto-generated task — same conclusion each time: [[adc-5jl]]
(`notes/adc-5jl-kubectl-delete-pod.md`) and [[adc-26bb]] (`notes/adc-26bb.md`).

The task generator appears to be re-emitting this bare command whenever the escalate
intent matches `kubectl delete pod` but the source utterance carries no operand. A
durable fix worth considering: have the escalate parser/classifier reject or request the
missing operand upstream so this bead type stops recurring (see
`src/escalate/commands.py:parse_delete_pod_utterance`, which already *requires* a
`<pod-name>` token — the bare command would fail to parse there too).

### Why it cannot run as given

1. **No pod name or selector.** `kubectl delete pod` with no argument is a usage error;
   it needs a name (`my-pod-123`) or selector (`-l app=foo`). None was provided.

2. **No cluster / no default context.** `kubectl config current-context` returns
   `error: current-context is not set`. There is no ambient cluster in this shell —
   access is via explicit per-cluster flags (proxies or kubeconfig paths). The task
   names none.

3. **Most clusters are read-only.** Per `CLAUDE.md`, every kubectl-proxy endpoint
   (`traefik-*-manager`, `traefik-iad-options`, `kubectl-proxy-iad-kalshi`, …) carries
   read-only RBAC — they **cannot delete**. Only `ardenone-manager`, `rs-manager`, and
   `iad-ci` hold direct cluster-admin kubeconfigs. A blind delete would have to pick one.

4. **GitOps policy.** Cluster writes are supposed to flow through
   `jedarden/declarative-config` / ArgoCD, not direct `kubectl` mutations. (Pods are
   generally Deployment-owned and not GitOps-managed, so a direct delete is a legitimate
   *operational* action — but it still must be deliberately targeted, not guessed.)

5. **Destructive + reversible-via-recreation.** If the target belongs to a
   Deployment/ReplicaSet it simply respawns, making a guessed delete pointless *and*
   potentially disruptive. Confirming intent first is the right call.

### Environment facts (gathered 2026-07-19)

- `kubectl config current-context` → `error: current-context is not set`
- `~/.kube/` kubeconfigs: `iad-acb.kubeconfig`, `iad-ci.kubeconfig`
- Prior identical tasks: `notes/adc-5jl-kubectl-delete-pod.md`, `notes/adc-26bb.md`
- Repo escalate system implements `kubectl delete pod` as an escalate intent at
  `src/escalate/commands.py` (`parse_delete_pod_utterance`, `execute_delete_pod`);
  the parser requires a `<pod-name>` operand, so the bare command is unparseable there.

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
