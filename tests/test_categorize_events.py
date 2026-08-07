"""
Comprehensive unit tests for event categorization module.

Tests cover all event type detection rules with real log samples from
Kubernetes events, pod status, deployment logs, and ReplicaSet status.
"""

import pytest
from src.categorize_events import (
    # Constants
    EVENT_DEPLOYMENT_START,
    EVENT_DEPLOYMENT_COMPLETE,
    EVENT_POD_CRASH,
    EVENT_OOM,
    EVENT_READINESS_FAIL,
    EVENT_TIMEOUT,
    EVENT_IMAGE_PULL_ERROR,
    EVENT_RESOURCE_LIMIT,
    EVENT_PROBE_FAILURE,
    EVENT_NETWORK_ERROR,
    EVENT_UNKNOWN,
    # Main functions
    categorize_event,
    categorize_events_batch,
    get_event_type_display_name,
    get_all_event_types,
    # Helper functions
    _is_oom_event,
    _is_deployment_start,
    _is_deployment_complete,
    _is_pod_crash,
    _is_readiness_failure,
    _is_timeout_event,
    _is_image_pull_error,
    _is_resource_limit,
    _is_probe_failure,
    _is_network_error,
)


# -----------------------------------------------------------------------------
# Test fixtures
# -----------------------------------------------------------------------------

@pytest.fixture
def base_parsed_event():
    """Base parsed event structure."""
    return {
        'timestamp': '2026-08-06T12:00:00Z',
        'service': 'test-service',
        'event_type': 'pod_status',
        'status': 'success',
        'error_code': None,
        'duration_ms': None,
        'cluster': 'ardenone-cluster',
        'namespace': 'test-ns',
        'metadata': {
            'source_fields': {},
            'raw_format': 'pod'
        }
    }


# -----------------------------------------------------------------------------
# Tests for categorize_event() - Main entry point
# -----------------------------------------------------------------------------

class TestCategorizeEvent:
    """Tests for categorize_event() function."""

    def test_none_input_returns_unknown(self):
        """None input returns unknown."""
        result = categorize_event(None)
        assert result == EVENT_UNKNOWN

    def test_invalid_input_returns_unknown(self):
        """Invalid input returns unknown."""
        result = categorize_event("not a dict")
        assert result == EVENT_UNKNOWN

    def test_empty_dict_returns_unknown(self):
        """Empty dict returns unknown."""
        result = categorize_event({})
        assert result == EVENT_UNKNOWN


# -----------------------------------------------------------------------------
# Tests for OOM detection
# -----------------------------------------------------------------------------

class TestOOMDetection:
    """Tests for OOM (Out of Memory) event detection."""

    def test_oom_error_code_detected(self, base_parsed_event):
        """error_code='OOMKilled' is detected as OOM."""
        base_parsed_event['error_code'] = 'OOMKilled'
        result = categorize_event(base_parsed_event)
        assert result == EVENT_OOM

    def test_oom_in_error_code_detected(self, base_parsed_event):
        """error_code containing 'OOM' is detected."""
        base_parsed_event['error_code'] = 'PostOOMKilled'
        result = categorize_event(base_parsed_event)
        assert result == EVENT_OOM

    def test_oom_reason_in_source_fields(self, base_parsed_event):
        """source_fields.reason='OOMKilled' is detected."""
        base_parsed_event['metadata']['source_fields']['reason'] = 'OOMKilled'
        result = categorize_event(base_parsed_event)
        assert result == EVENT_OOM

    def test_oom_message_in_source_fields(self, base_parsed_event):
        """source_fields.message with 'out of memory' is detected."""
        base_parsed_event['metadata']['source_fields']['message'] = 'Container out of memory'
        result = categorize_event(base_parsed_event)
        assert result == EVENT_OOM

    def test_exit_code_137_detected_as_oom(self, base_parsed_event):
        """exitCode 137 is detected as OOM."""
        base_parsed_event['metadata']['source_fields']['exitCode'] = 137
        result = categorize_event(base_parsed_event)
        assert result == EVENT_OOM

    def test_status_phase_oomkilled_detected(self, base_parsed_event):
        """status.phase='OOMKilled' is detected."""
        base_parsed_event['metadata']['source_fields']['status'] = {'phase': 'OOMKilled'}
        result = categorize_event(base_parsed_event)
        assert result == EVENT_OOM

    def test_real_oom_event_sample(self, base_parsed_event):
        """Real Kubernetes OOM event sample."""
        base_parsed_event.update({
            'event_type': 'event_oomkilled',
            'status': 'warning',
            'error_code': 'OOMKilled',
            'metadata': {
                'source_fields': {
                    'type': 'Warning',
                    'reason': 'OOMKilled',
                    'message': 'Container was killed because it used more memory than its limit.',
                    'firstTimestamp': '2026-08-06T12:00:00Z'
                },
                'raw_format': 'event'
            }
        })
        result = categorize_event(base_parsed_event)
        assert result == EVENT_OOM

    def test_non_oom_event_not_categorized_as_oom(self, base_parsed_event):
        """Non-OOM event is not categorized as OOM."""
        base_parsed_event['error_code'] = 'CrashLoopBackOff'
        result = categorize_event(base_parsed_event)
        assert result != EVENT_OOM


