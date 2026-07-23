"""
DOM verification for stuck and failed builtin cards (bead adc-1a551).

Companion to tests/test_canvas_builtin_cards.py (the render-contract test). Where
that file asserts the rendered HTML string, this file queries the rendered DOM
the way a browser test would — by selector — and verifies the visual structure,
styling classes, and DOM elements a canvas consumer relies on.

This runs **headlessly and hermetically** — no browser, no live server. It drives
the REAL production canvas module (src/canvas/canvas.js) through the Node DOM
runner (tests/e2e/canvas_dom_runner.js) and queries the emitted outerHTML with
a tiny stdlib-only DOM parser.
"""

from __future__ import annotations

from html.parser import HTMLParser

import pytest

from tests.e2e.canvas_render import node_available, render_builtin_card

pytestmark = pytest.mark.skipif(
    not node_available(), reason="node not on PATH — cannot drive canvas DOM runner"
)


# --- minimal selector-style DOM query over stdlib html.parser ------------------

class _Node:
    """One element node in the parsed tree."""

    __slots__ = ("tag", "attrs", "classes", "children", "text_parts")

    def __init__(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.tag = tag
        self.attrs = {k: (v if v is not None else "") for k, v in attrs}
        cls = self.attrs.get("class", "")
        self.classes = set(cls.split()) if cls else set()
        self.children: list[_Node] = []
        self.text_parts: list[str] = []

    def _walk(self):
        for child in self.children:
            yield child
            yield from child._walk()

    def find_all(self, *, tag: str | None = None, class_: str | None = None,
                 attrs: dict[str, str] | None = None) -> list["_Node"]:
        """All descendants matching tag / class / exact attribute values."""
        out: list[_Node] = []
        for node in self._walk():
            if tag is not None and node.tag != tag:
                continue
            if class_ is not None and class_ not in node.classes:
                continue
            if attrs and any(node.attrs.get(k) != v for k, v in attrs.items()):
                continue
            out.append(node)
        return out

    def find(self, **kw) -> "_Node | None":
        matches = self.find_all(**kw)
        return matches[0] if matches else None

    def has_class(self, class_: str) -> bool:
        return class_ in self.classes

    @property
    def text(self) -> str:
        """Own text plus all descendant text, whitespace-collapsed."""
        parts = list(self.text_parts)
        for node in self._walk():
            parts.extend(node.text_parts)
        return " ".join(p for p in parts if p).strip()


# Void elements never push onto the open-element stack.
_VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input",
         "link", "meta", "param", "source", "track", "wbr"}


