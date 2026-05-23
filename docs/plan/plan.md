# aide-de-camp: Application Plan

## Overview

aide-de-camp is a universal personal interface that accepts stream-of-consciousness voice and text input, routes it to parallel agents across any domain, and renders results as a live canvas of HTML cards or as synthesized audio narration. It is built on top of existing personal infrastructure and improves itself through conversational feedback after initial bootstrap.

CLI invocation: `adc`

---

## Problem Statement

Managing multiple active projects requires constant context-switching between dedicated tabs, terminals, and chat sessions. The input channel (typing into a specific Claude Code tab) is also the routing layer, and that conflation adds cognitive overhead. The same problem extends beyond coding: research, lookups, personal context, reminders — anything that requires knowing which system to ask before you can ask it.

aide-de-camp eliminates that overhead by providing a single input surface that routes automatically, dispatches in parallel, and returns organized results without requiring the user to know where to ask.

---

## Core Architecture

### The Hot Path

```
User utterance (voice or text)
  → STT transcription (Web Speech API or whisper-stt)
  → Intent Router (one LLM call, haiku-class, ~500ms)
      output: [{project_slug, intent_type, urgency, utterance_fragment}, ...]
  → N parallel Fetch+Synthesize workers (one per intent thread)
      Fetch: deterministic code, executes command matrix based on intent_type
      Synthesize: one LLM call per thread (sonnet-class, ~1-2s)
      output: {data, summary, urgency}
  → Results streamed via SSE to active canvas
  → Cards rendered client-side using component templates
```

Target: < 3 seconds from utterance to first partial result on canvas. No Claude Code session startup on this path.

### The Async Path

```
Task-profile intent (research, coding, long-running work)
  → NEEDLE task bead created (br create)
  → Existing Claude Code workers pick up bead normally
  → Bead watcher detects closure event
  → Result written to session store results table
  → SSE push to active canvas (or Telegram if no canvas)
```

### The Self-Improvement Path

```
Feedback signal (explicit instruction or implicit engagement pattern)
  → Self-modification agent (Claude Code via NEEDLE task bead)
      reads target artifact (prompt file, registry YAML, component template)
      generates update
      surfaces diff to user
  → User approves → artifact written → hot-reloaded on next invocation
```

---

## Components

### 1. Intent Router

**Runtime:** Direct API call (haiku-class via ZAI proxy)

One LLM call per utterance. Receives the full utterance text, the project registry, and a segmentation prompt. Returns a JSON array of intent threads, each tagged with:

```json
[
  {
    "project_slug": "options-pipeline",
    "intent_type": "status",
    "urgency": "normal",
    "utterance_fragment": "has the options pipeline caught up?"
  },
  {
    "project_slug": "ibkr-mcp",
    "intent_type": "status",
    "urgency": "normal",
    "utterance_fragment": "what's the state of the ibkr mcp"
  }
]
```

Intent types: `status`, `action`, `brainstorm`, `lookup`, `reminder`, `self-modification`, `monitoring-config`

The router reads its segmentation prompt and the project registry from disk on each call — no caching. Hot-reload is automatic.

Ambiguous intents: if confidence is below threshold, router returns an `intent_type: "clarification"` thread. The voice model or canvas handles the clarification round-trip before dispatching.

### 2. Project Registry

**Format:** YAML file, read per-invocation by the router

Defines projects the router knows about:

```yaml
projects:
  options-pipeline:
    aliases: ["the pipeline", "options"]
    description: "Options data pipeline on apexalgo-iad"
    cluster: apexalgo-iad
    namespace: options
    intent_support: [status, action, brainstorm]
    workflows:
      deploy:
        steps: [ci-status, image-tag, argocd-sync, pod-status]

  ibkr-mcp:
    aliases: ["ibkr", "the mcp"]
    description: "IBKR MCP server"
    cluster: apexalgo-iad
    namespace: ibkr-mcp
    intent_support: [status, brainstorm, lookup]
```

Updated by the self-modification agent. Hot-reloaded on every router call.

### 3. Fetch Strand

**Runtime:** Deterministic code, no LLM

