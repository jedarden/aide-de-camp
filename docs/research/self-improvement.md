# Self-Improvement: Hot-Reload and Minimal Dependencies

## The Core Principle

The system's most valuable property is its ability to improve itself based on
user feedback — faster and more continuously than any development cycle could
achieve. This property requires two architectural commitments that must be
universal, not bolt-on:

**Hot-reload**: any artifact that encodes behavior can be updated and takes
effect on the next invocation without restarting any process.

**Minimal dependencies**: each component has a narrow, stable interface. Updating
one thing does not require updating anything else. Coupling is the enemy of
iteration.

If these are honored, the self-improvement loop is:
```
user feedback (implicit or explicit)
  → identify which artifact encodes the problematic behavior
  → update that artifact (prompt, component, registry, routing rule)
  → hot-reload takes effect on next invocation
  → no deployment, no restart, no code change required
```

---

## Behavior Lives in Data, Not Code

The precondition for hot-reload: everything that makes the system behave a
particular way must be stored as a readable, writable artifact — not compiled
into a binary or hardcoded in source.

| Behavior | Artifact | Format |
|----------|----------|--------|
| How utterances are segmented | Router prompt | Text file |
| How intents are routed to projects | Project registry | YAML file |
| How workflow templates expand | Registry workflow section | YAML file |
| How agents fetch and synthesize | Strand system prompts | Text files |
| How results are rendered visually | Component library | DB (HTML/CSS) |
| How topics are labeled and linked | Topic vocabulary | Session store |
| What urgency tier an exception gets | Urgency classifier prompt | Text file |
| What a "good" summary sounds like | Voice summary prompt | Text file |

None of these require a code change to update. An agent or the user can modify
them directly. The system picks them up on the next invocation.

---

## Hot-Reload Points by Layer

### Router (prompt + registry)

