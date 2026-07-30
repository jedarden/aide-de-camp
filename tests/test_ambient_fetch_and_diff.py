"""
Tests for ambient.py fetch and diff logic with topic_context_cache integration.

Tests coverage:
- Fetch sources for watched topics using fetch-matrix
- Diff against topic_context_cache to detect state changes
- Track what changed for rule evaluation
- Cache persistence across checks
"""

import asyncio
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import aiosqlite
import pytest
import yaml

from src.monitoring.ambient import AmbientMonitor, MonitoringRule
from src.session.store import SessionStore


# --- Fixtures -----------------------------------------------------------------


@pytest.fixture
async def store():
    """In-memory session store for testing with cleanup."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)

    s = SessionStore(db_path)
    await s.initialize()

    yield s

    # Cleanup
    await s.close()
    db_path.unlink(missing_ok=True)


@pytest.fixture
def ambient_monitor(store):
    """Create an AmbientMonitor instance with test store."""
    return AmbientMonitor(session_store=store)


@pytest.fixture
def sample_monitoring_rule():
    """Create a sample monitoring rule for testing."""
    return MonitoringRule(
        topic_id="test-pipeline-status",
        project_slug="test-pipeline",
        intent_type="status",
        check_interval=60,
        urgency="normal",
        filters=["phase!=Running"],
        notification_threshold="any_change",
    )


# --- Tests ---------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fetch_sources_for_watched_topics(ambient_monitor):
    """Test that ambient monitor can fetch sources for watched topics using fetch command matrix."""
    from src.fetch.commands import FetchResult, FetchCoverage, SourceResult, FetchSource, IntentType

    # Create a rule without filters for simpler testing
    simple_rule = MonitoringRule(
        topic_id="test-pipeline-status",
        project_slug="test-pipeline",
        intent_type="status",
        check_interval=60,
        urgency="normal",
        filters=[],  # No filters for this test
        notification_threshold="any_change",
    )

    # Mock the execute_fetch function to return a complete fetch result
    mock_fetch_result = FetchResult(
        intent_id="monitoring-test-pipeline-status",
        intent_type=IntentType.STATUS,
        sources={
            FetchSource.KUBECTL_PODS: SourceResult(
                source=FetchSource.KUBECTL_PODS,
                status="success",
                data={
                    "namespace": "testpipeline",
                    "pods": [
                        {"name": "pod-1", "phase": "Failed", "ready": "0/1", "restarts": 5},
                    ],
                    "pod_count": 1,
                    "healthy_count": 0,
                },
                duration_ms=100,
            ),
        },
        coverage=FetchCoverage(
            total_sources=1,
            succeeded=[FetchSource.KUBECTL_PODS],
            timed_out=[],
            failed=[],
            skipped=[],
        ),
        total_duration_ms=100,
    )

    with patch("src.monitoring.ambient.execute_fetch", new=AsyncMock(return_value=mock_fetch_result)):
        state = await ambient_monitor.check_topic_state(simple_rule)

        assert state is not None
        assert state["project_slug"] == "test-pipeline"
        assert state["namespace"] == "testpipeline"
        assert state["pod_count"] == 1
        assert state["healthy_count"] == 0
        # Verify sources were tracked
        assert FetchSource.KUBECTL_PODS in state["sources"]


@pytest.mark.asyncio
async def test_diff_against_topic_context_cache(ambient_monitor, store, sample_monitoring_rule):
    """Test that ambient monitor diffs against topic_context_cache."""
    # First state
    initial_state = {
        "project_slug": "test-pipeline",
        "intent_type": "status",
        "phase": "Running",
        "restarts": 0,
    }

    # Set initial state in cache
    await ambient_monitor._update_topic_context_cache(
        sample_monitoring_rule.topic_id,
        initial_state,
    )

    # Verify cache was set
    cached = await ambient_monitor._get_topic_context_cache(sample_monitoring_rule.topic_id)
    assert cached is not None
    assert cached["phase"] == "Running"
    assert cached["restarts"] == 0

    # Second state with changes
    changed_state = {
        "project_slug": "test-pipeline",
        "intent_type": "status",
        "phase": "Failed",  # Changed
        "restarts": 5,  # Changed
    }

    # Detect change
    has_change, changes_dict = await ambient_monitor.detect_state_change(
        sample_monitoring_rule,
        changed_state,
    )

    assert has_change is True
    assert changes_dict["is_first"] is False
    assert "phase" in changes_dict.get("changed_fields", [])


@pytest.mark.asyncio
async def test_first_check_establishes_baseline(ambient_monitor, sample_monitoring_rule):
    """Test that first check establishes baseline and doesn't notify."""
    current_state = {
        "project_slug": "test-pipeline",
        "intent_type": "status",
        "phase": "Running",
        "restarts": 0,
    }

    # First check - should establish baseline and return False
    has_change, changes_dict = await ambient_monitor.detect_state_change(
        sample_monitoring_rule,
        current_state,
    )

    assert has_change is False, "First check should establish baseline, not notify"
    assert changes_dict["is_first"] is True

    # Verify state was cached
    cached = await ambient_monitor._get_topic_context_cache(sample_monitoring_rule.topic_id)
    assert cached is not None
    assert cached["phase"] == "Running"


