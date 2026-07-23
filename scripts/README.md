# Latency Test Infrastructure

This directory contains scripts for latency testing and demo rehearsal for Phase 5 Demo Readiness.

## Scripts

### verify_infrastructure.py
Verifies that all components needed for latency testing are in place.

**Usage:**
```bash
python scripts/verify_infrastructure.py
```

**Checks:**
- Server health and watcher status
- ZAI proxy connectivity
- Database accessibility and dispatch_timings table
- Test endpoints availability
- Timing capture verification

Run this before starting latency measurements to ensure everything is ready.

---

### measure_latency.py
Runs the Phase 5 demo script utterances repeatedly (30+ runs each) to collect timing data and establish p50/p95 latency baselines.

**Usage:**
```bash
python scripts/measure_latency.py
```

**What it does:**
1. Checks ZAI proxy reachability
2. Verifies server health
3. Clears old timing data
4. Runs each demo utterance 30 times
5. Collects timing data from dispatch_timings table
6. Calculates p50/p95 percentiles for each stage
7. Saves results to `docs/notes/latency-baseline-{timestamp}.json`
8. Checks results against the 3s budget

**Demo utterances (pbx-web and whisper-stt projects):**
1. Multi-intent status query
2. Lookup logs
3. Brainstorm
4. Lookup config
5. Task-profile escalation
6. Status with diff

**Output:**
- Latency analysis results (p50/p95 per stage)
- Budget compliance check
- JSON file with raw timing data

---

### rehearsal.py
Runs the golden path demo script, validates smooth criteria, and automatically files defect beads on violations.

**Usage:**
```bash
python scripts/rehearsal.py
python scripts/rehearsal.py --server http://localhost:8000
python scripts/rehearsal.py --inject-slow-step 3  # For testing violation detection
```

**What it does:**
1. Runs all 6 demo steps sequentially
2. Validates smooth criteria for each step:
   - First card ≤ 3s
   - Every thread renders as its own card
   - Zero visible error states
   - Zero dead-end cards
   - SSE connection stable
3. Records per-step timing data
4. Writes rehearsal log to `docs/notes/rehearsals/`
5. Automatically files defect beads for violations

**Output:**
- Rehearsal log JSON with timing data and violations
- Defect beads (if violations detected)

---

### run_demo_step.py
Run individual demo steps from the Phase 5 golden path script. Useful for testing specific shapes or manual rehearsal.

**Usage:**
```bash
python scripts/run_demo_step.py 1          # Run step 1
python scripts/run_demo_step.py 1-3       # Run steps 1-3
python scripts/run_demo_step.py all       # Run all steps
```

**What it does:**
- Executes the specified demo step(s)
- Reports success/failure and timing
- Uses a single session for multi-step runs

---

## Demo Script (Phase 5 Golden Path)

The demo uses pbx-web and whisper-stt projects (both on ardenone-cluster):

| Step | Utterance | Intent Type(s) | Description |
|------|-----------|----------------|-------------|
| 1 | "Has the pbx web caught up, and what's the state of whisper stt?" | status ×2 | Multi-intent status query |
| 2 | "Pull up the recent logs for whisper stt." | lookup/logs | Log lookup |
| 3 | "Should pbx web keep using the static site generator, or is it time to move to a dynamic frontend? Give me the trade-offs." | brainstorm | Brainstorm with trade-offs |
| 4 | "Find whisper stt's deployment config — which cluster and namespace is it on?" | lookup/config | Config lookup |
| 5 | "Queue up a research task: compare the last month of pbx web deployment patterns against whisper stt's and write up common failure patterns — no rush." | task-profile | Task-profile escalation |
| 6 | "Anything new on pbx web since we started?" | status | Status with in-place diff |

## Latency Budget

Per-stage targets (from plan.md Phase 5):

| Stage | Target |
|-------|--------|
| Intent Router | ~500ms |
| Fetch Window Close | ~1s |
| Synthesize First Token | ~1s |
| SSE Emit | ~100ms |
| **End-to-End (server)** | **< 3s** |

## Database Schema

The `dispatch_timings` table captures per-stage timings:

```sql
CREATE TABLE dispatch_timings (
    intent_id                 TEXT PRIMARY KEY,
    router_ms                 INTEGER,
    fetch_first_source_ms     INTEGER,
    fetch_total_ms            INTEGER,
    synthesize_first_token_ms INTEGER,
    synthesize_total_ms       INTEGER,
    escalate_ms               INTEGER,
    sse_emit_ms               INTEGER,
    stt_ms                    INTEGER,  -- client-reported
    first_render_ms           INTEGER,  -- client-reported
    created_at                INTEGER
);
```

## ZAI Proxy

All LLM calls go through the ZAI proxy:

```
https://zai-proxy-mcp-apexalgo-iad-ts.ardenone.com:8444/v1/messages
```

Configurable via `ZAI_PROXY_URL` environment variable.

## Typical Workflow

1. **Verify infrastructure:**
   ```bash
   python scripts/verify_infrastructure.py
   ```

2. **Run baseline measurement:**
   ```bash
   python scripts/measure_latency.py
   ```

3. **Review results:**
   - Check `docs/notes/latency-baseline-{timestamp}.json`
   - Verify budget compliance

4. **Run rehearsal:**
   ```bash
   python scripts/rehearsal.py
   ```

5. **Review rehearsal log:**
   - Check `docs/notes/rehearsals/rehearsal-{timestamp}.json`
   - File defects if violations detected

## Troubleshooting

**Server not healthy:**
- Start the server: `uvicorn src.main:app --host 0.0.0.0 --port 8000`
- Check logs: `tail -f /tmp/adc.log`

**ZAI proxy unreachable:**
- Check network connectivity
- Verify proxy URL in code matches environment

**No timing data collected:**
- Check server logs for errors
- Verify dispatch_timings table exists
- Run `verify_infrastructure.py` to check instrumentation

**Test dispatch fails:**
- Verify registry.yaml has pbx-web and whisper-stt configured
- Check kubectl proxies are running
- Verify ArgoCD applications exist on ardenone-manager
