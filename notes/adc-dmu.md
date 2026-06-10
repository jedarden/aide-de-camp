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

### Background Analysis Loop Error
**Location:** src/feedback/background_analysis.py:124
**Error:** KeyError: 'id' when accessing signal_ids

The background analysis processor crashes during startup with:
```
Error in background analysis loop: 'id'
KeyError: 'id' at line 124: signal_ids = [s["id"] for s in signals]
```

This is a non-blocking error - the server continues running. The code assumes all signal dictionaries have an 'id' key, but some signals are missing this field.

**Recommendation:** Add defensive check or investigate source of malformed signals.

## Summary

All 6 core HTTP/SSE assertions passed. One non-blocking startup anomaly identified in background analysis loop. Full evidence documented in docs/notes/core-verification-evidence.md.
