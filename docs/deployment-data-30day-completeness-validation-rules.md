# Deployment Data 30-Day Completeness Validation Rules Specification

## Overview

This specification defines the validation logic and rules for checking 30-day completeness of deployment data across services in the ardenone-cluster environment. These rules ensure data quality, completeness, and reliability for deployment analysis and comparison.

**Version:** 1.0  
**Date:** 2026-08-07  
**Bead ID:** adc-3zpep  
**Schema Reference:** WhisperSTTDeploymentSchema (whisper_stt_deployment_schema.py)

---

## 1. Scope and Applicability

### 1.1 Target Services
- **whisper-stt** (primary focus)
- **whisper-openai** (related service)
- **pbx-web** (comparison service)
- Any additional services added to the deployment monitoring system

### 1.2 Data Sources
- Kubernetes ReplicaSets via read-only kubectl proxy
- Argo Workflow runs (where applicable)
- ArgoCD application data (where applicable)
- Cluster deployment metadata

### 1.3 Time Period
- **Required Coverage:** 30 consecutive days
- **Measurement Period:** Rolling 30-day window from current date
- **Grace Period:** ±2 days allowable for data collection delays

---

## 2. Validation Rules Categories

### 2.1 Structural Validation Rules
Ensure the data structure conforms to the expected schema format.

#### Rule SV-001: Top-Level Structure
**Requirement:** JSON object must contain all required top-level keys.

**Required Keys:**
- `metadata` (object)
- `cluster_deployments` (object)
- `summary` (object)

**Optional Keys:**
- `argo_workflows` (object)
- `argo_cd` (object)
- `pod_health` (object)
- `resources` (object)
- `storage` (object)
- `error_incidents` (object)
- `notes` (array)

**Error Condition:** Missing any required key

**Validation Logic:**
```python
required_keys = {'metadata', 'cluster_deployments', 'summary'}
missing_keys = required_keys - set(data.keys())
if missing_keys:
    raise ValidationError(f"Missing required top-level keys: {missing_keys}")
```

#### Rule SV-002: Metadata Structure
**Requirement:** Metadata object must contain all required fields with valid data types.

**Required Fields:**
- `generated_at` (string, ISO8601 timestamp)
- `data_period_start` (string, ISO8601 timestamp)
- `data_period_end` (string, ISO8601 timestamp)
- `services` (array of strings)
- `clusters` (array of strings)
- `data_sources` (array of strings)

**Error Conditions:**
- Missing any required field
- Invalid data type for any field
- Empty arrays for services, clusters, or data_sources

**Validation Logic:**
```python
metadata = data.get('metadata', {})
required_metadata_fields = {
    'generated_at': str,
    'data_period_start': str,
    'data_period_end': str,
    'services': list,
    'clusters': list,
    'data_sources': list
}

for field, expected_type in required_metadata_fields.items():
    if field not in metadata:
        raise ValidationError(f"Missing metadata field: {field}")
    if not isinstance(metadata[field], expected_type):
        raise ValidationError(f"Invalid type for {field}: expected {expected_type}")
    if expected_type == list and len(metadata[field]) == 0:
        raise ValidationError(f"Empty array for {field}")
```

#### Rule SV-003: Service-Specific Structure
**Requirement:** Each service in `cluster_deployments` must contain required deployment fields.

**Required Fields per Service:**
- `namespace` (string)
- `deployment_name` (string)
- `created_at` (string, ISO8601 timestamp)
- `current_image` (string)
- `current_replicas` (integer, >= 0)
- `replica_history` (array)
- `deployments_last_30_days` (integer, >= 0)
- `successful_deployments` (integer, >= 0)
- `failed_deployments` (integer, >= 0)
- `deployment_versions` (array)
- `all_versions_in_history` (array)

**Error Conditions:**
- Missing any required field
- Negative values for numeric fields
- Invalid timestamp format
- Empty replica_history array

---

### 2.2 Temporal Validation Rules
Ensure time-based data completeness and accuracy.

#### Rule TV-001: 30-Day Coverage
**Requirement:** Data must cover at least 30 consecutive days within the expected time window.

**Parameters:**
- Minimum days covered: 30
- Maximum allowable gap: 2 days (for data collection delays)
- Measurement: From oldest deployment timestamp to newest

