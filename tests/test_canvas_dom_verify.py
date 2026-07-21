"""
DOM verification for canvas topic cards (bead adc-1rdt).

Companion to ``tests/test_canvas_render.py`` (the render-contract test). Where
that file asserts the rendered *HTML string*, this file queries the rendered DOM
the way a browser test would — by selector — and verifies the things a canvas
consumer relies on to locate and read a card:

- **data attributes**: every card exposes ``data-topic-id`` AND
  ``data-topic-type`` on its root (added in src/canvas/canvas.js for this bead),
  so cards are locatable by id and by type with a robust, stable selector.
- **layout classes**: the card skeleton is present — ``topic-card`` (root),
  ``topic-header`` (the card header), ``topic-label``, ``topic-type``, and the
  result body (``result-content`` / ``result-summary``) when there is a result.
  (The bead's AC names these as card / card-header / card-body; in this canvas
  they are topic-card / topic-header / result-content — the idiom the existing
  markup already uses. Both names map to the same elements below.)
- **text content**: the label, the result summary, the type-badge text and the
  urgency-badge text all match the data handed to ``createTopicCard()``.
- **every topic type**: project, research, personal, exception, compound each
  render with the right ``data-topic-type`` and type-badge.
- **negative cases**: an empty card list renders nothing; a card with no result
  renders no result body; one card's topic id never bleeds into another's.

This runs **headlessly and hermetically** — no browser, no live server. It drives
the REAL production canvas module (``src/canvas/canvas.js``) through the Node DOM
runner (``tests/e2e/canvas_dom_runner.js``) that adc-1l8w introduced, then queries
the emitted ``outerHTML`` with a tiny stdlib-only DOM parser. Playwright's own
``expect()``/locator API can't launch a browser on this NixOS host (its bundled
chromium is missing ~26 FHS libraries), so this is the suite that stays green
here; the Playwright counterpart lives in
``tests/e2e/test_canvas_dom_verification.py`` and runs wherever a browser can.
"""
from __future__ import annotations

from html.parser import HTMLParser

import pytest

from tests.e2e.canvas_render import node_available, render_card, render_cards

pytestmark = pytest.mark.skipif(
    not node_available(), reason="node not on PATH — cannot drive canvas DOM runner"
)


# --- minimal selector-style DOM query over stdlib html.parser ------------------
#
# BeautifulSoup/lxml aren't (and shouldn't need to be) a dependency, so we parse
# the well-formed, simple HTML createTopicCard() emits with the standard library.
# This deliberately mirrors how Playwright locators query the DOM: find elements
# by tag + class + attribute, then read their text.


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
    """Parse one ``render_card``/``render_cards`` output dict into a query tree.

    The node returned is the card root (``<div class="topic-card ...">``), so
    callers can ``.find(class_="topic-label")`` directly.
    """
    root = _TreeBuilder()
    root.feed(card_out["outerHTML"])
    root.close()
    # The card root is the first real element under the synthetic root.
    assert root.root.children, "rendered card had no root element"
    return root.root.children[0]


def render(card: dict) -> _Node:
    """Render a card dict through the real canvas.js and parse it for querying."""
    return parse_card(render_card(card))


# --- card-shape factory (mirrors TopicCard.to_dict()) -------------------------


def _level(seconds: int) -> str:
    if seconds < 600:
        return "fresh"
    if seconds < 3600:
        return "stale"
    return "very-stale"


def _card(
    label: str = "Pods",
    *,
    topic_id: str = "t-1",
    topic_type: str = "project",
    summary: str | None = "3 pods running",
    urgency: str = "normal",
    data: dict | None = None,
    seconds: int = 5,
    latest_result: dict | None | object = ...,  # sentinel
) -> dict:
    """Build a card dict in the exact shape GET /topics returns."""
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
            "result_count": 1,
        },
        "staleness": {"seconds": seconds, "level": _level(seconds)},
        "latest_result": latest_result,
    }


# === data attributes ==========================================================


class TestDataAttributes:
    def test_data_topic_id_present_and_matches(self):
        node = render(_card(topic_id="t-abc"))
        assert node.attrs["data-topic-id"] == "t-abc"

    def test_data_topic_type_present_and_matches(self):
        """The data-topic-type attribute (added this bead) reflects the type."""
        node = render(_card(topic_type="research"))
        assert node.attrs["data-topic-type"] == "research"

    def test_data_topic_type_defaults_to_adhoc_when_missing(self):
        """A topic with no type still yields a stable data-topic-type value."""
        card = _card()
        card["topic"]["type"] = None
        node = render(card)
        assert node.attrs["data-topic-type"] == "adhoc"

    def test_data_attributes_live_on_the_card_root(self):
        """Both data attributes are on the .topic-card root, not on children."""
        node = render(_card(topic_id="t-1", topic_type="project"))
        assert node.has_class("topic-card")
        # No descendant carries the data attributes — only the root.
        leaks = node.find_all(attrs={"data-topic-id": "t-1"})
        assert leaks == []
        leaks_type = node.find_all(attrs={"data-topic-type": "project"})
        assert leaks_type == []


