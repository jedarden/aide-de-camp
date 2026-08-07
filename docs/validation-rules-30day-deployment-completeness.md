# 30-Day Deployment Data Completeness Validation Rules

**Document Version:** 1.0  
**Date:** 2026-08-07  
**Purpose:** Define validation logic and rules for checking 30-day completeness of deployment data  
**Scope:** Applies to all deployment data analysis services (pbx-web, whisper-stt, etc.)

---

## Overview

This specification defines comprehensive validation rules for assessing 30-day deployment data completeness. It establishes minimum data quality standards, gap detection logic, and error classification for deployment analysis systems.

## Validation Framework

### Core Validation Components

1. **Temporal Coverage Validation** - Ensures 30-day window completeness
2. **Data Completeness Validation** - Validates required fields and values
3. **Quality Threshold Validation** - Ensures minimum data quality standards
4. **Consistency Validation** - Cross-field and cross-source consistency checks

---

## 1. Temporal Coverage Validation

### 1.1 30-Day Window Requirements

**Expected Window Definition:**
- **Duration:** Exactly 30 consecutive days
- **Start Date:** Any date (analysis-specific)
- **End Date:** Start Date + 30 days
- **Expected Days:** 30 calendar days (inclusive of both endpoints)

**Validation Rules:**
```yaml
temporal_coverage:
  window_validation:
    - rule: "window_length_must_be_30_days"
      description: "Analysis window must cover exactly 30 consecutive days"
      check: "end_date - start_date == 30 days"
      severity: "CRITICAL"
      error_message: "Analysis window is not 30 days. Got {actual_days} days."
    
    - rule: "date_range_must_be_contiguous"
      description: "Date range must have no temporal gaps"
      check: "no temporal gaps between start_date and end_date"
      severity: "CRITICAL"
      error_message: "Temporal gaps detected in analysis window."
    
    - rule: "dates_must_be_chronological"
      description: "All dates must be in chronological order"
      check: "start_date <= end_date for all records"
      severity: "ERROR"
      error_message: "Dates are not in chronological order."
```

### 1.2 Daily Coverage Requirements

**Expected Days:** 30 calendar days  
**Minimum Acceptable Days:** Varies by data type and service

**Validation Rules:**
```yaml
daily_coverage:
  general_requirements:
    - rule: "minimum_daily_coverage_threshold"
      description: "Must meet minimum coverage percentage threshold"
      check: "coverage_percentage >= minimum_threshold"
      severity: "WARNING"
      thresholds:
        CRITICAL: "< 10% coverage"
        WARNING: "10% - 49% coverage"
        ACCEPTABLE: "50% - 74% coverage"
        GOOD: "75% - 89% coverage"
        EXCELLENT: ">= 90% coverage"
      error_message: "Coverage {coverage_pct}% is below {threshold}% threshold."
    
    - rule: "consecutive_gap_limit"
      description: "Consecutive day gaps must not exceed maximum allowed"
      check: "longest_consecutive_gap <= maximum_allowed"
      thresholds:
        CRITICAL: "> 7 consecutive days"
        WARNING: "4-7 consecutive days"
        ACCEPTABLE: "1-3 consecutive days"
      severity: "CRITICAL"
      error_message: "Consecutive gap of {gap_length} days exceeds maximum of {max_allowed}."
```

---

## 2. Gap Detection Logic

### 2.1 Gap Classification System

**Gap Types:**
```yaml
gap_types:
  isolated_gap:
    definition: "Single missing day with data on adjacent days"
    example: "Day 15 missing, Days 14 and 16 present"
    severity: "LOW"
    
  consecutive_gap:
    definition: "Two or more consecutive missing days"
    severity: "MEDIUM to HIGH based on duration"
    examples:
      - "2-3 days: MEDIUM severity"
      - "4-7 days: HIGH severity"
      - ">7 days: CRITICAL severity"
      
  edge_gap:
    definition: "Missing data at window boundaries"
    types:
      - "leading_gap: Missing days at analysis start"
      - "trailing_gap: Missing days at analysis end"
    severity: "MEDIUM"
    
  data_anomaly_gap:
    definition: "Day present but with incomplete/invalid data"
    examples:
      - "Deployment record with missing required fields"
      - "Empty workflow execution data"
      - "Invalid timestamp values"
    severity: "WARNING to CRITICAL based on field importance"
```