Executes a command matrix based on `intent_type` and the project's registry entry. No LLM decisions — the commands are determined by the intent type and project config.

Example command matrix for `intent_type: status`:

| Source | Command |
|--------|---------|
| Pod status | `kubectl get pods -n {namespace}` |
| ArgoCD sync | `curl argocd-ro-api/applications/{app}` |
| Git log | `git -C {repo_path} log -10 --oneline` |
| Bead list | `br list --project {slug} --status open` |
| CI status | `kubectl get workflows -n argo-workflows -l project={slug}` |

Results are structured data passed to the Synthesize strand. Fetch runs each source concurrently; partial results (from sources that respond first) are passed to Synthesize incrementally to support streaming output.

A `fetch_coverage` field tracks which sources succeeded and which failed. Failed sources are surfaced as caveats in the result.

### 4. Synthesize Strand

**Runtime:** Direct API call (sonnet-class via ZAI proxy)

Takes `{intent_spec, fetched_context}` → produces `{data, summary}`.

- `data`: structured JSON matching the component library's expected schema for this intent type
- `summary`: 1-3 sentence narration suitable for audio mode

Single-turn inference. Reads its system prompt from a file per invocation (hot-reload). The synthesize prompt is the highest-leverage artifact in the system — it defines result format, detail level, and what fields to include.

Runs once per intent thread in parallel across all active threads.

### 5. Escalate Strand

**Runtime:** Direct API call + `br create`

For task-profile intents that need durable async handling:
1. One LLM call to formulate a bead body from the intent + context
2. `br create` to create the bead in the appropriate project
3. Returns a pending-card spec with the bead reference

The bead watcher subsequently bridges bead closure to result delivery.

### 6. Voice Model

**Runtime:** Realtime API (OpenAI or Claude Realtime, persistent session)

The conversational layer. Receives transcribed utterances (or audio directly), calls `dispatch_intent()` tool to trigger routing, and narrates results at appropriate moments.

Tool calls are triggers, not queries. `dispatch_intent()` returns an acknowledgment immediately; results arrive out-of-band and are surfaced by the voice model at natural conversational pauses.

The voice model's system prompt controls narration style, batching behavior, urgency handling, and multi-turn topic tracking. Read per session-turn from a file (hot-reload).

In audio mode there is no canvas. The voice model reads `result.summary` directly. When a user transitions from audio to canvas, pending results are rendered using the component library and appear on canvas — session continuity means the canvas catches up.

### 7. UI-Regen Agent

**Runtime:** Claude Code via NEEDLE (task bead)

Steward of the component library. Given a result's data shape:
1. Finds the best-fit existing component (semantic match against component descriptions)
2. If no good fit, generates a new component from scratch and stores it
3. Applies the component template to result data accounting for layout bucket
4. On feedback, iterates the component (updates library, triggers canvas re-render)

Multi-step: reads library, generates or selects, writes back. Claude Code's file access and tool use make this the right runtime.

Created as a task bead; not on the hot path. Canvas updates in place when a component is versioned (SSE push: `component_updated: {component_id, version}`).

### 8. Self-Modification Agent

**Runtime:** Claude Code via NEEDLE (task bead)

Reads and writes the artifacts that encode system behavior:
- Router prompt (`prompts/router.md`)
- Project registry (`config/registry.yaml`)
- Strand prompts (`prompts/fetch.md`, `prompts/synthesize.md`, etc.)
- Urgency classifier prompt (`prompts/urgency.md`)
- Voice model prompt (`prompts/voice.md`)
- Monitoring config (`config/monitoring.yaml`)
- Exception routing rules (`config/exceptions.yaml`)

Workflow for every modification:
1. Read current artifact
2. Understand intent of change
3. Generate updated artifact
4. Surface diff to user (in canvas or narrated in audio mode)
5. On approval: write artifact, hot-reload takes effect on next invocation
6. On rejection: discard

Safety model:
- Diffs before every application — no silent changes
- All artifacts versioned; any update can be rolled back with one instruction
- Confidence threshold: unambiguous changes (adding an alias) can auto-apply with notification; structural changes always require explicit approval

### 9. Background Analysis Bead

**Runtime:** Claude Code via NEEDLE (task bead, low priority)