# -----------------------------------------------------------------------------
# Tests for deployment lifecycle events
# -----------------------------------------------------------------------------

class TestDeploymentLifecycle:
    """Tests for deployment start and complete detection."""

    def test_deployment_start_feature_addition(self, base_parsed_event):
        """Deployment with feature_addition type is deployment_start."""
        base_parsed_event.update({
            'event_type': 'deployment_feature_addition',
            'status': 'success',
            'error_code': None
        })
        result = categorize_event(base_parsed_event)
        assert result == EVENT_DEPLOYMENT_START

    def test_deployment_start_initial_deployment(self, base_parsed_event):
        """Initial deployment is deployment_start."""
        base_parsed_event.update({
            'event_type': 'deployment_initial_deployment',
            'status': 'success'
        })
        result = categorize_event(base_parsed_event)
        assert result == EVENT_DEPLOYMENT_START

    def test_kubernetes_event_started(self, base_parsed_event):
        """Kubernetes event with reason='Started' is deployment_start."""
        base_parsed_event.update({
            'event_type': 'event_started',
            'status': 'success',
            'metadata': {
                'source_fields': {
                    'type': 'Normal',
                    'reason': 'Started',
                    'message': 'Started container'
                }
            }
        })
        result = categorize_event(base_parsed_event)
        assert result == EVENT_DEPLOYMENT_START

    def test_deployment_complete_replicaset_ready(self, base_parsed_event):
        """ReplicaSet with all replicas ready is deployment_complete."""
        base_parsed_event.update({
            'event_type': 'replicaset_status',
            'status': 'success',
            'metadata': {
                'source_fields': {
                    'replicas': 3,
                    'readyReplicas': 3
                }
            }
        })
        result = categorize_event(base_parsed_event)
        assert result == EVENT_DEPLOYMENT_COMPLETE

    def test_deployment_complete_pod_ready(self, base_parsed_event):
        """Pod with ready=True is deployment_complete."""
        base_parsed_event.update({
            'event_type': 'pod_status',
            'status': 'success',
            'metadata': {
                'source_fields': {
                    'ready': True,
                    'restartCount': 0
                }
            }
        })
        result = categorize_event(base_parsed_event)
        assert result == EVENT_DEPLOYMENT_COMPLETE

    def test_deployment_failure_not_complete(self, base_parsed_event):
        """Failed deployment is not deployment_complete."""
        base_parsed_event.update({
            'event_type': 'replicaset_status',
            'status': 'failure'
        })
        result = categorize_event(base_parsed_event)
        assert result != EVENT_DEPLOYMENT_COMPLETE


# -----------------------------------------------------------------------------
# Tests for pod crash detection
# -----------------------------------------------------------------------------