### 2.2 Gap Detection Algorithm

**Algorithm Steps:**
```python
def detect_gaps(expected_date_range, actual_data_dates):
    """
    Detect gaps in deployment data coverage.
    
    Args:
        expected_date_range: List of 30 expected dates
        actual_data_dates: Set of dates with actual data
        
    Returns:
        gaps: List of gap objects with classification
    """
    gaps = []
    
    # Find missing days
    missing_days = set(expected_date_range) - set(actual_data_dates)
    
    if not missing_days:
        return gaps  # No gaps
    
    # Classify gaps
    sorted_missing = sorted(missing_days)
    consecutive_sequences = find_consecutive_sequences(sorted_missing)
    
    for sequence in consecutive_sequences:
        if len(sequence) == 1:
            gap_type = "isolated"
            severity = "LOW"
        else:
            gap_type = "consecutive"
            severity = classify_consecutive_gap(len(sequence))
        
        gaps.append({
            "gap_type": gap_type,
            "start_date": sequence[0],
            "end_date": sequence[-1],
            "duration_days": len(sequence),
            "severity": severity,
            "dates_affected": list(sequence)
        })
    
    return gaps


def classify_consecutive_gap(duration):
    """Classify consecutive gap severity."""
    if duration >= 7:
        return "CRITICAL"
    elif duration >= 4:
        return "HIGH"
    elif duration >= 2:
        return "MEDIUM"
    else:
        return "LOW"


def find_consecutive_sequences(sorted_dates):
    """Find consecutive date sequences."""
    if not sorted_dates:
        return []
    
    sequences = []
    current_sequence = [sorted_dates[0]]
    
    for i in range(1, len(sorted_dates)):
        if (sorted_dates[i] - sorted_dates[i-1]).days == 1:
            current_sequence.append(sorted_dates[i])
        else:
            sequences.append(current_sequence)
            current_sequence = [sorted_dates[i]]
    
    sequences.append(current_sequence)
    return sequences
```

### 2.3 Gap Severity Assessment

**Severity Matrix:**
```yaml
gap_severity_matrix:
  CRITICAL:
    triggers:
      - "consecutive_gap >= 7 days"
      - "coverage_percentage < 10%"
      - "total_gap_count > 20 days"
      - "edge_gap > 3 days at both boundaries"
    actions:
      - "Flag analysis as unreliable"
      - "Recommend data collection extension"
      - "Suppress statistical calculations"
      
  HIGH:
    triggers:
      - "consecutive_gap >= 4 days and < 7 days"
      - "coverage_percentage 10% - 24%"
      - "total_gap_count 15-20 days"
      - "isolated_gaps > 10 days"
    actions:
      - "Flag analysis as questionable"
      - "Recommend gap investigation"
      - "Apply confidence interval warnings"
      
  MEDIUM:
    triggers:
      - "consecutive_gap 2-3 days"
      - "coverage_percentage 25% - 49%"
      - "total_gap_count 10-14 days"
      - "edge_gap at one boundary"
    actions:
      - "Flag analysis as acceptable with caveats"
      - "Document gap patterns"
      
  LOW:
    triggers:
      - "isolated_gap = 1 day"
      - "coverage_percentage >= 50%"
      - "total_gap_count < 10 days"
    actions:
      - "Accept analysis as reliable"
      - "Document minor gaps"
```

---

## 3. Data Completeness Validation

### 3.1 Required Field Validation

