# adc-3be5f: Unit tests for src/fetch/clusters.py

## Status: COMPLETE

All unit tests were implemented in commit 04faeb4 on 2026-07-23. The test suite is comprehensive and complete.

## Test Coverage Summary

### Test File: `tests/test_clusters_resolution.py`

**23 tests total, all passing**

### Test Classes

1. **TestResolveArgocdEndpoint** (8 tests)
   - ✅ test_none_cluster_unsatisfiable - None cluster returns unsatisfiable with "no cluster configured" reason
   - ✅ test_empty_string_cluster_unsatisfiable - Empty string cluster returns unsatisfiable
   - ✅ test_cluster_absent_from_config_unsatisfiable - Unknown cluster returns "no ArgoCD mapping" reason
   - ✅ test_read_only_proxy_with_argocd_api_satisfiable - read-only-proxy with argocd_api is satisfiable
   - ✅ test_authenticated_access_unsatisfiable - authenticated access returns "requires authentication" reason
   - ✅ test_unknown_access_mode_unsatisfiable - Unknown access mode returns "unsupported access mode" reason
   - ✅ test_read_only_proxy_missing_argocd_api_unsatisfiable - Missing argocd_api returns unsatisfiable
   - ✅ test_reason_is_friendly_string - All unsatisfiable results have non-empty reason strings

2. **TestHotReload** (5 tests)
   - ✅ test_cache_persists_on_same_mtime - Cache reused when mtime unchanged
   - ✅ test_force_reload_bypasses_mtime_check - force=True triggers reload
   - ✅ test_mtime_change_triggers_reload - Mtime change triggers reload
   - ✅ test_reset_cache_clears_state - reset_cache() clears cache for next read
   - ✅ test_get_clusters_returns_dict - Returns valid dict with cluster mappings

3. **TestPoisonProtection** (6 tests)
   - ✅ test_read_clusters_file_returns_cache_on_yaml_error - Malformed YAML preserves cache
   - ✅ test_read_clusters_file_returns_cache_on_non_dict_top_level - Non-dict top-level preserves cache
   - ✅ test_read_clusters_file_returns_cache_on_non_dict_clusters_key - Non-dict clusters key preserves cache
   - ✅ test_read_clusters_file_returns_cache_on_file_not_found - Missing file returns cached data
   - ✅ test_read_clusters_file_returns_empty_on_error_with_no_cache - Empty cache on error with no prior cache
   - ✅ test_get_clusters_preserves_cache_on_parse_failure - Parse failure preserves last-known-good cache

4. **TestArgocdResolutionDataclass** (2 tests)
   - ✅ test_satisfiable_resolution - Satisfiable resolution has all fields populated
   - ✅ test_unsatisfiable_resolution_includes_reason - Unsatisfiable includes reason

5. **TestArgocdEndpointUnresolvableException** (2 tests)
   - ✅ test_exception_carry_reason - Exception carries human-readable reason
   - ✅ test_exception_with_cluster - Exception optionally carries cluster name

## Acceptance Criteria Met

- ✅ Every resolve_argocd_endpoint branch has passing assertion with expected reason substring
- ✅ Hot-reload verified (mtime-based reload, reset_cache clears cache)
- ✅ Poison protection verified (malformed YAML returns last-known-good cache)
- ✅ reset_cache() fixture prevents cache state leakage between tests (autouse fixture)

## Functions Tested

All functions from src/fetch/clusters.py are tested:
- resolve_argocd_endpoint
- get_clusters
- reset_cache
- _read_clusters_file (via poison protection tests)
- ArgocdResolution dataclass
- ArgocdEndpointUnresolvable exception

## Verification

All tests pass:
```bash
.venv/bin/python -m pytest tests/test_clusters_resolution.py -v
# 23 passed in 0.08s
```