class TestPodCrashDetection:
    """Tests for pod crash detection."""

    def test_pod_status_failure_is_crash(self, base_parsed_event):
        """Pod status with failure status is pod_crash."""
        base_parsed_event.update({
            'event_type': 'pod_status',
            'status': 'failure',
            'error_code': 'failed'
        })
        result = categorize_event(base_parsed_event)
        assert result == EVENT_POD_CRASH

    def test_crashloopbackoff_is_crash(self, base_parsed_event):
        """CrashLoopBackOff status is pod_crash."""
        base_parsed_event.update({
            'event_type': 'pod_status',
            'status': 'failure',
            'error_code': 'crashloopbackoff',
            'metadata': {
                'source_fields': {
                    'status': 'CrashLoopBackOff'
                }
            }
        })
        result = categorize_event(base_parsed_event)
        assert result == EVENT_POD_CRASH

    def test_restart_count_positive_is_crash(self, base_parsed_event):
        """Pod with restartCount > 0 is pod_crash."""
        base_parsed_event.update({
            'event_type': 'pod_status',
            'status': 'warning',
            'metadata': {
                'source_fields': {
                    'restartCount': 3
                }
            }
        })
        result = categorize_event(base_parsed_event)
        assert result == EVENT_POD_CRASH

    def test_nonzero_exit_code_is_crash(self, base_parsed_event):
        """Container with non-zero exit code is pod_crash."""
        base_parsed_event.update({
            'event_type': 'pod_status',
            'metadata': {
                'source_fields': {
                    'state': {
                        'terminated': {
                            'exitCode': 1,
                            'reason': 'Error'
                        }
                    }
                }
            }
        })
        result = categorize_event(base_parsed_event)
        assert result == EVENT_POD_CRASH

    def test_zero_exit_code_not_crash(self, base_parsed_event):
        """Container with exit code 0 is not crash."""
        base_parsed_event.update({
            'event_type': 'pod_status',
            'metadata': {
                'source_fields': {
                    'state': {
                        'terminated': {
                            'exitCode': 0,
                            'reason': 'Completed'
                        }
                    }
                }
            }
        })
        result = categorize_event(base_parsed_event)
        assert result != EVENT_POD_CRASH

    def test_real_crashloopbackoff_sample(self, base_parsed_event):
        """Real CrashLoopBackOff pod sample."""
        base_parsed_event.update({
            'timestamp': '2026-08-06T12:30:00Z',
            'service': 'whisper-stt',
            'event_type': 'pod_status',
            'status': 'failure',
            'error_code': 'crashloopbackoff',
            'metadata': {
                'source_fields': {
                    'name': 'whisper-stt-abc123',
                    'status': 'CrashLoopBackOff',
                    'restartCount': 5,
                    'ready': False
                },
                'raw_format': 'pod'
            }
        })
        result = categorize_event(base_parsed_event)
        assert result == EVENT_POD_CRASH


# -----------------------------------------------------------------------------
# Tests for readiness failure detection
# -----------------------------------------------------------------------------

class TestReadinessFailureDetection:
    """Tests for readiness failure detection."""

    def test_readiness_in_error_code(self, base_parsed_event):
        """error_code containing 'readiness' is detected."""
        base_parsed_event['error_code'] = 'ReadinessProbeFailed'
        result = categorize_event(base_parsed_event)
        assert result == EVENT_READINESS_FAIL

    def test_unready_reason_detected(self, base_parsed_event):
        """reason='Unready' is detected."""
        base_parsed_event['metadata']['source_fields']['reason'] = 'Unready'
        result = categorize_event(base_parsed_event)
        assert result == EVENT_READINESS_FAIL

    def test_readiness_probe_failed_message(self, base_parsed_event):
        """Message with 'readiness probe failed' is detected."""
        base_parsed_event['metadata']['source_fields']['message'] = 'Readiness probe failed: HTTP 503'
        result = categorize_event(base_parsed_event)
        assert result == EVENT_READINESS_FAIL

    def test_ready_false_detected(self, base_parsed_event):
        """ready=False is detected."""
        base_parsed_event['metadata']['source_fields']['ready'] = False
        result = categorize_event(base_parsed_event)
        assert result == EVENT_READINESS_FAIL

    def test_ready_condition_false(self, base_parsed_event):
        """Condition with Ready=False is detected."""
        base_parsed_event['metadata']['source_fields']['conditions'] = [
            {'type': 'Ready', 'status': 'False'}
        ]
        result = categorize_event(base_parsed_event)
        assert result == EVENT_READINESS_FAIL

    def test_ready_condition_unknown(self, base_parsed_event):
        """Condition with Ready='Unknown' is detected."""
        base_parsed_event['metadata']['source_fields']['conditions'] = [
            {'type': 'Ready', 'status': 'Unknown'}
        ]
        result = categorize_event(base_parsed_event)
        assert result == EVENT_READINESS_FAIL

    def test_real_readiness_failure_sample(self, base_parsed_event):
        """Real readiness failure sample."""
        base_parsed_event.update({
            'event_type': 'event_unready',
            'status': 'warning',
            'error_code': 'ReadinessFailed',
            'metadata': {
                'source_fields': {
                    'type': 'Warning',
                    'reason': 'Unready',
                    'message': 'Readiness probe failed: Get http://pod:8080/health: dial tcp 10.0.0.1:8080: connect: connection refused'
                }
            }
        })
        result = categorize_event(base_parsed_event)
        assert result == EVENT_READINESS_FAIL


