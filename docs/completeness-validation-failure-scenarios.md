# Completeness Validation Failure Scenarios

**Document Version:** 1.0  
**Date:** 2026-08-07  
**Schema:** `schemas/core-deployment-schema-30day-completeness.json`

## Overview

This document catalogs all possible completeness validation failure scenarios in the current schema implementation. It identifies where each failure is detected in the code, maps current error messages to failure types, and specifies what each error message should convey for maximum clarity.

## Validation Architecture

The validation system uses a **4-stage pipeline** with early termination:

```
1. JSON Well-formedness → Early termination on failure
2. Required Fields       → Continue, collect errors
3. Data Types          → Continue, collect errors  
4. Completeness        → Continue, collect errors
```

**Key Implementation Files:**
- `src/validation/integration.py` - Main validation orchestrator
- `src/validation/completeness.py` - JSON and completeness validation
- `src/validation/deployment_data.py` - Schema-based validation
- `schemas/core-deployment-schema-30day-completeness.json` - Schema with error messages

---

# STAGE 1: JSON Well-Formedness Failures

## 1.1 Invalid JSON Syntax

**Detection Location:** `src/validation/integration.py:97-100`  
**Function:** `validate_all()` → file loading

**Current Error Message:**
```
"Invalid JSON in file {file_path}: {json.JSONDecodeError}"
```

**Failure Scenario:** JSON file contains syntax errors that prevent parsing.

**Examples:**
- Missing closing braces `}`
- Unclosed strings `"hello`
- Trailing commas `[1,2,3,]`
- Invalid escape sequences `\x`

**What the Error Should Convey:**
- File that failed to parse
- Line number and column where error occurred
- Specific syntax issue (if available from parser)
- Actionable guidance (fix syntax, use JSON linter)

**Current Message Quality:** ⚠️ **ADEQUATE** - Includes file path and parser error, but could be more specific about line/column.

---

## 1.2 Non-Serializable Data Types

**Detection Location:** `src/validation/completeness.py:24-56`  
**Function:** `validate_json_wellformedness()`

**Current Error Message:**
```
"Data is not well-formed JSON: {str(e)}"
```

**Failure Scenario:** Python object contains types that cannot be serialized to JSON.

**Examples:**
- `datetime` objects in data
- `set` objects (should be `list`)
- Complex objects without `__dict__`
- `None` values in unexpected places

**What the Error Should Convey:**
- Which field/path contains non-serializable data
- The actual type found vs expected type
- How to convert to JSON-serializable type

**Current Message Quality:** ❌ **UNCLEAR** - Generic error message doesn't identify the problematic field or type.

---

## 1.3 File Not Found

**Detection Location:** `src/validation/integration.py:97-98`  
**Function:** `validate_all()` → file loading

**Current Error Message:**
```
"File not found: {file_path}"
```

**Failure Scenario:** Validation attempts to load a non-existent file.

**What the Error Should Convey:**
- Exact file path that was not found
- Current working directory (for relative paths)
- Suggested alternative paths or check commands

**Current Message Quality:** ✅ **CLEAR** - Direct and actionable.

---

# STAGE 2: Required Field Failures

## 2.1 Missing Top-Level Required Fields

**Detection Location:** `src/validation/deployment_data.py` → schema validation  
**Schema Path:** `schemas/core-deployment-schema-30day-completeness.json:7-13`

**Required Top-Level Fields:**
```json
{
  "required": [
    "metadata",
    "deployment_info", 
    "current_status",
    "metrics",
    "completeness"
  ]
}
```

**Current Error Message:** (From schema errorMessage property)
```
"Completeness validation section is required but missing. Add a 'completeness' object with period_coverage_days, data_coverage_percent, gaps_detected, and meets_completeness_threshold fields."
```

**Failure Scenarios:**
- Missing `completeness` section entirely
- Missing `metadata` section
- Missing `deployment_info` section
- Missing `current_status` section
- Missing `metrics` section

**What the Error Should Convey:**
- Which specific required field(s) are missing
- Why the field is required (business reason)
- Minimal example structure for the missing field
- Where in the schema to find requirements

**Current Message Quality:** ⚠️ **PARTIAL** - Good for `completeness` section, but generic for other missing fields.

---

## 2.2 Missing Nested Required Fields

