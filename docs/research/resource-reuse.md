# Existing Resource Reuse Map

## Summary

Nearly every component needed already exists. The net-new work is thin: a new
strand waterfall config for NEEDLE, a bead watcher process (~100 lines), and
wiring between existing pieces. The infrastructure, voice layer, LLM proxy,
worker runtime, persistence, networking, and deployment pipeline are all present.

---

## DUCK-E: The Interface Scaffolding

DUCK-E (`jedarden/duck-e`) is the strongest reuse candidate for the frontend and
backend. It already solves the hardest parts of the voice interface:

| DUCK-E capability | Stream-dispatch need |
|---|---|
| FastAPI + WebSocket backend | ✅ Same stack needed |
| WebRTC voice session (browser ↔ server) | ✅ Voice input layer |
| `register_tool` pattern per session | ✅ Context-fetch tools (kubectl, git, br) |
| `UserMemoryStore` (per-session + persistent) | ✅ Session history for vague references |
| Cost protection + rate limiting middleware | ✅ Guards parallel NEEDLE invocations |
| Jinja2 templates + static file serving | ✅ Card renderer frontend |
| Containerized, already in CI pipeline | ✅ Deployment model reused directly |

**What changes from DUCK-E:**

1. **LLM provider**: DUCK-E uses OpenAI Realtime API. Stream-dispatch uses Claude
   via the ZAI proxy (`llm-proxy.ardenone.com`) for all LLM calls. The Realtime
   API WebRTC session for voice is replaced by Web Speech API (browser-native,
   zero server latency) or whisper-stt for transcription.

2. **Response model**: DUCK-E returns one sequential voice/text response. Stream-dispatch
   fans out to N parallel NEEDLE invocations and streams card specs back as each
   resolves. The WebSocket becomes an SSE-style card stream, not a conversation stream.

3. **Tool execution**: DUCK-E tools run inline in the session. Stream-dispatch tools
   (kubectl, git log, br list) are called by NEEDLE agents, not the session directly.
   The DUCK-E `register_tool` pattern maps to the context-fetch layer available to
   each NEEDLE invocation.

**What stays identical**: FastAPI app structure, WebSocket session management,
middleware stack, memory model, container build pipeline.

---

## whisper-stt: Voice Input

Already deployed on ardenone-cluster. Stream-dispatch routes audio through
whisper-stt for transcription instead of using the OpenAI Realtime API or
the browser's Web Speech API.

Two options:
- **Web Speech API** (browser-native): zero server round-trip, works offline,
  no whisper-stt involved. Good for high-responsiveness.
- **whisper-stt sidecar**: higher accuracy, language-agnostic, handles technical
  vocabulary better. Route audio from DUCK-E's WebRTC handler to whisper-stt
  before the router sees it.

Existing whisper-stt deployment handles the second option with no new infra.

---

## NEEDLE: The Worker Runtime

Already running on this server and the lab server. For stream-dispatch:

- **Task-profile intents**: create a `stream-task` labeled bead; existing NEEDLE
  workers pick it up. No NEEDLE changes required for this path.
- **Live-profile intents**: invoke NEEDLE with a stream-dispatch strand waterfall
  (`Fetch → Synthesize → Escalate`). One invocation per intent thread, in parallel.
  Requires a new NEEDLE config file and two new system prompts.

The same binary handles both modes. The lab server's NEEDLE workers handle task beads
without any changes.

---

## Beads (br): Persistence

Already the persistence layer. Two new uses:

1. **`stream-task` bead type**: task-profile intents become beads with `session_id`
   embedded in the body. Existing NEEDLE workers process them. No `br` changes needed.

2. **Session history**: prior turns stored as lightweight beads (or a dedicated
   SQLite table alongside `.beads/`). Segment strand reads these to resolve
   vague references ("that thing from earlier").

---

## telegram-claude-bridge: Push Notifications

Already a deployed human interface adapter
([needle-human-interface.md](../gascity-study/mayor/needle-human-interface.md) identified
this). Reuse directly for:

- HUMAN bead push: when a worker creates a HUMAN bead, Telegram notifies
- Pending card escalation: when a stream-task bead completes and the browser
  session is gone, push the result to Telegram instead
- Fleet alerts: worker crashes, queue exhaustion

No changes to the bridge. The bead watcher emits to both SSE (browser) and
Telegram depending on whether the session is active.

---

## claude-governor: Capacity Management

Already monitors Claude Code subscription usage and scales workers. For stream-dispatch:

