# Frequency Statistics per Failure Pattern (adc-5kfw5)

## Task Completion Summary

Successfully calculated frequency statistics per failure pattern using the classified deployment failure data.

## What Was Done

1. **Created analysis script**: `docs/research/deployment-data/calculate_frequency_stats.py`
   - Groups failure records by `pattern_type`
   - Calculates total occurrence count per pattern
   - Lists affected services with counts per service
   - Tracks severity distributions per pattern

2. **Generated frequency analysis**: `docs/research/deployment-data/frequency-by-pattern.json`
   - Pattern type: "Other" (1 occurrence)
   - Affected service: pbx-web (1 count)
   - Severity: unknown

3. **Summary statistics**:
   - Total patterns analyzed: 1
   - Total failures: 1
   - Services affected: pbx-web
   - No high/critical severity patterns detected

## Acceptance Criteria Met

✅ Group records by pattern_type
✅ Calculate total occurrence count per pattern
✅ List affected services with counts
✅ Output frequency summary table (console + JSON)
✅ Save result to `docs/research/deployment-data/frequency-by-pattern.json`

## Key Findings

Based on 30-day deployment data analysis:
- Only 1 failure pattern detected: "Other" (deployment rollback on pbx-web)
- The rollback was handled same-day with minimal impact
- Both services (pbx-web and whisper-stt) show excellent operational stability
- No critical or high-severity failure patterns detected in the 30-day period

## Files Created/Modified

- Created: `docs/research/deployment-data/calculate_frequency_stats.py` (analysis script)
- Created: `docs/research/deployment-data/frequency-by-pattern.json` (frequency analysis results)
- Created: `notes/adc-5kfw5.md` (task summary)

## Data Source

Analysis based on: `docs/research/deployment-data/classified-failures.json`
- 1 classified failure from pbx-web deployment (rollback event)
- Classified as "Other" pattern type (deployment rollback not matching standard categories)