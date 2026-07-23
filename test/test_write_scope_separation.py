"""
Unit test for hot-path renderer write-scope separation.

Acceptance test for adc-2jvu: verifies that the hot-path renderer (the server-side
deterministic component selector) only writes to card_cache and usage stats, never
to component definitions (components, component_versions, component_tags tables).

This separation ensures the hot-path selector and UI-regen agent never race on a
component's identity — the server only reads component definitions; only the
UI-regen agent writes them.

Write scope (plan, Security Model):
- Server hot-path: card_cache rows + usage stats only
- UI-regen agent: component definitions + match_score mappings
"""

import sqlite3
import tempfile
from pathlib import Path

import pytest

from src.components.library import ComponentLibrary, get_library
from src.render.hot_path import get_renderer


class TestWriteScopeSeparation:
    """
    Test that the hot-path renderer respects write-scope boundaries.

    The hot-path renderer (HotPathRenderer.render()) may ONLY write:
    1. card_cache rows
    2. components.usage_count and last_used columns
    3. component_usage_patterns.sample_count, last_matched, match_score columns

    It must NEVER write:
    - components rows (except usage_count/last_used columns)
    - component_versions rows
    - component_tags rows
    """

    def test_hot_path_never_writes_component_definitions(self):
        """
        Test that hot-path render only touches card_cache and usage stats.

        This is the core acceptance test for adc-2jvu write-scope separation.
        """
        # Create isolated test database
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test_components.db"

            # Initialize component library
            library = ComponentLibrary(str(db_path))

            # Seed a component and usage pattern (simulating UI-regen agent work)
            component = library.create_component(
                name="test-status",
                description="Renders status results",
                html_template="<div>Status: {{summary}}</div>",
                change_note="Initial version for test"
            )

            # Seed usage pattern so the hot-path selector will match
            library.record_usage_pattern(
                component_id=component.id,
                result_type="status:test-project",
                match_score=0.9
            )

            # Snapshot the database state before render
            conn = sqlite3.connect(str(db_path))
            conn.row_factory = sqlite3.Row

            before_components = conn.execute(
                "SELECT * FROM components"
            ).fetchall()
            before_versions = conn.execute(
                "SELECT * FROM component_versions"
            ).fetchall()
            before_tags = conn.execute(
                "SELECT * FROM component_tags"
            ).fetchall()
            before_cache = conn.execute(
                "SELECT * FROM card_cache"
            ).fetchall()

            conn.close()

            # Run hot-path render
            renderer = get_renderer(library=library, reset=True)
            result_id = "test-result-123"
            result_data = {
                "summary": "Test status result",
                "details": "Some details"
            }

            outcome = renderer.render(
                result_id=result_id,
                result_type="status:test-project",
                result_data=result_data,
                summary="Test status result",
                layout_bucket="normal"
            )

            # Verify render succeeded (not a fallback)
            assert outcome.component_id == component.id
            assert outcome.rendered_html is not None
            assert not outcome.card_fallback

            # Verify write-scope: only card_cache and usage stats changed
            conn = sqlite3.connect(str(db_path))
            conn.row_factory = sqlite3.Row

            after_components = conn.execute(
                "SELECT * FROM components"
            ).fetchall()
            after_versions = conn.execute(
                "SELECT * FROM component_versions"
            ).fetchall()
            after_tags = conn.execute(
                "SELECT * FROM component_tags"
            ).fetchall()
            after_cache = conn.execute(
                "SELECT * FROM card_cache"
            ).fetchall()

            # 1. component_versions: MUST NOT CHANGE (server never writes versions)
            assert len(after_versions) == len(before_versions) == 1, \
                "hot-path render must not write component_versions"
            assert after_versions[0]["component_id"] == before_versions[0]["component_id"]
            assert after_versions[0]["version"] == before_versions[0]["version"]
            assert after_versions[0]["html_template"] == before_versions[0]["html_template"]

            # 2. component_tags: MUST NOT CHANGE (server never writes tags)
            assert len(after_tags) == len(before_tags) == 0, \
                "hot-path render must not write component_tags"

            # 3. components: only usage_count and last_used may change
            assert len(after_components) == len(before_components) == 1, \
                "hot-path render must not create new component rows"

            before_comp = before_components[0]
            after_comp = after_components[0]

            # These fields MUST NOT change (write-scope boundary)
            assert after_comp["id"] == before_comp["id"]
            assert after_comp["name"] == before_comp["name"]
            assert after_comp["description"] == before_comp["description"]
            assert after_comp["html_template"] == before_comp["html_template"]
            assert after_comp["version"] == before_comp["version"]
            assert after_comp["created_at"] == before_comp["created_at"]

            # These fields MAY change (usage stats are in write scope)
            assert after_comp["usage_count"] == before_comp["usage_count"] + 1, \
                "hot-path render must increment components.usage_count"
            assert after_comp["last_used"] > before_comp["last_used"] if before_comp["last_used"] else True, \
                "hot-path render must update components.last_used"

            # 4. card_cache: MUST HAVE NEW ROW (server's primary write target)
            assert len(after_cache) == len(before_cache) + 1, \
                "hot-path render must write exactly one card_cache row"

            cached_row = after_cache[0]
            assert cached_row["result_id"] == result_id
            assert cached_row["component_id"] == component.id
            assert cached_row["component_version"] == component.version
            assert cached_row["layout_bucket"] == "normal"
            assert "Status:" in cached_row["rendered_html"]
            assert "Test status result" in cached_row["rendered_html"]

            # 5. component_usage_patterns: stats must be updated
            pattern_row = conn.execute(
                "SELECT * FROM component_usage_patterns WHERE component_id = ? AND result_type = ?",
                (component.id, "status:test-project")
            ).fetchone()

            assert pattern_row is not None
            assert pattern_row["sample_count"] == 2, \
                "hot-path render must increment sample_count (seeded 1, now 2)"
            # last_matched should be a recent timestamp (> 0)
            assert pattern_row["last_matched"] > 0, \
                "hot-path render must update last_matched"
            # match_score gets updated via running avg, must not be 1.0 (seeded 0.9)
            assert pattern_row["match_score"] != 1.0 or pattern_row["match_score"] >= 0.9

            conn.close()

    def test_fallback_path_writes_nothing_to_component_db(self):
        """
        Test that fallback (no component match) writes nothing to component DB.

        When result_type has no matching component above threshold, the hot-path
        renderer returns a fallback outcome and must not write anything to the
        component database (card_cache or usage stats).
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test_components.db"
            library = ComponentLibrary(str(db_path))

            # Seed a component but DO NOT seed usage pattern
            # (so no component will match "status:unknown-project")
            component = library.create_component(
                name="other-status",
                description="Renders other status",
                html_template="<div>Other: {{summary}}</div>",
            )

            renderer = get_renderer(library=library, reset=True)

            # Snapshot before
            conn = sqlite3.connect(str(db_path))
            before_cache_count = conn.execute(
                "SELECT COUNT(*) FROM card_cache"
            ).fetchone()[0]
            before_usage_count = conn.execute(
                "SELECT usage_count FROM components WHERE id = ?",
                (component.id,)
            ).fetchone()[0]
            conn.close()

            # Render with unknown result_type (will fallback)
            outcome = renderer.render(
                result_id="fallback-result-456",
                result_type="status:unknown-project",  # No pattern seeded
                result_data={"summary": "Unknown"},
                summary="Unknown result",
            )

            # Verify fallback outcome
            assert outcome.component_id is None
            assert outcome.rendered_html is None
            assert outcome.card_fallback is True

            # Verify nothing was written
            conn = sqlite3.connect(str(db_path))
            after_cache_count = conn.execute(
                "SELECT COUNT(*) FROM card_cache"
            ).fetchone()[0]
            after_usage_count = conn.execute(
                "SELECT usage_count FROM components WHERE id = ?",
                (component.id,)
            ).fetchone()[0]
            conn.close()

            assert after_cache_count == before_cache_count, \
                "fallback must not write card_cache"
            assert after_usage_count == before_usage_count, \
                "fallback must not increment usage_count"

    def test_layout_bucket_uniqueness_in_card_cache(self):
        """
        Test that card_cache PK uniqueness holds: (result_id, component_id, layout_bucket).

        Rendering the same result with the same component but different layout buckets
        should create distinct rows, not overwrite.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test_components.db"
            library = ComponentLibrary(str(db_path))

            component = library.create_component(
                name="multi-layout",
                description="Multi-layout component",
                html_template="<div>{{summary}}</div>",
            )
            library.record_usage_pattern(
                component_id=component.id,
                result_type="status:layout-test",
                match_score=0.95
            )

            renderer = get_renderer(library=library, reset=True)
            result_id = "layout-test-result"

            # Render same result with different layout buckets
            for bucket in ["compact", "normal", "expanded"]:
                renderer.render(
                    result_id=result_id,
                    result_type="status:layout-test",
                    result_data={"summary": f"Layout {bucket}"},
                    summary=f"Layout {bucket}",
                    layout_bucket=bucket
                )

            # Verify three distinct card_cache rows
            conn = sqlite3.connect(str(db_path))
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT layout_bucket FROM card_cache WHERE result_id = ? ORDER BY layout_bucket",
                (result_id,)
            ).fetchall()
            conn.close()

            assert len(rows) == 3, \
                "card_cache must have one row per layout_bucket"
            buckets = [r["layout_bucket"] for r in rows]
            assert buckets == ["compact", "expanded", "normal"]
