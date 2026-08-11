# Gap Detection Integration Test Scenarios

## Overview

This document outlines comprehensive test scenarios for gap detection integration in the aide-de-camp validation pipeline. These scenarios ensure that gap detection works correctly across the entire validation flow, from input data to final output structure.

## Architecture Summary

**Validation Pipeline Flow:**
```
validate_deployment_file()
  → _validate_json_wellformedness()
  → _validate_required_fields()
  → _validate_data_types()
  → _validate_completeness_with_gap_metrics()
    → validate_30day_completeness()
    → validate_gaps_with_guidance()
      → _extract_deployment_dates()
      → _calculate_gaps_from_dates()
      → calculate_gap_periods()
      → _assess_gap_severity()
      → _generate_actionable_guidance()
      → detect_anomalies()
      → _calculate_deployment_intervals()
    → Merge GapValidationResult into ValidationResult
  → Return ValidationResult.to_dict()
```

**Key Data Structures:**
- `ValidationResult`: Comprehensive result with gap metrics
- `GapValidationResult`: Detailed gap analysis from integration layer
- `GapPeriod`: Individual gap with classification
- `GapSeverity`: Severity levels (none, low, medium, high, critical)

---

## Category 1: Normal Gap Detection Flow Invocation

### Scenario 1.1: Complete Coverage (No Gaps)
**Description:** Deployment data with perfect 30-day coverage passes all validations.

**Test Data Requirements:**
- 30 consecutive deployment events (days 1-30)
- Valid metadata.time_period.start and .end
- All required fields present and valid types

**Expected Results:**
- `is_valid: true`
- `gap_detected: false`
- `coverage_percentage: 100.0`
- `gap_count: 0`
- `gap_severity: "none"`
- `gap_periods: []`
- Empty error messages list

**Test Cases:**
- [ ] Test with deployment_events_last_30_days containing all 30 days
- [ ] Test with replica_history containing all 30 days
- [ ] Test with mixed data sources (deployment_events + replica_history)
- [ ] Test leap year date ranges (Feb 29)
- [ ] Test month boundaries (cross-month 30-day periods)

---

### Scenario 1.2: Single Isolated Gap
**Description:** Deployment data with a single isolated gap day.

**Test Data Requirements:**
- 29 deployment events (missing day 15)
- Valid metadata structure
- Gap duration: 1 day

**Expected Results:**
- `is_valid: false` (if coverage < 95%)
- `gap_detected: true`
- `coverage_percentage: 96.67` (29/30)
- `gap_count: 1`
- `gap_severity: "low"` (1 day = tiny gap)
- `isolated_gap_count: 1`
- `consecutive_gap_sequence_count: 0`
- `gap_size_distribution: {tiny: 1, small: 0, medium: 0, large: 0, extended: 0}`
- `gap_periods: ["2026-07-15 to 2026-07-15"]`
- Actionable guidance includes filling the isolated gap

**Test Cases:**
- [ ] Test gap at beginning of period (day 1 missing)
- [ ] Test gap in middle of period (day 15 missing)
- [ ] Test gap at end of period (day 30 missing)
- [ ] Verify isolated gap classification (is_consecutive: false)

---

### Scenario 1.3: Consecutive Gap Sequence
**Description:** Deployment data with a consecutive gap sequence (multiple missing days in a row).

**Test Data Requirements:**
- 24 deployment events (missing days 10-15, 6 consecutive days)
- Valid metadata structure
- Gap duration: 6 days

**Expected Results:**
- `is_valid: false` (coverage < 95%)
- `gap_detected: true`
- `coverage_percentage: 80.0` (24/30)
- `gap_count: 6` (individual gap days)
- `gap_severity: "high"` (6 days = large gap)
- `isolated_gap_count: 0`
- `consecutive_gap_sequence_count: 1` (one sequence)
- `gap_size_distribution: {tiny: 0, small: 0, medium: 0, large: 1, extended: 0}`
- `gap_periods: ["2026-07-10 to 2026-07-15"]` (consolidated)
- All 6 gaps marked as `is_consecutive: true` with same `sequence_id`
- Actionable guidance mentions "consecutive gap sequence"

