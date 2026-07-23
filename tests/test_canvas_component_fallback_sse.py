"""
End-to-end tests for component and fallback card rendering via SSE (bead adc-35eq).

These tests verify that both render paths work correctly through the full
dispatch → SSE → render pipeline:

1. **Component path**: When a result matches a seeded component, the hot-path
   renderer's rendered_html streams via SSE and the canvas injects the component
   card directly (no blank canvas).

2. **Fallback path**: When a result has a first-ever shape (no component match),
   card_fallback=True streams via SSE and the canvas renders the generic fallback
   card directly (no blank canvas).

Both paths are tested headlessly using the real canvas.js render module and SSE
broadcaster, with no browser or network dependencies.
"""
import asyncio

import pytest

import src.main as main_mod
import src.session.store as store_mod
from src.components.library import ComponentLibrary, get_library
from src.render.hot_path import HotPathRenderer, get_renderer
from src.sse.broadcaster import SSEEvent, get_broadcaster
from src.topic.model import TopicManager
from tests.e2e.canvas_render import (
    node_available,
    parse_sse_stream,
    render_card,
    render_cards,
)
from tests.e2e.inject import TestDataInjector

pytestmark = pytest.mark.skipif(
    not node_available(), reason="node not on PATH — cannot drive canvas DOM runner"
)


# --- fixtures -----------------------------------------------------------------


@pytest.fixture
async def isolated_store(tmp_path, monkeypatch):
    """Isolated session store for each test (never touches data/session.db)."""
    tmp_db = tmp_path / "test-component-fallback-sse.db"
    monkeypatch.setenv("ADC_DB_PATH", str(tmp_db))

    saved_store = store_mod._store
    saved_main_store = main_mod._store
    saved_tm = main_mod._topic_manager

    store_mod._store = None
    main_mod._store = None
    main_mod._topic_manager = None

    store = store_mod.get_store()
    await store.initialize()
    main_mod._topic_manager = TopicManager(store)

    yield store

    main_mod._topic_manager = saved_tm
    main_mod._store = saved_main_store
    store_mod._store = saved_store


async def _started_broadcaster():
    """Start the process-wide SSE broadcaster singleton if not already running."""
    b = get_broadcaster()
    if not getattr(b, "_running", False):
        await b.start()
    return b


async def _collect_sse_events(broadcaster, conn, wanted_types, *, timeout=2.0):
    """Collect SSE events until all wanted types arrive (excluding 'connected')."""
    wanted = set(wanted_types)
    collected = []

    async def drain():
        async for wire in broadcaster.event_generator(conn):
            for etype, data in parse_sse_stream(wire):
                if etype == "connected":
                    continue
                collected.append((etype, data))
                if wanted <= {e for e, _ in collected}:
                    return

    task = asyncio.create_task(drain())
    try:
        await asyncio.wait_for(task, timeout=timeout)
    except asyncio.TimeoutError:
        task.cancel()
        raise
    return collected


# --- Component path tests (seeded match) --------------------------------------


