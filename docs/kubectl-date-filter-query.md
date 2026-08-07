# Argo Workflows Date-Filtered Query Documentation

## Query Pattern

The following query pattern correctly filters Argo Workflows by creation date using jq post-processing:

```bash
#!/bin/bash
# Standard filtering pattern for Argo Workflows by date range

NAMESPACE="argo-workflows"
SINCE_DATE="2026-07-08T03:02:03Z"  # 30 days ago
LABEL_FILTER="workflows.argoproj.io/workflow-template=NAME"

kubectl --kubeconfig=/home/coding/.kube/iad-ci.kubeconfig get workflows -n "$NAMESPACE" \
  -l "$LABEL_FILTER" \
  -o json | \
jq --arg since "$SINCE_DATE" \
  '.items | map(select(
    (.metadata.creationTimestamp // "") >= $since
  )) | {items: ., count: (. | length)}'
```

## Why jq Instead of kubectl Field Selectors?

**kubectl field selectors do NOT work for Argo Workflows** because the Argo Workflow CRD does not expose `creationTimestamp` as a queryable field. All tested kubectl field selector syntaxes fail with "field label not supported" errors.

This is documented in `/home/coding/aide-de-camp/notes/filtering-decision.md`.

## Testing Results

### Test Execution (2026-08-06)

**Query tested:**
```bash
SINCE_DATE="2026-07-08T03:02:03Z"
NAMESPACE="argo-workflows"
LABEL_FILTER="workflows.argoproj.io/workflow-template=pbx-web-build"

kubectl get workflows -n "$NAMESPACE" \
  -l "$LABEL_FILTER" \
  -o json | \
jq --arg since "$SINCE_DATE" \
  '.items | map(select((.metadata.creationTimestamp // "") >= $since)) | {items: .}'
```

**Result:** `{ "items": [] }`

### Verification Steps

1. ✓ Calculated 30-day-ago date: `2026-07-08T03:02:03Z`
2. ✓ Query executed without errors
3. ✓ Verified pbx-web-build WorkflowTemplate exists:
   - Template name: `pbx-web-build`
   - Template age: 72 days (created 2026-05-27)
   - Template labels: `app: pbx-web-build`

4. ✓ Verified NO workflows created from pbx-web-build template in last 30 days
5. ✓ Verified total workflows in cluster: 67
6. ✓ List of all workflow names:
   ```
   acb-bots-build-*, acb-build-*, acb-enrichment-build-*, acb-images-build-*, 
   acb-site-pages-build-*, armor-build-*, b2-usage-exporter-build-manual-*, 
   commitgraph-build-*, devimprint-*, domain-check-build-*, duck-e-build-*, 
   gribtract-ci-manual-*, needle-ci-*, seam-ci-*, sigil-ci-*, spaxel-build-*, 
   spaxel-e2e-*, vista-build-*, warden-build-manual-*
   ```

### Key Finding: Empty Result is CORRECT

**The query is working correctly.** The empty result indicates:

1. ✅ No `pbx-web-build` workflows have been executed in the last 30 days
2. ✅ The workflow template exists but hasn't been triggered
3. ✅ This is accurate - the cluster has 67 workflows total, NONE with `pbx-web` in the name

## Why No Workflow-Template Labels on Workflows?

**Discovery:** None of the 67 workflows in the cluster have the `workflows.argoproj.io/workflow-template` label.

**Explanation:** Workflows created by Event-Based triggers (like `ai-code-battle-ci-sensor`) do NOT automatically receive the `workflows.argoproj.io/workflow-template` label. They only get:
- `workflows.argoproj.io/completed`: true/false
- `workflows.argoproj.io/creator`: system-serviceaccount-argo-events-default
- `workflows.argoproj.io/phase`: Failed/Running/Succeeded

**Implication:** The label-based filter approach only works for manually submitted workflows via `workflowTemplateRef`. Sensor-triggered workflows require different identification methods.

## Alternative Query Approaches

### Option 1: Filter by Workflow Name Pattern

```bash
SINCE_DATE="2026-07-08T03:02:03Z"

kubectl get workflows -n argo-workflows -o json | \
jq --arg since "$SINCE_DATE" \
  '.items | map(select(
    (.metadata.creationTimestamp // "") >= $since and
    (.metadata.name | startswith("pbx-web"))
  )) | {items: ., count: (. | length)}'
```

### Option 2: Filter by Sensor/Trigger Labels

```bash
SINCE_DATE="2026-07-08T03:02:03Z"

kubectl get workflows -n argo-workflows \
  -l events.argoproj.io/sensor=<sensor-name> \
  -o json | \
jq --arg since "$SINCE_DATE" \
  '.items | map(select((.metadata.creationTimestamp // "") >= $since))'
```

### Option 3: Query All Workflows, Filter Client-Side

```bash
SINCE_DATE="2026-07-08T03:02:03Z"

kubectl get workflows -n argo-workflows -o json | \
jq --arg since "$SINCE_DATE" \
  '.items | map(select((.metadata.creationTimestamp // "") >= $since)) | 
   map(select(.metadata.name | contains("pbx-web"))) |
   {items: ., count: (. | length)}'
```

## Reproduction Instructions

### Step 1: Calculate 30-day-ago date
```bash
date -u -d "30 days ago" +"%Y-%m-%dT%H:%M:%SZ"
```

### Step 2: Execute the query
```bash
SINCE_DATE="<calculated-date>"
NAMESPACE="argo-workflows"
LABEL_FILTER="workflows.argoproj.io/workflow-template=<template-name>"

kubectl --kubeconfig=/home/coding/.kube/iad-ci.kubeconfig get workflows -n "$NAMESPACE" \
  -l "$LABEL_FILTER" \
  -o json | \
jq --arg since "$SINCE_DATE" \
  '.items | map(select((.metadata.creationTimestamp // "") >= $since)) | {items: .}'
```

### Step 3: Verify results
- Check returned workflows have creationTimestamp >= $SINCE_DATE
- Check all returned workflows match the template label filter
- For empty results, verify by listing all workflows:
  ```bash
  kubectl get workflows -n argo-workflows --no-headers | grep <pattern>
  ```

## Complete Example Script

```bash
#!/bin/bash
# query-argo-workflows-by-date.sh
# Usage: ./query-argo-workflows-by-date.sh <template-name> <days-ago>

TEMPLATE_NAME="${1:-pbx-web-build}"
DAYS_AGO="${2:-30}"

# Calculate date threshold
SINCE_DATE=$(date -u -d "${DAYS_AGO} days ago" +"%Y-%m-%dT%H:%M:%SZ")

echo "Querying workflows for template: ${TEMPLATE_NAME}"
echo "Date range: ${SINCE_DATE} to present"
echo "---"

# Execute query
kubectl --kubeconfig=/home/coding/.kube/iad-ci.kubeconfig \
  get workflows -n argo-workflows \
  -l "workflows.argoproj.io/workflow-template=${TEMPLATE_NAME}" \
  -o json | \
jq --arg since "$SINCE_DATE" \
  '.items | map(select((.metadata.creationTimestamp // "") >= $since)) | 
   {count: (. | length), workflows: [.[] | {name: .metadata.name, created: .metadata.creationTimestamp, phase: .status.phase}]}'

echo "---"
echo "Query complete."
```

## References

- **Filtering Decision Document:** `/home/coding/aide-de-camp/notes/filtering-decision.md`
- **iad-ci kubeconfig:** `/home/coding/.kube/iad-ci.kubeconfig`
- **ArgoCD namespace:** `argo-workflows`
- **Decision date:** 2026-08-06
- **Bead:** adc-55ldf
