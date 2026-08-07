# Validation Codebase Audit

**Generated:** 2026-08-07  
**Purpose:** Comprehensive inventory of all validation-related code in the aide-de-camp schema implementation

## Overview

The aide-de-camp project implements a multi-layered validation system covering:
- API request validation (Pydantic models)
- Deployment data schema validation
- Bead safety/validation enforcement
- Temporal completeness validation (30-day requirements)
- Runtime validation exception handling

**Statistics:**
- 340+ Pydantic model definitions and field definitions
- 50+ validation functions across the codebase
- 30+ `@field_validator` decorators
- 20+ validation-related test files
- 10+ JSON schema files
- 3 main validation modules

## 1. Core Validation Modules

### 1.1 Deployment Validator Module
**Location:** `src/validation/deployment_validator.py`

**Key Functions:**
```python
validate_timestamp(timestamp_str: str) -> Tuple[bool, Optional[str]]
validate_field_type(value: Any, expected_types: tuple, field_name: str, is_optional: bool = False) -> Tuple[bool, Optional[str]]
validate_metadata(metadata: Dict[str, Any]) -> Tuple[bool, List[str]]
validate_cluster_deployments(cluster_deployments: Dict[str, Any]) -> Tuple[bool, List[str]]
validate_summary(summary: Dict[str, Any]) -> Tuple[bool, List[str]]
validate_deployment_data(data: Dict[str, Any]) -> Tuple[bool, Optional[str]]
```

**Purpose:** Core validation logic for deployment data structures, type checking, and metadata validation.

### 1.2 Completeness Validator Module
**Location:** `src/validation/validate_completeness.py`

**Key Functions:**
```python
validate_completeness(data: List[Dict[str, Any]]) -> Tuple[bool, str]
validate_completeness_with_details(data: List[Dict[str, Any]]) -> Dict[str, Any]
```

**Purpose:** Validates 30-day temporal completeness requirements for deployment datasets.

### 1.3 Unified Validation Runner
**Location:** `src/validation/runner.py`

**Key Functions:**
```python
validate_deployment_file(file_path: str) -> Tuple[bool, List[str]]
```

**Purpose:** Orchestrates comprehensive deployment file validation by chaining multiple validation steps.

### 1.4 Validation Integration Module
**Location:** `src/validation/integration.py`

**Key Functions:**
```python
validate_all(file_path: Optional[str] = None, data: Optional[Dict] = None) -> Tuple[bool, List[str]]
```

**Purpose:** Chains all validation steps and collects errors from multiple validators.

### 1.5 Completeness Module
**Location:** `src/validation/completeness.py`

**Purpose:** JSON completeness validation for deployment data structures.

### 1.6 Deployment Data Module
**Location:** `src/validation/deployment_data.py`

**Purpose:** Deployment data validation functions and utilities.

## 2. Bead Validation System

### 2.1 Bead Validator
**Location:** `src/bead_validation/validator.py`

**Key Methods:**
```python
class BeadValidator:
    def validate_bead_body(self, bead_body: str, bead_type: str = "task") -> ValidationResult
    def _is_informational_bead(self, bead_body: str, body_lower: str) -> bool
    def _is_mutation_bead(self, body_lower: str) -> bool
    def _check_forbidden_kubectl_verbs(self, bead_body: str, body_lower: str) -> list[Violation]
    def _check_gitops_requirement(self, bead_body: str, body_lower: str) -> list[Violation]
    def _check_scoping_requirement(self, bead_body: str, body_lower: str) -> list[Violation]
```

**Purpose:** Enforces GitOps safety rules and organizational policies on bead bodies before creation.

**Validation Rules:**
- Forbidden kubectl verbs detection (apply, delete, patch, edit, etc.)
- GitOps requirement enforcement (declarative-config changes only)
- Scoping requirement validation (cluster-specific restrictions)
- Informational vs. mutation bead classification

### 2.2 Bead Validation Models
**Location:** `src/bead_validation/models.py`

**Purpose:** Validation models and enums for bead validation system.

### 2.3 Bead Validation Exceptions
**Location:** `src/bead_validation/exceptions.py`

**Purpose:** Custom validation exceptions for bead validation errors.