**Test Cases:**
- [ ] Test 2-day consecutive gap (small)
- [ ] Test 5-day consecutive gap (medium)
- [ ] Test 8-day consecutive gap (large)
- [ ] Test 15-day consecutive gap (extended)
- [ ] Verify sequence consolidation in gap_periods
- [ ] Verify all gaps in sequence share same sequence_id

---

### Scenario 1.4: Multiple Gap Periods
**Description:** Deployment data with multiple isolated and consecutive gap sequences.

**Test Data Requirements:**
- 20 deployment events (missing: days 5, 10-12, 18-20, 25)
- Mix of isolated (1 day) and consecutive (2-3 days) gaps
- Valid metadata structure

**Expected Results:**
- `is_valid: false` (coverage < 95%)
- `gap_detected: true`
- `coverage_percentage: 66.67` (20/30)
- `gap_count: 9` (total missing days)
- `gap_severity: "critical"` (coverage < 80%)
- `isolated_gap_count: 2` (days 5, 25)
- `consecutive_gap_sequence_count: 2` (10-12, 18-20)
- `gap_size_distribution: {tiny: 2, small: 1, medium: 1, large: 0, extended: 0}`
- `gap_periods: ["2026-07-05 to 2026-07-05", "2026-07-10 to 2026-07-12", "2026-07-18 to 2026-07-20", "2026-07-25 to 2026-07-25"]`
- Actionable guidance mentions both isolated and consecutive gaps

**Test Cases:**
- [ ] Test 2 isolated gaps + 1 consecutive sequence
- [ ] Test 3 consecutive sequences of varying sizes
- [ ] Test isolated gaps at period boundaries
- [ ] Verify gap_periods consolidation preserves all sequences

---

### Scenario 1.5: Edge Coverage Thresholds
**Description:** Test coverage at exact threshold boundaries.

**Test Data Requirements:**
- Variable deployment events for specific coverage percentages
- Test at 95%, 90%, 80%, 100% coverage

**Expected Results:**

| Coverage | Expected Days | Gap Count | Valid (95% threshold) | Severity |
|----------|---------------|-----------|------------------------|----------|
| 100%     | 30            | 0         | true                   | none     |
| 95%      | 28.5 → 28     | 2         | true                   | low      |
| 94%      | 28.2 → 28     | 2         | false                  | medium   |
| 90%      | 27            | 3         | false                  | high     |
| 80%      | 24            | 6         | false                  | critical |
| 79%      | 23.7 → 23     | 7         | false                  | critical |

**Test Cases:**
- [ ] Test exactly 95% coverage (28.5 days → 28 days, 2 gaps)
- [ ] Test just below 95% (94% coverage, 28 days, 2 gaps)
- [ ] Test exactly 90% coverage (27 days, 3 gaps)
- [ ] Test exactly 80% coverage (24 days, 6 gaps)
- [ ] Test just below 80% (79% coverage, 23 days, 7 gaps)
- [ ] Verify severity changes at thresholds

---

## Category 2: Result Merging with Existing Validation Results

### Scenario 2.1: Gap Metrics Preserved After Schema Validation Failures
**Description:** Gap metrics should be preserved even when schema validation fails.

**Test Data Requirements:**
- Invalid schema field (e.g., missing required field)
- Gap in deployment data
- Valid date range

**Expected Results:**
- `is_valid: false` (schema failure)
- `is_wellformed_json: true`
- `has_required_fields: false`
- `has_valid_types: true` (or false depending on type error)
- `has_complete_coverage: false` (gap detected)
- Gap metrics populated:
  - `gap_detected: true`
  - `coverage_percentage: < 100`
  - `gap_count: > 0`
  - `gap_periods: [...]`
- Error messages list includes both schema and gap errors

