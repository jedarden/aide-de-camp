# pbx-web-build Workflow Query Documentation

## Query for Last 30 Days

**Date range:** 2026-07-07 to 2026-08-06 (30 days from 2026-08-06)

### Method 1: Name Pattern + Date Filter (Recommended)

**IMPORTANT:** Workflows created from WorkflowTemplates do **NOT** automatically receive the `workflows.argoproj.io/workflow-template` label. Kubernetes field-selectors also **do NOT support wildcard patterns** (only exact matches with =, ==, !=).

The most reliable method is to fetch all workflows as JSON and filter by both name pattern and creation timestamp:

```bash
kubectl --kubeconfig=/home/coding/.kube/iad-ci.kubeconfig \
  get workflows -n argo-workflows \
  -o json | \
jq -r '.items[] | 
  select(.metadata.name | startswith("pbx-web-build-")) | 
  select(.metadata.creationTimestamp >= "2026-07-07") | 
  "\(.metadata.name) \(.status.phase) \(.metadata.creationTimestamp)"'
```

**Output format:** `workflow-name status creation-timestamp`

### Method 2: Simple grep Approach

For quick ad-hoc queries without JSON parsing:

```bash
kubectl --kubeconfig=/home/coding/.kube/iad-ci.kubeconfig \
  get workflows -n argo-workflows \
  --sort-by=.metadata.creationTimestamp | \
grep pbx-web-build
```

### Method 3: Custom Columns with Name Filter

For a tabular view with custom columns and name filtering:

```bash
kubectl --kubeconfig=/home/coding/.kube/iad-ci.kubeconfig \
  get workflows -n argo-workflows \
  --field-selector=metadata.name=pbx-web-build-xxx \
  --sort-by=.metadata.creationTimestamp \
  -o custom-columns=NAME:.metadata.name,PHASE:.status.phase,CREATED:.metadata.creationTimestamp
```

Note: `--field-selector` does NOT support wildcard patterns, so you must know the exact workflow name.

## Key Findings from Testing (2026-08-06)

### Label Behavior
- **Workflow templates exist:** `pbx-web-build`, `website-build`, and `devimprint-website-builder-build` templates are present in argo-workflows namespace (created 71d ago, 2026-05-27)
- **No workflow instances:** No pbx-web-build workflow instances exist (0 results) - template has never been run
- **Label behavior discovered:** Event-triggered workflows (via argo-events) do NOT receive the `workflows.argoproj.io/workflow-template` label
- **Best approach:** Name pattern filtering with `jq` is more reliable than label filtering

### Field Selector Limitations
- **No wildcard support:** Kubernetes field-selectors do NOT support wildcard patterns (`*`)
- **Only exact matches:** Field-selectors support only exact matches with operators: `=`, `==`, `!=`
- **No creationTimestamp filter:** Cannot filter by `metadata.creationTimestamp` directly in field-selector

### Query Verification
Tested with `armor-build` workflows (which have recent instances) - query returned:
```
armor-build-kgkvv Running 2026-08-07T00:33:45Z
armor-build-pvjrh Running 2026-08-07T00:38:05Z
armor-build-sq5xr Failed 2026-08-07T00:28:50Z
```

The pbx-web-build query runs successfully but returns no results (expected - no instances exist).

## Date Calculation

To calculate "30 days ago" for any date:

```bash
date -d "30 days ago" +%Y-%m-%d
```

For 2026-08-06, this gives `2026-07-07`.

## Complete, Tested Query

**Final working query for pbx-web-build workflows from last 30 days:**

```bash
kubectl --kubeconfig=/home/coding/.kube/iad-ci.kubeconfig \
  get workflows -n argo-workflows \
  -o json | \
jq -r '.items[] | 
  select(.metadata.name | startswith("pbx-web-build-")) | 
  select(.metadata.creationTimestamp >= "2026-07-07") | 
  "\(.metadata.name) \(.status.phase) \(.metadata.creationTimestamp)"'
```

This query:
- ✅ Filters by workflow name pattern (pbx-web-build-*)
- ✅ Filters by creation time (last 30 days from 2026-08-06)
- ✅ Returns workflow names, status, and timestamps
- ✅ Is documented and reproducible
- ✅ Tested and verified with other workflow types
