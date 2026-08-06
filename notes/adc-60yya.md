# Deployment Data Extraction - Task adc-60yya

## Summary

Created a Python script to parse Argo Workflow data and extract deployment fields, but discovered that no pbx-web-build workflow runs exist in the iad-ci cluster due to retention policy.

## What Was Done

### 1. Created Parser Script
File: `~/scratch/parse_deployments.py`

**Capabilities:**
- Parses Argo Workflow JSON data (raw kubectl output or query results)
- Extracts deployment fields:
  - Workflow name
  - Creation timestamp
  - Started/finished timestamps
  - Phase/status (Succeeded/Failed/Error)
  - Duration (calculated or from field)
  - Message field (error details)
  - Labels and annotations
- Handles missing fields gracefully
- Calculates duration from timestamps if not directly available
- Outputs structured JSON with metadata

### 2. Executed Parser
```bash
cd ~/scratch && python3 parse_deployments.py
```

### 3. Findings

**Result:** No deployment data found for pbx-web-build workflow.

**Root Cause:** iad-ci cluster workflow retention policy:
- Workflows are deleted after approximately 7-10 days
- Oldest workflow in cluster: 2026-07-27 (10 days ago)
- No pbx-web-build runs exist in the available retention window

**Cluster Status (from raw data):**
- Total workflows in cluster: 34
- Workflow template exists: Yes (created 2026-05-27)
- Requested timeframe: 30 days
- Actual lookback available: ~10 days

## Deliverables

1. **Parser Script:** `~/scratch/parse_deployments.py`
   - Reusable for any Argo Workflow data
   - Handles multiple input formats
   - Graceful error handling

2. **Parsed Output:** `~/scratch/pbx-web-deployments-parsed.json`
   - Structured format ready for analysis
   - Empty deployments array (no data available)
   - Includes metadata about parse operation

## Recommendations

For future deployment analysis:

1. **Check retention policy:** Review Argo Workflows retention settings in iad-ci
2. **Extend TTL:** Configure longer retention for pbx-web-build workflows if historical data is needed
3. **External logging:** Use Loki/Elasticsearch for workflow history beyond retention
4. **Alternative sources:** Check if pbx-web-build logs are persisted elsewhere
5. **Proactive collection:** Set up periodic workflow data export before deletion

## Script Usage

```bash
# Parse workflow data
python3 ~/scratch/parse_deployments.py

# Expected input: pbx-web-raw-workflows.json
# Output: pbx-web-deployments-parsed.json
```

The script is ready to process workflow data once it becomes available (future runs or from external sources).
