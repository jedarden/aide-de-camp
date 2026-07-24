# Task adc-3zhbz: whisper-stt 30-Day Deployment Data Collection

## Completed Actions

### 1. Verified pbx-web reference schema
- Confirmed existing data file at `~/scratch/pbx-web-deployments-30d.json`
- Analyzed schema structure for consistency

### 2. Queried whisper-stt-build workflow template
- Verified template exists in `iad-ci` cluster, `argo-workflows` namespace
- Template created: `2026-05-27T02:26:47Z`
- Template age: 58 days (as of 2026-07-24)

### 3. Queried workflow runs (last 30 days)
- Date range: 2026-06-24 to 2026-07-24
- Found **zero** workflow runs for whisper-stt-build
- Verified by multiple query methods:
  - Label selector: `workflows.argoproj.io/workflow-template=whisper-stt-build`
  - Name prefix: `whisper-stt-build-*`
  - General search for "whisper" workflows

### 4. Created structured output
- File: `~/scratch/whisper-stt-deployments-30d.json`
- Schema: Matches pbx-web collection for easy comparison
- Fields captured:
  - `query_metadata`: service, dates, cluster, namespace, template
  - `findings`: deployment counts (all zero)
  - `template_info`: existence, creation date, age
  - `summary`: descriptive finding
  - `comparison_note`: cross-reference with pbx-web

## Key Findings

**No whisper-stt deployments in the last 30 days.**

- Template exists but never executed
- Mirrors pbx-web findings exactly
- Both templates created same date (2026-05-27) but unused

## Data Consistency

The whisper-stt collection successfully mirrors the pbx-web schema:
- Same metadata structure
- Same field names and types
- Same date range (30 days ending 2026-07-24)
- Cross-referenced comparison note

## Output Location

`~/scratch/whisper-stt-deployments-30d.json`
