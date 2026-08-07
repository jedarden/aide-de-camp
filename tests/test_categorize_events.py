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

    def test_deployment_creation_event(self, base_parsed_event):
        """Deployment creation with status='created' is deployment_start."""
        base_parsed_event.update({
            'event_type': 'deployment_created',
            'status': 'created'
        })
        result = categorize_event(base_parsed_event)
        assert result == EVENT_DEPLOYMENT_START

    def test_deployment_create_in_event_type(self, base_parsed_event):
        """Event type containing 'deployment' and 'create' is deployment_start."""
        base_parsed_event.update({
            'event_type': 'deployment_create_new',
            'status': 'success'
        })
        result = categorize_event(base_parsed_event)
        assert result == EVENT_DEPLOYMENT_START

    def test_replicaset_creation_initial(self, base_parsed_event):
        """ReplicaSet creation with 'initial' in event_type is deployment_start."""
        base_parsed_event.update({
            'event_type': 'replicaset_initial',
            'status': 'success'
        })
        result = categorize_event(base_parsed_event)
        assert result == EVENT_DEPLOYMENT_START

    def test_replicaset_creation_with_created_status(self, base_parsed_event):
        """ReplicaSet with status='created' is deployment_start."""
        base_parsed_event.update({
            'event_type': 'replicaset_created',
            'status': 'created'
        })
        result = categorize_event(base_parsed_event)
        assert result == EVENT_DEPLOYMENT_START

    def test_deployment_starting_event(self, base_parsed_event):
        """Deployment with 'starting' in event_type is deployment_start."""
        base_parsed_event.update({
            'event_type': 'deployment_starting',
            'status': 'success'
        })
        result = categorize_event(base_parsed_event)
        assert result == EVENT_DEPLOYMENT_START

    def test_replicaset_new_generation(self, base_parsed_event):
        """ReplicaSet with 'generation' in event_type is deployment_start."""
        base_parsed_event.update({
            'event_type': 'replicaset_generation_new',
            'status': 'success'
        })
        result = categorize_event(base_parsed_event)
        assert result == EVENT_DEPLOYMENT_START

    def test_event_created_kubernetes(self, base_parsed_event):
        """Kubernetes event_created is deployment_start."""
        base_parsed_event.update({
            'event_type': 'event_created',
            'status': 'success',
            'metadata': {
                'source_fields': {
                    'type': 'Normal',
                    'reason': 'Created',
                    'message': 'Created new deployment'
                }
            }
        })
        result = categorize_event(base_parsed_event)
        assert result == EVENT_DEPLOYMENT_START

    def test_event_creating_kubernetes(self, base_parsed_event):
        """Kubernetes event_creating is deployment_start."""
        base_parsed_event.update({
            'event_type': 'event_creating',
            'status': 'success'
        })
        result = categorize_event(base_parsed_event)
        assert result == EVENT_DEPLOYMENT_START


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

    @pytest.mark.parametrize("event_config,expected_description", [
        # Basic uncategorizable events
        ({
            'event_type': 'random_event',
            'status': 'unknown',
            'error_code': None,
            'metadata': {'source_fields': {'random_field': 'random_value'}}
        }, "Random event with no categorizable features"),

        # Events with completely nonsense event types
        ({
            'event_type': 'foobar_baz_event',
            'status': 'success',
            'error_code': None,
            'metadata': {'source_fields': {'some_field': 'some_value'}}
        }, "Event with nonsense event_type"),

        # Events with custom metrics
        ({
            'event_type': 'custom_metric_event',
            'status': 'info',
            'error_code': None,
            'metadata': {'source_fields': {'metric_name': 'custom_latency', 'metric_value': 123.45}}
        }, "Custom metric event"),

        # Events with unrecognized error codes
        ({
            'event_type': 'pod_status',
            'status': 'warning',
            'error_code': 'CustomAppError',
            'metadata': {'source_fields': {'message': 'Custom application error occurred'}}
        }, "Event with unrecognized error code"),

        # Scaling events (benign, not error-related)
        ({
            'event_type': 'scaling_event',
            'status': 'info',
            'error_code': None,
            'metadata': {'source_fields': {'scaling_action': 'horizontal_pod_autoscaler', 'replicas': 5}}
        }, "Horizontal autoscaler scaling event"),

        # Config update events
        ({
            'event_type': 'config_update',
            'status': 'completed',
            'error_code': None,
            'duration_ms': 5000,
            'metadata': {'source_fields': {'configmap': 'app-config', 'version': 'v1.2.3'}}
        }, "ConfigMap update completion event"),

        # Audit/log events
        ({
            'event_type': 'audit_log_entry',
            'status': 'logged',
            'error_code': None,
            'metadata': {'source_fields': {'audit_id': 'abc123', 'user': 'system', 'action': 'config_read'}}
        }, "Audit log entry event"),

        # Volume/mount events
        ({
            'event_type': 'volume_mount_event',
            'status': 'success',
            'error_code': None,
            'metadata': {'source_fields': {'volume_name': 'data-volume', 'mount_path': '/app/data'}}
        }, "Volume mount success event"),

        # Security/auth events
        ({
            'event_type': 'auth_event',
            'status': 'allowed',
            'error_code': None,
            'metadata': {'source_fields': {'user': 'service-account', 'operation': 'create', 'resource': 'pod'}}
        }, "Authorization allowed event"),

        # Generic status update events
        ({
            'event_type': 'status_update',
            'status': 'pending',
            'error_code': None,
            'metadata': {'source_fields': {'previous_status': 'initializing', 'current_status': 'pending'}}
        }, "Generic status update event"),

        # Long-running tasks below timeout threshold
        ({
            'event_type': 'long_running_task',
            'status': 'completed',
            'error_code': None,
            'duration_ms': 300000,
            'metadata': {'source_fields': {'task': 'data_processing', 'records_processed': 1000}}
        }, "Long-running task below timeout threshold"),
    ])
    def test_parametrized_unknown_events(self, base_parsed_event, event_config, expected_description):
        """Parametrized test for various unknown event patterns.

        Each event configuration represents a realistic event that should
        not match any known categorization pattern and should be categorized
        as EVENT_UNKNOWN.
        """
        base_parsed_event.update(event_config)
        result = categorize_event(base_parsed_event)

        # Assert the event is categorized as unknown
        assert result == EVENT_UNKNOWN, f"Failed for: {expected_description}"

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

    def test_event_with_nonsense_event_type_is_unknown(self, base_parsed_event):
        """Event with completely nonsense event_type is unknown."""
        base_parsed_event.update({
            'event_type': 'foobar_baz_event',
            'status': 'success',
            'error_code': None,
            'metadata': {
                'source_fields': {
                    'some_field': 'some_value'
                }
            }
        })
        result = categorize_event(base_parsed_event)
        assert result == EVENT_UNKNOWN

    def test_event_with_valid_structure_no_indicators_is_unknown(self, base_parsed_event):
        """Event with valid structure but no recognizable indicators is unknown."""
        base_parsed_event.update({
            'event_type': 'custom_metric_event',
            'status': 'info',
            'error_code': None,
            'metadata': {
                'source_fields': {
                    'metric_name': 'custom_latency',
                    'metric_value': 123.45
                }
            }
        })
        result = categorize_event(base_parsed_event)
        assert result == EVENT_UNKNOWN

    def test_event_with_custom_error_code_not_recognized_is_unknown(self, base_parsed_event):
        """Event with unrecognized error code is unknown."""
        base_parsed_event.update({
            'event_type': 'pod_status',
            'status': 'warning',
            'error_code': 'CustomAppError',
            'metadata': {
                'source_fields': {
                    'message': 'Custom application error occurred'
                }
            }
        })
        result = categorize_event(base_parsed_event)
        assert result == EVENT_UNKNOWN

    def test_event_with_benign_status_no_error_indicators_is_unknown(self, base_parsed_event):
        """Event with benign status and no error indicators is unknown."""
        base_parsed_event.update({
            'event_type': 'scaling_event',
            'status': 'info',
            'error_code': None,
            'metadata': {
                'source_fields': {
                    'scaling_action': 'horizontal_pod_autoscaler',
                    'replicas': 5
                }
            }
        })
        result = categorize_event(base_parsed_event)
        assert result == EVENT_UNKNOWN

    def test_event_with_mixed_fields_no_pattern_match_is_unknown(self, base_parsed_event):
        """Event with mixed fields that don't form a recognized pattern is unknown."""
        base_parsed_event.update({
            'event_type': 'config_update',
            'status': 'completed',
            'error_code': None,
            'duration_ms': 5000,
            'metadata': {
                'source_fields': {
                    'configmap': 'app-config',
                    'version': 'v1.2.3'
                }
            }
        })
        result = categorize_event(base_parsed_event)
        assert result == EVENT_UNKNOWN

    def test_audit_event_with_no_deployment_indicators_is_unknown(self, base_parsed_event):
        """Audit/logging event with no deployment indicators is unknown."""
        base_parsed_event.update({
            'event_type': 'audit_log_entry',
            'status': 'logged',
            'error_code': None,
            'metadata': {
                'source_fields': {
                    'audit_id': 'abc123',
                    'user': 'system',
                    'action': 'config_read'
                }
            }
        })
        result = categorize_event(base_parsed_event)
        assert result == EVENT_UNKNOWN

    @pytest.mark.parametrize("field_modifications,expected_description", [
        # Missing critical fields
        ({
            'event_type': None,
            'status': None,
            'error_code': None,
            'metadata': {'source_fields': {}}
        }, "All key fields are None"),

        # Empty critical fields
        ({
            'event_type': '',
            'status': '',
            'error_code': '',
            'metadata': {'source_fields': {'message': '', 'reason': ''}}
        }, "All key fields are empty strings"),

        # Missing metadata entirely
        ({
            'event_type': 'some_event',
            'status': 'success',
            'error_code': None,
            'metadata': None
        }, "Missing metadata field entirely"),

        # Missing source_fields
        ({
            'event_type': 'pod_status',
            'status': 'warning',
            'error_code': None,
            'metadata': {'source_fields': None}
        }, "Missing source_fields in metadata"),

        # Invalid data types for fields
        ({
            'event_type': 12345,  # Should be string
            'status': [],      # Should be string
            'error_code': {},  # Should be string or None
            'metadata': {'source_fields': 'invalid'}  # Should be dict
        }, "Invalid data types for all fields"),

        # Mixed None and invalid types
        ({
            'event_type': None,
            'status': 'invalid_status_type',
            'error_code': None,
            'metadata': {'source_fields': {'nested': 'invalid_value'}}  # String instead of None
        }, "Mixed None values and invalid types"),

        # Missing required timestamp field (implicitly tested via base fixture)
        ({
            'timestamp': None,
            'service': None,
            'event_type': 'test',
            'status': 'test',
            'error_code': None,
            'cluster': None,
            'namespace': None,
            'metadata': {'source_fields': {}}
        }, "Missing identifying fields (timestamp, service, cluster)"),

        # Extremely long event_type that doesn't match patterns
        ({
            'event_type': 'a' * 1000,  # Unrealistically long
            'status': 'success',
            'error_code': None,
            'metadata': {'source_fields': {}}
        }, "Unrealistically long event_type"),

        # Unicode/special characters in event_type
        ({
            'event_type': '🚀🌟💥',  # Emoji-only event type
            'status': 'success',
            'error_code': None,
            'metadata': {'source_fields': {}}
        }, "Unicode emoji event_type"),

        # Numeric string where string expected
        ({
            'event_type': '12345',
            'status': '67890',
            'error_code': '99999',
            'metadata': {'source_fields': {'exitCode': 'not_a_number'}}
        }, "Numeric strings where text expected"),

        # Boolean as string (should be actual boolean)
        ({
            'event_type': 'custom_event',
            'status': 'info',
            'error_code': None,
            'metadata': {'source_fields': {'ready': 'true', 'restartCount': 'false'}}
        }, "Boolean values as strings"),

        # Negative numeric values where inappropriate
        ({
            'event_type': 'custom_metric',
            'status': 'warning',
            'error_code': None,
            'duration_ms': -5000,  # Invalid negative duration
            'metadata': {'source_fields': {'restartCount': -1}}
        }, "Negative numeric values"),

        # Future timestamp (unrealistic)
        ({
            'timestamp': '2099-12-31T23:59:59Z',
            'event_type': 'future_event',
            'status': 'pending',
            'error_code': None,
            'metadata': {'source_fields': {}}
        }, "Future timestamp event"),
    ])
    def test_parametrized_invalid_and_missing_fields(self, base_parsed_event, field_modifications, expected_description):
        """Parametrized test for events with missing or invalid field values.

        Tests edge cases where events have:
        - None values in critical fields
        - Empty strings
        - Invalid data types
        - Missing nested structures
        - Unrealistic values

        All should be categorized as EVENT_UNKNOWN after validation fails.
        """
        # Clear the base fixture and apply modifications
        base_parsed_event.clear()
        base_parsed_event.update(field_modifications)
        base_parsed_event.setdefault('timestamp', '2026-08-06T12:00:00Z')
        base_parsed_event.setdefault('service', 'test-service')
        base_parsed_event.setdefault('cluster', 'test-cluster')
        base_parsed_event.setdefault('namespace', 'test-ns')
        base_parsed_event.setdefault('duration_ms', None)

        result = categorize_event(base_parsed_event)

        # Assert the event is categorized as unknown due to invalid/missing fields
        assert result == EVENT_UNKNOWN, f"Failed for: {expected_description}"

    def test_unknown_event_with_none_values_is_unknown(self, base_parsed_event):
        """Event with None values in key fields is unknown."""
        base_parsed_event.update({
            'event_type': None,
            'status': None,
            'error_code': None,
            'metadata': {
                'source_fields': {}
            }
        })
        result = categorize_event(base_parsed_event)
        assert result == EVENT_UNKNOWN

    def test_unknown_event_with_empty_strings_is_unknown(self, base_parsed_event):
        """Event with empty strings in key fields is unknown."""
        base_parsed_event.update({
            'event_type': '',
            'status': '',
            'error_code': '',
            'metadata': {
                'source_fields': {
                    'message': '',
                    'reason': ''
                }
            }
        })
        result = categorize_event(base_parsed_event)
        assert result == EVENT_UNKNOWN

    def test_event_similar_to_timeout_but_below_threshold_is_unknown(self, base_parsed_event):
        """Event with duration below timeout threshold and no timeout indicators is unknown."""
        base_parsed_event.update({
            'event_type': 'long_running_task',
            'status': 'completed',
            'error_code': None,
            'duration_ms': 300000,  # 5 minutes - below 10 minute threshold
            'metadata': {
                'source_fields': {
                    'task': 'data_processing',
                    'records_processed': 1000
                }
            }
        })
        result = categorize_event(base_parsed_event)
        assert result == EVENT_UNKNOWN

    def test_event_with_generic_status_no_error_patterns_is_unknown(self, base_parsed_event):
        """Event with generic status field but no error patterns is unknown."""
        base_parsed_event.update({
            'event_type': 'status_update',
            'status': 'pending',
            'error_code': None,
            'metadata': {
                'source_fields': {
                    'previous_status': 'initializing',
                    'current_status': 'pending'
                }
            }
        })
        result = categorize_event(base_parsed_event)
        assert result == EVENT_UNKNOWN

    def test_volume_mount_event_with_no_deployment_indicators_is_unknown(self, base_parsed_event):
        """Volume/mount event with no deployment indicators is unknown."""
        base_parsed_event.update({
            'event_type': 'volume_mount_event',
            'status': 'success',
            'error_code': None,
            'metadata': {
                'source_fields': {
                    'volume_name': 'data-volume',
                    'mount_path': '/app/data'
                }
            }
        })
        result = categorize_event(base_parsed_event)
        assert result == EVENT_UNKNOWN

    def test_security_event_with_no_deployment_indicators_is_unknown(self, base_parsed_event):
        """Security/auth event with no deployment indicators is unknown."""
        base_parsed_event.update({
            'event_type': 'auth_event',
            'status': 'allowed',
            'error_code': None,
            'metadata': {
                'source_fields': {
                    'user': 'service-account',
                    'operation': 'create',
                    'resource': 'pod'
                }
            }
        })
        result = categorize_event(base_parsed_event)
        assert result == EVENT_UNKNOWN


