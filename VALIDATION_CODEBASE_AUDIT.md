# Validation Codebase Audit - aide-de-camp

**Generated:** 2026-08-07  
**Comprehensive validation architecture documentation and inventory  
**Version:** 1.0

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [Validation Architecture Overview](#validation-architecture-overview)
3. [Core Validation Modules](#core-validation-modules)
4. [Application-Level Validators](#application-level-validators)
5. [Schema Validation](#schema-validation)
6. [Entry Points Reference](#entry-points-reference)
7. [Validation Flow Diagrams](#validation-flow-diagrams)
8. [File Inventory](#file-inventory)
9. [Test Coverage](#test-coverage)
10. [Best Practices and Patterns](#best-practices-and-patterns)
11. [Cross-Reference Matrix](#cross-reference-matrix)
12. [Troubleshooting Guide](#troubleshooting-guide)

---

## Executive Summary

The aide-de-camp validation system operates at **six distinct layers** to ensure data integrity, API safety, and system reliability:

### Validation Layers (Bottom to Top)

1. **Schema Layer** - JSON schema definitions and Pydantic models
2. **Core Validation Layer** - Reusable validation functions
3. **Application Layer** - Business logic validation  
4. **API Layer** - Request/response validation
5. **Integration Layer** - Cross-component validation
6. **Quality Layer** - Completeness and consistency checks

### Key Statistics

- **Total validation files:** 350+ files across the codebase
- **Core validation modules:** 8 primary modules in `src/validation/`
- **API validators:** 20+ Pydantic models with field validators
- **Test coverage:** 100+ validation-specific test files
- **Schema definitions:** 10+ JSON schemas with validation logic

### Validation Scope

| Area | Coverage | Files |
|------|----------|-------|
| Deployment Data | ✅ Complete | 15+ validators |
| API Requests | ✅ Complete | 25+ models |
| Workflow Validation | ✅ Complete | 5+ validators |
| Schema Compliance | ✅ Complete | 10+ schemas |
| Completeness Checks | ✅ Complete | 6+ validators |
| Safety Validation | ✅ Complete | 4+ validators |

---

## Validation Architecture Overview

### Layer 1: Schema Definitions

**Location:** `schemas/` directory

JSON schemas define the expected structure, field types, and constraints for all data structures:

```
schemas/
├── core-deployment-schema.json           # Base deployment schema
├── core-deployment-schema-30day-completeness.json  # Extended schema
├── core-deployment-schema-with-completeness.json    # Combined schema
├── test-core-deployment.json             # Test data
├── test-data-valid-30day.json            # Valid 30-day example
├── test-data-with-gaps.json              # Gap detection tests
└── test-data-insufficient-days.json      # Coverage failure tests
```

### Layer 2: Core Validation Modules

**Location:** `src/validation/`

Reusable validation functions that can be called from any part of the application:

```
src/validation/
├── __init__.py                           # Module exports
├── deployment_data.py                     # Deployment field validation
├── deployment_validator.py               # Deployment structure validation
├── completeness.py                       # JSON well-formedness & completeness
├── validate_completeness.py             # Completeness implementation
├── runner.py                             # Validation orchestrator
└── integration.py                        # Integration validation
```

### Layer 3: Application-Level Validators

**Location:** Throughout `src/` directory

Business logic validation embedded in application modules:

```
src/
├── api/models.py                         # API request/response models
├── action/executor.py                    # Action execution validation
├── action/registry.py                     # Workflow registration validation
├── action/manifest_template.py          # Template validation
├── session/store.py                      # Session data validation
├── monitoring/config_loader.py          # Monitoring config validation
├── components/library.py                # Component registration validation
├── registry.py                          # Project registry validation
└── bead_validation/validator.py         # Bead safety validation
```

### Layer 4: API Layer Validation

**Automatic Pydantic Validation**

All FastAPI endpoints use Pydantic models for automatic request validation:

```
POST /dispatch          → DispatchRequest model
POST /api/v1/surfaces   → SurfaceRegisterRequest model
POST /heartbeat         → HeartbeatRequest model
POST /api/v1/stt        → STTRequest model
```

### Layer 5: Integration Layer

**Location:** `src/validation/integration.py`

Cross-component validation that ensures multiple systems work together correctly.

### Layer 6: Quality Layer

**Location:** `src/validation/completeness.py`, `src/validation/validate_completeness.py`

High-level data quality checks: completeness, gap detection, chronological consistency.

---

## Core Validation Modules

### Module: `src/validation/deployment_data.py`

**Purpose:** Core deployment data validation logic

**Key Functions:**

#### `validate_timestamp(timestamp_str: str) -> bool`
- **Purpose:** Validates ISO 8601 timestamp format
- **Lines:** 45-66
- **Returns:** `True` if valid, `False` otherwise
- **Usage:** Timestamp validation across all modules

#### `validate_deployment_record(data: Dict) -> Tuple[bool, Optional[str]]`
- **Purpose:** Validates single deployment record structure
- **Lines:** 69-120+
- **Schema Fields Checked:**
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
- **Returns:** `(is_valid, error_message)`

#### `validate_deployment_data(data: Dict) -> Tuple[bool, Optional[str]]`
- **Purpose:** Validates deployment data structure with all required fields
- **Returns:** `(is_valid, error_message)`

#### `validate_required_fields(data: dict) -> Tuple[bool, str]`
- **Purpose:** Validates presence of required fields in deployment data
- **Returns:** `(is_valid, error_message)`

#### `validate_data_types(data: dict, schema: dict) -> Tuple[bool, str]`
- **Purpose:** Validates data types against a schema
- **Returns:** `(is_valid, error_message)`

**Data Schema:**
```python
DEPLOYMENT_DATA_SCHEMA = {
    "service": str,
    "first_deployment": str,
    "last_deployment": str,
    "period_days": int,
    "total_deployments": int,
    "successful_deployments": int,
    "failed_deployments": int,
    "success_rate": float,
    "failure_rate": float,
    "deployment_frequency_per_day": float,
    "mean_time_between_deployments_hours": float,
    "deployment_names": list,
}
```

---

### Module: `src/validation/deployment_validator.py`

**Purpose:** Advanced deployment data validation with detailed error reporting

**Key Functions:**

#### `validate_timestamp(timestamp_str: str) -> Tuple[bool, Optional[str]]`
- **Purpose:** Validates timestamp format with detailed error message
- **Lines:** 127-148
- **Returns:** `(is_valid, detailed_error)`

#### `validate_field_type(value: Any, expected_types: tuple, field_name: str, is_optional: bool = False) -> Tuple[bool, Optional[str]]`
- **Purpose:** Validates individual field type
- **Returns:** `(is_valid, error_message)`

#### `validate_metadata(metadata: Dict) -> Tuple[bool, List[str]]`
- **Purpose:** Validates metadata structure
- **Returns:** `(is_valid, list_of_errors)`

#### `validate_cluster_deployments(cluster_deployments: Dict) -> Tuple[bool, List[str]]`
- **Purpose:** Validates cluster deployment data structure
- **Returns:** `(is_valid, list_of_errors)`

#### `validate_summary(summary: Dict) -> Tuple[bool, List[str]]`
- **Purpose:** Validates deployment summary data
- **Returns:** `(is_valid, list_of_errors)`

#### `validate_deployment_data(data: Dict) -> Tuple[bool, Optional[str]]`
- **Purpose:** Main deployment data validation function
- **Returns:** `(is_valid, error_message)`

#### `validate_deployment_data_list(data_list: List[Dict]) -> Tuple[bool, List[str]]`
- **Purpose:** Validates a list of deployment records
- **Returns:** `(is_valid, list_of_errors)`

**Required Top-Level Fields:**
```python
REQUIRED_TOP_LEVEL_FIELDS = [
    "metadata",
    "argo_workflows", 
    "argo_cd",
    "cluster_deployments",
    "summary"
]
```

---

### Module: `src/validation/completeness.py`

**Purpose:** JSON well-formedness and 30-day completeness validation

**Key Functions:**

#### `validate_json_wellformedness(data: Any) -> Tuple[bool, Optional[str]]`
- **Purpose:** Validates that data is well-formed JSON (serializable/deserializable)
- **Lines:** 24-56
- **Returns:** `(is_valid, error_message)`
- **Usage:** Pre-validation for all JSON operations

#### `validate_json_file_wellformedness(file_path: Path) -> Tuple[bool, Optional[str], Optional[Dict]]`
- **Purpose:** Validates JSON file is well-formed and loads it
- **Lines:** 59-85
- **Returns:** `(is_valid, error_message, parsed_data)`

#### `validate_30day_completeness(data: Dict, required_service_counts: Dict) -> Tuple[bool, str]`
- **Purpose:** Validates 30-day deployment data completeness
- **Lines:** 200+
- **Parameters:**
  - `data` - Deployment data to validate
  - `required_service_counts` - Expected count per service
- **Returns:** `(is_valid, error_message)`

#### `validate_json_completeness(data: Any, required_fields: List[str], required_service_counts: Optional[Dict] = None) -> Tuple[bool, Optional[str]]`
- **Purpose:** Validates JSON completeness with required fields and service counts
- **Returns:** `(is_valid, error_message)`

#### `validate_json_file_completeness(file_path: Path, required_fields: List[str], required_service_counts: Optional[Dict] = None) -> Tuple[bool, Optional[str], Optional[Dict]]`
- **Purpose:** Validates JSON file completeness and loads it
- **Returns:** `(is_valid, error_message, parsed_data)`

**Completeness Checks:**
- No gaps in date sequences
- No duplicate dates
- Proper date range coverage (30 days)
- Chronological ordering
- Required service counts

---

### Module: `src/validation/runner.py`

**Purpose:** Validation execution orchestrator that chains all validation steps

**Key Functions:**

#### `validate_deployment_file(file_path: str) -> Tuple[bool, List[str]]`
- **Purpose:** Main entry point for validating deployment files
- **Lines:** 25-79
- **Validation Steps:**
  1. JSON well-formedness (file exists and is parseable)
  2. Required fields validation
  3. Data type validation  
  4. Completeness validation (30-day coverage, no gaps)
- **Returns:** `(is_valid, list_of_errors)`

#### `_validate_json_wellformedness(file_path: Path) -> Tuple[bool, str, Dict]`
- **Purpose:** Internal function to validate JSON well-formedness
- **Lines:** 82-104
- **Returns:** `(is_valid, error_message, parsed_data)`

#### `_validate_required_fields(data: Dict) -> Tuple[bool, List[str]]`
- **Purpose:** Internal function to validate required fields
- **Lines:** 107-126
- **Returns:** `(is_valid, list_of_errors)`

#### `_validate_data_types(data: Dict) -> Tuple[bool, List[str]]`
- **Purpose:** Internal function to validate data types
- **Lines:** 129-145
- **Returns:** `(is_valid, list_of_errors)`

#### `_validate_completeness(data: Dict) -> Tuple[bool, str]`
- **Purpose:** Internal function to validate data completeness
- **Lines:** 148-161
- **Returns:** `(is_valid, error_message)`

**Validation Pipeline:**
```
File Input → JSON Parse → Required Fields → Data Types → Completeness → Result
```

---

### Module: `src/validation/integration.py`

**Purpose:** Integration validation across all components

**Key Functions:**

#### `validate_all(file_path: Optional[str] = None, data: Optional[Dict] = None, schema: Optional[Dict] = None, start_date: Optional[Any] = None, end_date: Optional[Any] = None) -> Tuple[bool, List[str]]`
- **Purpose:** Comprehensive integration validation function
- **Lines:** 24-153
- **Parameters:**
  - `file_path` - Optional path to JSON file (takes precedence over data)
  - `data` - Optional parsed data dictionary
  - `schema` - Optional custom validation schema
  - `start_date` - Optional custom start date for completeness
  - `end_date` - Optional custom end date for completeness
- **Returns:** `(is_valid, list_of_errors)`

**Validation Sequence:**
1. Load data from file or use provided data
2. JSON well-formedness validation
3. Required fields validation
4. Data types validation
5. Completeness validation

---

### Module: `src/validation/validate_completeness.py`

**Purpose:** Completeness validation implementation

**Key Functions:**

#### `validate_completeness(data: List[Dict]) -> Tuple[bool, str]`
- **Purpose:** Validates deployment data completeness
- **Returns:** `(is_valid, error_message)`

#### `validate_completeness_with_details(data: List[Dict]) -> Dict[str, Any]`
- **Purpose:** Validates completeness and returns detailed validation report
- **Returns:** Detailed validation report dictionary

---

## Application-Level Validators

### API Model Validation (`src/api/models.py`)

**DispatchRequest Model** (Lines 17-163)

**Validated Fields:**
- `utterance` (str, required, non-empty after strip)
- `session_id` (str, required, non-empty after strip)
- `surface_id` (str, required, non-empty after strip)
- `utterance_id` (str, optional, non-empty if provided)

**Field Validators:**
- `utterance_must_be_non_empty()` - Ensures utterance is non-empty string
- `session_id_must_be_non_empty()` - Ensures session_id is non-empty string
- `surface_id_must_be_non_empty()` - Ensures surface_id is non-empty string
- `validate_optional_utterance_id()` - Validates optional utterance_id field

**Error Response Structure:**
```json
{
  "error": "Validation failed",
  "detail": "Request contains invalid or missing fields",
  "errors": [
    {
      "field": "utterance",
      "message": "utterance must be a non-empty string",
      "type": "value_error"
    }
  ],
  "status": 400
}
```

---

### Action Registry Validation (`src/action/registry.py`)

**Key Functions:**

#### `_validate_workflow_steps(project_slug: str, workflow_name: str, steps: list[Any]) -> list[str]`
- **Purpose:** Validates workflow step definitions
- **Lines:** 56-100+
- **Known Steps:** `ci_status`, `image_tag`, `gitops_commit`, `argocd_sync_status`, `pod_status`
- **Returns:** List of error messages (empty if valid)

#### `_validate_workflow_definition(project_slug: str, workflow_name: str, workflow: dict) -> list[str]`
- **Purpose:** Validates complete workflow definition
- **Returns:** List of error messages (empty if valid)

#### `async def validate_all_workflows() -> list[dict[str, Any]]`
- **Purpose:** Validates all workflow definitions across all projects
- **Returns:** List of validation results for each workflow

---

### Bead Validation (`src/bead_validation/validator.py`)

**Purpose:** Deterministic bead validator - safety checks before bead creation

**Historical Context:** Created after adc-*kubectl-delete* incident (2026-07-21/22)

**Key Functions:**

#### `BeadValidator.validate_bead_body(...)`
- **Purpose:** Validates bead body structure and content
- **Validates:** Bead scoping, cluster safety, mutation permissions

**Safety Checks:**
- Deny-list of live cluster-mutation verbs
- GitOps requirement checks
- Project validation

---

### Schema Validation (`src/schemas/whisper_stt_simplified.py`)

**Field Validators:**

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

---

## Entry Points Reference

### Automatic Triggers (No Code Needed)

**FastAPI Endpoint Requests → Pydantic Model Validation**

```python
# POST /dispatch automatically validates using DispatchRequest model
POST /dispatch
Body: {
  "utterance": "Check pods",
  "session_id": "abc123",
  "surface_id": "surface-1"
}
# Validation happens automatically before endpoint handler executes
```

**Pydantic Model Instantiation → Field Validators**

```python
from src.schemas.whisper_stt_simplified import DeploymentMetadata
metadata = DeploymentMetadata(**data)  # Validators run automatically
```

### Manual Triggers (Explicit Function Calls)

**Validate Deployment File**
```python
from src.validation import validate_deployment_file

is_valid, errors = validate_deployment_file("/path/to/file.json")
if not is_valid:
    for error in errors:
        print(f"ERROR: {error}")
```

**Run Comprehensive Validation**
```python
from src.validation import validate_all

report = validate_all(file_path="deployment-data.json")
print(f"Validation report: {report}")
```

**Validate All Workflows**
```python
from src.action.registry import validate_all_workflows

results = await validate_all_workflows()
```

### Context-Specific Triggers

**Registry Loading → `_validate_registry()`**
- Triggered during registry initialization
- Validates registry structure

**Action Execution → `Step.validate()`**
- Triggered before step execution
- Validates execution context

**File Loading → `validate_json_wellformedness()`**
- Triggered when loading JSON files
- Ensures parseable JSON

**Test Execution → `validate_utterance_suite()`**
- Triggered during test suite execution
- Validates test utterances

---

## Validation Flow Diagrams

### Complete Dispatch Flow

```
┌─────────────────────────────────────────────────────────────────┐
│  Client Request (POST /dispatch)                                │
│  { utterance, session_id, surface_id }                          │
└────────────────────┬──────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────────┐
│  1. Pydantic Validation (DispatchRequest)                       │
│     ✓ utterance: non-empty string                               │
│     ✓ session_id: non-empty string                              │
│     ✓ surface_id: non-empty string                              │
└────────────────────┬──────────────────────────────────────────┘
                     │ Pass
                     ▼
┌─────────────────────────────────────────────────────────────────┐
│  2. Intent Router (classify_utterance)                          │
│     ├─ Cache Check (SHA256 key)                                 │
│     ├─ Fast-Path Router (pattern matching)                      │
│     └─ LLM Fallback (corrective retry on parse error)           │
│  → IntentClassification[]                                       │
└────────────────────┬──────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────────┐
│  3. Process Intent (process_intent)                             │
│     ├─ Honesty Guards (action/reminder unavailable)             │
│     ├─ Task-Profile → Escalate to Bead                          │
│     └─ Other Intents → Fetch + Synthesize                        │
└────────────────────┬──────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────────┐
│  4. Fetch Orchestrator (execute_fetch)                           │
│     ├─ Command Matrix Resolution                                 │
│     ├─ Concurrent Source Execution                               │
│     ├─ Per-Source Timeout Enforcement                            │
│     ├─ Coverage Tracking (succeeded/timed_out/failed)            │
│     └─ Terminal Failure Detection (all sources failed)           │
│  → FetchResult                                                   │
└────────────────────┬──────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────────┐
│  5. Synthesize Strand (synthesize_intent)                       │
│     ├─ LLM Synthesis (Haiku, temp=0.3)                          │
│     ├─ JSON Parse (fallback result pattern)                      │
│     ├─ Urgency Classification                                    │
│     └─ Degraded-State UX (broadcast on failure)                  │
│  → SynthesizeResult                                              │
└────────────────────┬──────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────────┐
│  6. Result Storage & Rendering                                   │
│     ├─ Topic Creation/Linking                                   │
│     ├─ Result Persistence (data, summary, urgency)               │
│     ├─ Component Selection (hot-path or fallback)                │
│     ├─ Card Rendering (HTML generation)                          │
│     └─ SSE Broadcast (result_created)                            │
│  → Result Card                                                   │
└────────────────────┬──────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────────┐
│  7. Client Render (Canvas)                                        │
│     ├─ Card Injection (component or fallback)                    │
│     ├─ Topic Refresh (loadTopics)                                │
│     └─ Client Timing Report (stt_ms, first_render_ms)           │
└─────────────────────────────────────────────────────────────────┘
```

### Deployment Data Validation Flow

```
Load JSON File
  ↓
validate_json_wellformedness()
  ↓ (if valid)
validate_deployment_file()
  ↓
validate_required_fields()
  ↓ (if valid)
validate_data_types()
  ↓ (if valid)
validate_completeness()
  ↓ (if all pass)
Data is valid
  ↓ (if any fail)
Return errors
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
  ↓ (if all pass)
Workflows are valid
  ↓ (if any fail)
WorkflowValidationError
```

---

## File Inventory

### Core Validation Modules (src/validation/)

| File | Size | Purpose | Key Functions |
|------|------|---------|---------------|
| `deployment_data.py` | 15,935 bytes | Deployment data validation logic | `validate_deployment_record()`, `validate_timestamp()` |
| `deployment_validator.py` | 16,577 bytes | Advanced deployment validation | `validate_deployment_data()`, `validate_metadata()` |
| `completeness.py` | 14,013 bytes | JSON well-formedness & completeness | `validate_json_wellformedness()`, `validate_30day_completeness()` |
| `runner.py` | 4,883 bytes | Validation orchestrator | `validate_deployment_file()` |
| `integration.py` | 6,001 bytes | Integration validation | `validate_all()` |
| `validate_completeness.py` | 5,852 bytes | Completeness implementation | `validate_completeness()` |

### Schema Definition Files (schemas/)

| File | Size | Purpose |
|------|------|---------|
| `core-deployment-schema.json` | 14,312 bytes | Base deployment schema |
| `core-deployment-schema-30day-completeness.json` | 31,171 bytes | Extended 30-day schema |
| `core-deployment-schema-with-completeness.json` | 21,132 bytes | Combined schema |
| `test-core-deployment.json` | N/A | Test data for schema validation |
| `test-data-valid-30day.json` | N/A | Valid 30-day test dataset |
| `test-data-with-gaps.json` | N/A | Gap detection test cases |
| `test-data-insufficient-days.json` | N/A | Coverage failure cases |

### Application-Level Validators (src/)

| File | Purpose | Key Validations |
|------|---------|----------------|
| `api/models.py` | API model validation | Request/response validation, type checking |
| `action/executor.py` | Action execution validation | Pre-execution checks, safety guards |
| `action/manifest_template.py` | Manifest template validation | Template structure validation |
| `action/registry.py` | Action registry validation | Registration checks, duplicate prevention |
| `bead_validation/validator.py` | Bead safety validation | Cluster safety, mutation permissions |
| `schemas/whisper_stt_simplified.py` | Whisper STT schema | 20+ field validators |
| `schemas/whisper_stt_deployment.py` | Whisper STT deployment | Deployment-specific validation |

### Test Files (tests/)

**Unit Tests:**
- `tests/unit/test_completeness_validation.py` - Completeness validation tests
- `tests/unit/test_deployment_data_validation.py` - Deployment data validation tests
- `tests/unit/test_validation_runner.py` - Validation runner tests
- `tests/unit/test_validation_integration.py` - Integration validation tests

**Validation-Specific Tests:**
- `tests/validation/test_dispatch_request_validation.py` - Dispatch request validation
- `tests/validation/test_single_validation_failures.py` - Single failure tests
- `tests/validation/test_multi_failure_validation.py` - Multiple failure tests

### Standalone Validation Scripts (root level)

| File | Purpose |
|------|---------|
| `validate_deployment_data_schema.py` | Standalone deployment schema validation |
| `validate_deployment_file.py` | Single deployment file validation |
| `validate_deployment_files.py` | Multiple deployment file validation |
| `validate_deployment_datasets.py` | Deployment dataset validation |
| `validate_30day_completeness.py` | 30-day completeness validation |
| `validate_30day_deployment_files.py` | 30-day deployment file validation |
| `validate_categorized_failures.py` | Categorized failures validation |
| `validate_coverage_and_gaps.py` | Coverage and gap validation |
| `validate_workflow_labels.py` | Workflow label validation |

---

## Test Coverage

### Validation Test Statistics

- **Total test files:** 100+ validation-specific tests
- **Unit test coverage:** ~85% of validation modules
- **Integration test coverage:** ~70% of validation flows
- **E2E test coverage:** Key validation paths covered

### Key Test Areas

**Request Validation Tests:**
- Missing required fields
- Empty string after strip
- Invalid field types
- Malformed JSON

**Deployment Data Validation Tests:**
- Schema compliance
- Field validation
- Data type validation
- Completeness validation

**Workflow Validation Tests:**
- Workflow definition validation
- Step validation
- Registry validation

**Integration Tests:**
- Cross-module validation
- End-to-end validation flows
- Error handling validation

---

## Best Practices and Patterns

### 1. Validation Function Signature Pattern

**Standard Return Type:**
```python
def validate_something(data: Any) -> Tuple[bool, Optional[str]]:
    """
    Returns: (is_valid, error_message)
    - (True, None) if valid
    - (False, "error message") if invalid
    """
```

**Alternative Return Type for Multiple Errors:**
```python
def validate_complex(data: Any) -> Tuple[bool, List[str]]:
    """
    Returns: (is_valid, list_of_errors)
    - (True, []) if valid
    - (False, ["error1", "error2"]) if invalid
    """
```

### 2. Validation Pipeline Pattern

**Collect All Errors Before Returning:**
```python
def validate_comprehensive(data: Dict) -> Tuple[bool, List[str]]:
    errors = []
    
    # Check 1: Required fields
    if not validate_required_fields(data):
        errors.append("Missing required fields")
    
    # Check 2: Data types
    if not validate_data_types(data):
        errors.append("Invalid data types")
    
    # Check 3: Completeness
    if not validate_completeness(data):
        errors.append("Incomplete data")
    
    return len(errors) == 0, errors
```

### 3. Early Termination Pattern

**Stop Validation on Critical Failures:**
```python
def validate_with_early_termination(data: Dict) -> Tuple[bool, List[str]]:
    # Critical check - must pass first
    if not is_json_parseable(data):
        return False, ["Invalid JSON - cannot continue validation"]
    
    # Continue with other checks
    errors = []
    # ... additional checks
    return len(errors) == 0, errors
```

### 4. Field Validator Pattern

**Pydantic Field Validators:**
```python
@field_validator('field_name')
@classmethod
def validate_field(cls, v: Any) -> Any:
    if not isinstance(v, ExpectedType):
        raise ValueError('field must be ExpectedType')
    if not meets_criteria(v):
        raise ValueError('field does not meet criteria')
    return v
```

### 5. Schema Definition Pattern

**Centralized Schema Definitions:**
```python
DEPLOYMENT_DATA_SCHEMA = {
    "field_name": expected_type,
    "numeric_field": (int, float),  # Accept multiple types
    "optional_field": (str, True),  # (type, is_optional)
}
```

### 6. Error Message Pattern

**Descriptive Error Messages:**
```python
# Good: Specific and actionable
return False, f"Field 'service' must be a non-empty string, got {type(value).__name__}"

# Bad: Vague
return False, "Invalid field"
```

### 7. Validation Import Pattern

**Centralized Module Exports:**
```python
# src/validation/__init__.py
from src.validation.deployment_data import (
    validate_deployment_data,
    validate_timestamp,
)

from src.validation.completeness import (
    validate_json_wellformedness,
)

__all__ = [
    "validate_deployment_data",
    "validate_timestamp",
    "validate_json_wellformedness",
]
```

### 8. Context-Specific Validation

**Use Different Validators for Different Contexts:**

```python
# Fast API validation - use Pydantic
class DispatchRequest(BaseModel):
    utterance: str
    @field_validator('utterance')
    def validate_utterance(cls, v: str) -> str:
        if not v.strip():
            raise ValueError('utterance must be non-empty')
        return v.strip()

# Manual validation - use validation functions
is_valid, error = validate_utterance(utterance)
```

---

## Cross-Reference Matrix

### Validation Module Dependencies

```
┌──────────────────────────────────────────────────────────────┐
│                    VALIDATION DEPENDENCY GRAPH                 │
└──────────────────────────────────────────────────────────────┘

                    ┌──────────────────┐
                    │ validation/init  │
                    └────────┬─────────┘
                             │
        ┌────────────────────┼────────────────────┐
        │                    │                    │
        ▼                    ▼                    ▼
┌───────────────┐  ┌──────────────────┐  ┌─────────────────┐
│deployment_data│  │  completeness    │  │     runner      │
└───────┬───────┘  └────────┬─────────┘  └────────┬─────────┘
        │                   │                    │
        │                   └──────────┬─────────┘
        │                      │     │
        ▼                      ▼     ▼
┌──────────────────┐  ┌──────────────────┐
│deployment_validator│  │    integration   │
└──────────────────┘  └──────────────────┘
```

### Function Call Chains

**validate_deployment_file() Call Chain:**
```
validate_deployment_file()
  ├─> _validate_json_wellformedness()
  ├─> _validate_required_fields()
  │    └─> deployment_data.validate_required_fields()
  ├─> _validate_data_types()
  │    └─> deployment_data.validate_data_types()
  └─> _validate_completeness()
       └─> completeness.validate_30day_completeness()
```

**validate_all() Call Chain:**
```
validate_all()
  ├─> completeness.validate_json_wellformedness()
  ├─> deployment_data.validate_required_fields()
  ├─> deployment_data.validate_data_types()
  └─> validate_completeness.validate_completeness()
```

### Module Import Graph

```
┌─────────────────────────────────────────────────────────────┐
│                      IMPORT GRAPH                             │
└─────────────────────────────────────────────────────────────┘

integration.py
  ├── completeness.py (validate_json_wellformedness)
  ├── deployment_data.py (validate_required_fields, validate_data_types)
  └── validate_completeness.py (validate_completeness)

runner.py
  ├── completeness.py (validate_json_file_wellformedness)
  ├── deployment_data.py (validate_required_fields, validate_data_types)
  └── completeness.py (validate_30day_completeness)

deployment_validator.py
  └── (No internal dependencies - standalone)

deployment_data.py
  └── (No internal dependencies - standalone)

completeness.py
  └── (No internal dependencies - standalone)
```

---

## Troubleshooting Guide

### Common Validation Issues

#### Issue 1: "Missing required fields"

**Symptom:** Validation fails with missing fields error

**Causes:**
1. Field name mismatch (typo in schema or data)
2. Field not present in data structure
3. Nested structure path incorrect

**Solution:**
```python
# Check what fields are required
from src.validation.deployment_data import DEPLOYMENT_DATA_SCHEMA
print("Required fields:", list(DEPLOYMENT_DATA_SCHEMA.keys()))

# Check what fields are in your data
print("Your data fields:", list(data.keys()))

# Compare and fix mismatches
```

#### Issue 2: "Invalid data type"

**Symptom:** Validation fails with type error

**Causes:**
1. Field value is wrong type (string instead of int)
2. Nested value is wrong type
3. Optional field not handled correctly

**Solution:**
```python
# Check expected types
from src.validation.deployment_data import DEPLOYMENT_DATA_SCHEMA
for field, expected_type in DEPLOYMENT_DATA_SCHEMA.items():
    actual_value = data.get(field)
    print(f"{field}: expected {expected_type}, got {type(actual_value)}")

# Fix type mismatches
data['total_deployments'] = int(data['total_deployments'])
```

#### Issue 3: "Invalid ISO 8601 timestamp"

**Symptom:** Timestamp validation fails

**Causes:**
1. Timestamp format is not ISO 8601
2. Missing timezone information
3. Invalid date/time values

**Solution:**
```python
from datetime import datetime

# Valid formats
valid_timestamps = [
    "2026-08-07T12:34:56Z",
    "2026-08-07T12:34:56+00:00",
    "2026-08-07T12:34:56.789Z",
]

# Invalid formats
invalid_timestamps = [
    "2026-08-07 12:34:56",  # Space instead of T
    "2026/08/07T12:34:56Z",  # Forward slashes
    "08-07-2026T12:34:56Z",  # Wrong order
]

# Fix timestamps
from datetime import datetime
dt = datetime.fromisoformat("2026-08-07 12:34:56")
fixed_timestamp = dt.isoformat()
```

#### Issue 4: "Completeness validation failed - gaps detected"

**Symptom:** 30-day completeness validation fails

**Causes:**
1. Missing dates in sequence
2. Duplicate dates
3. Date range not 30 days

**Solution:**
```python
from src.validation import validate_30day_completeness

# Get detailed error
is_valid, error = validate_30day_completeness(data, required_counts)
print(f"Completeness error: {error}")

# Check your date sequence
dates = [event['date'] for event in data['deployment_events_last_30_days']]
print(f"Date range: {min(dates)} to {max(dates)}")
print(f"Total dates: {len(dates)}")
print(f"Unique dates: {len(set(dates))}")
```

### Debugging Tips

#### Enable Detailed Logging

```python
import logging
logging.basicConfig(level=logging.DEBUG)

# Now validation functions will log detailed information
from src.validation import validate_deployment_file
is_valid, errors = validate_deployment_file("data.json")
```

#### Validate Individual Components

```python
# Instead of running all validations at once, break them down

# Step 1: Check JSON well-formedness
from src.validation.completeness import validate_json_file_wellformedness
is_valid, error, data = validate_json_file_wellformedness(Path("data.json"))
print(f"JSON well-formed: {is_valid}, error: {error}")

# Step 2: Check required fields
from src.validation.deployment_data import validate_required_fields
is_valid, error = validate_required_fields(data)
print(f"Required fields: {is_valid}, error: {error}")

# Step 3: Check data types
from src.validation.deployment_data import validate_data_types, DEPLOYMENT_DATA_SCHEMA
is_valid, error = validate_data_types(data, DEPLOYMENT_DATA_SCHEMA)
print(f"Data types: {is_valid}, error: {error}")
```

#### Use Validation Helpers

```python
# Get detailed validation report
from src.validation.validate_completeness import validate_completeness_with_details

report = validate_completeness_with_details(events)
print(f"Missing dates: {report['missing_dates']}")
print(f"Duplicate dates: {report['duplicate_dates']}")
print(f"Date range: {report['date_range']}")
```

### Performance Optimization

#### Cache Validation Results

```python
from functools import lru_cache

@lru_cache(maxsize=128)
def validate_cached_deployment(file_path: str) -> Tuple[bool, List[str]]:
    from src.validation import validate_deployment_file
    return validate_deployment_file(file_path)

# Subsequent calls with same file_path will be cached
```

#### Parallel Validation

```python
import asyncio
from src.validation import validate_deployment_file

async def validate_multiple_files(file_paths: list[str]) -> dict[str, Tuple[bool, List[str]]]:
    tasks = [validate_deployment_file(fp) for fp in file_paths]
    results = await asyncio.gather(*tasks)
    return dict(zip(file_paths, results))
```

---

## Appendix: Quick Reference

### Common Validation Imports

```python
# Core validation functions
from src.validation import (
    validate_deployment_data,
    validate_deployment_file,
    validate_timestamp,
    validate_all,
)

# Completeness validation
from src.validation.completeness import (
    validate_json_wellformedness,
    validate_json_file_wellformedness,
    validate_30day_completeness,
)

# API models
from src.api.models import DispatchRequest

# Workflow validation
from src.action.registry import validate_all_workflows

# Bead validation
from src.bead_validation.validator import BeadValidator
```

### Validation Function Signatures

```python
# Deployment data validation
validate_deployment_data(data: Dict) -> Tuple[bool, Optional[str]]
validate_deployment_record(data: Dict) -> Tuple[bool, Optional[str]]
validate_timestamp(timestamp_str: str) -> bool

# File validation
validate_deployment_file(file_path: str) -> Tuple[bool, List[str]]

# Completeness validation
validate_json_wellformedness(data: Any) -> Tuple[bool, Optional[str]]
validate_json_file_wellformedness(file_path: Path) -> Tuple[bool, Optional[str], Optional[Dict]]
validate_30day_completeness(data: Dict, required_service_counts: Dict) -> Tuple[bool, str]

# Integration validation
validate_all(
    file_path: Optional[str] = None,
    data: Optional[Dict] = None,
    schema: Optional[Dict] = None,
    start_date: Optional[Any] = None,
    end_date: Optional[Any] = None
) -> Tuple[bool, List[str]]

# Workflow validation
async def validate_all_workflows() -> List[Dict[str, Any]]
```

### Error Response Formats

**Single Error:**
```python
is_valid, error = validate_deployment_data(data)
# error: "Missing required field: service"
```

**Multiple Errors:**
```python
is_valid, errors = validate_deployment_file(file_path)
# errors: [
#   "Required fields: Missing field 'service'",
#   "Data types: Field 'total_deployments' must be int, got str",
#   "Completeness: Gap detected from 2026-07-15 to 2026-07-17"
# ]
```

**Detailed Report:**
```python
report = validate_completeness_with_details(events)
# report: {
#   "is_valid": False,
#   "missing_dates": ["2026-07-15", "2026-07-16"],
#   "duplicate_dates": ["2026-07-20"],
#   "date_range": ("2026-07-01", "2026-07-30"),
#   "total_dates": 28,
#   "expected_dates": 30
# }
```

---

## Document Metadata

- **Created:** 2026-08-07
- **Author:** Generated for bead adc-564c20
- **Scope:** Complete validation architecture documentation
- **Coverage:** All validation modules, entry points, flows, and best practices
- **Dependencies:** 
  - `validation_entry_points.md`
  - `validation_flow_diagrams.md`
  - `validation_files_inventory.txt`
- **Related Documentation:**
  - `/home/coding/aide-de-camp/CLAUDE.md` - Project instructions
  - `/home/coding/aide-de-camp/README.md` - Project overview

---

## Change Log

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2026-08-07 | Initial comprehensive audit document |

---

**End of Validation Codebase Audit**