## 3. Schema Definitions

### 3.1 Whisper STT Simplified Schema
**Location:** `src/schemas/whisper_stt_simplified.py`

**Pydantic Models:**
```python
class DeploymentMetadata(BaseModel):
    """Dataset metadata with 3 required fields"""
    dataset_name: str
    time_step_size_seconds: int
    generated_at: str

class ServiceSummary(BaseModel):
    """Service-level summaries with 23 fields per service"""
    service_name: str
    cluster: str
    namespace: str
    # ... 20 more fields

class DeploymentRecord(BaseModel):
    """Individual deployment records with 13 fields"""
    deployment_timestamp: str
    deployment_status: DeploymentStatus
    failure_type: Optional[FailureType]
    # ... 10 more fields

class WhisperSTTDeploymentSchema(BaseModel):
    """Complete schema with metadata, summaries, and deployment_records"""
    metadata: DeploymentMetadata
    summaries: List[ServiceSummary]
    deployment_records: List[DeploymentRecord]
```

**Enums:**
- `HealthStatus`: healthy, degraded, unhealthy, unknown
- `StabilityLevel`: high, medium, low, unknown
- `DeploymentStatus`: success, failed, pending, rollback
- `FailureType`: image_pull_error, crash_loop_back_off, oom_killed, etc.

**Field Validators (30+ total):**
```python
@field_validator('deployment_timestamp')
@classmethod
def validate_timestamp(cls, v: str) -> str:
    """ISO 8601 timestamp validation"""

@field_validator('source_files')
@classmethod
def validate_unique_source_files(cls, v: List[str]) -> List[str]:
    """Ensures source file uniqueness"""

@field_validator('ready_replicas')
@classmethod
def validate_ready_replicas(cls, v: int) -> int:
    """Ensures replica counts don't exceed limits"

# ... 27 more field validators
```

### 3.2 Whisper STT Deployment Schema
**Location:** `src/schemas/whisper_stt_deployment.py`

**Purpose:** Deployment-specific schema definitions for Whisper STT service.

### 3.3 JSON Schema Files
**Locations:**
- `schemas/core-deployment-schema.json` - Core deployment JSON schema
- `schemas/core-deployment-schema-30day-completeness.json` - 30-day completeness schema

## 4. API Model Validation

### 4.1 Dispatch Request Model
**Location:** `src/api/models.py`

**Pydantic Model:**
```python
class DispatchRequest(BaseModel):
    utterance: str
    session_id: str
    surface_id: str
    utterance_id: Optional[str]
    
    @field_validator('utterance')
    @classmethod
    def utterance_must_be_non_empty(cls, v: str) -> str:
        """Validates utterance is non-empty string"""
```

**Purpose:** API request validation for the dispatch endpoint.

### 4.2 Action Models
**Location:** `src/action/models.py`

**Models:**
- `ExecutionContext` - Context for workflow execution
- `StepResult` - Result of single workflow step
- `ActionResult` - Result of action workflow execution
- `Step` - Base class for workflow step types

## 5. Runtime Validation Integration

### 5.1 FastAPI Exception Handler
**Location:** `src/main.py`

```python
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc: RequestValidationError):
    """Handle Pydantic validation errors with clear error messages."""
```

**Purpose:** Global exception handler for API validation errors.

### 5.2 Deployment Persistence Validation
**Location:** `src/persistence/deployment_persistence.py`

```python
from pydantic import ValidationError

try:
    deployment_data = WhisperSTTDeploymentData(**data)
except ValidationError as e:
    raise DeploymentPersistenceError("Invalid deployment data schema")
```

**Purpose:** Validates deployment data before persistence.

### 5.3 Escalate Handler Validation
**Location:** `src/escalate/handler.py`

```python
from ..bead_validation import get_validator, ValidationResult, ValidationError, ValidationRetryExhaustedError

validator = get_validator()
result = validator.validate_bead_body(bead_body, bead_type="task")
```

**Purpose:** Validates bead bodies before creation in the escalate flow.

## 6. Standalone Validation Scripts

