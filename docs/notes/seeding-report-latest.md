# Demo Seeding Verification Report

**Generated:** 2026-07-23T15:37:29.957689

## Summary

- **Overall Status:** FAIL
- **Total Checks:** 4
  - Passed: 0
  - Failed: 2
  - Warnings: 0
  - Skipped: 2

## Check Details

### ❌ Registry Verification

**Status:** FAIL

**Message:** Failed with 4 error(s)

**Details:**

```json
{
  "errors": [
    "options-pipeline: repo_path does not exist: /home/coding/options-pipeline",
    "options-pipeline: ArgoCD endpoint not satisfiable for 'apexalgo-iad': Cluster 'apexalgo-iad' ArgoCD requires authentication (no no-auth read-only proxy available); ArgoCD source omitted",
    "ibkr-mcp: repo_path does not exist: /home/coding/ibkr-mcp",
    "ibkr-mcp: ArgoCD endpoint not satisfiable for 'apexalgo-iad': Cluster 'apexalgo-iad' ArgoCD requires authentication (no no-auth read-only proxy available); ArgoCD source omitted"
  ],
  "warnings": []
}
```

### ⏭️  Context Warmer

**Status:** SKIP

**Message:** Skipped (dry-run mode)

### ⏭️  Dispatch Execution

**Status:** SKIP

**Message:** Skipped (dry-run mode)

### ❌ Component Coverage

**Status:** FAIL

**Message:** Missing components for 5 result type(s)

**Details:**

```json
{
  "missing_result_types": [
    "status:options-pipeline",
    "status:ibkr-mcp",
    "lookup:logs:ibkr-mcp",
    "lookup:config:ibkr-mcp",
    "brainstorm:options-pipeline"
  ],
  "found_components": {},
  "action_required": "File UI-regen beads to create components for missing result types. Each missing result_type needs a component with a match_score >= 0.7 in component_usage_patterns."
}
```