Runs on a schedule. Reads intent history and engagement signals from the session store, identifies patterns, proposes artifact updates.

Examples:
- "User consistently drills into status results for more detail → propose adding causality fields to synthesize prompt"
- "User ignores pipeline monitoring pushes for 5 days → propose lowering urgency tier"
- "After deploy status, user always asks about pod logs within 2 minutes → propose speculative pre-fetch"

Proposals are surfaced as cards on canvas for user review. Auto-apply only above a high confidence threshold.

### 10. Bead Watcher

**Runtime:** Daemon process, no LLM

Watches for bead close events from NEEDLE workers. On close:
1. Reads `session_id` from closed bead metadata
2. Looks up active surface in session store
3. Writes result to `results` table
4. Fires SSE push to canvas or Telegram push if no canvas active

Pure I/O. Runs as a long-running process (Deployment, not a K8s Job per infrastructure conventions).

---

## Data Model

### Session Store (SQLite)

```sql
sessions (
  id          TEXT PRIMARY KEY,
  created_at  INTEGER,
  last_active INTEGER,
  primary_surface_id TEXT
)

surfaces (
  id              TEXT PRIMARY KEY,
  session_id      TEXT,
  type            TEXT,  -- 'canvas' | 'telegram' | 'audio'
  state           TEXT,  -- 'active' | 'idle' | 'disconnected'
  always_available INTEGER DEFAULT 0,  -- 1 for Telegram
  last_seen       INTEGER
)

utterances (
  id          TEXT PRIMARY KEY,
  session_id  TEXT,
  raw_text    TEXT,
  created_at  INTEGER
)

intents (
  id           TEXT PRIMARY KEY,
  utterance_id TEXT,
  session_id   TEXT,
  topic_id     TEXT,
  project_slug TEXT,
  intent_type  TEXT,
  status       TEXT,  -- 'pending' | 'dispatched' | 'resolved' | 'cancelled'
  bead_ref     TEXT,  -- set for task-profile intents
  created_at   INTEGER,
  resolved_at  INTEGER
)

results (
  id          TEXT PRIMARY KEY,
  intent_id   TEXT,
  topic_id    TEXT,
  session_id  TEXT,
  summary     TEXT,
  data        TEXT,  -- JSON
  urgency     TEXT,  -- 'critical' | 'high' | 'normal' | 'low'
  created_at  INTEGER,
  surfaced_at INTEGER,
  acked_at    INTEGER
)

topics (
  id           TEXT PRIMARY KEY,
  label        TEXT,
  type         TEXT,  -- 'project' | 'research' | 'personal' | 'exception'
  project_slugs TEXT,  -- JSON array
  scope        TEXT,  -- 'session' | 'cross-session' | 'global'
  session_id   TEXT,  -- null for cross-session/global
  created_at   INTEGER,
  last_active  INTEGER,
  archived_at  INTEGER
)

intent_topics (
  intent_id TEXT,
  topic_id  TEXT,
  PRIMARY KEY (intent_id, topic_id)
)
```

### Component Library (SQLite, separate DB)

```sql
components (
  id            TEXT PRIMARY KEY,
  name          TEXT,
  description   TEXT,
  html_template TEXT,
  version       INTEGER,
  created_at    INTEGER,
  last_used     INTEGER,
  usage_count   INTEGER
)

component_versions (
  component_id  TEXT,
  version       INTEGER,
  html_template TEXT,
  created_at    INTEGER,
  change_note   TEXT,
  PRIMARY KEY (component_id, version)
)

card_cache (
  result_id         TEXT,
  component_id      TEXT,
  component_version INTEGER,
  layout_bucket     TEXT,  -- 'compact' | 'normal' | 'expanded'
  rendered_html     TEXT,
  created_at        INTEGER,
  PRIMARY KEY (result_id, component_id, layout_bucket)
)
```

---

## File System Layout

