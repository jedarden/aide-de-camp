# Stream Dispatch

**A unified voice/text interface that ingests stream-of-consciousness input, routes it to project-aware agents, and renders results as dynamic HTML components.**

---

## Problem

Managing multiple active projects requires context-switching between dedicated tabs, terminals, or chat sessions. The cost is cognitive: before speaking to a project you must mentally locate it, open the right surface, and re-establish context. The input channel (typing into a specific Claude Code tab) is also the routing layer, and that conflation adds friction.

---

## Concept

A single web page you can speak or type into without caring which project you're addressing. Raw, unfiltered input ("has the options pipeline caught up? also I need to pick a name for the PDF tool and remind me what state the IBKR MCP is in") is ingested, fanned out to agents that hold or can fetch per-project context, and returned as structured HTML panels — one per answered thread — rendered live in the page.

```
┌────────────────────────────────────────────────────┐
│  Voice / Text Input                                 │
│  ┌──────────────────────────────────────────────┐  │
│  │  "has options pipeline caught up? what's the │  │
│  │   state of ibkr-mcp? name ideas for pdftract"│  │
│  └──────────────────────────────────────────────┘  │
│  [mic]  [send]                                      │
└────────────────────────────────────────────────────┘
         │
         ▼
┌────────────────────┐
│  Intent Router     │  ← LLM: splits utterance into N intent threads
│  (topic detection) │    tags each with project slug + intent type
└────────────────────┘
         │
   ┌─────┴──────┬──────────────┐
   ▼            ▼              ▼
[agent:        [agent:        [agent:
 options-       ibkr-mcp]      pdftract]
 pipeline]
   │            │              │
   ▼            ▼              ▼
 status        status         brainstorm
 card          card           card
         │
         ▼
┌────────────────────────────────────────────────────┐
│  Dynamic Pane                                       │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────┐ │
│  │ Options      │  │ IBKR MCP     │  │ pdftract │ │
│  │ pipeline     │  │ status       │  │ naming   │ │
│  │ [status card]│  │ [status card]│  │ [list]   │ │
│  └──────────────┘  └──────────────┘  └──────────┘ │
└────────────────────────────────────────────────────┘
```

---

## Key Components

### 1. Input Layer
- Web-based voice-to-text (Web Speech API or whisper-stt sidecar)
- Text fallback for the same surface
- Utterances are stamped, stored, and replayed (breadcrumb log)

### 2. Intent Router
- LLM pass that segments the utterance into N intent threads
- Each thread is tagged: `{project, intent_type, urgency}`
- Intent types: `status`, `action`, `brainstorm`, `lookup`, `reminder`
- Ambiguous threads ask for clarification before dispatching

### 3. Project Agents
- One agent per active project, or spawned on demand
- Each agent has a **context bundle**: recent beads, git log, k8s status, relevant files
- Agent fetches live state (kubectl, br, git) when needed for `status` intents
- Agent returns a **card spec**: structured JSON that describes what to render

### 4. Card Renderer
- Receives card specs; renders as web components in the pane
- Card types: `status`, `list`, `diff`, `timeline`, `qa`, `action-required`
- Cards are ephemeral by default; pinnable for session persistence
- Cards stream in as agents resolve — no waiting for all to finish

### 5. Context Memory
- Each spoken/typed utterance is logged with timestamp and project tags
- Agents can reference prior utterances for "what did I say about X last week?"
- Plugs into existing beads (`br`) for durable cross-session memory

---

## Interaction Model

### One-shot mode
Speak/type → router → agents run in parallel → cards render → done.

### Conversational mode
A card can spawn a follow-up prompt (e.g., "options pipeline is behind by 2h — want to check worker logs?"). Responding continues in the card's thread, not the global input.

### Ambient / push mode (stretch)
Background agents watch for events (CI failure, k8s crashloop, beads blocked) and push cards unsolicited. The page becomes a passive status surface, not just a query interface.

---

## Open Questions

1. **Routing accuracy** — how reliably can an LLM split a rambling utterance into clean project-tagged threads without over-splitting or under-splitting?

2. **Context bundle freshness** — agents need live state for useful status answers; how do you bound latency while still hitting kubectl/git/beads?

3. **Card schema** — what's the minimal set of card types that covers 90% of what gets asked? Too many types → render complexity; too few → agents contort output.

4. **Session vs. persistent state** — cards are ephemeral, but some output (a list of name candidates, a decision made) should survive a reload. What's the persistence model?

5. **Multi-agent parallelism** — each intent thread spins an agent; how many parallel agents are acceptable before the backend stalls? Need a concurrency budget.

6. **Integration surface** — agents need read access to: beads (br), git repos, k8s clusters (read-only proxy), possibly ArgoCD, possibly CI logs. How is auth handled cleanly?

7. **Voice input UX** — continuous listening vs. push-to-talk; silence detection; handling interruptions and corrections mid-utterance.

8. **Disambiguation flow** — when router isn't confident about project attribution, how does the clarification round-trip work without breaking flow?