**Error Conditions:**
- Days covered < 30 (FAIL)
- Days covered < 28 (WARN - borderline)
- Days covered >= 30 (PASS)

**Validation Logic:**
```python
def calculate_days_covered(replica_history):
    """Calculate the number of days covered by deployment data."""
    if not replica_history:
        return 0
    
    timestamps = []
    for entry in replica_history:
        try:
            ts = datetime.fromisoformat(entry['created_at'].replace('Z', '+00:00'))
            timestamps.append(ts)
        except (ValueError, KeyError):
            continue
    
    if not timestamps:
        return 0
    
    timestamps.sort()
    oldest = timestamps[0]
    newest = timestamps[-1]
    days_covered = (newest - oldest).days
    
    return days_covered

def validate_30day_coverage(days_covered):
    """Validate 30-day coverage requirement."""
    if days_covered < 28:
        return "FAIL", f"Insufficient coverage: {days_covered} days (< 28)"
    elif days_covered < 30:
        return "WARN", f"Borderline coverage: {days_covered} days (< 30)"
    else:
        return "PASS", f"Adequate coverage: {days_covered} days (>= 30)"
```

#### Rule TV-002: Timestamp Validity
**Requirement:** All timestamp fields must contain valid ISO8601 timestamps.

**Applicable Fields:**
- `metadata.generated_at`
- `metadata.data_period_start`
- `metadata.data_period_end`
- All `created_at` fields in replica_history
- Any `started_at`, `finished_at`, `last_updated` timestamps

**Error Conditions:**
- Empty timestamp string
- Invalid ISO8601 format
- Timestamp parsing failure
- Timestamp outside reasonable bounds (e.g., future dates)

**Validation Logic:**
```python
def validate_timestamp(timestamp_str, field_name="timestamp"):
    """Validate ISO8601 timestamp format and value."""
    if not timestamp_str or not isinstance(timestamp_str, str):
        raise ValidationError(f"Invalid {field_name}: empty or not a string")
    
    try:
        # Handle various ISO formats
        ts = timestamp_str
        if ts.endswith('Z'):
            ts = ts[:-1] + '+00:00'
        dt = datetime.fromisoformat(ts.replace('+00:00', ''))
        
        # Check for future timestamps (allow 2 days for clock skew)
        if dt > datetime.now() + timedelta(days=2):
            raise ValidationError(f"Invalid {field_name}: timestamp is in the future")
        
        # Check for unreasonably old timestamps (e.g., before 2020)
        if dt < datetime(2020, 1, 1):
            raise ValidationError(f"Invalid {field_name}: timestamp is unreasonably old")
        
        return dt
    except ValueError as e:
        raise ValidationError(f"Invalid {field_name}: {e}")
```

#### Rule TV-003: Timestamp Consistency
**Requirement:** Timestamp relationships must be logically consistent.

**Required Relationships:**
- `data_period_start` < `data_period_end`
- `data_period_end` <= `generated_at`
- All replica timestamps must be within [data_period_start, data_period_end]
- `started_at` < `finished_at` (for workflow runs)

**Error Conditions:**
- Inverted timestamp ranges
- Timestamps outside declared data period
- Negative duration calculations

**Validation Logic:**
```python
def validate_timestamp_consistency(metadata, replica_history):
    """Validate logical consistency of timestamps."""
    start = validate_timestamp(metadata['data_period_start'], 'data_period_start')
    end = validate_timestamp(metadata['data_period_end'], 'data_period_end')
    generated = validate_timestamp(metadata['generated_at'], 'generated_at')
    
    if start >= end:
        raise ValidationError("data_period_start must be before data_period_end")
    
    if end > generated:
        raise ValidationError("data_period_end must be before or equal to generated_at")
    
    # Check replica timestamps are within range
    for entry in replica_history:
        ts = validate_timestamp(entry.get('created_at'), 'replica created_at')
        if ts < start or ts > generated:
            raise ValidationError(f"Replica timestamp {ts} outside data period range")
```

---

### 2.3 Data Quality Validation Rules
Ensure data field values are valid and consistent.

#### Rule DQ-001: Required Fields Presence
**Requirement:** All critical fields must be present and non-null.

**Critical Fields:**
- `metadata.generated_at`
- `metadata.data_period_start`
- `metadata.data_period_end`
- All service deployment timestamps
- All status fields
- All replica count fields

