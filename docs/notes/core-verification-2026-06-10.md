# Core Verification Go/No-Go Report

**Report Date:** 2026-08-11  
**Actual Verification Dates:** 2026-06-10 through 2026-08-10  
**Repository:** /home/coding/aide-de-camp  
**Epic:** adc-1sb (Core verification: confirm ADC end-to-end function before any new integrations)

---

## Executive Summary: GO-WITH-CAVEATS

**Verdict:** **GO-WITH-CAVEATS** for ADC core function.

**Rationale:** The minimum bar for GO-WITH-CAVEATS is met: text path dispatch and fan-out execute successfully with results persisted and cards rendered. Voice and memory paths require `OPENAI_API_KEY` for full verification and remain UNIT-LEVEL VERIFIED only. Asterisk/PBX integration stays deferred as previously agreed.

---

## Per-Path Verification Status

| Path | Bead ID | Status | Details |
|------|---------|--------|---------|
| **Smoke** | adc-dmu | ✅ **PASS** | All 20 runs passed. Server starts cleanly, `/health` returns 200, canvas serves HTML, modern+legacy SSE endpoints connect and stay open ≥3s, surface registration generates UUIDs, shutdown clean. |
| **Text** | adc-3rt | ⚠️ **PASS WITH DEFECTS** | Router → fetch → synthesize → result persistence → SSE/card rendering works (9.00s E2E). **Defects:** (1) SSE `result_created` payload omits `data` field (HTML present as `rendered_html`). (2) Persistent `intents` row remains `status=pending` with store-generated ID, while `results` uses separate routed intent ID. (3) Existing database migration issue: `dispatch_timings` lacks `session_id` column, requiring manual migration fix. |
| **Fan-out** | adc-1ua | ⚠️ **PASS WITH DEFECTS** | Multi-intent utterance produces 2 concurrent agent cards (3.4ms apart). Parallel execution confirmed (both syntheses started before either completed). **Defects:** Same ID/status wiring issues as text path (missing SSE `data`, persistent intent `pending`, ID mismatch). |
| **Voice** | adc-4iq | ❌ **UNTESTABLE** | No `OPENAI_API_KEY` available. Graceful degradation verified (factory returns `None`, no exceptions), but actual voice turn with STT → response → narration → memory extraction could not be exercised. |
| **Memory** | adc-zec | ⚠️ **UNIT-LEVEL VERIFIED** | 58 tests pass (42 persistence + 16 extraction). Wiring verified (handler created, callback assigned, event-driven invocation). Graceful degradation without API key confirmed. **Integration NOT VERIFIED:** Requires voice bead with `OPENAI_API_KEY` to confirm actual memory file creation from real voice turns. |
| **Human** | adc-5zs | ❌ **NOT VERIFIED** | Real-microphone voice turn + listen to narration + visual canvas check pending. Blocked by missing `OPENAI_API_KEY`. |

---

## Environment Blockers and Owners

| Blocker | Impact | Owner | Resolution Path |
|--------|--------|-------|-----------------|
| **Missing `OPENAI_API_KEY`** | Blocks voice path verification (adc-4iq), integration-level memory verification (adc-zec), human verification (adc-5zs). All show UNTTESTABLE/NOT VERIFIED. | User | Set `OPENAI_API_KEY` environment variable. Key should be available from OpenAI dashboard or internal secrets store. |
| **Database schema drift** | Text path verification exposed `dispatch_timings` table missing `session_id` column. Current `SCHEMA_SQL` creates index before additive migration, causing `sqlite3.OperationalError: no such column: session_id`. | adc-3rt | Manual migration was applied locally during verification. Proper fix: update `SCHEMA_SQL` to include nullable column before index creation, or add versioned migration path. |
| **ID/status wiring defect** | `/dispatch` creates `intents` row with store-generated ID, `route_utterance()` creates separate `RoutedIntent.intent_id`. Result returns `status: resolved` but never updates persistent `intents.status`. Results/timings use routed ID, intents table uses store ID. | TBD ( adc-3rt follow-up) | Fix contract between store and router: either (1) use store ID throughout, or (2) update intents row with routed ID and status on completion. |

---

## How ADC Runs

**Current Deployment Model: Phase 0 (Local Development)**

- **Runtime:** Local uvicorn on Hetzner server (`python3 -m uvicorn src.main:app --host 127.0.0.1 --port 8000`)
- **Process Management:** Ad-hoc manual start/stop. No systemd unit, no tmux session, no k8s deployment.
- **Cluster Deployment:** Nothing deployed to Kubernetes. No declarative-config manifests exist for ADC.
- **Persistence:** SQLite database at `data/session.db` + memory files at `data/memory/session_*.json`
- **Configuration:** Environment variables (`ZAI_PROXY_URL`, `OPENAI_API_KEY` optional)

**Recommendation:** Before further integration work, ADC should get a systemd user service for reliable restart-on-failure and log persistence. Tmux session is acceptable but systemd is more robust. No k8s work needed until Phase 1 (if ever).

---

## Asterisk/PBX Integration Status

**Explicit Statement:** Asterisk/PBX integration remains **DEFERRED** until this verdict is GO or the user overrides. No PBX verification beads were part of this epic. All voice path work used fixture audio only.

---

## Bugs Found and Follow-up Beads