---

## Design Notes

- [`cross-project-intents.md`](./cross-project-intents.md) — how the router handles utterances that span multiple repos (e.g., container image + declarative-config). Introduces the project graph and workflow template concepts.
- [`context-model.md`](./context-model.md) — centralized storage vs. centralized access paths; why a shallow registry + on-demand fetch avoids the surface area problem. Includes federated agent path for future distribution.
- [`dispatch-architecture.md`](./dispatch-architecture.md) — how agent execution scales beyond one server: queue-based dispatch to long-running worker pods on remote clusters, phased scaling path, security posture per phase.
- [`execution-model.md`](./execution-model.md) — live workers (query intents, <10s) vs. task workers (deferred intents, bead-backed). NEEDLE workers handle task-profile intents with no changes; a small bead watcher bridges bead closure to card updates.
- [`needle-strands.md`](./needle-strands.md) — corrected model: strands are bead selection strategies in a priority waterfall. Stream-dispatch uses a separate, shallow waterfall (Fetch → Synthesize → Escalate) invoked per intent thread, not the standard bead-draining waterfall.
- [`self-improvement.md`](./self-improvement.md) — the governing architectural principle: behavior lives in data (prompts, registry, components), not code. Hot-reload at every layer. Minimal dependencies via narrow interface contracts. The feedback → artifact update → hot-reload loop enables continuous improvement without deployment.
- [`responsiveness.md`](./responsiveness.md) — what makes the interface feel alive: partial results while loading, pre-warmed context, speculative pre-fetch, ambient monitoring, diff-aware results, multi-turn within topic, staleness indicators, notification batching, implicit feedback, usage pattern recognition. Prioritized by phase.
- [`component-library.md`](./component-library.md) — cached, versioned, self-growing component library. UI-regen agent selects, generates, and iterates HTML templates. Two-layer caching: rendered card cache (result × component × layout bucket) and the component library itself. Starts empty, grows from actual usage.
- [`topic-model.md`](./topic-model.md) — threads as the canvas UI primitive (not cards); topic creation, vague reference resolution, persistence scopes (session / cross-session / global); exceptions thread as fixed DLQ surface; audio navigation by topic label.
- [`primitives.md`](./primitives.md) — are beads still the right primitive? Yes for work items and HUMAN exceptions. No for sessions, surfaces, live intents, results, and utterance history — those belong in a lightweight session store (SQLite, 5 tables).
- [`session-model.md`](./session-model.md) — session as surface-agnostic persistent entity; surface routing rules; human-as-exception-handler (DLQ pattern); exception queue design; relationship to existing NEEDLE HUMAN beads.
- [`interaction-modes.md`](./interaction-modes.md) — two distinct surfaces: mobile/audio (AI talks back, Telegram or push-to-talk web) and multimedia/canvas (HTML card grid, no voice output). Same backend, same card spec, different last-mile renderers.
- [`resource-reuse.md`](./resource-reuse.md) — full map of existing resources reused: DUCK-E scaffolding, whisper-stt, NEEDLE workers, beads, telegram-claude-bridge, claude-governor, ZAI proxy, kubectl proxies. Net-new is ~1,400 lines of wiring.
- [`mayor-parallel.md`](./mayor-parallel.md) — stream-dispatch as a parallel Mayor: how this maps to the human interface adapter pattern from gascity-study research. Multiple stateless NEEDLE invocations (one per intent thread) instead of one compounding Mayor session.

---

## Related Research

- [`speech-to-code`](../speech-to-code/) — STT engines, voice-to-intent pipeline, context-aware command generation
- [`mission-control`](../mission-control/) — multi-agent observability system; overlap in agent orchestration patterns
- [`control-panel`](../control-panel/) — dashboard design, TUI patterns, conversational interface notes

---

## Implementation Sketch (phase 0 / prototype)

The simplest viable surface:

1. Single HTML page, textarea + mic button, Web Speech API for transcription
2. POST to a backend endpoint: `{utterance: string}`
3. Backend: one LLM call to split + tag threads, then N parallel Claude API calls (one per thread)
4. Each agent call returns JSON `{title, type, body_html}`
5. Frontend SSE stream: cards appear as agents resolve
6. No persistence, no auth, no ambient push — just the query loop

This is buildable in ~2 days and validates the core question: does the routing + parallel agent model actually reduce friction, or does it just move it?

---

## Stack Candidates

| Layer | Options |
|-------|---------|
| Frontend | Vanilla JS + Web Components, or Svelte for reactivity |
| STT | Web Speech API (zero-latency, browser-native) or whisper-stt (already deployed on ardenone-cluster) |
| Backend | FastAPI (Python) or Hono (TypeScript) — lightweight, SSE-friendly |
| Agent runtime | Claude API directly, or NEEDLE workers if parallelism gets complex |
| Persistence | SQLite for session log; beads for durable cross-session items |
| Hosting | Existing cluster (iad-options or apexalgo-iad) behind Tailscale |
