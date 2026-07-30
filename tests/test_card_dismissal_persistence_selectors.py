"""
Comprehensive persistence and selector tests for card dismissal (bead adc-4gcyj).

Acceptance criteria:
- Test dismissed stuck card doesn't reappear on topic reload
- Test dismissed failed card doesn't reappear on topic reload
- Test CSS selectors for stuck cards by data-builtin
- Test CSS selectors for failed cards by data-builtin
- Test selector by specific bead_id
- Test multiple cards selective dismissal
- All persistence/selector tests pass
- Tests verify state persistence

This test suite verifies:
1. CSS selectors work correctly for finding stuck/failed cards
2. Dismissed cards persist across topic reloads (simulating page refresh)
3. Multiple cards can be selectively dismissed
4. Selector functionality by data-builtin and data-bead-id attributes
"""

from __future__ import annotations

import pytest
from pathlib import Path
from html.parser import HTMLParser


# --- DOM parser for selector testing -------------------------------------------


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


def parse_card_html(card_out: dict) -> _Node:
    """Parse one render_builtin_card output dict into a query tree."""
    root = _TreeBuilder()
    root.feed(card_out["outerHTML"])
    root.close()
    assert root.root.children, "rendered card had no root element"
    return root.root.children[0]


# --- Card data fixtures --------------------------------------------------------