# -----------------------------------------------------------------------------
# Tests for timeout detection
# -----------------------------------------------------------------------------

class TestTimeoutDetection:
    """Tests for timeout event detection."""

    def test_timeout_in_error_code(self, base_parsed_event):
        """error_code containing 'timeout' is detected."""
        base_parsed_event['error_code'] = 'ConnectionTimeout'
        result = categorize_event(base_parsed_event)
        assert result == EVENT_TIMEOUT

    def test_deadline_exceeded_reason(self, base_parsed_event):
        """reason='DeadlineExceeded' is detected."""
        base_parsed_event['metadata']['source_fields']['reason'] = 'DeadlineExceeded'
        result = categorize_event(base_parsed_event)
        assert result == EVENT_TIMEOUT

    def test_timeout_message(self, base_parsed_event):
        """Message with 'timeout' is detected."""
        base_parsed_event['metadata']['source_fields']['message'] = 'Request timeout after 30s'
        result = categorize_event(base_parsed_event)
        assert result == EVENT_TIMEOUT

    def test_duration_exceeds_threshold(self, base_parsed_event):
        """duration_ms > 600000 (10 minutes) is detected."""
        base_parsed_event['duration_ms'] = 600001  # Just over 10 minutes
        result = categorize_event(base_parsed_event)
        assert result == EVENT_TIMEOUT

    def test_duration_below_threshold_not_timeout(self, base_parsed_event):
        """duration_ms < 600000 is not timeout."""
        base_parsed_event['duration_ms'] = 599999  # Just under 10 minutes
        result = categorize_event(base_parsed_event)
        assert result != EVENT_TIMEOUT

    def test_real_timeout_sample(self, base_parsed_event):
        """Real Kubernetes timeout sample."""
        base_parsed_event.update({
            'event_type': 'event_deadlineexceeded',
            'status': 'warning',
            'error_code': 'DeadlineExceeded',
            'duration_ms': 900000,
            'metadata': {
                'source_fields': {
                    'type': 'Warning',
                    'reason': 'DeadlineExceeded',
                    'message': 'Job was active longer than specified deadline'
                }
            }
        })
        result = categorize_event(base_parsed_event)
        assert result == EVENT_TIMEOUT


# -----------------------------------------------------------------------------
# Tests for image pull error detection
# -----------------------------------------------------------------------------