**Core Required Fields (All Deployment Records):**
```yaml
required_fields:
  common:
    - field: "timestamp"
      type: "ISO 8601 datetime"
      validation: "Must be within 30-day window"
      required: true
      
    - field: "service_name"
      type: "string"
      validation: "Must match known service identifiers"
      allowed_values: ["pbx-web", "whisper-stt"]
      required: true
      
    - field: "deployment_id"
      type: "string"
      validation: "Unique identifier for deployment"
      required: true
      
    - field: "deployment_status"
      type: "enum"
      allowed_values: ["successful", "failed", "rolled_over", "scaled_down_or_failed"]
      required: true
      
    - field: "image_version"
      type: "string"
      validation: "Must follow semantic versioning or git commit"
      required: true
```

**Service-Specific Required Fields:**

```yaml
service_specific:
  pbx-web:
    - field: "workflow_runs"
      type: "array"
      validation: "List of workflow execution records"
      required: false
      
    - field: "replicaset_name"
      type: "string"
      validation: "Kubernetes ReplicaSet identifier"
      required: true
      
  whisper-stt:
    - field: "model_version"
      type: "string"
      validation: "Whisper model version identifier"
      required: true
      
    - field: "resource_allocation"
      type: "object"
      fields:
        - "cpu_limit"
        - "memory_limit"
        - "storage_type"
      required: true
```

### 3.2 Field Completeness Rules

```yaml
field_completeness:
  validation_rules:
    - rule: "no_null_required_fields"
      description: "Required fields must not be null or empty"
      check: "all required fields have non-null values"
      severity: "CRITICAL"
      error_message: "Required field '{field}' is null or empty in record {record_id}."
      
    - rule: "valid_field_types"
      description: "Field values must match expected types"
      check: "field value type matches schema definition"
      severity: "ERROR"
      error_message: "Field '{field}' has invalid type. Expected {expected_type}, got {actual_type}."
      
    - rule: "enum_value_validation"
      description: "Enum fields must use allowed values"
      check: "field value in allowed_values list"
      severity: "ERROR"
      error_message: "Field '{field}' has invalid value '{value}'. Must be one of {allowed_values}."
      
    - rule: "timestamp_range_validation"
      description: "Timestamps must be within analysis window"
      check: "timestamp >= start_date and timestamp <= end_date"
      severity: "WARNING"
      error_message: "Timestamp '{timestamp}' is outside analysis window."
```

---

## 4. Quality Threshold Validation

### 4.1 Minimum Data Quality Standards

**Deployment-Specific Thresholds:**

```yaml
quality_thresholds:
  deployment_data:
    minimum_deployment_days:
      description: "Minimum days with deployment activity"
      threshold: 2
      severity: "WARNING"
      rationale: "Need at least 2 deployment days for pattern analysis"
      error_message: "Only {actual_days} deployment days found. Minimum required: {min_days}."
      
    minimum_successful_deployments:
      description: "Minimum successful deployment count"
      threshold: 1
      severity: "CRITICAL"
      rationale: "At least one successful deployment needed for baseline"
      error_message: "No successful deployments found in 30-day window."
      
    maximum_deployment_failure_rate:
      description: "Maximum acceptable deployment failure rate"
      threshold: 0.75  # 75%
      severity: "WARNING"
      rationale: "High failure rates indicate systemic issues"
      error_message: "Deployment failure rate {failure_rate}% exceeds maximum {max_failure_rate}%."
```

**Workflow-Specific Thresholds:**

```yaml
workflow_data:
  minimum_workflow_runs:
    description: "Minimum workflow execution records"
    threshold: 5
    severity: "WARNING"
    rationale: "Need minimum sample size for statistical analysis"
    error_message: "Only {actual_runs} workflow runs found. Minimum required: {min_runs}."
    
  workflow_success_rate:
    description: "Minimum workflow success rate"
    threshold: 0.60  # 60%
    severity: "WARNING"
    rationale: "CI/CD pipeline health indicator"
    error_message: "Workflow success rate {success_rate}% is below minimum {min_rate}%."
```

