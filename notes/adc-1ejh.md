# adc-1ejh: Cluster to ArgoCD Endpoint Resolution — COMPLETED

## Implementation Summary

This bead has been fully implemented and tested. All acceptance criteria met.

## What Was Implemented

### 1. config/clusters.yaml
- Maps clusters to their ArgoCD API endpoints
- Defines access mode per cluster (`read-only-proxy` vs `authenticated`)
- Documented with comments explaining the security model
- Hot-reloaded via mtime-checked cache

### 2. src/fetch/clusters.py
- `ArgocdResolution` dataclass with `satisfiable` flag and `reason` field
- `resolve_argocd_endpoint(cluster)` function with comprehensive resolution logic
- `ArgocdEndpointUnresolvable` exception for clean failure propagation
- mtime-checked hot-reload (mirrors other config artifacts)
- Poison protection: malformed YAML returns last-known-good cache

### 3. src/fetch/orchestrator.py
- `_fetch_argocd_app()` uses `resolve_argocd_endpoint()` before any HTTP call
- Raises `ArgocdEndpointUnresolvable` when unsatisfiable
- Exception is caught by orchestrator and surfaced as `fetch_coverage` caveat

### 4. config/registry.yaml
- `argocd_app` field on project entries
- Defaults to project slug when omitted (e.g., `kalshi-tape`)
- Explicit values preserved (e.g., `options-pipeline`, `ibkr-mcp`)

### 5. Tests (35 tests, all passing)
- `tests/test_clusters_resolution.py` — 23 unit tests covering all branches
- `tests/test_argocd_resolution_acceptance.py` — 12 acceptance tests against real config

## Acceptance Criteria Status

✅ **Tests with mocked endpoints**: `test_clusters_resolution.py` has 8 unit tests covering:
- Read-only proxy cluster → satisfiable with correct API
- Authenticated cluster → unsatisfiable with caveat
- Unknown/missing cluster → unsatisfiable with caveat
- Poison protection on malformed YAML

✅ **apexalgo-iad caveat**: `test_argocd_resolution_acceptance.py::test_apexalgo_iad_unsatisfiable_with_authentication_caveat`
- Verifies honest caveat about no no-auth read-only proxy
- Documents this is intentional until HUMAN decision bead

✅ **Unmapped cluster caveat**: `test_clusters_resolution.py::test_cluster_absent_from_config_unsatisfiable`
- Verifies caveat mentions "no ArgoCD mapping"

✅ **argocd_app default**: `test_argocd_resolution_acceptance.py::test_kalshi_tape_defaults_argocd_app_to_slug`
- Verifies default to slug when omitted
- Verifies explicit values preserved

## Child Beads

- adc-3be5f: Unit tests for clusters.py
- adc-5g4nl: Acceptance criteria integration tests
- adc-ol4ua: Fail-fast caveat tests

## Verification

```bash
# Run all argocd resolution tests
.venv/bin/python -m pytest tests/test_clusters_resolution.py tests/test_argocd_resolution_acceptance.py -v

# Result: 35 passed in 0.15s
```

All security guarantees met:
- No silent wrong-instance queries
- Honest caveats for unsatisfiable cases
- Hot-reload without restart
- Poison protection on bad edits
