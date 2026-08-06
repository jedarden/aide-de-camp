# aide-de-camp — Agent Instructions

## What This Is

FastAPI server providing a voice/text → intent routing → parallel fetch+synthesize → SSE canvas pipeline. Runs locally on the Hetzner server at port 8000.

## Running the Server

> **Use the repo venv (`.venv/bin/python`), never bare system `python3`.**
> This host runs NixOS. The system `python3` (`/run/current-system/sw/bin/python3`, 3.12) ships **no pip, fastapi, uvicorn, httpx, or pytest** — they are not Nix-managed, so a `nixos-rebuild` wipes them. Deps live only in the project venv, which is git-ignored and must be recreated after a rebuild. Running `python3 -m uvicorn ...` (the old command) fails with `No module named uvicorn`. Always invoke `.venv/bin/python` (or activate the venv) instead.

### One-time setup (or after a NixOS rebuild)

```bash
# From /home/coding/aide-de-camp/
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
```

This installs fastapi, `uvicorn[standard]`, httpx, websockets, pydantic, aiosqlite (runtime) plus pytest, pytest-asyncio, ruff (dev), and the `src` package itself in editable mode, all from `pyproject.toml`.

Verify it took:

```bash
.venv/bin/python -c "import fastapi, uvicorn, httpx, pydantic, aiosqlite; print('deps OK')"
.venv/bin/pytest --collect-only -q   # should collect ~60+ tests
```

### One-time systemd setup

```bash
# From /home/coding/aide-de-camp/
mkdir -p ~/.config/systemd/user
ln -sT $(pwd)/deploy/aide-de-camp.service ~/.config/systemd/user/aide-de-camp.service
systemctl --user daemon-reload
systemctl --user enable aide-de-camp  # auto-start on login
```

The symlink ensures changes to the repo copy are reflected after `daemon-reload`.

### Start / restart / stop

```bash
# Start the service
systemctl --user start aide-de-camp

# Restart (graceful shutdown via SIGINT, then start)
systemctl --user restart aide-de-camp

# Stop (graceful shutdown via SIGINT)
systemctl --user stop aide-de-camp

# Check status
systemctl --user status aide-de-camp

# View logs (live)
journalctl --user -u aide-de-camp -f

# Health check (expect HTTP 200 + {"status":"ok","service":"adc-voice"})
curl -s http://localhost:8000/health
```

Logs are written to `/tmp/adc.log` (StandardOutput/StandardError) and systemd journal (accessible via `journalctl`). Root logging in `src/main.py` is visible at INFO level in both.

**Crash recovery:** The unit uses `Restart=on-failure` with 5-second backoff. If the process exits uncleanly (uncaught exception, OOM, etc.), systemd automatically restarts it.

## Keeping the Live Checkout Synced

The live checkout on the Hetzner server can drift from `origin/main` when commits are pushed from other locations (e.g., local machines, CI). Periodic syncs prevent merge conflicts and ensure the server runs the latest code.

### Checking current divergence

```bash
# Check if local HEAD is ahead of origin (unpushed local commits)
git log origin/main..HEAD --oneline

# Check if local HEAD is behind origin (unpulled remote commits)
git log HEAD..origin/main --oneline

# Full status (shows branch, diverging commits, uncommitted changes)
git status -sb
```

### Recommended sync frequency

**Sync before every release** — make it step 0 in the version bump checklist. This ensures the release tag is created from a fully-updated checkout.

Additional syncs are recommended:
- After any CI auto-bump (e.g., `chore: bump to vX.Y.Z` commits from declarative-config)
- Before starting new work that will create a release branch
- Weekly if the repo is active across multiple machines

### Safe merge procedure

**Always sync before creating a release tag.** The procedure:

```bash
# 1. Check for uncommitted changes (including .beads/)
git status

# 2. If .beads/ has uncommitted changes, flush them first
bf sync --flush-only

# 3. Commit any other uncommitted changes
git commit -am "WIP: pre-sync commit"

# 4. Fetch latest from origin
git fetch origin

# 5. Merge origin/main into local main
git merge origin/main -m "Merge origin/main into main"

# 6. Push the merge commit
git push origin main
```

This sequence guarantees:
- All `.beads/` state is preserved in the checkpoint
- No local work is lost
- `origin/main` is integrated into local history
- The merge commit is visible in the git log for attribution

### Handling .beads/ uncommitted changes

`.beads/` is git-ignored but contains live state (`beads.db`, `events.jsonl`). Before any sync:

