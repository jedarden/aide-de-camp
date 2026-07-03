# aide-de-camp — Agent Instructions

## What This Is

FastAPI server providing a voice/text → intent routing → parallel fetch+synthesize → SSE canvas pipeline. Runs locally on the Hetzner server at port 8000.

## Running the Server

```bash
# From /home/coding/aide-de-camp/
nohup python3 -m uvicorn src.main:app --host 0.0.0.0 --port 8000 > /tmp/adc.log 2>&1 &

# Restart (kill then start)
kill -2 $(ps aux | grep "uvicorn src.main" | grep -v grep | awk '{print $2}') 2>/dev/null; true
nohup python3 -m uvicorn src.main:app --host 0.0.0.0 --port 8000 > /tmp/adc.log 2>&1 &

# Health check
curl -s http://localhost:8000/health
```

Logs go to `/tmp/adc.log`. Root logging is configured in `src/main.py` — all `src.*` module loggers are visible at INFO level.

## Versioning

**Every meaningful push must bump the version and cut a git tag.**

Version lives in `pyproject.toml` → `[project] version`. At startup, `src/main.py` reads it via `tomllib` and passes it to FastAPI — the canvas header badge reads from `/openapi.json` which reflects this. **Do not hardcode the version anywhere else.**

### Scheme: semantic versioning (`MAJOR.MINOR.PATCH`)

- `PATCH` — bug fixes, pipeline corrections, prompt tweaks
- `MINOR` — new features, new intent types, new fetch sources, UI additions
- `MAJOR` — architectural changes, breaking API changes

### Release checklist

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

There are **two SSEEvent classes** — do not mix them:

- `src/sse/broadcaster.py` → `SSEEvent(event_type: str, data: dict, target_surface_id=...)` — **use this one** for broadcasting
- `src/sse/events.py` → `SSEEvent(type: EventType, data: dict)` — legacy, used internally

Canvas listens for `"result_created"` and `"topic_updated"` events. Broadcast with:

```python
await _broadcaster.broadcast(
    SSEEvent(
        event_type="result_created",
        target_surface_id=surface_id,
        data={...}
    )
)
```

## Canvas Dispatch Contract

The canvas sends `surface_id` with every dispatch POST — required for SSE targeting:

```javascript
body: JSON.stringify({ utterance, session_id: sessionId, surface_id: surfaceId })
```

The canvas fetches topics from `/api/v1/sessions/{session_id}/topics` on SSE `result_created`.