**Error Conditions:**
- Missing critical field
- Null value for critical field
- Empty string for string fields

**Validation Logic:**
```python
def validate_required_fields(data, service_name="whisper-stt"):
    """Validate presence of required fields."""
    errors = []
    
    # Check metadata
    metadata = data.get('metadata', {})
    critical_metadata_fields = ['generated_at', 'data_period_start', 'data_period_end']
    for field in critical_metadata_fields:
        if field not in metadata or metadata[field] is None:
            errors.append(f"Missing or null metadata.{field}")
    
    # Check service deployment data
    cluster_deployments = data.get('cluster_deployments', {})
    if service_name not in cluster_deployments:
        errors.append(f"Missing deployment data for service: {service_name}")
        return False, errors
    
    service_data = cluster_deployments[service_name]
    critical_service_fields = [
        'namespace', 'deployment_name', 'created_at', 'current_image',
        'current_replicas', 'deployments_last_30_days', 'replica_history'
    ]
    
    for field in critical_service_fields:
        if field not in service_data or service_data[field] is None:
            errors.append(f"Missing or null cluster_deployments.{service_name}.{field}")
    
    return len(errors) == 0, errors
```

#### Rule DQ-002: Numeric Field Ranges
**Requirement:** All numeric fields must be within acceptable ranges.

**Range Requirements:**
- `current_replicas`: >= 0
- `deployments_last_30_days`: >= 0
- `successful_deployments`: >= 0
- `failed_deployments`: >= 0
- `days_ago`: >= 0
- `restart_count`: >= 0
- `age_days`: >= 0

**Consistency Requirements:**
- `successful_deployments` + `failed_deployments` <= `deployments_last_30_days`
- `running_pods` <= `total_pods`
- `ready_replicas` <= `replicas`

**Error Conditions:**
- Negative values
- Values exceeding logical maximums
- Inconsistent aggregate calculations

**Validation Logic:**
```python
def validate_numeric_ranges(data):
    """Validate numeric field ranges and consistency."""
    errors = []
    
    for service_name, service_data in data.get('cluster_deployments', {}).items():
        # Check non-negative requirements
        non_negative_fields = {
            'current_replicas': service_data.get('current_replicas'),
            'deployments_last_30_days': service_data.get('deployments_last_30_days'),
            'successful_deployments': service_data.get('successful_deployments'),
            'failed_deployments': service_data.get('failed_deployments')
        }
        
        for field_name, value in non_negative_fields.items():
            if value is not None and value < 0:
                errors.append(f"{service_name}.{field_name} is negative: {value}")
        
        # Check aggregate consistency
        total = service_data.get('deployments_last_30_days', 0)
        successful = service_data.get('successful_deployments', 0)
        failed = service_data.get('failed_deployments', 0)
        
        if successful + failed > total:
            errors.append(
                f"{service_name}: successful + failed ({successful + failed}) > "
                f"total deployments ({total})"
            )
    
    return len(errors) == 0, errors
```

#### Rule DQ-003: Enum Field Validity
**Requirement:** Enumeration fields must contain only valid values.

**Valid Enum Values:**
- `ReplicaStatus`: "successful", "rolled_over", "scaled_down_or_failed"
- `WorkflowStatus`: "Succeeded", "Failed", "Running"
- `PodStatus`: "Running", "Pending", "Failed", "Succeeded", "Unknown"
- `StorageStatus`: "Bound", "Pending", "Lost"

**Error Conditions:**
- Invalid enum value
- Case mismatch
- Empty or null status field

**Validation Logic:**
```python
VALID_REPLICA_STATUSES = {"successful", "rolled_over", "scaled_down_or_failed"}
VALID_WORKFLOW_STATUSES = {"Succeeded", "Failed", "Running"}
VALID_POD_STATUSES = {"Running", "Pending", "Failed", "Succeeded", "Unknown"}
VALID_STORAGE_STATUSES = {"Bound", "Pending", "Lost"}

def validate_enum_fields(data):
    """Validate enum field values."""
    errors = []
    
    for service_name, service_data in data.get('cluster_deployments', {}).items():
        for entry in service_data.get('replica_history', []):
            status = entry.get('status')
            if status not in VALID_REPLICA_STATUSES:
                errors.append(
                    f"{service_name}: invalid replica status '{status}' "
                    f"(must be one of {VALID_REPLICA_STATUSES})"
                )
    
    return len(errors) == 0, errors
```