class TestImagePullErrorDetection:
    """Tests for image pull error detection."""

    def test_err_image_pull_error_code(self, base_parsed_event):
        """error_code='ErrImagePull' is detected."""
        base_parsed_event['error_code'] = 'ErrImagePull'
        result = categorize_event(base_parsed_event)
        assert result == EVENT_IMAGE_PULL_ERROR

    def test_image_pull_back_off(self, base_parsed_event):
        """error_code='ImagePullBackOff' is detected."""
        base_parsed_event['error_code'] = 'ImagePullBackOff'
        result = categorize_event(base_parsed_event)
        assert result == EVENT_IMAGE_PULL_ERROR

    def test_image_pull_in_reason(self, base_parsed_event):
        """reason containing 'image' and 'pull' is detected."""
        base_parsed_event['metadata']['source_fields']['reason'] = 'ImagePullError'
        result = categorize_event(base_parsed_event)
        assert result == EVENT_IMAGE_PULL_ERROR

    def test_back_off_pull_in_message(self, base_parsed_event):
        """Message with 'back-off pulling image' is detected."""
        base_parsed_event['metadata']['source_fields']['message'] = 'Back-off pulling image: image not found'
        result = categorize_event(base_parsed_event)
        assert result == EVENT_IMAGE_PULL_ERROR

    def test_real_image_pull_error_sample(self, base_parsed_event):
        """Real image pull error sample."""
        base_parsed_event.update({
            'event_type': 'event_errimagepull',
            'status': 'warning',
            'error_code': 'ErrImagePull',
            'metadata': {
                'source_fields': {
                    'type': 'Warning',
                    'reason': 'ErrImagePull',
                    'message': 'Back-off pulling image "myapp:v1": rpc error: code = Unknown desc = Error response from daemon: pull access denied'
                }
            }
        })
        result = categorize_event(base_parsed_event)
        assert result == EVENT_IMAGE_PULL_ERROR


# -----------------------------------------------------------------------------
# Tests for resource limit detection
# -----------------------------------------------------------------------------

class TestResourceLimitDetection:
    """Tests for resource limit error detection."""

    def test_resource_in_error_code(self, base_parsed_event):
        """error_code containing 'resource' is detected."""
        base_parsed_event['error_code'] = 'ResourceQuotaExceeded'
        result = categorize_event(base_parsed_event)
        assert result == EVENT_RESOURCE_LIMIT

    def test_insufficient_in_reason(self, base_parsed_event):
        """reason='Insufficient' is detected."""
        base_parsed_event['metadata']['source_fields']['reason'] = 'FailedScheduling'
        base_parsed_event['metadata']['source_fields']['message'] = 'Insufficient cpu'
        result = categorize_event(base_parsed_event)
        assert result == EVENT_RESOURCE_LIMIT

    def test_insufficient_memory_message(self, base_parsed_event):
        """Message with 'insufficient memory' is detected."""
        base_parsed_event['metadata']['source_fields']['message'] = 'Insufficient memory in node-1'
        result = categorize_event(base_parsed_event)
        assert result == EVENT_RESOURCE_LIMIT

    def test_real_resource_limit_sample(self, base_parsed_event):
        """Real Kubernetes resource limit sample."""
        base_parsed_event.update({
            'event_type': 'event_failedscheduling',
            'status': 'warning',
            'error_code': 'FailedScheduling',
            'metadata': {
                'source_fields': {
                    'type': 'Warning',
                    'reason': 'FailedScheduling',
                    'message': 'Insufficient cpu'
                }
            }
        })
        result = categorize_event(base_parsed_event)
        assert result == EVENT_RESOURCE_LIMIT


# -----------------------------------------------------------------------------
# Tests for probe failure detection
# -----------------------------------------------------------------------------

class TestProbeFailureDetection:
    """Tests for probe failure detection."""

    def test_probe_in_error_code(self, base_parsed_event):
        """error_code containing 'probe' is detected."""
        base_parsed_event['error_code'] = 'LivenessProbeFailed'
        result = categorize_event(base_parsed_event)
        assert result == EVENT_PROBE_FAILURE

    def test_unhealthy_reason(self, base_parsed_event):
        """reason='Unhealthy' is detected."""
        base_parsed_event['metadata']['source_fields']['reason'] = 'Unhealthy'
        result = categorize_event(base_parsed_event)
        assert result == EVENT_PROBE_FAILURE

    def test_probe_failed_message(self, base_parsed_event):
        """Message with 'probe' is detected."""
        base_parsed_event['metadata']['source_fields']['message'] = 'Liveness probe failed: connection refused'
        result = categorize_event(base_parsed_event)
        assert result == EVENT_PROBE_FAILURE

    def test_real_probe_failure_sample(self, base_parsed_event):
        """Real probe failure sample."""
        base_parsed_event.update({
            'event_type': 'event_unhealthy',
            'status': 'warning',
            'error_code': 'Unhealthy',
            'metadata': {
                'source_fields': {
                    'type': 'Warning',
                    'reason': 'Unhealthy',
                    'message': 'Liveness probe failed: HTTP probe failed with statuscode: 500'
                }
            }
        })
        result = categorize_event(base_parsed_event)
        assert result == EVENT_PROBE_FAILURE


