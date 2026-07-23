#!/usr/bin/env python3
"""
Headless tests for error card rendering from SSE error events.

Tests all five Degraded-State UX error card variants:
1. router_unavailable - ZAI proxy unreachable
2. all_sources_failed - Every fetch source failed
3. synthesis_failed - Summary unavailable (raw data present)
4. malformed_router_output - Couldn't parse router output
5. no_match - No matching project (with registered projects list)

Each test verifies:
- Error card is rendered from synthetic SSE error event
- Correct variant is applied via _normalizeVariant()
- All dynamic values are escaped (no raw HTML)
- Pending card is replaced when present
- Human-readable text is displayed
"""

import json
import subprocess
import pytest
from typing import Dict, Any


def run_eventsource_plan(plan: Dict[str, Any]) -> Dict[str, Any]:
    """
    Run the canvas_eventsource_runner.js with a test plan.

    Returns the telemetry JSON from the runner.
    """
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


def test_error_card_router_unavailable():
    """Test router_unavailable error card renders from SSE error event."""
    plan = {
        "session_id": "test-session",
        "register_surface_id": "surf-test",
        "openapi_version": "0.0.0",
        "cards": [],
        "steps": [
            {"action": "open"},
            {
                "action": "event",
                "name": "error",
                "data": {
                    "error_type": "router_unavailable",
                    "utterance": "What is the status of the cluster?",
                    "detail": "The LLM proxy (ZAI) was unreachable at the router stage.",
                    "intent_id": "intent-123",
                },
            },
        ],
    }

    telemetry = run_eventsource_plan(plan)

    # Verify error card is in container
    assert "error-card" in telemetry["containerHTML"]
    assert "error-router_unavailable" in telemetry["containerHTML"]

    # Verify escaped utterance is shown
    assert "You said:" in telemetry["containerHTML"]
    assert "What is the status of the cluster?" in telemetry["containerHTML"]

    # Verify icon and title
    assert "🔌" in telemetry["containerHTML"]
    assert "Router unavailable" in telemetry["containerHTML"]


def test_error_card_all_sources_failed():
    """Test all_sources_failed error card with per-source failure list."""
    plan = {
        "session_id": "test-session",
        "register_surface_id": "surf-test",
        "openapi_version": "0.0.0",
        "cards": [],
        "steps": [
            {"action": "open"},
            {
                "action": "event",
                "name": "error",
                "data": {
                    "error_type": "all_sources_failed",
                    "utterance": "Check the pipeline status",
                    "detail": "Every fetch source failed or timed out.",
                    "sources": [
                        {"name": "k8s-api", "reason": "timeout"},
                        {"name": "logs-api", "reason": "connection refused"},
                        {"name": "metrics-api", "reason": "503 Service Unavailable"},
                    ],
                    "intent_id": "intent-456",
                },
            },
        ],
    }

    telemetry = run_eventsource_plan(plan)

    # Verify error card variant
    assert "error-card" in telemetry["containerHTML"]
    assert "error-all_sources_failed" in telemetry["containerHTML"]

    # Verify per-source failure list is rendered
    assert "error-source-list" in telemetry["containerHTML"]
    assert "k8s-api" in telemetry["containerHTML"]
    assert "timeout" in telemetry["containerHTML"]
    assert "logs-api" in telemetry["containerHTML"]
    assert "connection refused" in telemetry["containerHTML"]
    assert "metrics-api" in telemetry["containerHTML"]

    # Verify icon and title
    assert "📭" in telemetry["containerHTML"]
    assert "No data available" in telemetry["containerHTML"]