### 6.1 Deployment Data Validators
**Locations:**
- `validate_deployment_data.py` - Command-line deployment data validation
- `validate_deployment_data_schema.py` - Schema validation
- `validate_30day_completeness.py` - 30-day completeness validation
- `validate_deployment_files.py` - Batch file validation
- `validate_whisper_stt_deployment.py` - Whisper STT specific validation

### 6.2 Verification Scripts
**Locations:**
- `verify_timestamp_consistency.py` - Timestamp consistency verification
- `verify_extraction_results.py` - Extraction results verification
- `verify_storage_and_sse.py` - Storage and SSE verification
- `verify_migration.py` - Migration verification

### 6.3 Schema Validation Scripts
**Locations:**
- `schemas/validate_core_schema.py` - Validates JSON schemas
- `schemas/validate_30day_completeness.py` - Validates 30-day completeness

## 7. Validation Entry Points

### 7.1 API Entry Points

#### Dispatch Endpoint
**Location:** `src/main.py`
```python
@app.post("/dispatch")
async def dispatch(request: DispatchRequest):
    # Pydantic validates request automatically
```

**Validation Flow:**
1. FastAPI receives POST /dispatch request
2. Pydantic validates against `DispatchRequest` model
3. `utterance_must_be_non_empty` validator runs
4. On failure: `RequestValidationError` exception handler catches
5. On success: request proceeds to intent router

#### Voice Session Endpoint
**Location:** `src/main.py`
```python
@app.websocket("/ws/voice/{session_id}")
async def voice_session(websocket: WebSocket, session_id: str):
    # Session parameter validation
```

### 7.2 Escalate Flow Entry Point

**Location:** `src/escalate/handler.py`

**Validation Flow:**
1. User submits task requiring bead creation
2. `validator.validate_bead_body(bead_body, bead_type="task")` called
3. BeadValidator checks:
   - Forbidden kubectl verbs
   - GitOps requirements
   - Scoping requirements
4. Result classification:
   - `result.requires_approval` → Show approval card
   - `not result.is_valid` → Trigger re-formulation
   - `result.is_valid` → Proceed to bead creation

### 7.3 Deployment Data Persistence Entry Point

**Location:** `src/persistence/deployment_persistence.py`

**Validation Flow:**
1. Deployment data received for storage
2. `WhisperSTTDeploymentData(**data)` Pydantic validation
3. All 30+ field validators run
4. On failure: `DeploymentPersistenceError` raised
5. On success: Data persisted to SQLite

### 7.4 Integration Validation Entry Point

**Location:** `src/validation/integration.py`

**Validation Flow:**
1. `validate_all(file_path, data)` called
2. Loads deployment data (from file or dict)
3. Runs validation pipeline:
   - JSON well-formedness
   - Required fields presence
   - Type checking
   - Completeness validation
4. Returns `(is_valid, error_list)`

## 8. Validation Patterns

### 8.1 Pydantic-Based Schema Validation
**Usage:** API requests, deployment data, configuration models

**Pattern:**
```python
class Model(BaseModel):
    field: type
    
    @field_validator('field')
    @classmethod
    def validate_field(cls, v: type) -> type:
        # Validation logic
        return v
```

**Benefits:**
- Automatic type checking
- Clear error messages
- IDE type hints support
- Serialization/deserialization

### 8.2 Deterministic Safety Validation
**Usage:** Bead body validation (GitOps enforcement)

**Pattern:**
```python
class BeadValidator:
    def validate_bead_body(self, bead_body: str, bead_type: str) -> ValidationResult:
        # Check forbidden patterns
        violations = []
        violations.extend(self._check_forbidden_kubectl_verbs(bead_body, body_lower))
        violations.extend(self._check_gitops_requirement(bead_body, body_lower))
        # Return result with violations
```

**Benefits:**
- Prevents dangerous operations
- Enforces organizational policies
- Clear violation reporting
- Approval workflow integration

### 8.3 Temporal Validation
**Usage:** 30-day completeness requirements

**Pattern:**
```python
def validate_completeness(data: List[Dict[str, Any]]) -> Tuple[bool, str]:
    # Check time step size consistency
    # Validate expected record count
    # Check for gaps in time series
    return (is_valid, error_message)
```

**Benefits:**
- Ensures data completeness
- Detects missing time periods
- Validates aggregation requirements

