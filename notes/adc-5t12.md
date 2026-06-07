# adc-5t12: Confirm src/intent/router.py exists

## Task
Locate and confirm `src/intent/router.py` exists and is accessible.

## Result
**Confirmed.** File exists at `/home/coding/aide-de-camp/src/intent/router.py`.

## File Details
- **Path:** `src/intent/router.py`
- **Size:** 16,155 bytes
- **Lines:** 460
- **Status:** Readable, non-empty Python module

## Module Purpose
Intent Router - classifies utterances and routes to appropriate strands.
Uses LLM to classify intents by type and project, then routes:
- task-profile intents → escalate strand (bead creation)
- other intents → fetch + synthesize strands