# -----------------------------------------------------------------------------
# Tests for fallback trigger mechanism
# -----------------------------------------------------------------------------

class TestFallbackTriggerMechanism:
    """
    Tests to verify the fallback mechanism is ONLY triggered when no patterns match.

    These tests use mocking to verify that:
    1. Fallback is called when all pattern matching functions return None/False
    2. Fallback is NOT called when at least one pattern matches
    3. The fallback receives the original event unchanged
    4. Edge cases where patterns exist but don't match
    """

    def test_fallback_triggered_when_all_patterns_return_none(self, base_parsed_event):
        """
        Test that fallback (EVENT_UNKNOWN) is triggered when all pattern matching
        functions return None/False.

        This verifies the fundamental fallback behavior: when no patterns match,
        the system falls back to EVENT_UNKNOWN.
        """
        # Create an event that should not match any known pattern
        base_parsed_event.update({
            'event_type': 'completely_unknown_event_type',
            'status': 'unknown_status',
            'error_code': None,
            'metadata': {
                'source_fields': {
                    'random_field': 'random_value'
                }
            }
        })

        result = categorize_event(base_parsed_event)

        # Assert that the fallback was triggered
        assert result == EVENT_UNKNOWN

    def test_fallback_not_triggered_when_oom_pattern_matches(self, base_parsed_event):
        """
        Test that fallback is NOT triggered when OOM pattern matches.

        Even with obscure other fields, if OOM pattern matches, it should
        return EVENT_OOM, not fall back to EVENT_UNKNOWN.
        """
        base_parsed_event.update({
            'event_type': 'obscure_event_name',
            'status': 'obscure_status',
            'error_code': 'OOMKilled',  # This should match OOM pattern
            'metadata': {
                'source_fields': {
                    'obscure_field': 'obscure_value'
                }
            }
        })

        result = categorize_event(base_parsed_event)

        # Assert OOM pattern matched, fallback NOT triggered
        assert result == EVENT_OOM
        assert result != EVENT_UNKNOWN

    def test_fallback_not_triggered_when_pod_crash_pattern_matches(self, base_parsed_event):
        """
        Test that fallback is NOT triggered when pod crash pattern matches.

        Even with unusual event_type, if pod crash pattern matches, it should
        return EVENT_POD_CRASH, not fall back to EVENT_UNKNOWN.
        """
        base_parsed_event.update({
            'event_type': 'weird_custom_event',
            'status': 'failure',
            'error_code': 'crashloopbackoff',  # This should match pod crash pattern
            'metadata': {
                'source_fields': {
                    'weird_field': 'weird_value'
                }
            }
        })

        result = categorize_event(base_parsed_event)

        # Assert pod crash pattern matched, fallback NOT triggered
        assert result == EVENT_POD_CRASH
        assert result != EVENT_UNKNOWN

    def test_fallback_preserves_original_event_unchanged(self, base_parsed_event):
        """
        Test that the fallback mechanism does not modify the original event.

        The original event should remain unchanged after categorization,
        even when falling back to EVENT_UNKNOWN.
        """
        # Create a copy of the original event for comparison
        original_event = base_parsed_event.copy()
        original_event.update({
            'event_type': 'unknown_event_xyz',
            'status': 'unknown_status',
            'error_code': None,
            'metadata': {
                'source_fields': {
                    'field1': 'value1',
                    'field2': 'value2'
                }
            }
        })
        base_parsed_event.update(original_event)

        # Categorize the event (should trigger fallback)
        result = categorize_event(base_parsed_event)

        # Verify fallback was triggered
        assert result == EVENT_UNKNOWN

        # Verify event was not modified
        assert base_parsed_event['event_type'] == original_event['event_type']
        assert base_parsed_event['status'] == original_event['status']
        assert base_parsed_event['error_code'] == original_event['error_code']
        assert base_parsed_event['metadata']['source_fields']['field1'] == 'value1'
        assert base_parsed_event['metadata']['source_fields']['field2'] == 'value2'

    def test_fallback_with_event_that_has_partial_pattern_matches(self, base_parsed_event):
        """
        Test edge case where event has some pattern-like fields but doesn't
        fully match any specific pattern.

        For example, an event with 'timeout' in message but below the duration
        threshold should still fall back to UNKNOWN.
        """
        base_parsed_event.update({
            'event_type': 'custom_task_event',
            'status': 'completed',
            'error_code': None,
            'duration_ms': 50000,  # Below timeout threshold (600000ms)
            'metadata': {
                'source_fields': {
                    'message': 'Task completed in reasonable time',  # Has 'timeout' word but not actually a timeout
                    'task_name': 'data_processing'
                }
            }
        })

        result = categorize_event(base_parsed_event)

        # Should fall back to UNKNOWN despite having timeout-like language
        assert result == EVENT_UNKNOWN

    def test_fallback_with_minimal_valid_event_structure(self, base_parsed_event):
        """
        Test fallback with minimal but valid event structure.

        Even with minimal fields, if no patterns match, should fallback to UNKNOWN.
        """
        # Minimal event that passes validation but matches no patterns
        minimal_event = {
            'timestamp': '2026-08-06T12:00:00Z',
            'event_type': 'minimal_event',
            'status': 'info',
            'error_code': None,
            'metadata': {'source_fields': {}}
        }

        result = categorize_event(minimal_event)

        # Should fallback to UNKNOWN
        assert result == EVENT_UNKNOWN

    def test_no_fallback_when_deployment_start_pattern_matches(self, base_parsed_event):
        """
        Test that fallback is NOT triggered for deployment start events.

        Even with minimal deployment indicators, if deployment start pattern
        matches, it should NOT fall back to UNKNOWN.
        """
        base_parsed_event.update({
            'event_type': 'deployment_initial_deployment',  # Clear deployment start indicator
            'status': 'success',
            'error_code': None,
            'metadata': {
                'source_fields': {
                    'deployment': 'my-app'
                }
            }
        })

        result = categorize_event(base_parsed_event)

        # Should match deployment start, NOT fallback
        assert result == EVENT_DEPLOYMENT_START
        assert result != EVENT_UNKNOWN

    def test_no_fallback_when_deployment_complete_pattern_matches(self, base_parsed_event):
        """
        Test that fallback is NOT triggered for deployment complete events.

        Even with unusual fields, if deployment complete pattern matches,
        it should NOT fall back to UNKNOWN.
        """
        base_parsed_event.update({
            'event_type': 'replicaset_status',  # ReplicaSet status
            'status': 'success',
            'error_code': None,
            'metadata': {
                'source_fields': {
                    'replicas': 3,
                    'readyReplicas': 3,  # All replicas ready
                    'unusual_field': 'unusual_value'
                }
            }
        })

        result = categorize_event(base_parsed_event)

        # Should match deployment complete, NOT fallback
        assert result == EVENT_DEPLOYMENT_COMPLETE
        assert result != EVENT_UNKNOWN

    @pytest.mark.parametrize("event_config,expected_not_unknown,description", [
        # Events that should match specific patterns and NOT fallback to UNKNOWN
        ({
            'error_code': 'OOMKilled',
            'metadata': {'source_fields': {}}
        }, EVENT_OOM, "OOM pattern should match, not fallback"),

        ({
            'event_type': 'pod_status',
            'status': 'failure',
            'error_code': 'crashloopbackoff',
            'metadata': {'source_fields': {}}
        }, EVENT_POD_CRASH, "Pod crash pattern should match, not fallback"),

        ({
            'event_type': 'deployment_created',
            'status': 'created',
            'error_code': None,
            'metadata': {'source_fields': {}}
        }, EVENT_DEPLOYMENT_START, "Deployment start pattern should match, not fallback"),

        ({
            'error_code': 'ErrImagePull',
            'metadata': {'source_fields': {}}
        }, EVENT_IMAGE_PULL_ERROR, "Image pull error pattern should match, not fallback"),

        ({
            'error_code': 'ConnectionTimeout',
            'metadata': {'source_fields': {}}
        }, EVENT_TIMEOUT, "Timeout pattern should match, not fallback"),

        ({
            'error_code': 'NetworkError',
            'metadata': {'source_fields': {}}
        }, EVENT_NETWORK_ERROR, "Network error pattern should match, not fallback"),

        ({
            'error_code': 'LivenessProbeFailed',
            'metadata': {'source_fields': {}}
        }, EVENT_PROBE_FAILURE, "Probe failure pattern should match, not fallback"),

        ({
            'error_code': 'ReadinessFailed',
            'metadata': {'source_fields': {}}
        }, EVENT_READINESS_FAIL, "Readiness failure pattern should match, not fallback"),

        ({
            'error_code': 'FailedScheduling',
            'metadata': {'source_fields': {'reason': 'FailedScheduling', 'message': 'Insufficient cpu'}}
        }, EVENT_RESOURCE_LIMIT, "Resource limit pattern should match, not fallback"),
    ])
    def test_patterns_match_before_fallback(self, base_parsed_event, event_config, expected_not_unknown, description):
        """
        Parametrized test verifying that known patterns match and prevent fallback.

        Each event configuration represents a known pattern that should match
        and return its specific event type, NOT fall back to EVENT_UNKNOWN.
        """
        base_parsed_event.update(event_config)
        result = categorize_event(base_parsed_event)

        # Assert the specific pattern matched, NOT the fallback
        assert result == expected_not_unknown, f"{description} - got {result} instead"
        assert result != EVENT_UNKNOWN, f"{description} - should not fallback to UNKNOWN"

    @pytest.mark.parametrize("event_config,description", [
        # Events that should NOT match any pattern and SHOULD fallback to UNKNOWN
        ({
            'event_type': 'custom_app_metric',
            'status': 'info',
            'error_code': None,
            'metadata': {'source_fields': {'metric_name': 'custom_latency', 'metric_value': 123.45}}
        }, "Custom app metric event should fallback"),

        ({
            'event_type': 'scaling_event',
            'status': 'info',
            'error_code': None,
            'metadata': {'source_fields': {'scaling_action': 'horizontal_pod_autoscaler', 'replicas': 5}}
        }, "Autoscaler scaling event should fallback"),

        ({
            'event_type': 'config_update',
            'status': 'completed',
            'error_code': None,
            'metadata': {'source_fields': {'configmap': 'app-config', 'version': 'v1.2.3'}}
        }, "ConfigMap update event should fallback"),

        ({
            'event_type': 'volume_mount',
            'status': 'success',
            'error_code': None,
            'metadata': {'source_fields': {'volume_name': 'data-volume', 'mount_path': '/app/data'}}
        }, "Volume mount event should fallback"),

        ({
            'event_type': 'auth_event',
            'status': 'allowed',
            'error_code': None,
            'metadata': {'source_fields': {'user': 'service-account', 'operation': 'create'}}
        }, "Authorization event should fallback"),

        ({
            'event_type': 'audit_log',
            'status': 'logged',
            'error_code': None,
            'metadata': {'source_fields': {'audit_id': 'abc123', 'user': 'system', 'action': 'config_read'}}
        }, "Audit log event should fallback"),

        ({
            'event_type': 'backup_complete',
            'status': 'success',
            'error_code': None,
            'metadata': {'source_fields': {'backup_type': 'snapshot', 'size_gb': 10}}
        }, "Backup completion event should fallback"),

        ({
            'event_type': 'model_training',
            'status': 'success',
            'error_code': None,
            'metadata': {'source_fields': {'model_name': 'predictor_v2', 'accuracy': 0.95}}
        }, "ML model training event should fallback"),
    ])
    def test_should_fallback_to_unknown(self, base_parsed_event, event_config, description):
        """
        Parametrized test verifying that events with no matching patterns
        correctly fall back to EVENT_UNKNOWN.

        Each event configuration represents a realistic event that does not
        match any known Kubernetes deployment or error pattern and should
        therefore fall back to EVENT_UNKNOWN.
        """
        base_parsed_event.update(event_config)
        result = categorize_event(base_parsed_event)

        # Assert the event fell back to UNKNOWN
        assert result == EVENT_UNKNOWN, f"{description} - got {result} instead"


