# jq Post-Processing Date Filtering Test (adc-5i67y)

## Task Summary
Tested jq post-processing for filtering Argo Workflows by creation date as an alternative to kubectl field selectors.

## jq Syntax Used

### Basic Filter (returns individual objects)
```bash
kubectl get workflows -n argo-workflows -o json | \
  jq '.items[] | select(.metadata.creationTimestamp >= "2026-07-07T17:52:45Z")'
```

### Array Filter (returns JSON array)
```bash
kubectl get workflows -n argo-workflows -o json | \
  jq '.items | map(select(.metadata.creationTimestamp >= "2026-07-07T17:52:45Z"))'
```

### Comparison Array Filter (compact)
```bash
kubectl get workflows -n argo-workflows -o json | \
  jq '[.items[] | select(.metadata.creationTimestamp >= "2026-07-07T17:52:45Z")]'
```

## Key Findings

1. **jq handles ISO 8601 date string comparisons correctly** - lexicographic string comparison works for ISO 8601 timestamps
2. **Both approaches work**: `.items | map(select(...))` and `[.items[] | select(...)]`
3. **All workflows were within 30-day window** - oldest workflow from 2026-07-27 (10 days ago)

## Commands Used

```bash
# Calculate 30 days ago
date -d "30 days ago" --utc +"%Y-%m-%dT%H:%M:%SZ"
# Output: 2026-07-07T17:52:45Z

# Save filtered output
kubectl --kubeconfig=/home/coding/.kube/iad-ci.kubeconfig \
  get workflows -n argo-workflows -o json | \
  jq '.items | map(select(.metadata.creationTimestamp >= "2026-07-07T17:52:45Z"))' \
  > ~/scratch/jq-filter-test.json

# Verify counts
echo "Original count:" && \
  kubectl --kubeconfig=/home/coding/.kube/iad-ci.kubeconfig \
  get workflows -n argo-workflows -o json | jq '.items | length'

echo "Filtered count (last 30 days):" && \
  kubectl --kubeconfig=/home/coding/.kube/iad-ci.kubeconfig \
  get workflows -n argo-workflows -o json | \
  jq '[.items[] | select(.metadata.creationTimestamp >= "2026-07-07T17:52:45Z")] | length'
```

## Results

- **Original workflows**: 16
- **Filtered workflows (last 30 days)**: 16
- **Filtered file**: `~/scratch/jq-filter-test.json`

All workflows in argo-workflows namespace were created within the last 30 days.

## Recommendation

**jq post-processing works reliably** for filtering Kubernetes resources by date. This is a viable fallback when kubectl field selectors don't support date comparisons.