```
aide-de-camp/
├── adc                      ← CLI entry point (shell script or compiled binary)
├── config/
│   ├── registry.yaml        ← project registry (hot-reloaded by router)
│   ├── monitoring.yaml      ← ambient monitoring rules
│   └── exceptions.yaml      ← exception routing rules
├── prompts/
│   ├── router.md            ← intent segmentation prompt
│   ├── synthesize.md        ← result generation prompt
│   ├── voice.md             ← voice model system prompt
│   ├── urgency.md           ← urgency classification prompt
│   └── fetch/               ← per-intent-type fetch instructions
│       ├── status.md
│       ├── action.md
│       └── ...
├── src/
│   ├── router/              ← intent segmentation (direct API call)
│   ├── fetch/               ← fetch strand (deterministic, per intent type)
│   ├── synthesize/          ← synthesize strand (direct API call)
│   ├── escalate/            ← escalate strand (bead creation)
│   ├── watcher/             ← bead watcher daemon
│   ├── session/             ← session store (SQLite)
│   ├── canvas/              ← web frontend (SSE consumer, card renderer)
│   └── cli/                 ← adc CLI
├── data/
│   ├── session.db           ← session store
│   └── components.db        ← component library
└── docs/
    ├── research/            ← architecture and design research
    ├── plan/
    │   └── plan.md          ← this file
    └── notes/
        └── naming.md
```

---

## Technology Stack

| Layer | Choice | Reason |
|-------|--------|--------|
| Backend | FastAPI (Python) | Reuse DUCK-E scaffolding; SSE support; async-native |
| STT | Web Speech API → whisper-stt fallback | Zero-latency browser-native; whisper-stt already deployed |
| Voice session | OpenAI Realtime API (via DUCK-E session handler) | DUCK-E scaffolding is already built on this |
| LLM calls | ZAI proxy (`llm-proxy.ardenone.com`) | Pay-per-token, no subscription pressure on hot path |
| Task workers | NEEDLE + Claude Code | Existing infrastructure, unchanged |
| Session store | SQLite | Lightweight, local, additive-only schema |
| Frontend | Vanilla JS + Web Components | No build pipeline needed for a personal tool |
| Hosting | ardenone-cluster or iad-options | Behind existing Tailscale ingress |

---

## Implementation Phases

### Phase 0 — Minimal Viable Surface (~2 days)

Validates the core question: does routing + parallel dispatch reduce friction?

- Single HTML page: textarea + mic button (Web Speech API)
- `POST /dispatch` endpoint: router → N parallel synthesize calls → SSE stream
- Results appear as basic cards as agents resolve
- No persistence, no auth, no component library, no ambient push

Deliverable: the core query loop working end-to-end.

### Phase 1 — Session and Topics (~1 week)

Results persist; the canvas has memory.

- Session store (SQLite, 7 tables)
- Topic model: canvas shows one card per active topic, updated in place
- Telegram surface fallback (reuse telegram-claude-bridge)
- Bead watcher: closed NEEDLE beads push results to active surface
- Workload summary on reconnect
- Staleness indicators on cards

Deliverable: sessions that survive browser refresh; Telegram fallback working.

### Phase 2 — Self-Improvement Loop (~2 weeks)

The interface can be improved by talking into it.

- Self-modification agent (Claude Code via NEEDLE)
- Hot-reload confirmed at every artifact layer
- Component library: UI-regen agent generates first components from actual result shapes
- Canvas live-updates when a component is versioned
- Explicit feedback processed: "always include X" → prompt updated → hot-reloaded

Deliverable: at least one end-to-end self-modification cycle working (user instructs change, diff surfaced, approved, takes effect without redeploy).

### Phase 3 — Responsiveness (~2-3 weeks)

The interface feels alive, not just reactive.

- Ambient monitoring: active topics watched for state changes
- Diff-aware results: show what changed since last result
- Pre-warmed context: active topics refreshed in background every N minutes
- Multi-turn within topic: follow-up questions deepen current topic context
- Speculative pre-fetch: common follow-up patterns pre-fetched
- Notification batching in audio mode
- Implicit feedback signals fed to background analysis bead

Deliverable: monitoring fires unprompted for a watched topic; follow-up questions are visibly faster.

### Phase 4 — Audio Surface (~1-2 weeks)

Full audio mode via Realtime API.