# -----------------------------------------------------------------------------
# Tests for network error detection
# -----------------------------------------------------------------------------

class TestNetworkErrorDetection:
    """Tests for network error detection."""

    def test_network_in_error_code(self, base_parsed_event):
        """error_code containing 'network' is detected."""
        base_parsed_event['error_code'] = 'NetworkError'
        result = categorize_event(base_parsed_event)
        assert result == EVENT_NETWORK_ERROR

    def test_connection_in_error_code(self, base_parsed_event):
        """error_code containing 'connection' is detected."""
        base_parsed_event['error_code'] = 'ConnectionRefused'
        result = categorize_event(base_parsed_event)
        assert result == EVENT_NETWORK_ERROR

    def test_dns_in_error_code(self, base_parsed_event):
        """error_code containing 'dns' is detected."""
        base_parsed_event['error_code'] = 'DNSTimeout'
        result = categorize_event(base_parsed_event)
        assert result == EVENT_NETWORK_ERROR

    def test_connection_refused_message(self, base_parsed_event):
        """Message with 'connection refused' is detected."""
        base_parsed_event['metadata']['source_fields']['message'] = 'dial tcp: connection refused'
        result = categorize_event(base_parsed_event)
        assert result == EVENT_NETWORK_ERROR

    def test_real_network_error_sample(self, base_parsed_event):
        """Real network error sample."""
        base_parsed_event.update({
            'event_type': 'event_networkerror',
            'status': 'warning',
            'error_code': 'NetworkUnavailable',
            'metadata': {
                'source_fields': {
                    'type': 'Warning',
                    'reason': 'NetworkError',
                    'message': 'Network: DNS resolution failed'
                }
            }
        })
        result = categorize_event(base_parsed_event)
        assert result == EVENT_NETWORK_ERROR


# -----------------------------------------------------------------------------
# Tests for unknown event categorization
# -----------------------------------------------------------------------------

class TestUnknownEventCategorization:
    """Tests for unknown event categorization."""

    def test_uncategorizable_event_is_unknown(self, base_parsed_event):
        """Event with no categorizable features is unknown."""
        base_parsed_event.update({
            'event_type': 'random_event',
            'status': 'unknown',
            'error_code': None,
            'metadata': {
                'source_fields': {
                    'random_field': 'random_value'
                }
            }
        })
        result = categorize_event(base_parsed_event)
        assert result == EVENT_UNKNOWN

    def test_successful_pod_with_no_issues_not_unknown(self, base_parsed_event):
        """Successful pod with restartCount=0 is not unknown."""
        base_parsed_event.update({
            'event_type': 'pod_status',
            'status': 'success',
            'metadata': {
                'source_fields': {
                    'ready': True,
                    'restartCount': 0
                }
            }
        })
        result = categorize_event(base_parsed_event)
        assert result != EVENT_UNKNOWN


# -----------------------------------------------------------------------------
# Tests for utility functions
# -----------------------------------------------------------------------------

