# Latency Baseline Data Parsing (adc-3da8y)

## Task Summary
Parse raw timing data files from adc-21k11 latency baseline tests into structured JSON format.

## Source Files
All timing data files located in `/home/coding/aide-de-camp/data/`:

1. **latency-baseline-shape1-20260723_170941.json**
   - Shape: `step1_multi_status`
   - Description: Multi-intent status query (pbx-web + whisper-stt)
   - Utterance: "Has the pbx web caught up, and what's the state of whisper stt?"
   - Records: 106 timing records

2. **latency-baseline-shape2-20260723_171458.json**
   - Shape: `step2_lookup_logs`
   - Description: Lookup logs (whisper-stt)
   - Utterance: "Pull up the recent logs for whisper stt."
   - Records: 64 timing records

3. **latency-baseline-shape3-20260723_172011.json**
   - Shape: `step3_brainstorm`
   - Description: Brainstorm (pbx-web)
   - Utterance: "Should pbx web keep using the static site generator, or is it time to move to a dynamic frontend? Give me the trade-offs."
   - Records: 35 timing records

## Data Structure
Each raw timing record contains:
- `intent_id`: Unique intent identifier
- `router_ms`: Intent classification/routing time
- `fetch_first_source_ms`: Time to first fetch result
- `fetch_total_ms`: Total fetch orchestration time
- `synthesize_first_token_ms`: Time to first synthesis token (all null in baseline)
- `synthesize_total_ms`: Total synthesis time
- `escalate_ms`: Escalation time (present in shape1 only)
- `sse_emit_ms`: SSE emit time (all null)
- `stt_ms`: Speech-to-text time (all null)
- `first_render_ms`: First render time (all null)
- `created_at`: Unix timestamp

## Stages Identified
All timing stages present across the baseline data:
1. **router** - Intent routing and classification
2. **fetch_first_source** - First fetch source completion
3. **fetch_total** - Complete fetch orchestration
4. **synthesize_total** - Complete synthesis (LLM generation)
5. **escalate** - Escalation handling (shape1 only)

## Consolidated Output
**Location**: `/home/coding/aide-de-camp/data/parsed/latency_baseline_consolidated.json`

### Summary Statistics
- **Total shapes processed**: 3
- **Total timing records**: 205
  - Shape 1 (multi-status): 106 records
  - Shape 2 (lookup logs): 64 records
  - Shape 3 (brainstorm): 35 records

### Output Structure
```json
{
  "metadata": {
    "parser_version": "1.0.0",
    "parsed_at": "2026-07-23T17:59:03.998716",
    "source_bead": "adc-21k11",
    "total_shapes": 3,
    "shapes": {...}
  },
  "shapes": {
    "shape1": {
      "metadata": {...},
      "analysis": {...},
      "dispatches": [
        {
          "iteration": 1,
          "intent_id": "...",
          "created_at": 1784840748,
          "stages": {
            "router": 1611,
            "fetch_first_source": 8,
            "fetch_total": 31,
            "synthesize_total": 2857
          }
        },
        ...
      ]
    },
    "shape2": {...},
    "shape3": {...}
  },
  "all_stages": ["escalate", "fetch_first_source", "fetch_total", "router", "synthesize_total"],
  "summary": {
    "total_records": 205,
    "records_by_shape": {
      "shape1": 106,
      "shape2": 64,
      "shape3": 35
    }
  }
}
```

## Parser Script
**Location**: `/home/coding/aide-de-camp/scripts/parse_latency_baseline.py`

Features:
- Loads all three shape JSON files
- Extracts non-null timing stages from each record
- Consolidates data by shape and dispatch iteration
- Outputs structured JSON with metadata, analysis, and raw dispatch data
- Identifies all unique timing stages across the dataset

## Usage
```bash
# Re-run the parser (if needed)
python3 scripts/parse_latency_baseline.py

# Output location
data/parsed/latency_baseline_consolidated.json
```

## Key Findings
1. **Shape variance**: Different shapes produce different timing record counts due to multi-intent splitting
   - Shape 1 produces 3x records (35 dispatches → 106 records) due to multi-intent handling
   - Shapes 2 and 3 produce 1:1 or 2:1 record ratios

2. **Stage coverage**: Not all stages are present in all records
   - `escalate_ms` only appears in shape1 (15/106 records)
   - `fetch_total_ms` and `fetch_first_source_ms` are null for escalate-only intents
   - `synthesize_total_ms` is null for escalate-only intents

3. **Missing stages**: The following stages had no data in baseline:
   - `synthesize_first_token_ms` (streaming not in baseline)
   - `sse_emit_ms` (SSE broadcast timing not captured)
   - `stt_ms` (voice input not in baseline)
   - `first_render_ms` (client-side rendering not captured)

## Next Steps
This parsed data can now be used for:
- Statistical analysis and visualization
- Performance regression detection
- Stage-by-stage latency breakdown
- Shape comparison and optimization opportunities
