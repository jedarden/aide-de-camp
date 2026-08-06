# Task adc-15oi2: Extract and Parse pbx-web Workflow Metadata

## Summary
Successfully created a workflow metadata parser and analyzed pbx-web-build workflow data from the iad-ci cluster.

## What Was Done

### 1. Created Workflow Metadata Parser (`parse_workflow_metadata.py`)
- **Purpose**: Parse kubectl output for Argo Workflows and extract relevant metadata
- **Supported Formats**:
  - Full kubectl JSON format with nested metadata/status/spec structure
  - Simplified format with just name/created/phase fields
  - Array format or `{"items": [...]}` format
- **Extracted Fields**:
  - `metadata.name` (workflow ID)
  - `status.phase` (success/failure/running)
  - `status.startedAt`
  - `status.finishedAt`
  - `status.message` (error messages if any)
  - Additional metadata: namespace, creationTimestamp, labels, annotations, resourcesDuration

### 2. Analyzed Available Data
- Ran parser on available workflow data files:
  - `/home/coding/aide-de-camp/data/pbx-web-workflows-last-30d.txt` - Raw kubectl output
  - `/home/coding/scratch/pbx-web-workflows-approach-b.json` - Query results with 30-day filter
- **Key Finding**: **Zero pbx-web-build workflow runs found** in the available retention window

### 3. Discovery: Cluster Retention Policy
The analysis revealed important context:
- **Cluster**: iad-ci (Rackspace Spot, us-east-iad-1)
- **Retention Policy**: Workflows are deleted after ~7-10 days
- **Oldest Workflow**: 2026-07-27 (10 days ago from query date 2026-08-06)
- **Total Workflows in Cluster**: 34
- **Workflow Template**: `pbx-web-build` exists (created 2026-05-27) but has no recent runs

### 4. Saved Intermediate Output
- **File**: `/home/coding/aide-de-camp/research/pbx-web-workflows-raw.json`
- **Contents**: Structured JSON with parsed workflow metadata plus context about retention policy
- **Purpose**: Ready for formatting step in the workflow analysis pipeline

## Acceptance Criteria Met ✅

- ✅ Raw kubectl output parsed successfully
- ✅ Extracted fields include all required metadata (name, phase, dates, messages)
- ✅ Data structured into a list of workflow records
- ✅ Output saved as intermediate JSON for formatting step

## Key Insights

1. **Data Availability Issue**: The requested 30-day analysis window exceeds the cluster's 7-10 day retention policy
2. **No Recent Activity**: No pbx-web-build workflow runs found in the available data window
3. **Template Status**: The pbx-web-build workflow template exists but appears unused in recent days
4. **Cluster Health**: Other workflows are actively running (spaxel-build, armor-build, needle-ci-verify)

## Recommendations for Next Steps

1. **Alternative Data Sources**: Check if pbx-web-build logs are persisted elsewhere (Loki, Elasticsearch)
2. **Retention Adjustment**: Consider longer TTL for pbx-web-build if historical analysis is needed
3. **Deployment Logs**: Analyze pbx-web deployment logs instead of workflow runs for 30-day window
4. **Manual Trigger Investigation**: Determine why pbx-web-build hasn't run recently (on-demand vs scheduled)

## Files Created/Modified

- `parse_workflow_metadata.py` - Workflow metadata parser script
- `research/pbx-web-workflows-raw.json` - Intermediate parsed output with context
- `notes/adc-15oi2.md` - This summary document

## Next Steps

The intermediate JSON is ready for the formatting step to create the final workflow analysis report.
