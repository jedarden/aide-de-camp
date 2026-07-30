# Rehearsal Logs

This directory contains logs from Phase 5 demo rehearsal runs.

## Log Format

Each rehearsal run produces a JSON log file named `rehearsal-YYYYMMDD-HHMMSS.json` with the following structure:

```json
{
  "run_id": "20250123-153045",
  "session_id": "abc123...",
  "start_time": "2025-01-23T15:30:45",
  "end_time": "2025-01-23T15:35:20",
  "duration_seconds": 275,
  "steps": [...],
  "violations": [...],
  "smooth_criteria": {...},
  "total_steps": 6,
  "steps_passed": 5,
  "steps_failed": 1
}
```

## Running Rehearsals

### Via CLI

```bash
# Run rehearsal against default server (http://localhost:8000)
adc rehearsal

# Run against custom server
adc rehearsal --server http://localhost:9000

# Inject slow step for testing violation detection
adc rehearsal --inject-slow-step 3
```

### Direct Script

```bash
# Run rehearsal
python scripts/rehearsal.py

# Inject slow step
python scripts/rehearsal.py --inject-slow-step 3
```

## Acceptance Criteria

Per Phase 5 rehearsal checklist, a demo take requires:

- [ ] 3 consecutive clean end-to-end runs of the golden path
- [ ] Every rehearsal starts from actual starting state (fresh session, seeded registry, warm cache, seeded component library)
- [ ] Every scripted result card is a real component-library card
- [ ] Rehearsals are recorded and reviewed
- [ ] Per-step timing log captured each run; any step > 3s files a defect bead
- [ ] Mid-take failure fallback decided in advance
- [ ] Known-issues register re-reviewed on demo day

## Smooth Criteria

Each step is validated against the following smooth criteria:

1. **First Card ≤ 3s**: First partial card appears within 3 seconds of utterance end
2. **Thread Card Count**: Every thread renders as its own card (zero dropped/merged)
3. **Zero Error States**: No visible error states (raw JSON, stack traces, empty cards, failed-fetch caveats)
4. **Zero Dead-End Cards**: Every card either resolves or shows honest pending state
5. **SSE Stable**: SSE connection never visibly drops
6. **STT First Attempt**: STT accepts each scripted utterance on first attempt (N/A for test endpoint)
7. **Single Capture**: Full take completes in single unedited capture (procedural)

## Defect Beads

Violations automatically file defect beads with the `rehearsal-defect:` prefix. These defects must be resolved before the demo take per the known-issues register.

## Golden Path Script

The demo script consists of 6 steps covering the golden path:

1. Multi-intent status query (options-pipeline + ibkr-mcp)
2. Log lookup (ibkr-mcp)
3. Brainstorm (options-pipeline)
4. Config lookup (ibkr-mcp)
5. Task-profile escalation (options-pipeline)
6. In-place diff status (options-pipeline)

See `/home/coding/aide-de-camp/docs/plan/plan.md` Phase 5 for full details.