**Test Cases:**
- [ ] Test missing required field + gaps
- [ ] Test invalid data type + gaps
- [ ] Test both required field AND type errors + gaps
- [ ] Verify gap metrics populate despite schema failures
- [ ] Verify errors list includes both schema and gap errors

---

### Scenario 2.2: Legacy Tuple Format Backward Compatibility
**Description:** Ensure legacy `(is_valid, errors)` tuple format still works.

**Test Data Requirements:**
- Deployment data with gaps
- Call `validate_deployment_file(file_path, return_type="legacy")`

**Expected Results:**
- Returns tuple `(bool, List[str])`
- First element: `is_valid` (False if gaps)
- Second element: list of error messages
- Error messages include gap information

**Test Cases:**
- [ ] Test legacy format with gaps
- [ ] Test legacy format with no gaps
- [ ] Test legacy format with schema + gap errors
- [ ] Verify tuple structure matches expectations

---

### Scenario 2.3: ValidationResult.to_dict() Output Structure
**Description:** Verify ValidationResult.to_dict() includes all gap metrics.

**Test Data Requirements:**
- ValidationResult with populated gap metrics

**Expected Results:**
```python
{
    "is_valid": bool,
    "file_path": str,
    "is_wellformed_json": bool,
    "has_required_fields": bool,
    "has_valid_types": bool,
    "has_complete_coverage": bool,
    "errors": List[str],
    "gap_detected": bool,
    "coverage_percentage": float,
    "expected_days": int,
    "actual_days": int,
    "gap_count": int,
    "gap_severity": str,  # "none", "low", "medium", "high", "critical"
    "isolated_gap_count": int,
    "consecutive_gap_sequence_count": int,
    "gap_size_distribution": {
        "tiny": int,      # 1 day gaps
        "small": int,     # 2-3 day gaps
        "medium": int,    # 4-7 day gaps
        "large": int,     # 8-14 day gaps
        "extended": int   # >14 day gaps
    },
    "gap_periods": List[str],  # ["2026-07-01 to 2026-07-03", ...]
    "actionable_guidance": List[str],
    "anomaly_messages": List[str],
    "deployment_intervals": Dict[str, Any],
    "validated_at": str  # ISO 8601 timestamp
}
```

**Test Cases:**
- [ ] Verify all 24 keys present in output
- [ ] Verify data types match schema
- [ ] Test with complete coverage (gap metrics zero/default)
- [ ] Test with gaps (gap metrics populated)
- [ ] Verify validated_at is valid ISO 8601 timestamp
- [ ] Test serialization to JSON (no datetime objects)

---

### Scenario 2.4: Gap Severity Enum Handling
**Description:** Verify GapSeverity enum converts correctly to string.

**Test Data Requirements:**
- GapValidationResult with each severity level

**Expected Results:**
- `GapSeverity.NONE` → `"none"`
- `GapSeverity.LOW` → `"low"`
- `GapSeverity.MEDIUM` → `"medium"`
- `GapSeverity.HIGH` → `"high"`
- `GapSeverity.CRITICAL` → `"critical"`

**Edge Cases:**
- [ ] Test with enum value directly
- [ ] Test with string value (if passed as string)
- [ ] Test handling of invalid severity values
- [ ] Verify default to "unknown" on error

---

### Scenario 2.5: Safe Defaults on Gap Detection Failure
**Description:** When gap detection fails, schema validation results should be preserved.

**Test Data Requirements:**
- Valid deployment data structure
- Gap detection throws exception (simulate with invalid date format, missing fields)

**Expected Results:**
- `is_valid: false` (gap detection failed)
- Schema validation flags populated:
  - `is_wellformed_json: true`
  - `has_required_fields: true`
  - `has_valid_types: true`
