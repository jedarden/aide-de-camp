# Validation Codebase Audit

## Overview

This document provides a comprehensive inventory of all validation-related code in the aide-de-camp schema implementation, including entry points, validation flow, and triggers.

## Summary

The validation system is organized into several distinct domains:

1. **Deployment Data Validation** - Schema-based validation for deployment datasets
2. **API Request Validation** - Pydantic models for HTTP requests
3. **Action/Workflow Validation** - Registry-based workflow validation
4. **Bead Validation** - Safety checks for escalate-generated beads
5. **Database Schema Validation** - SQLite schema constraints
6. **Utility Validation** - Query syntax, confirmation responses

## 1. Deployment Data Validation

### Core Schema Files

#### `/src/schemas/whisper_stt_simplified.py`
**Purpose**: Pydantic models for simplified, service-agnostic deployment schema

**Key Models**:
- `WhisperSTTDeploymentSchema` - Main schema (39 fields total, 31 required)
- `DeploymentMetadata` - Dataset metadata (3 fields)
- `ServiceSummary` - Service-level summaries (23 fields per service)
- `DeploymentRecord` - Individual deployment records (13 fields per record)

**Validators**:
- `validate_timestamp()` - ISO 8601 timestamp validation
- `validate_unique_source_files()` - Unique source files check
- `validate_last_deployment_timestamp()` - Not in future check
- `validate_ready_replicas()` - ready_replicas ≤ replicas
- `validate_available_replicas()` - available_replicas ≤ replicas
- `validate_running_pods()` - running_pods ≤ total_pods
- `validate_crashloops()` - crashloops ≤ total_pods
- `validate_oomkills()` - oomkills ≤ total_pods
- `validate_incident_counts()` - incident subtypes ≤ total_incidents
- `validate_deployment_counts()` - deployment counts ≤ total_deployments
- `validate_summaries_keys()` - Kubernetes name pattern validation
- `validate_deployment_records()` - Max 10,000 records check
- `validate_metadata_consistency()` - metadata.total_records matches deployment_records length
- `validate_timestamps()` - ISO 8601 date/timestamp formats
- `validate_docker_image()` - Docker image reference format (rejects :latest)
- `validate_revision()` - Numeric string 0-999999
- `validate_replica_counts()` - Replica count constraints
- `validate_failure_type_logic()` - failure_type populated when status='failed'

**Entry Points**:
- Direct instantiation: `WhisperSTTDeploymentSchema(**data)`
- Validation function: `validate_deployment_data(data: dict) -> tuple[bool, list[str]]`

#### `/src/schemas/whisper_stt_deployment.py`
**Purpose**: Pydantic models for whisper-stt specific deployment data

**Key Models**:
- `WhisperSTTDeploymentData` - Complete deployment data structure
- Enum models: `EventType`, `EventOutcome`, `HealthStatus`, `VolumeType`, `SecretType`, `StorageClass`
- Nested models: `TimePeriod`, `Metadata`, `CurrentStatus`, `DeploymentEvent`, etc.

**Entry Points**:
- Direct instantiation: `WhisperSTTDeploymentData(**data)`
- Validation function: `validate_deployment_data(data: dict) -> bool`

### Validation Modules

#### `/src/validation/__init__.py`
**Purpose**: Central export point for all validation functions

**Exports**:
- `validate_deployment_data` - Main validation function
- `validate_deployment_data_simple` - Boolean wrapper
- `validate_deployment_record` - Single record validation
- `validate_timestamp` - ISO 8601 timestamp validation
- `validate_required_fields` - Field presence validation
- `validate_data_types` - Schema type validation
- `validate_json_wellformedness` - JSON parse validation
- `validate_json_file_wellformedness` - File-based JSON validation
- `validate_30day_completeness` - 30-day coverage validation
- `validate_json_completeness` - Generic completeness validation
- `validate_json_file_completeness` - File-based completeness validation
- `validate_deployment_file` - Comprehensive file validation
- `validate_all` - Integration function

