"""
Event categorization module for deployment events.

Builds on top of parse_log to provide detailed categorization of deployment
events into specific types (deployment_start, deployment_complete, pod_crash,
OOM, readiness_fail, timeout, etc.).

Categorization rules analyze parsed event fields including event_type, status,
error_code, and metadata.source_fields to determine the specific event type.
"""

import re
from typing import Dict, Any, Optional, List
from logging import getLogger
from enum import Enum

logger = getLogger(__name__)


class EventType(Enum):
    """
    Enumeration of all supported event types for deployment categorization.

    Event types represent specific categories of deployment-related events that
    can occur during the lifecycle of a deployment. Each type captures a distinct
    class of events for filtering, alerting, and analytics purposes.

    Attributes:
        DEPLOYMENT_START: Events indicating a deployment has started
        DEPLOYMENT_COMPLETE: Events indicating a deployment has completed successfully
        POD_CRASH: Events indicating a pod has crashed or failed
        OOM: Events indicating an Out Of Memory kill
        READINESS_FAIL: Events indicating a readiness probe failure
        TIMEOUT: Events indicating a timeout occurred
        IMAGE_PULL_ERROR: Events indicating an image pull failure
        RESOURCE_LIMIT: Events indicating resource limits were exceeded
        PROBE_FAILURE: Events indicating a generic probe (liveness/startup) failure
        NETWORK_ERROR: Events indicating network connectivity issues
        UNKNOWN: Events that could not be categorized into any known type

    UNKNOWN Event Criteria:
        An event is categorized as UNKNOWN when it matches NONE of the specific
        detection patterns above. This includes events that are:

        - Malformed or missing required fields (None, not a dict, empty dict)
        - Using unrecognized event_type values not matching deployment/pod/event patterns
        - Missing error indicators (no error_code, no reason, no message patterns)
        - Having status values that don't correlate to known event states
        - Containing only unknown or unrecognized metadata fields

        The UNKNOWN category serves as a safe fallback to ensure all events are
        categorized, even if they don't match known patterns. This prevents
        data loss and allows for later analysis of emerging event types.

        Events are checked in specificity order (most specific to least specific):
        1. OOM (highest priority - distinct error pattern)
        2. Image pull errors (very specific error pattern)
        3. Pod crashes (more specific than readiness failures)
        4. Readiness failures (less specific than crashes)
        5. Timeouts (but not DNS timeouts - those are network errors)
        6. Resource limits (resource exhaustion, not timeout-related)
        7. Network errors (connectivity failures, not timeouts)
        8. Probe failures (generic liveness/startup, not readiness)
        9. Deployment start (deployment initialization)
        10. Deployment complete (successful rollout)
        11. UNKNOWN (fallback - matches no pattern above)
    """
    DEPLOYMENT_START = 'deployment_start'
    DEPLOYMENT_COMPLETE = 'deployment_complete'
    POD_CRASH = 'pod_crash'
    OOM = 'oom'
    READINESS_FAIL = 'readiness_fail'
    TIMEOUT = 'timeout'
    IMAGE_PULL_ERROR = 'image_pull_error'
    RESOURCE_LIMIT = 'resource_limit'
    PROBE_FAILURE = 'probe_failure'
    NETWORK_ERROR = 'network_error'
    UNKNOWN = 'unknown'