- Gap metrics set to safe defaults:
  - `gap_detected: false` (or true based on implementation)
  - `coverage_percentage: 100.0` (or 0.0 if critical)
  - `expected_days: 30` (from data)
  - `actual_days: 30` (expected only)
  - `gap_count: 0`
  - `gap_severity: "none"` (or "critical" if failure = critical)
  - `gap_size_distribution: {tiny: 0, small: 0, medium: 0, large: 0, extended: 0}`
  - `gap_periods: []`
- Error messages include gap detection failure notice
- `actionable_guidance` includes "Gap detection was unavailable" message

**Test Cases:**
- [ ] Test with missing metadata.time_period
- [ ] Test with invalid date format in time_period
- [ ] Test with empty deployment_events_last_30_days
- [ ] Test gap calculator exception handling
- [ ] Verify safe defaults don't break validation pipeline

---

## Category 3: Gap Metrics in Final Output Structure

### Scenario 3.1: Coverage Percentage Calculation
**Description:** Verify coverage percentage is calculated correctly.

**Test Data Requirements:**
- Varying deployment event counts

**Expected Results:**
- Formula: `(actual_days / expected_days) * 100`
- Rounded to 2 decimal places
- Range: 0.0 to 100.0

**Test Cases:**
- [ ] Test 30/30 → 100.0%
- [ ] Test 28/30 → 93.33%
- [ ] Test 15/30 → 50.0%
- [ ] Test 0/30 → 0.0%
- [ ] Test rounding behavior (28.5/30 = 95.0%, not 95.00%)

---

### Scenario 3.2: Gap Size Distribution Classification
**Description:** Verify gaps are classified by size correctly.

**Test Data Requirements:**
- Gaps of various sizes: 1, 2, 3, 5, 7, 8, 10, 15 days

**Expected Classification:**
| Gap Duration | Classification |
|--------------|----------------|
| 1 day        | tiny           |
| 2 days       | small          |
| 3 days       | small          |
| 4-7 days     | medium         |
| 8-14 days    | large          |
| >14 days     | extended       |

**Test Cases:**
- [ ] Test single 1-day gap → {tiny: 1}
- [ ] Test 2-day gap → {small: 1}
- [ ] Test 3-day gap → {small: 1}
- [ ] Test 5-day gap → {medium: 1}
- [ ] Test 8-day gap → {large: 1}
- [ ] Test 15-day gap → {extended: 1}
- [ ] Test mixed gaps → correct distribution

---

### Scenario 3.3: Isolated vs Consecutive Gap Classification
**Description:** Verify isolated and consecutive gaps are counted separately.

**Test Data Requirements:**
- Mix of isolated and consecutive gaps

**Expected Results:**
- `isolated_gap_count`: Number of gaps NOT in a consecutive sequence
- `consecutive_gap_sequence_count`: Number of unique consecutive sequences
- A 3-day consecutive sequence counts as:
  - 3 individual gap days in `gap_count`
  - 0 isolated gaps
  - 1 consecutive sequence

**Test Cases:**
- [ ] Test all isolated gaps (5 separate days) → isolated: 5, consecutive: 0
- [ ] Test single consecutive sequence (3 days) → isolated: 0, consecutive: 1
- [ ] Test mix (2 isolated + 1 sequence of 3) → isolated: 2, consecutive: 1
- [ ] Test multiple sequences (2 sequences of 2 days each) → isolated: 0, consecutive: 2

---

### Scenario 3.4: Actionable Guidance Content
**Description:** Verify actionable guidance provides specific, useful information.

**Expected Guidance Elements:**
1. Coverage shortfall information
2. Gap-specific guidance (isolated vs consecutive)
3. Deployment interval reference (Days 1-30)
4. Data source verification steps
5. Service-specific guidance (if service_name known)

**Test Cases:**
- [ ] Verify guidance includes coverage percentage
- [ ] Verify guidance includes missing day count
- [ ] Verify guidance references "Days 1-30" deployment interval
- [ ] Verify guidance distinguishes isolated vs consecutive gaps
- [ ] Verify guidance includes data source checks
- [ ] Verify guidance includes service name if available

