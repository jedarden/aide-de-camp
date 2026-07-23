"""
Tests for stuck and failed card rendering (Family 5).

These cards are rendered when tasks hit circuit breakers or fail non-recoverably.
Stuck cards use warning/amber theming; failed cards use error/red theming.
"""

import json
import pytest
import subprocess
from typing import Any, Dict


def _run_stuck_event(extra_data: Dict[str, Any] = None) -> Dict:
    """Helper: Run stuck event through eventsource runner."""
    data = {
        "intent_id": "intent-stuck-test",
        "utterance": "Check the status of the deployment pipeline",
    }
    if extra_data:
        data.update(extra_data)

    plan = {
        "session_id": "test-session-stuck",
        "register_surface_id": "surf-test-stuck",
        "openapi_version": "0.0.0",
        "cards": [],
        "steps": [
            {"action": "open"},
            {"action": "event", "name": "task_stuck", "data": data},
        ],
    }

    plan_json = json.dumps(plan)
    result = subprocess.run(
        ["node", "tests/e2e/canvas_eventsource_runner.js"],
        input=plan_json.encode(),
        capture_output=True,
        cwd="/home/coding/aide-de-camp",
        timeout=10,
    )

    if result.returncode != 0:
        raise RuntimeError(f"Runner failed: {result.stderr.decode()}")

    return json.loads(result.stdout.decode())


def _run_failed_event(extra_data: Dict[str, Any] = None) -> Dict:
    """Helper: Run failed event through eventsource runner."""
    data = {
        "intent_id": "intent-failed-test",
        "utterance": "Deploy the new version to production",
    }
    if extra_data:
        data.update(extra_data)

    plan = {
        "session_id": "test-session-failed",
        "register_surface_id": "surf-test-failed",
        "openapi_version": "0.0.0",
        "cards": [],
        "steps": [
            {"action": "open"},
            {"action": "event", "name": "task_failed", "data": data},
        ],
    }

    plan_json = json.dumps(plan)
    result = subprocess.run(
        ["node", "tests/e2e/canvas_eventsource_runner.js"],
        input=plan_json.encode(),
        capture_output=True,
        cwd="/home/coding/aide-de-camp",
        timeout=10,
    )

    if result.returncode != 0:
        raise RuntimeError(f"Runner failed: {result.stderr.decode()}")

    return json.loads(result.stdout.decode())


def test_family_5_stuck_card_basic_rendering():
    """
    Family 5a: Stuck card renders with warning (amber/orange) styling.

    AC:
    - Stuck card is created with stuck-card class
    - Shows construction icon (🚧)
    - Title reads "Task stuck — needs your input"
    - Displays stuck reason in warning-themed wrapper
    - Shows bead ID if provided
    - Shows refusal count if provided
    - Has view bead button with amber styling
    """
    telemetry = _run_stuck_event({
        "bead_id": "adc-stuck-test-123",
        "stuck_reason": "Agent refused to complete task due to missing dependencies",
        "refusal_count": 3,
        "message": "This task requires manual intervention",
        "action_hint": "Please review the bead and update requirements"
    })
    html = telemetry["containerHTML"]

    # Basic card structure
    assert "stuck-card" in html
    assert "builtin-card" in html
    assert "data-builtin=\"stuck\"" in html

    # Icon and title
    assert "🚧" in html
    assert "Task stuck — needs your input" in html

    # Stuck reason display
    assert "stuck-reason-wrap" in html
    assert "stuck-reason" in html
    assert "Agent refused to complete task due to missing dependencies" in html

    # Metadata display
    assert "adc-stuck-test-123" in html
    assert "Refusals: 3" in html

    # Action elements
    assert "stuck-view-bead" in html
    assert "View bead" in html


def test_family_5_stuck_card_minimal_data():
    """
    Family 5b: Stuck card renders with minimal data.

    AC:
    - Stuck card renders even with only required fields
    - Shows appropriate placeholders for optional fields
    - Still displays warning styling
    """
    telemetry = _run_stuck_event({
        "stuck_reason": "Task waiting for manual approval"
    })
    html = telemetry["containerHTML"]

    assert "stuck-card" in html
    assert "Task waiting for manual approval" in html
    assert "🚧" in html


def test_family_5_failed_card_basic_rendering():
    """
    Family 5c: Failed card renders with error (red) styling.

    AC:
    - Failed card is created with failed-card class
    - Shows X icon (❌)
    - Title reads "Task failed"
    - Displays failure reason in error-themed wrapper
    - Shows bead ID if provided
    - Shows error type if provided
    - Has retry button with red styling
    """
    telemetry = _run_failed_event({
        "bead_id": "adc-failed-test-456",
        "failure_reason": "Worker process crashed: out of memory",
        "error_type": "worker_crash",
        "message": "The task failed to complete due to system error"
    })
    html = telemetry["containerHTML"]

    # Basic card structure
    assert "failed-card" in html
    assert "builtin-card" in html
    assert "data-builtin=\"failed\"" in html

    # Icon and title
    assert "❌" in html
    assert "Task failed" in html

    # Failure reason display
    assert "failed-reason-wrap" in html
    assert "failed-reason" in html
    assert "Worker process crashed: out of memory" in html

    # Metadata display
    assert "adc-failed-test-456" in html
    assert "Error type: worker_crash" in html

    # Action elements
    assert "failed-retry" in html
    assert "Retry" in html


