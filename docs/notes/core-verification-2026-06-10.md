# Core Verification — Go / No-Go

**Epic:** adc-1sb (Core verification: confirm ADC end-to-end function before any new integrations)
**Baseline stated:** 2026-06-10
**This run:** 2026-07-19 (server pid 2169279, `.venv`, host `127.0.0.1:8000`)
**Verdict:** **CONDITIONAL GO** — text/SSE-canvas core is green and reproducible; voice/narration half is blocked purely on the `OPENAI_API_KEY` secret being unset, plus a human gate.

---

## Core function under test

```
utterance (text or voice)
  → POST /dispatch
  → intent router (one ZAI LLM call)
  → N parallel: fetch strand → synthesize strand
  → persist (topic + result in session.db)
  → broadcast SSE result_created → canvas reloads topics → HTML cards
  → (voice only) OpenAI Realtime audio narration
```

## Summary matrix

| # | Strand | Status | Evidence |
|---|--------|--------|----------|
| 0 | Python runtime (adc-unlu P0) | ✅ GREEN | `.venv` present: fastapi 0.139.2, uvicorn 0.51.0, httpx 0.28.1, aiosqlite, pytest 9.1.1. System python3 has no pip but the venv covers the app. |
| 1 | Smoke: server, /health, canvas, SSE (adc-dmu) | ✅ GREEN | `docs/notes/core-verification-evidence.md` (20 runs). Reconfirmed live: `/health`→`{"status":"ok"}`, `/`→200 HTML, SSE `/api/v1/sse` streams `connected`/`workload_summary`/`topic_cards`. |
| 2 | ZAI proxy (was 503 on `llm-proxy.ardenone.com`) | ✅ GREEN | Now repointed to `https://zai-proxy-mcp-apexalgo-iad-ts.ardenone.com:8444/v1/messages` (`src/escalate/llm.py:22`). Direct probe → HTTP 200, model `glm-4.7`, replied `PONG`. |
| 3 | Text path E2E: dispatch → router → synthesize → card via SSE | ✅ GREEN | `result_created` SSE received with `topic_id` + `summary`. See "Text path" below. |
| 4 | Parallel fan-out: multi-intent → multiple cards | ✅ GREEN | 2-intent utterance → 2 distinct `result_created` events, each with own topic_id + synthesized summary. |
| 5 | Voice path: /voice WS → STT → narration | ❌ NO-GO | `OPENAI_API_KEY` unset; `/voice` WS closes 1011 "OpenAI API key not configured" (`src/main.py:254`). OpenAI proxy infra is UP (`openai-proxy.ardenone.com:8444`→200) but realtime-session path returns "Invalid URL" — needs investigation once key is provisioned. |
| 6 | Memory extraction on voice turn completion | ❌ NO-GO | Depends on a voice turn completing; voice can't run (item 5). Memory client uses `OPENAI_PROXY_URL` (not direct api.openai.com as the baseline claimed). |
| 7 | Real-microphone + audio narration listening | ⛔ HUMAN | Requires a human with a mic to drive `/voice` and listen to narration (adc-jr35, blocked). Cannot be automated. |

## Text path (item 3) — detailed evidence

Driven via `test_e2e.py` against the running server. With `surface_id` included in the dispatch POST (per the CLAUDE.md canvas contract), the full chain fires:

```
POST /dispatch {utterance, session_id, surface_id}
  → router.classify_utterance  → ZAI POST …/v1/messages  200 OK
  → orchestrator.execute_fetch → 6/6 sources, 100%
  → synthesize_intent          → ZAI POST …/v1/messages  200 OK  ("3 data fields")
  → store.create_result        → persisted (GET /topics shows result_count: 1)
  → broadcaster.broadcast(result_created, target_surface_id=surface_id)
SSE client receives: event: result_created  data:{intent_id, topic_id, summary, urgency}
```

Example synthesized summary (single intent): *"The repo is active with 8 documentation commits in the last few minutes, focused on thread-safety design…"* — accurate against live git history.

Parallel fan-out (item 4) example: utterance "status of aide-de-camp repo AND status of forge repo" → router returned 2 intents → 2 `result_created` events, summaries *"10 commits in the last few hours…"* and *"forge repo is active on the main branch with a merge…"*.