- Realtime API voice session replaces text input path
- Tool-as-trigger model: `dispatch_intent()` returns ack, result arrives async
- Urgency-tiered voice narration
- Audio-to-canvas session continuity

Deliverable: full voice session with canvas catch-up on surface switch.

---

## Self-Improvement: Hot-Reload Architecture

Every artifact that encodes behavior is readable, writable, and reloaded per-invocation:

| Behavior | Artifact | Reload point |
|----------|----------|-------------|
| Utterance segmentation | `prompts/router.md` | Each router call |
| Intent→project routing | `config/registry.yaml` | Each router call |
| Context fetch strategy | `prompts/fetch/{type}.md` | Each fetch invocation |
| Result format and detail | `prompts/synthesize.md` | Each synthesize call |
| Voice narration style | `prompts/voice.md` | Each session turn |
| Urgency classification | `prompts/urgency.md` | Each escalate call |
| Visual rendering | Component library (DB) | Each card render |
| Monitoring rules | `config/monitoring.yaml` | Each monitoring tick |

Per-invocation reload is the implementation strategy (read file, check mtime). File watching adds complexity for no benefit — prompts change rarely and file reads are cheap.

---

## Surface Routing Rules

When a result is ready to surface, the bead watcher or synthesize strand uses this priority:

1. The surface the utterance originated from (if still connected)
2. Most recently active connected surface
3. Any connected surface
4. Telegram (always-available fallback)

Exception-class results (urgency: critical, type: exception) push to Telegram regardless of canvas state if no canvas has been active within the past N minutes.

---

## Relationship to Existing Infrastructure

aide-de-camp adds a routing and rendering layer on top of existing infrastructure without replacing any of it:

- **NEEDLE workers** — unchanged. Task beads work exactly as before. The bead watcher is a new daemon that observes bead closure events.
- **telegram-claude-bridge** — reused for Telegram surface and HUMAN bead push delivery.
- **whisper-stt** — already deployed on ardenone-cluster; available as STT backend.
- **ZAI proxy** — all direct API calls (router, synthesize, escalate) route through `llm-proxy.ardenone.com`.
- **claude-governor** — governs subscription token consumption for self-modification and UI-regen task beads.
- **DUCK-E** — FastAPI scaffolding, WebSocket handling, OpenAI Realtime API session management, and middleware reused as the voice layer foundation.
- **beads (br CLI)** — task work items and HUMAN exceptions only. Conversational session state lives in a separate SQLite session store.
- **kubectl proxies** — fetch strand uses existing kubectl proxy access per cluster.
- **ArgoCD read-only proxy** — fetch strand reads ArgoCD application state via `argocd-ro-ardenone-manager-ts.ardenone.com:8444`.

Net-new code: approximately 1,400 lines of wiring across router, strand waterfall, bead watcher, session store, and canvas frontend.

---

## Security Model

- aide-de-camp runs on the Hetzner server; all cluster access via read-only kubectl proxies (same as existing tooling)
- No cluster credentials stored by aide-de-camp; existing proxy infrastructure holds them
- Self-modification agent writes only to the `prompts/` and `config/` directories within the repo
- All artifact changes go through diff-review before application
- Rollback available for any artifact via version history

---

## Open Questions

1. **Routing accuracy** — how reliably can a haiku-class model split a rambling multi-project utterance into clean tagged threads? What's the false-split / under-split rate in practice?

2. **Context latency** — can the fetch strand reliably hit kubectl + ArgoCD + git + beads within a 2-3s window? Which sources need timeouts and what's the degraded-result behavior?

3. **Component selection** — when does the UI-regen agent generate a new component vs. stretch an existing one? How is "good enough" match defined?

4. **Concurrency budget** — how many parallel synthesize calls can the ZAI proxy handle without queue pressure affecting the <3s target?

5. **Topic vague reference resolution** — "the pipeline" vs. "options pipeline" vs. "options-pipeline". When does the router resolve from context vs. ask for clarification?

6. **Voice UX** — push-to-talk vs. continuous listening + VAD silence detection. What's the right default for the audio surface?

7. **Disambiguation flow** — when router confidence is below threshold, how does the clarification round-trip work without breaking conversational flow in audio mode?