@pytest.mark.asyncio
async def test_state_change_detection_any_change_threshold(ambient_monitor, sample_monitoring_rule):
    """Test state change detection with notification_threshold='any_change'."""
    # Set initial state
    initial_state = {"phase": "Running", "restarts": 0, "ready": "1/1"}
    await ambient_monitor._update_topic_context_cache(
        sample_monitoring_rule.topic_id,
        initial_state,
    )

    # Test with any_change threshold
    sample_monitoring_rule.notification_threshold = "any_change"

    # Same state - no change
    has_change, changes_dict = await ambient_monitor.detect_state_change(
        sample_monitoring_rule,
        initial_state,
    )
    assert has_change is False

    # Any field change - should trigger
    changed_state = {"phase": "Running", "restarts": 1, "ready": "1/1"}
    has_change, changes_dict = await ambient_monitor.detect_state_change(
        sample_monitoring_rule,
        changed_state,
    )
    assert has_change is True
    assert "restarts" in changes_dict.get("changed_fields", [])


@pytest.mark.asyncio
async def test_state_change_detection_state_change_threshold(ambient_monitor, sample_monitoring_rule):
    """Test state change detection with notification_threshold='state_change'."""
    # Set initial state
    initial_state = {
        "phase": "Running",
        "status": "Healthy",
        "restarts": 0,
        "other_field": "value",
    }
    await ambient_monitor._update_topic_context_cache(
        sample_monitoring_rule.topic_id,
        initial_state,
    )

    # Test with state_change threshold - only state fields matter
    sample_monitoring_rule.notification_threshold = "state_change"

    # Non-state field change - should not trigger
    non_state_change = {
        "phase": "Running",
        "status": "Healthy",
        "restarts": 0,
        "other_field": "changed_value",  # Non-state field
    }
    has_change, changes_dict = await ambient_monitor.detect_state_change(
        sample_monitoring_rule,
        non_state_change,
    )
    assert has_change is False, "Non-state field changes should not trigger state_change threshold"

    # State field change - should trigger
    state_changed = {
        "phase": "Failed",  # State field changed
        "status": "Unhealthy",
        "restarts": 5,
        "other_field": "value",
    }
    has_change, changes_dict = await ambient_monitor.detect_state_change(
        sample_monitoring_rule,
        state_changed,
    )
    assert has_change is True, "State field changes should trigger state_change threshold"
    assert "phase" in changes_dict.get("changed_fields", [])


@pytest.mark.asyncio
async def test_track_what_changed_for_rule_evaluation(ambient_monitor, store, sample_monitoring_rule):
    """Test that diff tracks what changed for rule evaluation."""
    # Set initial state
    previous_state = {
        "project_slug": "test-pipeline",
        "intent_type": "status",
        "phase": "Running",
        "restarts": 0,
        "ready": "1/1",
    }
    await ambient_monitor._update_topic_context_cache(
        sample_monitoring_rule.topic_id,
        previous_state,
    )

    # Current state with changes
    current_state = {
        "project_slug": "test-pipeline",
        "intent_type": "status",
        "phase": "Failed",  # Changed
        "restarts": 5,  # Changed
        "ready": "1/1",  # Unchanged
    }

    # Compute diff
    diff = ambient_monitor._compute_diff(previous_state, current_state)

    # Verify diff contains only changed fields
    assert "phase" in diff
    assert diff["phase"]["from"] == "Running"
    assert diff["phase"]["to"] == "Failed"

    assert "restarts" in diff
    assert diff["restarts"]["from"] == 0
    assert diff["restarts"]["to"] == 5

    # Unchanged field should not be in diff
    assert "ready" not in diff
    assert "project_slug" not in diff
    assert "intent_type" not in diff


@pytest.mark.asyncio
async def test_push_monitoring_result_updates_cache(ambient_monitor, store, sample_monitoring_rule):
    """Test that push_monitoring_result updates topic_context_cache."""
    # Set initial state
    initial_state = {"phase": "Running", "restarts": 0}
    await ambient_monitor._update_topic_context_cache(
        sample_monitoring_rule.topic_id,
        initial_state,
    )

    # Push monitoring result with new state
    new_state = {"phase": "Failed", "restarts": 5}
    changes_dict = {
        "is_first": False,
        "changed_fields": ["phase", "restarts"],
        "diff": {
            "phase": {"from": "Running", "to": "Failed"},
            "restarts": {"from": 0, "to": 5},
        },
    }
    session_id = "test-session"

    with patch("src.monitoring.ambient.get_store", return_value=store):
        # Mock find_or_create_topic to return a test topic_id
        with patch.object(
            store,
            "find_or_create_topic",
            new=AsyncMock(return_value=("test-topic-id", False)),
        ):
            await ambient_monitor.push_monitoring_result(
                sample_monitoring_rule,
                new_state,
                changes_dict,
                session_id,
            )

    # Verify cache was updated with new state
    cached = await ambient_monitor._get_topic_context_cache(sample_monitoring_rule.topic_id)
    assert cached is not None
    assert cached["phase"] == "Failed"
    assert cached["restarts"] == 5


