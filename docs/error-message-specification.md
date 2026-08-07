# Error Message Specification

**Purpose:** This document defines the standard format, templates, and implementation guidance for all error messages in the aide-de-camp system to ensure clarity, consistency, and actionability.

**Scope:** Covers API validation errors, SSE error events, network/transient errors, confirmation validation errors, and deployment data validation errors.

---

## Error Message Template

### Standard Template Structure

All error messages should follow this structure:

```plaintext
[Error Category]: [Brief Description]

Details: [Specific information about what went wrong]
Impact: [What this means for the user]
Action: [What the user can do to resolve it]
```

### Simplified Template for Client-Facing Messages

For client-facing API responses and SSE events:

```plaintext
[Category] — [Brief actionable description]
```

### Internal Error Template (for logs)

```plaintext
[ERROR] [Category] [Component]: [Description]
Context: {relevant context}
Stack: [if applicable]
```

---

## Error Categories and Specifications

### 1. API Validation Errors

#### 1.1 Missing Required Fields

**Template:**
```plaintext
Missing required field: '{field_name}'
Expected: {expected_type}
```

**Examples:**
- `Missing required field: 'utterance'`
- `Missing required field: 'session_id' - Expected: string (UUID format)`

**Implementation Guidance:**
- Use Pydantic field validators
- Return HTTP 400/422 status code
- Include field name in error response
- Specify expected type/format

**Current Implementation:** `src/api/models.py:DispatchRequest`

#### 1.2 Invalid Data Type

**Template:**
```plaintext
Invalid data type for field '{field_name}'
Received: {received_type}
Expected: {expected_type}
```

**Examples:**
- `Invalid data type for field 'utterance' - Received: int, Expected: string`
- `Invalid data type for field 'service' - Received: int, Expected: str`

**Implementation Guidance:**
- Validate type before processing
- Include both received and expected types
- Use specific type names (not generic "object")

**Current Implementation:** `src/api/models.py:field_validator`

#### 1.3 Empty or Whitespace-Only Values

**Template:**
```plaintext
Field '{field_name}' cannot be empty or whitespace-only
```

**Examples:**
- `Field 'utterance' cannot be empty or whitespace-only`
- `Field 'session_id' cannot be empty or whitespace-only`

**Implementation Guidance:**
- Strip whitespace before validation
- Check for empty strings after stripping
- Provide clear error before processing

**Current Implementation:** `src/api/models.py:utterance_must_be_non_empty`

#### 1.4 Malformed JSON

**Template:**
```plaintext
Invalid JSON in request body
Error: {specific_parse_error}
Position: {line}:{column} (if available)
```

**Examples:**
- `Invalid JSON in request body - Error: Expecting property name enclosed in double quotes`
- `Invalid JSON in request body - Error: Unterminated string starting at line 3, column 15`

**Implementation Guidance:**
- Catch JSON decode exceptions
- Extract specific error details
- Include line/column information when available
- Return HTTP 400 status

---

### 2. SSE Degraded State Errors

#### 2.1 Router Unavailable

**Template:**
```plaintext
Router unavailable — LLM proxy unreachable
Reason: {specific_reason}
Retry allowed: Yes/No
```

**Error Reasons:**
- `timeout` — Request to ZAI proxy timed out
- `quota_exhausted` — API quota exceeded
- `proxy_down` — ZAI proxy not responding
- `unknown_error` — Unknown connectivity issue

**Examples:**
- `Router unavailable — LLM proxy unreachable - Reason: timeout - Retry allowed: Yes`
- `Router unavailable — LLM proxy unreachable - Reason: quota_exhausted - Retry allowed: No`

**Implementation Guidance:**
- Preserve user's original utterance for retry
- Use specific error_reason codes
- Set retry_allowed flag appropriately
- Return SSE event with EventType.ROUTER_UNAVAILABLE

