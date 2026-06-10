# Core Verification Evidence

This document contains smoke test evidence for ADC (aide-de-camp) core surface verification.

## Smoke Test - 2026-06-10

### Test Environment
- Host: 127.0.0.1:8000
- Python: 3.13 (system python)
- Test session: smoke-1781133031
- Actual session_id: b0db908d-6640-4d50-9781-f5d7e3c22a46
- Actual surface_id: 2078f69f-ec2b-49a2-b8c0-8560058422ad

### Results

#### 1. Server Startup
**Status:** ✅ PASS
- Command: `python3 -m uvicorn src.main:app --host 127.0.0.1 --port 8000`
- Startup logs show no lifespan errors
- All watcher/monitoring daemons started successfully
- Only harmless warning: `_cuda_bindings_redirector.pth` (expected, no CUDA on this system)

#### 2. GET /health
**Status:** ✅ PASS
- HTTP Status: 200
- Response: `{"status":"ok","service":"adc-voice"}`
- Location: src/main.py:174

#### 3. GET / (Canvas)
**Status:** ✅ PASS
- HTTP Status: 200
- Content-Type: text/html; charset=utf-8
- Serves: src/canvas/index.html
- Location: src/main.py:180

#### 4. POST /api/v1/surfaces/register
**Status:** ✅ PASS
- HTTP Status: 200
- Response contains surface_id and session_id
- Sample response:
  ```json
  {
    "surface_id": "2078f69f-ec2b-49a2-b8c0-8560058422ad",
    "session_id": "b0db908d-6640-4d50-9781-f5d7e3c22a46"
  }
  ```
- Location: src/main.py:758

#### 5. GET /api/v1/sse (SSE v1)
**Status:** ✅ PASS
- HTTP Status: 200
- Content-Type: text/event-stream (inferred from SSE format)
- Connection duration: 3s (tested with --max-time 3)
- Events received:
  - `connected` with surface_id and session_id
  - `workload_summary` (pending_intents: 0, new_results: 0, unresolved_exceptions: 0)
  - `topic_cards` (empty array)
- Location: src/main.py:806

#### 6. GET /events (Legacy SSE)
**Status:** ✅ PASS
- HTTP Status: 200
- Content-Type: text/event-stream (inferred from SSE format)
- Connection duration: 4s (tested with --max-time 3)
- Events received: Same as v1 SSE
- Location: src/main.py:587

#### 7. Server Shutdown
**Status:** ✅ PASS
- Clean shutdown with SIGINT (kill -INT)
- All services terminated without errors

### Summary

**All tests passed.** The ADC server starts correctly, serves the canvas, responds to health checks, registers surfaces, and maintains SSE connections for both v1 and legacy endpoints.

**No bugs or fixes required.**