#### `/src/validation/deployment_data.py`
**Purpose**: Core deployment data validation functions

**Key Functions**:
- `validate_deployment_data(data: Dict[str, Any]) -> Tuple[bool, Optional[str]]` - Main validation (handles both single records and collections)
- `validate_deployment_record(data: Dict[str, Any]) -> Tuple[bool, Optional[str]]` - Single record validation
- `validate_deployment_data_simple(data: dict) -> bool` - Boolean wrapper
- `validate_required_fields(data: dict) -> Tuple[bool, str]` - Field presence check
- `validate_data_types(data: dict, schema: dict) -> Tuple[bool, str]` - Type validation
- `validate_timestamp(timestamp_str: str) -> bool` - ISO 8601 validation

**Schema Definition**:
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

**Business Logic Validation**:
- successful_deployments + failed_deployments == total_deployments
- success_rate + failure_rate == 100.0 (except when total_deployments is 0)
- Non-negative constraints on numeric fields
- Timestamp field validity

#### `/src/validation/completeness.py`
**Purpose**: JSON well-formedness and 30-day completeness validation

**Key Functions**:
- `validate_json_wellformedness(data: Any) -> Tuple[bool, Optional[str]]` - JSON serialization/deserialization check
- `validate_json_file_wellformedness(file_path: Path) -> Tuple[bool, Optional[str], Optional[Dict]]` - File-based JSON validation
- `parse_date_string(date_str: str) -> datetime` - Multi-format date parser
- `generate_expected_dates(start_date: datetime, end_date: datetime) -> List[datetime]` - Date range generation
- `extract_dates_from_data(data: Dict[str, Any]) -> Set[datetime]` - Date extraction from deployment events
- `validate_30day_completeness(data: Dict[str, Any]) -> Tuple[bool, str]` - 30-day coverage check
- `validate_json_completeness(data: Dict[str, Any], start_date, end_date) -> Tuple[bool, Optional[str]]` - Generic completeness validation
- `validate_json_file_completeness(file_path: Path) -> Tuple[bool, Optional[str], Optional[Dict]]` - File-based completeness validation

**Completeness Checks**:
- No gaps in date coverage
- No duplicate dates
- All expected dates present in data

#### `/src/validation/deployment_validator.py`
**Purpose**: Alternative deployment data validation implementation

**Key Functions**:
- `validate_timestamp(timestamp_str: str) -> Tuple[bool, Optional[str]]`
- `validate_field_type(value: Any, expected_types: tuple, field_name: str, is_optional: bool = False) -> Tuple[bool, Optional[str]]`
- `validate_metadata(metadata: Dict[str, Any]) -> Tuple[bool, List[str]]`
- `validate_cluster_deployments(cluster_deployments: Dict[str, Any]) -> Tuple[bool, List[str]]`
- `validate_summary(summary: Dict[str, Any]) -> Tuple[bool, List[str]]`
- `validate_deployment_data(data: Dict[str, Any]) -> Tuple[bool, Optional[str]]`
- `validate_deployment_data_list(data_list: List[Dict[str, Any]]) -> Tuple[bool, List[str]]`

#### `/src/validation/validate_completeness.py`
**Purpose**: Completeness validation with detailed reporting

**Key Functions**:
- `validate_completeness(data: List[Dict[str, Any]]) -> Tuple[bool, str]`
- `validate_completeness_with_details(data: List[Dict[str, Any]]) -> Dict[str, Any]`

**Returns**: Detailed breakdown of missing dates, gaps, and duplicates

#### `/src/validation/runner.py`
**Purpose**: Unified validation runner for deployment data files

**Key Functions**:
- `validate_deployment_file(file_path: str) -> Tuple[bool, List[str]]` - Comprehensive file validation

**Validation Sequence**:
1. JSON well-formedness (file exists and parseable)
2. Required fields validation
3. Data type validation
4. Completeness validation (30-day coverage, no gaps)