**Current Implementation:** `src/errors/degraded_state.py:broadcast_router_unavailable`

#### 2.2 All Sources Failed

**Template:**
```plaintext
No data — all required sources failed
Intent: {intent_type}
Failed sources: {count}
Details: [{source: {status}, {error}}]
Retry allowed: Yes
```

**Examples:**
- `No data — all required sources failed - Intent: ci_status - Failed sources: 2 - Retry allowed: Yes`

**Implementation Guidance:**
- List all failed sources with their errors
- Include intent type for context
- Allow retry since sources may recover
- Return SSE event with EventType.ALL_SOURCES_FAILED

**Current Implementation:** `src/errors/degraded_state.py:broadcast_all_sources_failed`

#### 2.3 Degraded Raw Data

**Template:**
```plaintext
Summary unavailable — showing raw fetch data
Reason: {error_reason}
Coverage: {succeeded}/{total_sources} succeeded
Retry allowed: Yes
```

**Error Reasons:**
- `synthesize_failed` — LLM synthesis failed
- `quota_exhausted` — Synthesis API quota exceeded
- `timeout` — Synthesis request timed out
- `malformed_response` — Invalid LLM response format

**Examples:**
- `Summary unavailable — showing raw fetch data - Reason: synthesize_failed - Coverage: 2/3 succeeded - Retry allowed: Yes`

**Implementation Guidance:**
- Preserve all fetched data for display
- Show coverage statistics
- Explain why synthesis failed
- Allow retry with same data

**Current Implementation:** `src/errors/degraded_state.py:broadcast_degraded_raw_data`

#### 2.4 Clarification Card

**Template:**
```plaintext
Couldn't parse that into intents
Error: {parse_error}
Retry attempted: {retry_count}/1
```

**Examples:**
- `Couldn't parse that into intents - Error: Missing 'intent_type' field in router response - Retry attempted: 1/1`
- `Couldn't parse that into intents - Error: Invalid JSON format - Retry attempted: 0/1`

**Implementation Guidance:**
- Preserve original utterance for editing
- Show specific parse error
- Log raw output snippet (not to client)
- Allow one corrective retry
- Return SSE event with EventType.CLARIFICATION_CARD

**Current Implementation:** `src/errors/degraded_state.py:broadcast_clarification_card`

#### 2.5 Action Design Only

**Template:**
```plaintext
Action execution is not yet available
Project: {project_slug or 'none'}
Requeue as task: Yes
```

**Examples:**
- `Action execution is not yet available - Project: aide-de-camp - Requeue as task: Yes`

**Implementation Guidance:**
- Explain feature is not built
- Offer to requeue as task bead
- Include project context if available
- Return SSE event with EventType.ACTION_DESIGN_ONLY

**Current Implementation:** `src/errors/degraded_state.py:broadcast_action_design_only`

#### 2.6 Reminder Unavailable

**Template:**
```plaintext
Reminders are not available yet
```

**Examples:**
- `Reminders are not available yet`

**Implementation Guidance:**
- Friendly, simple message
- No technical details needed
- Return SSE event with EventType.REMINDER_UNAVAILABLE

**Current Implementation:** `src/errors/degraded_state.py:broadcast_reminder_unavailable`

---

### 3. Network and Transient Errors

#### 3.1 Timeout Errors

**Template:**
```plaintext
Request timed out
Operation: {operation_description}
Duration: {duration_seconds}s
Timeout limit: {timeout_limit}s
Category: timeout (transient)
```

**Examples:**
- `Request timed out - Operation: Connect to api.github.com - Duration: 30.5s - Timeout limit: 30s - Category: timeout (transient)`

**Implementation Guidance:**
- Specify operation that timed out
- Show actual vs limit duration
- Mark as transient (retry-eligible)
- Use `is_transient()` for classification

**Current Implementation:** `src/errors/transient_errors.py:is_transient`

#### 3.2 Connection Errors

