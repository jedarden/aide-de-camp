# Cross-Project Intents

## The Problem

Some thoughts aren't about one project — they're about a **workflow** that always spans multiple repos/systems. The canonical example:

> "Deploy the new kalshi-tape build"

This is simultaneously about:
- `jedarden/kalshi-tape` — source, CI status, image tag
- `jedarden/declarative-config` — the k8s manifest that pins the image tag

Routing this to a single project agent produces a partial, misleading answer. Routing it to two isolated agents produces two partial answers that the user has to mentally join. Neither is better than the current tab-per-project workflow.

---

## Proposed Solution: Workflow Templates

Introduce a **project graph** where nodes are repos/systems and edges are typed relationships. Named **workflow templates** are subgraphs — a set of nodes that are always addressed together for a class of intent.

```
┌─────────────────────────────────────────────────────────────┐
│  Project Graph (partial)                                     │
│                                                             │
│  kalshi-tape ──[image-consumer]──▶ declarative-config       │
│  kalshi-weather ──[image-consumer]──▶ declarative-config    │
│  options-pipeline ──[image-consumer]──▶ declarative-config  │
│                                                             │
│  declarative-config ──[syncs-to]──▶ ardenone-cluster        │
│  declarative-config ──[syncs-to]──▶ apexalgo-iad            │
│                                                             │
│  iad-ci ──[produces-image-for]──▶ kalshi-tape               │
│  iad-ci ──[produces-image-for]──▶ kalshi-weather            │
└─────────────────────────────────────────────────────────────┘
```

### Workflow Templates (examples)

| Template | Nodes | Triggered by |
|----------|-------|--------------|
| `container-deploy` | image-repo + declarative-config | "deploy", "update image", "ship" |
| `container-build` | image-repo + iad-ci | "build", "run CI", "trigger workflow" |
| `full-release` | image-repo + iad-ci + declarative-config | "release", "cut a new version" |
| `cluster-status` | declarative-config + target-cluster + ArgoCD | "what's running", "is it synced" |
| `secret-rotation` | OpenBao + declarative-config + app-repo | "rotate secrets", "update creds" |

---

## Routing with the Project Graph

The intent router gains a second pass:

```
Utterance
  │
  ▼
[Pass 1: topic detection]
  → identifies subject entities (project names, systems, vague refs)
  │
  ▼
[Pass 2: workflow matching]
  → for each entity, look up graph edges
  → if entity participates in a known workflow template that matches the intent verb, expand to the full template
  │
  ▼
[Dispatch]
  → single-project intents → individual project agents
  → compound intents → multi-project agent with shared context bundle
```

### Example

Input: "has the kalshi-tape deploy gone out?"

- Pass 1: entity = `kalshi-tape`, intent verb = status/deploy
- Pass 2: `kalshi-tape` participates in `container-deploy` template → expands to `{kalshi-tape, declarative-config, apexalgo-iad}`
- Dispatch: one agent receives context from all three; returns a single compound card

Result: the card shows CI status + current image tag + ArgoCD sync status + running pod image — the full picture, in one place.

---

## Compound Cards

A compound card covers multiple projects but presents a unified answer:

```
┌─────────────────────────────────────────────────────────┐
│  kalshi-tape deploy                          [pinned]   │
│  ─────────────────────────────────────────────────────  │
│  CI (iad-ci)          ✓ kalshi-tape-build-xyz  3m ago   │
│  Image tag            ronaldraygun/kalshi-tape:abc123   │
│  declarative-config   pinned to :abc123  (in sync)      │
│  ArgoCD               Synced ✓  last sync 2m ago        │
│  Pod (apexalgo-iad)   Running  1/1  age 2m              │
└─────────────────────────────────────────────────────────┘
```

The user never has to mentally join two tabs. The compound card *is* the join.

---

## Representing the Project Graph

### Option A: Static YAML (simple, manual)

```yaml
# stream-dispatch/project-graph.yaml
projects:
  kalshi-tape:
    repo: jedarden/kalshi-tape
    edges:
      - type: image-consumer
        target: declarative-config
      - type: built-by
        target: iad-ci
  declarative-config:
    repo: jedarden/declarative-config
    edges:
      - type: syncs-to
        target: apexalgo-iad
      - type: syncs-to
        target: ardenone-cluster

workflow_templates:
  container-deploy:
    trigger_verbs: [deploy, ship, release, update image, rollout]
    nodes: [image-repo, declarative-config, target-cluster]
    card_type: compound-deploy
```

Pros: explicit, easy to bootstrap, no inference required.  
Cons: requires manual upkeep as projects are added.

### Option B: Derived from declarative-config (smarter, harder)

Parse `declarative-config/k8s/` to infer which images deploy to which clusters. The graph is always current because it's read from the source of truth.

Pros: zero maintenance.  
Cons: requires parsing k8s manifests + image references; non-trivial to bootstrap.

### Option C: Hybrid

Start with Option A for the known compound workflows. Add Option B inference later as a graph enrichment pass.

---

## Vague Cross-Project References

Some inputs don't name a project at all:

> "did that build go out?"
> "is the new version running yet?"

Handling requires:
1. **Session context** — what was the most recent compound workflow discussed in this session?
2. **Disambiguation** — if ambiguous, surface 2-3 candidate workflows as quick-select buttons; user picks one

This is the same disambiguation problem as the single-project case, just with compound templates as candidates instead of individual projects.

---

## Open Questions

1. **Graph bootstrap cost** — how much work is it to enumerate the project graph for the ~20 active projects? One-time manual effort, or too expensive to maintain?

2. **Template inference** — can the router learn new compound patterns from usage (user always mentions kalshi-tape + declarative-config together) without explicit template definition?

3. **Partial compound intents** — what if the user only cares about one leg of a compound workflow? ("just show me the CI status, I'll handle the deploy later") — does the agent respect that or always return the full compound card?

4. **Conflict resolution in compound context** — if kalshi-tape's image tag and declarative-config's pinned tag disagree, the card should highlight the drift rather than silently showing both. Who owns that logic — the agent or the card renderer?
