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

**Anomaly:** Background analysis loop error during lifespan startup:
```
Error in background analysis loop: 'id'
Traceback (most recent call last):
  File "/home/coding/aide-de-camp/src/feedback/background_analysis.py", line 410, in run
    proposals = await self.analyze_signals()
  File "/home/coding/aide-de-camp/src/feedback/background_analysis.py", line 124, in analyze_signals
    signal_ids = [s["id"] for s in signals]
KeyError: 'id'
```

This error occurs in `src/feedback/background_analysis.py:124` where the code assumes all signal dictionaries have an 'id' key. The server continues running despite this error.

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
**Anomalies:** 1 (background analysis KeyError)

The background analysis error in `src/feedback/background_analysis.py:124` is a non-blocking issue but should be investigated. The code assumes all signals have an 'id' field, but some signal objects in the signals list are missing this field. A defensive check like `signal_ids = [s.get("id") for s in signals if "id" in s]` or investigating the source of malformed signals would resolve this.

All critical HTTP and SSE endpoints function correctly. Server startup, health checks, canvas serving, surface registration, and event streaming all work as expected.