---

### 2.4 Completeness Validation Rules
Ensure comprehensive coverage of the 30-day period.

#### Rule CV-001: Minimum Deployment Days
**Requirement:** Must have deployment activity across a minimum number of distinct days.

**Parameters:**
- Minimum distinct deployment days: 10 (out of 30)
- Definition of "deployment day": At least one replica creation or update event
- Allowable for stable services: May have fewer days if service is intentionally stable

**Error Conditions:**
- < 5 distinct deployment days (FAIL - insufficient data)
- 5-9 distinct deployment days (WARN - limited activity)
- >= 10 distinct deployment days (PASS)

**Validation Logic:**
```python
def count_distinct_deployment_days(replica_history):
    """Count distinct days with deployment activity."""
    distinct_days = set()
    
    for entry in replica_history:
        if 'created_at' in entry:
            try:
                ts = datetime.fromisoformat(entry['created_at'].replace('Z', '+00:00'))
                distinct_days.add(ts.date())
            except (ValueError, KeyError):
                continue
    
    return len(distinct_days)

def validate_minimum_deployment_days(distinct_days):
    """Validate minimum deployment days requirement."""
    if distinct_days < 5:
        return "FAIL", f"Insufficient deployment activity: {distinct_days} days (< 5)"
    elif distinct_days < 10:
        return "WARN", f"Limited deployment activity: {distinct_days} days (< 10)"
    else:
        return "PASS", f"Adequate deployment activity: {distinct_days} days (>= 10)"
```

#### Rule CV-002: Gap Detection
**Requirement:** Identify and report significant temporal gaps in deployment data.

**Gap Definitions:**
- **Critical Gap:** > 14 days without deployment activity (FAIL if unexplained)
- **Warning Gap:** 7-14 days without deployment activity (WARN)
- **Acceptable Gap:** < 7 days (normal deployment frequency)

**Gap Detection Logic:**
```python
def detect_deployment_gaps(replica_history, critical_threshold=14, warning_threshold=7):
    """Detect significant gaps in deployment data."""
    gaps = []
    
    # Sort timestamps
    timestamps = []
    for entry in replica_history:
        if 'created_at' in entry:
            try:
                ts = datetime.fromisoformat(entry['created_at'].replace('Z', '+00:00'))
                timestamps.append(ts)
            except (ValueError, KeyError):
                continue
    
    timestamps.sort()
    
    # Calculate gaps between consecutive deployments
    for i in range(1, len(timestamps)):
        gap_days = (timestamps[i] - timestamps[i-1]).days
        
        if gap_days >= warning_threshold:
            gaps.append({
                'gap_start': timestamps[i-1].isoformat(),
                'gap_end': timestamps[i].isoformat(),
                'gap_days': gap_days,
                'severity': 'CRITICAL' if gap_days >= critical_threshold else 'WARNING'
            })
    
    return gaps

def validate_gap_coverage(gaps):
    """Validate gap coverage and report findings."""
    critical_gaps = [g for g in gaps if g['severity'] == 'CRITICAL']
    warning_gaps = [g for g in gaps if g['severity'] == 'WARNING']
    
    if critical_gaps:
        return "FAIL", f"{len(critical_gaps)} critical gaps detected (> {critical_threshold} days)"
    elif warning_gaps:
        return "WARN", f"{len(warning_gaps)} warning gaps detected (> {warning_threshold} days)"
    else:
        return "PASS", "No significant gaps detected"
```

#### Rule CV-003: Replica History Completeness
**Requirement:** Replica history must contain complete and accurate deployment records.

**Completeness Criteria:**
- All replica sets created within 30-day period must be recorded
- Replica status must be accurately reflected
- Image tags must be present and valid
- Creation timestamps must be accurate

**Error Conditions:**
- Empty replica_history array
- Missing critical replica information
- Duplicate replica entries (same name, different data)
- Incomplete image tags or version information

