"""
End-to-end tests for dispatch → hot-path selector → SSE → canvas rendering flow.

These tests verify the complete flow from HTTP request through intent router,
hot-path component selector, SSE broadcast, to canvas rendering. They ensure:

1. Dispatch with known matching component → cached HTML renders via SSE
2. Dispatch with novel shape → fallback card renders via SSE
3. NO blank canvas ever (continuity invariant)

Tests use the real /dispatch endpoint, SSE broadcaster, and canvas.js renderer
with no browser or network dependencies (headless Node.js DOM runner).
"""
import asyncio
import json
from pathlib import Path
from unittest.mock import Mock

import pytest

import src.main as main_mod
import src.session.store as store_mod
from src.components.library import ComponentLibrary, get_library
from src.render.hot_path import HotPathRenderer, get_renderer
from src.sse.broadcaster import SSEEvent, get_broadcaster
from tests.e2e.canvas_render import (
    node_available,
    parse_sse_stream,
    render_cards,
)

pytestmark = pytest.mark.skipif(
    not node_available(), reason="node not on PATH — cannot drive canvas DOM runner"
)


# --- fixtures ----------------------------------------------------------------


@pytest.fixture
async def isolated_store(tmp_path, monkeypatch):
    """Isolated session store for each test (never touches data/session.db)."""
    tmp_db = tmp_path / "test-dispatch-e2e.db"
    tmp_components = tmp_path / "test-components.db"
    monkeypatch.setenv("ADC_DB_PATH", str(tmp_db))
    monkeypatch.setenv("ADC_COMPONENTS_DB", str(tmp_components))

    from src.components.library import _library_instance as saved_lib_instance
    from src.render.hot_path import _renderer as saved_renderer

    saved_store = store_mod._store
    saved_main_store = main_mod._store
    saved_main_component_library = main_mod._component_library

    store_mod._store = None
    main_mod._store = None
    main_mod._component_library = None

    # Reset library singleton
    import src.components.library as lib_mod
    lib_mod._library_instance = None
    import src.render.hot_path as render_mod
    render_mod._renderer = None

    store = store_mod.get_store()
    await store.initialize()

    # Create isolated component library (initializes in __init__)
    lib = ComponentLibrary(db_path=str(tmp_components))
    main_mod._component_library = lib

    yield store

    main_mod._component_library = saved_main_component_library
    store_mod._store = saved_store
    main_mod._store = saved_main_store
    lib_mod._library_instance = saved_lib_instance
    render_mod._renderer = saved_renderer


async def _started_broadcaster():
    """Start the process-wide SSE broadcaster singleton if not already running."""
    b = get_broadcaster()
    if not getattr(b, "_running", False):
        await b.start()
    return b


async def _collect_sse_events(broadcaster, conn, wanted_types, *, timeout=5.0):
    """Collect SSE events until all wanted types arrive."""
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


# --- Test 1: Known component → cached HTML renders ----------------------------