def test_error_card_synthesis_failed():
    """Test synthesis_failed error card with degraded raw data."""
    plan = {
        "session_id": "test-session",
        "register_surface_id": "surf-test",
        "openapi_version": "0.0.0",
        "cards": [],
        "steps": [
            {"action": "open"},
            {
                "action": "event",
                "name": "error",
                "data": {
                    "error_type": "synthesis_failed",
                    "utterance": "Summarize the recent errors",
                    "detail": "The raw data was fetched, but the summary could not be produced.",
                    "data": {
                        "errors": [
                            {"time": "2025-01-10T10:00:00Z", "service": "api", "error": "timeout"},
                            {"time": "2025-01-10T10:05:00Z", "service": "db", "error": "connection reset"},
                        ]
                    },
                    "intent_id": "intent-789",
                },
            },
        ],
    }

    telemetry = run_eventsource_plan(plan)

    # Verify error card variant
    assert "error-card" in telemetry["containerHTML"]
    assert "error-synthesis_failed" in telemetry["containerHTML"]

    # Verify raw data is shown (fetched data is never discarded)
    assert "error-raw" in telemetry["containerHTML"]
    assert "Fetched data" in telemetry["containerHTML"]
    assert "errors" in telemetry["containerHTML"]

    # Verify icon and title
    assert "⚠️" in telemetry["containerHTML"]
    assert "Summary unavailable" in telemetry["containerHTML"]


def test_error_card_malformed_router_output():
    """Test malformed_router_output error card."""
    plan = {
        "session_id": "test-session",
        "register_surface_id": "surf-test",
        "openapi_version": "0.0.0",
        "cards": [],
        "steps": [
            {"action": "open"},
            {
                "action": "event",
                "name": "error",
                "data": {
                    "error_type": "malformed_router_output",
                    "utterance": "<script>alert('xss')</script> test",
                    "detail": "The router returned output the system could not interpret.",
                    "intent_id": "intent-abc",
                },
            },
        ],
    }

    telemetry = run_eventsource_plan(plan)

    # Verify error card variant
    assert "error-card" in telemetry["containerHTML"]
    assert "error-malformed_router_output" in telemetry["containerHTML"]

    # Verify utterance is escaped (no raw script tags)
    assert "<script>" not in telemetry["containerHTML"]
    assert "&lt;script&gt;" in telemetry["containerHTML"]

    # Verify button label for this variant
    assert "Edit &amp; resend" in telemetry["containerHTML"]

    # Verify icon and title
    assert "🧩" in telemetry["containerHTML"]
    assert "Couldn't parse that into intents" in telemetry["containerHTML"]


def test_error_card_no_match():
    """Test no_match error card with registered projects list."""
    plan = {
        "session_id": "test-session",
        "register_surface_id": "surf-test",
        "openapi_version": "0.0.0",
        "cards": [],
        "steps": [
            {"action": "open"},
            {
                "action": "event",
                "name": "error",
                "data": {
                    "error_type": "no_match",
                    "utterance": "Restart the foo-bar deployment",
                    "detail": "No registered project matched this request.",
                    "registered_projects": [
                        "options-pipeline",
                        "ibkr-mcp",
                        "cluster-monitor",
                    ],
                    "intent_id": "intent-def",
                },
            },
        ],
    }

    telemetry = run_eventsource_plan(plan)

    # Verify error card variant
    assert "error-card" in telemetry["containerHTML"]
    assert "error-no_match" in telemetry["containerHTML"]

    # Verify registered projects list is shown
    assert "error-project-list" in telemetry["containerHTML"]
    assert "options-pipeline" in telemetry["containerHTML"]
    assert "ibkr-mcp" in telemetry["containerHTML"]
    assert "cluster-monitor" in telemetry["containerHTML"]
    assert "Registered projects:" in telemetry["containerHTML"]

    # Verify button label for this variant
    assert "Edit &amp; resend" in telemetry["containerHTML"]

    # Verify icon and title
    assert "❓" in telemetry["containerHTML"]
    assert "No matching project" in telemetry["containerHTML"]


def test_error_card_replaces_pending_card():
    """Test that error card replaces associated pending card."""
    plan = {
        "session_id": "test-session",
        "register_surface_id": "surf-test",
        "openapi_version": "0.0.0",
        "cards": [],
        "steps": [
            {"action": "open"},
            # First, create a pending card via dispatch_ack
            {
                "action": "event",
                "name": "dispatch_ack",
                "data": {
                    "utterance_id": "utt-123",
                    "intent_ids": ["intent-pending-1"],
                    "utterance": "Check cluster status",
                },
            },
            # Then fire an error event for that intent_id
            {
                "action": "event",
                "name": "error",
                "data": {
                    "error_type": "router_unavailable",
                    "utterance": "Check cluster status",
                    "intent_id": "intent-pending-1",
                },
            },
        ],
    }

    telemetry = run_eventsource_plan(plan)

    # Verify error card is present
    assert "error-card" in telemetry["containerHTML"]

    # Verify pending card was removed (only one card should exist)
    # The pending card would have data-pending-kind="thread", which should be gone
    assert telemetry["containerHTML"].count('data-pending-kind="thread"') == 0

    # Verify error card has the intent_id association
    assert 'data-intent-id="intent-pending-1"' in telemetry["containerHTML"]