---

### Scenario 3.5: Anomaly Detection Messages
**Description:** Verify anomalies are detected for unusual gap patterns.

**Anomaly Types:**
1. Extended gaps (>14 days)
2. High gap intensity (>50% of days)
3. Consecutive gap dominance (>70% of gaps are consecutive)

**Test Cases:**
- [ ] Test 15-day gap → extended gap anomaly
- [ ] Test 20/30 days with gaps (67% intensity) → high intensity anomaly
- [ ] Test 10 gaps, 8 consecutive (80%) → consecutive dominance anomaly
- [ ] Verify anomaly messages include CRITICAL/HIGH severity indicators
- [ ] Verify anomaly messages include remediation steps

---

### Scenario 3.6: Deployment Intervals Calculation
**Description:** Verify deployment interval statistics are calculated.

**Expected Fields:**
```python
{
    "first_deployment": "2026-07-01",
    "last_deployment": "2026-07-30",
    "total_deployments": 30,
    "average_interval_days": 1.0,
    "longest_interval_days": 1,
    "shortest_interval_days": 1
}
```

**Test Cases:**
- [ ] Test daily deployments → average: 1.0, longest: 1
- [ ] Test every-other-day deployments → average: 2.0, longest: 2
- [ ] Test irregular intervals → correct average/max/min
- [ ] Test with gaps → intervals calculated from present deployments only

---

## Category 4: Error Scenarios

### Scenario 4.1: Gap Detection Timeout
**Description:** Handle timeout or hang in gap detection.

**Test Data Requirements:**
- Large dataset (simulated slow processing)
- or Simulate timeout with mock

**Expected Results:**
- Exception caught in `_validate_completeness_with_gap_metrics()`
- Safe default GapValidationResult returned
- Schema validation results preserved
- Error message indicates timeout/failure
- Validation completes without hanging

**Test Cases:**
- [ ] Simulate timeout in gap_calculator
- [ ] Verify safe default returned
- [ ] Verify error message includes timeout/failure indication
- [ ] Verify schema validation still completes

---

### Scenario 4.2: Invalid Date Formats
**Description:** Handle various invalid date format scenarios.

**Test Data Requirements:**
- Invalid ISO 8601 dates
- Missing timezone/offset
- Non-string date values
- Out-of-range dates

**Expected Results:**
- Invalid dates are skipped (not counted as deployment dates)
- Gaps are calculated from valid dates only
- No exceptions thrown
- Error logged (but validation continues)

**Test Cases:**
- [ ] Test date string without 'Z' (should still parse if ISO format)
- [ ] Test date with wrong format (e.g., "07/01/2026")
- [ ] Test date as integer/timestamp
- [ ] Test date as null/None
- [ ] Test future dates (beyond end_date)
- [ ] Test dates before start_date

---

### Scenario 4.3: Empty or Null Deployment Data
**Description:** Handle empty deployment data arrays.

**Test Data Requirements:**
- Empty `deployment_events_last_30_days: []`
- Empty `replica_history: []`
- Null/None deployment data

**Expected Results:**
- `gap_detected: true` (or false with 0% coverage)
- `coverage_percentage: 0.0` (if no dates)
- `gap_count: expected_days` (entire period is gap)
- `gap_severity: "critical"`
- `gap_periods: [start_date to end_date]` (entire period)
- Actionable guidance: "No deployment data found"

**Test Cases:**
- [ ] Test empty deployment_events_last_30_days
- [ ] Test empty replica_history
- [ ] Test both empty
- [ ] Verify gap covers entire period (30 days)
- [ ] Verify critical severity assigned

---

### Scenario 4.4: Missing Metadata Fields
**Description:** Handle missing or incomplete metadata.

**Test Data Requirements:**
- Missing `metadata.time_period.start`
- Missing `metadata.time_period.end`
- Missing entire `metadata` section
- Missing `metadata.time_period`

