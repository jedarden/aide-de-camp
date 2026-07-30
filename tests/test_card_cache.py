"""
Tests for card_cache table and caching infrastructure.

Tests verify:
- Migration creates card_cache table
- Cache write API stores rendered HTML
- Cache read API retrieves cached HTML by result_id
- Cache invalidation works correctly
"""

import os
import tempfile
from pathlib import Path

import pytest

from src.session.store import SessionStore


@pytest.fixture(scope="function")
async def temp_db_path() -> Path:
    """Create a temporary database for testing."""
    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".db") as f:
        db_path = Path(f.name)
    yield db_path
    # Cleanup
    try:
        os.unlink(db_path)
    except FileNotFoundError:
        pass


@pytest.fixture(scope="function")
async def store(temp_db_path: Path) -> SessionStore:
    """Create a SessionStore with a temporary database."""
    store = SessionStore(temp_db_path)
    await store.initialize()
    return store


class TestCardCacheMigration:
    """Test card_cache table migration."""

    @pytest.mark.asyncio
    async def test_card_cache_table_created(self, store: SessionStore):
        """Verify card_cache table exists after initialization."""
        import sqlite3

        # Direct connection to check table existence
        conn = sqlite3.connect(store.db_path)
        try:
            cursor = conn.cursor()

            # Check if card_cache table exists
            cursor.execute("""
                SELECT name FROM sqlite_master
                WHERE type='table' AND name='card_cache'
            """)
            result = cursor.fetchone()
            assert result is not None, "card_cache table should exist"

            # Check table schema
            cursor.execute("PRAGMA table_info(card_cache)")
            columns = {row[1]: row[2] for row in cursor.fetchall()}

            # Verify columns
            assert "result_id" in columns
            assert "component_id" in columns
            assert "layout_bucket" in columns
            assert "rendered_html" in columns
            assert "created_at" in columns

        finally:
            conn.close()

    @pytest.mark.asyncio
    async def test_card_cache_indexes_created(self, store: SessionStore):
        """Verify card_cache indexes exist."""
        import sqlite3

        conn = sqlite3.connect(store.db_path)
        try:
            cursor = conn.cursor()

            # Check for result_id index
            cursor.execute("""
                SELECT name FROM sqlite_master
                WHERE type='index' AND name='idx_card_cache_result_id'
            """)
            result = cursor.fetchone()
            assert result is not None, "idx_card_cache_result_id index should exist"

        finally:
            conn.close()


