# PBX-Web Latency Query Validation Log

**Execution Date:** 2026-08-07T06:44:50Z  
**Query Window:** 2026-07-08T06:44:49Z to 2026-08-07T06:44:49Z (31 days)  
**Cluster:** iad-ci  
**Output File:** `data/latency-metrics/pbx-web-latency-raw.json`

## Validation Results

### ✅ Script Execution
- Query script executed successfully without errors
- Kubectl connection to iad-ci cluster established
- Retrieved 15 total workflows from cluster
- JSON output file generated successfully

### ✅ Output Data Structure
The output JSON contains all required fields:
- `query_metadata`: Complete with timestamp, date range, cluster info
- `latency_metrics`: All percentile metrics present (p50, p75, p90, p95, p99, mean, median, min, max)
- `raw_data`: Empty array (no pbx-web workflows found)
- `data_quality`: Complete with valid/invalid workflow counts and error array

### ✅ Date Coverage
- Query covered 31 days (2026-07-08 to 2026-08-07)
- No temporal gaps detected (N/A - no data to analyze)

### ⚠️ Data Availability Issue
**Finding:** No pbx-web-build workflows exist in the iad-ci cluster

**Cluster Analysis:**
- Total workflows in cluster: 15
- Workflow templates found:
  - `needle-ci`: 6 workflows
  - `gribtract-ci`: 3 workflows
  - `mta-my-way-build`: 2 workflows
  - `armor-drift-check`: 1 workflow
  - `b2-usage-exporter-build`: 1 workflow
  - `seam-ci`: 1 workflow
  - `warden-build`: 1 workflow
- **`pbx-web-build`: 0 workflows**

### Metrics Summary
All latency metrics are zero (expected with no data):
- `count`: 0 workflows
- `p50_seconds`: 0.0
- `p95_seconds`: 0.0
- `p99_seconds`: 0.0
- `mean_seconds`: 0.0
- `min_seconds`: 0.0
- `max_seconds`: 0.0

### Data Quality Assessment
- `total_workflows_found`: 0
- `valid_workflows`: 0
- `invalid_workflows`: 0
- `errors`: [] (no technical errors)

## Conclusion

The query script functioned correctly but found no pbx-web-build workflows to analyze. This is expected behavior - the script correctly identified that:
1. The cluster contains workflows from other templates
2. None match the `pbx-web-build` workflow template
3. The date range filtering logic is working properly

**Recommendation:** Verify if pbx-web-build workflows should exist in the cluster. If pbx-web latency monitoring is required, the pbx-web-build WorkflowTemplate may need to be triggered or deployed to iad-ci.

## Anomalies Detected

None. The empty result set is accurate given the cluster state.
