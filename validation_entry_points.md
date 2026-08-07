# Validation Entry Points - aide-de-camp

This document maps all validation functions, modules, and endpoints that trigger validation in the aide-de-camp codebase.

## Overview

Validation in aide-de-camp occurs at multiple layers:
1. **API Request Validation** - Automatic Pydantic model validation on FastAPI endpoints
2. **Deployment Data Validation** - Manual validation functions for deployment records
3. **Schema Validation** - Field validators within Pydantic models
4. **Registry/Action Validation** - Workflow and project registry validation
5. **Completeness Validation** - JSON well-formedness and data completeness checks
6. **Test/Development Validation** - Test fixtures and validation helpers

---

## 1. API Request Validation (Automatic Pydantic)

These validations are triggered automatically when requests are made to FastAPI endpoints. No manual invocation needed.

### Core API Models (`src/api/models.py`)

#### `DispatchRequest`
**File:** `src/api/models.py:17-163`

**Triggers:**
- `POST /dispatch` endpoint

**Validates:**
- `utterance` (str, required, non-empty)
- `session_id` (str, required, non-empty)
- `surface_id` (str, required, non-empty)
- `utterance_id` (str, optional, non-empty if provided)

**Field Validators:**
- `utterance_must_be_non_empty()` - Ensures utterance is a non-empty string
- `session_id_must_be_non_empty()` - Ensures session_id is a non-empty string
- `surface_id_must_be_non_empty()` - Ensures surface_id is a non-empty string
- `validate_optional_utterance_id()` - Validates optional utterance_id field

**Data Flow:** Request body → Pydantic validation → Endpoint handler

---

### Main Application Models (`src/main.py`)

#### Request Models with Validation

**File:** `src/main.py`

| Model | Lines | Endpoint | Purpose |
|-------|-------|----------|---------|
| `SurfaceRegisterRequest` | ~100 | `POST /api/v1/surfaces/register` | Surface registration validation |
| `HeartbeatRequest` | ~100 | `POST /heartbeat` | Heartbeat validation |
| `FeedbackRequestModel` | ~100 | Various endpoints | Feedback submission validation |
| `ApprovalRequest` | ~100 | Various endpoints | Approval request validation |
| `BeadApproveRequest` | ~100 | Various endpoints | Bead approval validation |
| `BeadRejectRequest` | ~100 | Various endpoints | Bead rejection validation |
| `RollbackRequest` | ~100 | Various endpoints | Rollback request validation |
| `ComponentCreateRequest` | ~100 | Various endpoints | Component creation validation |
| `ComponentUpdateRequest` | ~100 | Various endpoints | Component update validation |
| `ComponentIterateRequest` | ~100 | Various endpoints | Component iteration validation |
| `UsagePatternRecord` | ~100 | Various endpoints | Usage pattern recording validation |
| `STTRequest` | ~100 | `POST /api/v1/stt` | Speech-to-text request validation |
| `CreateConfirmationRequest` | ~100 | `POST /api/v1/confirmations` | Confirmation creation validation |
| `ConfirmationResponseRequest` | ~100 | `POST /api/v1/confirmations` | Confirmation response validation |

**Data Flow:** HTTP Request → FastAPI → Pydantic Model → Validation Error (if invalid) or Handler (if valid)

---

### Test Router Models (`src/test/router.py`)

**File:** `src/test/router.py`

**Models with Field Validators:**
- `SessionCreateRequest` - Test session creation
- `TestClassificationRequest` - Intent classification testing
- `TestClassificationResponse` - Classification response validation
- `IntentClassifyRequest` - Intent classification requests
- `IntentClassifyResponse` - Intent classification responses
- `TestCreateTopicRequest` - Topic creation testing
- `TestDropSSERequest` - SSE drop testing
- `TestSSEBroadcastRequest` - SSE broadcast testing
- `DispatchRequest` - Dispatch request testing

**Field Validator:**
- `validate_session_id()` - Validates session_id format

**Trigger:** Test endpoint requests to `src/test/router.py` routes

---