```bash
# Flush the checkpoint (db → issues.jsonl)
bf sync --flush-only

# Verify the checkpoint is current
git log -1 .beads/issues.jsonl

# Proceed with sync
```

**Never** run `bf doctor --repair` before a sync without flushing first — repair rebuilds the db from the JSONL checkpoint and will destroy any unflushed beads.

## Versioning

**Every meaningful push must bump the version and cut a git tag.**

Version lives in `pyproject.toml` → `[project] version`. At startup, `src/main.py` reads it via `tomllib` and passes it to FastAPI — the canvas header badge reads from `/openapi.json` which reflects this. **Do not hardcode the version anywhere else.**

### Scheme: semantic versioning (`MAJOR.MINOR.PATCH`)

- `PATCH` — bug fixes, pipeline corrections, prompt tweaks
- `MINOR` — new features, new intent types, new fetch sources, UI additions
- `MAJOR` — architectural changes, breaking API changes

### Release checklist

0. **Sync with origin** — See [Keeping the Live Checkout Synced](#keeping-the-live-checkout-synced)
1. Edit `pyproject.toml` — bump `version`
2. Commit: `git commit -m "chore: bump to vX.Y.Z"`
3. Tag: `git tag vX.Y.Z`
4. Push: `git push origin main --tags`

There is no CI build for adc — it runs directly from source. The tag is the release.

## Architecture

```
utterance (text or voice)
  → POST /dispatch
  → intent router (ZAI LLM classify)
  → N parallel: fetch strand → synthesize strand
  → persist: topic + result in session.db
  → broadcast SSEEvent(event_type="result_created", target_surface_id=...)
  → canvas SSE listener calls loadTopics()
  → GET /api/v1/sessions/{session_id}/topics → cards rendered
```

Key files:
- `src/main.py` — FastAPI app, `/dispatch` endpoint, SSE broadcaster wiring
- `src/intent/router.py` — LLM classification → fetch+synthesize → store persistence
- `src/fetch/commands.py` — fetch command matrix, intent types, data structures
- `src/fetch/orchestrator.py` — concurrent fetch execution with streaming and coverage tracking (FetchStrand implementation)
- `src/synthesize/strand.py` — LLM synthesis into structured result
- `src/session/store.py` — SQLite session store (aiosqlite); `data/session.db`
- `src/sse/broadcaster.py` — SSE connection registry and event routing
- `src/canvas/index.html` — single-page canvas UI

## ZAI Proxy

All LLM calls go through the ZAI proxy at:

```
https://zai-proxy-mcp-apexalgo-iad-ts.ardenone.com:8444/v1/messages
```

Set via `ZAI_PROXY_URL` env var; default is the above. The vpn-wildcard-tls cert on the Traefik entrypoint is self-signed from Traefik's perspective — all httpx clients must use `verify=False`.

**GLM-4.7 wraps all JSON responses in ` ```json ... ``` ` markdown fences.** Strip them before `json.loads()`:

```python
raw = response.strip()
if raw.startswith("```"):
    raw = raw.split("\n", 1)[-1]
    raw = raw.rsplit("```", 1)[0].strip()
result = json.loads(raw)
```

The proxy also wraps the Anthropic response envelope under a `"result"` key. Unwrap with `data.get("result", data)` before accessing `content`/`usage`/`model`.

## Session Store

- `get_store()` is **synchronous** — do not `await` it
- `find_or_create_topic()` returns `(topic_id: str, created: bool)` — always unpack
- Topic `type` must be one of `('project', 'research', 'personal', 'exception', 'compound')` — map intent types before passing
- `create_utterance(session_id, raw_text, utterance_id=None)` — `utterance_id` is optional

## SSE Broadcaster

Canvas listens for `"result_created"` and `"topic_updated"` events. Broadcast with:

```python
from src.sse import get_broadcaster, SSEEvent

broadcaster = get_broadcaster()
await broadcaster.broadcast(
    SSEEvent(
        event_type="result_created",
        target_surface_id=surface_id,
        data={...}
    )
)
```

SSEEvent supports optional targeting filters:
- `target_session_id` — only send to connections for this session
- `target_surface_id` — only send to this specific surface
- `exclude_surface_id` — send to all surfaces except this one

## Canvas Dispatch Contract

The canvas sends `surface_id` with every dispatch POST — required for SSE targeting:

```javascript
body: JSON.stringify({ utterance, session_id: sessionId, surface_id: surfaceId })
```

The canvas fetches topics from `/api/v1/sessions/{session_id}/topics` on SSE `result_created`.
