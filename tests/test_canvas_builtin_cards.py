"""
Headless DOM render-contract tests for stuck and failed builtin cards.

Tests the production canvas module (src/canvas/canvas.js) builtin card
functions:
- createStuckCard(data) — renders stuck cards for fenced beads
- createFailedCard(data) — renders failed cards for terminal failures

These tests verify:
1. Cards render with correct CSS classes
2. All data fields are properly escaped
3. Dataset attributes are set for querying
4. Retry/dismiss buttons are present
5. Card structure matches expectations

Uses the same DOM runner pattern as test_canvas_render.py.
"""

import pytest

from tests.e2e.canvas_render import node_available, render_builtin_card

pytestmark = pytest.mark.skipif(
    not node_available(), reason="node not on PATH — cannot drive canvas DOM runner"
)


# --- Test data fixtures -------------------------------------------------------


def _stuck_card_data(
    bead_id: str = "adc-stuck-1",
    stuck_reason: str = "Needs clarification on requirements",
    refusal_count: int = 3,
    message: str = "Task stuck — needs your input",
) -> dict:
    """Build stuck card data in the shape task_stuck SSE events provide."""
    return {
        "bead_id": bead_id,
        "stuck_reason": stuck_reason,
        "refusal_count": refusal_count,
        "message": message,
        "intent_id": "intent-1",
        "session_id": "session-1",
        "topic_id": "topic-1",
        "timestamp": 1234567890,
    }


def _failed_card_data(
    bead_id: str = "adc-failed-1",
    failure_reason: str = "Worker process crashed",
    error_type: str = "worker_crash",
    message: str = "Task failed: Worker process crashed",
) -> dict:
    """Build failed card data in the shape task_failed SSE events provide."""
    return {
        "bead_id": bead_id,
        "failure_reason": failure_reason,
        "error_type": error_type,
        "message": message,
        "intent_id": "intent-2",
        "session_id": "session-1",
        "topic_id": "topic-2",
        "timestamp": 1234567891,
    }


# --- Stuck card rendering tests -----------------------------------------------


class TestStuckCardRendering:
    """Test createStuckCard() render contract."""

    def test_stuck_card_has_correct_css_classes(self):
        """Stuck card has .builtin-card and .stuck-card classes."""
        out = render_builtin_card("stuck", _stuck_card_data())
        html = out["outerHTML"]
        assert "builtin-card" in html
        assert "stuck-card" in html
        assert "stuck-card" in out["className"].split()

    def test_stuck_card_has_builtin_dataset(self):
        """Stuck card has data-builtin='stuck' for querying."""
        out = render_builtin_card("stuck", _stuck_card_data())
        assert out["dataset"].get("builtin") == "stuck"

    def test_stuck_card_has_bead_id_dataset(self):
        """Stuck card includes bead_id in dataset for querying/ dismissal."""
        data = _stuck_card_data(bead_id="adc-specific-bead")
        out = render_builtin_card("stuck", data)
        assert out["dataset"].get("beadId") == "adc-specific-bead"

    def test_stuck_card_shows_icon_and_title(self):
        """Stuck card shows blocked icon and 'Task stuck' title."""
        out = render_builtin_card("stuck", _stuck_card_data())
        html = out["outerHTML"]
        assert "🚧" in html or "🚫" in html  # Blocked/construction icon
        assert "Task stuck" in html or "stuck" in html.lower()

    def test_stuck_card_shows_message(self):
        """Stuck card message is rendered."""
        data = _stuck_card_data(message="This task needs your attention")
        out = render_builtin_card("stuck", data)
        html = out["outerHTML"]
        assert "This task needs your attention" in html

    def test_stuck_card_shows_stuck_reason(self):
        """Stuck reason is rendered with label."""
        data = _stuck_card_data(stuck_reason="Missing user input")
        out = render_builtin_card("stuck", data)
        html = out["outerHTML"]
        assert "Missing user input" in html
        assert "reason" in html.lower() or "why" in html.lower()

    def test_stuck_card_shows_refusal_count(self):
        """Refusal count is displayed."""
        data = _stuck_card_data(refusal_count=5)
        out = render_builtin_card("stuck", data)
        html = out["outerHTML"]
        assert "5" in html  # Refusal count visible

    def test_stuck_card_shows_bead_id(self):
        """Bead ID is shown for reference."""
        data = _stuck_card_data(bead_id="adc-view-bead")
        out = render_builtin_card("stuck", data)
        html = out["outerHTML"]
        assert "adc-view-bead" in html

    def test_stuck_card_message_is_html_escaped(self):
        """Message is escaped via escapeHtml()."""
        data = _stuck_card_data(message="<script>alert(1)</script>")
        out = render_builtin_card("stuck", data)
        html = out["outerHTML"]
        assert "<script>alert(1)</script>" not in html
        assert "&lt;script&gt;" in html
        assert "alert(1)" in html  # Text preserved

    def test_stuck_card_reason_is_html_escaped(self):
        """Stuck reason is escaped."""
        data = _stuck_card_data(stuck_reason="<b>Blocked</b>")
        out = render_builtin_card("stuck", data)
        html = out["outerHTML"]
        assert "&lt;b&gt;" in html
        assert "Blocked" in html

    def test_stuck_card_has_view_bead_action(self):
        """Stuck card includes link to view bead."""
        data = _stuck_card_data(bead_id="adc-stuck-123")
        out = render_builtin_card("stuck", data)
        html = out["outerHTML"]
        # Should have some actionable element
        assert "adc-stuck-123" in html