# -----------------------------------------------------------------------------
# Tests for unexpected event types (already present, kept for continuity)
# -----------------------------------------------------------------------------

class TestUnexpectedEventTypes:
    """Parametrized tests for events with completely unexpected event types."""

    @pytest.mark.parametrize("unexpected_type_config,description", [
        # Completely novel event type names
        ({
            'event_type': 'quantum_entanglement_event',
            'status': 'success',
            'error_code': None,
            'metadata': {'source_fields': {'qubits': 42, 'entangled': True}}
        }, "Quantum computing event type"),

        # Events from other systems (non-Kubernetes)
        ({
            'event_type': 'aws_cloudwatch_alarm',
            'status': 'ALARM',
            'error_code': None,
            'metadata': {'source_fields': {'alarm_name': 'HighCPU', 'metric': 'CPUUtilization'}}
        }, "AWS CloudWatch alarm event"),

        # Database-specific events (non-Kubernetes)
        ({
            'event_type': 'postgresql_slow_query',
            'status': 'detected',
            'error_code': None,
            'metadata': {'source_fields': {'query_duration_ms': 5000, 'table': 'users'}}
        }, "PostgreSQL slow query event"),

        # Application-level events (non-infrastructure)
        ({
            'event_type': 'user_login_event',
            'status': 'success',
            'error_code': None,
            'metadata': {'source_fields': {'user_id': 'user123', 'method': 'OAuth'}}
        }, "User authentication event"),

        # CI/CD pipeline events
        ({
            'event_type': 'jenkins_build_complete',
            'status': 'SUCCESS',
            'error_code': None,
            'metadata': {'source_fields': {'build_number': 42, 'job_name': 'deploy'}}
        }, "Jenkins CI build event"),

        # Monitoring/alerting system events
        ({
            'event_type': 'prometheus_alert_fired',
            'status': 'firing',
            'error_code': None,
            'metadata': {'source_fields': {'alert_name': 'HighMemory', 'severity': 'warning'}}
        }, "Prometheus alerting event"),

        # Service mesh events (not core Kubernetes)
        ({
            'event_type': 'istio_circuit_breaker_open',
            'status': 'open',
            'error_code': None,
            'metadata': {'source_fields': {'service': 'api', 'consecutive_errors': 5}}
        }, "Istio circuit breaker event"),

        # Storage system events (non-Kubernetes)
        ({
            'event_type': 'nfs_mount_timeout',
            'status': 'timeout',
            'error_code': None,
            'metadata': {'source_fields': {'server': 'nfs.example.com', 'export': '/data'}}
        }, "NFS storage timeout event"),

        # Custom application domain events
        ({
            'event_type': 'payment_gateway_declined',
            'status': 'declined',
            'error_code': 'INSUFFICIENT_FUNDS',
            'metadata': {'source_fields': {'transaction_id': 'txn123', 'amount': 99.99}}
        }, "Payment processing event"),

        # Backup/disaster recovery events
        ({
            'event_type': 'backup_job_completed',
            'status': 'success',
            'error_code': None,
            'metadata': {'source_fields': {'backup_type': 'snapshot', 'size_gb': 10}}
        }, "Backup job completion event"),

        # Machine learning pipeline events
        ({
            'event_type': 'model_training_complete',
            'status': 'success',
            'error_code': None,
            'metadata': {'source_fields': {'model_name': 'predictor_v2', 'accuracy': 0.95}}
        }, "ML model training event"),

        # Security incident events
        ({
            'event_type': 'intrusion_detection_alert',
            'status': 'alert',
            'error_code': 'SUSPICIOUS_ACTIVITY',
            'metadata': {'source_fields': {'source_ip': '192.168.1.100', 'severity': 'high'}}
        }, "Security intrusion detection event"),

        # CDN/edge network events
        ({
            'event_type': 'cloudflare_cache_purge',
            'status': 'success',
            'error_code': None,
            'metadata': {'source_fields': {'zone_id': 'abc123', 'files_purged': 42}}
        }, "CDN cache purge event"),

        # Message queue events
        ({
            'event_type': 'rabbitmq_queue_empty',
            'status': 'warning',
            'error_code': None,
            'metadata': {'source_fields': {'queue_name': 'jobs', 'consumer_count': 0}}
        }, "Message queue event"),

        # Custom orchestration events
        ({
            'event_type': 'airflow_task_failure',
            'status': 'failed',
            'error_code': 'TaskFailed',
            'metadata': {'source_fields': {'dag_id': 'etl', 'task_id': 'extract', 'attempt': 3}}
        }, "Airflow workflow event"),

        # Legacy system events
        ({
            'event_type': 'mainframe_job_complete',
            'status': 'SUCCESS',
            'error_code': None,
            'metadata': {'source_fields': {'job_name': 'BATCH_PROCESS', 'return_code': 0}}
        }, "Mainframe batch job event"),

        # Internet of Things events
        ({
            'event_type': 'iot_sensor_reading',
            'status': 'measured',
            'error_code': None,
            'metadata': {'source_fields': {'device_id': 'sensor01', 'temperature_c': 25.5}}
        }, "IoT sensor reading event"),

        # Blockchain/cryptocurrency events
        ({
            'event_type': 'ethereum_transaction_mined',
            'status': 'confirmed',
            'error_code': None,
            'metadata': {'source_fields': {'tx_hash': '0xabc...', 'block_number': 12345}}
        }, "Blockchain transaction event"),
    ])
    def test_parametrized_unexpected_event_types(self, base_parsed_event, unexpected_type_config, description):
        """Parametrized test for events with completely unexpected event types.

        These events represent realistic scenarios from various systems
        (cloud providers, databases, CI/CD, monitoring, security, etc.) that
        don't match any Kubernetes deployment or pod event patterns.

        All should be categorized as EVENT_UNKNOWN despite having valid
        structure and realistic fields.
        """
        base_parsed_event.update(unexpected_type_config)
        result = categorize_event(base_parsed_event)

        # Assert the event is categorized as unknown
        assert result == EVENT_UNKNOWN, f"Failed for: {description}"


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