**Coverage-Specific Thresholds:**

```yaml
coverage_thresholds:
  minimum_coverage_percentage:
    service_types:
      critical_services:
        threshold: 50
        severity: "CRITICAL"
        rationale: "Critical services need higher coverage"
        services: ["pbx-web", "whisper-stt"]
        
      optional_services:
        threshold: 25
        severity: "WARNING"
        rationale: "Lower threshold for non-critical services"
        
  acceptable_gap_distribution:
    max_consecutive_gaps: 3
    max_total_gaps: 15
    max_isolated_gaps: 10
    severity: "WARNING"
    error_message: "Gap distribution exceeds acceptable limits."
```

### 4.2 Data Quality Assessment

**Quality Scoring System:**

```yaml
quality_assessment:
  scoring_categories:
    excellent:
      criteria:
        coverage_percentage: ">= 90%"
        gap_count: "< 5 days"
        consecutive_gaps: "none"
        field_completeness: "100%"
      reliability: "High confidence in analysis results"
      
    good:
      criteria:
        coverage_percentage: "75% - 89%"
        gap_count: "5-9 days"
        consecutive_gaps: "max 2 days"
        field_completeness: ">= 95%"
      reliability: "Good confidence, minor caveats"
      
    fair:
      criteria:
        coverage_percentage: "50% - 74%"
        gap_count: "10-14 days"
        consecutive_gaps: "max 4 days"
        field_completeness: ">= 90%"
      reliability: "Acceptable confidence, notable limitations"
      
    poor:
      criteria:
        coverage_percentage: "< 50%"
        gap_count: "> 14 days"
        consecutive_gaps: "> 4 days"
        field_completeness: "< 90%"
      reliability: "Low confidence, results should be questioned"
```

---

## 5. Consistency Validation

### 5.1 Cross-Field Consistency

**Temporal Consistency:**
```yaml
temporal_consistency:
  rules:
    - rule: "deployment_timestamp_sequence"
      description: "Deployment timestamps must be sequential"
      check: "deployment timestamps are monotonically increasing"
      severity: "ERROR"
      error_message: "Deployment timestamps are not in chronological order."
      
    - rule: "workflow_deployment_alignment"
      description: "Workflow timestamps should align with deployment timestamps"
      check: "workflow_timestamp ≈ deployment_timestamp (within 1 hour)"
      severity: "WARNING"
      error_message: "Workflow and deployment timestamps are misaligned by {time_diff}."
```

**Status Consistency:**
```yaml
status_consistency:
  rules:
    - rule: "failed_deployment_no_replicas"
      description: "Failed deployments should not have running replicas"
      check: "if deployment_status == 'failed', then running_replicas == 0"
      severity: "ERROR"
      error_message: "Failed deployment {deployment_id} has {running_replicas} running replicas."
      
    - rule: "successful_deployment_has_replicas"
      description: "Successful deployments should have running replicas"
      check: "if deployment_status == 'successful', then running_replicas >= 1"
      severity: "ERROR"
      error_message: "Successful deployment {deployment_id} has no running replicas."
```

### 5.2 Cross-Source Consistency

**Kubernetes vs. Git Consistency:**
```yaml
cross_source_consistency:
  kubernetes_git:
    rules:
      - rule: "image_version_match"
        description: "Kubernetes image versions should match git tags"
        check: "kubernetes.image_version exists in git.tags"
        severity: "WARNING"
        error_message: "Image version {version} not found in git history."
        
      - rule: "deployment_count_consistency"
        description: "ReplicaSet count should approximate git deployment commits"
        check: "abs(replicaset_count - git_deployment_commits) <= 1"
        severity: "INFO"
        error_message: "ReplicaSet count ({rs_count}) differs from git commits ({git_count})."
```

