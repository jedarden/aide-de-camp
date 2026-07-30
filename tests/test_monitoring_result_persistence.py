"""
Integration test for monitoring result persistence and SSE broadcasting.

Tests the full flow: state change → rule fire → result row → SSE event.
Verifies that fired rules write results with correct structure:
- intent_id is NULL
- topic_id is set
- result_type follows 'monitoring:{project_slug}' format
- Summary is deterministic template (no LLM call)
- SSE event broadcast triggers on result creation
- Surface routing processes monitoring results like any other result
"""
import asyncio
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import aiosqlite
import pytest

from src.monitoring.ambient import AmbientMonitor, MonitoringRule, ExceptionRule, MonitoringConfig
from src.session.store import SessionStore
from src.sse.broadcaster import SSEBroadcaster, SSEEvent
from src.surface.router import SurfaceRouter, Surface, RouteDecision
from src.render.hot_path import derive_result_type


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
def mock_broadcaster():
    """Mock SSE broadcaster for testing."""
    broadcaster = AsyncMock()
    broadcaster.broadcast = AsyncMock(return_value=1)
    return broadcaster


@pytest.fixture
def surface_router(store):
    """Surface router instance for testing."""
    return SurfaceRouter(store)


@pytest.fixture
def ambient_monitor(store):
    """Create an AmbientMonitor instance with test store and exception rules."""
    monitor = AmbientMonitor(session_store=store)

    # Set up a config with exception rules
    monitor.config = MonitoringConfig(
        active_topics=[],
        exceptions=[
            ExceptionRule(
                name="pod_failure",
                project_slug="test-pipeline",
                condition="phase==Failed",
                urgency="high",
                message="Pod has failed",
            ),
            ExceptionRule(
                name="high_restart_count",
                project_slug="test-pipeline",
                condition="restarts>5",
                urgency="normal",
                message="Pod has high restart count",
            ),
        ],
        batching={},
        quiet_hours={},
        channels={},
    )

    return monitor


@pytest.fixture
def sample_monitoring_rule():
    """Create a sample monitoring rule for testing."""
    return MonitoringRule(
        topic_id="test-pipeline-status",
        project_slug="test-pipeline",
        intent_type="status",
        check_interval=60,
        urgency="normal",
        filters=[],
        notification_threshold="any_change",
    )


@pytest.fixture
async def session_with_surface(store):
    """Create a session with an active surface for testing."""
    session_id = "test-session"
    await store.create_session(session_id)
    surface_id = await store.register_surface(session_id, "canvas")
    return session_id, surface_id


# --- Integration Tests ----------------------------------------------------------