def categorize_event(log_data: Dict[str, Any]) -> EventType:
    """
    Categorize a parsed event into a specific event type.

    Analyzes the parsed event fields to determine the specific event type.
    Returns a detailed event category that can be used for filtering,
    alerting, and analytics.

    The categorization process checks event patterns in order of specificity,
    from most specific (OOM) to most generic (deployment lifecycle). Events
    that match no known pattern are categorized as UNKNOWN, serving as a
    safe fallback to prevent data loss.

    **Fallback Behavior:**
    The UNKNOWN category is the FINAL fallback after ALL specific checks:
    1. Input validation (None, not dict, empty) → UNKNOWN
    2. OOM detection → if matched, return OOM; continue if not
    3. Image pull errors → if matched, return IMAGE_PULL_ERROR; continue if not
    4. Pod crashes → if matched, return POD_CRASH; continue if not
    5. Readiness failures → if matched, return READINESS_FAIL; continue if not
    6. Timeouts → if matched, return TIMEOUT; continue if not
    7. Resource limits → if matched, return RESOURCE_LIMIT; continue if not
    8. Network errors → if matched, return NETWORK_ERROR; continue if not
    9. Probe failures → if matched, return PROBE_FAILURE; continue if not
    10. Deployment start → if matched, return DEPLOYMENT_START; continue if not
    11. Deployment complete → if matched, return DEPLOYMENT_COMPLETE; continue if not
    12. **FINAL FALLBACK → UNKNOWN** (if nothing above matched)

    This ensures ALL events are categorized, preventing data loss.

    Args:
        log_data: A normalized event dictionary from parse_log.parse_entry()
                 with fields: timestamp, service, event_type, status,
                 error_code, duration_ms, cluster, namespace, metadata

    Returns:
        EventType enum value indicating the category of the event.
        Returns EventType.UNKNOWN if:
        - log_data is None, not a dict, or empty (input validation failure)
        - No specific event pattern matches after all checks (pattern mismatch)
        - Event lacks recognizable error indicators or deployment signatures

    Examples:
        >>> event = {'event_type': 'pod_status', 'status': 'failure',
        ...          'error_code': 'OOMKilled', ...}
        >>> categorize_event(event)
        <EventType.OOM: 'oom'>

        >>> event = {'event_type': 'unknown_type', 'status': 'unknown', ...}
        >>> categorize_event(event)
        <EventType.UNKNOWN: 'unknown'>
    """
    if not log_data or not isinstance(log_data, dict):
        return EventType.UNKNOWN

    # Get key fields
    event_type = log_data.get('event_type', '')
    status = log_data.get('status', '')
    error_code = log_data.get('error_code')
    metadata = log_data.get('metadata', {})
    source_fields = metadata.get('source_fields', {})

    # Check specific error types FIRST (in order of specificity)

    # Check OOM first (highest priority for failure categorization)
    if _is_oom_event(error_code, source_fields):
        return EventType.OOM

    # Check for image pull errors (very specific error pattern)
    if _is_image_pull_error(error_code, source_fields):
        return EventType.IMAGE_PULL_ERROR

    # Check for pod crashes BEFORE readiness failures (crashes are more specific)
    if _is_pod_crash(event_type, status, error_code, source_fields):
        return EventType.POD_CRASH

    # Check for readiness failures AFTER pod crashes (readiness issues are less specific)
    if _is_readiness_failure(event_type, status, error_code, source_fields):
        return EventType.READINESS_FAIL

    # Check for timeout events (but NOT DNS timeouts - those are network errors)
    if _is_timeout_event(error_code, source_fields, log_data):
        return EventType.TIMEOUT

    # Check for resource limit errors (but NOT timeout exceeded)
    if _is_resource_limit(error_code, source_fields):
        return EventType.RESOURCE_LIMIT

    # Check for network errors (but not connection/network timeouts which are handled above)
    if _is_network_error(error_code, source_fields):
        return EventType.NETWORK_ERROR

    # Check for generic probe failures (liveness, startup, but not readiness which is handled above)
    if _is_probe_failure(error_code, source_fields):
        return EventType.PROBE_FAILURE

    # Check for deployment lifecycle events LAST (most generic)
    # These only apply if no error condition was detected
    if _is_deployment_start(event_type, status):
        return EventType.DEPLOYMENT_START

    if _is_deployment_complete(event_type, status, source_fields):
        return EventType.DEPLOYMENT_COMPLETE

    # Final fallback: unknown events
    # This is the last resort when no specific pattern matches.
    # Events reach this point when they:
    # - Pass all validation checks (not None, proper dict structure)
    # - Have valid event_type, status, and metadata fields
    # - Do NOT match any of the specific detection patterns above
    #
    # This fallback ensures ALL events are categorized, preventing data loss
    # and allowing for later analysis of emerging event types that may not
    # fit into known patterns.
    return EventType.UNKNOWN


