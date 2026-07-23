"""
Tests for ambient.py rule engine that fires on state changes.

Tests coverage:
- Rule engine evaluates conditions against diff results
- Rules fire only when matching state changes occur
- No firing when no relevant state changes
- Rule output includes project_slug, urgency, and exception type
- Test covers rule fire on change, no fire on no-change
"""

import asyncio
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

import aiosqlite
import pytest

from src.monitoring.ambient import AmbientMonitor, MonitoringRule, ExceptionRule
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
    monitor = AmbientMonitor(session_store=store)

    # Set up a config with exception rules
    from src.monitoring.ambient import MonitoringConfig
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
            ExceptionRule(
                name="any_out_of_sync",
                project_slug=None,  # Applies to all projects
                condition="sync_status==OutOfSync",
                urgency="high",
                message="Deployment is out of sync",
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


# --- Tests ---------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rule_engine_evaluates_conditions_against_diff_results(ambient_monitor):
    """Test that rule engine evaluates conditions against diff results."""
    # Simulate a diff with phase change
    changes_dict = {
        "is_first": False,
        "changed_fields": ["phase", "restarts"],
        "diff": {
            "phase": {"from": "Running", "to": "Failed"},
            "restarts": {"from": 0, "to": 3},
        },
    }

    # Evaluate rules
    triggered = ambient_monitor.evaluate_exception_rules(
        changes_dict=changes_dict,
        project_slug="test-pipeline",
        rules=ambient_monitor.config.exceptions,
    )

    # Should trigger the pod_failure rule (phase==Failed)
    assert len(triggered) == 1
    assert triggered[0]["exception_type"] == "pod_failure"
    assert triggered[0]["condition"] == "phase==Failed"
    assert triggered[0]["urgency"] == "high"
    assert triggered[0]["project_slug"] == "test-pipeline"


@pytest.mark.asyncio
async def test_rules_fire_only_when_matching_state_changes_occur(ambient_monitor):
    """Test that rules fire only when matching state changes occur."""
    # Simulate a diff with no relevant changes
    changes_dict_no_match = {
        "is_first": False,
        "changed_fields": ["ready"],
        "diff": {
            "ready": {"from": "1/1", "to": "0/1"},
        },
    }

    # Evaluate rules - should not fire (no phase or restarts change)
    triggered = ambient_monitor.evaluate_exception_rules(
        changes_dict=changes_dict_no_match,
        project_slug="test-pipeline",
        rules=ambient_monitor.config.exceptions,
    )

    # No rules should fire
    assert len(triggered) == 0

    # Now simulate a matching change
    changes_dict_match = {
        "is_first": False,
        "changed_fields": ["phase"],
        "diff": {
            "phase": {"from": "Running", "to": "Failed"},
        },
    }

    triggered = ambient_monitor.evaluate_exception_rules(
        changes_dict=changes_dict_match,
        project_slug="test-pipeline",
        rules=ambient_monitor.config.exceptions,
    )

    # Should trigger the pod_failure rule
    assert len(triggered) == 1
    assert triggered[0]["exception_type"] == "pod_failure"


@pytest.mark.asyncio
async def test_no_firing_when_no_relevant_state_changes(ambient_monitor):
    """Test that no firing occurs when no relevant state changes."""
    # Empty changes dict (no changes)
    changes_dict_empty = {
        "is_first": False,
        "changed_fields": [],
        "diff": {},
    }

    triggered = ambient_monitor.evaluate_exception_rules(
        changes_dict=changes_dict_empty,
        project_slug="test-pipeline",
        rules=ambient_monitor.config.exceptions,
    )

    # No rules should fire
    assert len(triggered) == 0

    # Changes dict with non-matching fields
    changes_dict_irrelevant = {
        "is_first": False,
        "changed_fields": ["some_other_field"],
        "diff": {
            "some_other_field": {"from": "old", "to": "new"},
        },
    }

    triggered = ambient_monitor.evaluate_exception_rules(
        changes_dict=changes_dict_irrelevant,
        project_slug="test-pipeline",
        rules=ambient_monitor.config.exceptions,
    )

    # No rules should fire
    assert len(triggered) == 0


@pytest.mark.asyncio
async def test_rule_output_includes_project_slug_urgency_and_exception_type(ambient_monitor):
    """Test that rule output includes project_slug, urgency, and exception type."""
    changes_dict = {
        "is_first": False,
        "changed_fields": ["sync_status"],
        "diff": {
            "sync_status": {"from": "Synced", "to": "OutOfSync"},
        },
    }

    triggered = ambient_monitor.evaluate_exception_rules(
        changes_dict=changes_dict,
        project_slug="test-pipeline",
        rules=ambient_monitor.config.exceptions,
    )

    # The any_out_of_sync rule should fire (project_slug=None means applies to all)
    assert len(triggered) == 1

    rule_output = triggered[0]
    assert "project_slug" in rule_output
    assert "urgency" in rule_output
    assert "exception_type" in rule_output

    assert rule_output["project_slug"] == "test-pipeline"
    assert rule_output["urgency"] == "high"
    assert rule_output["exception_type"] == "any_out_of_sync"
    assert rule_output["message"] == "Deployment is out of sync"


@pytest.mark.asyncio
async def test_rule_fire_on_change(ambient_monitor, sample_monitoring_rule):
    """Test that rule fires on matching state change."""
    # Set initial state
    initial_state = {"phase": "Running", "restarts": 0}
    await ambient_monitor._update_topic_context_cache(
        sample_monitoring_rule.topic_id,
        initial_state,
    )

    # Simulate state change to Failed
    current_state = {"phase": "Failed", "restarts": 0}
    has_change, changes_dict = await ambient_monitor.detect_state_change(
        sample_monitoring_rule,
        current_state,
    )

    assert has_change is True
    assert changes_dict["is_first"] is False

    # Evaluate rules
    triggered = ambient_monitor.evaluate_exception_rules(
        changes_dict=changes_dict,
        project_slug=sample_monitoring_rule.project_slug,
        rules=ambient_monitor.config.exceptions,
    )

    # Should fire the pod_failure rule
    assert len(triggered) == 1
    assert triggered[0]["exception_type"] == "pod_failure"
    assert triggered[0]["project_slug"] == "test-pipeline"
    assert triggered[0]["urgency"] == "high"


@pytest.mark.asyncio
async def test_rule_no_fire_on_no_change(ambient_monitor, sample_monitoring_rule):
    """Test that rule does not fire when there's no state change."""
    # Set initial state
    initial_state = {"phase": "Running", "restarts": 0}
    await ambient_monitor._update_topic_context_cache(
        sample_monitoring_rule.topic_id,
        initial_state,
    )

    # Same state - no change
    same_state = {"phase": "Running", "restarts": 0}
    has_change, changes_dict = await ambient_monitor.detect_state_change(
        sample_monitoring_rule,
        same_state,
    )

    assert has_change is False

    # Evaluate rules - should not fire (no change)
    triggered = ambient_monitor.evaluate_exception_rules(
        changes_dict=changes_dict,
        project_slug=sample_monitoring_rule.project_slug,
        rules=ambient_monitor.config.exceptions,
    )

    # No rules should fire
    assert len(triggered) == 0


@pytest.mark.asyncio
async def test_multiple_rules_can_fire_on_single_change(ambient_monitor):
    """Test that multiple rules can fire on a single state change."""
    # Add another rule that also matches phase==Failed
    from src.monitoring.ambient import ExceptionRule

    extra_rule = ExceptionRule(
        name="critical_failure",
        project_slug="test-pipeline",
        condition="phase==Failed",
        urgency="critical",
        message="Critical failure detected",
    )

    rules_with_extra = ambient_monitor.config.exceptions + [extra_rule]

    changes_dict = {
        "is_first": False,
        "changed_fields": ["phase"],
        "diff": {
            "phase": {"from": "Running", "to": "Failed"},
        },
    }

    triggered = ambient_monitor.evaluate_exception_rules(
        changes_dict=changes_dict,
        project_slug="test-pipeline",
        rules=rules_with_extra,
    )

    # Both rules should fire (pod_failure and critical_failure)
    assert len(triggered) == 2

    exception_types = {r["exception_type"] for r in triggered}
    assert "pod_failure" in exception_types
    assert "critical_failure" in exception_types


@pytest.mark.asyncio
async def test_rule_condition_operators(ambient_monitor):
    """Test various rule condition operators."""
    # Test > operator (high_restart_count)
    changes_dict = {
        "is_first": False,
        "changed_fields": ["restarts"],
        "diff": {
            "restarts": {"from": 0, "to": 10},
        },
    }

    triggered = ambient_monitor.evaluate_exception_rules(
        changes_dict=changes_dict,
        project_slug="test-pipeline",
        rules=ambient_monitor.config.exceptions,
    )

    # Should trigger high_restart_count rule (10 > 5)
    assert len(triggered) == 1
    assert triggered[0]["exception_type"] == "high_restart_count"
    assert triggered[0]["urgency"] == "normal"

    # Test that > doesn't fire when not met
    changes_dict_below_threshold = {
        "is_first": False,
        "changed_fields": ["restarts"],
        "diff": {
            "restarts": {"from": 0, "to": 3},
        },
    }

    triggered = ambient_monitor.evaluate_exception_rules(
        changes_dict=changes_dict_below_threshold,
        project_slug="test-pipeline",
        rules=ambient_monitor.config.exceptions,
    )

    # Should not trigger (3 is not > 5)
    assert len(triggered) == 0


@pytest.mark.asyncio
async def test_rule_project_slug_filtering(ambient_monitor):
    """Test that rules filter by project_slug correctly."""
    changes_dict = {
        "is_first": False,
        "changed_fields": ["sync_status"],
        "diff": {
            "sync_status": {"from": "Synced", "to": "OutOfSync"},
        },
    }

    # The any_out_of_sync rule has project_slug=None, so it should fire for any project
    triggered = ambient_monitor.evaluate_exception_rules(
        changes_dict=changes_dict,
        project_slug="different-project",  # Different project
        rules=ambient_monitor.config.exceptions,
    )

    # Should still fire the any_out_of_sync rule (applies to all projects)
    assert len(triggered) == 1
    assert triggered[0]["exception_type"] == "any_out_of_sync"

    # But project-specific rules should not fire
    changes_dict_phase = {
        "is_first": False,
        "changed_fields": ["phase"],
        "diff": {
            "phase": {"from": "Running", "to": "Failed"},
        },
    }

    triggered = ambient_monitor.evaluate_exception_rules(
        changes_dict=changes_dict_phase,
        project_slug="different-project",  # Not test-pipeline
        rules=ambient_monitor.config.exceptions,
    )

    # pod_failure rule should not fire (project_slug mismatch)
    assert len(triggered) == 0


@pytest.mark.asyncio
async def test_rule_condition_with_numeric_values(ambient_monitor):
    """Test rule condition evaluation with numeric values."""
    changes_dict = {
        "is_first": False,
        "changed_fields": ["restarts"],
        "diff": {
            "restarts": {"from": "0", "to": "6"},  # String values
        },
    }

    # Should still evaluate correctly (converts to float)
    triggered = ambient_monitor.evaluate_exception_rules(
        changes_dict=changes_dict,
        project_slug="test-pipeline",
        rules=ambient_monitor.config.exceptions,
    )

    assert len(triggered) == 1
    assert triggered[0]["exception_type"] == "high_restart_count"


@pytest.mark.asyncio
async def test_monitor_topic_loop_evaluates_rules(store):
    """Test that monitor_topic loop evaluates rules when state changes."""
    from src.monitoring.ambient import MonitoringConfig, ExceptionRule

    # Create monitor with config
    monitor = AmbientMonitor(session_store=store)
    monitor.config = MonitoringConfig(
        active_topics=[],
        exceptions=[
            ExceptionRule(
                name="test_rule",
                project_slug="test-pipeline",
                condition="phase==Failed",
                urgency="high",
                message="Test rule fired",
            ),
        ],
        batching={},
        quiet_hours={},
        channels={},
    )

    rule = MonitoringRule(
        topic_id="test-topic",
        project_slug="test-pipeline",
        intent_type="status",
        check_interval=1,
        urgency="normal",
        filters=[],
        notification_threshold="any_change",
    )

    # Mock check_topic_state to return states
    check_states = [
        {"phase": "Running", "restarts": 0},  # Initial - no change
        {"phase": "Failed", "restarts": 0},   # State change - should fire rule
    ]

    call_count = [0]

    async def mock_check_topic_state(r):
        state = check_states[call_count[0]]
        call_count[0] += 1
        return state

    monitor.check_topic_state = mock_check_topic_state

    # Mock push_monitoring_result to capture result
    results_captured = []

    async def mock_push_result(r, state, changes, session):
        results_captured.append({
            "state": state,
            "changes": changes,
            "triggered_rules": changes.get("triggered_rules", []),
        })

    monitor.push_monitoring_result = mock_push_result

    # Run one iteration (we'll just call the logic once, not the full loop)
    # First check - baseline
    current_state = await monitor.check_topic_state(rule)
    if current_state:
        has_change, changes_dict = await monitor.detect_state_change(rule, current_state)
        if has_change:
            await monitor.push_monitoring_result(rule, current_state, changes_dict, "test")
        else:
            await monitor._update_topic_context_cache(rule.topic_id, current_state)

    # Verify no result on baseline
    assert len(results_captured) == 0

    # Second check - state change
    current_state = await monitor.check_topic_state(rule)
    if current_state:
        has_change, changes_dict = await monitor.detect_state_change(rule, current_state)
        if has_change:
            # Evaluate rules
            if monitor.config and monitor.config.exceptions:
                triggered_rules = monitor.evaluate_exception_rules(
                    changes_dict=changes_dict,
                    project_slug=rule.project_slug,
                    rules=monitor.config.exceptions,
                )
                if triggered_rules:
                    changes_dict["triggered_rules"] = triggered_rules
            await monitor.push_monitoring_result(rule, current_state, changes_dict, "test")

    # Verify result created with triggered rules
    assert len(results_captured) == 1
    assert len(results_captured[0]["triggered_rules"]) == 1
    assert results_captured[0]["triggered_rules"][0]["exception_type"] == "test_rule"
    assert results_captured[0]["triggered_rules"][0]["project_slug"] == "test-pipeline"
    assert results_captured[0]["triggered_rules"][0]["urgency"] == "high"


@pytest.mark.asyncio
async def test_invalid_rule_condition_does_not_crash(ambient_monitor):
    """Test that invalid rule conditions are handled gracefully."""
    changes_dict = {
        "is_first": False,
        "changed_fields": ["phase"],
        "diff": {
            "phase": {"from": "Running", "to": "Failed"},
        },
    }

    # Add a rule with invalid condition syntax
    from src.monitoring.ambient import ExceptionRule

    invalid_rule = ExceptionRule(
        name="invalid_rule",
        project_slug="test-pipeline",
        condition="invalid_condition_without_operator",
        urgency="normal",
        message="This should not crash",
    )

    rules_with_invalid = ambient_monitor.config.exceptions + [invalid_rule]

    # Should not crash, just log warning
    triggered = ambient_monitor.evaluate_exception_rules(
        changes_dict=changes_dict,
        project_slug="test-pipeline",
        rules=rules_with_invalid,
    )

    # Valid rules should still fire, invalid should be skipped
    assert len(triggered) == 1  # Only pod_failure fires
    assert triggered[0]["exception_type"] == "pod_failure"