### 8.4 Multi-Stage Validation
**Usage:** Comprehensive deployment file validation

**Pattern:**
```python
def validate_all(file_path: Optional[str] = None, data: Optional[Dict] = None):
    # Stage 1: JSON well-formedness
    # Stage 2: Required fields
    # Stage 3: Type checking
    # Stage 4: Completeness validation
    # Collect all errors
    return (is_valid, all_errors)
```

**Benefits:**
- Complete error reporting
- Early failure detection
- Clear validation pipeline

### 8.5 Exception-Based Validation
**Usage:** Runtime validation with custom error types

**Pattern:**
```python
try:
    # Validation operation
    result = validate(data)
except ValidationError as e:
    # Handle validation error
except ValidationRetryExhaustedError as e:
    # Handle retry exhaustion
```

**Benefits:**
- Clear error types
- Exception handling flow
- Retry logic support

## 9. Validation Flow Diagrams

### 9.1 API Request Validation Flow

```
Client Request
    ↓
FastAPI POST /dispatch
    ↓
Pydantic DispatchRequest Validation
    ↓
utterance_must_be_non_empty Validator
    ↓
[Valid?] → Yes → Intent Router
    ↓
No → RequestValidationError Handler
    ↓
Error Response (400)
```

### 9.2 Bead Creation Validation Flow

```
User Submits Task
    ↓
Escalate Handler
    ↓
BeadValidator.validate_bead_body()
    ↓
Forbidden kubectl verbs check
    ↓
GitOps requirement check
    ↓
Scoping requirement check
    ↓
[Requires Approval?] → Yes → Approval Card
    ↓
No
    ↓
[Valid?] → Yes → Create Bead
    ↓
No → Re-formulation Prompt
```

### 9.3 Deployment Data Validation Flow

```
Deployment Data Received
    ↓
WhisperSTTDeploymentData(**data) Pydantic Validation
    ↓
Metadata Validation
    ↓
Service Summaries Validation (23 fields × N services)
    ↓
Deployment Records Validation (13 fields × N records)
    ↓
[All Valid?] → Yes → Persist to SQLite
    ↓
No → DeploymentPersistenceError
```

## 10. Validation Test Coverage

### 10.1 Test Files
The codebase includes 20+ validation-related test files covering:
- Pydantic model validation tests
- Bead validation rule tests
- Deployment data validation tests
- Completeness validation tests
- Integration validation tests

### 10.2 Test Categories
- Unit tests for individual validators
- Integration tests for validation pipelines
- Exception handling tests
- Edge case coverage tests
- Error message clarity tests

## 11. Key Validation Dependencies

### 11.1 External Libraries
- `pydantic` - Core validation framework
- `fastapi` - API validation integration
- `jsonschema` - JSON schema validation

### 11.2 Internal Dependencies
- `src/schemas/` - Schema definitions
- `src/bead_validation/` - Bead validation system
- `src/validation/` - Core validation modules
- `src/api/models.py` - API request models

## 12. Validation Configuration

### 12.1 Validation Settings
Validation behavior is configured through:
- Pydantic model definitions
- Bead validation patterns
- Schema constraints
- Exception handler configuration

### 12.2 Error Messages
Validation errors provide:
- Clear field identification
- Specific constraint violations
- Suggested corrections (where applicable)
- HTTP status codes (API context)

## Summary

The aide-de-camp validation system is comprehensive and well-structured, covering:

1. **API Layer:** Request validation via Pydantic models
2. **Business Logic Layer:** Bead safety validation and enforcement
3. **Data Layer:** Deployment data schema and completeness validation
4. **Persistence Layer:** Pre-storage validation
5. **Integration Layer:** Unified validation pipeline

The system uses a multi-layered approach with clear separation of concerns, comprehensive error reporting, and integration with FastAPI's exception handling infrastructure.

**Key Strengths:**
- Comprehensive coverage across all layers
- Clear, specific validation rules
- Good error messaging
- Integration with GitOps policies
- Temporal completeness enforcement

**Maintenance Areas:**
- Keep field validators synchronized with schema changes
- Update validation rules as policies evolve
- Maintain test coverage for new validators
- Document validation rule changes