def _is_oom_event(error_code: Optional[str], source_fields: Dict[str, Any]) -> bool:
    """
    Check if event indicates an OOM (Out of Memory) kill.

    OOM detection rules:
    - error_code is 'OOMKilled'
    - error_code contains 'OOM'
    - source_fields.reason is 'OOMKilled'
    - source_fields.message contains 'out of memory' (case insensitive)
    - source_fields.exitCode is 137 (OOM kill signal in containers)

    Args:
        error_code: Error code from parsed event
        source_fields: Original raw fields from the log entry

    Returns:
        True if event indicates OOM, False otherwise
    """
    # Check error_code directly
    if error_code == 'OOMKilled':
        return True

    if error_code and 'OOM' in str(error_code).upper():
        return True

    # Check source_fields for OOM indicators
    if not isinstance(source_fields, dict):
        return False

    # Check Kubernetes event reason
    if source_fields.get('reason') == 'OOMKilled':
        return True

    # Check error messages
    message = source_fields.get('message', '')
    if isinstance(message, str) and 'out of memory' in message.lower():
        return True

    # Check container exit code (137 = OOM kill)
    exit_code = source_fields.get('exitCode')
    if exit_code == 137:
        return True

    # Check status.phase for OOM
    status_phase = source_fields.get('status', {}).get('phase') if isinstance(source_fields.get('status'), dict) else source_fields.get('status')
    if isinstance(status_phase, str) and 'oomkilled' in status_phase.lower():
        return True

    return False


def _is_deployment_start(event_type: str, status: str) -> bool:
    """
    Check if event represents a deployment starting.

    Deployment start detection rules:
    - event_type starts with 'deployment_' and status is 'success', 'warning', or 'created'
    - event_type contains 'deployment' and 'create' (deployment creation events)
    - event_type is 'replicaset_status' or contains 'replicaset' with creation indicators
    - event_type is 'event_started', 'event_pulling', 'event_pullings', or 'event_created'
    - status is 'created' (indicating resource creation)
    - Kubernetes event with reason 'Started', 'Pulling', or 'Created'

    Args:
        event_type: Event type from parsed event
        status: Status from parsed event

    Returns:
        True if event indicates deployment start, False otherwise
    """
    # Check for creation status (highest priority for deployment start)
    if status == 'created':
        # Deployment or ReplicaSet creation events
        if 'deployment' in event_type.lower() or 'replicaset' in event_type.lower():
            return True

    # Deployment events that indicate start
    if event_type.startswith('deployment_') and status in ('success', 'warning', 'created'):
        return True

    # Deployment creation events (deployment created, deployment updated starting rollout)
    event_type_lower = event_type.lower()
    if 'deployment' in event_type_lower:
        if any(term in event_type_lower for term in ('create', 'created', 'initial', 'starting', 'started')):
            return True

    # ReplicaSet creation events (initial ReplicaSet created for deployment)
    if 'replicaset' in event_type_lower:
        if any(term in event_type_lower for term in ('create', 'created', 'initial', 'new', 'generation')):
            return True

    # Kubernetes events indicating start or creation
    if event_type in ('event_started', 'event_pulling', 'event_pullings', 'event_created', 'event_creating'):
        return True

    return False


def _is_deployment_complete(event_type: str, status: str, source_fields: Dict[str, Any]) -> bool:
    """
    Check if event represents a deployment completion.

    Deployment complete detection rules:
    - event_type is 'replicaset_status' and status is 'success'
    - event_type is 'pod_status' with ready=True and restartCount=0
    - Kubernetes event with reason 'Ready' or 'Completed'
    - Message patterns: "Rollout completed", "Deployment successfully updated", "successfully updated"
    - ReplicaSet update success patterns

    Args:
        event_type: Event type from parsed event
        status: Status from parsed event
        source_fields: Original raw fields from the log entry

    Returns:
        True if event indicates deployment completion, False otherwise
    """
    # ReplicaSet fully ready
    if event_type == 'replicaset_status' and status == 'success':
        return True

    # Pod ready and stable (must have ready=True)
    if event_type == 'pod_status' and status == 'success':
        # Check if pod is actually ready
        if isinstance(source_fields, dict):
            ready = source_fields.get('ready')
            # Only categorize as complete if ready is True or not set (assume ready)
            if ready is False:
                return False  # Not ready, so not complete
        return True

    # Kubernetes events indicating completion
    if event_type in ('event_ready', 'event_completed'):
        return True

    # Check for rollout completion and deployment update success patterns
    if isinstance(source_fields, dict):
        message = source_fields.get('message', '')
        reason = source_fields.get('reason', '')

        # Check message for deployment completion patterns
        if isinstance(message, str):
            message_lower = message.lower()
            completion_patterns = [
                'rollout completed',
                'deployment successfully updated',
                'successfully updated',
                'replica set updated',
                'replicaset successfully updated',
                'deployment complete'
            ]
            if any(pattern in message_lower for pattern in completion_patterns):
                return True

        # Check reason for successful deployment completion indicators
        if isinstance(reason, str):
            reason_lower = reason.lower()
            if reason in ('RolloutComplete', 'DeploymentComplete', 'Updated', 'ReplicaSetUpdated'):
                return True

    return False


