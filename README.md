# aide-de-camp

**A universal personal interface. Speak or type stream-of-consciousness input across any domain — projects, research, lookups, personal context — and receive parallel, organized results on a live canvas or in audio.**

CLI invocation: `adc`

---

## The Problem

Managing multiple active projects means constant context-switching: open the right tab, re-establish context, ask the question, wait, switch to the next project, repeat. The input channel — typing into a specific session — is also the routing layer, and that conflation is the friction.

Beyond projects: the same friction applies to research, personal notes, lookups, reminders, and anything else that requires knowing where to ask. You shouldn't have to know where to ask.

---

## What aide-de-camp Does

You speak or type without caring which project, domain, or system you're addressing:

> "Has the options pipeline caught up? Also what's the state of the IBKR MCP, and remind me what name candidates we had for pdftract."

aide-de-camp:
1. Segments the utterance into intent threads and tags each with project and intent type
2. Dispatches each thread to a parallel agent — one per thread, all running concurrently
3. Each agent fetches live context (kubectl, git, beads, personal notes) and produces a structured result
4. Results render as HTML cards on a live canvas, appearing as agents resolve
5. In audio mode, results are narrated at natural conversational pauses

No switching. No routing by hand. One surface for everything.

```
┌─────────────────────────────────────────────────────┐
│  Voice / Text Input                                  │
│  "has options pipeline caught up? ibkr mcp status?" │
└─────────────────────────────────────────────────────┘
                          │
                          ▼
               ┌──────────────────┐
               │   Intent Router  │  ← one LLM call, splits utterance
               │   (haiku-class)  │    tags each thread: project + intent_type
               └──────────────────┘
                          │
            ┌─────────────┴──────────────┐
            ▼                            ▼
     [agent: options-pipeline]   [agent: ibkr-mcp]
     Fetch → Synthesize           Fetch → Synthesize
            │                            │
            ▼                            ▼
      status card                  status card
                          │
                          ▼
┌─────────────────────────────────────────────────────┐
│  Canvas                                             │
│  ┌─────────────────┐   ┌─────────────────┐         │
│  │ options-pipeline │   │ ibkr-mcp        │         │
│  │ [status card]   │   │ [status card]   │         │
│  └─────────────────┘   └─────────────────┘         │
└─────────────────────────────────────────────────────┘
```

---

## Key Properties

### Universal scope
Not a coding assistant. Research, lookups, project status, personal context, reminders, brainstorming — any intent type the router can classify, any agent can handle.

### Parallel dispatch
Each intent thread runs concurrently. A compound utterance touching five projects takes as long as the slowest single agent, not the sum of all five.

### Self-improving through conversation
After initial bootstrap, the interface improves itself by talking into it:

- "Always include pod restart count in status cards" → synthesize prompt updated, hot-reloaded
- "You always route 'the feed' to the wrong project" → registry alias added
- "The deploy card is too cluttered" → UI-regen agent iterates the component
- "Start monitoring the pipeline and tell me if it goes behind" → monitoring rule created

No IDE switch. No PR. No deployment. The improvement loop collapses into the usage loop.

### Hot-reload everywhere
All behavior lives in data — prompt files, YAML registry, HTML component templates — not compiled code. Every artifact is read per-invocation. A change takes effect on the next utterance.

### Two surfaces, one backend
- **Canvas (multimedia)**: HTML card grid, no voice output, results stream in as they resolve
- **Audio (mobile/Telegram)**: AI narrates results, no visual output, tool calls are triggers not queries
- Same result schema. Same session. Switch surfaces mid-session without losing state.

### Human as exception handler
The system handles everything automatically. Genuine blockers — decisions only the user can make — are routed to an exception queue and pushed to Telegram or the canvas exception thread. Everything else resolves without interruption.

---

## Architecture Overview

### Hot path (< 3 seconds to first partial result)

```
Voice/text input
  → STT (Web Speech API or whisper-stt)
  → Intent Router (one direct API call, haiku-class)
  → N parallel Fetch+Synthesize strands (direct API calls, sonnet-class)
  → SSE stream to canvas
```

No Claude Code session startup on the critical path. All direct API calls via ZAI proxy.

### Async path (task beads, not time-critical)

```
Task intent (research, coding, long-running work)
  → NEEDLE task bead created
  → Claude Code worker picks up bead
  → Bead watcher detects closure
  → Result pushed to canvas via SSE or Telegram
```

### Self-improvement path (async, off critical path)

```
Feedback (explicit instruction or implicit signal)
  → Self-modification agent (Claude Code via NEEDLE)
  → Reads artifact → generates update → shows diff
  → User approves → artifact written → hot-reloaded
```

