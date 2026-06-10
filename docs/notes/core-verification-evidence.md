# Core Verification Evidence

This file records evidence from smoke tests and verification activities for the aide-de-camp (adc-voice) server.

## Smoke

**Date:** 2026-06-10  
**Bead:** adc-dmu  
**Purpose:** Verify basic server startup and endpoint functionality

### Test Environment
- Python: 3.13
- Server: uvicorn src.main:app --host 127.0.0.1 --port 8000
- Platform: Linux 6.12.63+deb13-amd64

### Results

#### ✅ 1. Server Startup
**Status:** PASS  
**Command:** `python3 -m uvicorn src.main:app --host 127.0.0.1 --port 8000`

Server started successfully. Expected harmless warning encountered:
```
Error processing line 4 of /home/coding/.local/lib/python3.13/site-packages/_cuda_bindings_redirector.pth:
  ModuleNotFoundError: No module named 'cuda'
```

**Anomaly (FIXED):** Background analysis loop error during lifespan startup:
```
Error in background analysis loop: 'id'
Traceback (most recent call last):
  File "/home/coding/aide-de-camp/src/feedback/background_analysis.py", line 410, in run
    proposals = await self.analyze_signals()
  File "/home/coding/aide-de-camp/src/feedback/background_analysis.py", line 124, in analyze_signals
    signal_ids = [s["id"] for s in signals]
KeyError: 'id'
```

**Root Cause:** Column name mismatch. The code at line 124 used `s["id"]` but the database schema uses `signal_id` as the primary key column (src/session/store.py:139).

**Fix Applied:** Changed `s["id"]` to `s["signal_id"]` in src/feedback/background_analysis.py:124. Verified in re-run - no errors, clean startup.

#### ✅ 2. GET /health
**Status:** PASS  
**Expected:** 200 `{"status":"ok","service":"adc-voice"}`  
**Actual:** 200 `{"status":"ok","service":"adc-voice"}`  
**Location:** src/main.py:174

#### ✅ 3. GET / (Canvas)
**Status:** PASS  
**Expected:** 200 with text/html content-type serving src/canvas/index.html  
**Actual:** 
- HTTP/1.1 200 OK
- content-type: text/html; charset=utf-8
- Serves src/canvas/index.html (23,736 bytes)
**Location:** src/main.py FileResponse handler

#### ✅ 4. POST /api/v1/surfaces/register
**Status:** PASS  
**Expected:** 200 with surface_id and session_id  
**Actual:** 200 with valid UUIDs:
```json
{
  "surface_id": "a830d6fc-11e4-4c9b-97a1-62d3e49b03e7",
  "session_id": "b0bbac08-e8e1-4096-9edc-68accd57902a"
}
```
**Location:** src/main.py:758

#### ✅ 5. GET /api/v1/sse
**Status:** PASS  
**Expected:** Stream opens (200, text/event-stream) and stays open >= 3s  
**Actual:**
- HTTP/1.1 200 OK
- content-type: text/event-stream; charset=utf-8
- Connection stayed open for full 3-second test duration
- Received multiple events including:
  - `connected` event with surface/session IDs
  - `workload_summary` event with pending_intents, new_results, unresolved_exceptions
  - `topic_cards` event (empty cards array)
  - Second `connected` event with connection_id

**Location:** src/main.py:806

#### ✅ 6. Legacy GET /events
**Status:** PASS  
**Expected:** Opens event stream  
**Actual:** Opens successfully, sends `connected` event with new surface_id

#### ✅ 7. Server Shutdown
**Status:** PASS  
**Method:** SIGTERM (graceful shutdown)  
**Result:** Server stopped cleanly

### Summary

**Pass:** 6/6 core assertions  
**Bugs Fixed:** 1 (trivial column name mismatch in background_analysis.py)

All critical HTTP and SSE endpoints function correctly. Server startup, health checks, canvas serving, surface registration, and event streaming all work as expected. The background analysis KeyError was a trivial bug - column name mismatch (`id` vs `signal_id`) - fixed and verified.