## 2. Deployment Data Validation (Manual Functions)

These validation functions must be explicitly invoked by calling the appropriate function.

### Core Deployment Validation (`src/validation/deployment_data.py`)

**File:** `src/validation/deployment_data.py`

#### `validate_timestamp(timestamp_str: str) -> bool`
**Lines:** 45-66

**Purpose:** Validates ISO 8601 timestamp strings

**Returns:** `True` if valid, `False` otherwise

**Usage:**
```python
from src.validation.deployment_data import validate_timestamp
is_valid = validate_timestamp("2026-08-07T12:34:56Z")
```

---

#### `validate_deployment_record(data: Dict[str, Any]) -> Tuple[bool, Optional[str]]`
**Lines:** 69-120+

**Purpose:** Validates a single deployment record against the expected schema

**Schema Fields Checked:**
- `service` (str, required)
- `first_deployment` (str, required)
- `last_deployment` (str, required)
- `period_days` (int, required)
- `total_deployments` (int, required)
- `successful_deployments` (int, required)
- `failed_deployments` (int, required)
- `success_rate` (float, required)
- `failure_rate` (float, required)
- `deployment_frequency_per_day` (float, required)
- `mean_time_between_deployments_hours` (float, required)
- `deployment_names` (list, required)

**Returns:** `(is_valid, error_message)`

**Usage:**
```python
from src.validation.deployment_data import validate_deployment_record
is_valid, error = validate_deployment_record(deployment_data)
```

---

#### `validate_deployment_data(data: Dict[str, Any]) -> Tuple[bool, Optional[str]]`
**Purpose:** Validates deployment data structure with all required fields

**Returns:** `(is_valid, error_message)`

**Usage:**
```python
from src.validation.deployment_data import validate_deployment_data
is_valid, error = validate_deployment_data(data)
```

---

#### `validate_deployment_data_simple(data: dict) -> bool`
**Purpose:** Simplified validation that returns boolean only

**Returns:** `True` if valid, `False` otherwise

**Usage:**
```python
from src.validation.deployment_data import validate_deployment_data_simple
is_valid = validate_deployment_data_simple(data)
```

---

#### `validate_required_fields(data: dict) -> Tuple[bool, str]`
**Purpose:** Validates presence of required fields in deployment data

**Returns:** `(is_valid, error_message)`

---

#### `validate_data_types(data: dict, schema: dict) -> Tuple[bool, str]`
**Purpose:** Validates data types against a schema

**Returns:** `(is_valid, error_message)`

---

### Deployment Validator (`src/validation/deployment_validator.py`)

**File:** `src/validation/deployment_validator.py`

#### `validate_timestamp(timestamp_str: str) -> Tuple[bool, Optional[str]]`
**Purpose:** Validates timestamp format and returns detailed error

---

#### `validate_field_type(value: Any, expected_types: tuple, field_name: str, is_optional: bool = False) -> Tuple[bool, Optional[str]]`
**Purpose:** Validates field type against expected types

---

#### `validate_metadata(metadata: Dict[str, Any]) -> Tuple[bool, List[str]]`
**Purpose:** Validates metadata structure

**Returns:** `(is_valid, list_of_errors)`

---

#### `validate_cluster_deployments(cluster_deployments: Dict[str, Any]) -> Tuple[bool, List[str]]`
**Purpose:** Validates cluster deployment data structure

---

#### `validate_summary(summary: Dict[str, Any]) -> Tuple[bool, List[str]]`
**Purpose:** Validates deployment summary data

---

#### `validate_deployment_data(data: Dict[str, Any]) -> Tuple[bool, Optional[str]]`
**Purpose:** Main deployment data validation function

---

#### `validate_deployment_data_list(data_list: List[Dict[str, Any]]) -> Tuple[bool, List[str]]`
**Purpose:** Validates a list of deployment records

---

## 3. Schema Validation (Pydantic Field Validators)

These validators are embedded in Pydantic models and run automatically when the model is instantiated.

### Whisper STT Deployment Schema (`src/schemas/whisper_stt_simplified.py`)