**Expected Results:**
- Cannot determine date range
- Gap validation fails gracefully
- Safe default GapValidationResult:
  - `is_valid: false`
  - `coverage_percentage: 0.0`
  - `error_message: "Cannot determine date range"`
  - `actionable_guidance: ["Add metadata.time_period.start and ..."]`

**Test Cases:**
- [ ] Test missing start date only
- [ ] Test missing end date only
- [ ] Test both start and end missing
- [ ] Test entire time_period missing
- [ ] Test entire metadata missing
- [ ] Verify helpful error messages

---

### Scenario 4.5: Malformed Gap Calculation Results
**Description:** Handle corrupted or invalid gap calculation results.

**Test Data Requirements:**
- Mock gap_calculator to return invalid data:
  - Negative gap durations
  - Null/None gap periods
  - Invalid date ranges (end before start)

**Expected Results:**
- Exception caught in `_validate_completeness_with_gap_metrics()`
- Safe default GapValidationResult returned
- Schema validation preserved
- No crashes or undefined behavior

**Test Cases:**
- [ ] Mock calculate_gap_periods() to raise exception
- [ ] Mock to return invalid gap period (end before start)
- [ ] Mock to return null gap_periods list
- [ ] Verify exception handling prevents crash
- [ ] Verify safe default returned

---

### Scenario 4.6: JSON Serialization Failures
**Description:** Handle failures in ValidationResult.to_dict().

**Test Data Requirements:**
- ValidationResult with non-serializable data:
  - datetime objects in gap_periods (should be strings)
  - Enum objects (should be strings)
  - Nested objects with circular references

**Expected Results:**
- to_dict() handles all serializable types
- datetime → ISO 8601 string
- enum → string value
- No JSON serialization errors

**Test Cases:**
- [ ] Test with datetime in deployment_intervals
- [ ] Test with GapSeverity enum
- [ ] Test JSON dumps of to_dict() output
- [ ] Verify no serialization errors

---

## Category 5: Integration Scenarios

### Scenario 5.1: End-to-End Validation with Gaps
**Description:** Full validation flow from file to output.

**Test Data Requirements:**
- Valid JSON file with gaps
- All required fields present
- Valid schema
- Gap in deployment_events_last_30_days

**Expected Results:**
1. JSON well-formedness: ✓
2. Required fields: ✓
3. Data types: ✓
4. Completeness: ✗ (gaps detected)
5. ValidationResult includes:
   - Schema validation flags all true
   - Gap metrics populated
   - Error messages include gap information
   - Actionable guidance provided

**Test Cases:**
- [ ] Create temp JSON file with gaps
- [ ] Run validate_deployment_file()
- [ ] Verify ValidationResult structure
- [ ] Verify all gap metrics present
- [ ] Clean up temp file

---

### Scenario 5.2: Multiple Validation Failures + Gaps
**Description:** Schema validation failures AND gaps.

**Test Data Requirements:**
- Invalid schema field (e.g., missing required field)
- Invalid data type (e.g., string instead of int)
- Gaps in deployment data

**Expected Results:**
- `is_valid: false`
- Multiple validation flags false:
  - `has_required_fields: false`
  - `has_valid_types: false`
  - `has_complete_coverage: false`
- Error messages list includes:
  - Required field error
  - Data type error
  - Gap error
- Gap metrics still populated

**Test Cases:**
- [ ] Test missing field + type error + gaps
- [ ] Verify all error types present
- [ ] Verify gap metrics still calculated
- [ ] Verify errors list order (schema before gaps)

---

### Scenario 5.3: Gap Detection with Custom Thresholds
**Description:** Test gap detection with non-default coverage thresholds.

**Test Data Requirements:**
- 90% coverage threshold (default 95%)
- Deployment data with 92% coverage

**Expected Results:**
- With 95% threshold: `is_valid: false` (92 < 95)
- With 90% threshold: `is_valid: true` (92 >= 90)
- Gap metrics same in both cases
- Only `is_valid` changes

