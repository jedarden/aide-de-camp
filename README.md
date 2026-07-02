# aide-de-camp

**A personal command interface.** Speak or type a stream-of-consciousness request — spanning multiple projects, questions, and tasks — and receive parallel, organized results on a live browser canvas or in audio.

CLI alias: `adc`

---

## How It Works

1. **Intent routing** — a single fast LLM call segments your utterance into typed intent threads, each tagged with a project, an intent type (`status`, `action`, `brainstorm`, `lookup`, `reminder`, `self-modification`, `monitoring-config`, `task-profile`), and an urgency level (`critical`, `high`, `normal`, `low`).

2. **Parallel dispatch** — all threads run concurrently. A compound utterance touching five projects takes as long as the slowest single agent, not their sum.

3. **Fetch strand** — each agent runs deterministic commands against live data sources (kubectl, git, local repos, SSH targets) to gather raw context for its thread.

4. **Synthesize strand** — one LLM call per thread converts the raw data into a 2–3 sentence structured result.

5. **Canvas delivery** — results stream to the browser via SSE and render as HTML cards, one per topic, updated in place as agents resolve.

```
  Voice / Text Input
  "has the pipeline caught up? also what's the ibkr mcp status?"
                        │
                        ▼
             ┌──────────────────┐
             │   Intent Router  │  ← one LLM call, splits utterance
             └──────────────────┘
                        │
          ┌─────────────┴──────────────┐
          ▼                            ▼
   [agent: pipeline]           [agent: ibkr-mcp]
   Fetch → Synthesize           Fetch → Synthesize
          │                            │
          └──────────────┬─────────────┘
                         ▼
              ┌─────────────────────────┐
              │  Canvas (SSE)           │
              │  ┌─────────┐ ┌───────┐  │
              │  │pipeline │ │ibkr   │  │
              │  │ card    │ │ card  │  │
              │  └─────────┘ └───────┘  │
              └─────────────────────────┘
```

**Task intents** (`task` type) skip fetch/synthesize. Instead, a work item is created and picked up asynchronously by an async worker fleet. When the work completes, the result is pushed to the canvas via the bead watcher daemon.

---

## Features

### Input methods
- **Text**: browser canvas at `http://localhost:8000/` or CLI: `adc dispatch "..."`
- **Voice**: OpenAI Realtime API (WebRTC) — speak directly into the browser

### Live canvas
Single-page dark-themed UI (`src/canvas/index.html`). Results stream in via Server-Sent Events. Each distinct topic (project + intent) gets its own card, updated in place as results arrive. No page reload needed.

### Voice narration
Results are narrated at urgency-tiered conversational pauses:
- `critical` — interrupt immediately
- `high` — next natural pause
- `normal` — batched delivery
- `low` — only when idle

### Self-modification and hot-reload
All behavior-defining artifacts are plain files, re-read on every invocation:
- `prompts/router.md`, `prompts/synthesize.md`, `prompts/voice.md`, `prompts/urgency.md`
- `config/registry.yaml` — project and alias definitions
- `config/monitoring.yaml` — ambient monitoring rules
- `data/components.db` — versioned HTML/CSS card templates (SQLite)

A spoken instruction like "the deploy card is too cluttered" triggers the `SelfModificationAgent`, which generates a diff, surfaces it for approval, and hot-reloads the artifact. No redeploy needed.

### Project registry
`config/registry.yaml` defines explicit project entries with cluster targets, namespaces, aliases, and workflow templates. aide-de-camp also auto-discovers git repos at startup. Refresh via `POST /api/v1/environment/refresh`.

### Session persistence
Session state lives in a SQLite WAL database (`data/session.db`). Tables: `sessions`, `surfaces`, `utterances`, `intents`, `topics`, `results`. The same session is accessible from the canvas, CLI, or audio mode simultaneously.

---

## Quick Start

```bash
# Clone and install
git clone <repo-url> aide-de-camp
cd aide-de-camp

pip install -e ".[dev]"
# or
pip install -r requirements.txt

# Start the server
uvicorn src.main:app --host 0.0.0.0 --port 8000

# Verify it's running
curl -s http://localhost:8000/health
```

Open `http://localhost:8000/` in your browser to use the canvas.

For voice mode, an OpenAI API key with Realtime API access is required (set `OPENAI_API_KEY`).

