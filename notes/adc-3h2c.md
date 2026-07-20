# adc-3h2c — "kubectl delete pod"

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
   durable authorization to proceed. The bead's own description flagged the
   missing pod name and called for verifying it before deletion to avoid
   accidental removal of critical infrastructure.

This is an automated bead dispatch (the same unscoped `kubectl delete pod`
fixture) with no interactive user present to confirm a target against, so the
"ask and confirm" path is not available here either.

## Classification note

The bead description itself flags this as unsafe to act on without a target:
"Missing Target — the user's utterance is incomplete" and "Safety Check — Verify
the pod name before executing the delete command to avoid accidental deletion of
critical infrastructure." Those guardrails cannot be satisfied here because no
pod name, namespace, or cluster was supplied and no interactive user is present
to supply them. The correct disposition for a real `kubectl delete pod`
utterance is to confirm the missing arguments (pod name, namespace, cluster)
with the user first, and to drive the change through declarative-config rather
than a manual `kubectl delete`.

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

This continues the established refusal pattern for the identical unscoped
`kubectl delete pod` test fixture (see [[adc-65lc]], [[adc-2rh8]], [[adc-3uum]],
[[adc-3017]], [[adc-5bwk]], and [[adc-16w5]] for the most recent refusals;
earlier occurrences were logged as "…incomplete — needs target" under adc-3b1o
and adc-4wdj). All were declined on the same grounds: unscoped target,
GitOps-only write policy, read-only RBAC on most clusters, and no
authorization/interactive confirmation. A routing guard that refuses bare
destructive `kubectl` writes — or that requires pod/namespace/cluster + an
explicit GitOps-or-direct confirmation before dispatching to an Execute/Action
Strand — would short-circuit this class of bead without manual intervention.
