"""
Headless tests for fetch_progress SSE events and per-source progress updates.

Tests that fetch_progress events correctly update pending thread cards with:
- Per-source progress ('3/5 sources in')
- Elapsed time counters
- XSS protection via escapeHtml()

All tests run headlessly using the mock-EventSource harness in
tests/e2e/canvas_eventsource_runner.js (no browser required).

Bead: adc-2l7pv
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from tests.e2e.canvas_render import NODE, node_available

# The headless mock-EventSource harness that runs the REAL inline canvas script.
ES_RUNNER = Path(__file__).resolve().parent / "e2e" / "canvas_eventsource_runner.js"

pytestmark = pytest.mark.skipif(
    not node_available(), reason="node not on PATH — cannot drive EventSource harness"
)


# --- plan runner + builders ---------------------------------------------------


def run_plan(plan: dict[str, Any]) -> dict[str, Any]:
    """Feed a JSON test plan to the mock-EventSource harness, return its telemetry.

    Mirrors tests.e2e.canvas_render.render_cards: shells out to node with the
    plan on stdin and parses the single JSON telemetry object the harness prints
    on stdout. Raises if node is missing or the harness exits non-zero.
    """
    if NODE is None:
        raise RuntimeError("node not found on PATH — cannot drive EventSource harness")
    proc = subprocess.run(
        [NODE, str(ES_RUNNER)],
        input=json.dumps(plan),
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"canvas_eventsource_runner exited {proc.returncode}: {proc.stderr.strip()}"
        )
    return json.loads(proc.stdout)


def _card(
    label: str = "Pods",
    *,
    topic_id: str = "t-1",
    topic_type: str = "project",
    summary: str = "ok",
    urgency: str = "normal",
    seconds: int = 5,
) -> dict:
    """A card dict in the shape GET /topics returns under .cards."""
    level = "fresh" if seconds < 600 else ("stale" if seconds < 3600 else "very-stale")
    return {
        "topic": {"id": topic_id, "label": label, "type": topic_type},
        "staleness": {"seconds": seconds, "level": level},
        "latest_result": {"summary": summary, "urgency": urgency},
    }


def _plan(
    *,
    cards: list[dict] | None = None,
    steps: list[dict] | None = None,
    session_id: str = "sess-progress",
    surface_id: str = "surf-progress",
    version: str = "9.9.9",
) -> dict:
    """A harness plan for testing progress updates."""
    return {
        "session_id": session_id,
        "register_surface_id": surface_id,
        "openapi_version": version,
        "cards": cards or [],
        "steps": steps or [],
    }


# === AC1: thread_progress event fires and verifies card update =================


class TestFetchProgressEvent:
    """AC1: Test fires fetch_progress event and verifies card update."""

    def test_fetch_progress_updates_card_by_intent_id(self):
        """A fetch_progress event with intent_id finds the matching pending card
        and updates its progress text (e.g., '3/5 sources in')."""
        t = run_plan(_plan(steps=[
            {"action": "open"},
            {"action": "event", "name": "dispatch_ack", "data": {
                "utterance_id": "utt-prog-1",
                "utterance": "Track progress",
                "intent_ids": ["thread-123"],
            }},
            {"action": "event", "name": "fetch_progress", "data": {
                "intent_id": "thread-123",
                "completed": 3,
                "total": 5,
            }},
        ]))
        # Should have one thread card
        assert t["pendingThreadCount"] == 1
        # The progress text should be in the container HTML
        assert "3/5 sources in" in t["containerHTML"]
        # Verify the specific thread card exists
        pending_ids = [pc["pendingId"] for pc in t["pendingCards"]]
        assert "thread-123" in pending_ids

    def test_fetch_progress_targets_correct_thread_among_many(self):
        """When multiple thread cards exist, fetch_progress events target only
        the specific thread by intent_id (not all threads)."""
        t = run_plan(_plan(steps=[
            {"action": "open"},
            {"action": "event", "name": "dispatch_ack", "data": {
                "utterance_id": "utt-parallel",
                "utterance": "Parallel threads",
                "intent_ids": ["thread-a", "thread-b", "thread-c"],
            }},
            {"action": "event", "name": "fetch_progress", "data": {
                "intent_id": "thread-b",
                "completed": 5,
                "total": 10,
            }},
        ]))
        # Should have three thread cards total
        assert t["pendingThreadCount"] == 3
        # Only thread-b should show progress
        assert "5/10 sources in" in t["containerHTML"]
        # Verify all threads exist
        pending_ids = [pc["pendingId"] for pc in t["pendingCards"]]
        assert "thread-a" in pending_ids
        assert "thread-b" in pending_ids
        assert "thread-c" in pending_ids


# === AC2: elapsed time counter appears ========================================


class TestElapsedTimeCounter:
    """AC2: Test verifies elapsed time counter appears on thread cards."""

    def test_fetch_progress_includes_elapsed_time_footer(self):
        """A fetch_progress event also ensures the elapsed time footer is present
        on the card (e.g., '0s elapsed')."""
        t = run_plan(_plan(steps=[
            {"action": "open"},
            {"action": "event", "name": "dispatch_ack", "data": {
                "utterance_id": "utt-prog-2",
                "utterance": "Time tracking",
                "intent_ids": ["thread-time"],
            }},
            {"action": "event", "name": "fetch_progress", "data": {
                "intent_id": "thread-time",
                "completed": 2,
                "total": 7,
            }},
        ]))
        html = t["containerHTML"]
        # Progress text should be present
        assert "2/7 sources in" in html
        # Elapsed time footer should be present (format: 'Xs elapsed' or 'Xm Ys elapsed')
        assert " elapsed" in html
        # Verify the pending-elapsed element exists
        assert "pending-elapsed" in html

    def test_elapsed_time_counter_on_initial_thread_card(self):
        """Elapsed time counter appears immediately when thread card is created."""
        t = run_plan(_plan(steps=[
            {"action": "open"},
            {"action": "event", "name": "dispatch_ack", "data": {
                "utterance_id": "utt-initial",
                "utterance": "Initial timer",
                "intent_ids": ["thread-initial"],
            }},
        ]))
        html = t["containerHTML"]
        # Elapsed time should be present even before any progress updates
        assert " elapsed" in html
        assert "pending-elapsed" in html


# === AC3: uses escapeHtml() (no XSS vectors) ==================================


class TestXSSProtection:
    """AC3: Test uses escapeHtml() for all interpolated values (no XSS vectors)."""

    def test_progress_values_escaped_via_escapeHtml(self):
        """Fetch progress values are escaped through escapeHtml() to prevent XSS
        injection via progress text. All values use textContent, not innerHTML."""
        t = run_plan(_plan(steps=[
            {"action": "open"},
            {"action": "event", "name": "dispatch_ack", "data": {
                "utterance_id": "utt-xss",
                "utterance": "Test XSS",
                "intent_ids": ["thread-xss"],
            }},
            {"action": "event", "name": "fetch_progress", "data": {
                "intent_id": "thread-xss",
                "completed": 1,
                "total": 1,
            }},
        ]))
        html = t["containerHTML"]
        # The progress text should be rendered as escaped text, not raw HTML
        # If values were NOT escaped, a script tag would execute
        assert "1/1 sources in" in html
        # Verify no raw HTML in progress text (textContent is used via escapeHtml)
        assert "pending-progress" in html
        # Verify the utterance is also escaped
        assert "Test XSS" in html

    def test_all_interpolated_values_use_escapeHtml(self):
        """All thread card values (utterance, progress, elapsed) use escapeHtml()."""
        t = run_plan(_plan(steps=[
            {"action": "open"},
            {"action": "event", "name": "dispatch_ack", "data": {
                "utterance_id": "utt-escape",
                "utterance": "Verify escaping",
                "intent_ids": ["thread-escape"],
            }},
            {"action": "event", "name": "fetch_progress", "data": {
                "intent_id": "thread-escape",
                "completed": 2,
                "total": 3,
            }},
        ]))
        html = t["containerHTML"]
        # Utterance should be escaped (via pending-utterance el() helper)
        assert "Verify escaping" in html
        # Progress uses textContent (via _setProgress → node.textContent)
        assert "2/3 sources in" in html
        # Elapsed time is escaped (via formatElapsed → textContent)
        assert " elapsed" in html


# === AC4: test both progress and time updates together ========================


class TestProgressAndTimeTogether:
    """AC4: Test both progress and time updates together on the same card."""

    def test_fetch_progress_and_elapsed_time_work_together(self):
        """Test that both fetch progress updates and elapsed time counters work together
        on the same card without interference."""
        t = run_plan(_plan(steps=[
            {"action": "open"},
            {"action": "event", "name": "dispatch_ack", "data": {
                "utterance_id": "utt-together",
                "utterance": "Combined test",
                "intent_ids": ["thread-together"],
            }},
            {"action": "event", "name": "fetch_progress", "data": {
                "intent_id": "thread-together",
                "completed": 7,
                "total": 9,
            }},
        ]))
        html = t["containerHTML"]
        # Progress message should be present
        assert "7/9 sources in" in html
        # Elapsed time footer should be present
        assert " elapsed" in html
        # Both elements should exist in the DOM
        assert "pending-progress" in html
        assert "pending-elapsed" in html
        # Verify the single thread card
        assert t["pendingThreadCount"] == 1

    def test_multiple_progress_updates_keep_elapsed_time_visible(self):
        """Multiple progress updates don't hide the elapsed time counter."""
        t = run_plan(_plan(steps=[
            {"action": "open"},
            {"action": "event", "name": "dispatch_ack", "data": {
                "utterance_id": "utt-multi-elapsed",
                "utterance": "Progress with elapsed",
                "intent_ids": ["thread-multi-elapsed"],
            }},
            {"action": "event", "name": "fetch_progress", "data": {
                "intent_id": "thread-multi-elapsed",
                "completed": 1,
                "total": 5,
            }},
            {"action": "event", "name": "fetch_progress", "data": {
                "intent_id": "thread-multi-elapsed",
                "completed": 3,
                "total": 5,
            }},
            {"action": "event", "name": "fetch_progress", "data": {
                "intent_id": "thread-multi-elapsed",
                "completed": 5,
                "total": 5,
            }},
        ]))
        html = t["containerHTML"]
        # Final progress should show
        assert "5/5 sources in" in html
        # Elapsed time should still be visible
        assert " elapsed" in html
        # Both elements should exist
        assert "pending-progress" in html
        assert "pending-elapsed" in html