## Harness fix committed this run

`test_e2e.py` previously omitted `surface_id` from the `/dispatch` POST. `/dispatch` only broadcasts `result_created` when `surface_id` is present (`src/main.py:523`, guard `if _broadcaster and surface_id`). The harness therefore reported a false `FAIL — no result_created within 30s` even though results persisted and the pipeline was healthy. Fixed to send `surface_id`; `test_e2e.py` now exits 0 / PASS.

This was the single highest-signal finding: it masqueraded as a core-pipeline failure across 20+ smoke runs that only ever exercised the surface layer (health/canvas/SSE-connect) and never proved dispatch→card.

## Blockers to full GO

1. **`OPENAI_API_KEY` unset** — gates `/voice` (`src/main.py:254`) and the memory-extraction path. Infrastructure (OpenAI proxy) is reachable; this is secret provisioning, not a code defect.
2. **Realtime-session routing** — `POST /v1/realtime/sessions` via `openai-proxy.ardenone.com:8444` returns "Invalid URL (POST /v1/realtime/sessions)". Confirm the proxy is meant to serve Realtime before declaring voice unblocked.
3. **Human microphone gate** — adc-jr35; cannot be closed by automation.

## Notes for downstream work

- Out of scope here, observed only: the bead dependency graph for this epic is not wired (`br dep tree adc-1sb` → "no dependencies"); adc-4ksl tracks that. Closing this epic does not require resolving it.
- `src/sse/events.py` is absent (adc-2qg3) — affects `component_updated` push / `test_phase2.py` import, not the `result_created` path verified here.
- Whisper-STT on ardenone-cluster is not wired into the fallback path (baseline item 3) — irrelevant while `OPENAI_API_KEY` blocks voice entirely.

## Re-verified on epic close (2026-07-19, run adc-1sb)

The closure run independently re-ran the live checks rather than trusting the matrix above (same server, pid 2169279, `OPENAI_API_KEY` still unset):

- **Item 1 (smoke):** `curl /health` → `{"status":"ok","service":"adc-voice"}`; `/` → 200. ✅
- **Item 3 (text path):** `test_e2e.py "status of the aide-de-camp repo"` → `PASS — result_created received`; summary accurate against live git log ("10 commits in the last hour… runtime restored via venv"). Router made one ZAI call, orchestrator 6/6 sources, one synthesized result persisted. ✅
- **Item 4 (fan-out):** `test_e2e.py "…aide-de-camp repo AND …forge repo"` → router returned **2 intents** (451953c8…, 521d804e…), `PASS — result_created received`. ✅
- **Item 5 (voice) blocker re-confirmed external:** `/voice` guard `api_key = os.getenv("OPENAI_API_KEY")` (`src/main.py:254`) → WS closes 1011 with the key unset. `src/memory/store.py` and `src/realtime/session.py` route through `OPENAI_PROXY_URL` but still require a Bearer `api_key`. All three are gated on the same unprovisioned secret — not a code defect. ❌ (unchanged)

Text → router → parallel fetch+synthesize → live SSE canvas is end-to-end green and reproducible. Voice/narration remains blocked on `OPENAI_API_KEY` provisioning + the human microphone gate (adc-jr35/adc-5zs).

## How to reproduce this run

```bash
cd /home/coding/aide-de-camp
nohup .venv/bin/python -m uvicorn src.main:app --host 127.0.0.1 --port 8000 > /tmp/adc.log 2>&1 &
# single intent (exits 0 on PASS)
.venv/bin/python test_e2e.py "status of the aide-de-camp repo"
# health / canvas / SSE
curl -s http://127.0.0.1:8000/health
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8000/
```

## Verdict

**GO** on the text → intent-router → parallel fetch+synthesize → live SSE canvas pipeline. It is end-to-end functional and reproducible (ZAI proxy up, results persist, `result_created` pushes cards).

**NO-GO** on the audio-narration half of the core function — blocked on `OPENAI_API_KEY` provisioning (not a code bug) and a human microphone gate. New integrations (PBX/telephony et al.) remain deferred until voice is unblocked and the human gate is cleared, per the epic scope.