@pytest.mark.asyncio
async def test_cache_persistence_across_checks(ambient_monitor, store, sample_monitoring_rule):
    """Test that topic_context_cache persists across multiple checks."""
    # First check - establish baseline
    first_state = {"phase": "Running", "restarts": 0}

    has_change, changes_dict = await ambient_monitor.detect_state_change(
        sample_monitoring_rule,
        first_state,
    )
    assert has_change is False, "First check should establish baseline"
    assert changes_dict["is_first"] is True

    # Second check - same state
    has_change, changes_dict = await ambient_monitor.detect_state_change(
        sample_monitoring_rule,
        first_state,
    )
    assert has_change is False, "Same state should not trigger change"

    # Third check - different state
    changed_state = {"phase": "Failed", "restarts": 5}
    has_change, changes_dict = await ambient_monitor.detect_state_change(
        sample_monitoring_rule,
        changed_state,
    )
    assert has_change is True, "Changed state should trigger"
    assert "phase" in changes_dict.get("changed_fields", [])

    # Fourth check - verify cache still has the latest state
    cached = await ambient_monitor._get_topic_context_cache(sample_monitoring_rule.topic_id)
    assert cached is not None
    # Cache should have the state from the last detect_state_change call
    # (which updates the cache internally)


@pytest.mark.asyncio
async def test_multiple_topics_independent_caches(ambient_monitor, store):
    """Test that multiple topics maintain independent caches."""
    rule1 = MonitoringRule(
        topic_id="topic1",
        project_slug="project1",
        intent_type="status",
        check_interval=60,
        urgency="normal",
        filters=[],
        notification_threshold="any_change",
    )

    rule2 = MonitoringRule(
        topic_id="topic2",
        project_slug="project2",
        intent_type="status",
        check_interval=60,
        urgency="normal",
        filters=[],
        notification_threshold="any_change",
    )

    # Set different states for each topic
    state1 = {"phase": "Running", "restarts": 0}
    state2 = {"phase": "Failed", "restarts": 5}

    await ambient_monitor._update_topic_context_cache(rule1.topic_id, state1)
    await ambient_monitor._update_topic_context_cache(rule2.topic_id, state2)

    # Verify each topic has its own cached state
    cached1 = await ambient_monitor._get_topic_context_cache(rule1.topic_id)
    cached2 = await ambient_monitor._get_topic_context_cache(rule2.topic_id)

    assert cached1["phase"] == "Running"
    assert cached2["phase"] == "Failed"

    # Changes to one topic don't affect the other
    changed_state1 = {"phase": "Succeeded", "restarts": 0}
    has_change1, changes_dict1 = await ambient_monitor.detect_state_change(rule1, changed_state1)
    assert has_change1 is True

    # Topic2 should still have its original cache
    cached2_again = await ambient_monitor._get_topic_context_cache(rule2.topic_id)
    assert cached2_again["phase"] == "Failed"


@pytest.mark.asyncio
async def test_sse_broadcast_on_monitoring_result_creation(ambient_monitor, store, sample_monitoring_rule):
    """Test that SSE event is broadcast when monitoring result is created."""
    from unittest.mock import AsyncMock

    # Set initial state in cache
    initial_state = {"phase": "Running", "restarts": 0}
    await ambient_monitor._update_topic_context_cache(
        sample_monitoring_rule.topic_id,
        initial_state,
    )

    # Prepare monitoring result with new state
    new_state = {"phase": "Failed", "restarts": 5}
    changes_dict = {
        "is_first": False,
        "changed_fields": ["phase", "restarts"],
        "diff": {
            "phase": {"from": "Running", "to": "Failed"},
            "restarts": {"from": 0, "to": 5},
        },
    }
    session_id = "test-session"

    # Mock broadcast_result to capture the call
    with patch("src.monitoring.ambient.broadcast_result", new=AsyncMock()) as mock_broadcast:
        with patch.object(
            store,
            "find_or_create_topic",
            new=AsyncMock(return_value=("test-topic-id", False)),
        ):
            await ambient_monitor.push_monitoring_result(
                sample_monitoring_rule,
                new_state,
                changes_dict,
                session_id,
            )

    # Verify broadcast was called once
    mock_broadcast.assert_awaited_once()

    # Verify the broadcast data structure
    call_args = mock_broadcast.call_args
    result = call_args.kwargs["result"]

    assert result["intent_id"] is None, "Monitoring results must have intent_id=NULL"
    assert result["result_type"] == f"monitoring:{sample_monitoring_rule.project_slug}"
    assert result["urgency"] == sample_monitoring_rule.urgency
    assert result["session_id"] == session_id
    assert "Monitoring:" in result["summary"] or "changed" in result["summary"]
    assert result["data"]["monitoring"] is True

    # Verify it was broadcast to the correct session
    assert call_args.kwargs["session_id"] == session_id
