# Validation Failure Scenarios Catalog

Complete catalog of all validation failure types in the aide-de-camp codebase, with code locations and triggering conditions.

**Generated:** 2026-08-07  
**Scope:** All validation modules across the codebase

---

## Table of Contents

1. [JSON Well-formedness Validation](#1-json-wellformedness-validation)
2. [30-Day Completeness Validation](#2-30-day-completeness-validation)
3. [Required Fields Validation](#3-required-fields-validation)
4. [Data Types Validation](#4-data-types-validation)
5. [Business Constraints Validation](#5-business-constraints-validation)
6. [Integration Validation](#6-integration-validation)
7. [Deployment Completeness Validation](#7-deployment-completeness-validation)
8. [Deployment Schema Validation](#8-deployment-schema-validation)
9. [API Request Validation](#9-api-request-validation)
10. [Bead Validation](#10-bead-validation)
11. [Manifest Template Validation](#11-manifest-template-validation)
12. [Pydantic Schema Validation](#12-pydantic-schema-validation)

---

## 1. JSON Well-formedness Validation

**Module:** `src/validation/completeness.py`  
**Functions:** `validate_json_wellformedness()`, `validate_json_file_wellformedness()`

### Failure Types

#### 1.1 Non-Serializable Data
- **Location:** `src/validation/completeness.py:45-56`
- **Detection:** `json.dumps()` raises `TypeError`
- **Error Message:** `"Data is not well-formed JSON: <error details>"`
- **Triggering Conditions:** Data contains non-JSON-serializable objects (datetime, custom classes, etc.)

#### 1.2 Parse Failure
- **Location:** `src/validation/completeness.py:49-50`
- **Detection:** `json.loads()` raises `ValueError`
- **Error Message:** `"Data is not well-formed JSON: <error details>"`
- **Triggering Conditions:** Serialized JSON cannot be deserialized (malformed structure)

#### 1.3 File Not Found
- **Location:** `src/validation/completeness.py:75-76`
- **Detection:** File existence check fails
- **Error Message:** `"File does not exist: <file_path>"`
- **Triggering Conditions:** Input file path does not exist on filesystem

#### 1.4 Invalid JSON in File
- **Location:** `src/validation/completeness.py:82-83`
- **Detection:** `json.load()` raises `JSONDecodeError`
- **Error Message:** `"Invalid JSON in file <file_path>: <decode error>"`
- **Triggering Conditions:** File contains malformed JSON syntax

#### 1.5 File Read Error
- **Location:** `src/validation/completeness.py:84-85`
- **Detection:** File open raises generic exception
- **Error Message:** `"Error reading file <file_path>: <error details>"`
- **Triggering Conditions:** Permission errors, I/O errors, encoding issues

---

## 2. 30-Day Completeness Validation

**Module:** `src/validation/completeness.py`  
**Function:** `validate_30day_completeness()`

### Failure Types

#### 2.1 Date Range Determination Failure
- **Location:** `src/validation/completeness.py:270-271`
- **Detection:** Start/end dates remain None after extraction
- **Error Message:** `"Cannot determine date range from data"`
- **Triggering Conditions:** Metadata lacks `time_period.start`/`time_period.end` or `report_metadata.time_range_start`/`time_range_end`

#### 2.2 Invalid Date Format in Metadata
- **Location:** `src/validation/completeness.py:257-258, 266-267`
- **Detection:** `parse_date_string()` raises `ValueError`
- **Error Message:** `"Invalid date in time_period: <error>"` or `"Invalid date in report_metadata: <error>"`
- **Triggering Conditions:** Date strings don't match ISO 8601 format

#### 2.3 Incorrect Day Count
- **Location:** `src/validation/completeness.py:284-285`
- **Detection:** Expected date count < 29 or > 31
- **Error Message:** `"Date range covers {count} days, expected ~30 days (from {start} to {end})"`
- **Triggering Conditions:** Date range is not approximately 30 days

#### 2.4 No Dates Found
- **Location:** `src/validation/completeness.py:290-291`
- **Detection:** `extract_dates_from_data()` returns empty set
- **Error Message:** `"No dates found in deployment data"`
- **Triggering Conditions:** Data lacks `deployment_events_last_30_days[].date` or `deployment_history_30_days.replicasets[].created` fields

#### 2.5 Missing Dates (Gaps)
- **Location:** `src/validation/completeness.py:294-297`
- **Detection:** `expected_dates - actual_dates` is non-empty
- **Error Message:** `"Missing data for {count} day(s): {date_list}"`
- **Triggering Conditions:** Date sequence has gaps (missing deployment data for specific dates)

#### 2.6 Extra Dates (Out of Range)
- **Location:** `src/validation/completeness.py:300-303`
- **Detection:** `actual_dates - expected_dates` is non-empty
- **Error Message:** `"Found {count} date(s) outside expected range: {date_list}"`
- **Triggering Conditions:** Data contains dates outside the expected 30-day window

#### 2.7 Non-Chronological Sequence
- **Location:** `src/validation/completeness.py:315-316`
- **Detection:** Date gap != 1 day
- **Error Message:** `"Non-chronological dates: {prev} → {curr} (gap of {days} days)"`
- **Triggering Conditions:** Dates are not consecutive (indicates data ordering issue)

---

## 3. Required Fields Validation

**Module:** `src/validation/deployment_data.py`  
**Function:** `validate_required_fields()`

### Failure Types

#### 3.1 Not a Dictionary
- **Location:** `src/validation/deployment_data.py:290-291`
- **Detection:** `isinstance(data, dict)` returns False
- **Error Message:** `"Data must be a dictionary, got {type_name}"`
- **Triggering Conditions:** Input is not a dictionary (e.g., list, string, None)

#### 3.2 Services Not a Dictionary
- **Location:** `src/validation/deployment_data.py:296-297`
- **Detection:** Services field exists but is not a dict
- **Error Message:** `"'services' must be a dictionary, got {type_name}"`
- **Triggering Conditions:** `data["services"]` is not a dict type

#### 3.3 Service Data Not a Dictionary
- **Location:** `src/validation/deployment_data.py:301-302`
- **Detection:** Service value is not a dict
- **Error Message:** `"Service '{service_name}' data must be a dictionary, got {type_name}"`
- **Triggering Conditions:** Individual service data is not a dict

#### 3.4 Missing Single Required Field
- **Location:** `src/validation/deployment_data.py:339-340`
- **Detection:** Exactly one field missing from DEPLOYMENT_DATA_SCHEMA
- **Error Message:** `"Missing required field: {field_name}"`
- **Triggering Conditions:** Single required field absent from data

#### 3.5 Missing Multiple Required Fields
- **Location:** `src/validation/deployment_data.py:342-343`
- **Detection:** Multiple fields missing from DEPLOYMENT_DATA_SCHEMA
- **Error Message:** `"Missing required fields: {field_list}"`
- **Triggering Conditions:** Two or more required fields absent from data

---

## 4. Data Types Validation

**Module:** `src/validation/deployment_data.py`  
**Function:** `validate_data_types()`

### Failure Types

#### 4.1 Schema Not a Dictionary
- **Location:** `src/validation/deployment_data.py:386-387`
- **Detection:** `isinstance(schema, dict)` returns False
- **Error Message:** `"Schema must be a dictionary, got {type_name}"`
- **Triggering Conditions:** Schema parameter is not a dict

#### 4.2 Numeric Type Mismatch (Float Fields)
- **Location:** `src/validation/deployment_data.py:400-401`
- **Detection:** Value is not int or float
- **Error Message:** `"{field_name} must be numeric, got {type_name}"`
- **Triggering Conditions:** Float field contains non-numeric value

#### 4.3 List Type Mismatch
- **Location:** `src/validation/deployment_data.py:405-406`
- **Detection:** Value is not a list
- **Error Message:** `"{field_name} must be a list, got {type_name}"`
- **Triggering Conditions:** List field contains non-list value

#### 4.4 String Type Mismatch
- **Location:** `src/validation/deployment_data.py:410-411`
- **Detection:** Value is not a string
- **Error Message:** `"{field_name} must be str, got {type_name}"`
- **Triggering Conditions:** String field contains non-string value

#### 4.5 Invalid Timestamp in String Field
- **Location:** `src/validation/deployment_data.py:415-416`
- **Detection:** `validate_timestamp()` returns False
- **Error Message:** `"{field_name} contains invalid date string: {value}"`
- **Triggering Conditions:** Timestamp field has non-ISO8601 date string

#### 4.6 Integer Type Mismatch
- **Location:** `src/validation/deployment_data.py:420-421`
- **Detection:** Value is not an integer
- **Error Message:** `"{field_name} must be int, got {type_name}"`
- **Triggering Conditions:** Integer field contains non-integer value

#### 4.7 Custom Type Mismatch
- **Location:** `src/validation/deployment_data.py:425-426`
- **Detection:** Value doesn't match expected type
- **Error Message:** `"{field_name} must be {expected_type}, got {actual_type}"`
- **Triggering Conditions:** Field value type doesn't match schema expectation

---

## 5. Business Constraints Validation

**Module:** `src/validation/deployment_data.py`  
**Function:** `validate_deployment_record()`

### Failure Types

#### 5.1 Not a Dictionary
- **Location:** `src/validation/deployment_data.py:79-80`
- **Detection:** `isinstance(data, dict)` returns False
- **Error Message:** `"Data must be a dictionary, got {type_name}"`
- **Triggering Conditions:** Input is not a dictionary

#### 5.2 Missing Required Fields
- **Location:** `src/validation/deployment_data.py:83-89`
- **Detection:** Field not in DEPLOYMENT_DATA_SCHEMA
- **Error Message:** `"Missing required fields: {field_list}"`
- **Triggering Conditions:** One or more required fields absent

#### 5.3 Type Errors (Multiple Fields)
- **Location:** `src/validation/deployment_data.py:91-108`
- **Detection:** Type mismatch for any field
- **Error Message:** `"; "` joined list of type errors
- **Triggering Conditions:** Any field value doesn't match expected type

#### 5.4 Negative Numeric Field
- **Location:** `src/validation/deployment_data.py:118-119`
- **Detection:** Numeric field value < 0
- **Error Message:** `"{field_name} must be non-negative, got {value}"`
- **Triggering Conditions:** Non-negative field contains negative value

#### 5.5 Invalid Timestamp
- **Location:** `src/validation/deployment_data.py:125-126`
- **Detection:** `validate_timestamp()` returns False
- **Error Message:** `"{field_name} contains invalid timestamp: {value}"`
- **Triggering Conditions:** Timestamp field has empty or non-ISO8601 string

#### 5.6 Deployment Count Mismatch
- **Location:** `src/validation/deployment_data.py:134-135`
- **Detection:** `successful + failed != total`
- **Error Message:** `"successful_deployments ({successful}) + failed_deployments ({failed}) must equal total_deployments ({total})"`
- **Triggering Conditions:** Deployment counts don't sum correctly

#### 5.7 Rate Sum Error (Non-Zero Total)
- **Location:** `src/validation/deployment_data.py:146-147`
- **Detection:** `abs(success_rate + failure_rate - 100.0) > 0.1`
- **Error Message:** `"success_rate ({success_rate}) + failure_rate ({failure_rate}) should equal 100.0"`
- **Triggering Conditions:** Success/failure rates don't sum to 100%

#### 5.8 Rate Sum Error (Zero Total)
- **Location:** `src/validation/deployment_data.py:144-145`
- **Detection:** `total == 0` but rates not both 0.0
- **Error Message:** `"When total_deployments is 0, success_rate and failure_rate must both be 0.0, got {success_rate} and {failure_rate}"`
- **Triggering Conditions:** Zero deployments but non-zero rates

---

## 6. Integration Validation

**Module:** `src/validation/integration.py`  
**Function:** `validate_all()`

### Failure Types

#### 6.1 No Input Provided
- **Location:** `src/validation/integration.py:89-90`
- **Detection:** Both file_path and data are None
- **Error Message:** `"Either file_path or data must be provided"`
- **Triggering Conditions:** Neither file_path nor data parameter provided

#### 6.2 File Not Found
- **Location:** `src/validation/integration.py:97-98`
- **Detection:** File open raises FileNotFoundError
- **Error Message:** `"File not found: {file_path}"`
- **Triggering Conditions:** Specified file doesn't exist

#### 6.3 JSON Decode Error
- **Location:** `src/validation/integration.py:99-100`
- **Detection:** `json.load()` raises JSONDecodeError
- **Error Message:** `"Invalid JSON in file {file_path}: {error}"`
- **Triggering Conditions:** File contains malformed JSON

#### 6.4 Not a Dictionary
- **Location:** `src/validation/integration.py:107-108`
- **Detection:** `isinstance(data, dict)` returns False
- **Error Message:** `"Data must be a dictionary, got {type_name}"`
- **Triggering Conditions:** Parsed data is not a dictionary

#### 6.5 JSON Validation Failure
- **Location:** `src/validation/integration.py:115-118`
- **Detection:** `validate_json_wellformedness()` returns False
- **Error Message:** `"JSON validation: {error}"`
- **Triggering Conditions:** Data is not well-formed JSON

#### 6.6 Required Fields Failure
- **Location:** `src/validation/integration.py:121-123`
- **Detection:** `validate_required_fields()` returns False
- **Error Message:** `"Required fields validation: {error}"`
- **Triggering Conditions:** Required fields missing from data

#### 6.7 Data Types Failure
- **Location:** `src/validation/integration.py:126-128`
- **Detection:** `validate_data_types()` returns False
- **Error Message:** `"Data types validation: {error}"`
- **Triggering Conditions:** Field data types don't match schema

#### 6.8 Completeness Failure
- **Location:** `src/validation/integration.py:147-149`
- **Detection:** `validate_completeness()` returns False
- **Error Message:** `"Completeness validation: {error}"`
- **Triggering Conditions:** Deployment events don't cover 30 days correctly

---

## 7. Deployment Completeness Validation

**Module:** `src/validation/validate_completeness.py`  
**Function:** `validate_completeness()`

### Failure Types

#### 7.1 Not a List
- **Location:** `src/validation/validate_completeness.py:26-27`
- **Detection:** `isinstance(data, list)` returns False
- **Error Message:** `"Data must be a list"`
- **Triggering Conditions:** Input data is not a list

#### 7.2 Entry Count Mismatch
- **Location:** `src/validation/validate_completeness.py:30-31`
- **Detection:** `len(data) != 30`
- **Error Message:** `"Expected 30 deployment entries, found {count}"`
- **Triggering Conditions:** List doesn't contain exactly 30 entries

#### 7.3 Entry Not a Dictionary
- **Location:** `src/validation/validate_completeness.py:38-39`
- **Detection:** `isinstance(entry, dict)` returns False
- **Error Message:** `"Entry {index} is not a dictionary"`
- **Triggering Conditions:** List element is not a dict

#### 7.4 Missing Timestamp Field
- **Location:** `src/validation/validate_completeness.py:48`
- **Detection:** Neither "timestamp" nor "creationTimestamp" in entry
- **Error Message:** `"Entry {index} missing timestamp field"`
- **Triggering Conditions:** Entry lacks timestamp field

#### 7.5 Empty Timestamp
- **Location:** `src/validation/validate_completeness.py:51-52`
- **Detection:** Timestamp value is falsy
- **Error Message:** `"Entry {index} has empty timestamp"`
- **Triggering Conditions:** Timestamp field is empty/None

#### 7.6 Timestamp Not a String
- **Location:** `src/validation/validate_completeness.py:60-61`
- **Detection:** `isinstance(ts_value, str)` returns False
- **Error Message:** `"Entry {index} timestamp must be a string"`
- **Triggering Conditions:** Timestamp value is not a string

#### 7.7 Invalid Timestamp Format
- **Location:** `src/validation/validate_completeness.py:71-72`
- **Detection:** `datetime.fromisoformat()` raises exception
- **Error Message:** `"Entry {index} has invalid timestamp: {error}"`
- **Triggering Conditions:** Timestamp string doesn't match ISO 8601 format

#### 7.8 Duplicate Date
- **Location:** `src/validation/validate_completeness.py:67-68`
- **Detection:** Date already in seen_dates set
- **Error Message:** `"Duplicate date found: {date}"`
- **Triggering Conditions:** Two entries have the same date

#### 7.9 Date Gap Detected
- **Location:** `src/validation/validate_completeness.py:83-85`
- **Detection:** `next_date != expected_next_date`
- **Error Message:** `"Date gap detected: {current} to {next} ({days} days, expected 1)"`
- **Triggering Conditions:** Consecutive dates are not 1 day apart

---

## 8. Deployment Schema Validation

**Module:** `src/validation/deployment_validator.py`  
**Functions:** Multiple validation functions

### Failure Types

#### 8.1 Input Not a Dictionary
- **Location:** `src/validation/deployment_validator.py:356-357`
- **Detection:** `isinstance(data, dict)` returns False
- **Error Message:** `"Input data must be a dictionary, got {type_name}"`
- **Triggering Conditions:** Input data is not a dict

#### 8.2 Missing Top-Level Field
- **Location:** `src/validation/deployment_validator.py:362-364`
- **Detection:** Required field not in data
- **Error Message:** `"Missing required top-level field: {field_name}"`
- **Triggering Conditions:** One of REQUIRED_TOP_LEVEL_FIELDS absent

#### 8.3 Metadata Not a Dictionary
- **Location:** `src/validation/deployment_validator.py:371-372`
- **Detection:** Metadata field exists but not a dict
- **Error Message:** `"metadata must be a dictionary"`
- **Triggering Conditions:** `data["metadata"]` is not dict type

#### 8.4 Missing Metadata Field
- **Location:** `src/validation/deployment_validator.py:195-197`
- **Detection:** Field not in metadata dict
- **Error Message:** `"Missing required metadata field: {field_name}"`
- **Triggering Conditions:** One of REQUIRED_METADATA_FIELDS absent

#### 8.5 Invalid Timestamp in Metadata
- **Location:** `src/validation/deployment_validator.py:201-203, 206-208, 211-213`
- **Detection:** `validate_timestamp()` returns False
- **Error Message:** Validation error from timestamp function
- **Triggering Conditions:** Metadata timestamp field has invalid format

#### 8.6 Services Not a List
- **Location:** `src/validation/deployment_validator.py:216-217`
- **Detection:** `isinstance(metadata["services"], list)` returns False
- **Error Message:** `"metadata.services must be a list"`
- **Triggering Conditions:** Services field is not a list

#### 8.7 Clusters Not a List
- **Location:** `src/validation/deployment_validator.py:219-220`
- **Detection:** Clusters field is not a list
- **Error Message:** `"metadata.clusters must be a list"`
- **Triggering Conditions:** Clusters field is not a list

#### 8.8 Data Sources Not a List
- **Location:** `src/validation/deployment_validator.py:222-223`
- **Detection:** Data sources field is not a list
- **Error Message:** `"metadata.data_sources must be a list"`
- **Triggering Conditions:** Data sources field is not a list

#### 8.9 Empty Cluster Deployments
- **Location:** `src/validation/deployment_validator.py:241-243`
- **Detection:** `cluster_deployments` is empty or None
- **Error Message:** `"cluster_deployments cannot be empty"`
- **Triggering Conditions:** No deployment data provided

#### 8.10 Service Data Not a Dictionary
- **Location:** `src/validation/deployment_validator.py:246-247`
- **Detection:** Service value is not a dict
- **Error Message:** `"cluster_deployments.{service_name} must be a dictionary"`
- **Triggering Conditions:** Individual service data is not a dict

#### 8.11 Missing Cluster Deployment Field
- **Location:** `src/validation/deployment_validator.py:251-253`
- **Detection:** Required field not in service data
- **Error Message:** `"Missing required field in cluster_deployments.{service_name}: {field_name}"`
- **Triggering Conditions:** One of REQUIRED_CLUSTER_DEPLOYMENT_FIELDS absent

#### 8.12 Cluster Deployments Not a Dictionary
- **Location:** `src/validation/deployment_validator.py:379-380`
- **Detection:** Field exists but not a dict
- **Error Message:** `"cluster_deployments must be a dictionary"`
- **Triggering Conditions:** `data["cluster_deployments"]` is not dict

#### 8.13 Summary Not a Dictionary
- **Location:** `src/validation/deployment_validator.py:387-388`
- **Detection:** Summary field exists but not a dict
- **Error Message:** `"summary must be a dictionary"`
- **Triggering Conditions:** `data["summary"]` is not dict

#### 8.14 Argo Workflows Not a Dictionary
- **Location:** `src/validation/deployment_validator.py:391-392`
- **Detection:** Field is not a dict
- **Error Message:** `"argo_workflows must be a dictionary"`
- **Triggering Conditions:** Argo workflows field is not dict

#### 8.15 ArgoCD Not a Dictionary
- **Location:** `src/validation/deployment_validator.py:394-396`
- **Detection:** Field is not a dict
- **Error Message:** `"argo_cd must be a dictionary"`
- **Triggering Conditions:** ArgoCD field is not dict

#### 8.16 Missing Summary Field
- **Location:** `src/validation/deployment_validator.py:312-314`
- **Detection:** Field not in summary dict
- **Error Message:** `"Missing required summary field: {field_name}"`
- **Triggering Conditions:** One of REQUIRED_SUMMARY_FIELDS absent

#### 8.17 Summary Field Type Mismatch
- **Location:** `src/validation/deployment_validator.py:317-336`
- **Detection:** Field value type doesn't match expectation
- **Error Message:** `"summary.{field_name} must be {expected_type}"`
- **Triggering Conditions:** Summary field has wrong data type

#### 8.18 Replica History Entry Not a Dictionary
- **Location:** `src/validation/deployment_validator.py:273-274`
- **Detection:** History entry is not a dict
- **Error Message:** `"cluster_deployments.{service_name}.replica_history[{index}] must be a dictionary"`
- **Triggering Conditions:** Replica history entry is not dict

#### 8.19 Missing Replica History Field
- **Location:** `src/validation/deployment_validator.py:277-279`
- **Detection:** Field not in history entry
- **Error Message:** `"Missing required field in cluster_deployments.{service_name}.replica_history[{index}]: {field_name}"`
- **Triggering Conditions:** One of REQUIRED_REPLICA_HISTORY_FIELDS absent

---

## 9. API Request Validation

**Module:** `src/api/models.py`  
**Model:** `DispatchRequest`

### Failure Types

#### 9.1 Utterance Not a String
- **Location:** `src/api/models.py:75-76`
- **Detection:** `@field_validator` checks type
- **Error Message:** `"utterance must be a string"`
- **Triggering Conditions:** Utterance field is not a string type

#### 9.2 Empty Utterance
- **Location:** `src/api/models.py:78-79`
- **Detection:** `stripped` string is empty
- **Error Message:** `"utterance must be a non-empty string"`
- **Triggering Conditions:** Utterance is whitespace-only or empty

#### 9.3 Session ID Not a String
- **Location:** `src/api/models.py:97-98`
- **Detection:** `@field_validator` checks type
- **Error Message:** `"session_id must be a string"`
- **Triggering Conditions:** Session ID field is not a string type

#### 9.4 Empty Session ID
- **Location:** `src/api/models.py:100-101`
- **Detection:** `stripped` string is empty
- **Error Message:** `"session_id must be a non-empty string"`
- **Triggering Conditions:** Session ID is whitespace-only or empty

#### 9.5 Surface ID Not a String
- **Location:** `src/api/models.py:119-120`
- **Detection:** `@field_validator` checks type
- **Error Message:** `"surface_id must be a string"`
- **Triggering Conditions:** Surface ID field is not a string type

#### 9.6 Empty Surface ID
- **Location:** `src/api/models.py:122-123`
- **Detection:** `stripped` string is empty
- **Error Message:** `"surface_id must be a non-empty string"`
- **Triggering Conditions:** Surface ID is whitespace-only or empty

#### 9.7 Utterance ID Not a String (When Provided)
- **Location:** `src/api/models.py:142-143`
- **Detection:** `@field_validator` checks type
- **Error Message:** `"utterance_id must be a string"`
- **Triggering Conditions:** Utterance ID provided but not a string

#### 9.8 Empty Utterance ID (When Provided)
- **Location:** `src/api/models.py:144-145`
- **Detection:** `stripped` string is empty
- **Error Message:** `"utterance_id must be a non-empty string if provided"`
- **Triggering Conditions:** Utterance ID provided but is empty/whitespace

---

## 10. Bead Validation

**Module:** `src/bead_validation/validator.py`  
**Class:** `BeadValidator`

### Failure Types

#### 10.1 Forbidden kubectl Verb
- **Location:** `src/bead_validation/validator.py:257-274`
- **Detection:** Regex matches forbidden kubectl verb
- **Error Message:** `"Direct kubectl '{verb}' command detected. Mutations must use GitOps (declarative-config) approach."`
- **Triggering Conditions:** Bead body contains `kubectl <forbidden_verb>` pattern

#### 10.2 Missing GitOps Pattern (Mutation)
- **Location:** `src/bead_validation/validator.py:285-297`
- **Detection:** No GitOps pattern found in mutation bead
- **Error Message:** `"Mutation operation detected but no GitOps pattern found. Cluster changes must go through declarative-config (jedarden/declarative-config), not direct kubectl."`
- **Triggering Conditions:** Bead mutates but lacks GitOps references

#### 10.3 Missing Scoping (kubectl/cluster Operation)
- **Location:** `src/bead_validation/validator.py:315-322`
- **Detection:** No scoping pattern in cluster-related bead
- **Error Message:** `"Command lacks proper scoping. Must include cluster, namespace, and/or resource scoping (e.g., 'namespace: production', 'cluster: ardenone-manager')."`
- **Triggering Conditions:** Bead mentions kubectl/namespace/cluster but lacks scoping

#### 10.4 Action Bead Requires Approval
- **Location:** `src/bead_validation/validator.py:198-205`
- **Detection:** Bead type is ACTION
- **Result:** `ValidationResult.requires_approval()`
- **Message:** `"Action-type beads require explicit user approval"`
- **Triggering Conditions:** Bead type is "action"

#### 10.5 Self-Modification Requires Approval
- **Location:** `src/bead_validation/validator.py:208-213`
- **Detection:** Bead type is SELF_MODIFICATION
- **Result:** `ValidationResult.requires_approval()`
- **Message:** `"Self_modification beads require explicit user approval"`
- **Triggering Conditions:** Bead type is "self_modification"

#### 10.6 Monitoring Config Requires Approval
- **Location:** `src/bead_validation/validator.py:208-213`
- **Detection:** Bead type is MONITORING_CONFIG
- **Result:** `ValidationResult.requires_approval()`
- **Message:** `"Monitoring_config beads require explicit user approval"`
- **Triggering Conditions:** Bead type is "monitoring_config"

---

## 11. Manifest Template Validation

**Module:** `src/action/manifest_template.py`  
**Classes:** `TemplateField`, `ManifestTemplateEngine`

### Failure Types

#### 11.1 Invalid Field Path (No Leading Slash)
- **Location:** `src/action/manifest_template.py:57-58`
- **Detection:** `path.startswith("/")` returns False
- **Error Message:** `"Invalid field path '{path}': must start with /"`
- **Triggering Conditions:** JSON Pointer path doesn't start with `/`

#### 11.2 Forbidden Pattern in Path
- **Location:** `src/action/manifest_template.py:63-66`
- **Detection:** Path contains `*`, `..`, `//`, newline, etc.
- **Error Message:** `"Invalid field path '{path}': contains forbidden pattern '{pattern}'"`
- **Triggering Conditions:** Path includes security-sensitive patterns

#### 11.3 Invalid Path Component
- **Location:** `src/action/manifest_template.py:73-76`
- **Detection:** Path component is not alphanumeric or digit
- **Error Message:** `"Invalid field path component '{part}' in '{path}': must be alphanumeric or digits"`
- **Triggering Conditions:** Path component has special characters

#### 11.4 Non-Whitelisted Path
- **Location:** `src/action/manifest_template.py` (security check)
- **Detection:** Path doesn't match `ALLOWED_PATH_PREFIXES`
- **Error Message:** Path not in allowed list
- **Triggering Conditions:** Attempt to modify field outside approved paths

#### 11.5 Forbidden Path
- **Location:** `src/action/manifest_template.py` (security check)
- **Detection:** Path matches `FORBIDDEN_PATHS`
- **Error Message:** Attempt to modify security-critical field
- **Triggering Conditions:** Attempt to modify metadata, status, kind, apiVersion

---

## 12. Pydantic Schema Validation

**Module:** `src/schemas/whisper_stt_deployment.py`  
**Model:** `WhisperSTTDeploymentData`

### Failure Types

#### 12.1 Schema Validation Failure
- **Location:** `src/schemas/whisper_stt_deployment.py:374-378`
- **Detection:** Pydantic model construction raises exception
- **Error Message:** `"Schema validation failed: {error}"`
- **Triggering Conditions:** Data doesn't match Pydantic schema structure

#### 12.2 Enum Validation Failure
- **Location:** Various enum fields (EventType, EventOutcome, HealthStatus, etc.)
- **Detection:** Pydantic enum validation
- **Error Message:** Enum value not in allowed set
- **Triggering Conditions:** Field value doesn't match enum options

#### 12.3 Field Constraint Violation
- **Location:** Fields with `ge`, `le` constraints
- **Detection:** Pydantic constraint validators
- **Error Message:** Value outside allowed range
- **Triggering Conditions:** Numeric value violates constraints (e.g., success_rate not 0-1)

#### 12.4 DateTime Validation Failure
- **Location:** All datetime fields
- **Detection:** Pydantic datetime parsing
- **Error Message:** Invalid datetime format
- **Triggering Conditions:** String cannot be parsed as ISO 8601 datetime

---

## Summary Statistics

- **Total Validation Modules:** 8
- **Total Failure Types:** 85+
- **Most Complex Module:** Deployment Schema Validation (18+ failure types)
- **Most Critical Module:** Bead Validation (security-critical GitOps enforcement)

## Validation Flow

```
User Input
    ↓
API Request Validation (DispatchRequest)
    ↓
Integration Validation (validate_all)
    ↓
├── JSON Well-formedness
├── Required Fields
├── Data Types
└── Completeness
    ↓
Business Logic Validation
    ↓
Bead Validation (for escalate operations)
    ↓
Manifest Template Validation (for GitOps operations)
```

## Error Severity Levels

- **ERROR:** Validation blocks operation (data rejected)
- **WARNING:** Operation continues but notes issue
- **APPROVAL REQUIRED:** Operation awaits user confirmation

## Testing Recommendations

For each failure type, create test cases that:
1. Provide valid data (baseline)
2. Trigger the specific failure condition
3. Verify error message format
4. Check error propagation through validation chain
5. Test recovery/correction scenarios