**Validation Logic:**
```python
def validate_replica_history_completeness(service_data):
    """Validate replica history completeness."""
    errors = []
    warnings = []
    
    replica_history = service_data.get('replica_history', [])
    
    if not replica_history:
        errors.append("Empty replica_history - no deployment records found")
        return False, errors, warnings
    
    # Check for required fields in each entry
    required_fields = ['name', 'created_at', 'image', 'replicas', 'status', 'days_ago']
    for i, entry in enumerate(replica_history):
        missing_fields = [f for f in required_fields if f not in entry or entry[f] is None]
        if missing_fields:
            errors.append(f"Replica entry {i}: missing fields {missing_fields}")
    
    # Check for duplicate replica names
    replica_names = [entry.get('name') for entry in replica_history]
    duplicates = [name for name in set(replica_names) if replica_names.count(name) > 1]
    if duplicates:
        warnings.append(f"Duplicate replica names detected: {duplicates}")
    
    # Check image tag format
    for entry in replica_history:
        image = entry.get('image', '')
        if ':' not in image or image.endswith(':latest'):
            warnings.append(f"Invalid image tag format: {image}")
    
    return len(errors) == 0, errors, warnings
```

#### Rule CV-004: Summary Metrics Consistency
**Requirement:** Summary metrics must accurately reflect the detailed deployment data.

**Consistency Checks:**
- `summary.total_deployments_last_30_days` must equal sum of all service deployments
- `summary.gaps_detected` must match actual gap analysis
- `summary.data_coverage` must accurately reflect completeness percentage
- `summary.largest_gap_days` must match actual largest gap

**Error Conditions:**
- Summary metrics don't match calculated values
- Data coverage percentage is inaccurate
- Largest gap reported doesn't match analysis

**Validation Logic:**
```python
def validate_summary_consistency(data):
    """Validate summary metrics consistency with detailed data."""
    errors = []
    warnings = []
    
    summary = data.get('summary', {})
    
    # Calculate actual values from detailed data
    actual_total_deployments = 0
    for service_data in data.get('cluster_deployments', {}).values():
        actual_total_deployments += service_data.get('deployments_last_30_days', 0)
    
    reported_total = summary.get('total_deployments_last_30_days', 0)
    if actual_total_deployments != reported_total:
        errors.append(
            f"Summary total_deployments mismatch: reported {reported_total}, "
            f"actual {actual_total_deployments}"
        )
    
    # Check gap detection consistency
    gaps_reported = summary.get('gaps_detected', False)
    # (Would need to run actual gap analysis to verify)
    
    return len(errors) == 0, errors, warnings
```

---

### 2.5 Cross-Service Validation Rules
Ensure consistency when comparing multiple services.

#### Rule CSV-001: Data Period Alignment
**Requirement:** When comparing services, data periods should be aligned or explicitly documented.

**Alignment Criteria:**
- Same 30-day period for all services (preferred)
- Or explicit documentation of period differences
- Data period start dates should not differ by > 3 days

**Error Conditions:**
- Misaligned data periods without documentation
- Significantly different data collection windows

**Validation Logic:**
```python
def validate_cross_service_period_alignment(data):
    """Validate data period alignment across services."""
    errors = []
    warnings = []
    
    if len(data.get('cluster_deployments', {})) <= 1:
        return True, errors, warnings  # Skip for single-service data
    
    metadata = data.get('metadata', {})
    global_start = metadata.get('data_period_start')
    global_end = metadata.get('data_period_end')
    
    if not global_start or not global_end:
        warnings.append("No global data period defined for multi-service comparison")
        return True, errors, warnings
    
    # All services should use the same global period
    return True, errors, warnings
```

#### Rule CSV-002: Cluster Consistency
**Requirement:** All services in comparison should be from the same cluster or explicitly documented.

**Consistency Criteria:**
- Single cluster for all services (preferred)
- Or explicit cluster documentation for multi-cluster deployments

---

## 3. Validation Error Conditions

### 3.1 Critical Errors (FAIL)
Validation fails immediately if any critical error is detected:

1. **Missing Required Top-Level Structure** (SV-001)
   - Any required top-level key is missing
   - Error message: "Missing required top-level keys: {keys}"

2. **Invalid Metadata Structure** (SV-002)
   - Metadata missing required fields
   - Invalid data types for metadata fields
   - Error message: "Invalid metadata structure: {details}"

3. **Insufficient 30-Day Coverage** (TV-001)
   - Days covered < 28 days
   - Error message: "Insufficient 30-day coverage: {days} days (< 28)"

4. **Invalid Timestamp Format** (TV-002)
   - Any timestamp field fails ISO8601 validation
   - Error message: "Invalid timestamp format for {field}: {timestamp}"