**Template:**
```plaintext
Connection failed
Target: {host}:{port}
Error: {specific_error}
Category: {connection|dns|network} (transient)
```

**Examples:**
- `Connection failed - Target: api.example.com:443 - Error: Connection refused - Category: connection (transient)`
- `Connection failed - Target: api.example.com:443 - Error: DNS resolution failed - Category: dns (transient)`

**Implementation Guidance:**
- Include target host and port
- Show specific socket/error message
- Categorize as connection/dns/network
- Mark as transient (retry-eligible)

**Current Implementation:** `src/errors/transient_errors.py:_is_httpx_network_error_transient`

#### 3.3 HTTP Status Errors

**Template (5xx Server Errors):**
```plaintext
Server error
Status: {status_code} {status_text}
URL: {request_url}
Category: server_error (transient)
```

**Template (4xx Client Errors):**
```plaintext
Client error
Status: {status_code} {status_text}
URL: {request_url}
Category: client_error (permanent)
```

**Template (429 Rate Limit):**
```plaintext
Rate limited
Status: 429 Too Many Requests
URL: {request_url}
Retry after: {retry_after_seconds}s (if available)
Category: rate_limit (transient)
```

**Examples:**
- `Server error - Status: 503 Service Unavailable - URL: https://api.example.com/data - Category: server_error (transient)`
- `Client error - Status: 404 Not Found - URL: https://api.example.com/resource - Category: client_error (permanent)`
- `Rate limited - Status: 429 Too Many Requests - URL: https://api.example.com/data - Retry after: 60s - Category: rate_limit (transient)`

**Implementation Guidance:**
- Always include HTTP status code and text
- Include request URL for debugging
- Classify correctly (transient vs permanent)
- Extract Retry-After header for 429

**Current Implementation:** `src/errors/transient_errors.py:_is_http_status_transient`

#### 3.4 Network Unreachable

**Template:**
```plaintext
Network unreachable
Host: {hostname}
Error: {specific_errno_message}
Category: network (transient)
```

**Examples:**
- `Network unreachable - Host: api.example.com - Error: No route to host - Category: network (transient)`
- `Network unreachable - Host: 192.168.1.100 - Error: Host is down - Category: network (transient)`

**Implementation Guidance:**
- Use errno messages for specificity
- Mark transient (network issues usually temporary)
- Include hostname for debugging

**Current Implementation:** `src/errors/transient_errors.py:_is_os_error_transient`

---

### 4. Confirmation Validation Errors

#### 4.1 Invalid Yes/No Response

**Template:**
```plaintext
Invalid response. Please respond with 'yes' or 'no'
Your response: "{user_response}"
Valid responses: yes, no, {pod_names}
```

**Examples:**
- `Invalid response. Please respond with 'yes' or 'no' - Your response: "maybe" - Valid responses: yes, no, test-pod-abc123`

**Implementation Guidance:**
- Preserve user's response for context
- Show valid options clearly
- Case-insensitive validation
- Strip whitespace before validation

**Current Implementation:** `tests/test_confirmation_validation.py`

#### 4.2 Invalid Pod Name

**Template:**
```plaintext
Invalid pod name
Your response: "{user_response}"
Valid pods: {comma_separated_pod_names}
```

**Examples:**
- `Invalid pod name - Your response: "wrong-pod-name" - Valid pods: test-pod-abc123, another-pod-def456`

**Implementation Guidance:**
- List all valid pod names
- Case-sensitive matching for pod names
- Show user's input for clarity

---

### 5. Deployment Data Validation Errors

#### 5.1 Missing Required Fields

**Template:**
```plaintext
Missing required field: '{field_name}'
Expected type: {type_description}
Required for: {validation_step}
```

**Examples:**
- `Missing required field: 'total_deployments' - Expected type: integer - Required for: completeness validation`
- `Missing required field: 'service' - Expected type: string - Required for: data type validation`