---

## Smoke Test - 2025-06-10 22:10 UTC (Repeat Verification)

**Purpose:** Re-verify after previous bug fix to confirm stable operation  
**Bead:** adc-dmu (repeat test)  
**Commit:** a1eca1e

### Test Execution
- **Timestamp:** 2025-06-10 22:10 UTC
- **Server Command:** `python3 -m uvicorn src.main:app --host 127.0.0.1 --port 8000`
- **Test Duration:** ~6 minutes

### Results

#### 1. Server Startup ✅
- **Status**: PASS
- **Details**: Server started successfully on process 1445979
- **Startup Log**:
  ```
  INFO:     Started server process [1445979]
  INFO:     Waiting for application startup.
  INFO:     Application startup complete.
  INFO:     Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)
  ```
- **Lifespan Errors**: None detected. All background services initialized cleanly:
  - Session store initialized
  - SSE broadcaster started
  - Topic manager initialized
  - Surface router initialized
  - Component library initialized
  - Hot-reload manager initialized
  - Feedback processor initialized
  - Ambient monitor started
  - Context warmer started
  - Background analysis processor started (NO KeyError - previous fix confirmed)
  - Bead watcher started

#### 2. GET /health ✅
- **Status**: PASS
- **Response**: 200 OK
- **Body**: `{"status":"ok","service":"adc-voice"}`
- **Endpoint**: src/main.py:174

#### 3. GET / (Canvas Serving) ✅
- **Status**: PASS
- **Response**: 200 OK
- **Content-Type**: text/html (via FileResponse)
- **Served**: src/canvas/index.html
- **Endpoint**: src/main.py:180

#### 4. POST /api/v1/surfaces/register ✅
- **Status**: PASS
- **Response**: 200 OK
- **Sample Request**: `{"session_id":"smoke-1781129462","surface_type":"canvas"}`
- **Sample Response**: `{"surface_id":"9b5f9c36-4d2a-4fda-a627-fa8a99485631","session_id":"77b866e1-fe2a-4fd3-9f57-e60c6407508a"}`
- **Endpoint**: src/main.py:758

#### 5. GET /api/v1/sse (SSE Connection) ✅
- **Status**: PASS
- **Response**: 200 OK
- **Content-Type**: text/event-stream
- **Connection Time**: >= 3s (tested with timeout)
- **Endpoint**: src/main.py:806
- **Sample Events Received**:
  ```
  event: connected
  data: {"surface_id": "9ace6c95-9b3a-4157-9cbe-7a4b9e591bab", "session_id": "b79a6203-b991-4231-8783-bfb2f0d8216c"}

  event: workload_summary
  data: {"pending_intents": 0, "new_results": 0, "unresolved_exceptions": 0}

  event: topic_cards
  data: {"cards": []}
  ```

#### 6. GET /events (Legacy SSE) ✅
- **Status**: PASS
- **Response**: 200 OK
- **Content-Type**: text/event-stream
- **Endpoint**: src/main.py:587
- **Behavior**: Identical to /api/v1/sse, maintains backward compatibility

#### 7. Server Shutdown ✅
- **Status**: PASS
- **Method**: `pkill -f "uvicorn src.main:app"`
- **Shutdown Log**:
  ```
  INFO:     Shutting down
  INFO:     Waiting for application shutdown.
  INFO:     Application shutdown complete.
  INFO:     Finished server process [1445979]
  ```

### Summary
**All 7 smoke test assertions PASSED.** Previous bug fix (background_analysis KeyError) confirmed stable. Core server surface verified:
- HTTP endpoints respond correctly
- Canvas HTML served successfully
- SSE streaming functional on both modern and legacy endpoints
- Background services initialize without error (previous fix confirmed working)
- Clean shutdown confirmed

**No new code modifications required.** All tested functionality works as specified.
