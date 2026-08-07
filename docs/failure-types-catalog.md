# Failure Types Catalog

A comprehensive catalog of all failure types in the aide-de-camp system.

## Overview

This document catalogs all unique failure types, exceptions, and errors used throughout the aide-de-camp codebase. Each entry includes:
- **Type**: The exception/failure type name
- **Description**: What the failure type represents
- **Location**: Where it is defined in the codebase
- **Usage**: Where and how it is used

---

## 1. Validation Failures

### ValidationError
- **Description**: Base exception for validation errors
- **Location**: `src/bead_validation/exceptions.py:6`
- **Usage**: Used as the base exception for all validation-related errors in the bead validation system

### ValidationRetryExhaustedError
- **Description**: Raised when re-formulation retry is exhausted after validation failures
- **Location**: `src/bead_validation/exceptions.py:11`
- **Usage**: Thrown when a bead body fails validation multiple times and re-formulation attempts are exhausted (max 3 attempts per session)
- **Attributes**: `original_violations` - list of validation violations that triggered the failure

### RegistryValidationError
- **Description**: Raised when the registry schema is invalid
- **Location**: `src/registry.py:116`
- **Usage**: Thrown when the project registry configuration fails schema validation
- **Attributes**: `errors` - list of specific validation error messages

### FetchConfigValidationError
- **Description**: Raised when the fetch config schema is invalid
- **Location**: `src/fetch/commands.py:86`
- **Usage**: Thrown when the fetch configuration file fails validation
- **Attributes**: `errors` - list of validation error messages

### WorkflowValidationError
- **Description**: Raised when a workflow definition is invalid
- **Location**: `src/action/registry.py:43`
- **Usage**: Thrown when workflow definitions in project registry fail validation
- **Attributes**: `project_slug`, `workflow_name`, `errors`

---

## 2. LLM & Parsing Failures

### ParseLLMError
- **Description**: Raised when LLM response parsing fails
- **Location**: `src/llm/response_parser.py:58`
- **Usage**: Thrown when parsing LLM responses (JSON extraction, markdown fence stripping, ZAI proxy unwrapping) fails
- **Attributes**: `raw_response` - the raw LLM response text that failed parsing (preserved for debugging)
- **Recovery Patterns**:
  - Corrective Retry Pattern: Used when LLM call is early in pipeline (router retries once)
  - Fallback Result Pattern: Used after expensive operations (synthesize returns degraded result)

---

## 3. Escalation & Bead Failures

### EscalateError
- **Description**: Base exception for escalate errors
- **Location**: `src/escalate/handler.py:120`
- **Usage**: Base class for all escalation-related failures

### BeadCreationError
- **Description**: Bead creation failed
- **Location**: `src/escalate/handler.py:125`
- **Usage**: Thrown when bf CLI fails to create a bead (CLI not found, execution failure, etc.)
- **Inherits from**: `EscalateError`

### BeadApprovalRequired
- **Description**: Bead requires user approval before creation
- **Location**: `src/escalate/handler.py:130`
- **Usage**: Raised when validation passes but requires user approval; carries approval card details
- **Attributes**: `approval_card`, `bead_body`, `bead_type`
- **Inherits from**: `EscalateError`

---

## 4. Command Execution Failures

### CommandExecutionError
- **Description**: Command execution failed
- **Location**: `src/escalate/commands.py:19`
- **Usage**: Thrown when auto-approved kubectl or git commands fail to execute

---

## 5. Git Operation Failures

### GitError
- **Description**: Base exception for git operation failures
- **Location**: `src/action/steps/gitops.py:32`
- **Usage**: Base class for all git-related failures in GitOps operations

### GitConflictError
- **Description**: Raised when git operations encounter merge conflicts or rejection
- **Location**: `src/action/steps/gitops.py:37`
- **Usage**: Thrown on merge conflicts, non-fast-forward push rejections
- **Inherits from**: `GitError`

### GitNetworkError
- **Description**: Raised when git operations fail due to network issues
- **Location**: `src/action/steps/gitops.py:42`
- **Usage**: Thrown on connection failures, timeouts, DNS issues
- **Retry**: Has retry decorator with exponential backoff (max 3 retries, 1.5x backoff factor)
- **Inherits from**: `GitError`

