# Task: Integrate Date Filter into kubectl Query

## Task Objective
Combine the base kubectl query with a date field selector to filter pbx-web-build workflows from the last 30 days.

## Technical Limitation: Field Selectors Don't Support Inequality Operators

### Attempted Field Selector Approach
```bash
kubectl get workflows -n argo-workflows \
  -l workflows.argoproj.io/workflow-template=pbx-web-build \
  --field-selector=metadata.creationTimestamp>=2026-07-08T02:03:28Z
```

### Error Result
```
Error from server (BadRequest): Unable to find "argoproj.io/v1alpha1, Resource=workflows" 
that match label selector "workflows.argoproj.io/workflow-template=pbx-web-build", 
field selector "metadata.creationTimestamp": invalid selector: 'metadata.creationTimestamp'; 
can't understand 'metadata.creationTimestamp'
```

### Root Cause
**Kubernetes field selectors do not support inequality operators (>=, <=, >, <) on timestamp fields.** This is a known API limitation that applies to all resource types, not just workflows.

Field selectors only support:
- Exact match: `field=value`
- Set operators: `field=in (value1,value2)`
- Equality: `field==value`, `field!=value`

## Working Solution: jq Post-Processing

The existing implementation at `/home/coding/aide-de-camp/scripts/query_pbx_web_workflows_30days.sh` uses jq post-processing, which is the correct approach.

### How It Works
1. Fetch all workflows with the template label selector
2. Calculate 30-day cutoff date in ISO 8601 format
3. Use jq to filter by `creationTimestamp >= cutoff_date`
4. Return structured JSON with filtering statistics

### Validated Query
```bash
# Base query with label selector (works)
kubectl get workflows -n argo-workflows \
  -l workflows.argoproj.io/workflow-template=pbx-web-build \
  -o json

# jq filtering (handles date comparison correctly)
jq --arg cutoff "2026-07-08T02:05:19Z" \
  '[.items[] | select(.metadata.creationTimestamp >= $cutoff)]'
```

### Test Results
- ✅ Executes successfully (no field selector errors)
- ✅ Correctly filters by creation date
- ✅ Handles edge cases (no workflows, empty results)
- ✅ Returns structured JSON with statistics

## Why Field Selectors Can't Work

Field selectors in Kubernetes are implemented as server-side filtering with a very restricted syntax for performance and simplicity. The API server only supports:

1. **Exact matches**: `name=my-workflow`
2. **Equality operators**: `status.phase==Succeeded`
3. **Set membership**: `name in (a,b,c)`

Timestamp comparisons require:
- Parsing ISO 8601 dates
- Performing chronological comparisons
- Handling timezone conversions

This complexity is why the Kubernetes API doesn't support it in field selectors. The jq post-processing approach is the standard pattern for date-based filtering.

## Conclusion

The task requirement to "integrate date filter into kubectl query using field selector" is **technically impossible** due to Kubernetes API limitations. The existing jq-based solution is the correct and only viable approach for date-filtered workflow queries.

### Working Implementation
- Script: `/home/coding/aide-de-camp/scripts/query_pbx_web_workflows_30days.sh`
- Method: jq post-processing after kubectl query
- Status: Fully functional and tested
- Output: Structured JSON with filtering statistics

### Alternative Not Feasible
- Field selector with inequality operators: ❌ Not supported by Kubernetes API
- Server-side date filtering: ❌ No API endpoint supports this
- Custom resource definitions: ❌ Would require cluster-wide changes

The jq post-processing approach is the industry-standard pattern for this use case.
