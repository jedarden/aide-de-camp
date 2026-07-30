"""
Headless DOM render-contract test for server-rendered component cards (bead adc-35eq).

``src/canvas/canvas.js`` exposes ``createComponentCard(renderedHtml, componentId, topic, staleness)``
— the function that renders hot-path renderer outcomes (HTML from
``src/render/hot_path.py``) into the canvas.

``tests/e2e/canvas_dom_runner.js`` loads that exact file under a minimal DOM shim
in ``--component`` mode and renders component cards headlessly; this test drives
it via ``tests/e2e/canvas_render.py`` → ``render_component_card()``.

The tests verify:
1. Component cards render with correct CSS classes (component-card, topic-card family)
2. Server-rendered HTML is injected as-is (already escaped at template-fill time)
3. Dataset attributes are set for querying (component_id, topic_id, topic_type)
4. Staleness indicators render correctly
5. Topic metadata (label, type) renders in the header

These tests ensure the hot-path renderer's HTML output streams to SSE and
injects into the canvas correctly (no blank canvas on a component match).
"""
import pytest

from tests.e2e.canvas_render import node_available, render_component_card, render_component_cards

pytestmark = pytest.mark.skipif(
    not node_available(), reason="node not on PATH — cannot drive canvas DOM runner"
)


# --- Test data fixtures -------------------------------------------------------


def _component_data(
    rendered_html: str = "<div>Custom component content</div>",
    component_id: str = "test-component-1",
    topic_id: str = "t-1",
    topic_label: str = "Pods",
    topic_type: str = "project",
    staleness_seconds: int = 5,
) -> dict:
    """Build component card data in the shape the hot-path renderer provides."""
    return {
        "rendered_html": rendered_html,
        "component_id": component_id,
        "topic": {
            "id": topic_id,
            "label": topic_label,
            "type": topic_type,
        },
        "staleness": {"seconds": staleness_seconds},
    }


# --- Component card rendering tests -------------------------------------------


class TestComponentCardRendering:
    """Test createComponentCard() render contract."""

    def test_component_card_has_correct_css_classes(self):
        """Component card has .topic-card and .component-card classes."""
        out = render_component_card(**_component_data())
        html = out["outerHTML"]
        assert "topic-card" in html
        assert "component-card" in html
        assert "component-card" in out["className"].split()
        assert "topic-card" in out["className"].split()

    def test_component_card_has_component_id_dataset(self):
        """Component card has data-component-id set from the component library."""
        data = _component_data(component_id="custom-component-abc")
        out = render_component_card(**data)
        assert out["dataset"].get("componentId") == "custom-component-abc"

    def test_component_card_has_topic_id_dataset(self):
        """Component card has data-topic-id from the topic."""
        data = _component_data(topic_id="t-xyz")
        out = render_component_card(**data)
        assert out["dataset"].get("topicId") == "t-xyz"

    def test_component_card_has_topic_type_dataset(self):
        """Component card has data-topic-type from the topic."""
        data = _component_data(topic_type="research")
        out = render_component_card(**data)
        assert out["dataset"].get("topicType") == "research"

    def test_component_card_injects_server_rendered_html(self):
        """Server-rendered HTML is injected as-is (already escaped by hot-path)."""
        custom_html = "<div class='custom-field'>Pods running: 3</div>"
        out = render_component_card(rendered_html=custom_html)
        html = out["outerHTML"]
        # The custom HTML should be present in the component-content div
        assert "custom-field" in html
        assert "Pods running: 3" in html

    def test_component_card_renders_topic_header(self):
        """Topic label and type badge render in the header."""
        out = render_component_card(
            rendered_html="<div>Content</div>",
            topic_label="Deployment Status",
            topic_type="action",
        )
        html = out["outerHTML"]
        assert "Deployment Status" in html
        assert "action" in html  # topic type badge

    def test_component_card_escapes_topic_label(self):
        """Topic label is escaped via escapeHtml()."""
        out = render_component_card(
            rendered_html="<div>Content</div>",
            topic_label="<script>alert(1)</script>",
        )
        html = out["outerHTML"]
        # Label should be escaped in the header
        assert "&lt;script&gt;" in html
        assert "alert(1)" in html  # Text preserved

    def test_component_card_shows_staleness_indicator(self):
        """Staleness indicator renders based on seconds."""
        # Fresh (under 10 minutes)
        out = render_component_card(
            rendered_html="<div>Content</div>",
            stal={"seconds": 60},
        )
        html = out["outerHTML"]
        assert "fresh" in out["className"].split()
        assert "Updated" in html or "ago" in html

    def test_component_card_shows_stale_badge(self):
        """Stale badge appears after threshold."""
        # Stale (over 10 minutes)
        out = render_component_card(
            rendered_html="<div>Content</div>",
            stal={"seconds": 900},  # 15 minutes
        )
        html = out["outerHTML"]
        assert "stale" in out["className"].split()
        assert "STALE" in html

    def test_component_card_with_empty_html(self):
        """Component card handles empty rendered HTML."""
        out = render_component_card(rendered_html="")
        # Should still render, just with empty component-content
        assert "topic-card" in out["className"]
        assert "component-card" in out["className"]