- Parallel NEEDLE invocations (N per utterance) consume subscription capacity
- claude-governor already governs this — stream-dispatch just needs to respect
  its scale-down signals before spawning invocations
- Prevents a burst of utterances from exhausting the usage window

No changes. The governor already does the right thing; stream-dispatch invocations
are just more NEEDLE workers from its perspective.

---

## ZAI Proxy: LLM Calls

Already configured at `llm-proxy.ardenone.com`. All LLM calls in stream-dispatch
go through it:

- Router segmentation call (fast, haiku-class model)
- NEEDLE agent synthesis calls (sonnet-class model, one per thread)
- Task-dispatch bead formulation (if used)

No changes. ZAI proxy rate limiting is another layer of protection alongside
claude-governor.

---

## kubectl Proxies + ArgoCD: Context Sources

All clusters already accessible read-only:
- `http://traefik-apexalgo-iad:8001` — options pipeline, kalshi
- `http://traefik-ardenone-cluster:8001` — ardenone apps
- `http://traefik-iad-options:8001` — options cluster
- `https://argocd-ro-ardenone-manager-ts.ardenone.com:8444` — ArgoCD read-only

NEEDLE live-query agents call these directly for status intents. No new access setup.

---

## declarative-config + ArgoCD: Deployment

Stream-dispatch components deploy the same way as every other service:

1. Add `k8s/apexalgo-iad/stream-dispatch/` to `jedarden/declarative-config`
2. ArgoCD syncs automatically
3. Stream-dispatch is a Deployment (not a Job — consistent with existing convention)

No new deployment infrastructure.

---

## iad-ci: Build Pipeline

Add a `stream-dispatch-build` WorkflowTemplate to `k8s/iad-ci/argo-workflows/`.
Same pattern as `duck-e-build`, `kalshi-tape-build`, etc.

---

## Full Resource Map

```
User (browser)
  │
  │ voice (Web Speech API or whisper-stt)
  │ text fallback
  ▼
DUCK-E scaffolding (FastAPI + WebSocket)  ← reused, modified
  ├─ UserMemoryStore                        ← reused unchanged
  ├─ cost protection middleware             ← reused unchanged
  ├─ rate limiting middleware               ← reused unchanged
  │
  ▼
Router (new, ~200 lines)
  ├─ ZAI proxy → Claude (haiku)            ← ZAI reused, new prompt
  ├─ project-registry.yaml                  ← new, ~200 lines YAML
  │
  ├─[live intent]──────────────────────────────────────────────┐
  │   NEEDLE invocation (stream-dispatch waterfall)            │
  │   ├─ kubectl proxy (read-only)          ← reused           │
  │   ├─ git log (local repos)              ← reused           │
  │   ├─ br list                            ← reused           │
  │   └─ ArgoCD read-only proxy             ← reused           │
  │   ZAI proxy → Claude (sonnet)           ← ZAI reused       │
  │   → card spec → SSE → DUCK-E frontend  ← DUCK-E reused    │
  │                                                            │
  ├─[task intent]──────────────────────────────────────────────┤
  │   br create (stream-task label)         ← reused           │
  │   NEEDLE workers (existing)             ← reused unchanged │
  │   → bead closes                                            │
  │   Bead watcher (new, ~100 lines)                           │
  │   ├─ SSE push (if session active)       ← DUCK-E reused    │
  │   └─ Telegram push (if session gone)    ← bridge reused    │
  │                                                            │
  └─ claude-governor (capacity gate)        ← reused unchanged │
                                                               │
  Card renderer (DUCK-E frontend, extended) ← reused, extended ┘
```

---

## What Is Actually Net-New

| Component | Size | Notes |
|---|---|---|
| Router | ~200 lines Python | Utterance → intent threads → dispatch |
| Project registry | ~200 lines YAML | Project slugs, endpoints, workflow templates |
| NEEDLE stream-dispatch config | ~50 lines TOML | New waterfall: Fetch → Synthesize → Escalate |
| Fetch strand | ~150 lines Rust | kubectl/git/br context fetch with deadline |
| Synthesize strand | ~100 lines Rust | LLM call → card spec |
| Escalate strand | ~80 lines Rust | Overflow → bead creation |
| Bead watcher | ~100 lines Python | Bead close → SSE/Telegram push |
| Card renderer (frontend) | ~300 lines JS | Card spec → HTML components |
| DUCK-E modifications | ~200 lines Python | Swap OpenAI → whisper-stt/Web Speech, add parallel dispatch |

Total net-new: roughly 1,400 lines across existing repos plus the project registry YAML.
Everything else is configuration and wiring of what already exists.
