# Demo Seeding Verification Report

**Generated:** 2026-07-23T16:08:59.660738

## Summary

- **Overall Status:** FAIL
- **Total Checks:** 4
  - Passed: 2
  - Failed: 2
  - Warnings: 0
  - Skipped: 0

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

### ❌ Context Warmer

**Status:** FAIL

**Message:** Exception during check: 'SessionStore' object has no attribute 'get_topic'

**Details:**

```json
{
  "error": "'SessionStore' object has no attribute 'get_topic'"
}
```

### ✅ Dispatch Execution

**Status:** PASS

**Message:** All dispatches succeeded

**Details:**

```json
{
  "successful_dispatches": [
    "What's the status of whisper stt?...",
    "How's the pbx web doing?...",
    "Pull up the recent logs for whisper stt....",
    "Find the whisper stt deployment config....",
    "Should the pbx web use redundant ingress controlle..."
  ]
}
```

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

