# Execution Model: Live Workers vs. Durable Tasks

## The Core Tension

NEEDLE workers are excellent at durable, async work: a bead is created, a worker picks it up, it runs to completion (or fails and retries), and the bead closes. The work survives crashes, spans hours, and leaves an audit trail.

Stream-dispatch intents are often the opposite: a user asks "is the options pipeline caught up?" and needs an answer in 3 seconds, not 3 minutes. Creating a bead for that is overhead — the round-trip through the bead lifecycle (create → pickup → process → close) adds latency and ceremony to something inherently ephemeral.

But some intents genuinely are tasks: "brainstorm names for the PDF tool", "draft the ADR for switching from Cloudflare R2 to B2", "summarize what changed in kalshi-weather this week." These take time, produce durable artifacts, and benefit from the retry/audit properties of beads.

**The router needs to classify intents by execution profile, not just by project.**

---

## Two Execution Profiles

### Live (query)

| Property | Value |
|----------|-------|
| Latency target | < 10 seconds |
| Durability needed | No |
| Retry on failure | No — just return an error card |
| Produces artifact | No (the card is ephemeral) |
| Examples | status checks, lookups, kubectl queries, "is X deployed?", "what are my open beads on Y?" |

Handled by **live workers**: long-running pods that hold a connection open, receive an intent via queue, fetch context, run a single LLM call, stream back a card spec. Stateless between intents.

### Task (deferred)

| Property | Value |
|----------|-------|
| Latency target | Minutes to hours |
| Durability needed | Yes |
| Retry on failure | Yes |
| Produces artifact | Often (doc, analysis, list, decision) |
| Examples | brainstorming, drafting, research, multi-step analysis, "go figure out X and report back" |

Handled by **task workers** (NEEDLE-compatible): a bead is created to represent the work; a worker picks it up, processes it, closes it. The result is attached to the bead. A card appears in the pane immediately as "pending" and updates when the bead resolves.

---

## Router Classification

The router adds an `execution_profile` field to each intent thread:

```
utterance → [Pass 1: topic/project detection]
           → [Pass 2: workflow template matching]
           → [Pass 3: execution profile classification]
                         │
              ┌──────────┴──────────┐
              ▼                     ▼
           live                  task
        (dispatch to          (create bead,
        live worker)          dispatch to
                              task worker)
```

Classification signals:
- **Live**: question words (is, has, what's, show me, how many), status verbs (running, deployed, synced), explicit time pressure ("quick check", "before I push")
- **Task**: creation verbs (draft, write, brainstorm, research, summarize, find, analyze), open-ended scope ("go figure out", "look into"), multi-step implied ("and then", "once you have that")
- **Ambiguous**: router surfaces a quick-select to the user: "Answer now (live) or work on it (task)?"

---

## The Pending Card

When a task intent creates a bead, the frontend receives a card immediately — but it's in pending state:

```
┌─────────────────────────────────────────────────────┐
│  pdftract naming                         [pending]  │
│  ─────────────────────────────────────────────────  │
│  Working on it...                                   │
│  bead: pdftract-0ab  ·  created 14s ago             │
│                                        [open bead ↗]│
└─────────────────────────────────────────────────────┘
```

When the bead closes, the card updates in-place:

```
┌─────────────────────────────────────────────────────┐
│  pdftract naming                       [complete]   │
│  ─────────────────────────────────────────────────  │
│  Candidates:                                        │
│  • Tractus — Latin root, implies pulling/extracting │
│  • Folio — page-first framing, domain-familiar      │
│  • Extrait — French, slightly more memorable        │
│  • Pulp — terse, memorable, slightly playful        │
│                                        [open bead ↗]│
└─────────────────────────────────────────────────────┘
```

The bead is the persistence layer. The card is just a view over it.

---

## NEEDLE Compatibility

NEEDLE workers process beads. Task-profile intents create beads. This means **existing NEEDLE workers can handle task intents with no changes** — as long as the bead is created with enough context for a NEEDLE worker to understand and execute it.

The bead body for a task intent becomes the agent prompt:

```
Title: Brainstorm names for pdftract
Type: research
Body:
  Context: jedarden/pdftract — a PDF text extraction tool with a Rust core,
  PyO3 bindings, and a CLI --serve mode. pdftract.com domain is available.
  
  Task: Generate 8-12 name candidates. For each: the name, a one-line
  rationale, and a domain availability note. Prefer short, memorable,
  extractable from the tool's function.
  
  Return format: markdown list, name as heading, rationale + availability as body.
```

A NEEDLE worker picks this up, runs it, closes the bead with the result attached. The stream-dispatch frontend watches for bead closure and updates the card.

The key addition needed: a **bead watcher** process that subscribes to bead close events and pushes card updates to the relevant SSE session.

---

## What This Means for Worker Design

### Live workers
- Stateless per intent (like NEEDLE workers, but for queries)
- No bead created — intent in, card spec out, done
- Can run anywhere with read access to the systems they query
- Scale horizontally; a pool of 3-5 is probably enough for interactive latency

### Task workers
- Already exist as NEEDLE workers
- Only change: bead body needs to carry enough context for the task (the router handles this at creation time)
- The result goes in the bead; the card update is triggered by bead closure

### Bead watcher (new, small)
- Polls or subscribes to bead close events
- Holds a map of `bead_id → session_id`
- When a bead closes, fetches the result, formats as a card spec, pushes to the SSE channel
- Stateless except for the in-flight `bead_id → session_id` map (can be Redis-backed)

---

## What Should NOT Become a Bead

Not every utterance deserves a bead, even for task-profile intents:

- **Transient brainstorms** the user will throw away anyway — maybe not worth the bead overhead
- **Status questions with slow answers** — "summarize this week's kalshi-weather changes" is borderline; it takes a minute but produces nothing durable
- **Follow-up questions** on an existing live card — these should extend the card's thread, not spawn new beads

The router should be conservative about bead creation. A pending card that resolves in 60 seconds is fine as a live intent with a longer timeout. Beads are for work that outlives the session or needs retry.

---

## Unified Worker Protocol

Despite the two execution paths, the protocol is the same from the frontend's perspective:

```
Intent dispatched
    │
    ├─ live path  →  card streams in within 10s
    └─ task path  →  pending card immediately, updates when bead closes

Card schema is identical in both cases:
{
  intent_id: string,
  session_id: string,
  title: string,
  type: "status" | "list" | "diff" | "pending" | "error" | ...,
  body_html: string,
  bead_ref?: string,   // only present for task-path cards
  timestamp: iso8601
}
```

The frontend doesn't need to know which path was taken. It just renders cards and handles updates.

---

## Open Questions

1. **Bead creation authority**: does the router create the bead directly (needs `br` access on this server), or does it ask a task-worker to create and self-assign it? The former is simpler; the latter keeps the router stateless.

2. **Session expiry vs. bead longevity**: what happens when the user closes the browser but a task bead is still running? The bead should complete regardless; when the user returns, the card should be visible in a session history view.

3. **Bead context portability**: NEEDLE workers run on the lab server too. If a task bead is picked up by a lab worker, it needs to be able to fetch context from the right systems. The bead body must be self-contained enough to not assume local file paths.

4. **Live worker timeout**: some "live" queries take longer than expected (kubectl on a struggling cluster, large git log). What's the timeout before a live intent auto-escalates to a task bead?

5. **Hybrid intents**: "check the options pipeline status, and if it's behind, draft a summary I can send" — live first leg, task second leg that depends on the live result. How does the router chain these?