5. **Missing Critical Fields** (DQ-001)
   - Any critical field is missing or null
   - Error message: "Missing or null critical field: {field}"

6. **Numeric Value Violations** (DQ-002)
   - Negative values for non-negative fields
   - Error message: "Negative value for {field}: {value}"

7. **Empty Deployment History** (CV-003)
   - replica_history array is empty
   - Error message: "Empty replica_history - no deployment records found"

### 3.2 Warning Conditions (WARN)
Validation passes but warnings are generated:

1. **Borderline 30-Day Coverage** (TV-001)
   - Days covered 28-29 days
   - Warning: "Borderline coverage: {days} days (< 30)"

2. **Limited Deployment Activity** (CV-001)
   - Distinct deployment days 5-9 days
   - Warning: "Limited deployment activity: {days} days (< 10)"

3. **Significant Gaps Detected** (CV-002)
   - Gaps of 7-14 days detected
   - Warning: "{count} warning gaps detected (> {threshold} days)"

4. **Data Quality Issues** (DQ-003)
   - Invalid enum values
   - Incomplete image tags
   - Warning: "Data quality issue: {details}"

5. **Summary Metrics Inconsistency** (CV-004)
   - Summary metrics don't match calculated values
   - Warning: "Summary metrics inconsistency: {details}"

### 3.3 Informational Messages (INFO)
Provided for context but don't affect validation status:

1. **Validation Success**
   - All validation rules passed
   - Info: "✅ Validation passed: All checks successful"

2. **Coverage Details**
   - Actual days covered and deployment count
   - Info: "Coverage: {days} days, {count} deployments"

3. **Gap Analysis Results**
   - Number and size of gaps found
   - Info: "Gap analysis: {count} gaps, largest: {days} days"

---

## 4. Validation Process Flow

### 4.1 Sequential Validation Steps

1. **Step 1: Structural Validation**
   - Run all SV rules (SV-001, SV-002, SV-003)
   - Fail fast on any structural error
   - Expected time: < 1 second

2. **Step 2: Temporal Validation**
   - Run all TV rules (TV-001, TV-002, TV-003)
   - Calculate 30-day coverage
   - Validate all timestamps
   - Expected time: 1-2 seconds

3. **Step 3: Data Quality Validation**
   - Run all DQ rules (DQ-001, DQ-002, DQ-003)
   - Validate field presence and ranges
   - Check enum values
   - Expected time: 1-2 seconds

4. **Step 4: Completeness Validation**
   - Run all CV rules (CV-001, CV-002, CV-003, CV-004)
   - Detect gaps and analyze coverage
   - Validate summary metrics
   - Expected time: 2-3 seconds

5. **Step 5: Cross-Service Validation**
   - Run CSV rules if multiple services present
   - Validate period alignment
   - Expected time: < 1 second

6. **Step 6: Report Generation**
   - Compile all errors, warnings, and info messages
   - Calculate overall validation status
   - Generate structured report
   - Expected time: < 1 second

**Total Expected Time:** 5-10 seconds for typical deployment data

### 4.2 Validation Status Determination

**Overall Validation Status:**
- **PASS:** No critical errors, warnings allowed
- **WARN:** No critical errors, 1+ warnings present
- **FAIL:** 1+ critical errors present

**Status Calculation:**
```python
def determine_validation_status(all_errors, all_warnings):
    """Determine overall validation status."""
    critical_errors = [e for e in all_errors if e['severity'] == 'CRITICAL']
    
    if critical_errors:
        return "FAIL", critical_errors
    elif all_warnings:
        return "WARN", all_warnings
    else:
        return "PASS", []
```

---

## 5. Implementation Requirements

### 5.1 Validation Function Signature

```python
def validate_30day_completeness(
    data: Dict[str, Any],
    service_name: str = "whisper-stt",
    strict_mode: bool = False
) -> Dict[str, Any]:
    """
    Validate 30-day deployment data completeness.
    
    Args:
        data: Deployment data dictionary matching WhisperSTTDeploymentSchema
        service_name: Primary service to validate (default: "whisper-stt")
        strict_mode: If True, treat warnings as failures (default: False)
    
    Returns:
        Dictionary with validation results:
        {
            "status": "PASS" | "WARN" | "FAIL",
            "errors": List[str],
            "warnings": List[str],
            "info": List[str],
            "metrics": {
                "days_covered": int,
                "distinct_deployment_days": int,
                "total_deployments": int,
                "gaps_detected": List[Dict],
                "coverage_percentage": float
            },
            "validation_timestamp": str (ISO8601)
        }
    """
```