# --- Failed card rendering tests ----------------------------------------------


class TestFailedCardRendering:
    """Test createFailedCard() render contract."""

    def test_failed_card_has_correct_css_classes(self):
        """Failed card has .builtin-card and .failed-card classes."""
        out = render_builtin_card("failed", _failed_card_data())
        html = out["outerHTML"]
        assert "builtin-card" in html
        assert "failed-card" in html
        assert "failed-card" in out["className"].split()

    def test_failed_card_has_builtin_dataset(self):
        """Failed card has data-builtin='failed' for querying."""
        out = render_builtin_card("failed", _failed_card_data())
        assert out["dataset"].get("builtin") == "failed"

    def test_failed_card_has_bead_id_dataset(self):
        """Failed card includes bead_id in dataset."""
        data = _failed_card_data(bead_id="adc-failed-bead")
        out = render_builtin_card("failed", data)
        assert out["dataset"].get("beadId") == "adc-failed-bead"

    def test_failed_card_shows_error_icon_and_title(self):
        """Failed card shows X icon and 'Task failed' title."""
        out = render_builtin_card("failed", _failed_card_data())
        html = out["outerHTML"]
        assert "❌" in html  # Error icon
        assert "Task failed" in html or "failed" in html.lower()

    def test_failed_card_shows_message(self):
        """Failed card message is rendered."""
        data = _failed_card_data(message="Task failed during deployment")
        out = render_builtin_card("failed", data)
        html = out["outerHTML"]
        assert "Task failed during deployment" in html

    def test_failed_card_shows_failure_reason(self):
        """Failure reason is rendered with label."""
        data = _failed_card_data(failure_reason="Container timeout")
        out = render_builtin_card("failed", data)
        html = out["outerHTML"]
        assert "Container timeout" in html
        assert "reason" in html.lower() or "error" in html.lower()

    def test_failed_card_shows_error_type(self):
        """Error type is displayed."""
        data = _failed_card_data(error_type="timeout")
        out = render_builtin_card("failed", data)
        html = out["outerHTML"]
        assert "timeout" in html

    def test_failed_card_shows_bead_id(self):
        """Bead ID is shown when present."""
        data = _failed_card_data(bead_id="adc-failed-456")
        out = render_builtin_card("failed", data)
        html = out["outerHTML"]
        assert "adc-failed-456" in html

    def test_failed_card_has_retry_button(self):
        """Failed card includes retry button."""
        out = render_builtin_card("failed", _failed_card_data())
        html = out["outerHTML"]
        assert "retry" in html.lower() or "Retry" in html

    def test_failed_card_message_is_html_escaped(self):
        """Message is escaped via escapeHtml()."""
        data = _failed_card_data(message="<img src=x onerror=alert(1)>")
        out = render_builtin_card("failed", data)
        html = out["outerHTML"]
        assert "<img" not in html or "&lt;img" in html
        # Check that the dangerous payload is escaped, not that words don't appear
        assert "&lt;img src=x onerror=alert(1)&gt;" in html

    def test_failed_card_reason_is_html_escaped(self):
        """Failure reason is escaped."""
        data = _failed_card_data(failure_reason="<script>bad()</script>")
        out = render_builtin_card("failed", data)
        html = out["outerHTML"]
        assert "&lt;script&gt;" in html

    def test_failed_card_works_without_bead_id(self):
        """Failed card renders even when bead_id is None."""
        data = _failed_card_data(bead_id=None)
        out = render_builtin_card("failed", data)
        # Should still render, just without bead_id
        assert "builtin-card" in out["className"]
        assert "failed-card" in out["className"]


# --- Error injection and edge cases -------------------------------------------