**File:** `src/schemas/whisper_stt_simplified.py`

#### Field Validators:

| Validator | Field | Purpose |
|-----------|-------|---------|
| `validate_timestamp` | `generated_at` | ISO 8601 timestamp validation |
| `validate_unique_source_files` | `source_files` | Ensures unique source file list |
| `validate_last_deployment_timestamp` | `last_deployment_timestamp` | Timestamp validation |
| `validate_ready_replicas` | `ready_replicas` | Replica count validation |
| `validate_available_replicas` | `available_replicas` | Replica count validation |
| `validate_running_pods` | `running_pods` | Pod count validation |
| `validate_crashloops` | `crashloops` | Crash loop count validation |
| `validate_oomkills` | `oomkills` | OOM kill count validation |
| `validate_incident_counts` | `incident_counts` | Incident count validation |
| `validate_deployment_counts` | `deployment_counts` | Deployment count validation |
| `validate_timestamps` | Various timestamp fields | Timestamp consistency validation |
| `validate_docker_image` | `docker_image` | Docker image format validation |
| `validate_revision` | `revision` | Revision format validation |
| `validate_replica_counts` | Replica fields | Replica count consistency |
| `validate_failure_type_logic` | `failure_type` | Failure type enum validation |
| `validate_summaries_keys` | `summaries` | Summary keys validation |
| `validate_deployment_records` | `deployment_records` | Deployment records list validation |
| `validate_metadata_consistency` | `metadata` | Metadata consistency validation |

**Trigger:** Automatic when `DeploymentMetadata` or related models are instantiated

**Usage:**
```python
from src.schemas.whisper_stt_simplified import DeploymentMetadata
metadata = DeploymentMetadata(**data)  # Validators run automatically
```

---

### Whisper STT Deployment Schema (`src/schemas/whisper_stt_deployment.py`)

**File:** `src/schemas/whisper_stt_deployment.py`

#### `validate_deployment_data(data: dict) -> bool`
**Purpose:** Validates deployment data structure

**Returns:** `True` if valid, `False` otherwise

---

## 4. Registry and Action Validation

### Registry Validation (`src/registry.py`)

**File:** `src/registry.py`

#### `_validate_project_entry(slug: str, entry: dict) -> list[str]`
**Purpose:** Validates a single project entry in the registry

**Returns:** List of error messages (empty if valid)

**Trigger:** Called during registry loading and validation

---

#### `_validate_registry(registry: dict) -> None`
**Purpose:** Validates the entire registry structure

**Raises:** Validation errors if registry is invalid

**Trigger:** Called during registry initialization

---

### Action Registry Validation (`src/action/registry.py`)

**File:** `src/action/registry.py`

#### `_validate_workflow_steps(project_slug: str, workflow_name: str, steps: list[Any]) -> list[str]`
**Lines:** 56-100+

**Purpose:** Validates workflow step definitions

**Checks:**
- Step names are known/valid
- Step definitions are properly structured

**Returns:** List of error messages (empty if valid)

**Known Steps:**
- `ci_status`
- `image_tag`
- `gitops_commit`
- `argocd_sync_status`
- `pod_status`

---

#### `_validate_workflow_definition(project_slug: str, workflow_name: str, workflow: dict) -> list[str]`
**Purpose:** Validates complete workflow definition including steps and metadata

**Returns:** List of error messages (empty if valid)

---

#### `async def validate_all_workflows() -> list[dict[str, Any]]`
**Purpose:** Validates all workflow definitions across all projects

**Returns:** List of validation results for each workflow

**Trigger:** Explicit call to validate all workflows

**Usage:**
```python
from src.action.registry import validate_all_workflows
results = await validate_all_workflows()
```

---

### Action Executor Validation (`src/action/executor.py`)

**File:** `src/action/executor.py`

#### `Step.validate(ctx: ExecutionContext) -> None`
**Purpose:** Validates step execution context

**Trigger:** Called before step execution

---

#### `ActionExecutor.validate(ctx: ExecutionContext) -> None`
**Purpose:** Validates action executor context

