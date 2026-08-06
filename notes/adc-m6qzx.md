# adc-m6qzx: Save structured pbx-web deployment data to JSON

## Task Completed
Successfully created structured JSON file with pbx-web deployment metrics for the last 30 days.

## Deliverable Location
`~/scratch/pbx-web-deployments-30d.json`

## File Details
- **Total Records:** 10 deployment entries
- **Date Range:** 2026-07-07 to 2026-07-16
- **Status Distribution:**
  - 6 Succeeded deployments
  - 3 Failed deployments
  - 1 Error deployment

## Schema
```json
{
  "workflow_name": "string",
  "started_at": "ISO 8601 timestamp",
  "finished_at": "ISO 8601 timestamp",
  "status": "Succeeded|Failed|Error",
  "duration_seconds": number,
  "error_message": "string (only for Failed/Error status)"
}
```

## Validation Results
- ✅ Valid JSON structure
- ✅ All required fields present
- ✅ Proper ISO 8601 timestamp formatting
- ✅ Error messages only present for Failed/Error deployments
- ✅ Duration calculations correct
- ✅ Readable by both jq and Python json.load()

## Transformation Notes
- Transformed data from `~/scratch/pbx-web-parsed-deployments.json` (prerequisite: adc-11773)
- Removed extraneous fields (success, failure, workflow_template)
- Mapped message → error_message only for non-Succeeded deployments
- Maintained exact record count from source data

## Related Beads
- Depends on: adc-11773 (deployment metrics extracted and parsed)
- Prerequisite chain: adc-2v31y → adc-11773 → adc-m6qzx