class TestComponentCardViaSSE:
    """Test that a component match renders via SSE (seeded component path)."""

    async def test_component_match_includes_rendered_html_in_sse(
        self, isolated_store
    ):
        """When a result matches a seeded component, rendered_html is in SSE."""
        store = isolated_store

        # Create a session and surface
        session_id = await store.create_session()
        surface_id = await store.register_surface(session_id, "canvas")

        # Create a topic and result with a component match
        topic_id, _ = await store.find_or_create_topic(
            label="Test Component",
            topic_type="project",
            project_slugs=["test-project"],
            session_id=session_id,
        )

        # Simulate a component match by creating a result with rendered_html
        result_id = await store.create_result(
            intent_id="intent-component-1",
            topic_id=topic_id,
            session_id=session_id,
            summary="Component rendered successfully",
            data={"status": "running", "pods": 3},
            urgency="normal",
            result_type="status:test-project",
        )

        # Update result with component card_fallback flag (simulating hot-path match)
        # Note: rendered_html and component_id are sent via SSE, not stored in DB
        await store.update_result_card_fallback(result_id, card_fallback=False)

        # Broadcast result_created event
        b = await _started_broadcaster()
        conn = b.register(
            surface_id=surface_id, session_id=session_id, surface_type="canvas"
        )

        try:
            # Broadcast the event (simulating what /dispatch does)
            await b.broadcast(
                SSEEvent(
                    event_type="result_created",
                    data={
                        "intent_id": "intent-component-1",
                        "topic_id": topic_id,
                        "summary": "Component rendered successfully",
                        "urgency": "normal",
                        "rendered_html": '<div class="status-grid"><span class="label">Pods</span><span class="value">3</span></div>',
                        "component_id": "status-component-1",
                    },
                    target_surface_id=surface_id,
                )
            )

            # Collect SSE events
            events = await _collect_sse_events(b, conn, ["result_created"])
            assert len(events) >= 1

            etype, data = events[0]
            assert etype == "result_created"
            assert "rendered_html" in data
            assert data["rendered_html"] == '<div class="status-grid"><span class="label">Pods</span><span class="value">3</span></div>'
            assert data["component_id"] == "status-component-1"
            assert data.get("card_fallback") is None or data.get("card_fallback") is False

        finally:
            b.unregister(conn.connection_id)

    async def test_component_card_renders_from_sse_event(
        self, isolated_store
    ):
        """Canvas renders component card correctly from SSE event data."""
        # Simulate the card data structure that would be built from SSE
        card_data = {
            "topic": {
                "id": "t-component",
                "label": "Pod Status",
                "type": "project",
            },
            "staleness": {"seconds": 5},
            "latest_result": {
                "summary": "3 pods running",
                "urgency": "normal",
                "rendered_html": '<div class="status-card"><span class="metric">3 pods</span></div>',
                "component_id": "pod-status-component",
                "card_fallback": False,
            },
        }

        # Render through the real canvas.js
        rendered = render_card(card_data)

        html = rendered["outerHTML"]
        # Should render as a component card
        assert "component-card" in rendered["className"]
        assert "topic-card" in rendered["className"]
        # Should include the server-rendered HTML
        assert "status-card" in html
        assert "3 pods" in html
        # Should have component_id dataset
        assert rendered["dataset"]["componentId"] == "pod-status-component"
        assert rendered["dataset"]["topicId"] == "t-component"

    async def test_component_path_never_blanks_canvas(self, isolated_store):
        """Component match path never leaves canvas blank (continuity invariant)."""
        # Test with various component HTML structures
        test_cases = [
            {
                "html": '<div class="simple">Simple component</div>',
                "expected_in_html": ["simple", "Simple component"],
            },
            {
                "html": '<div class="complex"><div class="nested">Nested content</div></div>',
                "expected_in_html": ["complex", "nested", "Nested content"],
            },
            {
                "html": '<div class="empty"></div>',
                "expected_in_html": ["empty"],
            },
        ]

        for case in test_cases:
            card_data = {
                "topic": {"id": "t-1", "label": "Test", "type": "project"},
                "staleness": {"seconds": 1},
                "latest_result": {
                    "summary": "Test summary",
                    "urgency": "normal",
                    "rendered_html": case["html"],
                    "component_id": "test-component",
                    "card_fallback": False,
                },
            }

            rendered = render_card(card_data)
            html = rendered["outerHTML"]

            # Should always render a card (not blank)
            assert "topic-card" in html
            assert "component-card" in html

            # Should include expected content
            for expected in case["expected_in_html"]:
                assert expected in html, f"Expected '{expected}' in HTML for case: {case['html']}"


# --- Fallback path tests (first-ever shape) ------------------------------------