**Test Cases:**
- [ ] Test with default 95% threshold
- [ ] Test with 90% threshold
- [ ] Test with 100% threshold (strict)
- [ ] Verify only validity changes, not metrics

---

### Scenario 5.4: Leap Year and Month Boundaries
**Description:** Test gap detection across date boundary edge cases.

**Test Data Requirements:**
- 30-day periods crossing month boundaries
- Leap year dates (Feb 29)
- 31-day months

**Expected Results:**
- Correct gap calculation regardless of month length
- Correct day counting across boundaries
- No off-by-one errors

**Test Cases:**
- [ ] Test Jan 15 - Feb 13 (30 days, crosses month)
- [ ] Test Feb 1 - Mar 1 (30 days, leap year)
- [ ] Test Feb 1 - Mar 2 (30 days, non-leap year)
- [ ] Test Jul 1 - Jul 30 (within single month)
- [ ] Verify day counts correct in all cases

---

### Scenario 5.5: Large Dataset Performance
**Description:** Test gap detection with large deployment datasets.

**Test Data Requirements:**
- 365+ deployment events (year-long period)
- Thousands of replica_history entries
- Multiple gaps

**Expected Results:**
- No performance degradation
- No timeouts
- Correct gap calculation
- Memory usage reasonable

**Test Cases:**
- [ ] Test with 365 deployment events
- [ ] Test with 1000 replica_history entries
- [ ] Measure execution time
- [ ] Verify memory usage
- [ ] Test with multiple large gaps

---

## Test Data Templates

### Template 1: Complete Coverage Data
```json
{
  "metadata": {
    "service_name": "test-service",
    "time_period": {
      "start": "2026-07-01T00:00:00Z",
      "end": "2026-07-30T23:59:59Z"
    }
  },
  "deployment_events_last_30_days": [
    {"date": "2026-07-01", "deployment_name": "test", "image": "test:1.0", "status": "successful"},
    ... (all 30 days)
  ]
}
```

### Template 2: Data with Single Gap
```json
{
  "metadata": {
    "service_name": "test-service",
    "time_period": {
      "start": "2026-07-01T00:00:00Z",
      "end": "2026-07-30T23:59:59Z"
    }
  },
  "deployment_events_last_30_days": [
    {"date": "2026-07-01", ...},
    {"date": "2026-07-02", ...},
    // Missing day 3 (gap)
    {"date": "2026-07-04", ...},
    ... (remaining 27 days)
  ]
}
```

### Template 3: Data with Consecutive Gap
```json
{
  "metadata": {
    "service_name": "test-service",
    "time_period": {
      "start": "2026-07-01T00:00:00Z",
      "end": "2026-07-30T23:59:59Z"
    }
  },
  "deployment_events_last_30_days": [
    {"date": "2026-07-01", ...},
    ... (days 1-9)
    // Missing days 10-15 (6-day consecutive gap)
    {"date": "2026-07-16", ...},
    ... (days 16-30)
  ]
}
```

### Template 4: Data with Multiple Gaps
```json
{
  "metadata": {
    "service_name": "test-service",
    "time_period": {
      "start": "2026-07-01T00:00:00Z",
      "end": "2026-07-30T23:59:59Z"
    }
  },
  "deployment_events_last_30_days": [
    {"date": "2026-07-01", ...},
    ... (days 1-4)
    // Missing day 5 (isolated)
    {"date": "2026-07-06", ...},
    ... (days 6-9)
    // Missing days 10-12 (consecutive)
    {"date": "2026-07-13", ...},
    ... (days 13-17)
    // Missing days 18-20 (consecutive)
    {"date": "2026-07-21", ...},
    ... (days 21-24)
    // Missing day 25 (isolated)
    {"date": "2026-07-26", ...},
    ... (days 26-30)
  ]
}
```

### Template 5: Empty Deployment Data
```json
{
  "metadata": {
    "service_name": "test-service",
    "time_period": {
      "start": "2026-07-01T00:00:00Z",
      "end": "2026-07-30T23:59:59Z"
    }
  },
  "deployment_events_last_30_days": []
}
```