**Detection Location:** Schema validation at multiple nested levels  
**Example Schema Paths:**
- `metadata.required` (lines 18-25)
- `deployment_info.required` (lines 77-82)
- `current_status.required` (lines 117-123)
- `completeness.required` (lines 279-288)

**Failure Scenarios:**

### Metadata Required Fields:
```json
{
  "metadata": {
    "required": ["generated_at", "data_period_start", "data_period_end", "service_name", "namespace", "cluster"]
  }
}
```

### Deployment Info Required Fields:
```json
{
  "deployment_info": {
    "required": ["deployment_name", "created_at", "current_image", "current_replicas"]
  }
}
```

### Current Status Required Fields:
```json
{
  "current_status": {
    "required": ["sync_status", "health_status", "ready_replicas", "available_replicas", "updated_replicas"]
  }
}
```

### Completeness Required Fields:
```json
{
  "completeness": {
    "required": [
      "period_coverage_days",
      "data_coverage_percent", 
      "gaps_detected",
      "gap_details",
      "meets_completeness_threshold",
      "minimum_deployment_days",
      "actual_deployment_days",
      "deployment_days_threshold_met"
    ]
  }
}
```

**Current Error Messages:** Schema-level validation errors

**What the Error Should Convey:**
- Exact path to missing field (e.g., `metadata.generated_at`)
- Expected data type for the field
- Whether field has a default value
- Example value for the field

**Current Message Quality:** ❌ **UNCLEAR** - Schema validation errors are often generic.

---

# STAGE 3: Data Type Failures

## 3.1 Type Mismatches

**Detection Location:** Schema validation throughout  
**Schema Example:** Line 28-31 for `generated_at`

**Current Error Message Pattern:**
```
"Field '{field_name}' must be {expected_type}, got {actual_type}"
```

**Failure Scenarios:**

### String vs Integer:
```json
// WRONG
{
  "service": 123,  // Should be string
  "period_days": "30"  // Should be integer
}

// CORRECT
{
  "service": "pbx-web",
  "period_days": 30
}
```

### Number vs String:
```json
// WRONG
{
  "deployment_success_rate": "95%"  // Should be number 0.95
}

// CORRECT
{
  "deployment_success_rate": 0.95
}
```

### Array vs Object:
```json
// WRONG
{
  "deployment_names": "pbx-web"  // Should be array
}

// CORRECT
{
  "deployment_names": ["pbx-web"]
}
```

**What the Error Should Convey:**
- Exact field path with type mismatch
- Expected type with allowed values/range
- Actual type found
- Example of correct value

**Current Message Quality:** ⚠️ **ADEQUATE** - Covers basics but could include examples.

---

## 3.2 Enum Value Failures

**Detection Location:** Schema enum constraints  
**Example:** Lines 125-135 for `sync_status` and `health_status`

**Current Error Message:**
```json
{
  "enum": "INVALID SEVERITY LEVEL: Severity must be one of: 'critical', 'warning', or 'info'. CURRENT VALUE: '{actual}'. SEVERITY CLASSIFICATION: 'critical' = gap >7 days (prevents completeness validation), 'warning' = gap 3-7 days (partial coverage concern), 'info' = gap <3 days (minor gap, often acceptable). ACTION: Map gap_duration_days to correct severity: if gap_duration_days > 7 → 'critical', if 3 <= gap_duration_days <= 7 → 'warning', if gap_duration_days < 3 → 'info'."
}
```

**Failure Scenarios:**

### Sync Status Values (Line 127):
```json
"enum": ["Synced", "OutOfSync", "Unknown"]
```

### Health Status Values (Line 133):
```json
"enum": ["Healthy", "Progressing", "Degraded", "Missing", "Unknown"]
```

### Gap Severity Values (Line 358):
```json
"enum": ["critical", "warning", "info"]
```

**What the Error Should Convey:**
- Invalid value provided
- List of allowed values
- Business meaning of each allowed value
- How to map data to correct value

**Current Message Quality:** ✅ **EXCELLENT** - Detailed severity enum message includes classification logic and mapping guidance.

---

## 3.3 Pattern Validation Failures

**Detection Location:** Schema pattern constraints  
**Example:** Lines 47-49 for `image_tag` pattern

**Current Error Message:**
```json
{
  "pattern": "^[a-z0-9-]+/[a-z0-9-]+:[\\w.+]+$"
}
```