**Trigger:** Called before action execution

---

### Action Manifest Validation (`src/action/manifest_template.py`)

**File:** `src/action/manifest_template.py`

#### `ManifestTemplate.validate() -> None`
**Purpose:** Validates manifest template structure

---

#### `_validate_field_allowed(path: str) -> None`
**Purpose:** Validates that a field path is allowed in the manifest

---

### GitOps Action Validation (`src/action/steps/gitops.py`)

**File:** `src/action/steps/gitops.py`

#### `validate() -> None`
**Purpose:** Validates GitOps action configuration

---

#### `_validate_declarative_config_repo() -> None`
**Purpose:** Validates declarative config repository configuration

---

#### `_parse_and_validate_fields(template_fields: list[dict[str, Any]]) -> list[TemplateField]`
**Purpose:** Parses and validates template field definitions

**Returns:** List of validated template fields

---

## 5. Completeness and JSON Validation

### JSON Completeness Validation (`src/validation/completeness.py`)

**File:** `src/validation/completeness.py`

#### `validate_json_wellformedness(data: Any) -> Tuple[bool, Optional[str]]`
**Purpose:** Validates that data is well-formed JSON

**Returns:** `(is_valid, error_message)`

---

#### `validate_json_file_wellformedness(file_path: Path) -> Tuple[bool, Optional[str], Optional[Dict[str, Any]]]`
**Purpose:** Validates JSON file is well-formed and loads it

**Returns:** `(is_valid, error_message, parsed_data)`

---

#### `validate_30day_completeness(data: Dict[str, Any], required_service_counts: Dict[str, int]) -> Tuple[bool, str]`
**Purpose:** Validates 30-day deployment data completeness

**Parameters:**
- `data` - Deployment data to validate
- `required_service_counts` - Expected count per service

**Returns:** `(is_valid, error_message)`

---

#### `validate_json_completeness(data: Any, required_fields: List[str], required_service_counts: Optional[Dict[str, int]] = None) -> Tuple[bool, Optional[str]]`
**Purpose:** Validates JSON completeness with required fields and service counts

**Returns:** `(is_valid, error_message)`

---

#### `validate_json_file_completeness(file_path: Path, required_fields: List[str], required_service_counts: Optional[Dict[str, int]] = None) -> Tuple[bool, Optional[str], Optional[Dict[str, Any]]]`
**Purpose:** Validates JSON file completeness and loads it

**Returns:** `(is_valid, error_message, parsed_data)`

---

### Validate Completeness Module (`src/validation/validate_completeness.py`)

**File:** `src/validation/validate_completeness.py`

#### `validate_completeness(data: List[Dict[str, Any]]) -> Tuple[bool, str]`
**Purpose:** Validates deployment data completeness

**Returns:** `(is_valid, error_message)`

---

#### `validate_completeness_with_details(data: List[Dict[str, Any]]) -> Dict[str, Any]`
**Purpose:** Validates completeness and returns detailed validation report

**Returns:** Detailed validation report dictionary

---

### Validation Runner (`src/validation/runner.py`)

**File:** `src/validation/runner.py`

#### `validate_deployment_file(file_path: str) -> Tuple[bool, List[str]]`
**Purpose:** Main entry point for validating deployment files

**Returns:** `(is_valid, list_of_errors)`

**Usage:**
```python
from src.validation.runner import validate_deployment_file
is_valid, errors = validate_deployment_file("/path/to/file.json")
```

---

#### `_validate_json_wellformedness(file_path: Path) -> Tuple[bool, str, Dict[str, Any]]`
**Purpose:** Internal function to validate JSON well-formedness

---

#### `_validate_required_fields(data: Dict[str, Any]) -> Tuple[bool, List[str]]`
**Purpose:** Internal function to validate required fields

---

#### `_validate_data_types(data: Dict[str, Any]) -> Tuple[bool, List[str]]`
**Purpose:** Internal function to validate data types

---

#### `_validate_completeness(data: Dict[str, Any]) -> Tuple[bool, str]`
**Purpose:** Internal function to validate data completeness

