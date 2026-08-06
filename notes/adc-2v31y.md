# Task adc-2v31y: Query pbx-web-build Workflows (Last 30 Days)

## Execution Summary

Executed kubectl query against iad-ci cluster to retrieve pbx-web-build workflow runs from the last 30 days.

## Results

**Total workflows found: 0**

The query found no pbx-web-build workflow runs in the argo-workflows namespace for the last 30 days.

### Verification Steps

1. Verified cluster access working: 38 total workflows exist in argo-workflows namespace
2. Searched for any pbx-related workflows: none found
3. Confirmed query syntax was correct (based on adc-30n6n verification)

## Conclusion

No pbx-web-build workflow runs have been executed in the last 30 days. This could indicate:
- The workflow template exists but hasn't been triggered
- Build activity is handled differently
- The template label may differ from expected format

## Raw Data

Saved to: `~/scratch/pbx-web-raw.json`

## Query Used

```bash
kubectl --kubeconfig=/home/coding/.kube/iad-ci.kubeconfig \
  get workflows -n argo-workflows \
  -l workflows.argoproj.io/workflow-template=pbx-web-build \
  -o json
```

**Date executed:** 2026-08-06
**Cluster:** iad-ci
**Namespace:** argo-workflows