class TestComponentCardContentInjection:
    """Test server-rendered HTML injection contract."""

    def test_html_with_custom_structure(self):
        """Complex server-rendered structure is preserved."""
        custom_html = """
            <div class="status-grid">
                <div class="status-item">
                    <span class="label">Pods</span>
                    <span class="value">3</span>
                </div>
                <div class="status-item">
                    <span class="label">CPU</span>
                    <span class="value">45%</span>
                </div>
            </div>
        """
        out = render_component_card(rendered_html=custom_html)
        html = out["outerHTML"]
        assert "status-grid" in html
        assert "Pods" in html
        assert "3" in html
        assert "CPU" in html
        assert "45%" in html

    def test_html_with_escaped_content(self):
        """Server-rendered HTML is already escaped; we don't double-escape."""
        # The hot-path renderer already escaped dangerous content at template-fill time
        # (html.escape() in src/render/hot_path.py:fill_template)
        escaped_html = "&lt;script&gt;dangerous()&lt;/script&gt;"
        out = render_component_card(rendered_html=escaped_html)
        html = out["outerHTML"]
        # Should be injected as-is (not double-escaped)
        assert escaped_html in html

    def test_html_with_nested_structure(self):
        """Nested component structure renders correctly."""
        nested_html = """
            <div class="panel">
                <h3>Overview</h3>
                <ul>
                    <li>Item 1</li>
                    <li>Item 2</li>
                </ul>
            </div>
        """
        out = render_component_card(rendered_html=nested_html)
        html = out["outerHTML"]
        assert "panel" in html
        assert "Overview" in html
        assert "Item 1" in html
        assert "Item 2" in html


class TestMultipleComponentCards:
    """Test rendering multiple component cards (parallel dispatch)."""

    def test_multiple_component_cards_each_have_own_component_id(self):
        """Multiple component cards each have their own component_id."""
        cards = [
            _component_data(
                rendered_html="<div>Status A</div>",
                component_id="comp-a",
                topic_id="t-a",
            ),
            _component_data(
                rendered_html="<div>Status B</div>",
                component_id="comp-b",
                topic_id="t-b",
            ),
            _component_data(
                rendered_html="<div>Status C</div>",
                component_id="comp-c",
                topic_id="t-c",
            ),
        ]

        outs = render_component_cards(cards)
        assert len(outs) == 3

        component_ids = {o.get("dataset", {}).get("componentId") for o in outs}
        assert component_ids == {"comp-a", "comp-b", "comp-c"}

        topic_ids = {o.get("dataset", {}).get("topicId") for o in outs}
        assert topic_ids == {"t-a", "t-b", "t-c"}

    def test_multiple_component_cards_each_have_own_content(self):
        """Each component card renders its own HTML content."""
        cards = [
            _component_data(rendered_html="<div>Content A</div>"),
            _component_data(rendered_html="<div>Content B</div>"),
            _component_data(rendered_html="<div>Content C</div>"),
        ]

        outs = render_component_cards(cards)
        assert len(outs) == 3

        htmls = [o["outerHTML"] for o in outs]
        assert "Content A" in htmls[0]
        assert "Content B" in htmls[1]
        assert "Content C" in htmls[2]


# --- Contract sanity ----------------------------------------------------------


def test_dom_runner_targets_real_canvas_module():
    """Guard: the runner loads the actual src/canvas/canvas.js, not a stub."""
    from tests.e2e.canvas_render import CANVAS_JS

    assert CANVAS_JS.exists(), f"canvas.js missing at {CANVAS_JS}"
    content = CANVAS_JS.read_text()
    assert "createComponentCard" in content