def _is_pod_crash(event_type: str, status: str, error_code: Optional[str],
                  source_fields: Dict[str, Any]) -> bool:
    """
    Check if event represents a pod crash.

    Pod crash detection rules:
    - event_type is 'pod_status' and status is 'failure'
    - error_code is 'failed', 'error', or 'crashloopbackoff'
    - source_fields.status is CrashLoopBackOff, Failed, or Error
    - source_fields.restartCount > 0

    Args:
        event_type: Event type from parsed event
        status: Status from parsed event
        error_code: Error code from parsed event
        source_fields: Original raw fields from the log entry

    Returns:
        True if event indicates pod crash, False otherwise
    """
    # Pod status failure
    if event_type == 'pod_status' and status == 'failure':
        return True

    # Check error_code for crash indicators
    if error_code and error_code.lower() in ('failed', 'error', 'crashloopbackoff'):
        return True

    # Check source_fields for pod status
    if isinstance(source_fields, dict):
        pod_status = source_fields.get('status', '')
        if isinstance(pod_status, str) and pod_status.lower() in ('crashloopbackoff', 'failed', 'error'):
            return True

        # Check restart count (any restarts indicate crashes)
        restart_count = source_fields.get('restartCount')
        if restart_count and isinstance(restart_count, int) and restart_count > 0:
            return True

        # Check container status
        if 'state' in source_fields:
            state = source_fields.get('state', {})
            if isinstance(state, dict) and 'terminated' in state:
                terminated = state['terminated']
                if isinstance(terminated, dict):
                    exit_code = terminated.get('exitCode')
                    # Non-zero exit codes indicate crashes
                    if exit_code and isinstance(exit_code, int) and exit_code != 0:
                        return True

    return False


def _is_readiness_failure(event_type: str, status: str, error_code: Optional[str],
                          source_fields: Dict[str, Any]) -> bool:
    """
    Check if event represents a readiness probe failure.

    Readiness failure detection rules:
    - error_code is specifically 'ReadinessFailed' or contains 'readiness'
    - source_fields.reason is 'Unready' or 'ReadinessFailed'
    - source_fields.message contains 'readiness' (not generic 'probe')
    - source_fields.ready is False (and not explicitly a probe failure)

    Note: This is distinct from generic probe failures and focuses on readiness-specific issues.

    Args:
        event_type: Event type from parsed event
        status: Status from parsed event
        error_code: Error code from parsed event
        source_fields: Original raw fields from the log entry

    Returns:
        True if event indicates readiness failure, False otherwise
    """
    # Check error_code for readiness-specific indicators
    if error_code:
        error_str = str(error_code).lower()
        if 'readiness' in error_str:
            return True
        if error_code == 'ReadinessFailed':
            return True

    # Check source_fields
    if not isinstance(source_fields, dict):
        return False

    # Check Kubernetes event reason (readiness-specific)
    reason = source_fields.get('reason', '')
    if reason in ('Unready', 'ReadinessFailed', 'ContainersNotReady'):
        return True

    # Check message for readiness-specific failures (not generic probe failures)
    message = source_fields.get('message', '')
    if isinstance(message, str):
        message_lower = message.lower()
        # Look for 'readiness' specifically, not just 'probe'
        if 'readiness' in message_lower and 'probe' in message_lower:
            return True

    # Check ready field explicitly (only if not a crash or other failure state)
    ready = source_fields.get('ready')
    if ready is False:
        pod_status = source_fields.get('status', '')
        # Only categorize as readiness failure if pod is running but not ready
        if isinstance(pod_status, str) and pod_status.lower() == 'running':
            return True
        # Also categorize as readiness failure if there's an explicit readiness indicator
        if (event_type and 'readiness' in event_type.lower() or
            error_code and 'readiness' in str(error_code).lower() or
            reason and 'readiness' in reason.lower()):
            return True
        # If ready=False and event_type is pod_status, categorize as readiness failure
        # This handles the case where a pod is not ready but hasn't failed otherwise
        if event_type == 'pod_status':
            return True

    # Check pod conditions for readiness-specific failures
    conditions = source_fields.get('conditions', [])
    if isinstance(conditions, list):
        for condition in conditions:
            if isinstance(condition, dict):
                if condition.get('type') == 'Ready' and condition.get('status') != 'True':
                    return True

    return False