### Template 6: Missing Metadata
```json
{
  "deployment_events_last_30_days": [
    {"date": "2026-07-01", ...},
    ... (30 days)
  ]
  // No metadata section
}
```

---

## Existing Test Patterns Reference

**Test Files to Review:**
1. `tests/test_gap_validation_integration.py` - End-to-end gap validation tests
2. `tests/test_coverage_gap_validation.py` - Coverage gap validation tests
3. `tests/test_validation_result_gap_metrics.py` - ValidationResult output tests
4. `tests/unit/test_validation_runner.py` - Validation runner unit tests
5. `tests/unit/test_completeness_validation.py` - Completeness validation tests

**Common Test Patterns:**
```python
# Pattern 1: Create deployment data with gaps
def _create_deployment_data_with_gaps(service_name, start_date, end_date, missing_days):
    # Generate deployment events excluding missing_days
    ...

# Pattern 2: Test validation result structure
result = validate_deployment_file(temp_path)
assert result.gap_detected == expected
assert result.coverage_percentage == expected
assert len(result.gap_periods) == expected

# Pattern 3: Test with temporary file
with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
    json.dump(data, f)
    temp_path = f.name
try:
    result = validate_deployment_file(temp_path)
finally:
    Path(temp_path).unlink()

# Pattern 4: Test gap severity classification
assert result.severity == GapSeverity.CRITICAL  # for extended gaps
assert result.severity == GapSeverity.HIGH      # for large gaps
assert result.severity == GapSeverity.MEDIUM    # for medium gaps
assert result.severity == GapSeverity.LOW       # for small gaps
assert result.severity == GapSeverity.NONE      # for no gaps
```

---

## Priority Test Scenarios

**High Priority (Must Implement):**
1. Scenario 1.1: Complete coverage (happy path)
2. Scenario 1.3: Consecutive gap sequence (core functionality)
3. Scenario 2.3: ValidationResult.to_dict() output structure (schema compliance)
4. Scenario 4.1: Gap detection timeout (error handling)
5. Scenario 4.3: Empty deployment data (edge case)

**Medium Priority (Should Implement):**
1. Scenario 1.2: Single isolated gap
2. Scenario 1.4: Multiple gap periods
3. Scenario 2.1: Gap metrics preserved after schema failures
4. Scenario 3.2: Gap size distribution classification
5. Scenario 4.4: Missing metadata fields

**Low Priority (Nice to Have):**
1. Scenario 1.5: Edge coverage thresholds
2. Scenario 3.5: Anomaly detection messages
3. Scenario 4.5: Malformed gap calculation results
4. Scenario 5.3: Gap detection with custom thresholds
5. Scenario 5.5: Large dataset performance

---

## Summary

This document outlines **45+ test scenarios** across 5 categories:

1. **Normal Gap Detection Flow Invocation** (5 scenarios, 20+ test cases)
   - Complete coverage, isolated gaps, consecutive gaps, multiple gaps, edge thresholds

2. **Result Merging with Existing Validation Results** (5 scenarios, 15+ test cases)
   - Schema failure compatibility, legacy format, output structure, enum handling, safe defaults

3. **Gap Metrics in Final Output Structure** (6 scenarios, 25+ test cases)
   - Coverage calculation, size distribution, classification, guidance, anomalies, intervals

4. **Error Scenarios** (6 scenarios, 20+ test cases)
   - Timeouts, invalid dates, empty data, missing metadata, malformed results, serialization

5. **Integration Scenarios** (5 scenarios, 15+ test cases)
   - End-to-end, multiple failures, custom thresholds, boundary dates, performance

**Total Test Cases:** 95+

**Implementation Priority:** High (25) → Medium (20) → Low (15)

All test scenarios follow existing test patterns in the codebase and ensure comprehensive coverage of gap detection integration functionality.
