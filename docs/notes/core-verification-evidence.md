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

---

## Smoke Test - 2026-06-11

### Test Environment
- Host: 127.0.0.1:8000
- Python: 3.13 (system python)
- Test session: smoke-$(timestamp)
- Actual session_id: b29d2f7d-88ad-44ba-a8dd-69810b057645
- Actual surface_id: 435a9ac9-3498-4379-b655-910afc8ac8a7

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
    "surface_id": "435a9ac9-3498-4379-b655-910afc8ac8a7",
    "session_id": "b29d2f7d-88ad-44ba-a8dd-69810b057645"
  }
  ```
- Location: src/main.py:758

#### 5. GET /api/v1/sse (SSE v1)
**Status:** ✅ PASS
- HTTP Status: 200
- Content-Type: text/event-stream (inferred from SSE format)
- Connection duration: 4s (tested with timeout)
- Events received:
  - `connected` with surface_id and session_id
  - `workload_summary` (pending_intents: 0, new_results: 0, unresolved_exceptions: 0)
  - `topic_cards` (empty array)
- Location: src/main.py:806

#### 6. GET /events (Legacy SSE)
**Status:** ✅ PASS
- HTTP Status: 200
- Content-Type: text/event-stream (inferred from SSE format)
- Connection duration: 4s (tested with timeout)
- Events received: Same as v1 SSE (connected, workload_summary, topic_cards)
- Location: src/main.py:587

#### 7. Server Shutdown
**Status:** ✅ PASS
- Clean shutdown with SIGINT (kill -INT)
- All services terminated without errors

### Summary

**All tests passed.** The ADC server starts correctly, serves the canvas, responds to health checks, registers surfaces, and maintains SSE connections for both v1 and legacy endpoints.

**No bugs or fixes required.**

---

## Smoke Test - 2026-06-11 (Run 2)

**Bead:** adc-dmu
**Tested by:** claude-fable-5

### Test Environment
- Host: 127.0.0.1:8000
- Python: 3.13 (system python)
- Server PID: 2973985

### Results

#### 1. Server Startup
**Status:** ✅ PASS
- Command: `python3 -m uvicorn src.main:app --host 127.0.0.1 --port 8000`
- Startup logs: No errors, clean startup
- Lifespan events: All components initialized (session store, SSE broadcaster, topic manager, surface router, component library, hot-reload manager, feedback processor, ambient monitor, context warmer, background processor, bead watcher)
- Notes: Harmless CUDA warning present in `_cuda_bindings_redirector.pth` but no impact on functionality

#### 2. GET /health
**Status:** ✅ PASS
- HTTP Status: 200
- Response: `{"status":"ok","service":"adc-voice"}`
- Location: src/main.py:174

#### 3. GET / (Canvas)
**Status:** ✅ PASS
- HTTP Status: 200
- Content-Type: text/html; charset=utf-8
- Content-Length: 33001 bytes
- Serves: src/canvas/index.html
- Location: src/main.py:180

#### 4. POST /api/v1/surfaces/register
**Status:** ✅ PASS
- HTTP Status: 200
- Response:
  ```json
  {
    "surface_id": "0f96e83a-3382-4313-a7d4-f1647b8a1a4b",
    "session_id": "8839384f-0bdf-4026-b02a-2e6c4fa3ab67"
  }
  ```
- Location: src/main.py:758

#### 5. GET /api/v1/sse (SSE v1)
**Status:** ✅ PASS
- HTTP Status: 200
- Content-Type: text/event-stream
- Connection duration: 3s (tested)
- Events received:
  - `connected` event with surface_id and session_id
  - `workload_summary` event (pending_intents: 0, new_results: 0, unresolved_exceptions: 0)
- Stream remained open for full test duration
- Location: src/main.py:806

#### 6. GET /events (Legacy SSE)
**Status:** ✅ PASS
- HTTP Status: 200
- Content-Type: text/event-stream
- Connection duration: 3s (tested)
- Events received:
  - `connected` event with surface_id and session_id
  - `workload_summary` event (pending_intents: 0, new_results: 0, unresolved_exceptions: 0)
- Stream remained open for full test duration
- Location: src/main.py:587

#### 7. Server Shutdown
**Status:** ✅ PASS
- Method: SIGTERM (kill)
- Shutdown logs:
  ```
  INFO:     Shutting down
  INFO:     Waiting for application shutdown.
  INFO:     Application shutdown complete.
  INFO:     Finished server process [2973985]
  ```
- Clean shutdown with proper lifespan cleanup

### Summary

| Test | Result |
|------|--------|
| Server startup | ✅ PASS |
| GET /health | ✅ PASS |
| GET / (canvas) | ✅ PASS |
| POST /api/v1/surfaces/register | ✅ PASS |
| GET /api/v1/sse (modern SSE) | ✅ PASS |
| GET /events (legacy SSE) | ✅ PASS |
| Server shutdown | ✅ PASS |

**Overall Status:** ✅ ALL TESTS PASSED

**No source code modifications required. All endpoints responded correctly and SSE connections maintained properly.**
