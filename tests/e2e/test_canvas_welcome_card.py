"""
Headless render-contract test for the first-run welcome card (bead adc-4nd25).

The welcome card builder (``createWelcomeCard``) ships in the served frontend
module ``src/canvas/canvas.js``; this bead WIRING job makes ``loadTopics()``
actually render it on a fresh session (zero topics) instead of the bare
"No active topics" empty-state. The headlessly-testable core of that wiring is
``buildContainerChildren(cards, projects, description)``: empty ``cards`` → the
welcome card; any real card → topic cards only (welcome dropped, never shown
alongside a real card).

This suite drives that exact function through the Node DOM runner
(``tests/e2e/canvas_dom_runner.js --container``) under a minimal DOM shim — no
browser, no live server, no DB — and asserts the bead's acceptance criteria:

* a zero-card (fresh) session renders the welcome card, its registered-project
  list, and **>=2** example utterances;
* the welcome card is **replaced, not duplicated**, the moment the first real
  result lands (a non-empty card set yields topic cards only);
* every interpolated value is a text node — markup in a registry slug or
  description surfaces as visible text, never as injected HTML (the escaping
  contract, bead adc-3ixa).

It is the Python companion the runner's own docstring names
("tests/e2e/test_canvas_welcome_card.py"), mirroring how
``tests/test_canvas_dom_verify.py`` covers the topic-card family.
"""
from __future__ import annotations

from html.parser import HTMLParser

import pytest

from tests.e2e.canvas_render import node_available, render_container

pytestmark = pytest.mark.skipif(
    not node_available(), reason="node not on PATH — cannot drive canvas DOM runner"
)


# --- minimal selector-style DOM query over stdlib html.parser ------------------
# BeautifulSoup/lxml are intentionally not a dependency; createWelcomeCard()
# emits simple, well-formed HTML we parse with the standard library. This
# mirrors the query style in tests/test_canvas_dom_verify.py.


class _Node:
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

    def find_all(self, *, tag: str | None = None, class_: str | None = None) -> list["_Node"]:
        out: list[_Node] = []
        for node in self._walk():
            if tag is not None and node.tag != tag:
                continue
            if class_ is not None and class_ not in node.classes:
                continue
            out.append(node)
        return out

    def find(self, *, tag: str | None = None, class_: str | None = None) -> "_Node | None":
        matches = self.find_all(tag=tag, class_=class_)
        return matches[0] if matches else None

    def has_class(self, class_: str) -> bool:
        return class_ in self.classes

    @property
    def text(self) -> str:
        parts = list(self.text_parts)
        for node in self._walk():
            parts.extend(node.text_parts)
        return " ".join(p for p in parts if p).strip()


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


def parse(node_out: dict) -> _Node:
    """Parse one ``render_container`` output dict into a queryable tree; returns
    the rendered root element."""
    tb = _TreeBuilder()
    tb.feed(node_out["outerHTML"])
    tb.close()
    assert tb.root.children, "rendered node had no root element"
    return tb.root.children[0]


def _project(slug: str, *, description: str = "", intents: list[str] | None = None) -> dict:
    """A registry entry in the shape GET /api/v1/registry returns under .projects."""
    return {"slug": slug, "description": description, "intent_support": intents or []}


# Two described projects with supported intents, so examples are derived from
# real registry entries (not the default fallback set).
_PROJECTS = [
    _project("options-pipeline", description="options data pipeline",
             intents=["status", "action"]),
    _project("ibkr-mcp", description="IBKR MCP server", intents=["task-profile"]),
]


def _real_card(topic_id: str = "t-1") -> dict:
    """A card dict in the exact shape GET /topics returns under .cards."""
    return {
        "topic": {"id": topic_id, "label": "Options", "type": "project"},
        "staleness": {"seconds": 5},
        "latest_result": {"summary": "3 pods running", "urgency": "normal"},
    }


# === fresh session: welcome card renders =====================================