### GitAuthenticationError
- **Description**: Raised when git operations fail due to authentication issues
- **Location**: `src/action/steps/gitops.py:47`
- **Usage**: Thrown on credential failures, permission denied, authentication errors
- **Inherits from**: `GitError`

### GitStateError
- **Description**: Raised when git repository is in an unexpected state
- **Location**: `src/action/steps/gitops.py:52`
- **Usage**: Thrown when repository has uncommitted changes, is on wrong branch, or has invalid state
- **Inherits from**: `GitError`

---

## 6. Persistence Failures

### DeploymentPersistenceError
- **Description**: Custom exception for deployment persistence operations
- **Location**: `src/persistence/deployment_persistence.py:29`
- **Usage**: Thrown when reading/writing deployment data fails (file I/O, JSON parsing, validation)
- **Attributes**: `message`, `filepath`, `original_error`

---

## 7. Configuration & Hot-Reload Failures

### HotReloadError
- **Description**: Base exception for hot-reload errors
- **Location**: `src/components/hot_reload.py:31`
- **Usage**: Base class for all hot-reload related failures

### PermissionDeniedError
- **Description**: Raised when file permission is denied
- **Location**: `src/components/hot_reload.py:36`
- **Usage**: Thrown when hot-reload cannot read a file due to insufficient permissions
- **Attributes**: `path`, `operation`
- **Inherits from**: `HotReloadError`

### RegistryNotFoundError
- **Description**: Raised when registry file is not found
- **Location**: `src/components/hot_reload.py:49`
- **Usage**: Thrown when hot-reload cannot locate a registry file
- **Attributes**: `path`
- **Inherits from**: `HotReloadError`

### RegistryParseError
- **Description**: Raised when registry file parsing fails
- **Location**: `src/components/hot_reload.py:61`
- **Usage**: Thrown when YAML/JSON parsing of registry files fails
- **Attributes**: `path`, `parse_error`, `content_preview`
- **Inherits from**: `HotReloadError`

### EmptyRegistryError
- **Description**: Raised when registry file is empty or contains no data
- **Location**: `src/components/hot_reload.py:81`
- **Usage**: Thrown when registry file exists but has no valid content
- **Attributes**: `path`
- **Inherits from**: `HotReloadError`

---

## 8. ArgoCD Resolution Failures

### ArgocdEndpointUnresolvable
- **Description**: Raised when an ArgoCD query cannot be issued without risking the wrong instance
- **Location**: `src/fetch/clusters.py:194`
- **Usage**: Thrown when cluster → ArgoCD endpoint resolution fails (unmapped cluster, unsupported access mode, no read-only proxy)
- **Attributes**: `reason`, `cluster`
- **Recovery**: Fetch strand treats this as a failed source and emits a fetch_coverage caveat

---

## 9. CLI & Confirmation Failures

### CLIError
- **Description**: Base exception for CLI errors
- **Location**: `src/cli/main.py`
- **Usage**: Base class for CLI-related failures

### ConnectionError
- **Description**: CLI connection error
- **Location**: `src/cli/main.py`
- **Usage**: Thrown when CLI cannot connect to the aide-de-camp server
- **Inherits from**: `CLIError`

### ConfirmationPromptError
- **Description**: Base exception for confirmation prompt errors
- **Location**: `src/confirmations/prompts.py`
- **Usage**: Base class for confirmation-related failures

### ConfirmationPromptExpired
- **Description**: Raised when a confirmation prompt has expired
- **Location**: `src/confirmations/prompts.py`
- **Usage**: Thrown when user tries to respond to an expired confirmation prompt
- **Inherits from**: `ConfirmationPromptError`

---

## 10. Action & Template Failures

### ValidationError (Action Template)
- **Description**: Raised when action manifest template validation fails
- **Location**: `src/action/manifest_template.py`
- **Usage**: Thrown when action manifest templates fail validation

---

## 11. Terminal Failure Constants

### ALL_SOURCES_FAILED
- **Description**: Constant indicating all fetch sources failed
- **Location**: `src/sse/broadcaster.py`
- **Usage**: Used as a terminal failure flag when all data sources fail in the fetch orchestrator
- **Value**: `"all_sources_failed"`