**Workflow vs. Deployment Consistency:**
```yaml
workflow_deployment:
  rules:
    - rule: "workflow_deployment_count_reasonableness"
      description: "Workflow runs should roughly correlate with deployments"
      check: "workflow_runs should be within reasonable range of deployments"
      threshold: "workflow_runs >= deployments * 0.8 and workflow_runs <= deployments * 1.5"
      severity: "WARNING"
      error_message: "Workflow run count ({workflows}) unusual for deployment count ({deployments})."
```

---

## 6. Validation Error Conditions

### 6.1 Error Severity Levels

**Severity Definitions:**
```yaml
error_severity_levels:
  CRITICAL:
    impact: "Analysis cannot be performed or results are unreliable"
    action: "Stop analysis, require data correction or collection extension"
    examples:
      - "Coverage < 10%"
      - "No successful deployments"
      - "Required fields missing"
      - "Window not 30 days"
      
  ERROR:
    impact: "Analysis components are compromised"
    action: "Flag affected components, continue with warnings"
    examples:
      - "Invalid field types"
      - "Status inconsistencies"
      - "Timestamp out of range"
      
  WARNING:
    impact: "Analysis quality may be reduced"
    action: "Document issues, proceed with caveats"
    examples:
      - "Coverage 10-49%"
      - "High gap counts"
      - "Cross-source inconsistencies"
      
  INFO:
    impact: "Analysis not affected, but worth noting"
    action: "Log for reference"
    examples:
      - "Minor count discrepancies"
      - "Unexpected but valid patterns"
```

### 6.2 Validation Error Codes

**Error Code Structure:** `VAL-{CATEGORY}-{SPECIFIC}-{NUMBER}`

**Category Codes:**
- `TEMP`: Temporal validation errors
- `COV`: Coverage validation errors
- `FIELD`: Field validation errors
- `QUAL`: Quality threshold errors
- `CONS`: Consistency validation errors

**Specific Error Codes:**
```yaml
error_codes:
  # Temporal Errors
  TEMP-001: "Analysis window not 30 days"
  TEMP-002: "Dates not in chronological order"
  TEMP-003: "Temporal gaps in analysis window"
  
  # Coverage Errors
  COV-001: "Coverage below 10% (CRITICAL)"
  COV-002: "Coverage below 50% (WARNING)"
  COV-003: "Consecutive gap >= 7 days (CRITICAL)"
  COV-004: "Total gap count > 20 days (CRITICAL)"
  COV-005: "Consecutive gap >= 4 days (WARNING)"
  COV-006: "Total gap count > 10 days (WARNING)"
  
  # Field Errors
  FIELD-001: "Required field null or empty"
  FIELD-002: "Invalid field type"
  FIELD-003: "Invalid enum value"
  FIELD-004: "Timestamp outside analysis window"
  
  # Quality Errors
  QUAL-001: "No successful deployments found"
  QUAL-002: "Deployment failure rate > 75%"
  QUAL-003: "Workflow runs below minimum sample size"
  QUAL-004: "Data quality assessment: POOR"
  
  # Consistency Errors
  CONS-001: "Deployment timestamp sequence violation"
  CONS-002: "Failed deployment with running replicas"
  CONS-003: "Successful deployment with no running replicas"
  CONS-004: "Image version not found in git history"
```

### 6.3 Error Handling Workflow

**Validation Process Flow:**
```yaml
validation_workflow:
  steps:
    1. pre_validation:
       - check: "Data files exist and are readable"
       - check: "JSON parsing successful"
       - on_failure: "Return CRITICAL error, stop validation"
       
    2. structural_validation:
       - check: "Required fields present and non-null"
       - check: "Field types match schema"
       - on_failure: "Return ERROR, continue with warnings"
       
    3. temporal_validation:
       - check: "30-day window validity"
       - check: "Chronological date order"
       - on_failure: "Return CRITICAL error for window issues"
       
    4. coverage_validation:
       - check: "Coverage percentages"
       - check: "Gap detection and classification"
       - on_failure: "Classify severity, document gaps"
       
    5. quality_validation:
       - check: "Minimum thresholds met"
       - check: "Data quality assessment"
       - on_failure: "Flag quality issues, continue analysis"
       
    6. consistency_validation:
       - check: "Cross-field consistency"
       - check: "Cross-source consistency"
       - on_failure: "Log inconsistencies, continue analysis"
       
    7. final_assessment:
       - aggregate: "All validation results"
       - determine: "Overall data quality rating"
       - recommend: "Proceed/flag/stop analysis"
```