**Failure Scenarios:**

### Image Tag Pattern (Line 98):
```json
// Expected format: registry/image:tag
"ronaldraygun/whisper-stt:1.8.6"

// Invalid examples:
"whisper-stt:1.8.6"           // Missing registry
"ronaldraygun/whisper-stt"    // Missing tag
"ronaldraygun/whisper-stt:1"  // Tag too simple (acceptable but not recommended)
```

### Coverage Percentage Pattern (Line 302):
```json
// Expected format: "XX%" with % symbol
"95%", "100%", "87%"

// Invalid examples:
95,     // Missing % symbol
"95",   // Missing % symbol  
"95.5%" // Decimal not allowed (should be integer)
```

### Resource Pattern (Lines 487, 493):
```json
// CPU patterns: '1', '100m'
// Memory patterns: '4Gi', '512Mi'
```

**What the Error Should Convey:**
- Expected pattern format with examples
- Actual value that failed validation
- Common mistakes and how to fix them
- Regular expression pattern (for technical users)

**Current Message Quality:** ⚠️ **VARIABLE** - Coverage percentage has excellent errorMessage (lines 304-307), but others rely on generic pattern errors.

---

## 3.4 Range Constraint Failures

**Detection Location:** Schema minimum/maximum constraints  
**Example:** Lines 103-105 for `current_replicas`

**Current Error Message Pattern:**
```json
{
  "minimum": "Period coverage is only {actual} days. Required minimum: 30 days for completeness validation. SHORTFALL: {30 - actual} days. ACTION: Extend the data collection period from '{data_period_start}' to '{data_period_end}' by at least {30 - actual} more days, or expand the analysis period to cover a full 30-day window."
}
```

**Failure Scenarios:**

### Period Coverage Days (Line 292):
```json
{
  "type": "integer",
  "minimum": 30
}
// Error when: period_coverage_days < 30
```

### Gap Duration Days (Line 349):
```json
{
  "type": "integer", 
  "minimum": 1
}
// Error when: gap_duration_days < 1 (shouldn't record 0-day gaps)
```

### Replicas Counts (Lines 138, 142, 147):
```json
{
  "type": "integer",
  "minimum": 0
}
// Error when: ready_replicas < 0 (should never be negative)
```

**What the Error Should Convey:**
- Actual value vs minimum/maximum allowed
- How far outside the valid range
- Business reason for constraint
- How to adjust data to meet requirement

**Current Message Quality:** ✅ **EXCELLENT** for period_coverage_days (lines 294-296) - detailed shortfall calculation and actionable guidance.

---

# STAGE 4: Completeness Validation Failures

## 4.1 Insufficient Period Coverage

**Detection Location:** `src/validation/completeness.py:284-286`  
**Function:** `validate_30day_completeness()`

**Current Error Message:**
```
"Date range covers {expected_count} days, expected ~30 days (from {start_date.date()} to {end_date.date()})"
```

**Failure Scenario:** Analysis period is less than 29 or more than 31 days (when `require_exact_30_days=True`).

**Examples:**
- Period covers only 15 days
- Period covers 45 days (too long)
- Start date or end date missing/invalid

**What the Error Should Convey:**
- Actual day count found
- Expected day count (~30)
- Exact date range analyzed
- Whether range is too short or too long
- How to adjust date range

**Current Message Quality:** ✅ **CLEAR** - Includes actual vs expected count and date range.

---

## 4.2 Missing Data Days (Gaps)

**Detection Location:** `src/validation/completeness.py:294-298`  
**Function:** `validate_30day_completeness()`

**Current Error Message:**
```
"Missing data for {len(missing_sorted)} day(s): {', '.join([d.strftime('%Y-%m-%d') for d in missing_sorted[:5]])}{'...' if len(missing_sorted) > 5 else ''}"
```

**Failure Scenario:** Expected dates are not present in deployment data.

**Examples:**
- No deployment data for weekends
- Missing data for 2026-07-15 through 2026-07-22
- Scattered missing days throughout period

**What the Error Should Convey:**
- Total count of missing days
- List of first 5 missing dates (truncated with ...)
- Whether gaps are consecutive or scattered
- Impact on completeness percentage
- How critical the gaps are (shortfall vs threshold)

