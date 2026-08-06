# Voice Path Verification (Bead adc-4iq)

**Bead ID:** adc-4iq
**Task:** Voice path scripted: /voice WS turn -> STT -> response + narration (fixture audio)
**Date:** 2026-08-05
**Status:** ⚠️ UNTESTABLE — API key missing

## Task Summary

Verify the voice WebSocket path through to STT transcription and response narration with fixture audio.

## Findings

### API Key Availability
- **Status:** NOT AVAILABLE
- **Checked locations:**
  - Environment variables: No `OPENAI_API_KEY` found
  - `.env` file: Not found
  - `~/.config/adc/`: Directory does not exist

### Graceful Error Path
**Status:** ✅ VERIFIED

Tested WebSocket connection to `/voice` without API key:
- Connection accepted by server
- Error JSON received: `{"type": "error", "error": "OpenAI API key not configured"}`
- WebSocket closed with code 1011 and reason "API key missing"

This matches the expected behavior in `src/main.py:318-325`.

### Test Execution
```bash
$ .venv/bin/python test_voice_error_path.py
✓ WebSocket connection accepted
✓ Received message: {"type": "error", "error": "OpenAI API key not configured"}
✓ Error message format is correct
✓ WebSocket closed as expected
  Close code: 1011
  Close reason: API key missing
✓ Close code is correct (1011)
✓ Close reason mentions API key
✓ All checks passed - graceful error handling verified
```

### STT Backend Fact
The voice path uses OpenAI Realtime API's built-in input transcription model "whisper-1":
- Location: `src/realtime/session.py:122` (session creation against api.openai.com)
- **NOT** using the whisper-stt service on ardenone-cluster
- Cluster whisper-stt service is RUNNING but NOT wired into ADC
- Plan.md lists cluster whisper-stt as an unimplemented fallback

## Full E2E Flow (Not Tested)

The following could not be tested due to missing API key:

1. **WebSocket connection** ✅ (tested - accepts connection)
2. **Realtime session creation** ❌ (requires API key)
3. **Fixture audio transmission** ❌ (requires active session)
4. **STT transcription** ❌ (requires audio and session)
5. **dispatch_intent tool call** ❌ (requires successful transcription)
6. **Result narration** ❌ (requires tool call result)
7. **Audio output deltas** ❌ (requires narration event)

## Evidence Location

Findings documented in `docs/notes/core-verification-evidence.md` under "## Voice path" section.

## Conclusion

Voice path verification **INCOMPLETE** due to missing OPENAI_API_KEY. The graceful error path works as designed, but the full E2E flow (WebSocket → STT → dispatch → result → narration) cannot be tested without an API key.

**To complete verification:** Configure OPENAI_API_KEY and re-run with fixture audio.