---

## 7. Minimum Required Deployment Days Criteria

### 7.1 Service-Specific Minimums

**Deployment Day Requirements:**

```yaml
minimum_deployment_days:
  pbx-web:
    minimum_days: 2
    rationale: "Need at least 2 deployment events for pattern analysis"
    exception_handling: "If only 1 day, flag as WARNING, proceed with caveats"
    
  whisper-stt:
    minimum_days: 3
    rationale: "Higher deployment frequency expected for ML service iterations"
    exception_handling: "If < 3 days, investigate but don't fail analysis"
    
  all_services:
    absolute_minimum: 1
    rationale: "At least one deployment needed for baseline"
    critical_threshold: 0
    critical_action: "If 0 deployment days, CRITICAL error, stop analysis"
```

### 7.2 Deployment Frequency Validation

**Frequency Reasonableness Checks:**

```yaml
deployment_frequency_validation:
  rules:
    - rule: "deployment_frequency_reasonableness"
      description: "Deployment frequency should be within expected ranges"
      expected_ranges:
        pbx-web: "1-5 deployments per 30 days"
        whisper-stt: "2-8 deployments per 30 days"
      severity: "INFO"
      check: "deployment_count within expected range"
      error_message: "Deployment count ({count}) outside expected range ({min}-{max})."
      
    - rule: "deployment_clustering_detection"
      description: "Deployments should not be excessively clustered"
      check: "no more than 5 deployments in any 3-day period"
      severity: "WARNING"
      error_message: "Excessive deployment clustering detected."
```

---

## 8. Implementation Guidelines

### 8.1 Validation Function Structure

**Core Validation Functions:**
```python
def validate_30day_completeness(deployment_data, analysis_window):
    """
    Main validation function for 30-day deployment data completeness.
    
    Args:
        deployment_data: Deployment records dict/list
        analysis_window: (start_date, end_date) tuple
        
    Returns:
        ValidationResult object with:
        - valid (bool)
        - severity (str: 'CRITICAL', 'ERROR', 'WARNING', 'INFO')
        - errors (list of Error objects)
        - quality_assessment (str: 'excellent', 'good', 'fair', 'poor')
        - recommendations (list of str)
    """
    validator = DeploymentDataValidator(deployment_data, analysis_window)
    
    results = {
        'temporal_validation': validator.validate_temporal_coverage(),
        'field_validation': validator.validate_required_fields(),
        'coverage_validation': validator.validate_coverage(),
        'quality_validation': validator.validate_quality_thresholds(),
        'consistency_validation': validator.validate_consistency(),
    }
    
    return validator.aggregate_results(results)
```

### 8.2 Error Reporting Format

**Standard Error Object:**
```python
@dataclass
class ValidationError:
    error_code: str
    severity: str
    category: str
    field: str
    message: str
    context: Dict[str, Any]
    recommendation: str
    
    def to_dict(self):
        return {
            'error_code': self.error_code,
            'severity': self.severity,
            'category': self.category,
            'field': self.field,
            'message': self.message,
            'context': self.context,
            'recommendation': self.recommendation
        }
```

### 8.3 Validation Output Format