### Agent runtimes

| Runtime | Components |
|---------|-----------|
| Realtime API | Voice model (persistent session, voice I/O) |
| Direct API via ZAI | Intent router, Synthesize strand, Escalate strand |
| Deterministic code | Fetch strand (kubectl/git/br execution), Bead watcher |
| Claude Code via NEEDLE | UI-regen agent, Self-modification agent, Background analysis, Task beads |

---

## Session and State Model

**Session**: surface-agnostic persistent entity. The same session is accessible from the canvas, Telegram, or audio mode simultaneously. Switching surfaces does not reset context.

**Topic**: a persistent concern (a project, a research thread, a recurring question). The canvas shows one card per active topic, updated in place as new results arrive.

**Result**: stored structured data (`{data, summary, urgency}`). Persists in the session store.

**Card**: ephemeral rendering artifact. Generated from a result by the UI-regen agent using a component template. Not stored — regenerated as needed.

**Component library**: versioned HTML/CSS templates generated by the UI-regen agent from actual usage. Starts empty, grows organically. Components are iterated when feedback (explicit or implicit) indicates they're serving poorly.

---

## Self-Improvement: What Can Be Changed Through Conversation

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

---

## CLI

`adc` is the CLI invocation for aide-de-camp.

```bash
# Dispatch a text utterance (bypasses web UI)
adc dispatch "has the options pipeline caught up?"

# Query a specific topic
adc ask "what name candidates did we have for pdftract?"

# Check active session status
adc status

# List active topics
adc topics

# Show exception queue
adc exceptions
```

---

## Repository Structure

```
aide-de-camp/
├── README.md
├── docs/
│   ├── research/          ← architecture and design research
│   │   ├── overview.md          — system concept, components, open questions
│   │   ├── agent-runtimes.md    — which runtime powers each component
│   │   ├── component-library.md — cached, versioned, self-growing UI components
│   │   ├── context-model.md     — shallow registry + on-demand fetch
│   │   ├── cross-project-intents.md — project graph, workflow templates
│   │   ├── dispatch-architecture.md — queue-based dispatch, scaling path
│   │   ├── execution-model.md   — live vs. task profile, bead watcher
│   │   ├── interaction-modes.md — canvas vs. audio surfaces
│   │   ├── mayor-parallel.md    — parallel Mayor pattern, Gas City validation
│   │   ├── mayor-parallel-gascity-update.md — May 2026 Gas City state
│   │   ├── needle-strands.md    — corrected strand model, dispatch waterfall
│   │   ├── primitives.md        — what uses beads vs. session store
│   │   ├── resource-reuse.md    — existing infrastructure reused
│   │   ├── responsiveness.md    — latency, awareness, conversational quality
│   │   ├── self-improvement.md  — hot-reload, feedback loop, safety model
│   │   ├── session-model.md     — surface routing, DLQ exception model
│   │   └── topic-model.md       — topic/intent/result/card hierarchy
│   ├── plan/
│   │   └── roadmap.md           — phased implementation plan (Phase 0–4)
│   └── notes/
│       └── naming.md            — why aide-de-camp, why adc
```

---

## What Requires Code vs. Conversation

### Requires a code change and deploy
- New context-fetch integrations (new APIs, new data sources)
- New tool implementations for NEEDLE workers
- Initial bootstrap (Phase 0 implementation)

### Reachable through conversation after bootstrap
- All prompt tuning (router, synthesize, voice model, urgency classifier)
- Project registry (aliases, new projects, workflow templates)
- Component iteration (layout, fields, visual design)
- Monitoring rules and urgency thresholds
- Exception routing configuration

---

## Relationship to Existing Infrastructure

aide-de-camp is built on top of existing infrastructure, not alongside it:

- **NEEDLE workers** — task beads unchanged; aide-de-camp adds a bead watcher to route closed-bead results to the canvas
- **telegram-claude-bridge** — reused as always-available surface fallback and HUMAN bead push
- **whisper-stt** — already deployed on ardenone-cluster; used as STT backend in audio mode
- **ZAI proxy** (`llm-proxy.ardenone.com`) — all direct API calls (router, synthesize, escalate) route through this
- **claude-governor** — governs Claude Code subscription consumption for self-modification and UI-regen task beads
- **DUCK-E** — FastAPI scaffolding, WebSocket handling, and OpenAI Realtime API session management reused as the voice layer foundation
- **beads (br CLI)** — task work items and HUMAN exceptions; session conversational state lives in a separate SQLite session store

Net-new code: approximately 1,400 lines of wiring across router, strand waterfall, bead watcher, session store, and canvas frontend.