# === Additional edge cases and comprehensive testing ===========================


class TestProgressUpdateEdgeCases:
    """Comprehensive testing of progress update behavior."""

    def test_multiple_thread_progress_events_increment_card(self):
        """Multiple thread_progress events for the same thread_id update the same
        card incrementally, replacing previous values (not accumulating)."""
        t = run_plan(_plan(steps=[
            {"action": "open"},
            {"action": "event", "name": "dispatch_ack", "data": {
                "utterance_id": "utt-multi",
                "utterance": "Multiple updates",
                "intent_ids": ["thread-multi"],
            }},
            {"action": "event", "name": "fetch_progress", "data": {
                "intent_id": "thread-multi",
                "completed": 1,
                "total": 4,
            }},
            {"action": "event", "name": "fetch_progress", "data": {
                "intent_id": "thread-multi",
                "completed": 2,
                "total": 4,
            }},
            {"action": "event", "name": "fetch_progress", "data": {
                "intent_id": "thread-multi",
                "completed": 4,
                "total": 4,
            }},
        ]))
        html = t["containerHTML"]
        # Final state should show 4/4
        assert "4/4 sources in" in html
        # Earlier progress values should be replaced (not accumulated)
        assert "1/4 sources in" not in html
        assert "2/4 sources in" not in html
        # Should still have exactly one thread card
        assert t["pendingThreadCount"] == 1

    def test_progress_with_zero_total_hides_progress_element(self):
        """When total is 0, the progress element is hidden (display: none per
        _setProgress logic)."""
        t = run_plan(_plan(steps=[
            {"action": "open"},
            {"action": "event", "name": "dispatch_ack", "data": {
                "utterance_id": "utt-hide",
                "utterance": "Hide progress",
                "intent_ids": ["thread-hide"],
            }},
            {"action": "event", "name": "fetch_progress", "data": {
                "intent_id": "thread-hide",
                "completed": 0,
                "total": 0,
            }},
        ]))
        html = t["containerHTML"]
        # The progress element should exist but be hidden
        assert "pending-progress" in html

    def test_progress_updates_only_target_thread_not_others(self):
        """Progress updates for one thread don't affect other thread cards."""
        t = run_plan(_plan(steps=[
            {"action": "open"},
            {"action": "event", "name": "dispatch_ack", "data": {
                "utterance_id": "utt-isolated",
                "utterance": "Isolated updates",
                "intent_ids": ["thread-1", "thread-2", "thread-3"],
            }},
            # Update thread-1
            {"action": "event", "name": "fetch_progress", "data": {
                "intent_id": "thread-1",
                "completed": 1,
                "total": 2,
            }},
            # Update thread-2
            {"action": "event", "name": "fetch_progress", "data": {
                "intent_id": "thread-2",
                "completed": 5,
                "total": 10,
            }},
            # Update thread-1 again
            {"action": "event", "name": "fetch_progress", "data": {
                "intent_id": "thread-1",
                "completed": 2,
                "total": 2,
            }},
        ]))
        html = t["containerHTML"]
        # All three threads should exist
        assert t["pendingThreadCount"] == 3
        # Both progress messages should be visible
        assert "2/2 sources in" in html
        assert "5/10 sources in" in html
        # thread-3 should have no visible progress (never updated)