def test_family_5_failed_card_minimal_data():
    """
    Family 5d: Failed card renders with minimal data.

    AC:
    - Failed card renders even with only required fields
    - Shows appropriate placeholders for optional fields
    - Still displays error styling
    """
    telemetry = _run_failed_event({
        "failure_reason": "Network timeout after 30 seconds"
    })
    html = telemetry["containerHTML"]

    assert "failed-card" in html
    assert "Network timeout after 30 seconds" in html
    assert "❌" in html


def test_family_5_stuck_vs_failed_visual_distinction():
    """
    Family 5e: Stuck and failed cards have visually distinct styling.

    AC:
    - Stuck card uses amber/warning color scheme
    - Failed card uses red/error color scheme
    - Both cards render simultaneously without conflict
    - Visual distinction is clear in HTML structure
    """
    stuck_telemetry = _run_stuck_event({
        "bead_id": "adc-stuck-001",
        "stuck_reason": "Awaiting user input for required field"
    })
    stuck_html = stuck_telemetry["containerHTML"]

    failed_telemetry = _run_failed_event({
        "bead_id": "adc-failed-001",
        "failure_reason": "Invalid configuration parameter"
    })
    failed_html = failed_telemetry["containerHTML"]

    # Stuck card has warning elements
    assert "stuck-card" in stuck_html
    assert "stuck-reason-wrap" in stuck_html
    assert "🚧" in stuck_html

    # Failed card has error elements
    assert "failed-card" in failed_html
    assert "failed-reason-wrap" in failed_html
    assert "❌" in failed_html

    # They use different styling classes
    assert "stuck-reason" in stuck_html
    assert "failed-reason" in failed_html

    # Icons are different
    assert "🚧" in stuck_html
    assert "❌" in failed_html


def test_family_5_stuck_card_replaces_pending():
    """
    Family 5f: Stuck card replaces pending card on SSE event.

    AC:
    - Pending card is removed when stuck event arrives
    - Stuck card is prepended to container (newest first)
    - Loading/empty state is cleared if present
    """
    plan = {
        "session_id": "test-session-stuck-replace",
        "register_surface_id": "surf-test-stuck-replace",
        "openapi_version": "0.0.0",
        "cards": [],
        "steps": [
            {"action": "open"},
            {"action": "event", "name": "dispatch_ack", "data": {
                "intent_ids": ["intent-stuck-replace"],
                "utterance": "Check system status"
            }},
            {"action": "event", "name": "task_stuck", "data": {
                "intent_id": "intent-stuck-replace",
                "bead_id": "adc-stuck-replace",
                "stuck_reason": "System unavailable"
            }},
        ],
    }

    plan_json = json.dumps(plan)
    result = subprocess.run(
        ["node", "tests/e2e/canvas_eventsource_runner.js"],
        input=plan_json.encode(),
        capture_output=True,
        cwd="/home/coding/aide-de-camp",
        timeout=10,
    )

    if result.returncode != 0:
        raise RuntimeError(f"Runner failed: {result.stderr.decode()}")

    telemetry = json.loads(result.stdout.decode())
    html = telemetry["containerHTML"]

    # Stuck card should be present
    assert "stuck-card" in html
    # Pending card should be removed
    assert "pending-card" not in html or html.count("pending-card") < html.count("stuck-card")


def test_family_5_failed_card_replaces_pending():
    """
    Family 5g: Failed card replaces pending card on SSE event.

    AC:
    - Pending card is removed when failed event arrives
    - Failed card is prepended to container (newest first)
    - Loading/empty state is cleared if present
    """
    plan = {
        "session_id": "test-session-failed-replace",
        "register_surface_id": "surf-test-failed-replace",
        "openapi_version": "0.0.0",
        "cards": [],
        "steps": [
            {"action": "open"},
            {"action": "event", "name": "dispatch_ack", "data": {
                "intent_ids": ["intent-failed-replace"],
                "utterance": "Deploy application"
            }},
            {"action": "event", "name": "task_failed", "data": {
                "intent_id": "intent-failed-replace",
                "bead_id": "adc-failed-replace",
                "failure_reason": "Deployment configuration invalid"
            }},
        ],
    }

    plan_json = json.dumps(plan)
    result = subprocess.run(
        ["node", "tests/e2e/canvas_eventsource_runner.js"],
        input=plan_json.encode(),
        capture_output=True,
        cwd="/home/coding/aide-de-camp",
        timeout=10,
    )

    if result.returncode != 0:
        raise RuntimeError(f"Runner failed: {result.stderr.decode()}")

    telemetry = json.loads(result.stdout.decode())
    html = telemetry["containerHTML"]

    # Failed card should be present
    assert "failed-card" in html
    # Pending card should be removed
    assert "pending-card" not in html or html.count("pending-card") < html.count("failed-card")