**Helper Functions**:
- `_validate_json_wellformedness(file_path: Path)` - File parse validation
- `_validate_required_fields(data: Dict[str, Any])` - Field presence validation
- `_validate_data_types(data: Dict[str, Any])` - Type validation
- `_validate_completeness(data: Dict[str, Any])` - Completeness validation

#### `/src/validation/integration.py`
**Purpose**: Integration function that chains all validation steps

**Key Functions**:
- `validate_all(file_path: Optional[str] = None, data: Optional[Dict[str, Any]] = None, schema: Optional[Dict[str, Any]] = None, start_date: Optional[Any] = None, end_date: Optional[Any] = None) -> Tuple[bool, List[str]]`

**Validation Sequence**:
1. JSON well-formedness validation (early termination on failure)
2. Required fields validation
3. Data types validation
4. Completeness validation

**Entry Points**:
- File-based: `validate_all(file_path="deployment-data.json")`
- Data-based: `validate_all(data={"service": "pbx-web", ...})`

## 2. API Request Validation

#### `/src/api/models.py`
**Purpose**: Pydantic models for API request/response validation

**Key Models**:
- `DispatchRequest` - POST /dispatch endpoint request validation

**Validators**:
- `utterance_must_be_non_empty()` - Non-empty utterance string
- `session_id_must_be_non_empty()` - Non-empty session ID
- `surface_id_must_be_non_empty()` - Non-empty surface ID
- `validate_optional_utterance_id()` - Optional utterance ID validation

**Triggers**: Automatic on POST /dispatch endpoint via FastAPI

## 3. Action/Workflow Validation

#### `/src/action/registry.py`
**Purpose**: Workflow definition validation from project registry

**Key Functions**:
- `_validate_workflow_steps(project_slug: str, workflow_name: str, steps: list[Any]) -> list[str]` - Workflow step validation
- `_validate_workflow_definition(project_slug: str, workflow_name: str, workflow_config: dict) -> list[str]` - Complete workflow validation
- `validate_all_workflows() -> list[dict[str, Any]]` - All workflows validation

**Known Step Types**:
- ci_status, image_tag, gitops_commit, argocd_sync_status, pod_status
- deployment_info, git_log, argocd_apps, open_beads

**Validation Rules**:
- steps must be a list
- workflow must have at least one step
- each step must be a string
- each step must be in known_steps set

**Triggers**: Registry loading and workflow execution

#### `/src/action/manifest_template.py`
**Purpose**: ArgoCD manifest template validation

**Key Functions**:
- `validate(self) -> None` - Manifest validation method
- `_validate_field_allowed(self, path: str) -> None` - Field permission validation

**Triggers**: Template generation and application

#### `/src/action/steps/gitops.py`
**Purpose**: GitOps step validation

**Key Functions**:
- `validate(self) -> None` - Step validation
- `_validate_declarative_config_repo(self) -> None` - Repository validation
- `_parse_and_validate_fields(self, template_fields: list[dict[str, Any]]) -> list[TemplateField]` - Field validation

**Triggers**: GitOps workflow step execution

## 4. Bead Validation

#### `/src/bead_validation/validator.py`
**Purpose**: Deterministic safety checks for escalate-generated beads

**Key Functions**:
- `validate_bead_body(bead_body: str, bead_type: BeadType, max_retries: int = 3) -> ValidationResult` - Main bead validation

**Deny-list Patterns**:
- FORBIDDEN_KUBECTL_VERBS: apply, create, delete, scale, patch, edit, annotate, rollout, replace, cordon, uncordon, drain, taint
- KUBECTL_DIRECT_PATTERNS: Direct kubectl usage patterns

**GitOps-Approved Patterns**:
- edit.*declarative-config
- edit.*k8s/
- jedarden/declarative-config
- argocd app
- git push.*declarative

**Scoping Requirements**:
- cluster:\s*\S+
- namespace:\s*\S+
- pod:\s*\S+
- deployment:\s*\S+

**Informational Patterns** (no approval needed):
- look( up| at| into)?, check, show, display, list, describe, get, status, health

