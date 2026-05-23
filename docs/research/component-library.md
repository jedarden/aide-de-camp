# Component Library: Cached, Iterated, Self-Growing

## The Insight

Cards are rendering artifacts generated from results. But generating a card via
an LLM call for every render is wasteful — the same result rendered in the same
layout context should produce the same card. More importantly, the **component
template** used to render a result is itself a reusable artifact that improves
over time.

Two layers of caching:

1. **Rendered card cache**: a specific result rendered in a specific layout
   context. Invalidated when the result changes or the component is iterated.

2. **Component library**: the set of named HTML/CSS templates the UI-regen agent
   has generated. Reused across results of similar type. Iterated when a component
   renders something poorly or a new capability is needed.

The component library starts empty and grows organically from actual usage.
No templates are designed up front.

---

## Component Lifecycle

```
New result arrives
  │
  ▼
UI-regen agent: does an existing component handle this result well?
  │
  ├─[yes]──→ render with existing component → cache result
  │
  └─[no]───→ generate new component
               │
               ├─ store in component library
               ├─ render result with new component
               └─ cache result
```

Over time: the library accumulates components for the actual result types the
system produces. A kubectl pod status renders differently from a git log summary,
which renders differently from a bead dependency graph. Each gets its own
component, refined through use.

### Component Iteration

When a component renders something poorly — wrong level of detail, awkward layout
for certain data shapes, missing a field the user keeps asking about — the
UI-regen agent iterates it:

```
User expands a compact status card and asks "why can't I see the pod restart count?"
  │
  ▼
UI-regen agent: iterate the pod-status component to include restart count
  │
  ├─ updates component in library (new version)
  ├─ invalidates cached renders that used the old version
  └─ re-renders all active results that use this component
```

Components are versioned. Old versions are kept for history but new renders use
the latest version. The canvas updates in place when a component is iterated.

---

## Component Library Store

```sql
components (
  id           TEXT PRIMARY KEY,
  name         TEXT,               -- "pod-status", "git-log-summary", "bead-dep-graph"
  description  TEXT,               -- what result types this handles
  html_template TEXT,              -- the actual HTML/CSS (parameterized)
  version      INTEGER,
  created_at   INTEGER,
  last_used    INTEGER,
  usage_count  INTEGER
)

component_versions (
  component_id TEXT,
  version      INTEGER,
  html_template TEXT,
  created_at   INTEGER,
  change_note  TEXT                -- why it was iterated
)
```

### Rendered Card Cache

```sql
card_cache (
  result_id      TEXT,
  component_id   TEXT,
  component_version INTEGER,
  layout_bucket  TEXT,             -- 'compact' | 'normal' | 'expanded'
  rendered_html  TEXT,
  created_at     INTEGER,
  PRIMARY KEY (result_id, component_id, layout_bucket)
)
```

Cache key: `(result_id, component_id, layout_bucket)`. Layout is bucketed rather
than exact — a window resize within the same bucket reuses the cached card; a
bucket change triggers a re-render.

Layout buckets:
- `compact`: many active topics, minimal space per topic
- `normal`: few active topics, standard space
- `expanded`: topic is focused or maximized, full canvas available

Cache invalidation:
- Component iterated (new version) → invalidate all rows for that `component_id`
- Result updated (new data) → invalidate all rows for that `result_id`
- Layout bucket changes → serve different bucket's cached render (or generate if uncached)

---

## UI-Regen Agent's Job (Revised)

With the component library, the UI-regen agent has a richer task:

1. **Component selection**: given a result's data shape, find the best-fit
   existing component. Semantic match — does this component's description match
   what the result contains?

2. **Component generation**: if no good fit, generate a new component from scratch.
   Store it. Name it meaningfully.

3. **Rendering**: apply the selected component template to the result data,
   accounting for the layout bucket.

4. **Iteration**: when feedback (explicit or implicit) indicates a component
   isn't serving well, improve it. Update the library. Trigger re-renders.

The UI-regen agent is the steward of the component library. It decides when to
create, reuse, and iterate components. It has access to the full library as context
when making these decisions — "here are the 12 components we have; does any of them
handle this result, or do we need a new one?"

---

## What the Component Library Looks Like After Sustained Use

Starting from zero, after a few weeks of use across the project graph, the library
would naturally contain components for:

- Pod status (phase, restarts, age, image tag)
- ArgoCD sync status (synced/outofsync, last sync, health)
- Git log summary (recent commits, author, message)
- CI workflow status (phase, duration, link to logs)
- Bead list (open beads for a project, priority, status)
- Bead dependency graph (visual DAG for compound work)
- Compound deploy status (CI + image + config pin + pod — all in one)
- Pipeline lag (lag metric, last event, trend)
- Exception card (what's blocked, what decision is needed, action buttons)
- Naming candidates list (names, rationales, domain status)
- Research summary (key findings, structured output from a task bead)

None of these are hand-coded. They emerge from what the system actually needs to
render. Each is refined over time as the user implicitly or explicitly requests
more detail or better layout.

---

## Relationship to the UI-Regen Agent in Audio Mode

In audio mode there is no canvas and no card rendering. The component library is
irrelevant to the audio path. The voice model reads `result.summary` directly.

However: when a user transitions from audio to canvas mode mid-session, the pending
results that were narrated in audio mode can be rendered as cards using the component
library. The results were stored; the cards just weren't generated yet. Session
continuity means the canvas catches up to what was already discussed.