def _is_timeout_event(error_code: Optional[str], source_fields: Dict[str, Any],
                      parsed_event: Dict[str, Any]) -> bool:
    """
    Check if event represents a timeout.

    Timeout detection rules:
    - error_code contains 'timeout' (but not 'DNSTimeout' which is a network error)
    - error_code is 'DeadlineExceeded' (but not resource limit related)
    - source_fields.reason is 'DeadlineExceeded' or 'TimedOut'
    - source_fields.message contains 'timeout' (but not just 'timeout' in generic context)
    - duration_ms exceeds threshold (default 10 minutes = 600000 ms)

    Note: Connection and network timeouts ARE categorized as timeout events,
    not network_error. Network_error is for connection failures, not timeouts.
    DNS timeouts are network errors, not timeout events.

    Args:
        error_code: Error code from parsed event
        source_fields: Original raw fields from the log entry
        parsed_event: Full parsed event for duration checking

    Returns:
        True if event indicates timeout, False otherwise
    """
    # Check error_code for timeout indicators (but NOT DNS timeout which is network error)
    if error_code:
        error_str = str(error_code).lower()
        # DNS timeout is a network error, not a timeout event
        if 'dns' in error_str and 'timeout' in error_str:
            return False
        if 'timeout' in error_str or error_code == 'DeadlineExceeded':
            return True

    # Check source_fields
    if not isinstance(source_fields, dict):
        return False

    # Check Kubernetes event reason
    reason = source_fields.get('reason', '')
    if reason in ('DeadlineExceeded', 'TimedOut'):
        # Don't categorize as timeout if it's actually a resource limit issue
        message = source_fields.get('message', '')
        if isinstance(message, str) and 'insufficient' in message.lower():
            return False
        return True

    # Check message for timeout indicators (but avoid 'readiness probe timeout' which is a probe failure)
    message = source_fields.get('message', '')
    if isinstance(message, str):
        message_lower = message.lower()
        # Look for 'timeout' specifically (but avoid 'readiness probe timeout' which is a probe failure)
        if 'timeout' in message_lower and 'readiness probe' not in message_lower:
            return True

    # Check duration (10 minute threshold) - only if not a CrashLoopBackOff
    duration_ms = parsed_event.get('duration_ms')
    if duration_ms and isinstance(duration_ms, int) and duration_ms > 600000:
        # Don't categorize CrashLoopBackOff pods as timeout
        pod_status = source_fields.get('status', '') if isinstance(source_fields, dict) else ''
        if 'crashloopbackoff' not in str(pod_status).lower():
            return True

    return False


def _is_image_pull_error(error_code: Optional[str], source_fields: Dict[str, Any]) -> bool:
    """
    Check if event represents an image pull error.

    Image pull error detection rules:
    - error_code is 'ErrImagePull' or 'ImagePullBackOff'
    - source_fields.reason contains 'Image' or 'Pull'
    - source_fields.message contains 'image pull' or 'back-off pulling image'

    Args:
        error_code: Error code from parsed event
        source_fields: Original raw fields from the log entry

    Returns:
        True if event indicates image pull error, False otherwise
    """
    # Check error_code for image pull indicators
    if error_code and error_code in ('ErrImagePull', 'ImagePullBackOff', 'ErrImageNeverPull'):
        return True

    if error_code and 'image' in str(error_code).lower() and 'pull' in str(error_code).lower():
        return True

    # Check source_fields
    if not isinstance(source_fields, dict):
        return False

    # Check Kubernetes event reason
    reason = source_fields.get('reason', '')
    if 'image' in reason.lower() and 'pull' in reason.lower():
        return True

    if reason in ('ErrImagePull', 'ImagePullBackOff', 'ErrImageNeverPull', 'Failed'):
        # Check if it's specifically an image error (other failures also use 'Failed')
        message = source_fields.get('message', '')
        if isinstance(message, str) and 'image' in message.lower():
            return True

    # Check message for image pull indicators
    message = source_fields.get('message', '')
    if isinstance(message, str) and 'image' in message.lower():
        if 'pull' in message.lower() or 'back-off' in message.lower():
            return True

    return False


