# Deployment Data Validation Summary

**Generated:** 2026-08-07  
**Validation Tool:** `scripts/validate_deployment_data.py`  
**Purpose:** Load and validate deployment JSON files against expected schema

## Overview

This document summarizes the validation results for deployment data files collected for the aide-de-camp project. The validation ensures data quality and completeness for deployment analysis.

## Files Validated

### 1. pbx-web-deployment-data-30days.json
- **Location:** `docs/research/deployment-data/pbx-web-deployment-data-30days.json`
- **Records:** 5 deployment events
- **Status:** ✅ All records valid (100%)
- **Time Period:** 2026-07-13 to 2026-07-28 (15 days covered)

### 2. whisper-stt-deployment-data-30days.json
- **Location:** `docs/research/deployment-data/whisper-stt-deployment-data-30days.json`
- **Records:** 5 ReplicaSet records
- **Status:** ✅ All records valid (100%)
- **Time Period:** Covers last 30 days with active deployments

### 3. deployment-events-30days-comprehensive.json
- **Location:** `docs/research/deployment-data/deployment-events-30days-comprehensive.json`
- **Records:** 9 deployment events
- **Status:** ✅ All records valid (100%)
- **Time Period:** 30 days comprehensive view

## Validation Results

### Overall Statistics
- **Total Files Checked:** 3
- **Files Valid:** 3 (100%)
- **Total Records:** 19
- **Valid Records:** 19 (100%)
- **Invalid Records:** 0 (0%)
- **Success Rate:** 100%

### Schema Requirements

The validation script checks for the following required fields:

#### Base Requirements (All Records)
- **timestamp**: ISO 8601 format deployment timestamp
- **outcome/status**: Deployment outcome (success, failure, rolled_back, partial, unknown, active, inactive)

#### Failure-Specific Requirements (When outcome = failure/partial)
- **error_type**: Type of failure encountered
- **phase**: Deployment phase where failure occurred
- **error_message**: Detailed error description

### Field Mapping Flexibility

The validation script supports multiple field name variations:

- **timestamp**: timestamp, date, created, created_at, time, datetime
- **outcome**: outcome, status, result, state
- **error_type**: error_type, error, failure_type
- **phase**: phase, stage, deployment_phase
- **error_message**: error_message, message, error_message, failure_reason

## Validation Script Features

### Error Detection
- ✅ Missing files detection
- ✅ Malformed JSON detection
- ✅ Missing required fields
- ✅ Invalid timestamp format validation
- ✅ Missing failure-specific fields

### Data Quality Checks
- Timestamp format validation (ISO 8601)
- Outcome value validation against known values
- Field presence and null value checks
- Type validation (string vs other types)

### Summary Reporting
- File-by-file breakdown
- Record counts and validity rates
- Detailed error and warning lists
- Exit codes for automation (0 = success, 1 = errors found)

## Usage Examples

### Basic Usage
```bash
python scripts/validate_deployment_data.py path/to/file1.json path/to/file2.json
```

### Quiet Mode
```bash
python scripts/validate_deployment_data.py -q path/to/file.json
```

### Multiple Files
```bash
python scripts/validate_deployment_data.py \
    docs/research/deployment-data/pbx-web-deployment-data-30days.json \
    docs/research/deployment-data/whisper-stt-deployment-data-30days.json
```

## Test Results

### Valid Data Test
```bash
$ python scripts/validate_deployment_data.py \
    docs/research/deployment-data/pbx-web-deployment-data-30days.json \
    docs/research/deployment-data/whisper-stt-deployment-data-30days.json

✅ Files Processed: 2
✅ Total Records: 10
✅ Valid Records: 10 (100%)
✅ Success Rate: 100.0%
```

### Error Detection Test
```bash
$ python scripts/validate_deployment_data.py test_deployment_bad.json

❌ Records: 3, Valid: 1, Invalid: 2
❌ Success Rate: 33.3%
❌ Errors: 2 (Missing required failure fields)
⚠️  Warnings: 1 (Invalid timestamp format)
```

### Missing File Test
```bash
$ python scripts/validate_deployment_data.py nonexistent.json

❌ Files Missing: 1
❌ Errors: 1 (File not found)
```

## Conclusion

All deployment data files have been successfully validated and meet the required schema standards. The data is ready for analysis and reporting.

### Key Findings
1. **Data Quality**: 100% validation success rate across all files
2. **Schema Compliance**: All required fields present and properly formatted
3. **Coverage**: 19 total deployment records across 3 services
4. **Reliability**: No malformed JSON or missing critical data

### Next Steps
- ✅ Use validated data for deployment analysis
- ✅ Generate deployment metrics and reports
- ✅ Feed data into deployment pattern analysis
- ✅ Monitor ongoing deployment data quality