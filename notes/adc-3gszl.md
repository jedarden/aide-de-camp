# P50/P95 Latency Calculation per Stage

**Task**: adc-3gszl
**Completed**: 2026-07-23

## Objective

Calculate p50 (median) and p95 statistics for each pipeline stage across all dispatches from the consolidated latency baseline data.

## Data Source

- Input: `/home/coding/aide-de-camp/data/parsed/latency_baseline_consolidated.json`
- Source bead: adc-21k11 (parsed latency baseline timing data)

## Processing Summary

**Total dispatches processed: 205**
- Shape 1: 106 dispatches
- Shape 2: 64 dispatches
- Shape 3: 35 dispatches

Verification: ✓ All 205 dispatches successfully processed

## Results

### Shape 1 - Multi-intent status query (pbx-web + whisper-stt)

| Stage | Count | p50 (ms) | p95 (ms) |
|-------|-------|----------|----------|
| intent_router | 106 | 2074.0 | 4187.5 |
| fetch_strands | 91 | 37.0 | 178.5 |
| synthesize | 91 | 3108.0 | 4592.5 |
| escalate | 15 | 3992.0 | 5402.3 |
| e2e | 106 | 5553.5 | 8031.5 |

### Shape 2 - Lookup logs (whisper-stt)

| Stage | Count | p50 (ms) | p95 (ms) |
|-------|-------|----------|----------|
| intent_router | 64 | 1640.0 | 3297.4 |
| fetch_strands | 64 | 45.0 | 190.7 |
| synthesize | 64 | 3787.5 | 5320.8 |
| escalate | 0 | N/A | N/A |
| e2e | 64 | 5640.5 | 8427.35 |

### Shape 3 - Brainstorm (pbx-web)

| Stage | Count | p50 (ms) | p95 (ms) |
|-------|-------|----------|----------|
| intent_router | 35 | 1587.0 | 2487.1 |
| fetch_strands | 35 | 0.0 | 0.0 |
| synthesize | 35 | 3984.0 | 6666.7 |
| escalate | 0 | N/A | N/A |
| e2e | 35 | 5937.0 | 8784.2 |

## Stages Analyzed

✓ **intent_router** - Intent classification latency
✓ **fetch_strands** - Fetch orchestration total time
✓ **synthesize** - LLM synthesis time
✓ **escalate** - Escalation handling time (where applicable)
✓ **e2e** - End-to-end latency (sum of all stages per dispatch)

## Missing Stages

The following stages were not available in the source data:
- **persist** - Not captured in timing records
- **sse_broadcast** - Count is 0 in all shapes

## Output Files

1. **Script**: `/home/coding/aide-de-camp/scripts/calculate_stage_percentiles.py`
2. **Results**: `/home/coding/aide-de-camp/data/parsed/stage_percentiles.json`

## Key Findings

1. **End-to-end latency**: Ranges from ~5.5s median (Shape 1) to ~5.9s median (Shape 3)
2. **Intent router**: Most consistent across shapes, ~1.6-2.1s median
3. **Synthesis**: Dominant latency contributor, ~3.1-4.0s median
4. **Shape 3** has no fetch latency (0ms) as it's a brainstorm task with no external data sources
5. **Shape 1** has escalations (15 occurrences) adding ~4s median

## Acceptance Criteria Met

✓ p50 and p95 values calculated for every stage per shape
✓ Results in structured JSON format ready for aggregation
✓ Verification that all 205 dispatches (106 + 64 + 35) are processed