class TestUtilityFunctions:
    """Tests for utility functions."""

    def test_get_event_type_display_name(self):
        """Display name mapping works for all event types."""
        assert get_event_type_display_name(EVENT_OOM) == 'Out of Memory'
        assert get_event_type_display_name(EVENT_POD_CRASH) == 'Pod Crash'
        assert get_event_type_display_name(EVENT_TIMEOUT) == 'Timeout'
        assert get_event_type_display_name(EVENT_UNKNOWN) == 'Unknown Event'
        assert get_event_type_display_name('invalid') == 'Unknown Event'

    def test_get_all_event_types(self):
        """All event types are returned."""
        event_types = get_all_event_types()
        assert EVENT_DEPLOYMENT_START in event_types
        assert EVENT_DEPLOYMENT_COMPLETE in event_types
        assert EVENT_POD_CRASH in event_types
        assert EVENT_OOM in event_types
        assert EVENT_READINESS_FAIL in event_types
        assert EVENT_TIMEOUT in event_types
        assert EVENT_IMAGE_PULL_ERROR in event_types
        assert EVENT_RESOURCE_LIMIT in event_types
        assert EVENT_PROBE_FAILURE in event_types
        assert EVENT_NETWORK_ERROR in event_types
        assert EVENT_UNKNOWN in event_types
        assert len(event_types) == 11


# -----------------------------------------------------------------------------
# Tests for batch categorization
# -----------------------------------------------------------------------------

class TestBatchCategorization:
    """Tests for categorize_events_batch() function."""

    def test_batch_categorization_groups_events(self, base_parsed_event):
        """Events are grouped by type correctly."""
        events = [
            # OOM event
            {**base_parsed_event, 'error_code': 'OOMKilled', 'metadata': {'source_fields': {}}},
            # Pod crash
            {**base_parsed_event, 'event_type': 'pod_status', 'status': 'failure', 'metadata': {'source_fields': {'status': 'Failed'}}},
            # Unknown event
            {**base_parsed_event, 'event_type': 'random', 'status': 'unknown', 'metadata': {'source_fields': {}}}
        ]

        result = categorize_events_batch(events)

        assert len(result[EVENT_OOM]) == 1
        assert len(result[EVENT_POD_CRASH]) == 1
        assert len(result[EVENT_UNKNOWN]) == 1
        assert sum(len(events) for events in result.values()) == 3

    def test_empty_batch_returns_empty_lists(self):
        """Empty batch returns lists with zero counts."""
        result = categorize_events_batch([])
        for event_type in get_all_event_types():
            assert result[event_type] == []

    def test_mixed_real_world_batch(self, base_parsed_event):
        """Real-world mixed event batch."""
        events = [
            # Deployment start
            {**base_parsed_event, 'event_type': 'deployment_feature_addition', 'status': 'success'},
            # Deployment complete
            {**base_parsed_event, 'event_type': 'replicaset_status', 'status': 'success', 'metadata': {'source_fields': {'replicas': 3, 'readyReplicas': 3}}},
            # OOM kill
            {**base_parsed_event, 'error_code': 'OOMKilled', 'metadata': {'source_fields': {}}},
            # Pod crash
            {**base_parsed_event, 'event_type': 'pod_status', 'status': 'failure', 'metadata': {'source_fields': {'status': 'CrashLoopBackOff'}}},
            # Readiness failure
            {**base_parsed_event, 'error_code': 'ReadinessFailed', 'metadata': {'source_fields': {}}},
            # Timeout
            {**base_parsed_event, 'error_code': 'ConnectionTimeout', 'metadata': {'source_fields': {}}},
            # Image pull error
            {**base_parsed_event, 'error_code': 'ErrImagePull', 'metadata': {'source_fields': {}}},
            # Resource limit
            {**base_parsed_event, 'error_code': 'FailedScheduling', 'metadata': {'source_fields': {'reason': 'FailedScheduling', 'message': 'Insufficient cpu'}}},
            # Probe failure
            {**base_parsed_event, 'error_code': 'Unhealthy', 'metadata': {'source_fields': {'reason': 'Unhealthy'}}},
            # Network error
            {**base_parsed_event, 'error_code': 'NetworkError', 'metadata': {'source_fields': {}}},
        ]

        result = categorize_events_batch(events)

        assert len(result[EVENT_DEPLOYMENT_START]) == 1
        assert len(result[EVENT_DEPLOYMENT_COMPLETE]) == 1
        assert len(result[EVENT_OOM]) == 1
        assert len(result[EVENT_POD_CRASH]) == 1
        assert len(result[EVENT_READINESS_FAIL]) == 1
        assert len(result[EVENT_TIMEOUT]) == 1
        assert len(result[EVENT_IMAGE_PULL_ERROR]) == 1
        assert len(result[EVENT_RESOURCE_LIMIT]) == 1
        assert len(result[EVENT_PROBE_FAILURE]) == 1
        assert len(result[EVENT_NETWORK_ERROR]) == 1


