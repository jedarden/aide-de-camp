"""
Staleness indicator verification for canvas topic cards (bead adc-2vto).

Companion to ``tests/test_canvas_dom_verify.py`` (the card-DOM contract). Where
that file proves the card skeleton exists and is queryable, this file locks down
the **staleness** affordance end to end:

- **Per-level rendering** — fresh / stale / very-stale cards each render the
  right combination of: a level class on the card root, the always-on
  staleness footer (indicator + dot + "Updated <time-ago>"), and the
  "STALE" badge that only appears once a card stops being fresh.
- **Presence AND absence** — a fresh card has no stale-badge; a stale/very-stale
  card does. The level class never bleeds into the wrong card.
- **Visual rendering (color)** — the AC asks that stale cards show a *visual*
  indicator (badge, color change), not just a class name. A browser isn't
  available on this NixOS host (Playwright's chromium is missing ~26 FHS
  libs), so we verify the visual layer hermetically by parsing the production
  ``<style>`` in src/canvas/index.html and asserting the rules that turn each
  rendered class into a distinct color actually exist and are wired to the
  exact level class createTopicCard() emits. If the CSS stops distinguishing
  stale from fresh, these fail — exactly the regression a screenshot test
  would catch.

This runs **headlessly and hermetically** — no browser, no live server. It
drives the REAL production canvas module (``src/canvas/canvas.js``) through the
Node DOM runner (``tests/e2e/canvas_dom_runner.js``), then queries the emitted
``outerHTML`` with the same stdlib DOM parser adc-1rdt introduced.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from tests.e2e.canvas_render import node_available, render_card
from tests.test_canvas_dom_verify import parse_card

pytestmark = pytest.mark.skipif(
    not node_available(), reason="node not on PATH — cannot drive canvas DOM runner"
)

CANVAS_HTML = Path(__file__).resolve().parents[1] / "src" / "canvas" / "index.html"


# --- card factory (mirrors TopicCard.to_dict(), with explicit staleness) -------


def _level(seconds: int) -> str:
    """Mirror src/canvas/canvas.js getStalenessLevel() exactly."""
    if seconds < 600:
        return "fresh"      # < 10 minutes
    if seconds < 3600:
        return "stale"      # < 1 hour
    return "very-stale"


def _card(seconds: int, *, label: str = "Pods", topic_id: str = "t-1",
          topic_type: str = "project", summary: str = "3 running",
          urgency: str = "normal") -> dict:
    """Build a card dict in the exact shape GET /topics returns, pinned to a
    specific staleness ``seconds`` so each level is rendered deterministically."""
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
        "latest_result": {"summary": summary, "urgency": urgency, "data": None},
    }


def render(card: dict):
    """Render a card through the REAL canvas.js and parse it for querying."""
    return parse_card(render_card(card))


# --- production CSS parser (stdlib only) --------------------------------------
#
# Verifies the *visual* layer: the rules in src/canvas/index.html that turn each
# rendered staleness class into a distinct on-screen color. A browser would
# compute these via getComputedStyle; here we assert the source CSS that
# produces that computed style is present and correct — a deterministic,
# hermetic substitute for a screenshot diff.

_RULE_RE = re.compile(r"([^{}]+)\{([^{}]*)\}", re.DOTALL)


def _parse_css(text: str) -> dict[str, dict[str, str]]:
    """Parse a CSS stylesheet into ``{selector: {prop: value}}``.

    Handles comma-separated selector lists and ``;``-separated declarations.
    Good enough for the flat, well-formed rules the canvas stylesheet uses.
    """
    rules: dict[str, dict[str, str]] = {}
    for sel_body, decl_body in _RULE_RE.findall(text):
        decls: dict[str, str] = {}
        for decl in decl_body.split(";"):
            decl = decl.strip()
            if ":" in decl:
                prop, val = decl.split(":", 1)
                decls[prop.strip()] = val.strip()
        if not decls:
            continue
        for sel in sel_body.split(","):
            sel = sel.strip()
            if sel:
                rules[sel] = decls
    return rules


@pytest.fixture(scope="module")
def css() -> dict[str, dict[str, str]]:
    """The parsed ``<style>`` block from the production canvas HTML."""
    html = CANVAS_HTML.read_text(encoding="utf-8")
    m = re.search(r"<style>(.*?)</style>", html, re.DOTALL)
    assert m, "canvas index.html has no <style> block"
    return _parse_css(m.group(1))


# === per-level class wiring ===================================================


class TestStalenessLevelOnCardRoot:
    """The card root carries the staleness level as a class — the hook the CSS
    color rules hang off of (``.topic-card.stale`` etc.)."""

    def test_fresh_card_has_fresh_class(self):
        node = render(_card(seconds=5))
        assert node.has_class("topic-card")
        assert node.has_class("fresh")
        assert not node.has_class("stale")
        assert not node.has_class("very-stale")

    def test_stale_card_has_stale_class(self):
        node = render(_card(seconds=1200))  # 20 min
        assert node.has_class("topic-card")
        assert node.has_class("stale")
        assert not node.has_class("very-stale")

    def test_very_stale_card_has_very_stale_class(self):
        node = render(_card(seconds=7200))  # 2 hours
        assert node.has_class("topic-card")
        assert node.has_class("very-stale")
        assert not node.has_class("stale")

    @pytest.mark.parametrize("seconds,expected", [
        (0, "fresh"),
        (599, "fresh"),     # one second under the 10-minute threshold
        (600, "stale"),     # exactly 10 minutes → stale
        (3599, "stale"),    # one second under 1 hour
        (3600, "very-stale"),
        (86400, "very-stale"),
    ])
    def test_level_boundary_matches_getstalenesslevel(self, seconds, expected):
        """The level class tracks the same thresholds canvas.js uses, including
        the exact boundary seconds."""
        node = render(_card(seconds=seconds))
        assert node.has_class(expected)


# === staleness footer (always present) ========================================


class TestStalenessFooter:
    """The ``staleness-indicator`` footer renders for every card, fresh or not,
    carrying the level class on both the footer and its dot, plus a human
    "Updated <time-ago>" label."""

    @pytest.mark.parametrize("seconds", [5, 1200, 7200])
    def test_footer_present_at_every_level(self, seconds):
        node = render(_card(seconds=seconds))
        ind = node.find(class_="staleness-indicator")
        assert ind is not None
        dot = ind.find(class_="staleness-dot")
        assert dot is not None

    @pytest.mark.parametrize("seconds,level", [
        (5, "fresh"), (1200, "stale"), (7200, "very-stale"),
    ])
    def test_footer_and_dot_carry_level_class(self, seconds, level):
        node = render(_card(seconds=seconds))
        ind = node.find(class_="staleness-indicator")
        dot = ind.find(class_="staleness-dot")
        assert level in ind.classes
        assert level in dot.classes

    @pytest.mark.parametrize("seconds,expected_text", [
        (5, "Updated just now"),
        (1200, "Updated 20m ago"),    # 20 min
        (7200, "Updated 2h ago"),     # 2 hours
        (90000, "Updated 1d ago"),    # > 1 day
    ])
    def test_time_ago_text_matches_formatstaleness(self, seconds, expected_text):
        """The footer's visible "Updated <time-ago>" text matches
        canvas.js formatStaleness() for that age."""
        node = render(_card(seconds=seconds))
        assert node.find(class_="staleness-indicator").text == expected_text


# === stale badge (only when not fresh) ========================================


class TestStaleBadge:
    """The uppercase "STALE" badge is the at-a-glance visual flag. It appears
    ONLY once a card is no longer fresh, carrying the level class for its
    color."""

    def test_fresh_card_has_no_stale_badge(self):
        node = render(_card(seconds=5))
        assert node.find(class_="stale-badge") is None

    def test_stale_card_has_stale_badge(self):
        node = render(_card(seconds=1200))
        badge = node.find(class_="stale-badge")
        assert badge is not None
        assert "stale" in badge.classes
        assert badge.text == "STALE"

    def test_very_stale_card_has_stale_badge(self):
        node = render(_card(seconds=7200))
        badge = node.find(class_="stale-badge")
        assert badge is not None
        assert "very-stale" in badge.classes
        assert badge.text == "STALE"

    def test_stale_badge_lives_in_the_header(self):
        """The badge is rendered inside .topic-header (next to the type badge),
        not loose in the card body."""
        node = render(_card(seconds=1200))
        header = node.find(class_="topic-header")
        assert header is not None
        assert header.find(class_="stale-badge") is not None


# === visual rendering: the CSS that turns class → color =======================
#
# These are the "color change" half of the AC. createTopicCard() only emits
# classes; the on-screen color comes from the stylesheet. Asserting the rules
# exist and are wired to the right level class guarantees the rendered card is
# actually visually distinct — not just tagged.

class TestStalenessVisualColorRules:
    """The production stylesheet distinguishes each staleness level by color."""

    def test_stale_card_border_turns_amber(self, css):
        assert css[".topic-card.stale"]["border-color"] == "#f59e0b"

    def test_very_stale_card_border_turns_red(self, css):
        assert css[".topic-card.very-stale"]["border-color"] == "#ef4444"

    def test_stale_indicator_text_turns_amber(self, css):
        assert css[".staleness-indicator.stale"]["color"] == "#f59e0b"

    def test_very_stale_indicator_text_turns_red(self, css):
        assert css[".staleness-indicator.very-stale"]["color"] == "#ef4444"

    def test_fresh_dot_is_green(self, css):
        """The default (fresh) staleness-dot is green — the 'all good' color."""
        assert css[".staleness-dot"]["background"] == "#22c55e"

    def test_stale_dot_turns_amber(self, css):
        assert css[".staleness-dot.stale"]["background"] == "#f59e0b"

    def test_very_stale_dot_turns_red(self, css):
        assert css[".staleness-dot.very-stale"]["background"] == "#ef4444"

    def test_stale_badge_has_distinct_text_color(self, css):
        assert css[".stale-badge.stale"]["color"] == "#fcd34d"
        assert css[".stale-badge.very-stale"]["color"] == "#fca5a5"

    def test_stale_and_very_stale_use_different_colors(self, css):
        """The two non-fresh levels are visually distinguishable from each
        other, not just from fresh."""
        assert (css[".topic-card.stale"]["border-color"]
                != css[".topic-card.very-stale"]["border-color"])
        assert (css[".staleness-dot.stale"]["background"]
                != css[".staleness-dot.very-stale"]["background"])

    def test_every_rendered_level_class_has_a_color_rule(self, css):
        """Every staleness class createTopicCard() can emit has at least one
        color rule in the stylesheet — no level renders unstyled."""
        for level in ("stale", "very-stale"):
            assert any(
                sel.endswith(f".{level}") and (
                    "color" in decls or "border-color" in decls or "background" in decls
                )
                for sel, decls in css.items()
            ), f"no color rule for staleness level {level!r}"


# === rendering stays correct across multiple cards ============================


class TestMultipleStaleCards:
    """A canvas with cards of mixed ages renders each at its own level —
    staleness never leaks across cards."""

    def test_each_card_keeps_own_level(self):
        from tests.e2e.canvas_render import render_cards
        outs = render_cards([
            _card(seconds=5, label="Fresh", topic_id="t-f"),
            _card(seconds=1200, label="Stale", topic_id="t-s"),
            _card(seconds=7200, label="VeryStale", topic_id="t-v"),
        ])
        fresh = parse_card(outs[0])
        stale = parse_card(outs[1])
        vstale = parse_card(outs[2])

        assert fresh.has_class("fresh") and not fresh.has_class("stale")
        assert stale.has_class("stale") and not stale.has_class("very-stale")
        assert vstale.has_class("very-stale")

        # Only the non-fresh cards carry a badge.
        assert fresh.find(class_="stale-badge") is None
        assert stale.find(class_="stale-badge") is not None
        assert vstale.find(class_="stale-badge") is not None