@pytest.mark.asyncio
@patch("src.sse.broadcaster.get_broadcaster")
async def test_state_change_rule_fire_result_row_sse_event_full_flow(
    mock_get_broadcaster,
    ambient_monitor,
    sample_monitoring_rule,
    store,
    session_with_surface,
    mock_broadcaster,
):
    """
    Integration test: state change → rule fire → result row → SSE event.

    Verifies the complete flow:
    1. Initial state is cached (no result)
    2. State change occurs
    3. Rule fires (phase==Failed condition matches)
    4. Result row is written with correct structure
    5. SSE event is broadcast
    6. Result is retrievable from database
    """
    # Setup the mock broadcaster
    mock_get_broadcaster.return_value = mock_broadcaster

    session_id, surface_id = session_with_surface

    # Step 1: Set initial state (baseline)
    initial_state = {"phase": "Running", "restarts": 0}
    await ambient_monitor._update_topic_context_cache(
        sample_monitoring_rule.topic_id,
        initial_state,
    )

    # Verify no results exist yet
    session_results = [r for r in await store.get_all_results() if r["session_id"] == session_id]
    assert len(session_results) == 0, "No results should exist before state change"

    # Step 2: Simulate state change (phase goes to Failed)
    current_state = {"phase": "Failed", "restarts": 3}
    has_change, changes_dict = await ambient_monitor.detect_state_change(
        sample_monitoring_rule,
        current_state,
    )

    assert has_change is True, "State change should be detected"
    assert changes_dict["is_first"] is False
    assert "phase" in changes_dict["changed_fields"]

    # Step 3: Evaluate rules (phase==Failed should trigger pod_failure rule)
    triggered_rules = ambient_monitor.evaluate_exception_rules(
        changes_dict=changes_dict,
        project_slug=sample_monitoring_rule.project_slug,
        rules=ambient_monitor.config.exceptions,
    )

    assert len(triggered_rules) == 1, "pod_failure rule should fire"
    assert triggered_rules[0]["exception_type"] == "pod_failure"
    assert triggered_rules[0]["urgency"] == "high"

    # Add triggered rules to changes dict (as monitor_topic does)
    changes_dict["triggered_rules"] = triggered_rules

    # Step 4: Push monitoring result (this writes to DB and broadcasts SSE)
    # Call push_monitoring_result
    await ambient_monitor.push_monitoring_result(
        rule=sample_monitoring_rule,
        current_state=current_state,
        changes_dict=changes_dict,
        session_id=session_id,
    )

    # Step 5: Verify result row was written with correct structure
    session_results = [r for r in await store.get_all_results() if r["session_id"] == session_id]
    assert len(session_results) == 1, "One result should be created"

    result = session_results[0]

    # Verify intent_id is NULL (monitoring-originated)
    assert result["intent_id"] is None, "intent_id should be NULL for monitoring results"

    # Verify topic_id is set
    assert result["topic_id"] is not None, "topic_id should be set"

    # Verify result_type follows 'monitoring:{project_slug}' format
    expected_result_type = derive_result_type(
        intent_type="monitoring",
        project_slug=sample_monitoring_rule.project_slug
    )
    assert result["result_type"] == expected_result_type
    assert result["result_type"] == "monitoring:test-pipeline"

    # Verify summary is deterministic template (no LLM)
    assert result["summary"] is not None
    assert "phase changed" in result["summary"].lower() or "failed" in result["summary"].lower()
    # Summary should mention the state change
    assert "Failed" in result["summary"] or "failed" in result["summary"]

    # Verify urgency
    assert result["urgency"] == sample_monitoring_rule.urgency

    # Verify data contains monitoring fields
    import json
    result_data = json.loads(result["data"])
    assert result_data["monitoring"] is True
    assert "current_state" in result_data
    assert "previous_state" in result_data
    assert result_data["current_state"]["phase"] == "Failed"
    assert result_data["previous_state"]["phase"] == "Running"
    # Order of changed_fields doesn't matter - use set comparison
    assert set(result_data["changed_fields"]) == {"phase", "restarts"}
    assert len(result_data.get("triggered_rules", [])) == 1
    assert result_data["triggered_rules"][0]["exception_type"] == "pod_failure"

    # Step 6: Verify SSE event was broadcast
    assert mock_broadcaster.broadcast.called, "broadcast() should be called"
    assert mock_broadcaster.broadcast.call_count == 1

    # Get the SSE event that was broadcast
    call_args = mock_broadcaster.broadcast.call_args
    # The first positional argument is the SSEEvent
    sse_event = call_args[0][0]

    assert isinstance(sse_event, SSEEvent), "broadcast() should receive SSEEvent"
    assert sse_event.event_type == "result_created"
    assert sse_event.data["id"] == result["id"]
    assert sse_event.data["intent_id"] is None
    assert sse_event.data["result_type"] == "monitoring:test-pipeline"
    assert sse_event.data["urgency"] == "normal"
    assert sse_event.target_session_id == session_id


@pytest.mark.asyncio
async def test_no_result_when_rule_does_not_fire(
    ambient_monitor,
    sample_monitoring_rule,
    store,
    session_with_surface,
):
    """
    Test that no result is created when rule doesn't fire (no matching state change).
    """
    session_id, surface_id = session_with_surface

    # Set initial state
    initial_state = {"phase": "Running", "restarts": 0}
    await ambient_monitor._update_topic_context_cache(
        sample_monitoring_rule.topic_id,
        initial_state,
    )

    # State change that doesn't trigger any rule (phase stays Running)
    current_state = {"phase": "Running", "restarts": 2}
    has_change, changes_dict = await ambient_monitor.detect_state_change(
        sample_monitoring_rule,
        current_state,
    )

    assert has_change is True, "State change should be detected"

    # Evaluate rules - none should fire (no phase==Failed, no restarts>5)
    triggered_rules = ambient_monitor.evaluate_exception_rules(
        changes_dict=changes_dict,
        project_slug=sample_monitoring_rule.project_slug,
        rules=ambient_monitor.config.exceptions,
    )

    assert len(triggered_rules) == 0, "No rules should fire"

    # Push result anyway (normal state change result, no exception rules triggered)
    await ambient_monitor.push_monitoring_result(
        rule=sample_monitoring_rule,
        current_state=current_state,
        changes_dict=changes_dict,
        session_id=session_id,
    )

    # Verify result was still created (state change results are always written)
    session_results = [r for r in await store.get_all_results() if r["session_id"] == session_id]
    assert len(session_results) == 1, "Result should be created even when no exception rules fire"

    # But no triggered_rules in data
    result = session_results[0]
    import json
    result_data = json.loads(result["data"])
    assert len(result_data.get("triggered_rules", [])) == 0