class TestFreshSessionWelcome:
    def test_zero_cards_renders_single_welcome_card(self):
        """A fresh session (no topics) shows exactly the welcome card — not the
        bare empty-state, and not the welcome card alongside anything else."""
        outs = render_container(cards=[], projects=_PROJECTS)
        assert len(outs) == 1
        node = outs[0]
        assert "welcome-card" in node["className"]
        assert node["dataset"].get("builtin") == "welcome"

    def test_welcome_card_header_and_description(self):
        node = parse(render_container(cards=[], projects=_PROJECTS,
                                      description="ADC voice canvas")[0])
        assert node.find(class_="builtin-title").text == "Welcome to ADC"
        assert node.find(class_="builtin-desc").text == "ADC voice canvas"

    def test_welcome_card_lists_registered_projects(self):
        """The registered-project list comes from the registry (never the DB)."""
        node = parse(render_container(cards=[], projects=_PROJECTS)[0])
        projects = node.find_all(class_="builtin-project")
        slugs = [li.find(class_="builtin-project-slug").text for li in projects]
        assert "options-pipeline" in slugs
        assert "ibkr-mcp" in slugs
        # The described projects surface their description text too.
        first = projects[0]
        assert "options data pipeline" in first.text

    def test_welcome_card_has_at_least_two_examples(self):
        """AC: >=2 example utterances, derived from the projects' intents."""
        node = parse(render_container(cards=[], projects=_PROJECTS)[0])
        examples = node.find_all(class_="builtin-example")
        assert len(examples) >= 2
        # Each example is non-empty visible text.
        assert all(li.text.strip() for li in examples)
        # Examples reference the real projects' supported intents.
        joined = " ".join(li.text for li in examples)
        assert "options-pipeline" in joined or "ibkr-mcp" in joined

    def test_empty_registry_still_renders_welcome_with_defaults(self):
        """A wedged/empty registry endpoint never leaves the canvas bare: the
        welcome card still renders with the default example utterances."""
        node = parse(render_container(cards=[], projects=[])[0])
        assert node.has_class("welcome-card")
        # Default examples (>=2) are shown even with no projects registered.
        assert len(node.find_all(class_="builtin-example")) >= 2
        assert node.find(class_="builtin-project") is not None  # "No projects…" row


# === first real result: welcome card is dropped, not duplicated ===============


class TestWelcomeDroppedOnFirstResult:
    def test_first_real_result_replaces_welcome_card(self):
        """The moment the first real topic card exists, the container shows only
        topic cards — the welcome card is gone, not kept alongside it."""
        outs = render_container(cards=[_real_card()], projects=_PROJECTS)
        assert len(outs) == 1
        node = outs[0]
        assert "topic-card" in node["className"]
        assert "welcome-card" not in node["className"]
        assert node["dataset"].get("builtin") is None  # not a built-in card

    def test_no_welcome_card_survives_any_non_empty_card_set(self):
        """No element in a non-empty container carries data-builtin=welcome."""
        outs = render_container(cards=[_real_card("a"), _real_card("b")],
                                projects=_PROJECTS)
        assert len(outs) == 2
        assert all("topic-card" in o["className"] for o in outs)
        assert all(o["dataset"].get("builtin") != "welcome" for o in outs)
        assert all("welcome-card" not in o["className"] for o in outs)

    def test_zero_then_one_card_transition_drops_welcome(self):
        """The exact SSE result_created → loadTopics() reload transition: the
        same projects list yields the welcome card at zero cards and a topic
        card (no welcome) once one card lands."""
        zero = render_container(cards=[], projects=_PROJECTS)
        one = render_container(cards=[_real_card()], projects=_PROJECTS)
        assert zero[0]["dataset"].get("builtin") == "welcome"
        assert one[0]["dataset"].get("builtin") is None
        assert "topic-card" in one[0]["className"]


# === escaping contract (bead adc-3ixa) =======================================
# Every interpolated value is a text node, so markup can't break out.


class TestEscaping:
    def test_markup_in_project_slug_is_visible_text(self):
        """A slug containing markup renders as literal text, not an element."""
        evil = _project("<script>alert(1)</script>", description="x", intents=["status"])
        node = parse(render_container(cards=[], projects=[evil])[0])
        slug = node.find(class_="builtin-project-slug")
        assert slug.text == "<script>alert(1)</script>"
        # Nothing was actually injected into the card's DOM.
        assert node.find_all(tag="script") == []
        assert node.find_all(tag="img") == []

    def test_markup_in_description_is_visible_text(self):
        node = parse(render_container(
            cards=[], projects=[],
            description='"><img src=x onerror=alert(1)>')[0])
        desc = node.find(class_="builtin-desc")
        assert desc.text == '"><img src=x onerror=alert(1)>'
        assert node.find_all(tag="img") == []
        assert node.find_all(tag="script") == []