**Current Message Quality:** ⚠️ **ADEQUATE** - Lists missing dates but doesn't convey severity or impact.

---

## 4.3 Extra Data Days (Duplicates/Out of Range)

**Detection Location:** `src/validation/completeness.py:300-304`  
**Function:** `validate_30day_completeness()`

**Current Error Message:**
```
"Found {len(extra_sorted)} date(s) outside expected range: {', '.join([d.strftime('%Y-%m-%d') for d in extra_sorted[:5]])}{'...' if len(extra_sorted) > 5 else ''}"
```

**Failure Scenario:** Data contains dates outside the expected analysis period.

**Examples:**
- Data from 2026-06-30 (before period start)
- Data from 2026-08-06 (after period end)
- Duplicate dates within period

**What the Error Should Convey:**
- Count of extra dates
- List of problematic dates
- Whether dates are before start, after end, or duplicates
- Guidance on filtering or adjusting date range

**Current Message Quality:** ✅ **CLEAR** - Lists problematic dates and truncates long lists.

---

## 4.4 Non-Chronological Date Sequence

**Detection Location:** `src/validation/completeness.py:306-317`  
**Function:** `validate_30day_completeness()`

**Current Error Message:**
```
"Non-chronological dates: {prev_date.strftime('%Y-%m-%d')} → {curr_date.strftime('%Y-%m-%d')} (gap of {actual_diff} days)"
```

**Failure Scenario:** Dates are not in consecutive daily order.

**Examples:**
- Dates: 2026-07-01, 2026-07-02, 2026-07-05 (gap from 2nd to 5th)
- Dates out of order: 2026-07-05, 2026-07-03, 2026-07-04
- Duplicate dates: 2026-07-01, 2026-07-01, 2026-07-02

**What the Error Should Convey:**
- Which specific dates are out of order
- Size of the gap detected
- Expected vs actual day difference
- Whether this indicates missing data or sorting issue

**Current Message Quality:** ✅ **CLEAR** - Shows exact date pair with gap size.

---

## 4.5 Completeness Threshold Not Met

**Detection Location:** Schema custom errorMessage (lines 376-382)  
**Schema Path:** `completeness.meets_completeness_threshold`

**Current Error Message:**
```json
{
  "custom": "COMPLETENESS THRESHOLD NOT MET: Deployment data fails minimum coverage requirements. COVERAGE: {data_coverage_percent} actual vs {completeness_threshold_percent} required. SHORTFALL: Calculate missing percentage gap. ROOT CAUSES: 1) Data gaps in replica_history (see gap_details), 2) Insufficient period length (<30 days), 3) Missing deployment events. ACTIONS: 1) Extend data collection period to cover full 30-day window, 2) Fill missing deployment data from gap_details periods, 3) Verify replica_history has no gaps >7 days, 4) Consider adjusting completeness_threshold_percent if current threshold is too strict for this use case."
}
```

**Failure Scenario:** `meets_completeness_threshold` is `false` (coverage below required percentage).

**Examples:**
- 85% coverage when threshold is 95%
- 60% coverage when threshold is 95%
- 0% coverage (no deployment data)

**What the Error Should Convey:**
- Actual coverage percentage
- Required threshold percentage  
- Shortfall percentage
- Root causes of insufficient coverage
- Specific actions to meet threshold
- Link to gap_details for specifics

**Current Message Quality:** ✅ **EXCELLENT** - Comprehensive with coverage comparison, root causes, and actionable next steps.

---

## 4.6 Gaps Detected Flag Set

**Detection Location:** Schema custom errorMessage (lines 313-316)  
**Schema Path:** `completeness.gaps_detected`

**Current Error Message:**
```json
{
  "custom": "GAPS DETECTED: Data gaps found in deployment coverage. SEVERITY: See gap_details array. CRITICAL GAPS: >7 days prevent completeness validation. WARNING GAPS: 3-7 days indicate partial coverage. ACTION: Review gap_details array for specific missing periods (gap_start_days_ago, gap_end_days_ago, gap_duration_days). Fill missing deployment data or extend data collection period."
}
```

**Failure Scenario:** `gaps_detected` is `true` (any gaps present in data).

**Examples:**
- 3-day gap in deployment data
- 10-day gap (critical)
- Multiple scattered gaps