class TestCardCacheAPI:
    """Test card cache write/read API."""

    @pytest.mark.asyncio
    async def test_write_card_cache(self, store: SessionStore):
        """Test writing rendered HTML to cache."""
        result_id = "test-result-123"
        component_id = "test-component"
        layout_bucket = "default"
        rendered_html = "<div>Test Card Content</div>"

        await store.write_card_cache(result_id, component_id, layout_bucket, rendered_html)

        # Verify cache was written
        cached_entries = await store.get_card_cache(result_id)
        assert len(cached_entries) == 1
        assert cached_entries[0]["result_id"] == result_id
        assert cached_entries[0]["component_id"] == component_id
        assert cached_entries[0]["layout_bucket"] == layout_bucket
        assert cached_entries[0]["rendered_html"] == rendered_html
        assert cached_entries[0]["created_at"] is not None

    @pytest.mark.asyncio
    async def test_write_card_cache_updates_existing(self, store: SessionStore):
        """Test that writing to cache updates existing entries."""
        result_id = "test-result-456"
        component_id = "test-component"
        layout_bucket = "default"

        # Write initial HTML
        initial_html = "<div>Initial Content</div>"
        await store.write_card_cache(result_id, component_id, layout_bucket, initial_html)

        # Write updated HTML (should replace via INSERT OR REPLACE)
        updated_html = "<div>Updated Content</div>"
        await store.write_card_cache(result_id, component_id, layout_bucket, updated_html)

        # Verify only one entry exists with updated content
        cached_entries = await store.get_card_cache(result_id)
        assert len(cached_entries) == 1
        assert cached_entries[0]["rendered_html"] == updated_html

    @pytest.mark.asyncio
    async def test_get_card_cache_empty(self, store: SessionStore):
        """Test getting cache for non-existent result."""
        cached_entries = await store.get_card_cache("non-existent-result")
        assert cached_entries == []

    @pytest.mark.asyncio
    async def test_get_card_cache_multiple_entries(self, store: SessionStore):
        """Test getting multiple cache entries for same result."""
        result_id = "test-result-789"

        # Write multiple entries with different layouts
        await store.write_card_cache(result_id, "component-a", "mobile", "<div>Mobile</div>")
        await store.write_card_cache(result_id, "component-a", "desktop", "<div>Desktop</div>")
        await store.write_card_cache(result_id, "component-b", "default", "<div>Default</div>")

        # Get all entries
        cached_entries = await store.get_card_cache(result_id)
        assert len(cached_entries) == 3

        # Verify entries are returned
        result_ids = [e["result_id"] for e in cached_entries]
        assert all(rid == result_id for rid in result_ids)

    @pytest.mark.asyncio
    async def test_get_card_cache_entry_specific(self, store: SessionStore):
        """Test getting a specific cache entry."""
        result_id = "test-result-specific"
        component_id = "test-component"
        layout_bucket = "wide"
        rendered_html = "<div>Wide Layout</div>"

        await store.write_card_cache(result_id, component_id, layout_bucket, rendered_html)

        # Get specific entry
        entry = await store.get_card_cache_entry(result_id, component_id, layout_bucket)
        assert entry is not None
        assert entry["result_id"] == result_id
        assert entry["component_id"] == component_id
        assert entry["layout_bucket"] == layout_bucket
        assert entry["rendered_html"] == rendered_html

    @pytest.mark.asyncio
    async def test_get_card_cache_entry_not_found(self, store: SessionStore):
        """Test getting non-existent cache entry."""
        entry = await store.get_card_cache_entry("no-result", "no-component", "no-layout")
        assert entry is None

    @pytest.mark.asyncio
    async def test_invalidate_card_cache(self, store: SessionStore):
        """Test invalidating all cache entries for a result."""
        result_id = "test-result-invalidate"

        # Create multiple entries
        await store.write_card_cache(result_id, "component-a", "layout-1", "<div>1</div>")
        await store.write_card_cache(result_id, "component-b", "layout-2", "<div>2</div>")
        await store.write_card_cache(result_id, "component-c", "layout-3", "<div>3</div>")

        # Verify entries exist
        entries = await store.get_card_cache(result_id)
        assert len(entries) == 3

        # Invalidate all
        deleted_count = await store.invalidate_card_cache(result_id)
        assert deleted_count == 3

        # Verify entries are gone
        entries = await store.get_card_cache(result_id)
        assert len(entries) == 0

    @pytest.mark.asyncio
    async def test_invalidate_card_cache_no_entries(self, store: SessionStore):
        """Test invalidating cache for result with no entries."""
        deleted_count = await store.invalidate_card_cache("non-existent-result")
        assert deleted_count == 0

    @pytest.mark.asyncio
    async def test_invalidate_card_cache_entry(self, store: SessionStore):
        """Test invalidating a specific cache entry."""
        result_id = "test-result-invalidate-specific"

        # Create multiple entries
        await store.write_card_cache(result_id, "component-a", "layout-1", "<div>1</div>")
        await store.write_card_cache(result_id, "component-b", "layout-2", "<div>2</div>")

        # Invalidate specific entry
        deleted_count = await store.invalidate_card_cache_entry(
            result_id, "component-a", "layout-1"
        )
        assert deleted_count == 1

        # Verify only one entry remains
        entries = await store.get_card_cache(result_id)
        assert len(entries) == 1
        assert entries[0]["component_id"] == "component-b"

    @pytest.mark.asyncio
    async def test_invalidate_card_cache_entry_not_found(self, store: SessionStore):
        """Test invalidating non-existent cache entry."""
        deleted_count = await store.invalidate_card_cache_entry(
            "no-result", "no-component", "no-layout"
        )
        assert deleted_count == 0

    @pytest.mark.asyncio
    async def test_cache_primary_key_constraint(self, store: SessionStore):
        """Test that primary key prevents duplicate entries."""
        result_id = "test-result-pk"
        component_id = "test-component"
        layout_bucket = "default"

        # Write same entry twice (should update, not create duplicate)
        await store.write_card_cache(result_id, component_id, layout_bucket, "<div>V1</div>")
        await store.write_card_cache(result_id, component_id, layout_bucket, "<div>V2</div>")

        # Verify only one entry exists
        entries = await store.get_card_cache(result_id)
        assert len(entries) == 1
        assert entries[0]["rendered_html"] == "<div>V2</div>"

    @pytest.mark.asyncio
    async def test_cache_supports_different_components_same_result(self, store: SessionStore):
        """Test that different components for same result create separate entries."""
        result_id = "test-result-multiple-components"

        await store.write_card_cache(result_id, "component-a", "default", "<div>A</div>")
        await store.write_card_cache(result_id, "component-b", "default", "<div>B</div>")

        entries = await store.get_card_cache(result_id)
        assert len(entries) == 2

        component_ids = {e["component_id"] for e in entries}
        assert component_ids == {"component-a", "component-b"}

    @pytest.mark.asyncio
    async def test_cache_supports_different_layouts_same_component(self, store: SessionStore):
        """Test that different layouts for same component create separate entries."""
        result_id = "test-result-multiple-layouts"
        component_id = "test-component"

        await store.write_card_cache(result_id, component_id, "mobile", "<div>Mobile</div>")
        await store.write_card_cache(result_id, component_id, "desktop", "<div>Desktop</div>")

        entries = await store.get_card_cache(result_id)
        assert len(entries) == 2

        layout_buckets = {e["layout_bucket"] for e in entries}
        assert layout_buckets == {"mobile", "desktop"}
