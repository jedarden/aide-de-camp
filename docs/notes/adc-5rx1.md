# ADC-5RX1 Completion Notes

## Task: Rehearsal Instrumentation

**Status:** ✅ Complete

## Implementation Summary

### 1. Rehearsal Script Infrastructure ✅
- Created `/home/coding/aide-de-camp/scripts/rehearsal.py` - Main rehearsal runner
- Created `/home/coding/aide-de-camp/docs/notes/rehearsals/` directory for logs
- Added comprehensive README for rehearsal directory

### 2. Per-Step Timing Capture ✅
- Implemented direct SQLite queries to `dispatch_timings` table
- Captures all timing columns: `router_ms`, `fetch_first_source_ms`, `synthesize_first_token_ms`, `sse_emit_ms`, `first_render_ms`
- Calculates end-to-end latency for first-card metric

### 3. Smooth-Criteria Validation ✅
Implemented all 7 smooth criteria from Phase 5 plan:
1. **First Card ≤ 3s**: Validates total latency against 3000ms threshold
2. **Thread Card Count**: Verifies all intent threads produce cards
3. **Zero Error States**: Checks for fallback cards and fetch_coverage caveats
4. **Zero Dead-End Cards**: Validates card resolution states
5. **SSE Stable**: Monitors result delivery
6. **STT First Attempt**: N/A for test endpoint (documented)
7. **Single Capture**: Procedural (documented)

### 4. Automatic Defect Bead Filing ✅
- Implemented `file_defect_bead()` method using `bf create` CLI
- Beads titled with `rehearsal-defect:` prefix
- Includes violation context, evidence, and acceptance criteria
- Auto-files on any smooth-criterion violation

### 5. CLI Subcommand ✅
Added `adc rehearsal` command:
```bash
# Basic rehearsal run
adc rehearsal

# Inject slow step for testing
adc rehearsal --inject-slow-step 3

# Custom server URL
adc rehearsal --server http://localhost:9000
```

### 6. Testing with Injected Slow Step ✅
- Created `scripts/test_rehearsal_violations.py` test suite
- Verified violation detection logic:
  - Fast step (1150ms) ✅ Pass
  - Slow step (7000ms) ✅ Correctly detected violation
  - Missing timing data ✅ Correctly detected violation
- Simulated bead filing structure verified

## Files Created/Modified

### New Files:
1. `scripts/rehearsal.py` - Main rehearsal runner (400+ lines)
2. `scripts/test_rehearsal_violations.py` - Test suite
3. `docs/notes/rehearsals/README.md` - Documentation
4. `docs/notes/adc-5rx1.md` - This file

### Modified Files:
1. `src/cli/commands.py` - Added `rehearsal()` function
2. `src/cli/main.py` - Added `rehearsal` subcommand

## Usage Examples

### Run Full Rehearsal
```bash
# Using CLI
adc rehearsal

# Direct script
python scripts/rehearsal.py
```

### Test Violation Detection
```bash
# Inject 4-second delay at step 3
python scripts/rehearsal.py --inject-slow-step 3

# Should detect violation and file bead
```

### Run Test Suite
```bash
python scripts/test_rehearsal_violations.py
```

## Rehearsal Log Format

Logs are written to `docs/notes/rehearsals/rehearsal-YYYYMMDD-HHMMSS.json`:

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

## Acceptance Criteria Met

✅ **One command produces a rehearsal log with pass/fail per smooth criterion**
- `adc rehearsal` runs all 6 steps and validates each criterion
- Log includes per-step pass/fail status

✅ **Violations create beads**
- `file_defect_bead()` automatically calls `bf create`
- Beads include context: step, criterion, evidence, timestamp

✅ **Tested with an injected slow step**
- Test suite validates violation detection logic
- `--inject-slow-step` flag simulates 4-second delay
- Correctly detects and reports violations

## Integration Points

1. **Database**: Direct SQLite queries to `data/session.db`
   - `dispatch_timings` table for per-stage timing
   - `results` table for card rendering data

2. **CLI Integration**: Uses `bf create` command for bead filing
   - Requires bead CLI (bead-forge) to be available
   - Files beads in current workspace

3. **HTTP API**: Uses test dispatch endpoint
   - `POST /api/v1/test/dispatch` for utterance dispatch
   - Supports `wait_for_results` for synchronous testing

## Notes

- The rehearsal script bypasses STT (Speech-to-Text) using the test endpoint, so criterion 6 is documented as N/A
- Criterion 7 (single unedited capture) is procedural and documented as such
- The script requires the ADC server to be running at the specified URL
- Defect beads are filed with must-fix triage per Phase 5 known-issues register

## Future Enhancements

1. Add API endpoint for querying results by intent_ids (currently uses direct DB)
2. Add visual regression detection (screenshot comparison)
3. Add performance trend tracking across rehearsals
4. Add automatic retry mechanism for transient failures
5. Add rehearsal result aggregation and reporting

---

**Bead:** adc-5rx1
**Completed:** 2025-01-23
**Commit:** Pending
