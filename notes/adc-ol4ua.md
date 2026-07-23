# adc-ol4ua: Fail-fast caveat tests for ArgoCD endpoint resolution

## Changes Made

Added three new test methods to `tests/test_fetch_source_types.py` in the `TestArgocdApp` class:

### 1. `test_authenticated_cluster_fails_fast_with_caveat`
- Tests apexalgo-iad (cluster with `access: authenticated` in config/clusters.yaml)
- Asserts `ArgocdEndpointUnresolvable` is raised with a reason mentioning "authentication"
- Asserts cluster name "apexalgo-iad" appears in the reason
- **CRITICAL**: Asserts `client.requests == []` — no HTTP request issued

### 2. `test_unmapped_cluster_fails_fast_with_caveat`
- Tests a cluster absent from config/clusters.yaml (e.g., 'some-unmapped-cluster')
- Asserts `ArgocdEndpointUnresolvable` is raised with a reason mentioning "no ArgoCD mapping"
- Asserts cluster name appears in the reason
- **CRITICAL**: Asserts `client.requests == []` — no HTTP request issued

### 3. `test_none_cluster_fails_fast_with_caveat`
- Tests `cluster=None` (no cluster configured)
- Asserts `ArgocdEndpointUnresolvable` is raised with a reason mentioning "no cluster configured"
- **CRITICAL**: Asserts `client.requests == []` — no HTTP request issued

## Acceptance Criteria Met

Both primary triggers (apexalgo-iad and unmapped cluster) produce a caveat whose reason substring names the cluster and both assert zero HTTP requests, proving a wrong-instance query is impossible.

## Implementation Notes

The existing implementation in `src/fetch/orchestrator.py` already handles these cases correctly:
- `_fetch_argocd_app` calls `resolve_argocd_endpoint(context.cluster)` 
- If `resolution.satisfiable` is False, it raises `ArgocdEndpointUnresolvable` with the human-readable reason
- This exception is raised BEFORE any HTTP call, preventing wrong-instance queries
- The exception is caught by `_execute_source` and bucketed as a failed source
- The fetch loop emits a `fetch_coverage` caveat carrying the reason

These tests verify that behavior works as designed.