**Triggers**: Bead creation via bead-forge CLI

#### `/src/bead_validation/models.py`
**Purpose**: Bead validation data models

**Key Models**:
- `ValidationResult` - Validation result with approval requirements
- `ApprovalRequirement` - Approval requirement types
- `ValidationRule` - Validation rule definitions
- `Violation` - Validation violation details
- `BeadType` - Bead type enumeration

## 5. Database Schema Validation

#### `/src/session/store.py`
**Purpose**: SQLite database schema with CHECK constraints

**Schema Validations**:
- Surfaces.type: CHECK(type IN ('canvas', 'telegram', 'audio'))
- Surfaces.state: CHECK(state IN ('active', 'idle', 'disconnected'))
- Surfaces.always_available: CHECK(always_available IN (0, 1))
- Intents.status: CHECK(status IN ('pending', 'dispatched', 'resolved', 'cancelled'))
- Results.urgency: CHECK(urgency IN ('critical', 'high', 'normal', 'low'))

**Triggers**: Automatic on INSERT/UPDATE via SQLite constraints

## 6. Utility Validation

#### `/src/victorialogs_queries.py`
**Purpose**: Victorialogs query syntax validation

**Key Functions**:
- `validate_query_syntax(query: str) -> bool` - Query syntax validation

**Triggers**: Query execution

#### `/src/victorialogs_latency_queries.py`
**Purpose**: Victorialogs latency query validation

**Key Functions**:
- `validate_query_syntax(query: str) -> Dict[str, Any]` - Detailed query validation

**Triggers**: Latency query execution

#### `/src/confirmations/prompts.py`
**Purpose**: Confirmation response validation

**Key Functions**:
- `async def validate_confirmation_response(confirmation_id: str, response: dict) -> dict` - Confirmation validation

**Triggers**: User confirmation response handling

#### `/src/registry.py`
**Purpose**: Project registry validation

**Key Functions**:
- `_validate_project_entry(slug: str, entry: dict) -> list[str]` - Project entry validation
- `_validate_registry(registry: dict) -> None` - Registry structure validation

**Triggers**: Registry loading and caching

## Validation Triggers Summary

### Automatic Triggers
1. **API Requests**: FastAPI automatically validates DispatchRequest models
2. **Database Operations**: SQLite CHECK constraints validate on INSERT/UPDATE
3. **Pydantic Model Instantiation**: Validators run on model construction

### Manual Triggers
1. **File Validation**: `validate_deployment_file(file_path)`
2. **Data Validation**: `validate_all(data=data)`
3. **Workflow Validation**: `validate_all_workflows()`
4. **Bead Validation**: `validate_bead_body(bead_body, bead_type)`
5. **Query Validation**: `validate_query_syntax(query)`

### Entry Points by Use Case

**Deployment Data Validation**:
- `validate_deployment_file(path)` - File validation
- `validate_all(data=data)` - Data validation
- `validate_deployment_data(data)` - Quick validation

**API Request Validation**:
- Automatic via FastAPI + Pydantic

**Workflow Validation**:
- `validate_all_workflows()` - Registry validation
- Automatic on workflow execution

**Bead Validation**:
- `validate_bead_body(bead_body, bead_type)` - Pre-creation validation

**Utility Validation**:
- `validate_query_syntax(query)` - Query validation
- `validate_confirmation_response()` - Confirmation validation

## Validation Flow Diagrams

### Deployment Data Validation Flow

```
User/API Request
    ↓
validate_deployment_file(file_path)
    ↓
┌─────────────────────────────────┐
│ 1. JSON Well-formedness        │
│    - File exists?               │
│    - Parseable JSON?           │
│    Early termination on failure │
└─────────────────────────────────┘
    ↓
┌─────────────────────────────────┐
│ 2. Required Fields              │
│    - All required fields present?│
└─────────────────────────────────┘
    ↓
┌─────────────────────────────────┐
│ 3. Data Types                   │
│    - Correct types for fields?  │
└─────────────────────────────────┘
    ↓
┌─────────────────────────────────┐
│ 4. Completeness                 │
│    - 30-day coverage?           │
│    - No gaps/duplicates?        │
└─────────────────────────────────┘
    ↓
Return (is_valid, error_messages)
```

