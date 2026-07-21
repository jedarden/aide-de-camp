# adc-4so2 — "kubectl delete pod"

## Outcome

**No destructive action taken.** The request was declined and documented rather
than executed. No `kubectl delete` (or any kubectl write) command was issued.

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
   durable authorization to proceed. The bead's own description classifies
   `kubectl delete pod` as an immediate `action`/execution intent and explicitly
   instructs the executor to verify the cluster context, identify the target pod,
   and ask the user to specify the pod name when it is missing — a step that
   cannot be satisfied here.

This is an automated bead dispatch (the unscoped `kubectl delete pod` fixture)
with no interactive user present to confirm a target against, so the "ask and
confirm" path is not available here either.

## Classification note

The bead description itself flags `kubectl delete pod` as an immediate-execution
`action` intent that requires specific context — a pod name and namespace — to be
actionable, and warns that the task "causes immediate downtime for the pod" and
must "ensure the user is aware of the target." It instructs the executor to
"verify the current cluster context and potentially list pods to help identify the
target, or ask the user to specify the pod name" when the target is omitted. None
of those preconditions are satisfiable here: no pod name, namespace, or cluster was
supplied, and no interactive user is present to supply them. The correct
disposition for a real `kubectl delete pod` utterance is to confirm the missing
arguments (pod name, namespace, cluster) with the user first, and to drive the
change through declarative-config (or a GitOps-driven rollout/restart) rather than
a manual `kubectl delete`.

## What a real invocation would require

Before a `kubectl delete pod <name> -n <ns>` could be run for a genuine request:

- Confirm the exact pod name and namespace.
- Confirm the cluster, and use the appropriate access path:
  - read-only proxy for inspection (`kubectl --server=http://traefik-...:8001 ...`),
  - the direct cluster-admin kubeconfig only for clusters that have one
    (ardenone-manager, rs-manager, iad-ci, iad-options).
- Prefer a GitOps-driven restart/rollout over a manual pod delete where possible.

No kubectl write command was issued for this bead.

## Pattern

This continues the established refusal pattern for the identical unscoped
`kubectl delete pod` test fixture (see [[adc-1ogd]], [[adc-55ij]], [[adc-4eqs]],
[[adc-6zfb]], [[adc-3h2c]], [[adc-65lc]], [[adc-5cnz]], and [[adc-414x]] for prior
refusals; earlier occurrences were logged as "…incomplete — needs target" under
adc-3b1o and adc-4wdj). All were declined on the same grounds: unscoped target,
GitOps-only write policy, read-only RBAC on most clusters, and no
authorization/interactive confirmation. A routing guard that refuses bare
destructive `kubectl` writes — or that requires pod/namespace/cluster + an explicit
GitOps-or-direct confirmation before dispatching to an Execute/Action Strand —
would short-circuit this class of bead without manual intervention.