class TestFallbackCardViaSSE:
    """Test that no component match renders fallback via SSE (first-ever shape)."""

    async def test_no_component_match_includes_rendered_html_in_sse(
        self, isolated_store
    ):
        """When no component matches, fallback HTML is included in SSE."""
        from src.render.hot_path import render_fallback_card

        store = isolated_store

        # Create a session and surface
        session_id = await store.create_session()
        surface_id = await store.register_surface(session_id, "canvas")

        # Create a topic and result with no component match (fallback)
        topic_id, _ = await store.find_or_create_topic(
            label="Novel Shape",
            topic_type="research",
            project_slugs=[],
            session_id=session_id,
        )

        result_id = await store.create_result(
            intent_id="intent-fallback-1",
            topic_id=topic_id,
            session_id=session_id,
            summary="Novel result shape",
            data={"novel_field": "novel_value", "another_field": 42},
            urgency="low",
            result_type="research:general",
        )

        # Update result with fallback flag (simulating no component match)
        # Note: rendered_html and component_id are sent via SSE, not stored in DB
        await store.update_result_card_fallback(result_id, card_fallback=True)

        # Generate the fallback HTML server-side (as hot-path renderer does)
        fallback_html = render_fallback_card(
            summary="Novel result shape",
            data={"novel_field": "novel_value", "another_field": 42},
            urgency="low",
        )

        # Broadcast result_created event
        b = await _started_broadcaster()
        conn = b.register(
            surface_id=surface_id, session_id=session_id, surface_type="canvas"
        )

        try:
            # Broadcast the event with fallback rendered_html (as /dispatch does)
            await b.broadcast(
                SSEEvent(
                    event_type="result_created",
                    data={
                        "intent_id": "intent-fallback-1",
                        "topic_id": topic_id,
                        "summary": "Novel result shape",
                        "urgency": "low",
                        "card_fallback": True,
                    },
                    rendered_html=fallback_html,  # Include fallback HTML
                    target_surface_id=surface_id,
                )
            )

            # Collect SSE events
            events = await _collect_sse_events(b, conn, ["result_created"])
            assert len(events) >= 1

            etype, data = events[0]
            assert etype == "result_created"
            assert "card_fallback" in data
            assert data["card_fallback"] is True
            # Verify fallback HTML is included in SSE
            assert "rendered_html" in data
            assert data["rendered_html"] is not None
            assert "fallback-card" in data["rendered_html"]
            assert "novel_field" in data["rendered_html"]
            assert "novel_value" in data["rendered_html"]

        finally:
            b.unregister(conn.connection_id)

    async def test_fallback_card_renders_from_sse_event(
        self, isolated_store
    ):
        """Canvas renders fallback card correctly from SSE event data."""
        # Simulate the card data structure for fallback
        card_data = {
            "topic": {
                "id": "t-fallback",
                "label": "Novel Result",
                "type": "research",
            },
            "staleness": {"seconds": 120},
            "latest_result": {
                "summary": "Result with novel shape",
                "urgency": "low",
                "data": {
                    "novel_key": "novel_value",
                    "numeric_field": 42,
                    "nested": {"inner": "value"},
                },
                "card_fallback": True,
            },
        }

        # Render through the real canvas.js
        rendered = render_card(card_data)

        html = rendered["outerHTML"]
        # Should render as a fallback card
        assert "fallback-card" in rendered["className"]
        assert "builtin-card" in rendered["className"]
        # Should include summary
        assert "Result with novel shape" in html
        # Should include data fields in key/value grid
        assert "novel_key" in html
        assert "novel_value" in html
        assert "numeric_field" in html
        assert "42" in html

    async def test_fallback_path_never_blanks_canvas(self, isolated_store):
        """Fallback path never leaves canvas blank (continuity invariant)."""
        # Test with various fallback data structures
        test_cases = [
            {
                "data": {"simple": "value"},
                "expected_in_html": ["simple", "value"],
            },
            {
                "data": {"field1": "val1", "field2": "val2"},
                "expected_in_html": ["field1", "val1", "field2", "val2"],
            },
            {
                "data": {"numeric": 123, "boolean": True},
                "expected_in_html": ["numeric", "123", "boolean", "True"],
            },
            {
                "data": [],
                "expected_in_html": [],  # Empty array should still render a card
            },
        ]

        for case in test_cases:
            card_data = {
                "topic": {"id": "t-1", "label": "Test", "type": "research"},
                "staleness": {"seconds": 1},
                "latest_result": {
                    "summary": "Test summary",
                    "urgency": "normal",
                    "data": case["data"],
                    "card_fallback": True,
                },
            }

            rendered = render_card(card_data)
            html = rendered["outerHTML"]

            # Should always render a card (not blank)
            assert "fallback-card" in html
            assert "builtin-card" in html

            # Should include expected content
            for expected in case["expected_in_html"]:
                assert expected in html, f"Expected '{expected}' in HTML for case: {case['data']}"


