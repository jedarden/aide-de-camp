# Latency Test Infrastructure Setup

**Bead:** adc-3p45e
**Completed:** 2026-07-23

## Summary

Set up complete latency test infrastructure and demo scripts for Phase 5 Demo Readiness.

## What Was Done

### 1. Updated Scripts with Correct Demo Utterances

- **measure_latency.py**: Updated to use pbx-web and whisper-stt projects (both on ardenone-cluster) instead of the old options-pipeline/ibkr-mcp projects
- **rehearsal.py**: Updated with correct demo utterances matching the plan.md Phase 5 golden path

### 2. Created New Scripts

- **verify_infrastructure.py**: Comprehensive health check script that verifies:
  - Server health and watcher status
  - ZAI proxy connectivity
  - Database accessibility and dispatch_timings table
  - Test endpoints availability
  - Timing capture verification

- **run_demo_step.py**: Simple script to run individual demo steps:
  - Run single steps: `python scripts/run_demo_step.py 1`
  - Run ranges: `python scripts/run_demo_step.py 1-3`
  - Run all: `python scripts/run_demo_step.py all`

### 3. Documentation

- **scripts/README.md**: Complete documentation covering:
  - Script usage and examples
  - Demo script utterances
  - Latency budget targets
  - Database schema
  - Typical workflow
  - Troubleshooting guide

## Verification

All infrastructure checks passed:

```
✓ Server Health
✓ ZAI Proxy Reachable
✓ Database Accessible
✓ dispatch_timings Table
✓ Test Endpoint
✓ Timings Endpoint
✓ Timing Capture
```

### Test Results

- Server is running at localhost:8000
- ZAI proxy is reachable (status: 200)
- Database has 401 existing timing records
- Test dispatch successfully captured timings:
  - router_ms: 3809ms
  - fetch_first_source_ms: 8ms
  - fetch_total_ms: 17ms
  - synthesize_total_ms: 3082ms

## Demo Script (Phase 5 Golden Path)

The demo uses pbx-web and whisper-stt projects (both on ardenone-cluster):

1. **Multi-intent status**: "Has the pbx web caught up, and what's the state of whisper stt?"
2. **Lookup logs**: "Pull up the recent logs for whisper stt."
3. **Brainstorm**: "Should pbx web keep using the static site generator, or is it time to move to a dynamic frontend? Give me the trade-offs."
4. **Lookup config**: "Find whisper stt's deployment config — which cluster and namespace is it on?"
5. **Task-profile**: "Queue up a research task: compare the last month of pbx web deployment patterns against whisper stt's and write up common failure patterns — no rush."
6. **Status with diff**: "Anything new on pbx web since we started?"

## How to Use

### Verify Infrastructure
```bash
python scripts/verify_infrastructure.py
```

### Measure Latency (30 runs per utterance)
```bash
python scripts/measure_latency.py
```

### Run Rehearsal
```bash
python scripts/rehearsal.py
```

### Run Individual Steps
```bash
python scripts/run_demo_step.py 1
python scripts/run_demo_step.py all
```

## Acceptance Criteria Status

✅ Server at localhost:8000 logs dispatch_timings for each stage
✅ Demo-step scripts exist for each shape (6 steps from Phase 5)
✅ Test runner script (measure_latency.py) can execute >=30 dispatches per shape
✅ ZAI proxy responds to health checks (reachable, status 200)

## Files Modified/Created

### Modified
- `scripts/measure_latency.py` - Updated with correct demo utterances and ZAI proxy check
- `scripts/rehearsal.py` - Updated with correct demo utterances

### Created
- `scripts/verify_infrastructure.py` - Infrastructure verification script
- `scripts/run_demo_step.py` - Individual demo step runner
- `scripts/README.md` - Complete documentation
- `notes/adc-3p45e.md` - This summary document

## Next Steps

The infrastructure is ready for:
1. Running full latency baseline measurements (30+ runs per shape)
2. Conducting rehearsals with smooth criteria validation
3. Filing defect beads for any violations found
4. Working through the known-issues register in Phase 5