---

## CLI Usage

```bash
# Route an utterance and stream results to the canvas
adc dispatch "has the options pipeline caught up?"

# Query a specific topic
adc ask "what name candidates did we have for pdftract?"

# Current session summary
adc status

# List active topic cards
adc topics

# Show exception queue
adc exceptions

# Configure the CLI
adc config --set-server http://myhost:8000
adc config --set-session <session-id>

# Help
adc --help
```

---

## Configuration

### Environment variables

| Variable | Purpose | Default |
|----------|---------|---------|
| `OPENAI_API_KEY` | OpenAI key — required for voice/Realtime API | _(none; voice disabled without it)_ |
| `ZAI_PROXY_URL` | ZAI proxy endpoint for LLM calls (routing and synthesis) | `https://zai-proxy-mcp-apexalgo-iad-ts.ardenone.com:8444/v1/messages` |
| `ADC_SERVER_URL` | Server URL used by the `adc` CLI | `http://localhost:8000` |
| `ADC_TELEGRAM_BRIDGE_URL` | Telegram bridge URL for async task notifications | `https://telegram-proxy-telegram-bridge-ardenone-cluster-ts.ardenone.com:8444` ✓ |

The LLM backend for intent routing and synthesis is configured via the `ZAI_PROXY_URL` environment variable. All LLM calls route through the ZAI proxy.

### Prompts directory

All prompts are hot-reloaded on every invocation. Edit these files to tune behavior without restarting the server:

| File | Purpose |
|------|---------|
| `prompts/router.md` | Intent classification and thread segmentation |
| `prompts/synthesize.md` | Result synthesis (raw data → 2–3 sentence summary) |
| `prompts/voice.md` | Narration style and pacing |
| `prompts/urgency.md` | Urgency classification rules |

### Project registry

`config/registry.yaml` defines the projects aide-de-camp knows about. Each entry specifies:
- `name` and `aliases` — how the router maps utterance fragments to projects
- `cluster` and `namespace` — where to run kubectl-based fetch commands
- `workflow_templates` — named multi-step workflows (e.g., "deploy", "rollback")

---

## Architecture

### Key source files

| File | Responsibility |
|------|---------------|
| `src/main.py` | FastAPI app; `/dispatch`, `/voice`, `/sse` endpoints |
| `src/intent/router.py` | LLM classification and parallel thread dispatch |
| `src/fetch/commands.py` | Fetch command matrix per intent type |
| `src/fetch/orchestrator.py` | Parallel fetch execution |
| `src/synthesize/strand.py` | LLM synthesis strand |
| `src/session/store.py` | SQLite session store (aiosqlite) |
| `src/sse/broadcaster.py` | SSE connection registry and event routing |
| `src/canvas/index.html` | Canvas single-page app |
| `src/realtime/session.py` | OpenAI Realtime API voice session |
| `src/watcher/daemon.py` | Async work-item watcher — pushes completed results to canvas |
| `src/agents/self_modification.py` | Self-improvement agent |
| `src/environment/discovery.py` | Local and remote repo scanner |
| `config/registry.yaml` | Explicit project registry |
| `prompts/` | Hot-reload prompt files |

### Runtime breakdown

| Runtime | Used for |
|---------|---------|
| Realtime API | Voice model (persistent session, voice I/O) |
| Configurable LLM backend | Intent router, synthesize strand |
| Deterministic code | Fetch strand (kubectl/git execution), bead watcher |
| Async worker fleet | UI-regen agent, self-modification agent, background analysis, task work items |

### Data flow

```
POST /dispatch
  → intent router (LLM classify)
  → N parallel: fetch strand → synthesize strand
  → persist: topic + result in session.db
  → broadcast SSEEvent("result_created", surface_id)
  → canvas calls GET /api/v1/sessions/{id}/topics
  → cards rendered / updated in place
```

---

## Requirements

- Python 3.11+
- `fastapi`, `uvicorn[standard]`, `httpx`, `websockets`, `pydantic`, `aiosqlite`
- Dev: `pytest`, `pytest-asyncio`, `ruff`

---

## Versioning

Version is in `pyproject.toml` only. No CI build — runs from source.

Release: bump version in `pyproject.toml` → commit → `git tag vX.Y.Z` → push.
