# Smoke Test Summary - Bead adc-dmu

**Date:** 2026-06-10
**Task:** Smoke test ADC server startup and core endpoints
**Bead:** adc-dmu (core-verification epic adc-1sb)

## Tests Performed

### 1. Server Startup
✅ PASS - Server started successfully on port 8000
```bash
python3 -m uvicorn src.main:app --host 127.0.0.1 --port 8000
```

### 2. GET /health
✅ PASS - Returns 200 with `{"status":"ok","service":"adc-voice"}`

### 3. GET / (Canvas)
✅ PASS - Serves src/canvas/index.html with text/html content-type

### 4. POST /api/v1/surfaces/register
✅ PASS - Returns surface_id and session_id with 200 status

### 5. GET /api/v1/sse (Server-Sent Events)
✅ PASS - Opens event stream, stays open for 3+ seconds, sends events properly

### 6. GET /events (Legacy SSE)
✅ PASS - Opens event stream successfully

### 7. Server Shutdown
✅ PASS - Clean shutdown via SIGTERM

## Anomalies Found

### Background Analysis Loop Error (FIXED)
**Location:** src/feedback/background_analysis.py:124
**Error:** KeyError: 'id' when accessing signal_ids
**Status:** ✅ FIXED in commit be62853

The background analysis processor previously crashed during startup with:
```
Error in background analysis loop: 'id'
KeyError: 'id' at line 124: signal_ids = [s["id"] for s in signals]
```

**Root Cause:** Column name mismatch - code used `s["id"]` but database schema uses `signal_id`
**Fix:** Changed `s["id"]` to `s["signal_id"]` in src/feedback/background_analysis.py:124
**Verification:** Re-smoke test confirmed fix - no errors, clean startup with all services initialized

## Summary

✅ All 7 core HTTP/SSE assertions passed.
✅ Previous startup anomaly (background_analysis KeyError) confirmed fixed.
✅ Server starts, serves endpoints, handles SSE connections, and shuts down cleanly.

Full evidence documented in docs/notes/core-verification-evidence.md.
