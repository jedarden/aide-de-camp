# adc-1lxz — "kubectl delete pod"

## Outcome

**No destructive action taken.** The request was declined and documented rather
than executed.

## Why this was not executed

The utterance `kubectl delete pod` is unactionable as a destructive command and
was unsafe to run blind:

1. **No target.** No pod name was supplied. Running `kubectl delete pod` with no
   name either errors or — far worse — risks a `--all` style mass deletion. There
   is nothing specific to delete.
2. **No namespace.** The target namespace is unspecified.
3. **No cluster.** This host reaches 8+ clusters (apexalgo-iad, ardenone-cluster,
   ardenone-hub, ardenone-manager, rs-manager, ord-devimprint, iad-ci, iad-kalshi,
   iad-options). Most are **read-only** via the proxy. No cluster was named.
4. **GitOps policy.** Per `~/CLAUDE.md`, cluster writes are never done via direct
   `kubectl`; they go through `jedarden/declarative-config` (k8s/) via ArgoCD. A
   direct `kubectl delete` write is outside the established workflow even when a
   target existed.
5. **No authorization context.** Pod deletion is hard-to-reverse and there was no
   durable authorization to proceed. The bead's own description recommended
   verifying the target with the user before executing.

This is also an automated test fixture (`intent_id=test-1`, `session_id=session-1`)
with no interactive user present to confirm a target against, so the "ask and
confirm" path is not available here either.

## Classification note

The bead description itself flags this as a routing conflict: a direct,
synchronous shell `action` that has been mis-routed into a `task-profile` bead
(designed for async, multi-step work). The correct disposition for a real
`kubectl delete pod` utterance is to execute it directly in the user's shell
context — *after* the missing arguments (pod name, namespace, cluster) are
supplied or confirmed — not to escalate it into durable async work.

## What a real invocation would require

Before a `kubectl delete pod <name> -n <ns>` could be run for a genuine request:

- Confirm the exact pod name and namespace.
- Confirm the cluster, and use the appropriate access path:
  - read-only proxy for inspection (`kubectl --server=http://traefik-...:8001 ...`),
  - the direct cluster-admin kubeconfig only for clusters that have one
    (ardenone-manager, rs-manager, iad-ci, iad-options).
- Prefer GitOps-driven restart/rollout over a manual pod delete where possible.

No kubectl write command was issued for this bead.