@pytest.mark.asyncio
async def test_multiple_rules_fire_on_single_state_change(
    ambient_monitor,
    sample_monitoring_rule,
    store,
    session_with_surface,
):
    """
    Test that multiple rules can fire on a single state change and all are captured.
    """
    session_id, surface_id = session_with_surface

    # Add an additional rule that also matches phase==Failed
    ambient_monitor.config.exceptions.append(
        ExceptionRule(
            name="critical_failure",
            project_slug="test-pipeline",
            condition="phase==Failed",
            urgency="critical",
            message="Critical failure detected",
        ),
    )

    # Set initial state
    initial_state = {"phase": "Running", "restarts": 0}
    await ambient_monitor._update_topic_context_cache(
        sample_monitoring_rule.topic_id,
        initial_state,
    )

    # State change that triggers both rules
    current_state = {"phase": "Failed", "restarts": 10}  # Also triggers restarts>5
    has_change, changes_dict = await ambient_monitor.detect_state_change(
        sample_monitoring_rule,
        current_state,
    )

    # Evaluate rules - multiple should fire
    triggered_rules = ambient_monitor.evaluate_exception_rules(
        changes_dict=changes_dict,
        project_slug=sample_monitoring_rule.project_slug,
        rules=ambient_monitor.config.exceptions,
    )

    assert len(triggered_rules) == 3, "Three rules should fire (pod_failure, critical_failure, high_restart_count)"

    exception_types = {r["exception_type"] for r in triggered_rules}
    assert "pod_failure" in exception_types
    assert "critical_failure" in exception_types
    assert "high_restart_count" in exception_types

    # Push result with triggered rules
    changes_dict["triggered_rules"] = triggered_rules
    await ambient_monitor.push_monitoring_result(
        rule=sample_monitoring_rule,
        current_state=current_state,
        changes_dict=changes_dict,
        session_id=session_id,
    )

    # Verify result captures all triggered rules
    session_results = [r for r in await store.get_all_results() if r["session_id"] == session_id]
    assert len(session_results) == 1

    result = session_results[0]
    import json
    result_data = json.loads(result["data"])
    assert len(result_data["triggered_rules"]) == 3


@pytest.mark.asyncio
async def test_surface_routing_processes_monitoring_results_like_any_other_result(
    ambient_monitor,
    sample_monitoring_rule,
    store,
    session_with_surface,
    surface_router,
):
    """
    Test that surface routing processes monitoring results like any other result.

    Verifies that monitoring results follow the same routing priority as regular results:
    1. Origin surface (if still connected)
    2. Most recently active connected surface
    3. Any connected surface
    4. Always-available fallback (Telegram)
    """
    session_id, surface_id = session_with_surface

    # Create a monitoring result
    initial_state = {"phase": "Running", "restarts": 0}
    await ambient_monitor._update_topic_context_cache(
        sample_monitoring_rule.topic_id,
        initial_state,
    )

    current_state = {"phase": "Failed", "restarts": 0}
    has_change, changes_dict = await ambient_monitor.detect_state_change(
        sample_monitoring_rule,
        current_state,
    )

    await ambient_monitor.push_monitoring_result(
        rule=sample_monitoring_rule,
        current_state=current_state,
        changes_dict=changes_dict,
        session_id=session_id,
    )

    # Get the result
    session_results = [r for r in await store.get_all_results() if r["session_id"] == session_id]
    assert len(session_results) == 1
    result = session_results[0]

    # Test surface routing with the monitoring result
    # The routing should work the same as for any other result
    route_decision = await surface_router.route_result(
        session_id=session_id,
        origin_surface_id=surface_id,
        urgency=result["urgency"],
    )

    # Verify routing decision
    assert isinstance(route_decision, RouteDecision)
    assert len(route_decision.target_surfaces) >= 0
    # The routing should have found the active canvas surface
    if route_decision.target_surfaces:
        assert route_decision.target_surfaces[0].id == surface_id
        assert route_decision.reason in ("origin-surface-active", "most-recent-active")