### has_required_failure
- **Description**: Flag indicating required sources failed
- **Location**: `src/fetch/commands.py` (FetchCoverage)
- **Usage**: Boolean flag set when required fetch sources fail, making the result incomplete

### terminal_failure
- **Description**: Field for terminal failure type
- **Location**: `src/fetch/orchestrator.py` (FetchResult)
- **Usage**: Set to `"all_sources_failed"` when all sources fail, indicating no data could be retrieved

---

## 12. Watcher & Bead Refusal Failures

### Refusal (Not an exception, but a failure mode)
- **Description**: Bead refusal by NEEDLE worker
- **Location**: `src/watcher/daemon.py`
- **Usage**: Tracked via `bead_watch.refusal_count` and `bead_watch.last_refusal_reason`
- **Thresholds**:
  - 3 refusals → bead fenced
  - 24 hours age → bead fenced
- **Recovery**: Fenced beads are marked as failed in the intent store

---

## Summary Statistics

- **Total Exception Classes**: 30
- **Total Base Exceptions**: 6 (ValidationError, EscalateError, GitError, HotReloadError, CLIError, ConfirmationPromptError)
- **Total Specialized Exceptions**: 24
- **Terminal Failure Constants**: 3
- **Modules with Exceptions**: 13

## Exception Hierarchy

```
Exception
├── ValidationError
│   └── ValidationRetryExhaustedError
├── EscalateError
│   ├── BeadCreationError
│   └── BeadApprovalRequired
├── GitError
│   ├── GitConflictError
│   ├── GitNetworkError
│   ├── GitAuthenticationError
│   └── GitStateError
├── HotReloadError
│   ├── PermissionDeniedError
│   ├── RegistryNotFoundError
│   ├── RegistryParseError
│   └── EmptyRegistryError
├── CLIError
│   └── ConnectionError
├── ConfirmationPromptError
│   └── ConfirmationPromptExpired
└── [Other standalone exceptions]
    ├── RegistryValidationError
    ├── FetchConfigValidationError
    ├── WorkflowValidationError
    ├── ParseLLMError
    ├── CommandExecutionError
    ├── DeploymentPersistenceError
    ├── ArgocdEndpointUnresolvable
    └── ValidationError (action manifest template)
```

## Failure Categories by Layer

1. **Validation Layer**: ValidationError, ValidationRetryExhaustedError, RegistryValidationError, FetchConfigValidationError, WorkflowValidationError
2. **LLM/Parsing Layer**: ParseLLMError
3. **Escalation Layer**: EscalateError, BeadCreationError, BeadApprovalRequired
4. **Execution Layer**: CommandExecutionError, GitError and subclasses
5. **Persistence Layer**: DeploymentPersistenceError
6. **Configuration Layer**: HotReloadError and subclasses
7. **Cluster/Infrastructure Layer**: ArgocdEndpointUnresolvable
8. **CLI Layer**: CLIError, ConnectionError
9. **Confirmation Layer**: ConfirmationPromptError, ConfirmationPromptExpired
10. **Fetch Layer**: ALL_SOURCES_FAILED, has_required_failure, terminal_failure
11. **Watcher Layer**: Refusal (tracked in bead_watch)

---

## Usage Patterns

### Retry Patterns
- **GitNetworkError**: Has `@retry_on_network_failure` decorator (3 retries, 1.5x backoff)
- **ValidationRetryExhaustedError**: Max 3 re-formulation attempts per session
- **Registry/Config errors**: Use mtime cache to preserve last-known-good state on parse failures

### Recovery Strategies
- **Corrective Retry**: Used for early-pipeline failures (LLM parsing in intent router)
- **Fallback Result**: Used for late-pipeline failures after expensive operations (synthesize strand)
- **Terminal Failure**: Used when all sources fail (broadcasts failure event, creates failed card)

### Error Context Preservation
- **ParseLLMError**: Preserves `raw_response` for debugging
- **DeploymentPersistenceError**: Preserves `filepath`, `original_error`
- **ValidationRetryExhaustedError**: Preserves `original_violations`
- **GitError subclasses**: Include specific error details (auth, network, state, conflict)

---

*Document generated: 2026-08-07*
*Source: aide-de-camp codebase analysis*
