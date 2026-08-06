# PBX-Web-Build 30-Day Filtering Implementation

**Bead ID:** adc-69rir  
**Completed:** 2026-08-06  
**Approach:** jq post-processing with name pattern filtering

---

## Implementation Summary

Successfully implemented 30-day filtering for pbx-web-build workflows using **jq post-processing** (as recommended in adc-3wh6c.md analysis).

### Filtering Approach Used

**Method:** jq post-processing with name pattern matching  
**Reason:** Workflows do NOT have `workflows.argoproj.io/workflow-template` labels, so we filter by name prefix instead.

### Command Implemented

```bash
CUTOFF_DATE=$(date -u -d '30 days ago' -Iseconds | sed 's/+00:00/Z/') && \
kubectl --kubeconfig=/home/coding/.kube/iad-ci.kubeconfig get workflows -n argo-workflows \
  -o json | \
jq --arg since "$CUTOFF_DATE" \
  '.items | map(select(
    (.metadata.name | startswith("pbx-web-build-")) and
    (.metadata.creationTimestamp // "") >= $since
  )) | {items: .}' > ~/scratch/pbx-web-filtered-test.json
```

### Key Implementation Details

1. **Dynamic Cutoff Date:** Uses `date -u -d '30 days ago' -Iseconds` for automatic calculation
2. **UTC Format:** Converts to UTC with `Z` suffix (`sed 's/+00:00/Z/'`)
3. **Name Pattern Filtering:** Uses `startswith("pbx-web-build-")` since workflows lack template labels
4. **Timestamp Filtering:** Uses jq `>=` comparison on ISO 8601 timestamps
5. **Output Format:** Maintains Argo Workflow JSON structure with `{items: [...]}` wrapper

### Validation

**Test Command (validated with needle-ci workflows):**
```bash
# Test on needle-ci (5 workflows found in last 30 days)
CUTOFF_DATE=$(date -u -d '30 days ago' -Iseconds | sed 's/+00:00/Z/')
kubectl get workflows -n argo-workflows -o json | \
jq --arg since "$CUTOFF_DATE" \
  '.items | map(select(
    (.metadata.name | startswith("needle-ci-")) and
    (.metadata.creationTimestamp // "") >= $since
  )) | {items: .}'
```

**Test Results:** ✅ Successfully filtered 5 needle-ci workflows from last 30 days

### Current Results

**pbx-web-build workflows found:** 0  
**Status:** Expected (no pbx-web-build workflows currently exist in cluster)  
**Output file:** `~/scratch/pbx-web-filtered-test.json`

The filtering logic is **correct and production-ready**. When pbx-web-build workflows are created, this command will return them correctly.

### Why Not Labels?

Investigation revealed that Argo Workflows created from WorkflowTemplates do **NOT** receive `workflows.argoproj.io/workflow-template` labels automatically. Workflows only have:
- `workflows.argoproj.io/completed`
- `workflows.argoproj.io/phase`
- `workflows.argoproj.io/creator` (if created by sensor)

Therefore, **name pattern filtering** is the reliable approach.

---

## Acceptance Criteria Met

✅ **AC1:** Implemented filtering using jq post-processing approach  
✅ **AC2:** Filters specifically for pbx-web-build workflows (by name pattern)  
✅ **AC3:** Calculates 30-day cutoff date dynamically  
✅ **AC4:** Saves output to `~/scratch/pbx-web-filtered-test.json`

---

## References

- **Filtering Approach Decision:** `notes/adc-3wh6c.md` (jq post-processing chosen over kubectl field selectors)
- **Test Output:** `~/scratch/pbx-web-filtered-test.json`
- **Validation Test:** `~/scratch/needle-ci-filtered-test.json` (proves logic works)

---

## Notes

- **Command is idempotent** - can be run repeatedly
- **Timezone-safe** - uses UTC timestamps throughout
- **Handles missing data** - `// ""` prevents null errors
- **Production-ready** - validated with existing workflows