def _stuck_card_data(
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


def _failed_card_data(
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


# === CSS Selector Tests =========================================================


class TestCSSSelectorsStuckCards:
    """Test CSS selectors work correctly for stuck cards."""

    def test_selector_stuck_cards_by_data_builtin(self):
        """CSS selector [data-builtin="stuck"] finds all stuck cards."""
        from tests.e2e.canvas_render import render_builtin_cards, node_available

        if not node_available():
            pytest.skip("node not on PATH")

        cards = [
            _stuck_card_data(bead_id="adc-stuck-1", stuck_reason="Reason 1"),
            _stuck_card_data(bead_id="adc-stuck-2", stuck_reason="Reason 2"),
            _stuck_card_data(bead_id="adc-stuck-3", stuck_reason="Reason 3"),
        ]

        outs = render_builtin_cards("stuck", cards)

        # All cards should have data-builtin="stuck"
        for out in outs:
            assert out["dataset"].get("builtin") == "stuck"
            node = parse_card_html(out)
            assert node.attrs.get("data-builtin") == "stuck"
            # Selector: [data-builtin="stuck"] would match all these cards

    def test_selector_stuck_card_by_bead_id(self):
        """CSS selector [data-bead-id="adc-specific"] finds specific stuck card."""
        from tests.e2e.canvas_render import render_builtin_cards, node_available

        if not node_available():
            pytest.skip("node not on PATH")

        target_bead_id = "adc-target-stuck"
        cards = [
            _stuck_card_data(bead_id="adc-other-1", stuck_reason="Other 1"),
            _stuck_card_data(bead_id=target_bead_id, stuck_reason="Target"),
            _stuck_card_data(bead_id="adc-other-2", stuck_reason="Other 2"),
        ]

        outs = render_builtin_cards("stuck", cards)

        # Find the target card
        target_card = None
        for out in outs:
            if out.get("dataset", {}).get("beadId") == target_bead_id:
                target_card = out
                break

        assert target_card is not None, "Target card should exist"
        node = parse_card_html(target_card)
        # Selector: [data-builtin="stuck"][data-bead-id="adc-target-stuck"]
        assert node.attrs.get("data-builtin") == "stuck"
        assert node.attrs.get("data-bead-id") == target_bead_id

    def test_selector_stuck_card_combined_attributes(self):
        """CSS selector with both data-builtin and data-bead-id works correctly."""
        from tests.e2e.canvas_render import render_builtin_card, node_available

        if not node_available():
            pytest.skip("node not on PATH")

        bead_id = "adc-combined-test"
        data = _stuck_card_data(bead_id=bead_id, stuck_reason="Combined test")
        out = render_builtin_card("stuck", data)
        node = parse_card_html(out)

        # Combined selector: [data-builtin="stuck"][data-bead-id="adc-combined-test"]
        assert node.attrs.get("data-builtin") == "stuck"
        assert node.attrs.get("data-bead-id") == bead_id
        assert node.has_class("stuck-card")

    def test_selector_stuck_card_class_based(self):
        """CSS selector .stuck-card finds stuck cards."""
        from tests.e2e.canvas_render import render_builtin_card, node_available

        if not node_available():
            pytest.skip("node not on PATH")

        data = _stuck_card_data(bead_id="adc-class-test", stuck_reason="Class test")
        out = render_builtin_card("stuck", data)
        node = parse_card_html(out)

        # Class selector: .stuck-card
        assert node.has_class("stuck-card")
        # Combined: .stuck-card[data-builtin="stuck"]
        assert node.has_class("stuck-card")
        assert node.attrs.get("data-builtin") == "stuck"


class TestCSSSelectorsFailedCards:
    """Test CSS selectors work correctly for failed cards."""

    def test_selector_failed_cards_by_data_builtin(self):
        """CSS selector [data-builtin="failed"] finds all failed cards."""
        from tests.e2e.canvas_render import render_builtin_cards, node_available

        if not node_available():
            pytest.skip("node not on PATH")

        cards = [
            _failed_card_data(bead_id="adc-failed-1", failure_reason="Fail 1"),
            _failed_card_data(bead_id="adc-failed-2", failure_reason="Fail 2"),
        ]

        outs = render_builtin_cards("failed", cards)

        # All cards should have data-builtin="failed"
        for out in outs:
            assert out["dataset"].get("builtin") == "failed"
            node = parse_card_html(out)
            assert node.attrs.get("data-builtin") == "failed"
            # Selector: [data-builtin="failed"] would match all these cards

    def test_selector_failed_card_by_bead_id(self):
        """CSS selector [data-bead-id="adc-specific-failed"] finds specific failed card."""
        from tests.e2e.canvas_render import render_builtin_cards, node_available

        if not node_available():
            pytest.skip("node not on PATH")

        target_bead_id = "adc-target-failed"
        cards = [
            _failed_card_data(bead_id="adc-other-f1", failure_reason="Other 1"),
            _failed_card_data(bead_id=target_bead_id, failure_reason="Target"),
            _failed_card_data(bead_id="adc-other-f2", failure_reason="Other 2"),
        ]

        outs = render_builtin_cards("failed", cards)

        # Find the target card
        target_card = None
        for out in outs:
            if out.get("dataset", {}).get("beadId") == target_bead_id:
                target_card = out
                break

        assert target_card is not None, "Target card should exist"
        node = parse_card_html(target_card)
        # Selector: [data-builtin="failed"][data-bead-id="adc-target-failed"]
        assert node.attrs.get("data-builtin") == "failed"
        assert node.attrs.get("data-bead-id") == target_bead_id

    def test_selector_failed_card_combined_attributes(self):
        """CSS selector with both data-builtin and data-bead-id works correctly for failed cards."""
        from tests.e2e.canvas_render import render_builtin_card, node_available

        if not node_available():
            pytest.skip("node not on PATH")

        bead_id = "adc-failed-combined"
        data = _failed_card_data(bead_id=bead_id, failure_reason="Combined test")
        out = render_builtin_card("failed", data)
        node = parse_card_html(out)

        # Combined selector: [data-builtin="failed"][data-bead-id="adc-failed-combined"]
        assert node.attrs.get("data-builtin") == "failed"
        assert node.attrs.get("data-bead-id") == bead_id
        assert node.has_class("failed-card")

    def test_selector_failed_card_class_based(self):
        """CSS selector .failed-card finds failed cards."""
        from tests.e2e.canvas_render import render_builtin_card, node_available

        if not node_available():
            pytest.skip("node not on PATH")

        data = _failed_card_data(bead_id="adc-failed-class", failure_reason="Class test")
        out = render_builtin_card("failed", data)
        node = parse_card_html(out)

        # Class selector: .failed-card
        assert node.has_class("failed-card")
        # Combined: .failed-card[data-builtin="failed"]
        assert node.has_class("failed-card")
        assert node.attrs.get("data-builtin") == "failed"


class TestCSSSelectorsMixedCards:
    """Test CSS selectors work correctly when stuck and failed cards are mixed."""

    def test_selector_distinguishes_stuck_from_failed(self):
        """Selectors correctly distinguish stuck cards from failed cards."""
        from tests.e2e.canvas_render import render_builtin_cards, node_available

        if not node_available():
            pytest.skip("node not PATH")

        # Mix stuck and failed cards
        stuck_cards = [
            _stuck_card_data(bead_id="adc-stuck-mix-1", stuck_reason="Stuck 1"),
            _stuck_card_data(bead_id="adc-stuck-mix-2", stuck_reason="Stuck 2"),
        ]

        failed_cards = [
            _failed_card_data(bead_id="adc-failed-mix-1", failure_reason="Failed 1"),
            _failed_card_data(bead_id="adc-failed-mix-2", failure_reason="Failed 2"),
        ]

        stuck_outs = render_builtin_cards("stuck", stuck_cards)
        failed_outs = render_builtin_cards("failed", failed_cards)

        # [data-builtin="stuck"] should only match stuck cards
        for out in stuck_outs:
            node = parse_card_html(out)
            assert node.attrs.get("data-builtin") == "stuck"
            assert node.has_class("stuck-card")
            assert not node.has_class("failed-card")

        # [data-builtin="failed"] should only match failed cards
        for out in failed_outs:
            node = parse_card_html(out)
            assert node.attrs.get("data-builtin") == "failed"
            assert node.has_class("failed-card")
            assert not node.has_class("stuck-card")

    def test_selector_finds_specific_card_in_mixed_set(self):
        """Can select a specific card by bead_id even when other cards are present."""
        from tests.e2e.canvas_render import render_builtin_cards, node_available

        if not node_available():
            pytest.skip("node not on PATH")

        target_bead_id = "adc-target-mixed"
        cards = [
            _stuck_card_data(bead_id="adc-stuck-a", stuck_reason="Stuck A"),
            _failed_card_data(bead_id=target_bead_id, failure_reason="Target"),
            _stuck_card_data(bead_id="adc-stuck-b", stuck_reason="Stuck B"),
        ]

        # Render stuck cards first, then failed
        stuck_outs = render_builtin_cards("stuck", cards[:1] + [cards[2]])
        failed_outs = render_builtin_cards("failed", [cards[1]])

        # Find target in failed cards
        target_found = False
        for out in failed_outs:
            if out.get("dataset", {}).get("beadId") == target_bead_id:
                target_found = True
                node = parse_card_html(out)
                # Selector: [data-builtin="failed"][data-bead-id="adc-target-mixed"]
                assert node.attrs.get("data-builtin") == "failed"
                assert node.attrs.get("data-bead-id") == target_bead_id

        assert target_found, "Target card should be found"


# === Persistence Tests ==========================================================


@pytest.mark.asyncio
class TestDismissalPersistenceStuckCards:
    """Test dismissed stuck cards don't reappear on topic reload."""

    async def test_dismissed_stuck_card_not_recreated_on_topic_reload(self, tmp_path):
        """Once a stuck card is dismissed, it doesn't reappear when topics are reloaded."""
        from src.session.store import SessionStore

        db_path = tmp_path / "test_stuck_persistence.db"
        store = SessionStore(db_path)
        await store.initialize()

        try:
            session_id = await store.create_session()

            utterance_id = await store.create_utterance(
                session_id=session_id,
                raw_text="Test stuck persistence",
            )

            topic_id, _ = await store.find_or_create_topic(
                label="Stuck Persistence Test",
                session_id=session_id,
                topic_type="project",
            )

            bead_ref = "adc-stuck-persist-test"
            intent_id = await store.create_intent(
                utterance_id=utterance_id,
                session_id=session_id,
                project_slug="adc",
                intent_type="task-profile",
                bead_ref=bead_ref,
                topic_id=topic_id,
            )

            # Create stuck result
            result_id = await store.create_result(
                intent_id=intent_id,
                topic_id=topic_id,
                session_id=session_id,
                summary="Task stuck — needs your input",
                data={
                    "bead_id": bead_ref,
                    "stuck_reason": "Persistence test",
                    "refusal_count": 1,
                    "message": "Stuck for testing",
                },
                urgency="high",
            )

            # First "page load" - verify card appears
            import json
            results_before = await store.get_results_for_intent(intent_id)
            assert len(results_before) == 1, "Card should appear on first load"
            result_data_before = json.loads(results_before[0]["data"])
            assert result_data_before["bead_id"] == bead_ref

            # User dismisses the card
            deletion_result = await store.delete_result(result_id, session_id)
            assert deletion_result["result_deleted"] == 1

            # Simulate "page reload" - query topics again
            results_after = await store.get_results_for_intent(intent_id)
            assert len(results_after) == 0, "Dismissed card should not reappear on reload"

            # Also verify via topics query (simulating canvas reload)
            topics = await store.get_active_topics(session_id)
            topic = next((t for t in topics if t["id"] == topic_id), None)
            assert topic is not None, "Topic should still exist"

        finally:
            await store.close()

    async def test_dismissed_stuck_card_persists_across_session_reopen(self, tmp_path):
        """Dismissed stuck card stays dismissed even after closing and reopening the session store."""
        from src.session.store import SessionStore

        db_path = tmp_path / "test_stuck_session_reopen.db"

        # First session: create and dismiss
        store1 = SessionStore(db_path)
        await store1.initialize()

        session_id = await store1.create_session()
        utterance_id = await store1.create_utterance(
            session_id=session_id,
            raw_text="Test session reopen",
        )

        topic_id, _ = await store1.find_or_create_topic(
            label="Session Reopen Test",
            session_id=session_id,
            topic_type="project",
        )

        bead_ref = "adc-stuck-session-test"
        intent_id = await store1.create_intent(
            utterance_id=utterance_id,
            session_id=session_id,
            project_slug="adc",
            intent_type="task-profile",
            bead_ref=bead_ref,
            topic_id=topic_id,
        )

        result_id = await store1.create_result(
            intent_id=intent_id,
            topic_id=topic_id,
            session_id=session_id,
            summary="Task stuck",
            data={"bead_id": bead_ref, "stuck_reason": "Session test"},
            urgency="high",
        )

        # Verify result exists
        results_before = await store1.get_results_for_intent(intent_id)
        assert len(results_before) == 1

        # Dismiss the card
        await store1.delete_result(result_id, session_id)
        await store1.close()

        # Second session: reopen and verify card is still dismissed
        store2 = SessionStore(db_path)
        await store2.initialize()

        try:
            results_after = await store2.get_results_for_intent(intent_id)
            assert len(results_after) == 0, "Dismissed card should stay dismissed after session reopen"

        finally:
            await store2.close()


@pytest.mark.asyncio
class TestDismissalPersistenceFailedCards:
    """Test dismissed failed cards don't reappear on topic reload."""

    async def test_dismissed_failed_card_not_recreated_on_topic_reload(self, tmp_path):
        """Once a failed card is dismissed, it doesn't reappear when topics are reloaded."""
        from src.session.store import SessionStore

        db_path = tmp_path / "test_failed_persistence.db"
        store = SessionStore(db_path)
        await store.initialize()

        try:
            session_id = await store.create_session()

            utterance_id = await store.create_utterance(
                session_id=session_id,
                raw_text="Test failed persistence",
            )

            topic_id, _ = await store.find_or_create_topic(
                label="Failed Persistence Test",
                session_id=session_id,
                topic_type="project",
            )

            bead_ref = "adc-failed-persist-test"
            intent_id = await store.create_intent(
                utterance_id=utterance_id,
                session_id=session_id,
                project_slug="adc",
                intent_type="task-profile",
                bead_ref=bead_ref,
                topic_id=topic_id,
            )

            # Create failed result
            result_id = await store.create_result(
                intent_id=intent_id,
                topic_id=topic_id,
                session_id=session_id,
                summary="Task Failed: Worker_Crash",
                data={
                    "bead_ref": bead_ref,
                    "failure_reason": "Persistence test",
                    "error_type": "worker_crash",
                    "message": "Failed for testing",
                },
                urgency="high",
            )

            # First "page load" - verify card appears
            import json
            results_before = await store.get_results_for_intent(intent_id)
            assert len(results_before) == 1, "Card should appear on first load"
            result_data_before = json.loads(results_before[0]["data"])
            assert result_data_before["bead_ref"] == bead_ref

            # User dismisses the card
            deletion_result = await store.delete_result(result_id, session_id)
            assert deletion_result["result_deleted"] == 1

            # Simulate "page reload" - query topics again
            results_after = await store.get_results_for_intent(intent_id)
            assert len(results_after) == 0, "Dismissed card should not reappear on reload"

        finally:
            await store.close()

    async def test_dismissed_failed_card_persists_across_session_reopen(self, tmp_path):
        """Dismissed failed card stays dismissed even after closing and reopening the session store."""
        from src.session.store import SessionStore

        db_path = tmp_path / "test_failed_session_reopen.db"

        # First session: create and dismiss
        store1 = SessionStore(db_path)
        await store1.initialize()

        session_id = await store1.create_session()
        utterance_id = await store1.create_utterance(
            session_id=session_id,
            raw_text="Test failed session reopen",
        )

        topic_id, _ = await store1.find_or_create_topic(
            label="Failed Session Reopen Test",
            session_id=session_id,
            topic_type="project",
        )

        bead_ref = "adc-failed-session-test"
        intent_id = await store1.create_intent(
            utterance_id=utterance_id,
            session_id=session_id,
            project_slug="adc",
            intent_type="task-profile",
            bead_ref=bead_ref,
            topic_id=topic_id,
        )

        result_id = await store1.create_result(
            intent_id=intent_id,
            topic_id=topic_id,
            session_id=session_id,
            summary="Task Failed",
            data={
                "bead_ref": bead_ref,
                "failure_reason": "Session test",
                "error_type": "test_error",
            },
            urgency="high",
        )

        # Verify result exists
        results_before = await store1.get_results_for_intent(intent_id)
        assert len(results_before) == 1

        # Dismiss the card
        await store1.delete_result(result_id, session_id)
        await store1.close()

        # Second session: reopen and verify card is still dismissed
        store2 = SessionStore(db_path)
        await store2.initialize()

        try:
            results_after = await store2.get_results_for_intent(intent_id)
            assert len(results_after) == 0, "Dismissed card should stay dismissed after session reopen"

        finally:
            await store2.close()


@pytest.mark.asyncio
class TestSelectiveDismissalMultipleCards:
    """Test selective dismissal of multiple cards."""

    async def test_multiple_stuck_cards_selective_dismissal(self, tmp_path):
        """Dismissing one stuck card doesn't affect other stuck cards."""
        from src.session.store import SessionStore

        db_path = tmp_path / "test_multiple_stuck.db"
        store = SessionStore(db_path)
        await store.initialize()

        try:
            session_id = await store.create_session()
            topic_id, _ = await store.find_or_create_topic(
                label="Multi Stuck Test",
                session_id=session_id,
                topic_type="project",
            )

            # Create three stuck cards
            cards = []
            for i in range(1, 4):
                utterance_id = await store.create_utterance(
                    session_id=session_id,
                    raw_text=f"Test stuck {i}",
                )

                bead_ref = f"adc-stuck-{i}"
                intent_id = await store.create_intent(
                    utterance_id=utterance_id,
                    session_id=session_id,
                    project_slug="adc",
                    intent_type="task-profile",
                    bead_ref=bead_ref,
                    topic_id=topic_id,
                )

                result_id = await store.create_result(
                    intent_id=intent_id,
                    topic_id=topic_id,
                    session_id=session_id,
                    summary=f"Stuck card {i}",
                    data={"bead_id": bead_ref, "stuck_reason": f"Reason {i}"},
                    urgency="high",
                )
                cards.append({"bead_ref": bead_ref, "intent_id": intent_id, "result_id": result_id})

            # Verify all three cards exist
            for card in cards:
                results = await store.get_results_for_intent(card["intent_id"])
                assert len(results) == 1

            # Dismiss the second card only
            await store.delete_result(cards[1]["result_id"], session_id)

            # Verify card 2 is gone, but cards 1 and 3 remain
            results_1 = await store.get_results_for_intent(cards[0]["intent_id"])
            results_2 = await store.get_results_for_intent(cards[1]["intent_id"])
            results_3 = await store.get_results_for_intent(cards[2]["intent_id"])

            assert len(results_1) == 1, "Card 1 should still exist"
            assert len(results_2) == 0, "Card 2 should be dismissed"
            assert len(results_3) == 1, "Card 3 should still exist"

        finally:
            await store.close()

    async def test_multiple_failed_cards_selective_dismissal(self, tmp_path):
        """Dismissing one failed card doesn't affect other failed cards."""
        from src.session.store import SessionStore

        db_path = tmp_path / "test_multiple_failed.db"
        store = SessionStore(db_path)
        await store.initialize()

        try:
            session_id = await store.create_session()
            topic_id, _ = await store.find_or_create_topic(
                label="Multi Failed Test",
                session_id=session_id,
                topic_type="project",
            )

            # Create three failed cards
            cards = []
            for i in range(1, 4):
                utterance_id = await store.create_utterance(
                    session_id=session_id,
                    raw_text=f"Test failed {i}",
                )

                bead_ref = f"adc-failed-{i}"
                intent_id = await store.create_intent(
                    utterance_id=utterance_id,
                    session_id=session_id,
                    project_slug="adc",
                    intent_type="task-profile",
                    bead_ref=bead_ref,
                    topic_id=topic_id,
                )

                result_id = await store.create_result(
                    intent_id=intent_id,
                    topic_id=topic_id,
                    session_id=session_id,
                    summary=f"Task Failed {i}",
                    data={
                        "bead_ref": bead_ref,
                        "failure_reason": f"Failure {i}",
                        "error_type": "test_error",
                    },
                    urgency="high",
                )
                cards.append({"bead_ref": bead_ref, "intent_id": intent_id, "result_id": result_id})

            # Verify all three cards exist
            for card in cards:
                results = await store.get_results_for_intent(card["intent_id"])
                assert len(results) == 1

            # Dismiss the first and third cards
            await store.delete_result(cards[0]["result_id"], session_id)
            await store.delete_result(cards[2]["result_id"], session_id)

            # Verify cards 1 and 3 are gone, but card 2 remains
            results_1 = await store.get_results_for_intent(cards[0]["intent_id"])
            results_2 = await store.get_results_for_intent(cards[1]["intent_id"])
            results_3 = await store.get_results_for_intent(cards[2]["intent_id"])

            assert len(results_1) == 0, "Card 1 should be dismissed"
            assert len(results_2) == 1, "Card 2 should still exist"
            assert len(results_3) == 0, "Card 3 should be dismissed"

        finally:
            await store.close()

    async def test_mixed_stuck_and_failed_cards_selective_dismissal(self, tmp_path):
        """Dismissing cards works correctly when stuck and failed cards are mixed."""
        from src.session.store import SessionStore

        db_path = tmp_path / "test_mixed_cards.db"
        store = SessionStore(db_path)
        await store.initialize()

        try:
            session_id = await store.create_session()
            topic_id, _ = await store.find_or_create_topic(
                label="Mixed Cards Test",
                session_id=session_id,
                topic_type="project",
            )

            cards = []

            # Create stuck card 1
            utterance_id = await store.create_utterance(
                session_id=session_id,
                raw_text="Stuck 1",
            )
            intent_id_1 = await store.create_intent(
                utterance_id=utterance_id,
                session_id=session_id,
                project_slug="adc",
                intent_type="task-profile",
                bead_ref="adc-stuck-1",
                topic_id=topic_id,
            )
            result_id_1 = await store.create_result(
                intent_id=intent_id_1,
                topic_id=topic_id,
                session_id=session_id,
                summary="Stuck 1",
                data={"bead_id": "adc-stuck-1", "stuck_reason": "Stuck 1"},
                urgency="high",
            )
            cards.append({"type": "stuck", "intent_id": intent_id_1, "result_id": result_id_1})

            # Create failed card 1
            utterance_id = await store.create_utterance(
                session_id=session_id,
                raw_text="Failed 1",
            )
            intent_id_2 = await store.create_intent(
                utterance_id=utterance_id,
                session_id=session_id,
                project_slug="adc",
                intent_type="task-profile",
                bead_ref="adc-failed-1",
                topic_id=topic_id,
            )
            result_id_2 = await store.create_result(
                intent_id=intent_id_2,
                topic_id=topic_id,
                session_id=session_id,
                summary="Failed 1",
                data={"bead_ref": "adc-failed-1", "failure_reason": "Failed 1", "error_type": "test"},
                urgency="high",
            )
            cards.append({"type": "failed", "intent_id": intent_id_2, "result_id": result_id_2})

            # Create stuck card 2
            utterance_id = await store.create_utterance(
                session_id=session_id,
                raw_text="Stuck 2",
            )
            intent_id_3 = await store.create_intent(
                utterance_id=utterance_id,
                session_id=session_id,
                project_slug="adc",
                intent_type="task-profile",
                bead_ref="adc-stuck-2",
                topic_id=topic_id,
            )
            result_id_3 = await store.create_result(
                intent_id=intent_id_3,
                topic_id=topic_id,
                session_id=session_id,
                summary="Stuck 2",
                data={"bead_id": "adc-stuck-2", "stuck_reason": "Stuck 2"},
                urgency="high",
            )
            cards.append({"type": "stuck", "intent_id": intent_id_3, "result_id": result_id_3})

            # Verify all cards exist
            for card in cards:
                results = await store.get_results_for_intent(card["intent_id"])
                assert len(results) == 1

            # Dismiss the failed card and second stuck card
            await store.delete_result(cards[1]["result_id"], session_id)  # failed card
            await store.delete_result(cards[2]["result_id"], session_id)  # stuck card 2

            # Verify selective dismissal worked
            results_1 = await store.get_results_for_intent(cards[0]["intent_id"])
            results_2 = await store.get_results_for_intent(cards[1]["intent_id"])
            results_3 = await store.get_results_for_intent(cards[2]["intent_id"])

            assert len(results_1) == 1, "Stuck card 1 should still exist"
            assert len(results_2) == 0, "Failed card should be dismissed"
            assert len(results_3) == 0, "Stuck card 2 should be dismissed"

        finally:
            await store.close()


# === End-to-End Persistence Tests ===============================================


@pytest.mark.asyncio
class TestEndToEndDismissalPersistence:
    """Comprehensive end-to-end tests for dismissal persistence."""

    async def test_complete_dismissal_flow_with_topic_reload(self, tmp_path):
        """Test complete flow: create card → dismiss → reload topics → verify gone."""
        from src.session.store import SessionStore

        db_path = tmp_path / "test_e2e_flow.db"
        store = SessionStore(db_path)
        await store.initialize()

        try:
            session_id = await store.create_session()

            # Create utterance
            utterance_id = await store.create_utterance(
                session_id=session_id,
                raw_text="Deploy to production",
            )

            # Create topic
            topic_id, _ = await store.find_or_create_topic(
                label="Production Deployment",
                session_id=session_id,
                topic_type="project",
            )

            # Create intent with stuck scenario
            bead_ref = "adc-deploy-stuck"
            intent_id = await store.create_intent(
                utterance_id=utterance_id,
                session_id=session_id,
                project_slug="adc",
                intent_type="task-profile",
                bead_ref=bead_ref,
                topic_id=topic_id,
            )

            # Create stuck result
            result_id = await store.create_result(
                intent_id=intent_id,
                topic_id=topic_id,
                session_id=session_id,
                summary="Task stuck — needs your input",
                data={
                    "bead_id": bead_ref,
                    "stuck_reason": "Missing credentials",
                    "refusal_count": 3,
                    "message": "Task blocked",
                },
                urgency="high",
            )

            # Step 1: First topic load - card appears
            import json
            topics_first_load = await store.get_active_topics(session_id)
            assert len(topics_first_load) >= 1

            results_first_load = await store.get_results_for_intent(intent_id)
            assert len(results_first_load) == 1
            assert json.loads(results_first_load[0]["data"])["bead_id"] == bead_ref

            # Step 2: User dismisses the card
            deletion_result = await store.delete_result(result_id, session_id)
            assert deletion_result["result_deleted"] == 1

            # Step 3: Topic reload (simulating page refresh) - card should be gone
            topics_second_load = await store.get_active_topics(session_id)
            assert len(topics_second_load) >= 1

            results_second_load = await store.get_results_for_intent(intent_id)
            assert len(results_second_load) == 0, "Dismissed card should not appear on reload"

            # Step 4: Topic still exists, just the card is gone
            topic_still_exists = next((t for t in topics_second_load if t["id"] == topic_id), None)
            assert topic_still_exists is not None

        finally:
            await store.close()

    async def test_dismissal_state_survives_database_reopen(self, tmp_path):
        """Dismissal state persists even after completely closing and reopening the database."""
        from src.session.store import SessionStore

        db_path = tmp_path / "test_db_reopen.db"

        # First session: create and dismiss
        store1 = SessionStore(db_path)
        await store1.initialize()

        session_id = await store1.create_session()
        utterance_id = await store1.create_utterance(
            session_id=session_id,
            raw_text="Test DB reopen",
        )

        topic_id, _ = await store1.find_or_create_topic(
            label="DB Reopen Test",
            session_id=session_id,
            topic_type="project",
        )

        bead_ref = "adc-db-reopen"
        intent_id = await store1.create_intent(
            utterance_id=utterance_id,
            session_id=session_id,
            project_slug="adc",
            intent_type="task-profile",
            bead_ref=bead_ref,
            topic_id=topic_id,
        )

        result_id = await store1.create_result(
            intent_id=intent_id,
            topic_id=topic_id,
            session_id=session_id,
            summary="Test card",
            data={"bead_id": bead_ref, "stuck_reason": "DB reopen test"},
            urgency="high",
        )

        # Verify it exists
        results_before = await store1.get_results_for_intent(intent_id)
        assert len(results_before) == 1

        # Dismiss it
        await store1.delete_result(result_id, session_id)

        # Verify it's gone
        results_after = await store1.get_results_for_intent(intent_id)
        assert len(results_after) == 0

        # Close the database completely
        await store1.close()

        # Reopen the database with a new SessionStore instance
        store2 = SessionStore(db_path)
        await store2.initialize()

        try:
            # Verify the card is still dismissed
            results_reopened = await store2.get_results_for_intent(intent_id)
            assert len(results_reopened) == 0, "Card should stay dismissed after DB reopen"

            # Verify other data is intact
            session = await store2.get_session(session_id)
            assert session is not None, "Session should still exist"

            topics = await store2.get_active_topics(session_id)
            assert len(topics) >= 1, "Topic should still exist"

        finally:
            await store2.close()
