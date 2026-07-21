"""
Headless render-contract test for the production canvas module (bead adc-1l8w).

``src/canvas/canvas.js`` exposes ``createTopicCard(cardData)`` — the function
``loadTopics()`` (src/canvas/index.html) calls for every card returned by
``GET /api/v1/sessions/{id}/topics``. ``tests/e2e/canvas_dom_runner.js`` loads
that exact file under a minimal DOM shim and renders card JSON headlessly; its
docstring names this file as the consumer.

This test feeds it card dicts in the REAL ``TopicCard.to_dict()`` shape
(``{topic, latest_result, staleness}``) and asserts the rendered HTML, so a
regression in the render contract (label, staleness badge, urgency badge, HTML
escaping, topic-id dataset) is caught in CI with no browser. These are the
cards ``loadTopics()`` would hand to ``createTopicCard()`` after an SSE
``result_created`` event triggers a reload.
"""
import pytest

from tests.e2e.canvas_render import node_available, render_card, render_cards

pytestmark = pytest.mark.skipif(
    not node_available(), reason="node not on PATH — cannot drive canvas DOM runner"
)


# --- card-shape factory -------------------------------------------------------


def _staleness_level(seconds: int) -> str:
    """Mirror canvas.js getStalenessLevel() thresholds for the test fixtures."""
    if seconds < 600:
        return "fresh"
    if seconds < 3600:
        return "stale"
    return "very-stale"


def _card(
    label: str = "Pods",
    *,
    seconds: int = 5,
    summary: str | None = "3 pods running",
    urgency: str = "normal",
    data: dict | None = None,
    topic_type: str = "project",
    topic_id: str = "t-1",
    result_count: int = 1,
    latest_result: dict | None = ...,  # sentinel: build from summary/urgency
) -> dict:
    """Build a card dict in the exact TopicCard.to_dict() shape the canvas gets."""
    if latest_result is ... and summary is not None:
        latest_result = {"summary": summary, "urgency": urgency, "data": data}
    elif latest_result is ...:
        latest_result = None
    return {
        "topic": {
            "id": topic_id,
            "label": label,
            "type": topic_type,
            "project_slugs": [],
            "scope": "session",
            "session_id": "s-1",
            "created_at": 0,
            "last_active": 0,
            "archived_at": None,
            "result_count": result_count,
        },
        "staleness": {"seconds": seconds, "level": _staleness_level(seconds)},
        "latest_result": latest_result,
    }


# --- render contract ----------------------------------------------------------


class TestCardRendering:
    def test_card_with_result_renders_label_and_summary(self):
        out = render_card(_card(label="Pods", summary="3 running"))
        html = out["outerHTML"]
        assert "topic-card" in html  # the root class loadTopics() appends
        assert "fresh" in out["className"].split()  # fresh staleness class
        assert "Pods" in html  # label rendered
        assert "3 running" in html  # result summary rendered
        assert out["dataset"]["topicId"] == "t-1"  # data-topic-id dataset

    def test_card_without_result_still_renders(self):
        """A topic with no latest_result still renders its header + staleness."""
        out = render_card(_card(label="Empty", summary=None))
        html = out["outerHTML"]
        assert "Empty" in html
        assert "result-content" not in html  # no result block
        assert "staleness-indicator" in html  # staleness footer still present

    def test_label_is_html_escaped(self):
        """Labels are escaped via escapeHtml() — no raw markup injection."""
        out = render_card(_card(label="<script>alert(1)</script>", summary="ok"))
        html = out["outerHTML"]
        assert "<script>alert(1)</script>" not in html  # not rendered raw
        assert "&lt;script&gt;" in html  # escaped
        assert "alert(1)" in html  # visible text preserved

    def test_summary_is_html_escaped(self):
        out = render_card(_card(summary="<b>bold</b>"))
        assert "&lt;b&gt;" in out["outerHTML"]

    def test_topic_type_badge_reflects_type(self):
        out = render_card(_card(topic_type="research"))
        assert 'class="topic-type research"' in out["outerHTML"]


class TestStaleness:
    """getStalenessLevel() drives both the card class and the STALE badge."""

    def test_fresh_has_no_stale_badge(self):
        out = render_card(_card(seconds=60))
        assert "fresh" in out["className"].split()
        assert "STALE" not in out["outerHTML"]

    def test_stale_shows_badge(self):
        out = render_card(_card(seconds=900))  # 15 min -> stale
        assert "stale" in out["className"].split()
        assert "STALE" in out["outerHTML"]

    def test_very_stale_shows_badge(self):
        out = render_card(_card(seconds=7200))  # 2 h -> very-stale
        assert "very-stale" in out["className"].split()
        assert "STALE" in out["outerHTML"]


class TestUrgency:
    def test_urgency_badge_class_and_text(self):
        out = render_card(_card(summary="fire", urgency="critical"))
        html = out["outerHTML"]
        assert "urgency-badge critical" in html  # class reflects urgency
        assert "critical" in html  # badge text is the urgency value


class TestBatch:
    def test_multiple_cards_each_get_their_topic_id(self):
        cards = [
            _card(label="A", topic_id="t-a"),
            _card(label="B", topic_id="t-b"),
            _card(label="C", topic_id="t-c"),
        ]
        outs = render_cards(cards)
        assert len(outs) == 3
        assert {o["dataset"]["topicId"] for o in outs} == {"t-a", "t-b", "t-c"}
        # Every card renders its own label.
        assert "A" in outs[0]["outerHTML"]
        assert "B" in outs[1]["outerHTML"]
        assert "C" in outs[2]["outerHTML"]


# --- contract sanity ----------------------------------------------------------


def test_dom_runner_targets_real_canvas_module():
    """Guard: the runner loads the actual src/canvas/canvas.js, not a stub."""
    from tests.e2e.canvas_render import CANVAS_JS

    assert CANVAS_JS.exists(), f"canvas.js missing at {CANVAS_JS}"
    assert "createTopicCard" in CANVAS_JS.read_text()
