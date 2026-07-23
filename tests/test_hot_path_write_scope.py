"""
Test write-scope separation for hot-path renderer (bead adc-2jvu).

Acceptance criteria: The hot-path server (router, monitoring) writes ONLY
card_cache + usage-stat columns; it NEVER writes component definitions
(components, component_versions, component_tags tables).

This test verifies that the server respects the write-scope boundary:
- The UI-regen agent is the sole writer of component definitions
- The hot-path renderer only writes rendered cards and usage stats
"""
import pytest
import sqlite3
import tempfile
from pathlib import Path

from src.components.library import ComponentLibrary, get_library
from src.render.hot_path import HotPathRenderer, get_renderer


@pytest.fixture
def temp_db_path():
    """Create a temporary database for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    yield db_path
    # Cleanup
    Path(db_path).unlink(missing_ok=True)


@pytest.fixture
def library(temp_db_path):
    """Create a component library for testing."""
    lib = ComponentLibrary(temp_db_path)
    # Initialize schema
    conn = sqlite3.connect(temp_db_path)
    schema_path = Path(__file__).parent.parent / "data" / "schema.sql"
    if schema_path.exists():
        with open(schema_path) as f:
            conn.executescript(f.read())
    conn.close()
    yield lib
    lib.close()


@pytest.fixture
def renderer(library):
    """Create a hot-path renderer for testing."""
    return HotPathRenderer(library=library)


class TestWriteScopeSeparation:
    """Verify hot-path renderer never writes component definitions."""

    def test_renderer_writes_only_card_cache_and_stats(self, library, renderer):
        """Hot-path render writes card_cache and usage stats, never component definitions."""
        # Seed a component and usage pattern (simulating UI-regen agent work)
        component = library.create_component(
            name="status-test",
            description="Status component for test project",
            html_template="<div>{{summary}}</div>",
            change_note="Initial version"
        )
        library.record_usage_pattern(
            component_id=component.id,
            result_type="status:test-project",
            match_score=0.95
        )

        # Count rows before render
        def count_table_rows(table_name):
            conn = sqlite3.connect(library.db_path)
            cursor = conn.execute(f"SELECT COUNT(*) FROM {table_name}")
            count = cursor.fetchone()[0]
            conn.close()
            return count

        components_before = count_table_rows("components")
        versions_before = count_table_rows("component_versions")
        tags_before = count_table_rows("component_tags")
        cache_before = count_table_rows("card_cache")

        # Run hot-path render (what the dispatch flow does)
        render_outcome = renderer.render(
            result_id="test-result-123",
            result_type="status:test-project",
            result_data={"summary": "Test summary"},
            summary="Test summary",
        )

        # Verify outcome is successful (not fallback)
        assert render_outcome.rendered_html is not None
        assert render_outcome.card_fallback is False
        assert render_outcome.component_id == component.id

        # Count rows after render
        components_after = count_table_rows("components")
        versions_after = count_table_rows("component_versions")
        tags_after = count_table_rows("component_tags")
        cache_after = count_table_rows("card_cache")

        # Verify component definition tables are UNCHANGED
        assert components_after == components_before, \
            "hot-path renderer wrote to components table (write-scope violation)"
        assert versions_after == versions_before, \
            "hot-path renderer wrote to component_versions table (write-scope violation)"
        assert tags_after == tags_before, \
            "hot-path renderer wrote to component_tags table (write-scope violation)"

        # Verify card_cache WAS written (the only table it should write)
        assert cache_after == cache_before + 1, \
            "hot-path renderer did not write to card_cache"

    def test_renderer_updates_component_usage_stats(self, library, renderer):
        """Hot-path render updates usage_count and last_used on component."""
        # Seed component with usage pattern
        component = library.create_component(
            name="test-component",
            description="Test component",
            html_template="<div>{{data}}</div>",
        )
        library.record_usage_pattern(
            component_id=component.id,
            result_type="status:test",
            match_score=0.9
        )

        # Get initial usage stats
        conn = sqlite3.connect(library.db_path)
        cursor = conn.execute(
            "SELECT usage_count, last_used FROM components WHERE id = ?",
            (component.id,)
        )
        usage_count_before, last_used_before = cursor.fetchone()
        conn.close()

        # Render a card
        renderer.render(
            result_id="result-1",
            result_type="status:test",
            result_data={"data": "test"},
        )

        # Verify usage stats incremented
        conn = sqlite3.connect(library.db_path)
        cursor = conn.execute(
            "SELECT usage_count, last_used FROM components WHERE id = ?",
            (component.id,)
        )
        usage_count_after, last_used_after = cursor.fetchone()
        conn.close()

        assert usage_count_after == usage_count_before + 1, \
            "usage_count was not incremented"
        # last_used may have been None initially
        if last_used_before is not None:
            assert last_used_after >= last_used_before, \
                "last_used was not updated"
        else:
            assert last_used_after is not None, \
                "last_used should be set after render"

    def test_renderer_updates_usage_pattern_stats(self, library, renderer):
        """Hot-path render updates sample_count and last_matched on usage pattern."""
        # Seed component and pattern
        component = library.create_component(
            name="pattern-test",
            description="Pattern test component",
            html_template="<div>{{summary}}</div>",
        )
        library.record_usage_pattern(
            component_id=component.id,
            result_type="status:pattern-test",
            match_score=0.85
        )

        # Get initial pattern stats
        conn = sqlite3.connect(library.db_path)
        cursor = conn.execute(
            "SELECT sample_count, last_matched FROM component_usage_patterns "
            "WHERE component_id = ? AND result_type = ?",
            (component.id, "status:pattern-test")
        )
        sample_count_before, last_matched_before = cursor.fetchone()
        conn.close()

        # Render a card (hot-path records match_score=1.0 for confirmed matches)
        renderer.render(
            result_id="result-pattern-1",
            result_type="status:pattern-test",
            result_data={"summary": "Test"},
        )

        # Verify pattern stats updated
        conn = sqlite3.connect(library.db_path)
        cursor = conn.execute(
            "SELECT sample_count, last_matched FROM component_usage_patterns "
            "WHERE component_id = ? AND result_type = ?",
            (component.id, "status:pattern-test")
        )
        sample_count_after, last_matched_after = cursor.fetchone()
        conn.close()

        assert sample_count_after == sample_count_before + 1, \
            "sample_count was not incremented in component_usage_patterns"
        # last_matched may equal last_matched_before if renders are within same second
        assert last_matched_after >= last_matched_before, \
            "last_matched was not updated in component_usage_patterns"

    def test_fallback_path_writes_nothing(self, library, renderer):
        """When no component matches (fallback), hot-path writes nothing to component DB.

        The server now renders the fallback HTML server-side (for SSE streaming),
        but still writes nothing to card_cache or component_usage_patterns — the
        fallback path is read-only against the component DB.
        """
        # Get initial row counts
        def count_rows(table):
            conn = sqlite3.connect(library.db_path)
            cursor = conn.execute(f"SELECT COUNT(*) FROM {table}")
            count = cursor.fetchone()[0]
            conn.close()
            return count

        cache_before = count_rows("card_cache")
        components_before = count_rows("components")
        patterns_before = count_rows("component_usage_patterns")

        # Render with unmatched result_type (fallback path)
        render_outcome = renderer.render(
            result_id="fallback-result",
            result_type="unmatched:type",
            result_data={"test": "data"},
        )

        # Verify fallback outcome (server now renders fallback HTML)
        assert render_outcome.rendered_html is not None, \
            "fallback path should generate fallback HTML server-side"
        assert "fallback-card" in render_outcome.rendered_html, \
            "fallback HTML should contain fallback-card class"
        assert render_outcome.card_fallback is True
        assert render_outcome.component_id is None

        # Verify nothing was written to component DB (fallback is read-only)
        cache_after = count_rows("card_cache")
        components_after = count_rows("components")
        patterns_after = count_rows("component_usage_patterns")

        assert cache_after == cache_before, \
            "fallback path wrote to card_cache (should write nothing)"
        assert components_after == components_before
        assert patterns_after == patterns_before


class TestWriteScopeAcrossMultipleRenders:
    """Verify write-scope holds across repeated renders."""

    def test_multiple_repeats_respect_write_scope(self, library, renderer):
        """Multiple renders still only write to card_cache and stats."""
        # Seed one component
        component = library.create_component(
            name="multi-render-test",
            description="Multi-render test component",
            html_template="<div>{{value}}</div>",
        )
        library.record_usage_pattern(
            component_id=component.id,
            result_type="status:multi-test",
            match_score=0.92
        )

        # Record initial state
        def get_table_counts():
            conn = sqlite3.connect(library.db_path)
            cursor = conn.execute("""
                SELECT
                    (SELECT COUNT(*) FROM components),
                    (SELECT COUNT(*) FROM component_versions),
                    (SELECT COUNT(*) FROM component_tags),
                    (SELECT COUNT(*) FROM card_cache)
            """)
            row = cursor.fetchone()
            conn.close()
            return {
                "components": row[0],
                "versions": row[1],
                "tags": row[2],
                "cache": row[3],
            }

        initial_counts = get_table_counts()

        # Render 5 cards
        for i in range(5):
            renderer.render(
                result_id=f"result-{i}",
                result_type="status:multi-test",
                result_data={"value": f"test-{i}"},
            )

        # Verify only card_cache grew
        final_counts = get_table_counts()

        assert final_counts["components"] == initial_counts["components"], \
            "components table changed across multiple renders"
        assert final_counts["versions"] == initial_counts["versions"], \
            "component_versions table changed across multiple renders"
        assert final_counts["tags"] == initial_counts["tags"], \
            "component_tags table changed across multiple renders"
        assert final_counts["cache"] == initial_counts["cache"] + 5, \
            f"card_cache should have 5 new rows, grew by {final_counts['cache'] - initial_counts['cache']}"

    def test_component_stats_increment_correctly(self, library, renderer):
        """Component usage_count increments per render."""
        component = library.create_component(
            name="stats-test",
            description="Stats test component",
            html_template="<div>{{test}}</div>",
        )
        # Seed the pattern (initial sample_count = 1)
        library.record_usage_pattern(
            component_id=component.id,
            result_type="status:stats-test",
            match_score=0.88
        )

        # Render 3 times (each adds 1 to sample_count via hot-path render)
        for i in range(3):
            renderer.render(
                result_id=f"stats-result-{i}",
                result_type="status:stats-test",
                result_data={"test": f"value-{i}"},
            )

        # Verify usage_count = 3 (one per render)
        conn = sqlite3.connect(library.db_path)
        cursor = conn.execute(
            "SELECT usage_count FROM components WHERE id = ?",
            (component.id,)
        )
        usage_count = cursor.fetchone()[0]

        # Verify sample_count = 4 (1 initial seed + 3 renders)
        cursor = conn.execute(
            "SELECT sample_count FROM component_usage_patterns "
            "WHERE component_id = ? AND result_type = ?",
            (component.id, "status:stats-test")
        )
        sample_count = cursor.fetchone()[0]
        conn.close()

        assert usage_count == 3, f"Expected usage_count=3, got {usage_count}"
        assert sample_count == 4, f"Expected sample_count=4 (1 initial + 3 renders), got {sample_count}"