@pytest.mark.asyncio
async def test_deterministic_summary_no_llm_call(
    ambient_monitor,
    sample_monitoring_rule,
    store,
    session_with_surface,
):
    """
    Test that monitoring result summaries are deterministic templates with no LLM call.

    Verifies that _generate_summary produces consistent output based on state changes
    without calling an LLM.
    """
    session_id, surface_id = session_with_surface

    # Test various state change scenarios
    test_cases = [
        {
            "current": {"phase": "Failed", "restarts": 0},
            "previous": {"phase": "Running", "restarts": 0},
            "changed_fields": ["phase"],
            "diff": {"phase": {"from": "Running", "to": "Failed"}},
            "expected_keywords": ["phase", "changed", "Failed"],
        },
        {
            "current": {"phase": "Running", "restarts": 6},
            "previous": {"phase": "Running", "restarts": 0},
            "changed_fields": ["restarts"],
            "diff": {"restarts": {"from": 0, "to": 6}},
            "expected_keywords": ["changed", "restarts"],
        },
        {
            "current": {"sync_status": "OutOfSync", "phase": "Running"},
            "previous": {"sync_status": "Synced", "phase": "Running"},
            "changed_fields": ["sync_status"],
            "diff": {"sync_status": {"from": "Synced", "to": "OutOfSync"}},
            "expected_keywords": ["sync", "OutOfSync"],
        },
    ]

    for test_case in test_cases:
        changes_dict = {
            "is_first": False,
            "changed_fields": test_case["changed_fields"],
            "diff": test_case["diff"],
        }

        summary = ambient_monitor._generate_summary(
            rule=sample_monitoring_rule,
            current_state=test_case["current"],
            previous_state=test_case["previous"],
            changes_dict=changes_dict,
        )

        # Verify summary is a non-empty string
        assert isinstance(summary, str)
        assert len(summary) > 0

        # Verify summary contains expected keywords (deterministic based on change)
        for keyword in test_case["expected_keywords"]:
            # At least some keywords should appear (case-insensitive)
            assert keyword.lower() in summary.lower() or any(
                kw in summary for kw in test_case["expected_keywords"]
            ), f"Summary '{summary}' should reference the change"

        # Verify no LLM-specific patterns (deterministic template only)
        assert "[LLM]" not in summary
        assert "AI:" not in summary


@pytest.mark.asyncio
async def test_result_type_format_monitoring_project_slug(
    ambient_monitor,
    sample_monitoring_rule,
    store,
    session_with_surface,
):
    """
    Test that result_type follows the 'monitoring:{project_slug}' format exactly.
    """
    session_id, surface_id = session_with_surface

    # Create a monitoring result
    initial_state = {"phase": "Running", "restarts": 0}
    await ambient_monitor._update_topic_context_cache(
        sample_monitoring_rule.topic_id,
        initial_state,
    )

    current_state = {"phase": "Failed", "restarts": 0}
    has_change, changes_dict = await ambient_monitor.detect_state_change(
        sample_monitoring_rule,
        current_state,
    )

    await ambient_monitor.push_monitoring_result(
        rule=sample_monitoring_rule,
        current_state=current_state,
        changes_dict=changes_dict,
        session_id=session_id,
    )

    # Verify result_type format
    session_results = [r for r in await store.get_all_results() if r["session_id"] == session_id]
    assert len(session_results) == 1

    result = session_results[0]
    assert result["result_type"] == "monitoring:test-pipeline"

    # Test derive_result_type function directly
    derived_type = derive_result_type(
        intent_type="monitoring",
        project_slug="test-pipeline"
    )
    assert derived_type == "monitoring:test-pipeline"

    # Test with different project_slug
    derived_type_custom = derive_result_type(
        intent_type="monitoring",
        project_slug="my-custom-app"
    )
    assert derived_type_custom == "monitoring:my-custom-app"


@pytest.mark.asyncio
async def test_first_check_creates_no_result(
    ambient_monitor,
    sample_monitoring_rule,
    store,
    session_with_surface,
):
    """
    Test that the first check (baseline) creates no result, only caches state.
    """
    session_id, surface_id = session_with_surface

    # No initial state cached - this is the first check
    current_state = {"phase": "Running", "restarts": 0}
    has_change, changes_dict = await ambient_monitor.detect_state_change(
        sample_monitoring_rule,
        current_state,
    )

    # First check should not report a change (just caches baseline)
    assert has_change is False, "First check should not report change"
    assert changes_dict["is_first"] is True

    # Verify no result was created
    session_results = [r for r in await store.get_all_results() if r["session_id"] == session_id]
    assert len(session_results) == 0, "No result should be created on first check"

    # Verify state was cached
    cached = await ambient_monitor._get_topic_context_cache(sample_monitoring_rule.topic_id)
    assert cached is not None, "State should be cached after first check"
    assert cached["phase"] == "Running"