def _is_resource_limit(error_code: Optional[str], source_fields: Dict[str, Any]) -> bool:
    """
    Check if event represents a resource limit error.

    Resource limit detection rules:
    - error_code contains 'resource' or 'limit' or 'quota'
    - source_fields.reason is 'Insufficient' (cpu, memory, etc.)
    - source_fields.message contains 'insufficient' (cpu, memory, disk, etc.)

    Note: DeadlineExceeded is NOT a resource limit - it's a timeout event.

    Args:
        error_code: Error code from parsed event
        source_fields: Original raw fields from the log entry

    Returns:
        True if event indicates resource limit error, False otherwise
    """
    # Check source_fields
    if not isinstance(source_fields, dict):
        return False

    # Don't categorize DeadlineExceeded as resource limit (it's a timeout)
    reason = source_fields.get('reason', '')
    if reason == 'DeadlineExceeded':
        return False

    message = source_fields.get('message', '')
    if isinstance(message, str) and 'deadline' in message.lower() and 'exceeded' in message.lower():
        return False

    # Check error_code for resource limit indicators (but not deadline exceeded)
    if error_code:
        error_str = str(error_code).lower()
        if 'deadline' in error_str:
            return False
        if any(term in error_str for term in ('resource', 'limit', 'quota', 'exceeded')):
            return True

    # Check Kubernetes event reason
    if 'insufficient' in reason.lower() or 'resource' in reason.lower():
        return True

    if reason == 'FailedScheduling':
        # Verify it's a scheduling failure due to resources
        if isinstance(message, str) and 'insufficient' in message.lower():
            return True

    # Check message for resource limit indicators
    if isinstance(message, str):
        message_lower = message.lower()
        resource_terms = ['insufficient', 'limit exceeded', 'out of', 'quota exceeded']
        if any(term in message_lower for term in resource_terms):
            return True

    return False


def _is_probe_failure(error_code: Optional[str], source_fields: Dict[str, Any]) -> bool:
    """
    Check if event represents a generic probe failure (liveness or startup).

    Probe failure detection rules:
    - error_code contains 'probe' but not 'readiness'
    - source_fields.reason is 'Unhealthy' or 'ProbeFailed' but not readiness-specific
    - source_fields.message contains 'probe' but not 'readiness'

    Note: Readiness probe failures are categorized as readiness_failure events
    and are checked BEFORE this function. This function handles liveness and
    startup probe failures only.

    Args:
        error_code: Error code from parsed event
        source_fields: Original raw fields from the log entry

    Returns:
        True if event indicates generic probe failure, False otherwise
    """
    # Check error_code for probe indicators (but not readiness-specific)
    if error_code:
        error_str = str(error_code).lower()
        if 'readiness' in error_str:
            return False  # Readiness failures are handled separately
        if 'probe' in error_str:
            return True

    # Check source_fields
    if not isinstance(source_fields, dict):
        return False

    # Check Kubernetes event reason (but not readiness-specific)
    reason = source_fields.get('reason', '')
    if reason in ('Unhealthy', 'ProbeFailed', 'ProbeWarning'):
        # Exclude readiness-specific reasons
        if reason not in ('ReadinessFailed', 'Unready'):
            return True

    # Check message for probe failures (but not readiness-specific)
    message = source_fields.get('message', '')
    if isinstance(message, str):
        message_lower = message.lower()
        # Check for probe failures but exclude readiness-specific ones
        if 'probe' in message_lower and 'readiness' not in message_lower:
            return True

    return False


