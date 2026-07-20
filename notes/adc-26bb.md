# ADC-26BB: kubectl delete pod

## Task
Execute `kubectl delete pod` to remove a Kubernetes pod from the cluster.

## Outcome: INCOMPLETE — requires user input

`kubectl delete pod` is syntactically incomplete: it targets **no pod** and **no cluster**.
It cannot be executed autonomously without guessing a destructive target, which this
environment's safety posture forbids. This matches the prior identical bead
[[adc-5jl]] (`notes/adc-5jl-kubectl-delete-pod.md`), which reached the same conclusion.

### Why it cannot run as given

1. **No pod name or selector.** `kubectl delete pod` with no argument is a no-op syntax
   error; it needs a name (`my-pod-123`) or selector (`-l app=foo`). None was provided.

2. **No cluster / no default context.** `kubectl config current-context` returns
   `error: current-context is not set`. There is no ambient cluster in this shell —
   access is via explicit per-cluster flags (proxies or kubeconfig paths). The task
   names none.

3. **Most clusters are read-only.** Per `CLAUDE.md`, every kubectl-proxy endpoint
   (`traefik-*-manager`, `traefik-iad-options`, `kubectl-proxy-iad-kalshi`, …) carries
   read-only RBAC — they **cannot delete**. Only `ardenone-manager` and `rs-manager`
   have direct cluster-admin kubeconfigs, and `iad-ci` has a direct cluster-admin
   kubeconfig. A blind delete would have to pick one of these.

4. **GitOps policy.** Cluster writes are supposed to flow through
   `jedarden/declarative-config` / ArgoCD, not direct `kubectl` mutations. (Pods are
   generally Deployment-owned and not GitOps-managed, so a direct delete is a legitimate
   *operational* action — but it still must be deliberately targeted, not guessed.)

5. **Destructive + reversible-via-recreation caveat.** If the target belongs to a
   Deployment/ReplicaSet it will simply respawn. That makes a guessed delete pointless
   *and* still potentially disruptive. Confirming intent first is the right call.

### Environment facts (gathered)

- `kubectl config current-context` → not set
- `~/.kube/` contains: `iad-acb.kubeconfig`, `iad-ci.kubeconfig` (+ cache)
- `notes/adc-5jl-kubectl-delete-pod.md` — prior identical task, same "incomplete,
  needs user input" outcome

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