### 5.2 Error Handling Requirements

1. **Graceful Degradation:** Continue validation after non-critical errors to collect all issues
2. **Clear Error Messages:** Each error must specify the rule, field, and condition
3. **Recovery Suggestions:** Where possible, suggest how to fix the error
4. **Logging:** All validation attempts should be logged with timestamp and data source

### 5.3 Performance Requirements

- **Maximum validation time:** 30 seconds for large datasets (>1000 entries)
- **Memory usage:** < 100MB for typical deployment datasets
- **Scalability:** Should handle 100+ services without significant performance degradation

---

## 6. Testing Requirements

### 6.1 Test Cases

**Positive Test Cases (Should Pass):**
1. Valid 30-day deployment data with complete coverage
2. Valid data with acceptable gaps (< 7 days)
3. Valid multi-service data with aligned periods
4. Valid data with minimal deployment activity (stable service)

**Negative Test Cases (Should Fail):**
1. Missing required top-level keys
2. Invalid timestamp formats
3. Insufficient 30-day coverage (< 28 days)
4. Negative replica counts
5. Empty replica history
6. Inconsistent summary metrics

**Boundary Test Cases:**
1. Exactly 30 days coverage (pass)
2. 28-29 days coverage (warn)
3. 7-day gap (warn threshold)
4. 14-day gap (critical threshold)
5. Single deployment record

### 6.2 Validation Test Suite

A comprehensive test suite should include:
- Unit tests for each validation rule
- Integration tests for the complete validation flow
- Performance tests for large datasets
- Regression tests for known edge cases

---

## 7. Maintenance and Updates

### 7.1 Version Control
- Maintain version numbers for this specification
- Document all changes with rationale
- Update implementation code when specification changes

### 7.2 Rule Evolution
- Review rules quarterly for relevance
- Add new rules as deployment patterns evolve
- Deprecate rules that are no longer applicable

### 7.3 Feedback Loop
- Collect validation failure patterns
- Analyze false positives and false negatives
- Refine thresholds and criteria based on operational experience

---

## 8. Appendix: Validation Rule Reference

### Quick Reference Table

| Rule ID | Category | Name | Severity | Error Condition |
|---------|----------|------|----------|------------------|
| SV-001 | Structural | Top-Level Structure | CRITICAL | Missing required keys |
| SV-002 | Structural | Metadata Structure | CRITICAL | Invalid/missing metadata |
| SV-003 | Structural | Service-Specific Structure | CRITICAL | Missing service fields |
| TV-001 | Temporal | 30-Day Coverage | CRITICAL | Days < 28 |
| TV-002 | Temporal | Timestamp Validity | CRITICAL | Invalid ISO8601 |
| TV-003 | Temporal | Timestamp Consistency | CRITICAL | Inverted timestamps |
| DQ-001 | Data Quality | Required Fields Presence | CRITICAL | Missing/null fields |
| DQ-002 | Data Quality | Numeric Field Ranges | CRITICAL | Negative values |
| DQ-003 | Data Quality | Enum Field Validity | WARNING | Invalid enum values |
| CV-001 | Completeness | Minimum Deployment Days | WARNING | < 10 distinct days |
| CV-002 | Completeness | Gap Detection | CRITICAL/WARNING | Gaps > 14/7 days |
| CV-003 | Completeness | Replica History Completeness | CRITICAL | Empty history |
| CV-004 | Completeness | Summary Metrics Consistency | WARNING | Metric mismatches |
| CSV-001 | Cross-Service | Data Period Alignment | WARNING | Misaligned periods |

---

## 9. References and Related Documentation

- **Schema Definition:** `whisper_stt_deployment_schema.py`
- **Existing Validation:** `validate_30day_deployment_coverage.py`
- **Deployment Data Files:** `docs/deployment-data-files-2026-08-06.md`
- **Test Cases:** `test_required_fields_validation.py`

---

**Document Status:** Complete  
**Last Updated:** 2026-08-07  
**Next Review:** 2026-11-07 (quarterly review)  
**Approval Status:** Ready for implementation