def _is_network_error(error_code: Optional[str], source_fields: Dict[str, Any]) -> bool:
    """
    Check if event represents a network error.

    Network error detection rules:
    - error_code contains 'network' or 'connection' or 'dns' (but not 'timeout' - those are handled separately)
    - source_fields.reason is 'NetworkError' or 'ConnectionRefused'
    - source_fields.message contains 'network', 'connection', 'dns', 'unreachable' (but not 'timeout' or 'probe')

    Note: Timeouts (including connection timeouts) are categorized as timeout events,
    not network_error. DNS timeouts ARE network errors (not timeout events).
    This function is for network connectivity failures only.

    Args:
        error_code: Error code from parsed event
        source_fields: Original raw fields from the log entry

    Returns:
        True if event indicates network error, False otherwise
    """
    # Check error_code for network indicators (including DNS)
    if error_code:
        error_str = str(error_code).lower()
        # DNS timeout is a network error (not a timeout event)
        if 'dns' in error_str and 'timeout' in error_str:
            return True
        # Exclude timeout error codes - those are handled by _is_timeout_event
        if 'timeout' in error_str and 'dns' not in error_str:
            return False
        if any(term in error_str for term in ('network', 'connection', 'dns', 'networkerror')):
            return True

    # Check source_fields
    if not isinstance(source_fields, dict):
        return False

    # Check Kubernetes event reason
    reason = source_fields.get('reason', '')
    reason_lower = reason.lower()
    if any(term in reason_lower for term in ('network', 'connection', 'dns')):
        return True

    # Check message for network errors (but not timeouts or probe failures)
    message = source_fields.get('message', '')
    if isinstance(message, str):
        message_lower = message.lower()
        # Exclude timeout and probe messages - those are handled elsewhere
        if 'timeout' in message_lower and 'readiness probe' not in message_lower and 'liveness probe' not in message_lower and 'startup probe' not in message_lower:
            return False
        # Don't match probe failures as network errors
        if 'probe' in message_lower:
            return False
        network_terms = ['network', 'connection refused', 'dns', 'unreachable', 'connection failed']
        if any(term in message_lower for term in network_terms):
            return True

    return False


def get_event_type_display_name(event_type: EventType) -> str:
    """
    Get a human-readable display name for an event type.

    Args:
        event_type: EventType enum value

    Returns:
        Human-readable display name
    """
    display_names = {
        EventType.DEPLOYMENT_START: 'Deployment Start',
        EventType.DEPLOYMENT_COMPLETE: 'Deployment Complete',
        EventType.POD_CRASH: 'Pod Crash',
        EventType.OOM: 'Out of Memory',
        EventType.READINESS_FAIL: 'Readiness Failure',
        EventType.TIMEOUT: 'Timeout',
        EventType.IMAGE_PULL_ERROR: 'Image Pull Error',
        EventType.RESOURCE_LIMIT: 'Resource Limit',
        EventType.PROBE_FAILURE: 'Probe Failure',
        EventType.NETWORK_ERROR: 'Network Error',
        EventType.UNKNOWN: 'Unknown Event'
    }
    return display_names.get(event_type, 'Unknown Event')


def get_all_event_types() -> List[EventType]:
    """
    Get a list of all supported event types.

    Returns:
        List of EventType enum values
    """
    return list(EventType)


# -----------------------------------------------------------------------------
# Module-level constants for backward compatibility and test imports
# These constants provide direct access to EventType enum values
# -----------------------------------------------------------------------------

# Deployment lifecycle events
EVENT_DEPLOYMENT_START = EventType.DEPLOYMENT_START
EVENT_DEPLOYMENT_COMPLETE = EventType.DEPLOYMENT_COMPLETE

# Failure event types
EVENT_POD_CRASH = EventType.POD_CRASH
EVENT_OOM = EventType.OOM
EVENT_READINESS_FAIL = EventType.READINESS_FAIL
EVENT_TIMEOUT = EventType.TIMEOUT
EVENT_IMAGE_PULL_ERROR = EventType.IMAGE_PULL_ERROR
EVENT_RESOURCE_LIMIT = EventType.RESOURCE_LIMIT
EVENT_PROBE_FAILURE = EventType.PROBE_FAILURE
EVENT_NETWORK_ERROR = EventType.NETWORK_ERROR

# Uncategorized events
EVENT_UNKNOWN = EventType.UNKNOWN


def categorize_events_batch(events: List[Dict[str, Any]]) -> Dict[EventType, List[Dict[str, Any]]]:
    """
    Categorize a batch of events and group them by type.

    Args:
        events: List of parsed event dictionaries from parse_log.parse_entry()

    Returns:
        Dictionary mapping EventType to list of events of that type:
        {
            EventType.OOM: [...],
            EventType.POD_CRASH: [...],
            EventType.UNKNOWN: [...],
            ...
        }
    """
    categorized = {event_type: [] for event_type in get_all_event_types()}

    for event in events:
        event_type = categorize_event(event)
        categorized[event_type].append(event)

    return categorized