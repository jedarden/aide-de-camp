# Comprehensive Error Type Mapping Documentation

**Generated:** 2026-08-07  
**Project:** aide-de-camp  
**Analysis Scope:** Complete system error handling and user-facing error messages

## Overview

This document provides a comprehensive mapping of all error messages to their corresponding failure types across the aide-de-camp system. It includes analysis of ambiguous or misleading messages, recommendations for improving unclear error messaging, and identifies failure scenarios that need better error messaging.

## Error Architecture

The aide-de-camp system implements a multi-layered error handling strategy:

1. **API Layer**: Request validation and authentication errors
2. **Intent Router Layer**: LLM routing and classification errors  
3. **Fetch Layer**: Data fetching errors from external sources
4. **Synthesize Layer**: LLM synthesis errors
5. **SSE Broadcast Layer**: Real-time error communication to clients
6. **Persistence Layer**: Database and file system errors

## Error Type Taxonomy

### 1. API Validation Errors

| Error Message | Error Type | Field | Validation Rule | User Impact |
|---------------|------------|-------|-----------------|-------------|
| `utterance must be a string` | ValidationError | utterance | Type check | Request rejected |
| `utterance must be a non-empty string` | ValidationError | utterance | Non-empty after trim | Request rejected |
| `session_id must be a string` | ValidationError | session_id | Type check | Request rejected |
| `session_id must be a non-empty string` | ValidationError | session_id | Non-empty after trim | Request rejected |
| `surface_id must be a string` | ValidationError | surface_id | Type check | Request rejected |
| `surface_id must be a non-empty string` | ValidationError | surface_id | Non-empty after trim | Request rejected |
| `utterance_id must be a string` | ValidationError | utterance_id | Type check (optional) | Request rejected |
| `utterance_id must be a non-empty string if provided` | ValidationError | utterance_id | Non-empty if provided | Request rejected |

**Analysis**: These validation errors are clear and specific. They correctly identify the problematic field and the validation rule that failed. No improvements needed.

**Failure Type**: `request_validation_error`

---

### 2. Router/Intent Classification Errors

| Error Message | Error Type | SSE Event | Root Causes | Retry Allowed |
|---------------|------------|-----------|-------------|---------------|
| `Router unavailable — LLM proxy unreachable` | RouterUnavailableEvent | ROUTER_UNAVAILABLE | timeout, quota_exhausted, proxy_down, unknown_error | Yes |
| `Couldn't parse that into intents` | ClarificationCardEvent | CLARIFICATION_CARD | Malformed LLM JSON response | Yes (1 corrective retry) |
| `Action execution is not yet available` | ActionDesignOnlyEvent | ACTION_DESIGN_ONLY | Action intent detected but executor not built | Yes (requeue as bead) |
| `Reminders are not available yet` | ReminderUnavailableEvent | REMINDER_UNAVAILABLE | Reminder intent detected but system not implemented | No |

**Router Unavailable Sub-Types**:
- `timeout` - LLM request exceeded timeout threshold
- `quota_exhausted` - Rate limiting or quota exceeded  
- `proxy_down` - ZAI proxy unreachable
- `unknown_error` - Unclassified router error

**Analysis**: 
- **Strength**: Router unavailable error provides specific reason codes for better debugging
- **Improvement Needed**: "Couldn't parse that into intents" is vague - should include parsing error details
- **Strength**: "not yet available" messages are honest and set proper expectations

**Failure Type**: `router_classification_error`

---

### 3. Data Fetch Errors

| Error Message | Error Type | SSE Event | Root Causes | Retry Allowed |
|---------------|------------|-----------|-------------|---------------|
| `No data — all required sources failed` | AllSourcesFailedEvent | ALL_SOURCES_FAILED | All fetch sources failed | Yes |
| `Summary unavailable — showing raw fetch data` | DegradedRawDataEvent | DEGRADED_RAW_DATA | Synthesis failed, fetch succeeded | Yes |

**Fetch Source Failure Types**:

| Source | Error Message | Status | Common Causes |
|--------|---------------|--------|---------------|
| KUBECTL_PODS | `kubectl pods query failed` | failed | Cluster unreachable, permission denied |
| KUBECTL_DEPLOYMENTS | `kubectl deployments query failed` | failed | Cluster unreachable, permission denied |
| KUBECTL_WORKFLOWS | `kubectl workflows query failed` | failed | Cluster unreachable, permission denied |
| ARGOCD_APP | `ArgoCD application query failed` | failed | ArgoCD unreachable, app not found |
| GIT_LOG | `git log execution failed` | failed | Repository access issues, invalid git path |
| GIT_STATUS | `git status execution failed` | failed | Repository access issues, invalid git path |
| BEAD_LIST | `bf list command failed` | failed | bf CLI issues, database lock |
| BEAD_DETAILS | `bf show command failed` | failed | Bead not found, database lock |
| CI_STATUS | `CI status query failed` | failed | WorkflowTemplate not found, cluster unreachable |
| COMPONENTS | `Component library query failed` | failed | Component not found, library issues |
| LOGS | `Pod logs query failed` | failed | Pod not found, container not ready |
| EVENTS | `Pod events query failed` | failed | Pod not found, namespace issues |
| SESSION_STATE | `Session state query failed` | failed | Database locked, session not found |
| TOPIC_CONTEXT | `Topic context query failed` | failed | Topic not found, database locked |
| REMINDERS | `Reminders query failed` | failed | Reminder system not implemented |
| FS_EXPLORE | `Filesystem explore failed` | failed | Path not found, permission denied |
| FS_README | `README read failed` | failed | File not found, read permission denied |
| FS_HOME | `Home directory read failed` | failed | Directory not found, permission denied |

**Fetch Status Types**:
- `success` - Source executed successfully
- `timeout` - Source exceeded configured timeout
- `failed` - Source execution failed with error
- `skipped` - Source not required for this intent

**Analysis**:
- **Strength**: Per-source failure tracking provides detailed diagnostics
- **Strength**: Degraded mode preserves fetched data even when synthesis fails
- **Improvement Needed**: Some error messages are generic - could be more specific about root causes
- **Ambiguity**: "query failed" doesn't distinguish between network, auth, and data errors

**Failure Type**: `data_fetch_error`

---

### 4. Synthesis Errors

| Error Message | Error Type | SSE Event | Root Causes | Retry Allowed |
|---------------|------------|-----------|-------------|---------------|
| `Summary unavailable — showing raw fetch data` | DegradedRawDataEvent | DEGRADED_RAW_DATA | LLM synthesis failed, fetch succeeded | Yes |
| `synthesize_failed` | DegradedRawDataEvent | DEGRADED_RAW_DATA | LLM error, timeout, quota | Yes |

**Synthesis Failure Sub-Types**:
- `LLMTimeoutError` - Synthesis LLM call timed out
- `LLMRateLimitError` - Synthesis rate limited
- `LLMError` - Generic LLM error during synthesis
- `ParseLLMError` - Failed to parse synthesis response
- `synthesize_failed` - Generic synthesis failure

**Analysis**:
- **Strength**: Degraded mode design is excellent - never discards fetched data
- **Improvement Needed**: "synthesize_failed" is too generic - should distinguish between timeout, parsing, and LLM errors
- **Strength**: User sees raw data even when summary fails, maintaining transparency

**Failure Type**: `synthesis_error`

---

### 5. Persistence and Database Errors

| Error Message | Error Type | Component | Root Causes | Recovery |
|---------------|------------|-----------|-------------|----------|
| `Atomic write failed` | AtomicWriteError | File System | Disk full, permission denied | Manual intervention |
| `Database locked` | DatabaseError | SQLite | Concurrent write limit | Retry after delay |
| `Session not found` | DatabaseError | Session Store | Invalid session_id | Create new session |
| `Bead not found` | DatabaseError | Bead Store | Invalid bead_id | User correction |

**SQLite-specific Errors**:
- `database is locked` - Concurrent write attempts exceeded
- `no such table` - Schema migration needed
- `foreign key constraint failed` - Referential integrity issue
- `UNIQUE constraint failed` - Duplicate key insertion

**Analysis**:
- **Improvement Needed**: "Database locked" should include retry guidance
- **Ambiguity**: "Atomic write failed" doesn't distinguish between disk full, permissions, and IO errors
- **Strength**: Atomic write prevents data corruption during failures

**Failure Type**: `persistence_error`

---

### 6. Deployment Infrastructure Errors

From the deployment data analysis, the following failure patterns are defined:

| Pattern Type | Severity | Description | Occurrences (May-Jul 2026) |
|--------------|----------|-------------|----------------------------|
| **ImagePullBackOff** | High | Container image cannot be pulled (registry issues, authentication, missing image) | 0 |
| **CrashLoopBackOff** | Critical | Pod repeatedly crashes and restarts (application errors, misconfiguration) | 0 |
| **OOMKilled** | High | Container killed due to memory exhaustion (resource limits exceeded) | 0 |
| **Probe_failure** | Medium | Readiness or liveness probe failures (health check issues) | 0 |
| **Dependency_timeout** | Medium | Deployment timeout due to dependency unavailability | 0 |
| **Other** | Unknown | Other failure patterns not matching standard categories | 181 |