### API Request Validation Flow

```
POST /dispatch
    ↓
FastAPI Request Processing
    ↓
DispatchRequest Model Instantiation
    ↓
┌─────────────────────────────────┐
│ Pydantic Field Validators       │
│ - utterance_must_be_non_empty   │
│ - session_id_must_be_non_empty  │
│ - surface_id_must_be_non_empty  │
│ - validate_optional_utterance_id│
└─────────────────────────────────┘
    ↓
ValidationError (if invalid) → 422 response
Valid request → Business logic
```

### Bead Validation Flow

```
Bead Creation Request
    ↓
validate_bead_body(bead_body, bead_type)
    ↓
┌─────────────────────────────────┐
│ 1. Pattern Matching             │
│    - Forbidden kubectl verbs?    │
│    - GitOps-approved patterns?  │
│    - Scoping present?           │
└─────────────────────────────────┘
    ↓
┌─────────────────────────────────┐
│ 2. Classification               │
│    - Informational? (no approval)│
│    - Mutational? (requires approval)│
└─────────────────────────────────┘
    ↓
Return ValidationResult
    ↓
┌─────────────────────────────────┐
│ Action Based on Result          │
│ - Valid & no approval: create   │
│ - Valid & requires approval: prompt│
│ - Invalid: trigger reformulation│
└─────────────────────────────────┘
```

## Related Files

### Test Files
- `/tests/validation/test_dispatch_request_validation.py`
- `/tests/validation/test_single_validation_failures.py`
- `/tests/validation/test_multi_failure_validation.py`
- `/tests/unit/test_completeness_validation.py`
- `/tests/unit/test_deployment_data_validation.py`
- `/tests/unit/test_validate_completeness.py`
- `/tests/unit/test_validation_integration.py`
- `/tests/unit/test_validation_runner.py`

### Standalone Validation Scripts
- `/schemas/validate_30day_completeness.py`
- `/schemas/validate_30day_completeness_combined.py`
- `/schemas/validate_core_schema.py`
- `/validate_deployment_data.py`
- `/validate_deployment_data_schema.py`
- `/validate_whisper_stt_deployment.py`

### JSON Schema Files
- `/schemas/core-deployment-schema-30day-completeness.json`
- `/schemas/core-deployment-schema.json`
- `/schemas/core-deployment-schema-with-completeness.json`

## Key Validation Patterns

### Pydantic Model Validation
- Field-level constraints (min_length, max_length, pattern)
- Custom @field_validator decorators
- Cross-field validation (using `info.data`)
- Business logic validation in validators

### Functional Validation
- Tuple return pattern: `(is_valid: bool, error_message: str)`
- Early termination on fatal errors
- Error collection for non-fatal validation
- Nested validation for complex structures

### Integration Validation
- Sequential validation steps
- Error accumulation across steps
- Early termination on parse failures
- Comprehensive error reporting

## Maintenance Notes

### Adding New Validation
1. Create validator function with `(is_valid, error_message)` return pattern
2. Add to appropriate module (deployment_data.py, completeness.py, etc.)
3. Export from `/src/validation/__init__.py`
4. Add to `validate_all()` integration function if needed
5. Add unit tests in `/tests/validation/` or `/tests/unit/`

### Modifying Existing Validation
1. Update validator function
2. Update related tests
3. Update this documentation
4. Consider backward compatibility

### Validation Performance
- Early termination on JSON parse failures
- Lazy validation (only when needed)
- Caching of expensive validations
- Concurrent-safe validation with retry logic

---

**Last Updated**: 2026-08-07  
**Audit Scope**: All validation-related code in `/src/`  
**Total Validation Modules**: 10  
**Total Validation Functions**: 50+  
**Pydantic Models with Validators**: 15+  
**Database CHECK Constraints**: 5