# === layout classes (card / card-header / card-body) ==========================


class TestLayoutClasses:
    """The card skeleton every canvas consumer assumes is present.

    AC layout classes → this canvas's actual class names:
        card        → ``topic-card``       (root)
        card-header → ``topic-header``     (label + type row)
        card-body   → ``result-content``   (the result block, when present)
    """

    def test_root_is_a_topic_card(self):
        node = render(_card())
        assert node.has_class("topic-card")

    def test_card_header_present(self):
        node = render(_card())
        assert node.find(class_="topic-header") is not None

    def test_card_label_present(self):
        node = render(_card(label="Pods"))
        assert node.find(class_="topic-label") is not None

    def test_type_badge_present(self):
        node = render(_card(topic_type="project"))
        assert node.find(class_="topic-type") is not None

    def test_card_body_present_when_there_is_a_result(self):
        node = render(_card(summary="3 running"))
        assert node.find(class_="result-content") is not None
        assert node.find(class_="result-summary") is not None

    def test_urgency_badge_present(self):
        node = render(_card(urgency="critical"))
        assert node.find(class_="urgency-badge") is not None

    def test_staleness_footer_present(self):
        node = render(_card())
        assert node.find(class_="staleness-indicator") is not None


# === text content matches the data ===========================================


class TestTextContent:
    def test_label_text_matches(self):
        node = render(_card(label="Options Pipeline"))
        assert node.find(class_="topic-label").text == "Options Pipeline"

    def test_summary_text_matches(self):
        node = render(_card(summary="3 pods running, 0 crashed"))
        assert "3 pods running, 0 crashed" in node.find(class_="result-summary").text

    def test_type_badge_text_matches(self):
        node = render(_card(topic_type="research"))
        assert node.find(class_="topic-type").text == "research"

    def test_urgency_badge_text_matches(self):
        node = render(_card(urgency="high"))
        assert node.find(class_="urgency-badge").text == "high"

    def test_label_text_is_unescaped_visible_text(self):
        """Escaped markup in the label surfaces as visible text, not raw HTML."""
        node = render(_card(label="<script>alert(1)</script>"))
        assert node.find(class_="topic-label").text == "<script>alert(1)</script>"


# === every topic type ========================================================


ALL_TYPES = ["project", "research", "personal", "exception", "compound"]


class TestAllTopicTypes:
    @pytest.mark.parametrize("topic_type", ALL_TYPES)
    def test_type_renders_in_data_attr_and_badge(self, topic_type):
        """Each supported topic type is queryable via [data-topic-type=...] and
        shows the right type-badge class + text."""
        node = render(_card(topic_type=topic_type, topic_id=f"t-{topic_type}"))
        # Robust selector: data attribute carries the type.
        assert node.attrs["data-topic-type"] == topic_type
        # The badge class is `topic-type <type>` and its text is the type.
        badge = node.find(class_="topic-type")
        assert topic_type in badge.classes
        assert badge.text == topic_type


# === negative cases ==========================================================


class TestNegative:
    def test_empty_card_list_renders_no_cards(self):
        """No topics → no .topic-card elements at all (missing topics not
        rendered)."""
        outs = render_cards([])
        assert outs == []
        # And parsing yields nothing to query.
        assert all("topic-card" not in o["outerHTML"] for o in outs)

    def test_card_without_result_has_no_card_body(self):
        """A topic with no latest_result renders a header but no result body."""
        node = render(_card(label="Empty", summary=None))
        assert node.find(class_="topic-label") is not None  # header still there
        assert node.find(class_="result-content") is None   # no card-body
        assert node.find(class_="result-summary") is None

    def test_no_element_carries_an_unrelated_topic_type(self):
        """A card never advertises a type it doesn't have."""
        node = render(_card(topic_type="project"))
        assert node.find(attrs={"data-topic-type": "research"}) is None
        assert node.find(class_="research") is None

    def test_topic_id_does_not_leak_across_cards(self):
        """Two cards keep distinct topic ids — A's id is not on B."""
        outs = render_cards([_card(label="A", topic_id="t-a"),
                             _card(label="B", topic_id="t-b")])
        a = parse_card(outs[0])
        b = parse_card(outs[1])
        assert a.attrs["data-topic-id"] == "t-a"
        assert b.attrs["data-topic-id"] == "t-b"
        assert b.find(attrs={"data-topic-id": "t-a"}) is None
        assert a.find(attrs={"data-topic-id": "t-b"}) is None

    def test_malformed_label_still_renders_as_text_not_markup(self):
        """A label containing markup can't break out of its element."""
        node = render(_card(label='"><img src=x onerror=alert(1)>', summary="ok"))
        label = node.find(class_="topic-label")
        assert label is not None
        # No <img> was injected anywhere in the card.
        assert node.find(tag="img") is None
        assert node.find(tag="script") is None