---

### Integration Validation (`src/validation/integration.py`)

**File:** `src/validation/integration.py`

#### `validate_all() -> Dict[str, Any]`
**Purpose:** Runs all validation checks across the codebase

**Returns:** Comprehensive validation report

**Trigger:** Explicit call for comprehensive validation

**Usage:**
```python
from src.validation.integration import validate_all
report = validate_all()
```

---

## 6. Specialized Validation Functions

### VictorioLogs Queries Validation (`src/victorialogs_queries.py`)

**File:** `src/victorialogs_queries.py`

#### `validate_query_syntax(query: str) -> bool`
**Purpose:** Validates VictorioLogs query syntax

**Returns:** `True` if valid, `False` otherwise

**Trigger:** Before executing VictorioLogs queries

---

### VictorioLogs Latency Queries Validation (`src/victorialogs_latency_queries.py`)

**File:** `src/victorialogs_latency_queries.py`

#### `validate_query_syntax(query: str) -> Dict[str, Any]`
**Purpose:** Validates latency query syntax and returns detailed validation

**Returns:** Validation result dictionary

---

### Fetch Commands Validation (`src/fetch/commands.py`)

**File:** `src/fetch/commands.py`

#### `_validate_timeout_ms(value: Any, source_name: str) -> int | None`
**Purpose:** Validates timeout value for fetch commands

**Returns:** Validated timeout in milliseconds or `None`

**Trigger:** During fetch command initialization

---

### Escalate Handler Validation (`src/escalate/handler.py`)

**File:** `src/escalate/handler.py`

#### `_validate_and_prepare_approval(...)`
**Purpose:** Validates and prepares escalation approval requests

**Trigger:** Before escalation approval

---

### Pod Input Validation (`src/escalate/pod_input.py`)

**File:** `src/escalate/pod_input.py`

#### `validate_pod_name(pod_name: str) -> Tuple[bool, Optional[str]]`
**Purpose:** Validates Kubernetes pod name format

**Returns:** `(is_valid, error_message)`

**Trigger:** Before pod operations

---

### Confirmation Prompts Validation (`src/confirmations/prompts.py`)

**File:** `src/confirmations/prompts.py`

#### `validate_confirmation_response(response: str) -> bool`
**Purpose:** Validates user confirmation response

**Returns:** `True` if valid response, `False` otherwise

**Trigger:** When processing confirmation responses

---

## 7. Bead Validation

### Bead Validator (`src/bead_validation/validator.py`)

**File:** `src/bead_validation/validator.py`

#### `BeadValidator.validate_bead_body(...)`
**Purpose:** Validates bead body structure and content

**Trigger:** During bead creation/update

---

## 8. Test and Development Validation

### Test Helpers (`src/test/helpers.py`)

**File:** `src/test/helpers.py`

#### `validate_utterance_suite() -> dict[str, Any]`
**Purpose:** Validates test utterance suite

**Returns:** Validation report

**Trigger:** Test suite execution

---

### Validate Utterances Fixture (`src/test/fixtures/validate_utterances.py`)

**File:** `src/test/fixtures/validate_utterances.py`

#### `validate_single_utterance(utterance: dict[str, Any], session_id: str = "test-session") -> dict[str, Any]`
**Purpose:** Validates a single test utterance

**Returns:** Validation result dictionary

---

#### `validate_all_utterances()`
**Purpose:** Validates all test utterances in the fixture

**Trigger:** Test execution

---

## 9. Initialization and Import-Time Validation

### Session Store Cache Invalidation (`src/session/store.py`)

**File:** `src/session/store.py`

#### `invalidate_card_cache(result_id: str)`
**Purpose:** Invalidates card cache for a result (not validation, but related)

**Trigger:** After result updates

---

#### `invalidate_card_cache_entry(...)`
**Purpose:** Invalidates specific card cache entry

---

#### `invalidate_topic_context(topic_id: str)`
**Purpose:** Invalidates topic context cache

---

### Monitoring Config Cache Invalidation (`src/monitoring/config_loader.py`)

