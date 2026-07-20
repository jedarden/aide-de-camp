# adc-1atb — "kubectl delete pod"

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
   durable authorization to proceed.

This is also an automated test fixture (the same utterance that produced
`adc-1lxz`) with no interactive user present to confirm a target against, so the
"ask and confirm" path is not available here either.

## Classification note

The bead description flags this as a routing conflict: a direct, synchronous
shell `action` that has been mis-routed into a `task-profile` bead (designed for
async, multi-step work). Its own "Reasoning" recommends routing to the Execute
Strand for "immediate shell execution" — but that recommendation is unsafe here
because it ignores two hard constraints: the GitOps-only write policy and the
read-only RBAC on most clusters. The correct disposition for a real
`kubectl delete pod` utterance is to confirm the missing arguments (pod name,
namespace, cluster) with the user first, and to drive the change through
declarative-config rather than a manual `kubectl delete` — not to escalate it
into durable async work, and not to fire it blind into a shell.

## What a real invocation would require

Before a `kubectl delete pod <name> -n <ns>` could be run for a genuine request:

- Confirm the exact pod name and namespace.
- Confirm the cluster, and use the appropriate access path:
  - read-only proxy for inspection (`kubectl --server=http://traefik-...:8001 ...`),
  - the direct cluster-admin kubeconfig only for clusters that have one
    (ardenone-manager, rs-manager, iad-ci, iad-options).
- Prefer GitOps-driven restart/rollout over a manual pod delete where possible.

No kubectl write command was issued for this bead.

## Pattern

This is the second occurrence of the identical unscoped `kubectl delete pod`
test fixture (see [[adc-1lxz]]). Both were declined on the same grounds.
A routing guard that refuses bare destructive `kubectl` writes — or that
requires pod/namespace/cluster + an explicit GitOps-or-direct confirmation
before dispatching to an Execute Strand — would short-circuit this class of
bead without manual intervention.