# -----------------------------------------------------------------------------
# Integration tests with real log samples
# -----------------------------------------------------------------------------

class TestRealLogSamples:
    """Integration tests with real Kubernetes log samples."""

    def test_real_kubernetes_oom_event(self):
        """Real Kubernetes OOM event from production logs."""
        event = {
            'timestamp': '2026-08-06T14:23:45Z',
            'service': 'whisper-stt',
            'event_type': 'event_oomkilled',
            'status': 'warning',
            'error_code': 'OOMKilled',
            'duration_ms': None,
            'cluster': 'ardenone-cluster',
            'namespace': 'whisper-stt',
            'metadata': {
                'source_fields': {
                    'type': 'Warning',
                    'reason': 'OOMKilled',
                    'object': 'pod/whisper-stt-abc123-def456',
                    'message': 'Container was killed because it used more memory than its limit.',
                    'firstTimestamp': '2026-08-06T14:23:45Z',
                    'lastTimestamp': '2026-08-06T14:23:45Z'
                },
                'raw_format': 'event'
            }
        }
        result = categorize_event(event)
        assert result == EVENT_OOM

    def test_real_pod_crashloopbackoff(self):
        """Real pod in CrashLoopBackOff from production logs."""
        event = {
            'timestamp': '2026-08-06T15:10:30Z',
            'service': 'pbx-web',
            'event_type': 'pod_status',
            'status': 'failure',
            'error_code': 'crashloopbackoff',
            'duration_ms': 3600000,
            'cluster': 'ardenone-cluster',
            'namespace': 'pbx-web',
            'metadata': {
                'source_fields': {
                    'name': 'pbx-web-7d9f8c5b4-xyz123',
                    'status': 'CrashLoopBackOff',
                    'ready': False,
                    'restartCount': 7,
                    'nodeName': 'node-2',
                    'podIP': '10.244.2.45'
                },
                'raw_format': 'pod'
            }
        }
        result = categorize_event(event)
        assert result == EVENT_POD_CRASH

    def test_real_deployment_success(self):
        """Real successful deployment from production logs."""
        event = {
            'timestamp': '2026-08-06T12:00:00Z',
            'service': 'pbx-web',
            'event_type': 'replicaset_status',
            'status': 'success',
            'error_code': None,
            'duration_ms': 180000,
            'cluster': 'ardenone-cluster',
            'namespace': 'pbx-web',
            'metadata': {
                'source_fields': {
                    'name': 'pbx-web-7d9f8c5b4',
                    'replicas': 3,
                    'readyReplicas': 3,
                    'observedGeneration': 10
                },
                'raw_format': 'replicaset'
            }
        }
        result = categorize_event(event)
        assert result == EVENT_DEPLOYMENT_COMPLETE

    def test_real_image_pull_backoff(self):
        """Real image pull backoff from production logs."""
        event = {
            'timestamp': '2026-08-06T16:45:20Z',
            'service': 'test-service',
            'event_type': 'event_imagepullbackoff',
            'status': 'warning',
            'error_code': 'ImagePullBackOff',
            'duration_ms': None,
            'cluster': 'ardenone-cluster',
            'namespace': 'default',
            'metadata': {
                'source_fields': {
                    'type': 'Warning',
                    'reason': 'ImagePullBackOff',
                    'object': 'pod/test-pod-abc123',
                    'message': 'Back-off pulling image "myapp:v1.0.0": rpc error: code = Unknown desc = Error response from daemon: pull access denied',
                    'firstTimestamp': '2026-08-06T16:45:20Z'
                },
                'raw_format': 'event'
            }
        }
        result = categorize_event(event)
        assert result == EVENT_IMAGE_PULL_ERROR