**What the Error Should Convey:**
- Severity classification (critical/warning/info)
- Gap duration thresholds
- How to interpret gap_details
- Action based on gap severity

**Current Message Quality:** ✅ **EXCELLENT** - Clear severity classification and links to gap_details.

---

# GAP-SPECIFIC VALIDATION FAILURES

## 5.1 Invalid Gap Timing Values

**Detection Location:** Schema minimum constraints (lines 333, 343)  
**Schema Paths:** `gap_details[].gap_start_days_ago`, `gap_end_days_ago`

**Current Error Message:**
```json
{
  "minimum": "INVALID GAP TIMING: gap_start_days_ago cannot be negative. CURRENT VALUE: '{actual}' days ago. REQUIRED: 0 or more days ago (relative to data_period_end). INTERPRETATION: Negative values indicate gap starts in the future, which is impossible. ACTION: Check gap calculation logic - ensure gap_start_days_ago = (data_period_end - gap_start_date).days is always non-negative."
}
```

**Failure Scenario:** Gap timing values are negative (mathematically impossible).

**Examples:**
- `gap_start_days_ago: -5` (gap starts 5 days in the future?)
- `gap_end_days_ago: -2` (gap ends 2 days in the future?)

**What the Error Should Convey:**
- Why negative values are impossible
- Correct calculation formula
- How to debug gap calculation logic
- Expected range (0 to analysis_period_days)

**Current Message Quality:** ✅ **EXCELLENT** - Explains impossibility and provides correct calculation formula.

---

## 5.2 Invalid Gap Duration

**Detection Location:** Schema minimum constraint (line 352)  
**Schema Path:** `gap_details[].gap_duration_days`

**Current Error Message:**
```json
{
  "minimum": "INVALID GAP DURATION: gap_duration_days must be at least 1 day. CURRENT VALUE: '{actual}' days. REQUIRED: Minimum 1 day (gaps of 0 days should not be recorded as gaps). INTERPRETATION: 0-day gaps indicate no actual missing data. ACTION: Either remove this gap entry from gap_details (if no actual gap exists) or verify gap calculation: gap_duration_days = (gap_end_date - gap_start_date).days must be >= 1."
}
```

