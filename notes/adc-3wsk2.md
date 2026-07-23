# Latency Test Infrastructure Verification

**Bead:** adc-3wsk2  
**Date:** 2026-07-23  
**Status:** ✓ COMPLETE

## Verification Results

### 1. Test Runner Script ✓
- **Location:** `scripts/measure_latency.py` (executable, rwxr-xr-x)
- **Executable via:** `.venv/bin/python scripts/measure_latency.py`
- **Purpose:** Runs 6 demo utterances 30+ times each to collect latency baselines

### 2. Server Health ✓
- **Health endpoint:** `http://localhost:8000/health`
- **Status:** 200 OK
- **Service:** adc-voice
- **Watcher:** alive (593 ticks, interval 30s)

### 3. Demo-Step Shapes (6 total) ✓

From `DEMO_UTTERANCES` in measure_latency.py:

1. **step1_multi_status** - Multi-intent status query (pbx-web + whisper-stt)
   - "Has the pbx web caught up, and what's the state of whisper stt?"

2. **step2_lookup_logs** - Log lookup (whisper-stt)
   - "Pull up the recent logs for whisper stt."

3. **step3_brainstorm** - Brainstorm with trade-offs (pbx-web)
   - "Should pbx web keep using the static site generator..."

4. **step4_lookup_config** - Config lookup (whisper-stt)
   - "Find whisper stt's deployment config..."

5. **step5_task_profile** - Task-profile escalation
   - "Queue up a research task: compare deployment patterns..."

6. **step6_status_with_diff** - Status with in-place diff (pbx-web)
   - "Anything new on pbx web since we started?"

**Projects:** pbx-web and whisper-stt (both on ardenone-cluster)

### 4. Data Directory ✓
- **Location:** `data/`
- **Writable:** Yes
- **Contents:** session.db, components.db (SQLite databases)

### 5. Output Directory ✓
- **Location:** `docs/notes/`
- **Writable:** Yes
- **Existing files:** Previous latency baselines present (latency-baseline-*.json)

### 6. Python Environment ✓
- **Venv:** `.venv/` exists
- **Dependencies:** httpx, aiosqlite installed and verified
- **Python:** `.venv/bin/python` (required for script execution)

## Next Steps

Infrastructure is ready. Can proceed with:
- Running latency baseline: `.venv/bin/python scripts/measure_latency.py`
- Running rehearsal: `.venv/bin/python scripts/rehearsal.py`

## Latency Budget (from Phase 5 plan.md)

| Stage | Target |
|-------|--------|
| Intent Router | ~500ms |
| Fetch Window Close | ~1s |
| Synthesize First Token | ~1s |
| SSE Emit | ~100ms |
| **End-to-End (server)** | **< 3s** |

All acceptance criteria met. Infrastructure verified and ready for latency testing.