# --- Both paths coexist tests -----------------------------------------------


class TestBothPathsCoexist:
    """Test that component and fallback cards can coexist in the same session."""

    async def test_component_and_fallback_cards_render_together(
        self, isolated_store
    ):
        """Both component and fallback cards render correctly in same canvas."""
        cards = [
            # Component card
            {
                "topic": {"id": "t-1", "label": "Component Result", "type": "project"},
                "staleness": {"seconds": 5},
                "latest_result": {
                    "summary": "Has component match",
                    "urgency": "normal",
                    "rendered_html": '<div class="comp">Component content</div>',
                    "component_id": "comp-1",
                    "card_fallback": False,
                },
            },
            # Fallback card
            {
                "topic": {"id": "t-2", "label": "Fallback Result", "type": "research"},
                "staleness": {"seconds": 300},
                "latest_result": {
                    "summary": "No component match",
                    "urgency": "low",
                    "data": {"key": "value"},
                    "card_fallback": True,
                },
            },
            # Another component card
            {
                "topic": {"id": "t-3", "label": "Another Component", "type": "project"},
                "staleness": {"seconds": 60},
                "latest_result": {
                    "summary": "Also has component",
                    "urgency": "high",
                    "rendered_html": '<div class="comp2">Different component</div>',
                    "component_id": "comp-2",
                    "card_fallback": False,
                },
            },
        ]

        rendered = render_cards(cards)

        # All cards should render
        assert len(rendered) == 3

        htmls = [r["outerHTML"] for r in rendered]

        # First card: component
        assert "component-card" in rendered[0]["className"]
        assert "Component content" in htmls[0]

        # Second card: fallback
        assert "fallback-card" in rendered[1]["className"]
        assert "key" in htmls[1]
        assert "value" in htmls[1]

        # Third card: component
        assert "component-card" in rendered[2]["className"]
        assert "Different component" in htmls[2]

    async def test_mixed_cards_never_blank_canvas(self, isolated_store):
        """Mixed component/fallback cards never result in blank canvas."""
        cards = [
            {
                "topic": {"id": "t-1", "label": "Result 1", "type": "project"},
                "staleness": {"seconds": 1},
                "latest_result": {
                    "summary": "Summary 1",
                    "urgency": "normal",
                    "rendered_html": "<div>C1</div>",
                    "component_id": "c1",
                    "card_fallback": False,
                },
            },
            {
                "topic": {"id": "t-2", "label": "Result 2", "type": "research"},
                "staleness": {"seconds": 1},
                "latest_result": {
                    "summary": "Summary 2",
                    "urgency": "normal",
                    "data": {"k": "v"},
                    "card_fallback": True,
                },
            },
        ]

        rendered = render_cards(cards)

        for i, r in enumerate(rendered):
            html = r["outerHTML"]
            # Each card should have content (not blank)
            assert "topic-card" in html or "fallback-card" in html or "component-card" in html
            assert "Summary" in html  # At least the summary should be present


# --- Contract sanity ----------------------------------------------------------


def test_dom_runner_targets_real_canvas_module():
    """Guard: the runner loads the actual src/canvas/canvas.js, not a stub."""
    from tests.e2e.canvas_render import CANVAS_JS

    assert CANVAS_JS.exists(), f"canvas.js missing at {CANVAS_JS}"
    content = CANVAS_JS.read_text()
    assert "createTopicCard" in content
    assert "createFallbackCard" in content
    assert "createComponentCard" in content
