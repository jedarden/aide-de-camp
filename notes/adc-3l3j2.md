# Workflow Metrics Parser Implementation

## Task Completed: Parse and Extract Deployment Metrics from Workflow Data

## What Was Built

Created `/home/coding/aide-de-camp/scripts/parse_workflow_metrics.py` - a Python script that:

### Core Functionality
- Parses raw kubectl workflow output into structured JSON format
- Extracts key metrics: workflow_id, timestamp, phase, started_at, finished_at, duration_seconds, status_message
- Calculates duration (finishedAt - startedAt) for completed workflows
- Filters workflows to 30-day window (2026-07-07 to 2026-08-06)
- Validates data completeness (flags incomplete entries)

### Input/Output Format
**Input:** Raw kubectl workflow data (JSON or table format)
**Output:** Structured JSON with:
```json
{
  "total_count": int,
  "timeframe": {"start": "ISO-date", "end": "ISO-date", "days": int},
  "workflows": [list of workflow objects],
  "summary": {"succeeded": int, "failed": int, "running": int, "pending": int}
}
```

### Edge Cases Handled
- No workflows found (returns empty list with appropriate messaging)
- Missing timestamps (duration calculation skipped)
- Incomplete records (flagged with `data_complete: false`)
- Multiple kubectl output formats (JSON and table)

## Current Data Status

**pbx-web workflows (Last 30 Days):**
- Total workflows found: **0**
- The pbx-web-build WorkflowTemplate exists but has no executions in the timeframe
- Timeframe: 2026-07-07 to 2026-08-06

This confirms the analysis in `logs/whisper-stt-30day.json` showing pbx-web has no deployment data.

## Usage

```bash
# Parse workflow metrics
.venv/bin/python scripts/parse_workflow_metrics.py /tmp/pbx-web-workflows-raw.txt

# Output written to: /tmp/pbx-web-workflows-parsed.json
```

## Acceptance Criteria Met

✓ Parse raw workflow data into structured format
✓ Extract fields: metadata.name, status.phase, status.startedAt, status.finishedAt, status.message
✓ Calculate duration for completed workflows
✓ Filter to 30-day window
✓ Validate data completeness