def test_error_card_unknown_error_type_defaults_to_no_match():
    """Test that unknown error_type defaults to no_match variant."""
    plan = {
        "session_id": "test-session",
        "register_surface_id": "surf-test",
        "openapi_version": "0.0.0",
        "cards": [],
        "steps": [
            {"action": "open"},
            {
                "action": "event",
                "name": "error",
                "data": {
                    "error_type": "unknown_error_xyz",
                    "utterance": "Something went wrong",
                    "intent_id": "intent-999",
                },
            },
        ],
    }

    telemetry = run_eventsource_plan(plan)

    # Should default to no_match variant
    assert "error-card" in telemetry["containerHTML"]
    assert "error-no_match" in telemetry["containerHTML"]
    assert "❓" in telemetry["containerHTML"]


def test_error_card_kebab_case_normalization():
    """Test that kebab-case error_type normalizes to snake_case variant."""
    plan = {
        "session_id": "test-session",
        "register_surface_id": "surf-test",
        "openapi_version": "0.0.0",
        "cards": [],
        "steps": [
            {"action": "open"},
            {
                "action": "event",
                "name": "error",
                "data": {
                    "error_type": "router-unavailable",  # kebab-case
                    "utterance": "Test kebab normalization",
                    "intent_id": "intent-kebab",
                },
            },
        ],
    }

    telemetry = run_eventsource_plan(plan)

    # Should normalize to router_unavailable
    assert "error-card" in telemetry["containerHTML"]
    assert "error-router_unavailable" in telemetry["containerHTML"]
    assert "🔌" in telemetry["containerHTML"]


def test_error_card_no_failure_mode_blanks():
    """Test that error cards never leave blank regions or raw JSON."""
    plan = {
        "session_id": "test-session",
        "register_surface_id": "surf-test",
        "openapi_version": "0.0.0",
        "cards": [],
        "steps": [
            {"action": "open"},
            {
                "action": "event",
                "name": "error",
                "data": {
                    "error_type": "router_unavailable",
                    "utterance": "Test for visible content",
                    "detail": "Should always show human-readable text",
                    "intent_id": "intent-visible",
                },
            },
        ],
    }

    telemetry = run_eventsource_plan(plan)

    html = telemetry["containerHTML"]

    # Should have human-readable content
    assert "Router unavailable" in html
    assert "You said:" in html
    assert "Test for visible content" in html

    # Should NOT have raw JSON or stack traces
    assert "{" not in html or "error_type" not in html  # No raw JSON object
    assert "stack trace" not in html.lower()
    assert "error_detail" not in html  # No raw field names

    # Should have retry button
    assert "error-retry" in html
    assert "Retry" in html


def test_multiple_error_cards_render():
    """Test that multiple error events render multiple error cards."""
    plan = {
        "session_id": "test-session",
        "register_surface_id": "surf-test",
        "openapi_version": "0.0.0",
        "cards": [],
        "steps": [
            {"action": "open"},
            {
                "action": "event",
                "name": "error",
                "data": {
                    "error_type": "router_unavailable",
                    "utterance": "First error",
                    "intent_id": "intent-1",
                },
            },
            {
                "action": "event",
                "name": "error",
                "data": {
                    "error_type": "all_sources_failed",
                    "utterance": "Second error",
                    "intent_id": "intent-2",
                },
            },
        ],
    }

    telemetry = run_eventsource_plan(plan)

    html = telemetry["containerHTML"]

    # Both error cards should be present
    assert "error-router_unavailable" in html
    assert "error-all_sources_failed" in html

    # Both utterances should be shown
    assert "First error" in html
    assert "Second error" in html

    # Should have two error cards total
    assert html.count('data-builtin="error"') == 2