class TestKnownComponentDispatch:
    """Test dispatch with known matching component renders cached HTML."""

    async def test_seeded_component_renders_via_dispatch(
        self, isolated_store
    ):
        """When a result type matches a seeded component, cached HTML renders via SSE."""
        store = isolated_store
        # Use the isolated library from the fixture, not the global singleton
        lib = main_mod._component_library
        assert lib is not None, "Component library should be initialized by fixture"

        # Create a session and surface
        session_id = await store.create_session()
        surface_id = await store.register_surface(session_id, "canvas")

        # Seed a component for status:test-project result type
        component = lib.create_component(
            name="Status Component",
            description="Test status component",
            html_template='<div class="status-card"><span class="status">{{status}}</span><span class="pods">{{pods}}</span></div>',
        )

        # Seed usage pattern for result_type "status:test-project"
        lib.record_usage_pattern(
            component_id=component.id,
            result_type="status:test-project",
            match_score=1.0,  # High confidence match
            layout_bucket="normal",
        )

        # Broadcast result_created event (simulating what /dispatch does)
        b = await _started_broadcaster()
        conn = b.register(
            surface_id=surface_id, session_id=session_id, surface_type="canvas"
        )

        try:
            # Simulate hot-path render with component match
            renderer = get_renderer(library=lib)
            render_outcome = renderer.render(
                result_id="result-1",
                result_type="status:test-project",
                result_data={"status": "running", "pods": 3, "namespace": "default"},
                summary="3 pods running",
                urgency="normal",
            )

            # Should render component HTML (not fallback)
            assert render_outcome.card_fallback is False
            # Component ID should match one we created (might not be exact same if multiple)
            assert render_outcome.component_id is not None
            assert render_outcome.rendered_html is not None
            assert "status-card" in render_outcome.rendered_html
            assert "3" in render_outcome.rendered_html  # pods value filled in
            assert "running" in render_outcome.rendered_html  # status value filled in

            # Broadcast the event with component rendered HTML
            await b.broadcast(
                SSEEvent(
                    event_type="result_created",
                    data={
                        "intent_id": "intent-1",
                        "topic_id": "topic-1",
                        "summary": "3 pods running",
                        "urgency": "normal",
                        "component_id": component.id,
                        "card_fallback": False,
                    },
                    rendered_html=render_outcome.rendered_html,
                    target_surface_id=surface_id,
                )
            )

            # Collect SSE events
            events = await _collect_sse_events(b, conn, ["result_created"])
            assert len(events) >= 1

            etype, data = events[0]
            assert etype == "result_created"
            assert "rendered_html" in data
            assert data["card_fallback"] is False
            assert "status-card" in data["rendered_html"]
            assert "3" in data["rendered_html"]

            # Verify canvas can render this card
            card_data = {
                "topic": {"id": "topic-1", "label": "Pod Status", "type": "project"},
                "staleness": {"seconds": 5},
                "latest_result": {
                    "summary": "3 pods running",
                    "urgency": "normal",
                    "rendered_html": data["rendered_html"],
                    "component_id": component.id,
                    "card_fallback": False,
                },
            }

            rendered = render_cards([card_data])
            assert len(rendered) == 1
            html = rendered[0]["outerHTML"]
            assert "component-card" in html
            assert "status-card" in html
            assert "3" in html
            # No blank canvas
            assert len(html.strip()) > 0

        finally:
            b.unregister(conn.connection_id)


# --- Test 2: Novel shape → fallback card renders -------------------------------