class _TreeBuilder(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = _Node("__root__", [])
        self._stack: list[_Node] = [self.root]

    def handle_starttag(self, tag, attrs):
        node = _Node(tag, attrs)
        self._stack[-1].children.append(node)
        if tag not in _VOID:
            self._stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self._stack[-1].children.append(_Node(tag, attrs))

    def handle_endtag(self, tag):
        for i in range(len(self._stack) - 1, 0, -1):
            if self._stack[i].tag == tag:
                del self._stack[i:]
                break

    def handle_data(self, data):
        s = data.strip()
        if s:
            self._stack[-1].text_parts.append(s)


def parse_card(card_out: dict) -> _Node:
    """Parse one render_builtin_card output dict into a query tree."""
    root = _TreeBuilder()
    root.feed(card_out["outerHTML"])
    root.close()
    # The card root is the first real element under the synthetic root.
    assert root.root.children, "rendered card had no root element"
    return root.root.children[0]


def render(card_type: str, data: dict) -> _Node:
    """Render a builtin card through canvas.js and parse it for querying."""
    return parse_card(render_builtin_card(card_type, data))


# --- Card data fixtures --------------------------------------------------------


def _stuck_data(
    bead_id: str = "adc-stuck-1",
    stuck_reason: str = "Needs clarification on requirements",
    refusal_count: int = 3,
    message: str = "Task stuck — needs your input",
    action_hint: str = "Please provide more details",
) -> dict:
    """Build stuck card data matching the SSE event shape."""
    return {
        "bead_id": bead_id,
        "stuck_reason": stuck_reason,
        "refusal_count": refusal_count,
        "message": message,
        "action_hint": action_hint,
        "intent_id": "intent-1",
        "session_id": "session-1",
        "topic_id": "topic-1",
        "timestamp": 1234567890,
    }


def _failed_data(
    bead_id: str = "adc-failed-1",
    failure_reason: str = "Worker process crashed",
    error_type: str = "worker_crash",
    message: str = "Task failed: Worker process crashed",
) -> dict:
    """Build failed card data matching the SSE event shape."""
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


# === Stuck card DOM structure ===================================================


class TestStuckCardDOMStructure:
    """Verify stuck card DOM elements and structure."""

    def test_stuck_card_root_is_builtin_card(self):
        """Root element has .builtin-card class."""
        node = render("stuck", _stuck_data())
        assert node.has_class("builtin-card")

    def test_stuck_card_has_stuck_card_class(self):
        """Stuck card has .stuck-card class for type-specific styling."""
        node = render("stuck", _stuck_data())
        assert node.has_class("stuck-card")

    def test_stuck_card_has_builtin_header(self):
        """Stuck card has a header element with icon and title."""
        node = render("stuck", _stuck_data())
        header = node.find(class_="builtin-header")
        assert header is not None

    def test_stuck_card_has_icon_element(self):
        """Stuck card has icon element with construction emoji."""
        node = render("stuck", _stuck_data())
        icon = node.find(class_="builtin-icon")
        assert icon is not None
        assert "🚧" in icon.text

    def test_stuck_card_has_title_element(self):
        """Stuck card has title element with 'Task stuck' text."""
        node = render("stuck", _stuck_data())
        title = node.find(class_="builtin-title")
        assert title is not None
        assert "Task stuck" in title.text

    def test_stuck_card_has_message_when_provided(self):
        """Stuck card renders message element when message is provided."""
        data = _stuck_data(message="This task needs your attention")
        node = render("stuck", data)
        message = node.find(class_="stuck-message")
        assert message is not None
        assert "This task needs your attention" in message.text

    def test_stuck_card_has_reason_wrap(self):
        """Stuck card has reason wrapper with label and content."""
        data = _stuck_data(stuck_reason="Missing user input")
        node = render("stuck", data)
        reason_wrap = node.find(class_="stuck-reason-wrap")
        assert reason_wrap is not None

    def test_stuck_card_has_reason_label(self):
        """Stuck card has 'Reason:' label."""
        data = _stuck_data(stuck_reason="Needs clarification")
        node = render("stuck", data)
        label = node.find(class_="stuck-reason-label")
        assert label is not None
        assert "Reason" in label.text

    def test_stuck_card_has_reason_content(self):
        """Stuck card renders the actual reason text."""
        data = _stuck_data(stuck_reason="Needs clarification")
        node = render("stuck", data)
        reason = node.find(class_="stuck-reason")
        assert reason is not None
        assert "Needs clarification" in reason.text

    def test_stuck_card_has_meta_section(self):
        """Stuck card has meta section for refusal count and bead ID."""
        data = _stuck_data(refusal_count=3, bead_id="adc-123")
        node = render("stuck", data)
        meta = node.find(class_="stuck-meta")
        assert meta is not None

    def test_stuck_card_has_refusal_count(self):
        """Stuck card shows refusal count in meta section."""
        data = _stuck_data(refusal_count=5)
        node = render("stuck", data)
        count = node.find(class_="stuck-refusal-count")
        assert count is not None
        assert "Refusals:" in count.text
        assert "5" in count.text

    def test_stuck_card_has_bead_id_in_meta(self):
        """Stuck card shows bead ID in meta section."""
        data = _stuck_data(bead_id="adc-bead-xyz")
        node = render("stuck", data)
        bead_elem = node.find(class_="stuck-bead-id")
        assert bead_elem is not None
        assert "adc-bead-xyz" in bead_elem.text

    def test_stuck_card_has_action_hint_when_provided(self):
        """Stuck card renders action hint when provided."""
        data = _stuck_data(action_hint="Please provide more details")
        node = render("stuck", data)
        hint = node.find(class_="stuck-action-hint")
        assert hint is not None
        assert "Please provide more details" in hint.text

    def test_stuck_card_has_view_bead_button(self):
        """Stuck card has a 'View bead' button element."""
        node = render("stuck", _stuck_data())
        button = node.find(class_="stuck-view-bead")
        assert button is not None
        assert button.tag == "button"
        assert "View bead" in button.text


# === Failed card DOM structure ==================================================


class TestFailedCardDOMStructure:
    """Verify failed card DOM elements and structure."""

    def test_failed_card_root_is_builtin_card(self):
        """Root element has .builtin-card class."""
        node = render("failed", _failed_data())
        assert node.has_class("builtin-card")

    def test_failed_card_has_failed_card_class(self):
        """Failed card has .failed-card class for type-specific styling."""
        node = render("failed", _failed_data())
        assert node.has_class("failed-card")

    def test_failed_card_has_builtin_header(self):
        """Failed card has a header element with icon and title."""
        node = render("failed", _failed_data())
        header = node.find(class_="builtin-header")
        assert header is not None

    def test_failed_card_has_error_icon_element(self):
        """Failed card has icon element with X emoji."""
        node = render("failed", _failed_data())
        icon = node.find(class_="builtin-icon")
        assert icon is not None
        assert "❌" in icon.text

    def test_failed_card_has_title_element(self):
        """Failed card has title element with 'Task failed' text."""
        node = render("failed", _failed_data())
        title = node.find(class_="builtin-title")
        assert title is not None
        assert "Task failed" in title.text

    def test_failed_card_has_message_when_provided(self):
        """Failed card renders message element when message is provided."""
        data = _failed_data(message="Deployment failed")
        node = render("failed", data)
        message = node.find(class_="failed-message")
        assert message is not None
        assert "Deployment failed" in message.text

    def test_failed_card_has_reason_wrap(self):
        """Failed card has reason wrapper with label and content."""
        data = _failed_data(failure_reason="Container timeout")
        node = render("failed", data)
        reason_wrap = node.find(class_="failed-reason-wrap")
        assert reason_wrap is not None

    def test_failed_card_has_reason_label(self):
        """Failed card has 'Reason:' label."""
        data = _failed_data(failure_reason="Network error")
        node = render("failed", data)
        label = node.find(class_="failed-reason-label")
        assert label is not None
        assert "Reason" in label.text

    def test_failed_card_has_reason_content(self):
        """Failed card renders the actual reason text."""
        data = _failed_data(failure_reason="Network error")
        node = render("failed", data)
        reason = node.find(class_="failed-reason")
        assert reason is not None
        assert "Network error" in reason.text

    def test_failed_card_has_error_type_when_provided(self):
        """Failed card shows error type element when provided."""
        data = _failed_data(error_type="timeout")
        node = render("failed", data)
        error_type = node.find(class_="failed-error-type")
        assert error_type is not None
        assert "timeout" in error_type.text

    def test_failed_card_has_bead_id_element(self):
        """Failed card shows bead ID in dedicated element."""
        data = _failed_data(bead_id="adc-failed-xyz")
        node = render("failed", data)
        bead_elem = node.find(class_="failed-bead-id")
        assert bead_elem is not None
        assert "adc-failed-xyz" in bead_elem.text

    def test_failed_card_has_retry_button(self):
        """Failed card has a 'Retry' button element."""
        node = render("failed", _failed_data())
        button = node.find(class_="failed-retry")
        assert button is not None
        assert button.tag == "button"
        assert "Retry" in button.text


# === Visual styling classes =====================================================


class TestStuckCardStyling:
    """Verify stuck card visual styling through CSS classes."""

    def test_stuck_card_has_all_required_classes(self):
        """Stuck card has both .builtin-card and .stuck-card classes."""
        node = render("stuck", _stuck_data())
        assert "builtin-card" in node.classes
        assert "stuck-card" in node.classes

    def test_stuck_card_classes_are_distinct(self):
        """Stuck card classes don't overlap with failed card classes."""
        node = render("stuck", _stuck_data())
        assert "stuck-card" in node.classes
        assert "failed-card" not in node.classes


class TestFailedCardStyling:
    """Verify failed card visual styling through CSS classes."""

    def test_failed_card_has_all_required_classes(self):
        """Failed card has both .builtin-card and .failed-card classes."""
        node = render("failed", _failed_data())
        assert "builtin-card" in node.classes
        assert "failed-card" in node.classes

    def test_failed_card_classes_are_distinct(self):
        """Failed card classes don't overlap with stuck card classes."""
        node = render("failed", _failed_data())
        assert "failed-card" in node.classes
        assert "stuck-card" not in node.classes


# === Dataset attributes for querying ===========================================


class TestStuckCardDatasets:
    """Verify stuck card dataset attributes for querying and dismissal."""

    def test_stuck_card_has_builtin_dataset(self):
        """Stuck card has data-builtin='stuck' for querying."""
        node = render("stuck", _stuck_data())
        assert node.attrs.get("data-builtin") == "stuck"

    def test_stuck_card_has_bead_id_dataset(self):
        """Stuck card includes bead_id in data-bead-id attribute."""
        data = _stuck_data(bead_id="adc-stuck-query")
        node = render("stuck", data)
        assert node.attrs.get("data-bead-id") == "adc-stuck-query"

    def test_stuck_card_datasets_queryable_by_selector(self):
        """Stuck card can be queried by [data-builtin="stuck"] selector."""
        node = render("stuck", _stuck_data())
        # Check the root node's attrs directly
        assert node.attrs.get("data-builtin") == "stuck"

    def test_stuck_card_without_bead_id_still_renders(self):
        """Stuck card without bead_id still renders with data-builtin."""
        data = _stuck_data(bead_id=None)
        node = render("stuck", data)
        assert node.attrs.get("data-builtin") == "stuck"


class TestFailedCardDatasets:
    """Verify failed card dataset attributes for querying and dismissal."""

    def test_failed_card_has_builtin_dataset(self):
        """Failed card has data-builtin='failed' for querying."""
        node = render("failed", _failed_data())
        assert node.attrs.get("data-builtin") == "failed"

    def test_failed_card_has_bead_id_dataset(self):
        """Failed card includes bead_id in data-bead-id attribute."""
        data = _failed_data(bead_id="adc-failed-query")
        node = render("failed", data)
        assert node.attrs.get("data-bead-id") == "adc-failed-query"

    def test_failed_card_datasets_queryable_by_selector(self):
        """Failed card can be queried by [data-builtin="failed"] selector."""
        node = render("failed", _failed_data())
        # Check the root node's attrs directly
        assert node.attrs.get("data-builtin") == "failed"

    def test_failed_card_without_bead_id_still_renders(self):
        """Failed card without bead_id still renders with data-builtin."""
        data = _failed_data(bead_id=None)
        node = render("failed", data)
        assert node.attrs.get("data-builtin") == "failed"


# === Distinct rendering between stuck and failed ==============================


class TestDistinctCardRendering:
    """Verify stuck and failed cards render distinctly."""

    def test_stuck_and_failed_have_different_root_classes(self):
        """Stuck and failed cards have different identifying classes."""
        stuck = render("stuck", _stuck_data())
        failed = render("failed", _failed_data())

        assert "stuck-card" in stuck.classes
        assert "failed-card" not in stuck.classes

        assert "failed-card" in failed.classes
        assert "stuck-card" not in failed.classes

    def test_stuck_and_failed_have_different_icons(self):
        """Stuck shows construction icon, failed shows error icon."""
        stuck = render("stuck", _stuck_data())
        failed = render("failed", _failed_data())

        stuck_icon = stuck.find(class_="builtin-icon")
        failed_icon = failed.find(class_="builtin-icon")

        assert "🚧" in stuck_icon.text
        assert "❌" in failed_icon.text

    def test_stuck_and_failed_have_different_titles(self):
        """Stuck says 'Task stuck', failed says 'Task failed'."""
        stuck = render("stuck", _stuck_data())
        failed = render("failed", _failed_data())

        stuck_title = stuck.find(class_="builtin-title")
        failed_title = failed.find(class_="builtin-title")

        assert "stuck" in stuck_title.text.lower()
        assert "failed" in failed_title.text.lower()

    def test_stuck_and_failed_have_different_buttons(self):
        """Stuck has 'View bead' button, failed has 'Retry' button."""
        stuck = render("stuck", _stuck_data())
        failed = render("failed", _failed_data())

        stuck_button = stuck.find(class_="stuck-view-bead")
        failed_button = failed.find(class_="failed-retry")

        assert stuck_button is not None
        assert "View bead" in stuck_button.text

        assert failed_button is not None
        assert "Retry" in failed_button.text

    def test_stuck_and_failed_have_different_structural_elements(self):
        """Stuck has action-hint, failed has error-type (different sections)."""
        data_stuck = _stuck_data(action_hint="Provide more details")
        data_failed = _failed_data(error_type="timeout")

        stuck = render("stuck", data_stuck)
        failed = render("failed", data_failed)

        # Stuck has action hint
        assert stuck.find(class_="stuck-action-hint") is not None
        # Failed doesn't have action hint element
        assert failed.find(class_="stuck-action-hint") is None

        # Failed has error type
        assert failed.find(class_="failed-error-type") is not None
        # Stuck doesn't have error type element
        assert stuck.find(class_="failed-error-type") is None


# === Visual indicators =========================================================


class TestStuckCardVisualIndicators:
    """Test stuck card visual indicators (icons, badges, colors via classes)."""

    def test_stuck_card_icon_is_construction_emoji(self):
        """Stuck card uses construction emoji as visual indicator."""
        node = render("stuck", _stuck_data())
        icon = node.find(class_="builtin-icon")
        assert "🚧" in icon.text

    def test_stuck_card_title_indicates_stuck_state(self):
        """Title text clearly indicates stuck state."""
        node = render("stuck", _stuck_data())
        title = node.find(class_="builtin-title")
        assert "stuck" in title.text.lower()

    def test_stuck_card_has_refusal_count_indicator(self):
        """Refusal count is visible as a numeric indicator."""
        data = _stuck_data(refusal_count=7)
        node = render("stuck", data)
        count = node.find(class_="stuck-refusal-count")
        assert "7" in count.text
        assert "Refusals:" in count.text

    def test_stuck_card_styling_class_provides_color_hook(self):
        """.stuck-card class provides CSS hook for styling/colors."""
        node = render("stuck", _stuck_data())
        assert "stuck-card" in node.classes


class TestFailedCardVisualIndicators:
    """Test failed card visual indicators (icons, badges, colors via classes)."""

    def test_failed_card_icon_is_error_emoji(self):
        """Failed card uses X emoji as visual indicator."""
        node = render("failed", _failed_data())
        icon = node.find(class_="builtin-icon")
        assert "❌" in icon.text

    def test_failed_card_title_indicates_failed_state(self):
        """Title text clearly indicates failed state."""
        node = render("failed", _failed_data())
        title = node.find(class_="builtin-title")
        assert "failed" in title.text.lower()

    def test_failed_card_has_error_type_indicator(self):
        """Error type is visible as a text indicator."""
        data = _failed_data(error_type="worker_crash")
        node = render("failed", data)
        error_type = node.find(class_="failed-error-type")
        assert "worker_crash" in error_type.text

    def test_failed_card_styling_class_provides_color_hook(self):
        """.failed-card class provides CSS hook for styling/colors."""
        node = render("failed", _failed_data())
        assert "failed-card" in node.classes


# === Button elements ============================================================


class TestStuckCardButtons:
    """Test stuck card action buttons."""

    def test_stuck_card_view_bead_button_exists(self):
        """View bead button is present."""
        node = render("stuck", _stuck_data())
        button = node.find(tag="button", class_="stuck-view-bead")
        assert button is not None

    def test_stuck_card_button_has_correct_class(self):
        """Button has .stuck-view-bead class."""
        node = render("stuck", _stuck_data())
        button = node.find(tag="button")
        assert button is not None
        assert "stuck-view-bead" in button.classes

    def test_stuck_card_button_text_is_correct(self):
        """Button text is 'View bead'."""
        node = render("stuck", _stuck_data())
        button = node.find(class_="stuck-view-bead")
        assert "View bead" in button.text


class TestFailedCardButtons:
    """Test failed card action buttons."""

    def test_failed_card_retry_button_exists(self):
        """Retry button is present."""
        node = render("failed", _failed_data())
        button = node.find(tag="button", class_="failed-retry")
        assert button is not None

    def test_failed_card_button_has_correct_class(self):
        """Button has .failed-retry class."""
        node = render("failed", _failed_data())
        button = node.find(tag="button")
        assert button is not None
        assert "failed-retry" in button.classes

    def test_failed_card_button_text_is_correct(self):
        """Button text is 'Retry'."""
        node = render("failed", _failed_data())
        button = node.find(class_="failed-retry")
        assert "Retry" in button.text


# === Nested structure verification =============================================


class TestStuckCardNestedStructure:
    """Verify stuck card element nesting and structure."""

    def test_stuck_card_header_children_structure(self):
        """Header contains icon and title in correct order."""
        node = render("stuck", _stuck_data())
        header = node.find(class_="builtin-header")
        assert header is not None

        children = header.children
        assert len(children) >= 2

        # First child should be icon
        assert children[0].has_class("builtin-icon")
        # Second child should be title
        assert children[1].has_class("builtin-title")

    def test_stuck_card_reason_wrap_structure(self):
        """Reason wrap contains label and reason content."""
        data = _stuck_data(stuck_reason="Test reason")
        node = render("stuck", data)
        reason_wrap = node.find(class_="stuck-reason-wrap")

        assert reason_wrap is not None
        children = reason_wrap.children
        assert len(children) >= 2

        assert children[0].has_class("stuck-reason-label")
        assert children[1].has_class("stuck-reason")


class TestFailedCardNestedStructure:
    """Verify failed card element nesting and structure."""

    def test_failed_card_header_children_structure(self):
        """Header contains icon and title in correct order."""
        node = render("failed", _failed_data())
        header = node.find(class_="builtin-header")
        assert header is not None

        children = header.children
        assert len(children) >= 2

        # First child should be icon
        assert children[0].has_class("builtin-icon")
        # Second child should be title
        assert children[1].has_class("builtin-title")

    def test_failed_card_reason_wrap_structure(self):
        """Reason wrap contains label and reason content."""
        data = _failed_data(failure_reason="Test failure")
        node = render("failed", data)
        reason_wrap = node.find(class_="failed-reason-wrap")

        assert reason_wrap is not None
        children = reason_wrap.children
        assert len(children) >= 2

        assert children[0].has_class("failed-reason-label")
        assert children[1].has_class("failed-reason")


# === Edge cases and error handling =============================================


class TestStuckCardEdgeCases:
    """Test stuck card edge cases and error handling."""

    def test_stuck_card_with_minimal_data_renders(self):
        """Stuck card renders with minimal required data."""
        node = render("stuck", {})
        assert node.has_class("builtin-card")
        assert node.has_class("stuck-card")

    def test_stuck_card_missing_optional_fields(self):
        """Stuck card handles missing optional fields gracefully."""
        node = render("stuck", {"bead_id": "test"})
        assert node.has_class("stuck-card")
        # Header should still be present
        assert node.find(class_="builtin-header") is not None


class TestFailedCardEdgeCases:
    """Test failed card edge cases and error handling."""

    def test_failed_card_with_minimal_data_renders(self):
        """Failed card renders with minimal required data."""
        node = render("failed", {})
        assert node.has_class("builtin-card")
        assert node.has_class("failed-card")

    def test_failed_card_missing_optional_fields(self):
        """Failed card handles missing optional fields gracefully."""
        node = render("failed", {"bead_id": "test"})
        assert node.has_class("failed-card")
        # Header should still be present
        assert node.find(class_="builtin-header") is not None


# === Data attribute integrity ====================================================


class TestStuckCardDataIntegrity:
    """Test that stuck card preserves data integrity."""

    def test_stuck_card_bead_id_preserved_exactly(self):
        """Bead ID is preserved exactly as provided."""
        data = _stuck_data(bead_id="adc-123-XYZ_test")
        node = render("stuck", data)
        assert node.attrs.get("data-bead-id") == "adc-123-XYZ_test"

    def test_stuck_card_refusal_count_preserved(self):
        """Refusal count is preserved accurately."""
        data = _stuck_data(refusal_count=42)
        node = render("stuck", data)
        count_elem = node.find(class_="stuck-refusal-count")
        assert "42" in count_elem.text


class TestFailedCardDataIntegrity:
    """Test that failed card preserves data integrity."""

    def test_failed_card_bead_id_preserved_exactly(self):
        """Bead ID is preserved exactly as provided."""
        data = _failed_data(bead_id="adc-456-ABC_test")
        node = render("failed", data)
        assert node.attrs.get("data-bead-id") == "adc-456-ABC_test"

    def test_failed_card_error_type_preserved(self):
        """Error type is preserved accurately."""
        data = _failed_data(error_type="custom_error_type")
        node = render("failed", data)
        error_type_elem = node.find(class_="failed-error-type")
        assert "custom_error_type" in error_type_elem.text