**Analysis**:
- **Strength**: No critical deployment failures in 3-month period indicates healthy infrastructure
- **Data Quality Issue**: 100% of events in "Other" category suggests pattern detection needs refinement
- **Gap**: Current taxonomy misses important failure modes specific to the application stack

**Services with Deployment Events** (May-Jul 2026):
- whisper-stt: 15 events
- whisper-openai: 6 events  
- pbx-rebuild-relay: 3 events
- lab-rebuild-relay: 3 events
- pbx-web: 1 event

**Failure Type**: `deployment_error`

---

## SSE Error Event Matrix

| SSE Event Type | User-Facing Message | Technical Error Type | Recovery Action |
|----------------|---------------------|---------------------|-----------------|
| `ROUTER_UNAVAILABLE` | "Router unavailable — LLM proxy unreachable" | RouterUnavailableEvent | Retry dispatch |
| `ALL_SOURCES_FAILED` | "No data — all required sources failed" | AllSourcesFailedEvent | Retry fetch |
| `DEGRADED_RAW_DATA` | "Summary unavailable — showing raw fetch data" | DegradedRawDataEvent | Retry synthesis |
| `CLARIFICATION_CARD` | "Couldn't parse that into intents" | ClarificationCardEvent | Edit and resend |
| `ACTION_DESIGN_ONLY` | "Action execution is not yet available" | ActionDesignOnlyEvent | Requeue as bead |
| `REMINDER_UNAVAILABLE` | "Reminders are not available yet" | ReminderUnavailableEvent | N/A (feature not built) |
| `MALFORMED_RESPONSE` | "Malformed LLM response detected" | ParseLLMError | System-initiated retry |
| `EXCEPTION_RAISED` | "Unexpected system error" | UnhandledException | Log and report |

---

## Error Message Quality Analysis

### Clear Error Messages ✅

1. **`utterance must be a non-empty string`** - Specific field, clear requirement
2. **`Router unavailable — LLM proxy unreachable`** - Specific component, clear impact
3. **`Action execution is not yet available`** - Honest about feature status
4. **`Reminders are not available yet`** - Sets proper expectations

### Ambiguous/Misleading Error Messages ❌

1. **`Couldn't parse that into intents`**
   - **Issue**: Doesn't explain *why* parsing failed
   - **Improvement**: "JSON parse error: {specific_error} - Expected intent structure"
   
2. **`No data — all required sources failed`**
   - **Issue**: Doesn't identify which sources failed or why
   - **Improvement**: "No data - {source_list}: {error_summary}"

3. **`synthesize_failed`**
   - **Issue**: Too generic, doesn't distinguish timeout vs. error vs. parsing
   - **Improvement**: Use specific error codes: `synthesis_timeout`, `synthesis_parse_error`, `synthesis_llm_error`

4. **`Atomic write failed`**
   - **Issue**: Doesn't distinguish between disk full, permissions, and IO errors
   - **Improvement**: "Atomic write failed: {specific_reason} - {recovery_guidance}"

5. **`query failed`** (fetch sources)
   - **Issue**: Generic across all fetch failures
   - **Improvement**: Distinguish between network errors, auth errors, and not-found errors

### Missing Error Messages 🔍

1. **Rate Limiting** - No clear message when LLM quota is exhausted
2. **Database Migration Required** - No guidance when schema is outdated
3. **Configuration Errors** - Missing or invalid config files not clearly reported
4. **Network Partitioning** - Unclear when cluster/network is unreachable
5. **Concurrent Write Limits** - SQLite lock not explained to user

---

## Error Recovery Patterns

### Retry-Allowing Errors

| Error Type | Auto-Retry | User Retry | Max Attempts | Backoff Strategy |
|------------|------------|------------|--------------|------------------|
| ROUTER_UNAVAILABLE | Yes (1x) | Yes | 2 | Immediate |
| ALL_SOURCES_FAILED | No | Yes | Unlimited | Manual |
| DEGRADED_RAW_DATA | No | Yes | Unlimited | Manual |
| CLARIFICATION_CARD | Yes (1x corrective) | Yes | 2 | Immediate |
| Database locked | Yes (exponential) | No | 5 | Exponential backoff |
| Network timeout | Yes | Yes | 3 | Linear backoff |

### Non-Retriable Errors