**File:** `src/monitoring/config_loader.py`

#### `invalidate_cache()`
**Purpose:** Invalidates monitoring configuration cache

**Trigger:** Configuration changes

---

### Component Library Invalidation (`src/components/library.py`)

**File:** `src/components/library.py`

#### `invalidate_result(result_id: str)`
**Purpose:** Invalidates cached result

**Trigger:** Result updates

---

## 10. Data Flow Summary

### API Request Flow
```
HTTP Request
  ↓
FastAPI Endpoint
  ↓
Pydantic Model Validation (automatic)
  ↓
[If invalid] → 422 Unprocessable Entity
  ↓
[If valid] → Endpoint Handler
  ↓
Business Logic
  ↓
Manual Validation Functions (if triggered)
  ↓
[If invalid] → Error Response
  ↓
[If valid] → Continue processing
```

### Deployment Data Validation Flow
```
Load JSON File
  ↓
validate_json_wellformedness()
  ↓
validate_deployment_file()
  ↓
validate_required_fields()
  ↓
validate_data_types()
  ↓
validate_completeness()
  ↓
[All pass] → Data is valid
  ↓
[Any fail] → Return errors
```

### Workflow Validation Flow
```
Load Registry
  ↓
_validate_registry()
  ↓
For each project:
  _validate_project_entry()
  ↓
For each workflow:
  _validate_workflow_definition()
  ↓
_validate_workflow_steps()
  ↓
[All pass] → Workflows are valid
  ↓
[Any fail] → WorkflowValidationError
```

---

## 11. Import Paths and Module Organization

### Main Validation Module (`src/validation/__init__.py`)

**Exports:**
```python
from src.validation import (
    # Deployment data validation
    validate_deployment_data,
    validate_deployment_data_simple,
    validate_deployment_record,
    validate_timestamp,
    validate_required_fields,
    validate_data_types,
    
    # JSON completeness validation
    validate_json_wellformedness,
    validate_json_file_wellformedness,
    validate_30day_completeness,
    validate_json_completeness,
    validate_json_file_completeness,
    
    # File validation
    validate_deployment_file,
    
    # Integration validation
    validate_all,
)
```

### Usage Examples

#### Validate deployment data
```python
from src.validation import validate_deployment_data

data = {"service": "pbx-web", "total_deployments": 10, ...}
is_valid, error = validate_deployment_data(data)
if not is_valid:
    print(f"Validation failed: {error}")
```

#### Validate a deployment file
```python
from src.validation import validate_deployment_file

is_valid, errors = validate_deployment_file("/path/to/file.json")
if not is_valid:
    for error in errors:
        print(f"Error: {error}")
```

#### Run comprehensive validation
```python
from src.validation import validate_all

report = validate_all()
print(f"Validation report: {report}")
```

---

## 12. Trigger Contexts

### Automatic Triggers (No Code Needed)
- FastAPI endpoint requests → Pydantic model validation
- Pydantic model instantiation → Field validators

### Manual Triggers (Explicit Function Calls)
- `validate_deployment_file()` → Call explicitly
- `validate_all_workflows()` → Call explicitly
- `validate_all()` → Call explicitly
- `validate_query_syntax()` → Call before query execution

### Context-Specific Triggers
- Registry loading → `_validate_registry()`
- Action execution → `Step.validate()`
- File loading → `validate_json_wellformedness()`
- Test execution → `validate_utterance_suite()`

---

## Summary

The aide-de-camp validation system operates at multiple layers:

1. **API Layer** - Automatic Pydantic validation on all endpoints
2. **Data Layer** - Manual validation functions for deployment data
3. **Schema Layer** - Field validators within Pydantic models
4. **Workflow Layer** - Registry and action validation
5. **Quality Layer** - JSON well-formedness and completeness checks
6. **Test Layer** - Test fixture validation

All validation functions return clear error messages to facilitate debugging and data quality improvement. The modular design allows validation to be triggered at appropriate points in the data lifecycle without imposing unnecessary overhead.