**Validation Result Structure:**
```json
{
  "validation_timestamp": "2026-08-07T12:00:00Z",
  "overall_status": "VALID_WITH_WARNINGS",
  "quality_assessment": "fair",
  "validation_results": {
    "temporal_validation": {
      "valid": true,
      "errors": []
    },
    "coverage_validation": {
      "valid": false,
      "errors": [
        {
          "error_code": "COV-002",
          "severity": "WARNING",
          "message": "Coverage 45% is below 50% threshold."
        }
      ]
    },
    "quality_validation": {
      "valid": true,
      "errors": []
    }
  },
  "summary": {
    "total_errors": 1,
    "critical_errors": 0,
    "error_errors": 0,
    "warning_errors": 1,
    "info_errors": 0
  },
  "recommendations": [
    "Extend data collection period to improve coverage",
    "Investigate missing deployment days"
  ]
}
```

---

## 9. Acceptance Criteria Validation

### 9.1 Task Requirements Validation

**Requirements Met:**
- ✅ **Validation Rules Specified**: Comprehensive rule set for 30-day coverage checks
- ✅ **Gap Detection Logic Defined**: Complete gap classification and detection algorithm
- ✅ **Minimum Deployment Criteria Established**: Service-specific minimums with thresholds
- ✅ **Validation Error Conditions Documented**: Full error code system and severity matrix

### 9.2 Validation Implementation Checklist

**To implement these rules:**
- [ ] Create `DeploymentDataValidator` class with all validation methods
- [ ] Implement gap detection algorithm
- [ ] Create error code enumeration and error objects
- [ ] Implement quality assessment scoring
- [ ] Create validation result aggregation
- [ ] Add comprehensive test coverage
- [ ] Document API and usage examples

---

## Appendix A: Validation Examples

### Example 1: Excellent Data Quality

**Input:**
```json
{
  "analysis_window": {
    "start_date": "2026-07-07",
    "end_date": "2026-08-06",
    "expected_days": 30
  },
  "deployment_data": {
    "service": "pbx-web",
    "deployment_days": 28,
    "coverage_percentage": 93.3,
    "gaps": [
      {"date": "2026-07-15", "type": "isolated"}
    ]
  }
}
```

**Validation Result:**
```json
{
  "status": "VALID",
  "quality_assessment": "excellent",
  "errors": []
}
```

### Example 2: Poor Data Quality

**Input:**
```json
{
  "deployment_data": {
    "service": "whisper-stt",
    "deployment_days": 5,
    "coverage_percentage": 16.7,
    "gaps": [
      {"consecutive": ["2026-07-10", "2026-07-11", "2026-07-12", "2026-07-13", "2026-07-14"]},
      {"consecutive": ["2026-07-20", "2026-07-21"]},
      ... (23 total gap days)
    ]
  }
}
```

**Validation Result:**
```json
{
  "status": "CRITICAL",
  "quality_assessment": "poor",
  "errors": [
    {
      "error_code": "COV-001",
      "severity": "CRITICAL",
      "message": "Coverage 16.7% is below 10% threshold."
    },
    {
      "error_code": "COV-003",
      "severity": "CRITICAL",
      "message": "Consecutive gap of 5 days exceeds maximum."
    },
    {
      "error_code": "COV-004",
      "severity": "CRITICAL",
      "message": "Total gap count 25 exceeds maximum 20."
    }
  ]
}
```

---

## Appendix B: Related Documentation

**Related Documents:**
- `/home/coding/aide-de-camp/validate_coverage_and_gaps.py` - Existing gap validation implementation
- `/home/coding/aide-de-camp/validate_deployment_data.py` - Deployment data structure validation
- `/home/coding/aide-de-camp/deployment-analysis-30d.md` - 30-day analysis methodology
- `/home/coding/aide-de-camp/whisper_stt_deployment_schema.py` - Data schema definitions

---

**Document Control:**
- **Author:** Claude (AI Assistant)
- **Version:** 1.0
- **Last Updated:** 2026-08-07
- **Review Cycle:** Quarterly or when validation requirements change
- **Status:** Complete specification ready for implementation