**Implementation Guidance:**
- Specify the validation step that requires it
- Include expected type
- Collect all missing fields before reporting

**Current Implementation:** `tests/validation/test_multi_failure_validation.py`

#### 5.2 Type Mismatch Errors

**Template:**
```plaintext
Type mismatch for field '{field_name}'
Received: {received_type} ({received_value})
Expected: {expected_type}
```

**Examples:**
- `Type mismatch for field 'service' - Received: int (123) - Expected: str`
- `Type mismatch for field 'period_days' - Received: str ("30") - Expected: int`
- `Type mismatch for field 'deployment_names' - Received: str ("pbx-web") - Expected: list`

**Implementation Guidance:**
- Show both received and expected types
- Include received value for debugging
- Collect all type errors before reporting

**Current Implementation:** `tests/validation/test_multi_failure_validation.py`

#### 5.3 Completeness/Gap Errors

**Template:**
```plaintext
Data completeness gap detected
Expected dates: {expected_date_range}
Missing dates: {missing_dates_count} dates
Gap locations: {specific_missing_dates}
Coverage: {coverage_percentage}%
```

**Examples:**
- `Data completeness gap detected - Expected dates: 2026-07-01 to 2026-07-30 - Missing dates: 3 dates - Gap locations: 2026-07-04, 2026-07-15, 2026-07-29 - Coverage: 90%`

**Implementation Guidance:**
- Show expected date range
- List specific missing dates
- Calculate coverage percentage
- Make gaps visually clear

**Current Implementation:** `tests/validation/test_multi_failure_validation.py`

#### 5.4 Multiple Validation Errors

**Template:**
```plaintext
Multiple validation errors detected
Errors: {error_count} errors

1. [Error 1]
2. [Error 2]
...
N. [Error N]

All errors must be resolved before processing.
```

**Examples:**
```plaintext
Multiple validation errors detected
Errors: 5 errors

1. Type mismatch for field 'service' - Received: int (123) - Expected: str
2. Type mismatch for field 'period_days' - Received: str ("30") - Expected: int
3. Type mismatch for field 'deployment_names' - Received: str ("pbx-web") - Expected: list
4. Missing required field: 'total_deployments' - Expected type: integer - Required for: completeness validation
5. Missing required field: 'successful_deployments' - Expected type: integer - Required for: completeness validation

All errors must be resolved before processing.
```

**Implementation Guidance:**
- Collect all errors before returning
- Number errors for clarity
- Show error count prominently
- List errors in logical order
- Emphasize that all must be resolved

**Current Implementation:** `tests/validation/test_multi_failure_validation.py`

---

## Implementation Guidelines

### General Principles

1. **Be Specific**: Include field names, expected values, and actual values
2. **Be Actionable**: Tell the user what to do next
3. **Be Contextual**: Include relevant context (URLs, timestamps, counts)
4. **Be Consistent**: Use the same terminology across similar errors
5. **Be User-Facing**: Avoid jargon and stack traces in client messages

### Error Response Structure

All error responses should follow this JSON structure:

```json
{
  "error": {
    "category": "validation|network|server|client",
    "message": "Human-readable error message",
    "details": {
      "field": "field_name (if applicable)",
      "received": "what was received",
      "expected": "what was expected",
      "context": "additional context"
    },
    "retry_allowed": true|false,
    "retry_after": "seconds (if applicable)"
  }
}
```

### Logging vs Client Messages

**For logs (internal):**
```python
logger.error(
    f"[{category}] {component}: {description}",
    extra={
        "context": context_dict,
        "stack_trace": traceback.format_exc(),
        "timestamp": datetime.now().isoformat()
    }
)
```

**For clients (API/SSE):**
```python
error_response = {
    "message": "Clear, actionable description",
    "retry_allowed": True,
    "category": "network"
}
```

### Error Categories for Routing

Use these categories for surface routing decisions:

- **critical**: System-down errors, requires immediate attention
- **transient**: Temporary errors, will retry automatically
- **permanent**: Configuration/data errors, user intervention needed
- **degraded**: Partial functionality, degraded state

### Error Message Localization

Currently all messages are in English. Future localization should:
- Preserve error codes and field names (technical terms)
- Only translate human-readable descriptions
- Maintain template structure across languages

---

## Testing Error Messages

### Unit Test Requirements

Each error type should have tests verifying:

1. **Message Content**: Error message contains required information
2. **Format Compliance**: Follows the standard template
3. **Actionability**: Includes retry guidance or next steps
4. **Context Preservation**: Includes relevant context data

### Test Examples

```python
def test_router_unavailable_error_message():
    """Test router unavailable error message contains all required fields."""
    handler = get_degraded_state_handler()
    
    # Broadcast error
    await handler.broadcast_router_unavailable(
        utterance="test utterance",
        intent_id="test-intent",
        session_id="test-session",
        error_reason="timeout"
    )
    
    # Verify message contains:
    # - "Router unavailable"
    # - "timeout" reason
    # - Retry guidance
    assert "Router unavailable" in message
    assert "timeout" in message
    assert "retry" in message.lower()
```

---

## Maintenance and Updates

### Adding New Error Types

When adding new error types:

1. Define the error message template following the standard structure
2. Add implementation guidance in this document
3. Create tests for the new error messages
4. Update this document with the new specification
5. Tag with relevant feature bead ID

### Review Schedule

Review error messages quarterly or after major releases to ensure:
- Messages remain clear and actionable
- Templates are followed consistently
- New errors are documented
- Implementation guidance is current

---

## Appendix: Error Type Reference

### Complete Error Type Inventory

| Error Type | Category | Retry | Template Section | Implementation |
|------------|----------|-------|------------------|----------------|
| Missing required field | validation | No | 1.1 | `src/api/models.py` |
| Invalid data type | validation | No | 1.2 | `src/api/models.py` |
| Empty/whitespace value | validation | No | 1.3 | `src/api/models.py` |
| Malformed JSON | validation | No | 1.4 | `src/main.py` |
| Router unavailable | degraded | Yes | 2.1 | `src/errors/degraded_state.py` |
| All sources failed | degraded | Yes | 2.2 | `src/errors/degraded_state.py` |
| Degraded raw data | degraded | Yes | 2.3 | `src/errors/degraded_state.py` |
| Clarification card | degraded | Yes | 2.4 | `src/errors/degraded_state.py` |
| Action design only | degraded | No | 2.5 | `src/errors/degraded_state.py` |
| Reminder unavailable | degraded | No | 2.6 | `src/errors/degraded_state.py` |
| Timeout | network | Yes | 3.1 | `src/errors/transient_errors.py` |
| Connection error | network | Yes | 3.2 | `src/errors/transient_errors.py` |
| HTTP 5xx error | network | Yes | 3.3 | `src/errors/transient_errors.py` |
| HTTP 4xx error | network | No | 3.3 | `src/errors/transient_errors.py` |
| Rate limit (429) | network | Yes | 3.3 | `src/errors/transient_errors.py` |
| Network unreachable | network | Yes | 3.4 | `src/errors/transient_errors.py` |
| Invalid yes/no | confirmation | N/A | 4.1 | `src/confirmations.py` |
| Invalid pod name | confirmation | N/A | 4.2 | `src/confirmations.py` |
| Missing deployment field | deployment | No | 5.1 | `src/validation/` |
| Type mismatch | deployment | No | 5.2 | `src/validation/` |
| Completeness gap | deployment | No | 5.3 | `src/validation/` |
| Multiple errors | deployment | No | 5.4 | `src/validation/` |

---

**Document Version:** 1.0  
**Last Updated:** 2026-08-07  
**Bead ID:** adc-506hdn  
**Status:** Active
