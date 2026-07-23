# Demo Seeding Verification Report

**Generated:** 2026-07-23T16:04:32.094219

## Summary

- **Overall Status:** FAIL
- **Total Checks:** 4
  - Passed: 1
  - Failed: 1
  - Warnings: 0
  - Skipped: 2

## Check Details

### ✅ Registry Verification

**Status:** PASS

**Message:** All registry entries verified

**Details:**

```json
{
  "projects": [
    "whisper-stt",
    "pbx-web"
  ]
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
    "status:whisper-stt",
    "status:pbx-web",
    "lookup:logs:whisper-stt",
    "lookup:config:whisper-stt",
    "brainstorm:pbx-web"
  ],
  "found_components": {},
  "action_required": "File UI-regen beads to create components for missing result types. Each missing result_type needs a component with a match_score >= 0.7 in component_usage_patterns."
}
```