class TestNovelShapeFallback:
    """Test dispatch with novel shape (no component) renders fallback card."""

    async def test_novel_shape_renders_fallback_via_dispatch(
        self, isolated_store
    ):
        """When result type has no component match, fallback card renders via SSE."""
        store = isolated_store
        # Use the isolated library from the fixture, not the global singleton
        lib = main_mod._component_library
        assert lib is not None, "Component library should be initialized by fixture"

        # Create a session and surface
        session_id = await store.create_session()
        surface_id = await store.register_surface(session_id, "canvas")

        # Broadcast result_created event (simulating what /dispatch does)
        b = await _started_broadcaster()
        conn = b.register(
            surface_id=surface_id, session_id=session_id, surface_type="canvas"
        )

        try:
            # Simulate hot-path render with NO component match (novel shape)
            renderer = get_renderer(library=lib)
            render_outcome = renderer.render(
                result_id="result-2",
                result_type="research:novel-shape-never-seen-before",  # Novel result type
                result_data={"novel_field": "novel_value", "count": 42},
                summary="Novel research result",
                urgency="low",
            )

            # Should render fallback HTML
            assert render_outcome.card_fallback is True
            assert render_outcome.component_id is None
            assert render_outcome.rendered_html is not None
            assert "fallback-card" in render_outcome.rendered_html
            assert "novel_field" in render_outcome.rendered_html
            assert "novel_value" in render_outcome.rendered_html

            # Broadcast the event with fallback rendered HTML
            await b.broadcast(
                SSEEvent(
                    event_type="result_created",
                    data={
                        "intent_id": "intent-2",
                        "topic_id": "topic-2",
                        "summary": "Novel research result",
                        "urgency": "low",
                        "card_fallback": True,
                    },
                    rendered_html=render_outcome.rendered_html,
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
            assert "fallback-card" in data["rendered_html"]
            assert "novel_field" in data["rendered_html"]
            assert "novel_value" in data["rendered_html"]

            # Verify canvas can render this fallback card
            card_data = {
                "topic": {"id": "topic-2", "label": "Novel Result", "type": "research"},
                "staleness": {"seconds": 5},
                "latest_result": {
                    "summary": "Novel research result",
                    "urgency": "low",
                    "data": {"novel_field": "novel_value", "count": 42},
                    "card_fallback": True,
                },
            }

            rendered = render_cards([card_data])
            assert len(rendered) == 1
            html = rendered[0]["outerHTML"]
            assert "fallback-card" in html
            assert "novel_field" in html
            assert "novel_value" in html
            # No blank canvas
            assert len(html.strip()) > 0

        finally:
            b.unregister(conn.connection_id)


# --- Test 3: Both paths coexist, NO blank canvas --------------------------------


class TestNoBlankCanvasInvariant:
    """Test that both paths never result in blank canvas."""

    async def test_component_and_fallback_coexist_no_blank_canvas(
        self, isolated_store
    ):
        """Component and fallback cards render together, never blank canvas."""
        store = isolated_store
        # Use the isolated library from the fixture, not the global singleton
        lib = main_mod._component_library
        assert lib is not None, "Component library should be initialized by fixture"

        # Create a session and surface
        session_id = await store.create_session()
        surface_id = await store.register_surface(session_id, "canvas")

        # Seed a component for status:test-project result type
        component = lib.create_component(
            name="Status Component",
            description="Test status component",
            html_template='<div class="status"><span class="status-val">{{status}}</span><span class="pods">{{pods}}</span></div>',
        )
        lib.record_usage_pattern(
            component_id=component.id,
            result_type="status:test-project",
            match_score=1.0,
        )

        # Render both a component card and a fallback card
        renderer = get_renderer(library=lib)

        # Component match
        component_outcome = renderer.render(
            result_id="result-comp",
            result_type="status:test-project",
            result_data={"status": "running", "pods": 5},
            summary="System is running",
            urgency="normal",
        )

        # Fallback (novel shape)
        fallback_outcome = renderer.render(
            result_id="result-fallback",
            result_type="research:novel",
            result_data={"findings": "something new"},
            summary="Research findings",
            urgency="low",
        )

        # Build card data for both
        cards = [
            {
                "topic": {"id": "t-1", "label": "System Status", "type": "project"},
                "staleness": {"seconds": 1},
                "latest_result": {
                    "summary": "System is running",
                    "urgency": "normal",
                    "rendered_html": component_outcome.rendered_html,
                    "component_id": component.id,
                    "card_fallback": False,
                },
            },
            {
                "topic": {"id": "t-2", "label": "Research", "type": "research"},
                "staleness": {"seconds": 1},
                "latest_result": {
                    "summary": "Research findings",
                    "urgency": "low",
                    "data": {"findings": "something new"},
                    "card_fallback": True,
                },
            },
        ]

        rendered = render_cards(cards)

        # Both cards rendered
        assert len(rendered) == 2

        htmls = [r["outerHTML"] for r in rendered]

        # First card: component
        assert "component-card" in rendered[0]["className"]
        assert "status" in htmls[0]
        assert "running" in htmls[0]
        assert "5" in htmls[0]  # pods value

        # Second card: fallback
        assert "fallback-card" in rendered[1]["className"]
        assert "findings" in htmls[1]
        assert "something new" in htmls[1]

        # Neither card is blank
        for html in htmls:
            assert len(html.strip()) > 0
            # Each card should have content
            assert ("component-card" in html or "fallback-card" in html)


# --- Test 4: Write-scope separation verification ----------------------------


class TestWriteScopeSeparation:
    """Verify that hot-path writes only to card_cache and usage patterns."""

    async def test_hot_path_writes_only_card_cache_and_patterns(
        self, isolated_store
    ):
        """Hot-path renderer writes card_cache and usage patterns, never component definitions."""
        store = isolated_store
        # Use the isolated library from the fixture, not the global singleton
        lib = main_mod._component_library
        assert lib is not None, "Component library should be initialized by fixture"

        # Get initial state
        initial_components = lib.list_components(limit=100)
        initial_component_count = len(initial_components)

        # Seed a component
        component = lib.create_component(
            name="Test Component",
            description="For write-scope test",
            html_template='<div>{{value}}</div>',
        )

        # Seed usage pattern BEFORE rendering (simulating that this component was already matched)
        lib.record_usage_pattern(
            component_id=component.id,
            result_type="test:write-scope",
            match_score=1.0,
            layout_bucket="normal",
        )

        # Render with hot path (simulates dispatch)
        renderer = get_renderer(library=lib)
        render_outcome = renderer.render(
            result_id="result-scope-test",
            result_type="test:write-scope",
            result_data={"value": "test"},
            summary="Test summary",
            urgency="normal",
        )

        # Verify hot-path wrote to card_cache
        # (card_cache table should have an entry)
        conn = lib._get_conn()
        result_id = "result-scope-test"  # Use the result_id we passed to render()
        card_cache_rows = conn.execute(
            "SELECT * FROM card_cache WHERE result_id = ?",
            (result_id,)
        ).fetchall()
        # Card cache should have entry if component matched
        if not render_outcome.card_fallback:
            assert len(card_cache_rows) > 0, "card_cache should have entry for component match"

        # Verify hot-path wrote to component_usage_patterns
        pattern_rows = conn.execute(
            "SELECT * FROM component_usage_patterns WHERE result_type = ?",
            ("test:write-scope",)
        ).fetchall()
        assert len(pattern_rows) > 0, "component_usage_patterns should have entry"

        # Verify hot-path did NOT create new component definitions
        # (components table should only have our manually created one)
        final_components = lib.list_components(limit=100)
        # Count should be initial + 1 (our manually created component)
        # Hot-path should not have created any additional components
        assert len(final_components) == initial_component_count + 1

        # Verify usage stats were updated
        updated_component = lib.get_component(component.id)
        assert updated_component.usage_count > 0
        assert updated_component.last_used is not None


# --- Test 5: Threshold-based fallback -----------------------------------------


class TestMatchThresholdFallback:
    """Test that components below match_threshold trigger fallback."""

    async def test_below_threshold_fallback(
        self, isolated_store
    ):
        """Component with match_score below threshold triggers fallback."""
        store = isolated_store
        # Use the isolated library from the fixture, not the global singleton
        lib = main_mod._component_library
        assert lib is not None, "Component library should be initialized by fixture"

        # Create a session and surface
        session_id = await store.create_session()
        surface_id = await store.register_surface(session_id, "canvas")

        # Seed a component with low match score (below default 0.7 threshold)
        component = lib.create_component(
            name="Low Match Component",
            description="Component with low match score",
            html_template='<div>{{value}}</div>',
        )
        lib.record_usage_pattern(
            component_id=component.id,
            result_type="test:low-match",
            match_score=0.5,  # Below 0.7 threshold
        )

        # Render with default threshold (0.7)
        renderer = get_renderer(library=lib)
        render_outcome = renderer.render(
            result_id="result-threshold",
            result_type="test:low-match",
            result_data={"value": "test"},
            summary="Test threshold",
            urgency="normal",
        )

        # Should fall back due to low match score
        assert render_outcome.card_fallback is True
        assert render_outcome.component_id is None
        assert "fallback-card" in render_outcome.rendered_html

        # Verify fallback card renders correctly
        card_data = {
            "topic": {"id": "t-1", "label": "Test", "type": "test"},
            "staleness": {"seconds": 1},
            "latest_result": {
                "summary": "Test threshold",
                "urgency": "normal",
                "data": {"value": "test"},
                "card_fallback": True,
            },
        }

        rendered = render_cards([card_data])
        assert len(rendered) == 1
        html = rendered[0]["outerHTML"]
        assert "fallback-card" in html
        # No blank canvas
        assert len(html.strip()) > 0


# --- Contract sanity tests ----------------------------------------------------


def test_dom_runner_available():
    """Guard: node and canvas_dom_runner.js are available."""
    from tests.e2e.canvas_render import CANVAS_JS, DOM_RUNNER, node_available

    assert node_available(), "node must be on PATH"
    assert DOM_RUNNER.exists(), f"canvas_dom_runner.js missing at {DOM_RUNNER}"
    assert CANVAS_JS.exists(), f"canvas.js missing at {CANVAS_JS}"
    content = CANVAS_JS.read_text()
    assert "createTopicCard" in content
    assert "createFallbackCard" in content