The router runs a fresh LLM call per utterance. It reads its segmentation prompt
and the project registry from disk on each call — no caching of these artifacts.
File mtime checking is cheap; prompt reload is free (it's just a string).

When the user says "you always route 'the pipeline' to the wrong project", an
agent updates the registry YAML (adds an alias, adjusts a workflow template
match). The next utterance picks it up.

**Dependency boundary**: the router knows about the registry and its own prompt.
It does not know about strand internals, the session store schema, or component
formats.

### NEEDLE Strand Prompts

Each strand reads its system prompt from a file path in config. The strand
reloads the file at the start of each invocation — not at NEEDLE startup. A
prompt file change takes effect on the next NEEDLE invocation with no restart.

The `Synthesize` strand's prompt is the highest-leverage artifact: it defines
how results are formatted, what fields are included in the summary, what level
of detail is appropriate. Changes here propagate to every future result for
every topic.

**Dependency boundary**: each strand knows its prompt file path and the structured
result schema. It does not know about the canvas layout, the component library,
or other strands.

### Component Library

Components are already versioned in the DB and updated by the UI-regen agent.
Hot-reload on the canvas means active sessions subscribe to component update
events — when a component is versioned, the canvas re-renders all cards using
that component without a page refresh.

The canvas maintains a WebSocket or SSE connection. The server pushes
`component_updated: {component_id, version}` events. The canvas re-renders
affected cards in place.

**Dependency boundary**: a component is self-contained HTML/CSS/JS. It receives
a `data` object and renders it. It does not import other components, does not
call APIs, does not know about the session model.

### Session Store and Topic Model

The session store schema must be additive-only. New columns, new tables — never
rename or remove. This lets the router, agents, and watcher all evolve their
use of the store without a coordinated migration.

**Dependency boundary**: the session store is a shared database with a stable
schema contract. Each process reads only the tables it needs. No process owns
the whole schema.

### Voice Model System Prompt

The voice model's system prompt defines how it narrates results, handles
exceptions, batches notifications, and maintains conversational flow. It is a
text file, hot-reloaded by the session handler at the start of each session
turn.

Changes here affect tone, verbosity, and timing behavior without touching any
other layer.

---

## The Feedback → Update Loop

### Implicit feedback signals

| User action | Signal | Artifact to update |
|-------------|--------|--------------------|
| Expands a card immediately | Summary too sparse | Voice summary prompt, component default detail level |
| Dismisses a result without reading | Result not useful for this topic | Routing rules (deprioritize this intent type for this project) |
| Asks "why?" after every status result | Status results don't include causality | Synthesize strand prompt |
| Ignores proactive push for N days | That urgency tier too high | Urgency classifier prompt |
| Corrects a routing ("I meant kalshi, not options") | Router misidentified | Registry: add alias to correct project |
| Never uses a component type | Component doesn't fit actual data | UI-regen agent: iterate component |

These signals are collected passively by the session store (engagement events
alongside results). A background analysis bead runs periodically, identifies
patterns, and proposes artifact updates.

### Explicit feedback

The user can directly instruct updates:
- "Always include pod restart count in status cards" → Synthesize prompt updated
- "Stop pushing pipeline updates unless it's been behind for more than an hour"
  → Urgency classifier or monitoring config updated
- "The deploy card is too cluttered" → UI-regen agent iterates the component

These are natural language instructions, not configuration dialogs. The voice
model receives them, identifies which artifact to update, generates the update,
applies it. Hot-reload takes effect immediately.

---

## Minimal Dependencies: Interface Contracts

Each layer exposes a narrow interface. Downstream layers depend on the contract,
not the implementation.

```
Voice model
  contract: receive utterance → call dispatch_intent() → narrate summary field
  knows nothing about: routing internals, strand prompts, component formats

Router
  contract: receive utterance → return [intent_spec, ...]
  knows nothing about: strand internals, canvas layout, session model schema

NEEDLE strand (Fetch/Synthesize/Escalate)
  contract: receive intent_spec + context → return result (data + summary)
  knows nothing about: canvas, component library, session routing

UI-regen agent
  contract: receive result.data → return rendered HTML for component
  knows nothing about: how results were generated, session state, routing

Component
  contract: receive data object → render HTML
  knows nothing about: other components, the session, the agent that produced the data
```

Violations of these boundaries are the main risk to iteration speed. If the
Synthesize strand's prompt assumes a specific component format, changing the
component requires changing the strand prompt too — two artifacts to update
instead of one. The interfaces must be kept clean.

---

## Practical Constraints

### What hot-reload cannot cover

Some changes do require a restart or redeploy:

- **Schema migrations** (adding tables/columns): requires coordinated migration,
  not hot-reloadable. Mitigated by additive-only policy.
- **Binary changes to NEEDLE or router**: new strand types, new tool implementations.
  These are code changes and require a CI build. The hot-reload path covers prompt
  and config changes; new capabilities require deployment.
- **Security-relevant changes**: auth credentials, kubeconfig paths. These are
  not hot-reloadable for safety reasons.

The goal is to make the common case (behavior tuning, prompt improvement, component
iteration) require zero deployment. The uncommon case (new capabilities, new
integrations) follows the normal CI/CD path.

### File watching vs. per-invocation reload

Two options for prompt hot-reload:
- **File watching** (inotify): daemon detects file change, signals the process
- **Per-invocation reload**: process re-reads file at the start of each call,
  checks mtime

Per-invocation reload is simpler, zero-infra, and correct for the use case —
prompts change rarely, and re-reading a file is cheap. File watching adds
complexity (daemon process, signal handling) for marginal benefit. Use
per-invocation reload.

### Component hot-reload on canvas

The canvas subscribes to a component update event stream (same SSE connection
used for results). When a component is updated, the canvas calls
`rerenderCardsUsingComponent(componentId)`. Cards update in place. No page
reload. No flash.

This requires cards to be rendered client-side from `result.data` + component
template, not server-rendered HTML served once. The component template is fetched
from the server (with versioned cache headers) and applied in the browser.

---

## The Interface Improves Itself Through Conversation

Once bootstrapped, the interface can improve itself simply by talking into it.
Every category of improvement that lives in data — prompts, components, registry,
routing rules, monitoring config — is reachable through natural language
instructions dispatched as task intents.

```
User (via voice or text):
  "The options pipeline status card should show the lag trend, not just the current lag."

→ router classifies: self-modification intent, target: component library
→ UI-regen agent receives: current pod-status component + instruction
→ agent generates updated component with trend sparkline
→ diff surfaced to user: "Here's what changed — want me to apply it?"
→ user approves
→ component versioned in library, cache invalidated, canvas re-renders
→ hot-reload: takes effect immediately, no deployment
```

Or:

```
User: "You always route 'the feed' to the wrong project — it means the options aggregator."

→ router classifies: routing correction, target: project registry
→ self-modification agent adds alias: options-aggregator: ["the feed", "feed"]
→ registry YAML updated, hot-reloaded
→ next utterance containing "the feed" routes correctly
```

Or:

```
User: "Start monitoring the pipeline and tell me if it goes behind."

→ router classifies: monitoring config, target: topic monitoring rules
→ agent creates monitoring entry: options-pipeline, threshold: lag > 30min, urgency: high
→ ambient monitoring activates for this topic
→ no restart, no deployment
```

### What can be improved through conversation

| Category | Example instruction | Artifact updated |
|----------|--------------------|--------------------|
| Result format | "Always include restart count in pod status" | Synthesize strand prompt |
| Visual layout | "The deploy card is too cluttered" | Component iterated |
| Routing | "'The feed' means options-aggregator" | Project registry alias |
| Compound workflows | "Add a workflow for deploying IBKR MCP" | Registry workflow template |
| Monitoring | "Watch the pipeline and alert if behind" | Topic monitoring config |
| Voice behavior | "Summaries are too long for audio" | Voice model prompt |
| Urgency | "Don't push pipeline updates unless critical" | Urgency classifier prompt |
| New project | "Add pdftract to the registry" | Project registry |
| Exception handling | "Auto-approve deploys to staging" | Exception routing rules |

### What still requires code

Two categories remain outside the conversational improvement loop:

1. **New binary capabilities**: a new context-fetch tool (a new API integration,
   a new kubectl query type, a new data source) requires implementing a function
   and deploying updated NEEDLE or the router binary. The prompt can invoke the
   tool once it exists; the tool itself must be written.

2. **Initial bootstrap**: the first version of the system requires code. Once
   it exists, the loop is closed. The initial implementation doesn't need to be
   good — it needs to be working. Everything after that is conversational iteration.

### The development model after bootstrap

After the initial build, the interface becomes its own development environment
for improving the interface. The workflow:

```
Notice something wrong or missing
  ↓
Say what's wrong, while using the interface
  ↓
Self-modification agent proposes the artifact change
  ↓
Review the diff (in the canvas, or narrated in audio mode)
  ↓
Approve or adjust
  ↓
Hot-reload — takes effect immediately
```

No IDE switch. No PR. No deployment. The development loop collapses into the
usage loop. Improvement happens at the speed of conversation.

### Safety model for self-modification

Unconstrained self-modification is risky — a poorly-specified instruction could
make the router worse, break a component, or create a monitoring rule that floods
with noise. Three guardrails:

1. **Diffs before application**: the self-modification agent always shows what
   will change before applying. For prompts: the before/after text. For
   components: the visual diff in the canvas. For registry: the YAML delta. The
   user approves, adjusts, or cancels.

2. **Version history for all artifacts**: prompts, components, and registry
   entries are versioned. Any update can be rolled back with a single instruction:
   "revert the pipeline status component to the previous version."

3. **Confidence threshold**: below a threshold, changes require explicit approval.
   Above it (e.g., adding an alias that's unambiguous), changes can apply
   automatically with a notification. The threshold is configurable and starts
   conservative.

---

## The Self-Improving System

With hot-reload and minimal dependencies in place, the improvement loop becomes
continuous rather than episodic:

1. System runs. User interacts. Engagement signals accumulate.
2. Background analysis bead identifies patterns: "Synthesize prompt produces
   results that users consistently drill into for more detail."
3. Analysis bead proposes a prompt update: "Include the top 3 contributing
   factors in every status summary."
4. User reviews the proposal (or it applies automatically above a confidence
   threshold).
5. Prompt file updated. Hot-reloaded. Behavior changes on the next invocation.
6. New engagement signals accumulate. Loop continues.

No deployment. No PR. No context switching to fix a behavior that's mildly
wrong but not wrong enough to file a bug for. The system corrects continuously
at the granularity of artifacts, not releases.
