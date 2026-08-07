# Whisper-STT Latency Query - Summary Statistics

## Query Parameters
- **Script:** query_whisper_stt_latency.py  
- **Execution Time:** 2026-08-07T07:01:19Z  
- **Query Window:** 30 days (2026-07-08 to 2026-08-07)  
- **Target Template:** whisper-stt-build  
- **Cluster:** iad-ci (argo-workflows namespace)  

## Summary Statistics

| Metric | Value |
|--------|-------|
| **Total Workflows Retrieved** | 15 (from cluster) |
| **whisper-stt-build Workflows** | 0 |
| **Total Records Found** | 0 |
| **Successful Workflows** | 0 |
| **Failed Workflows** | 0 |
| **Valid Duration Records** | 0 |
| **Missing Timestamps** | 0 |
| **Records with Processing Duration** | 0 |
| **Date Coverage** | 0 days (no data) |

## Temporal Analysis

### Expected Date Range: 2026-07-08 to 2026-08-07 (30 days)
- **Days with Data:** 0
- **Days without Data:** 30
- **Data Coverage:** 0%

### Active Workflow Templates in Cluster (Last 30 Days)
```
needle-ci: 6 workflows (40% of total)
gribtract-ci: 3 workflows (20% of total)
seam-ci: 2 workflows (13% of total)
mta-my-way-build: 2 workflows (13% of total)
warden-build: 1 workflow (7% of total)
b2-usage-exporter-build: 1 workflow (7% of total)
whisper-stt-build: 0 workflows (0% of total) ← TARGET
```

## Anomaly Detection Results

### Critical Anomalies
1. **Complete Data Gap:** No whisper-stt workflows found in entire 30-day window
2. **Template Exists But Unused:** whisper-stt-build WorkflowTemplate is defined but has zero executions
3. **Possible CI/CD Gap:** Template auto-trigger may not be configured or working

### Data Quality Assessment
- **Completeness:** ❌ FAILED - No data available
- **Temporal Coverage:** ❌ FAILED - 0% coverage  
- **Metric Availability:** ❌ FAILED - No duration metrics to analyze
- **Data Structure:** ✅ PASS - Output JSON properly formatted

## Root Cause Analysis

The whisper-stt-build WorkflowTemplate exists at:
`declarative-config/k8s/iad-ci/argo-workflows/whisper-stt-workflowtemplate.yml`

Template configuration:
- **Target:** jedarden/nixos-asterisk repository (whisper-stt/ subdirectory)
- **Trigger:** Watches for changes to `whisper-stt/VERSION` file
- **Action:** Auto-bumps version, builds Docker image, pushes to ronaldraygun/whisper-stt

**Hypothesis:** The template is not triggered by automation (missing webhook, manual trigger only, or never invoked).

## Conclusion

**Query Status:** ✅ Successfully executed  
**Data Quality:** ❌ Complete data gap  
**Validation Status:** ⚠️ Critical anomaly detected  

The whisper-stt latency query infrastructure is functional, but no data is available because the whisper-stt-build workflow has never been executed in the observable window. This indicates a potential gap in the CI/CD pipeline for whisper-stt components.

---

**Output Files Generated:**
1. `data/latency-metrics/whisper-stt-latency-raw.json` - Raw query results (empty dataset)
2. `data/latency-metrics/whisper-stt-validation-report.md` - Detailed validation analysis
3. `data/latency-metrics/whisper-stt-summary-stats.md` - This summary document

**Exit Status:** 0 (query successful, data gap expected behavior given no workflows)