# -----------------------------------------------------------------------------
# Tests for unknown event fallback exclusivity
# -----------------------------------------------------------------------------

class TestUnknownEventFallbackExclusivity:
    """Tests to verify unknown fallback is ONLY triggered when no patterns match."""

    def test_oom_always_takes_precedence_over_unknown(self, base_parsed_event):
        """OOM pattern always matches, never falls back to unknown."""
        base_parsed_event.update({
            'event_type': 'obscure_event_name',
            'status': 'obscure_status',
            'error_code': 'OOMKilled',
            'metadata': {
                'source_fields': {
                    'obscure_field': 'obscure_value'
                }
            }
        })
        result = categorize_event(base_parsed_event)
        assert result == EVENT_OOM
        assert result != EVENT_UNKNOWN

    def test_pod_crash_always_takes_precedence_over_unknown(self, base_parsed_event):
        """Pod crash pattern always matches, never falls back to unknown."""
        base_parsed_event.update({
            'event_type': 'weird_event',
            'status': 'failure',
            'error_code': 'crashloopbackoff',
            'metadata': {
                'source_fields': {
                    'weird_field': 'weird_value'
                }
            }
        })
        result = categorize_event(base_parsed_event)
        assert result == EVENT_POD_CRASH
        assert result != EVENT_UNKNOWN

    def test_deployment_start_takes_precedence_over_unknown(self, base_parsed_event):
        """Deployment start pattern always matches, never falls back to unknown."""
        base_parsed_event.update({
            'event_type': 'deployment_initial_deployment',
            'status': 'success',
            'error_code': None,
            'metadata': {
                'source_fields': {
                    'random_field': 'random_value'
                }
            }
        })
        result = categorize_event(base_parsed_event)
        assert result == EVENT_DEPLOYMENT_START
        assert result != EVENT_UNKNOWN

    def test_deployment_complete_takes_precedence_over_unknown(self, base_parsed_event):
        """Deployment complete pattern always matches, never falls back to unknown."""
        base_parsed_event.update({
            'event_type': 'replicaset_status',
            'status': 'success',
            'error_code': None,
            'metadata': {
                'source_fields': {
                    'replicas': 3,
                    'readyReplicas': 3,
                    'unusual_field': 'unusual_value'
                }
            }
        })
        result = categorize_event(base_parsed_event)
        assert result == EVENT_DEPLOYMENT_COMPLETE
        assert result != EVENT_UNKNOWN

    def test_readiness_failure_takes_precedence_over_unknown(self, base_parsed_event):
        """Readiness failure pattern always matches, never falls back to unknown."""
        base_parsed_event.update({
            'event_type': 'random_event',
            'status': 'warning',
            'error_code': 'ReadinessFailed',
            'metadata': {
                'source_fields': {
                    'random_data': 'random_value'
                }
            }
        })
        result = categorize_event(base_parsed_event)
        assert result == EVENT_READINESS_FAIL
        assert result != EVENT_UNKNOWN

    def test_timeout_takes_precedence_over_unknown(self, base_parsed_event):
        """Timeout pattern always matches, never falls back to unknown."""
        base_parsed_event.update({
            'event_type': 'obscure_timeout',
            'status': 'warning',
            'error_code': 'ConnectionTimeout',
            'metadata': {
                'source_fields': {
                    'obscure_info': 'obscure_value'
                }
            }
        })
        result = categorize_event(base_parsed_event)
        assert result == EVENT_TIMEOUT
        assert result != EVENT_UNKNOWN

    def test_image_pull_error_takes_precedence_over_unknown(self, base_parsed_event):
        """Image pull error pattern always matches, never falls back to unknown."""
        base_parsed_event.update({
            'event_type': 'unknown_image_event',
            'status': 'warning',
            'error_code': 'ErrImagePull',
            'metadata': {
                'source_fields': {
                    'unknown_field': 'unknown_value'
                }
            }
        })
        result = categorize_event(base_parsed_event)
        assert result == EVENT_IMAGE_PULL_ERROR
        assert result != EVENT_UNKNOWN

    def test_resource_limit_takes_precedence_over_unknown(self, base_parsed_event):
        """Resource limit pattern always matches, never falls back to unknown."""
        base_parsed_event.update({
            'event_type': 'strange_resource_event',
            'status': 'warning',
            'error_code': 'FailedScheduling',
            'metadata': {
                'source_fields': {
                    'reason': 'FailedScheduling',
                    'message': 'Insufficient cpu',
                    'strange_field': 'strange_value'
                }
            }
        })
        result = categorize_event(base_parsed_event)
        assert result == EVENT_RESOURCE_LIMIT
        assert result != EVENT_UNKNOWN

    def test_probe_failure_takes_precedence_over_unknown(self, base_parsed_event):
        """Probe failure pattern always matches, never falls back to unknown."""
        base_parsed_event.update({
            'event_type': 'unusual_probe_event',
            'status': 'warning',
            'error_code': 'LivenessProbeFailed',
            'metadata': {
                'source_fields': {
                    'unusual_info': 'unusual_value'
                }
            }
        })
        result = categorize_event(base_parsed_event)
        assert result == EVENT_PROBE_FAILURE
        assert result != EVENT_UNKNOWN

    def test_network_error_takes_precedence_over_unknown(self, base_parsed_event):
        """Network error pattern always matches, never falls back to unknown."""
        base_parsed_event.update({
            'event_type': 'obscure_network_event',
            'status': 'warning',
            'error_code': 'NetworkError',
            'metadata': {
                'source_fields': {
                    'obscure_data': 'obscure_value'
                }
            }
        })
        result = categorize_event(base_parsed_event)
        assert result == EVENT_NETWORK_ERROR
        assert result != EVENT_UNKNOWN

    def test_unknown_only_when_no_error_indicators(self, base_parsed_event):
        """Unknown is only returned when there are truly no error indicators."""
        # This should match pod crash, not unknown
        base_parsed_event.update({
            'event_type': 'pod_status',
            'status': 'failure',
            'error_code': 'crashloopbackoff',
            'metadata': {
                'source_fields': {
                    'restartCount': 5
                }
            }
        })
        result = categorize_event(base_parsed_event)
        assert result == EVENT_POD_CRASH
        assert result != EVENT_UNKNOWN

    def test_unknown_only_when_no_deployment_indicators(self, base_parsed_event):
        """Unknown is only returned when there are truly no deployment indicators."""
        # This should match deployment start, not unknown
        base_parsed_event.update({
            'event_type': 'deployment_created',
            'status': 'created',
            'error_code': None,
            'metadata': {
                'source_fields': {
                    'deployment': 'my-app',
                    'namespace': 'production'
                }
            }
        })
        result = categorize_event(base_parsed_event)
        assert result == EVENT_DEPLOYMENT_START
        assert result != EVENT_UNKNOWN