| Bug | File:Line | Description | Follow-up Bead |
|-----|-----------|-------------|-----------------|
| Missing SSE `data` field | src/main.py (SSE event construction) | `result_created` SSE payload lacks `result["data"]` field. HTML present as `rendered_html`, but raw JSON data missing from client-visible event. | None yet (recorded in adc-3rt close comment) |
| Persistent intent status mismatch | src/main.py, src/session/store.py | `intents.status` remains `pending` despite successful resolution. Result dict returns `resolved` but never updates persistent row. ID mismatch between store-generated intent ID and routed intent ID. | None yet (recorded in adc-3rt close comment) |
| Database schema drift | Schema SQL migration order | `dispatch_timings` table missing `session_id` column in existing databases. Current `SCHEMA_SQL` creates index before column exists, causing migration failure. | None yet (manual fix applied during adc-3rt) |
| Whisper STT fallback never implemented | Original voice spec | Fallback to local STT when cloud service unavailable was never implemented. Voice path untestable without `OPENAI_API_KEY` anyway, but this remains an incomplete feature. | None yet (deferred) |

---

## Detailed Evidence References

**Smoke Tests (adc-dmu):** 20 independent runs, all passing. Full evidence in `docs/notes/core-verification-evidence.md` (lines 5-2105). Tests covered:
- Server startup (no lifespan errors)
- GET /health (200 OK, correct JSON)
- GET / (canvas, text/html)
- POST /api/v1/surfaces/register (UUID generation)
- GET /api/v1/sse (modern SSE, ≥3s connection)
- GET /events (legacy SSE, ≥3s connection)
- Server shutdown (clean SIGINT)

**Text Path (adc-3rt):** Evidence in `docs/notes/core-verification-evidence.md` (lines 3222-3305). Key findings:
- ZAI proxy reachable (200 OK, 1767ms latency)
- Initial startup failure: coroutine 'get_store' never awaited (session store initialization bug)
- Database migration issue: missing `session_id` column
- E2E harness passed: `result_created` received in 9.00s
- Strict assertions failed: missing SSE `data`, `intents.status=pending`
- Hot-reload verification passed (14 tests, live routing confirmed)

**Fan-out (adc-1ua):** Evidence in `docs/notes/core-verification-evidence.md` (lines 3306-3351). Key findings:
- Multi-intent utterance → 2 concurrent agent cards (3.4ms apart)
- Parallel execution confirmed (both syntheses started before completion)
- Router segmentation accurate (2 intents, correct project slugs)
- Same ID/status defects as text path

**Voice (adc-4iq):** Closed with status "UNTESTABLE - No OPENAI_API_KEY available". Graceful degradation verified (factory returns None, no exceptions). No actual voice turn executed.

**Memory (adc-zec):** Evidence in `docs/notes/core-verification-evidence.md` (lines 2215-3221). Key findings:
- 58 unit tests pass (42 MemoryStore + 16 extraction)
- Wiring verified: handler created → callback assigned → event-driven invocation
- Graceful degradation without API key confirmed
- Integration NOT VERIFIED: requires voice turn with API key
- All memory files in `data/memory/` are from unit tests (`test-session-*` pattern)

---

## Acceptance Criteria Status

**Original Epic adc-1sb Acceptance Criteria:**

1. ✅ Smoke tests pass (adc-dmu) - All 20 runs passed
2. ⚠️ Text path end-to-end works (adc-3rt) - Works but with defects (SSE data missing, status pending)
3. ⚠️ Fan-out produces parallel cards (adc-1ua) - Works but with same defects
4. ❌ Voice path works (adc-4iq) - UNTTESTABLE (no API key)
5. ⚠️ Memory persists across sessions (adc-zec) - Unit verified, integration not verified (no API key)
6. ❌ Human verification (adc-5zs) - NOT VERIFIED (no API key)

**Minimum Bar for GO-WITH-CAVEATS:** Text path + fan-out = **MET**

**Full GO Requirements:** Voice + memory functional = **NOT MET** (blocked by API key)

---

## Recommendations

1. **Immediate:** Set `OPENAI_API_KEY` environment variable to enable voice/memory/human verification. Without it, 3 of 6 paths remain untestable at integration level.

2. **Short-term:** Fix ID/status wiring defect between store and router. This is a correctness issue: results show `resolved` but database shows `pending`, and ID mismatch complicates tracking.

3. **Short-term:** Add `data` field to SSE `result_created` payload. Current implementation sends `rendered_html` but not raw JSON data, breaking client expectations.

4. **Short-term:** Fix database schema drift. Update `SCHEMA_SQL` to handle `dispatch_timings.session_id` migration properly (nullable column before index, or versioned migration).

5. **Operations:** Add systemd user service for ADC before further integration work. Manual process management is not sustainable for development or production.

6. **Deferred:** Whisper STT fallback implementation remains deferred. Not blocking for GO-WITH-CAVEATS but should be tracked for eventual completion.

---

## Sign-off

**Report Prepared By:** adc-5kp (Core verification synthesis bead)  
**Date:** 2026-08-11  
**Epic Status:** adc-1sb is **CLOSED** - All verification beads completed (some with caveats)

**Final Verdict:** **GO-WITH-CAVEATS** for ADC core function. Text and fan-out paths work. Voice/memory require API key for full verification. Asterisk/PBX remains deferred. Proceed with integration work aware of documented defects.