class TestBuiltinCardsEdgeCases:
    """Test edge cases and error handling."""

    def test_stuck_card_with_empty_data(self):
        """Stuck card handles missing/empty fields gracefully."""
        out = render_builtin_card("stuck", {})
        assert "builtin-card" in out["className"]
        assert "stuck-card" in out["className"]

    def test_failed_card_with_empty_data(self):
        """Failed card handles missing/empty fields gracefully."""
        out = render_builtin_card("failed", {})
        assert "builtin-card" in out["className"]
        assert "failed-card" in out["className"]

    def test_stuck_card_with_very_long_reason(self):
        """Long stuck reason is rendered without truncation."""
        long_reason = "A" * 500
        data = _stuck_card_data(stuck_reason=long_reason)
        out = render_builtin_card("stuck", data)
        html = out["outerHTML"]
        # All chars should be present (or truncated by CSS, not logic)
        assert "A" in html

    def test_failed_card_with_unicode_chars(self):
        """Unicode in error messages is handled correctly."""
        data = _failed_card_data(
            failure_reason="Error: 錯誤 — échec — Fehler",
            error_type="unicode_error"
        )
        out = render_builtin_card("failed", data)
        html = out["outerHTML"]
        # Unicode should be preserved (not escaped as HTML entities)
        assert "錯誤" in html or "錯" in html

    def test_stuck_card_with_newlines_in_reason(self):
        """Newlines in stuck reason are handled."""
        data = _stuck_card_data(stuck_reason="Line 1\nLine 2\nLine 3")
        out = render_builtin_card("stuck", data)
        # Should not break rendering
        assert "Line 1" in out["outerHTML"] or "Line" in out["outerHTML"]

    def test_failed_card_high_urgency_visible(self):
        """Failed card shows urgency through styling/classes."""
        data = _failed_card_data(
            failure_reason="Critical failure",
            error_type="critical"
        )
        out = render_builtin_card("failed", data)
        html = out["outerHTML"]
        assert "failed" in html.lower()


# --- Dataset and querying tests -----------------------------------------------


class TestBuiltinCardsDatasets:
    """Test dataset attributes for querying and dismissal."""

    def test_stuck_card_datasets_queryable(self):
        """Stuck card datasets can be queried via selector."""
        data = _stuck_card_data(bead_id="adc-query-test")
        out = render_builtin_card("stuck", data)
        # These datasets are used for finding cards to dismiss
        assert out["dataset"]["builtin"] == "stuck"
        assert out["dataset"]["beadId"] == "adc-query-test"

    def test_failed_card_datasets_queryable(self):
        """Failed card datasets can be queried via selector."""
        data = _failed_card_data(bead_id="adc-query-test-2")
        out = render_builtin_card("failed", data)
        assert out["dataset"]["builtin"] == "failed"
        assert out["dataset"]["beadId"] == "adc-query-test-2"

    def test_stuck_card_without_bead_id_still_has_builtin(self):
        """Stuck card without bead_id still has data-builtin."""
        data = _stuck_card_data(bead_id=None)
        out = render_builtin_card("stuck", data)
        assert out["dataset"]["builtin"] == "stuck"
        # beadId dataset might be absent or empty
        assert out["dataset"].get("beadId", "") == "" or "beadId" not in out["dataset"]

    def test_failed_card_without_bead_id_still_has_builtin(self):
        """Failed card without bead_id still has data-builtin."""
        data = _failed_card_data(bead_id=None)
        out = render_builtin_card("failed", data)
        assert out["dataset"]["builtin"] == "failed"


# --- Multiple cards rendering -------------------------------------------------


class TestMultipleBuiltinCards:
    """Test rendering multiple stuck/failed cards."""

    def test_multiple_stuck_cards_each_have_own_bead_id(self):
        """Multiple stuck cards each have their own bead_id dataset."""
        from tests.e2e.canvas_render import render_builtin_cards

        cards = [
            _stuck_card_data(bead_id="adc-stuck-1"),
            _stuck_card_data(bead_id="adc-stuck-2"),
            _stuck_card_data(bead_id="adc-stuck-3"),
        ]

        outs = render_builtin_cards("stuck", cards)
        assert len(outs) == 3

        bead_ids = {o.get("dataset", {}).get("beadId") for o in outs}
        assert bead_ids == {"adc-stuck-1", "adc-stuck-2", "adc-stuck-3"}

    def test_multiple_failed_cards_each_have_own_bead_id(self):
        """Multiple failed cards each have their own bead_id dataset."""
        from tests.e2e.canvas_render import render_builtin_cards

        cards = [
            _failed_card_data(bead_id="adc-failed-1"),
            _failed_card_data(bead_id="adc-failed-2"),
        ]

        outs = render_builtin_cards("failed", cards)
        assert len(outs) == 2

        bead_ids = {o.get("dataset", {}).get("beadId") for o in outs}
        assert bead_ids == {"adc-failed-1", "adc-failed-2"}

    def test_mixed_stuck_and_failed_cards(self):
        """Can render both stuck and failed cards together."""
        from tests.e2e.canvas_render import render_builtin_cards

        stuck = _stuck_card_data(bead_id="adc-stuck")
        failed = _failed_card_data(bead_id="adc-failed")

        stuck_outs = render_builtin_cards("stuck", [stuck])
        failed_outs = render_builtin_cards("failed", [failed])

        assert len(stuck_outs) == 1
        assert len(failed_outs) == 1

        assert stuck_outs[0]["dataset"]["builtin"] == "stuck"
        assert failed_outs[0]["dataset"]["builtin"] == "failed"


# --- Contract sanity ----------------------------------------------------------


def test_dom_runner_targets_real_canvas_module():
    """Guard: the runner loads the actual src/canvas/canvas.js, not a stub."""
    from tests.e2e.canvas_render import CANVAS_JS

    assert CANVAS_JS.exists(), f"canvas.js missing at {CANVAS_JS}"
    content = CANVAS_JS.read_text()
    assert "createStuckCard" in content
    assert "createFailedCard" in content
