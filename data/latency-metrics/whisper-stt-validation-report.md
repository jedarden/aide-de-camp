# Whisper-STT Latency Query Validation Report

**Generated:** 2026-08-07T07:01:19Z  
**Query Window:** 2026-07-08T07:01:18Z to 2026-08-07T07:01:18Z (30 days)  
**Script:** query_whisper_stt_latency.py  
**Output File:** data/latency-metrics/whisper-stt-latency-raw.json

## Validation Summary

| Criterion | Status | Details |
|-----------|--------|---------|
| Script execution | ✅ PASS | Script executed successfully with exit code 0 |
| JSON output structure | ✅ PASS | Output contains complete metadata structure |
| Date coverage | ❌ ANOMALY | No whisper-stt workflows found in 30-day window |
| Processing duration metrics | ❌ N/A | No workflows found, so no metrics to validate |
| Temporal gaps | ⚠️ CRITICAL | Entire 30-day window has no whisper-stt workflows |

## Data Quality Assessment

### Total Records Found: 0

**Workflow Statistics:**
- Total workflows in cluster: 15 (retrieved from argo-workflows namespace)
- whisper-stt-build workflows: 0
- Matching workflows in 30-day window: 0

**Active Workflow Templates in Cluster:**
```
b2-usage-exporter-build: 1 workflow
gribtract-ci: 3 workflows
mta-my-way-build: 2 workflows
needle-ci: 6 workflows
seam-ci: 2 workflows
warden-build: 1 workflow
whisper-stt-build: 0 workflows  ← ANOMALY
```

### Anomaly Detection

**Critical Finding:** The whisper-stt-build WorkflowTemplate exists in the cluster, but **zero workflows** have been created from it in the last 30 days (and likely ever).

**Possible Explanations:**
1. **Template never triggered** - The whisper-stt-build template exists but has never been executed
2. **Old workflows deleted** - Previous whisper-stt workflows existed but were deleted/purged
3. **Wrong template name** - The actual whisper-stt workflows might use a different template name
4. **External execution** - Whisper-STT builds might run elsewhere (GitHub Actions, manual builds, etc.)

### Output JSON Structure Validation

The output file `whisper-stt-latency-raw.json` contains:

```json
{
  "query_metadata": {
    "timestamp": "2026-08-07T07:01:19.415627",
    "days_back": 30,
    "start_date": "2026-07-08T07:01:18.871003",
    "end_date": "2026-08-07T07:01:18.871003",
    "workflow_template": "whisper-stt-build",
    "namespace": "argo-workflows"
  },
  "raw_data": [],
  "summary": {
    "total_workflows": 0,
    "successful_workflows": 0,
    "failed_workflows": 0,
    "other_phases": 0,
    "valid_duration_records": 0,
    "missing_timestamps": 0
  },
  "errors": null
}
```

**Structure Validation:** ✅ All required fields present, properly formatted, no parse errors

## Recommendations

1. **Investigate template usage** - Check if whisper-stt-build template should be triggered (e.g., by git push to nixos-asterisk repo)
2. **Check alternative sources** - Determine if whisper-stt latency data should be collected from elsewhere
3. **Manual trigger test** - Consider manually triggering whisper-stt-build to verify template works
4. **Check declarative-config** - Review declarative-config/k8s/iad-ci/argo-workflows/ to see if whisper-stt-build template exists and is properly configured

## Conclusion

The query executed successfully but found **no whisper-stt workflows** in the 30-day window. This represents a **complete data gap** for the intended latency analysis. The workflow template exists but appears to never have been executed, suggesting either:
- The template is not triggered by any automation
- The template is newly created and hasn't been used yet
- The template is a fallback/reserve that isn't currently in use

**Next Steps:** Investigate the whisper-stt-build template configuration and determine if this data gap is expected or indicates a missing CI/CD trigger.

---

**Validation Status:** ⚠️ DATA GAP DETECTED  
**Exit Code:** 0 (script success)  
**Data Quality:** FAILED (no data to analyze)  
**Anomaly Severity:** CRITICAL (entire 30-day window empty)