**Failure Scenario:** Gap duration is less than 1 day (shouldn't be recorded).

**Examples:**
- `gap_duration_days: 0` (no actual gap)
- `gap_duration_days: -1` (calculation error)

**What the Error Should Convey:**
- Why 0-day gaps shouldn't exist
- Correct calculation formula
- Whether to remove entry or fix calculation
- Distinction between calculation error and no gap

**Current Message Quality:** ✅ **EXCELLENT** - Clear guidance on removal vs correction.

---

## 5.3 Invalid Severity Classification

**Detection Location:** Schema enum constraint (line 360)  
**Schema Path:** `gap_details[].severity`

**Current Error Message:**
```json
{
  "enum": "INVALID SEVERITY LEVEL: Severity must be one of: 'critical', 'warning', or 'info'. CURRENT VALUE: '{actual}'. SEVERITY CLASSIFICATION: 'critical' = gap >7 days (prevents completeness validation), 'warning' = gap 3-7 days (partial coverage concern), 'info' = gap <3 days (minor gap, often acceptable). ACTION: Map gap_duration_days to correct severity: if gap_duration_days > 7 → 'critical', if 3 <= gap_duration_days <= 7 → 'warning', if gap_duration_days < 3 → 'info'."
}
```

**Failure Scenario:** Severity value is not one of the allowed enum values.

**Examples:**
- `severity: "high"` (should be "critical")
- `severity: "medium"` (should be "warning")  
- `severity: "low"` (should be "info")
- `severity: "error"` (not a valid severity)

**What the Error Should Convey:**
- List of valid severity values
- Duration thresholds for each severity
- Business impact of each level
- Mapping logic from duration to severity

**Current Message Quality:** ✅ **EXCELLENT** - Complete classification table and mapping logic.

---

## 5.4 Missing Gap Details When Threshold Not Met

**Detection Location:** Schema conditional validation (lines 679-707)  
**Validation Rule:** `if meets_completeness_threshold is false, then gap_details must have minItems: 1`

**Current Error Message:**
```json
{
  "description": "When completeness threshold is not met, gap_details must contain at least one entry explaining the failure"
}
```

**Failure Scenario:** `meets_completeness_threshold: false` but `gap_details: []` (empty array).

**What the Error Should Convey:**
- Why gap_details is required when threshold not met
- What gap_details should contain
- Minimum required fields for each gap entry
- Example gap entry structure

**Current Message Quality:** ⚠️ **ADEQUATE** - Explains requirement but lacks example structure.

---

## 5.5 Deployment Days Threshold Not Met

**Detection Location:** Schema custom errorMessage (lines 418-421)  
**Schema Path:** `completeness.deployment_days_threshold_met`

**Current Error Message:**
```json
{
  "custom": "DEPLOYMENT DAYS THRESHOLD NOT MET: Insufficient deployment activity in analysis period. ACTUAL DEPLOYMENT DAYS: {actual_deployment_days} distinct days with deployments vs REQUIRED MINIMUM: {minimum_deployment_days} days. SHORTFALL: {minimum_deployment_days - actual_deployment_days} deployment days missing. ROOT CAUSES: 1) New deployment with limited history, 2) Deployment paused during analysis period, 3) Insufficient replica_history coverage. ACTIONS: 1) Verify replica_history captures all deployment events, 2) Check deployment occurred on distinct days (not same day multiple times), 3) Extend analysis period to capture more deployment activity, 4) Adjust minimum_deployment_days if deployment frequency is lower than expected for this service."
}
```

**Failure Scenario:** `deployment_days_threshold_met: false` (not enough distinct deployment days).

**Examples:**
- Only 2 deployment days when minimum is 5
- 0 deployment days (service never deployed)
- All deployments on same day (counts as 1 day)

**What the Error Should Convey:**
- Actual deployment day count
- Required minimum
- Shortfall in days
- Root causes (new service, paused deployments, etc.)
- Actions to meet threshold

**Current Message Quality:** ✅ **EXCELLENT** - Detailed comparison, root causes, and multiple corrective actions.

---

# ERROR MESSAGE QUALITY SUMMARY

## Excellent (✅): Comprehensive, Actionable, Context-Rich
- **Period coverage shortfall** (lines 294-296): Detailed shortfall calculation and guidance
- **Completeness threshold not met** (lines 376-382): Coverage comparison, root causes, actions
- **Gaps detected flag** (lines 313-316): Severity classification, links to details
- **Gap timing errors** (lines 333-334, 343-344): Impossibility explanation, formula
- **Gap duration errors** (lines 352-354): Removal vs correction guidance
- **Severity classification** (lines 360-362): Complete mapping logic
- **Deployment days threshold** (lines 418-421): Root causes, multiple actions

## Adequate (⚠️): Covers Basics, Could Include Examples
- **Invalid JSON syntax** (lines 99-100): Includes file path and parser error
- **Missing data days** (lines 294-298): Lists missing dates but lacks severity
- **Extra data days** (lines 300-304): Lists problematic dates
- **Non-chronological sequence** (lines 306-317): Shows date pairs with gaps
- **Missing top-level fields** (line 276-278): Good for completeness, generic otherwise
- **Type mismatches**: Basic type information without examples
- **Pattern validation**: Variable quality (excellent for coverage percentage)

## Unclear (❌): Generic, Lacks Specifics or Guidance
- **Non-serializable types** (lines 53-54): Doesn't identify problematic field
- **Missing nested fields**: Generic schema validation errors
- **Gap details when threshold not met** (line 699): Lacks example structure

---

# RECOMMENDATIONS FOR IMPROVEMENT

## 1. Standardize Error Message Format
All error messages should follow this structure:
```
[FAILURE_TYPE]: [SPECIFIC_ISSUE]. 
CURRENT VALUE: [actual_value]. 
EXPECTED: [expected_value/range]. 
IMPACT: [business_consequence]. 
ACTION: [steps_to_fix].
```

## 2. Include Examples in Type Errors
For type mismatch errors, add examples:
```json
{
  "errorMessage": {
    "type": "Field 'service' must be string. Got: integer (123). EXAMPLE: Change to 'pbx-web'."
  }
}
```

## 3. Add Severity Indicators
Include severity level in all completeness errors:
```
"CRITICAL: Period coverage only 15 days vs required 30 days"
"WARNING: Missing 2 days of deployment data (6.7% gap)"
"INFO: Extra data date 2026-06-30 is before analysis period"
```

## 4. Provide Suggested Fixes
For recoverable errors, include fix suggestions:
```json
{
  "errorMessage": {
    "fix": "Remove entry or correct calculation: gap_duration_days = (gap_end_date - gap_start_date).days"
  }
}
```

## 5. Add Cross-References
Link related error messages:
```json
{
  "errorMessage": {
    "see_also": "completeness.meets_completeness_threshold for coverage requirements"
  }
}
```

---

# VALIDATION FLOW DIAGRAM

```
┌─────────────────────────────────────────────────────────────┐
│                    VALIDATION REQUEST                       │
│                (file_path or data object)                    │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│              STEP 1: JSON Well-Formedness                    │
│         validate_json_wellformedness(data)                  │
│  ┌────────────────────────────────────────────────────────┐ │
│  │ Check: Can serialize/deserialize to JSON               │ │
│  │ Failure: Data is not well-formed JSON: {error}        │ │
│  │ Action: Early termination (return False, [error])       │ │
│  └────────────────────────────────────────────────────────┘ │
└────────────────────┬────────────────────────────────────────┘
                     │ ✅ Pass
                     ▼
┌─────────────────────────────────────────────────────────────┐
│              STEP 2: Required Fields                        │
│           validate_required_fields(data)                     │
│  ┌────────────────────────────────────────────────────────┐ │
│  │ Check: All required fields present                     │ │
│  │ Failure: Required fields validation: {missing_fields}  │ │
│  │ Action: Collect error, continue validation             │ │
│  └────────────────────────────────────────────────────────┘ │
└────────────────────┬────────────────────────────────────────┘
                     │ ✅ Pass (or collect errors)
                     ▼
┌─────────────────────────────────────────────────────────────┐
│              STEP 3: Data Types                             │
│            validate_data_types(data, schema)                │
│  ┌────────────────────────────────────────────────────────┐ │
│  │ Check: All field types match schema                     │ │
│  │ Failure: Data types validation: {type_errors}         │ │
│  │ Action: Collect error, continue validation             │ │
│  └────────────────────────────────────────────────────────┘ │
└────────────────────┬────────────────────────────────────────┘
                     │ ✅ Pass (or collect errors)
                     ▼
┌─────────────────────────────────────────────────────────────┐
│              STEP 4: Completeness                            │
│         validate_completeness(deployment_events)              │
│  ┌────────────────────────────────────────────────────────┐ │
│  │ Check: 30-day coverage, no gaps, chronological          │ │
│  │ Failure: Completeness validation: {completeness_error} │ │
│  │ Action: Collect error, continue validation             │ │
│  └────────────────────────────────────────────────────────┘ │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│                   RETURN RESULTS                             │
│              (is_valid, collected_errors)                    │
│        is_valid = (len(errors) == 0)                         │
└─────────────────────────────────────────────────────────────┘
```

---

# APPENDIX: Quick Reference

## Critical Failure Types (Prevent Validation)
1. **Invalid JSON syntax** - Cannot parse data
2. **Non-serializable types** - Cannot process data
3. **File not found** - Cannot access data

## Warning Failure Types (Collect but Continue)
1. **Missing required fields** - Incomplete data structure
2. **Type mismatches** - Schema violations
3. **Enum violations** - Invalid categorical values
4. **Pattern failures** - Format violations
5. **Range violations** - Value constraints

## Completeness Failure Types (Business Logic)
1. **Insufficient period coverage** - <30 days analysis window
2. **Missing data days** - Gaps in coverage
3. **Extra data days** - Duplicates or out-of-range dates
4. **Non-chronological sequence** - Ordering issues
5. **Threshold not met** - Below required coverage percentage
6. **Gaps detected** - Any gaps present

## Error Message Priority
1. **CRITICAL**: Data unusable, must fix before validation
2. **HIGH**: Schema violation, prevents completeness check
3. **MEDIUM**: Business logic violation, data incomplete
4. **LOW**: Format/validation issue, may not impact analysis

---

**Document Status:** Complete  
**Last Updated:** 2026-08-07  
**Maintainer:** aide-de-camp validation team  
**Related Documents:**
- `schemas/core-deployment-schema-30day-completeness.json`
- `src/validation/integration.py`
- `docs/validation-rules-30day-deployment-completeness.md`