# NEEDLE Strands for Stream Dispatch

## The Inversion

Normal NEEDLE: beads exist → worker polls → waterfall finds one → worker processes it.

Stream-dispatch: utterance arrives → NEEDLE invoked with it → strands process it.

The beads don't exist yet. The utterance is the work item. A different waterfall is configured to handle it — the strands aren't finding pre-existing work, they're executing a processing pipeline over the incoming request.

---

## Two Waterfall Configurations

### Standard NEEDLE waterfall (existing)
Drains a bead queue. Strands are selection strategies.

```
Pluck → Mend → Explore → Weave → Unravel → Pulse → Reflect → Splice → Knot
```

Input: bead store state.
Output: one claimed bead to work.

### Stream-dispatch waterfall (new)
Processes a human utterance. Strands are pipeline stages.

```
Segment → Route → Fetch → Synthesize → Escalate
```

Input: raw utterance + session context.
Output: N card specs (one per intent thread), or a bead ref for deferred work.

---

## Stream-Dispatch Strand Definitions

### Segment
Splits the raw utterance into intent threads. Each thread carries a topic,
an intent type, and a confidence score.

- Input: `{utterance, session_history}`
- Output: `[{topic, intent_type, confidence, text_fragment}, ...]`
- Returns `WorkCreated` if it produces threads, `NoWork` if utterance is empty/unparseable

### Route
Matches each intent thread to projects and workflow templates using the
project registry. Expands compound intents (e.g. "deploy X" → image-repo +
declarative-config + cluster).

- Input: intent threads from Segment
- Output: threads annotated with `{project_slugs, workflow_template, context_spec}`
- Returns `WorkCreated` (routes found), `NoWork` (no match → disambiguation needed)

### Fetch
For each routed thread, executes the context spec: kubectl, git log, br list,
ArgoCD queries. Respects the live intent deadline (8s hard limit).

- Input: routed threads with context specs
- Output: threads enriched with `{fetched_context}`
- Returns `WorkCreated` on success, `Error` if context fetch fails entirely

### Synthesize
Runs the LLM call per thread with its fetched context. Produces a card spec.
Parallel across threads.

- Input: enriched threads
- Output: `[card_spec, ...]` — title, type, body_html, optional bead_ref
- Returns `BeadFound` (the card specs, borrowing the type) or `Error`

### Escalate
Handles threads that exceeded the live deadline or whose intent_type is
`task` (requires durable work). Creates a bead for each, returns a
pending card spec.

- Input: threads that Fetch or Synthesize couldn't complete live
- Output: pending card specs with bead refs
- Returns `WorkCreated` (beads created for NEEDLE standard waterfall to pick up)

---

## Invocation Model

Standard NEEDLE runs a continuous loop: waterfall → claim → work → repeat.

Stream-dispatch NEEDLE is invoked **per utterance** (or per session turn):

```
Router receives utterance
  │
  ▼
Invoke NEEDLE with stream-dispatch waterfall config + utterance as input
  │
  ├─ Segment → Route → Fetch → Synthesize  (live path, parallel per thread)
  │                                │
  │                                ▼
  │                         card specs → SSE → frontend
  │
  └─ Escalate (for any threads that go async)
               │
               ▼
         beads created → standard NEEDLE waterfall picks them up
               │
               ▼
         bead watcher → pending card updates → SSE → frontend
```

The same NEEDLE binary handles both modes. The difference is the waterfall
configuration passed at invocation time.

---

## How Input Reaches the Strands

Standard strands receive a `BeadStore` — they query it to find candidates.

Stream-dispatch strands need access to the utterance. Two options:

**Option A: Utterance bead**
The router creates a minimal bead (`type: utterance`, body: raw text) before
invoking NEEDLE. Strands read the bead store as normal — Segment claims the
utterance bead and produces thread beads, each subsequent strand works those.
Waterfall restarts carry state forward via bead creation.

Pros: no changes to the strand interface (`evaluate(store)` signature unchanged).
Cons: bead-store round-trips add latency; utterance beads clutter the store.

**Option B: Extended invocation context**
NEEDLE accepts a context payload at startup in stream-dispatch mode. Strands
receive it alongside the store. The utterance never touches the bead store.

Pros: lower latency (no bead I/O for the live path); clean separation.
Cons: requires extending the strand interface and NEEDLE's invocation API.

Option B is the right call for live intents. Option A is acceptable for task
intents where the latency is tolerable and bead durability is wanted anyway.

---

## Config Shape

```toml
# needle.stream.toml  — stream-dispatch invocation config
[mode]
type = "stream"

[waterfall]
strands = ["segment", "route", "fetch", "synthesize", "escalate"]

[strands.segment]
# LLM model to use for intent splitting
model = "claude-haiku-4-5"

[strands.route]
registry = "/home/coding/stream-dispatch/project-registry.yaml"

[strands.fetch]
deadline_secs = 8
tools = ["kubectl_get", "git_log", "br_list", "argocd_get"]

[strands.synthesize]
model = "claude-sonnet-4-6"
parallel = true

[strands.escalate]
bead_workspace = "/home/coding/stream-dispatch/tasks"
```

vs. the standard config:

```toml
# needle.toml — standard bead-draining config
[mode]
type = "bead"

[waterfall]
strands = ["pluck", "mend", "explore", "weave", "unravel", "pulse", "reflect", "splice", "knot"]
```

---

## Open Questions

1. **Strand interface extension**: the current `evaluate(store: &dyn BeadStore) -> StrandResult`
   signature doesn't carry utterance context. Extending it to
   `evaluate(store, context: Option<&InvocationContext>)` is backwards-compatible
   (standard strands ignore context), but requires touching every strand impl. Worth it?

2. **Parallel synthesis**: Synthesize runs one LLM call per thread in parallel.
   NEEDLE's current model is single-threaded per bead. Does stream-dispatch synthesis
   need to run inside NEEDLE, or is it cleaner as a separate parallel dispatcher that
   NEEDLE hands off to?

3. **Session history**: Segment needs prior turns to resolve vague references ("that
   thing we discussed"). Where does session history live — passed in the invocation
   context, or stored as a special bead type that Segment queries?

4. **Escalation bead workspace**: task beads created by Escalate need to be picked up
   by standard NEEDLE workers. They should land in a workspace that those workers
   monitor — either the current project workspace or a dedicated stream-dispatch tasks
   workspace.