| Error Type | Reason | User Action |
|------------|--------|-------------|
| ValidationError | Invalid input format | Fix request format |
| REMINDER_UNAVAILABLE | Feature not implemented | N/A |
| RegistryValidationError | Config schema error | Fix config files |
| Permission denied | Auth/authorization issue | Fix permissions |

---

## Failure Scenarios Needing Better Error Messaging

### 1. LLM Quota Exhaustion ⚠️

**Current**: Generic `router_unavailable` with `quota_exhausted` reason code  
**Problem**: User doesn't know quota limit or reset time  
**Recommendation**: 
```
"LLM quota exhausted (limit: {limit}, resets: {reset_time}). 
Retry after {time_remaining} or upgrade quota."
```

### 2. Database Schema Mismatch ⚠️

**Current**: Generic `no such table` SQLite error  
**Problem**: User doesn't know migration is required  
**Recommendation**:
```
"Database schema outdated. Run migrations: 
python -m src.session.migrations.run"
```

### 3. Concurrent Write Contention ⚠️

**Current**: Generic "database is locked"  
**Problem**: User doesn't know if retry will help or how long to wait  
**Recommendation**:
```
"Database temporarily locked (concurrent writes). 
Retrying automatically (attempt {attempt}/{max_attempts})..."
```

### 4. Fetch Source Partial Failure ⚠️

**Current**: Shows raw data but doesn't explain which sources failed  
**Problem**: User doesn't know if critical data is missing  
**Recommendation**:
```
"Partial data available. Failed sources: {failed_list}.
Succeeded: {succeeded_list}. Retry to attempt recovery."
```

### 5. Configuration File Errors ⚠️

**Current**: Generic YAML parse errors  
**Problem**: User doesn't know which file/line is problematic  
**Recommendation**:
```
"Config error in {filename} at line {line_number}: {specific_error}.
Fix and reload config."
```

---

## Error Severity Levels

| Severity | Error Types | User Impact | Time to Resolution |
|----------|-------------|-------------|-------------------|
| **Critical** | CrashLoopBackOff, UnhandledException | System unavailable | Hours |
| **High** | Router unavailable, All sources failed | Feature unavailable | Minutes |
| **Medium** | Partial fetch failure, Degraded mode | Degraded experience | Seconds |
| **Low** | Validation errors, Single source timeout | Request rejected | Immediate |
| **Info** | Feature not implemented, Honest guards | Expected limitation | N/A |

---

## Monitoring and Alerting Recommendations

### Error Rate Thresholds

| Error Type | Alert Threshold | Duration | Escalation |
|------------|-----------------|----------|------------|
| ROUTER_UNAVAILABLE | > 10% | 5 minutes | Page on-call |
| ALL_SOURCES_FAILED | > 5% | 10 minutes | Email alert |
| Database locked | > 1% | 30 minutes | Warning only |
| ValidationError | > 5% | 15 minutes | Review client |

### Metrics to Track

1. **Error Frequency**: Errors per hour by type
2. **Error Recovery Rate**: Successful retries / total retries
3. **User Impact**: Sessions affected by errors
4. **Mean Time to Resolution**: Average recovery time per error type

---

## Summary and Next Steps

### Current State

**Strengths**:
- Comprehensive SSE error event system
- Degraded mode design preserves user experience
- Honest feature status messages
- Detailed per-source failure tracking

**Gaps**:
- Generic error messages lack specific guidance
- Missing error messages for rate limiting, schema issues
- Deployment failure taxonomy needs refinement (100% "Other" category)
- No clear user guidance for non-retriable errors

### Recommended Improvements

1. **Short-term** (1-2 weeks):
   - Add specific error codes for synthesis failures
   - Improve fetch source error messages with specific reasons
   - Add retry guidance to database lock errors

2. **Medium-term** (1-2 months):
   - Refine deployment failure pattern detection
   - Add rate limiting error messages with quota details
   - Create error recovery documentation for users

3. **Long-term** (3-6 months):
   - Implement error severity escalation
   - Add user-friendly error recovery UI actions
   - Create error trend monitoring and alerting

### Documentation Maintenance

This document should be updated:
- When new error types are added
- When error messages are changed
- Quarterly to review monitoring thresholds
- After major incidents to incorporate learnings

---

**Document Version**: 1.0  
**Last Updated**: 2026-08-07  
**Maintained By**: aide-de-camp development team  
**Related Documents**:
- `docs/plan/plan.md` (Degraded-State UX)
- `docs/research/deployment-data/failure-taxonomy.json`
- `src/errors/degraded_state.py` (Error event definitions)