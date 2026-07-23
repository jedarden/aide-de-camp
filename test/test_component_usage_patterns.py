"""
Tests for component_usage_patterns table and tracking.

Tests the migration, pattern storage, retrieval, and API endpoints
for the component usage patterns system.
"""

import pytest
import sqlite3
import time
from pathlib import Path
import tempfile
import os

from src.components.library import ComponentLibrary, get_library
from src.components.seed_patterns import load_seed_patterns, ensure_seed_patterns


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    fd, path = tempfile.mkstemp(suffix='.db')
    os.close(fd)
    db_path = Path(path)
    yield db_path
    # Cleanup
    if db_path.exists():
        db_path.unlink()


@pytest.fixture
def library(temp_db):
    """Create a component library with temporary database."""
    # Reset the global singleton
    import src.components.library
    src.components.library._library_instance = None
    lib = ComponentLibrary(str(temp_db))
    yield lib
    lib.close()


@pytest.fixture
def sample_component(library):
    """Create a sample component for testing."""
    component = library.create_component(
        name="test-status",
        description="Test status component",
        html_template='<div class="test-card">{{summary}}</div>',
        change_note="Initial version"
    )
    return component


class TestComponentUsagePatternsMigration:
    """Tests for component_usage_patterns table migration."""

    def test_schema_has_layout_bucket_column(self, library):
        """Test that the schema includes layout_bucket column."""
        conn = library._get_conn()
        cursor = conn.execute("PRAGMA table_info(component_usage_patterns)")
        columns = {row[1] for row in cursor.fetchall()}

        assert 'layout_bucket' in columns
        assert 'updated_at' in columns
        assert 'result_type' in columns
        assert 'component_id' in columns
        assert 'match_score' in columns
        assert 'sample_count' in columns

    def test_primary_key_includes_layout_bucket(self, library):
        """Test that the primary key includes (result_type, component_id, layout_bucket)."""
        conn = library._get_conn()
        cursor = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='component_usage_patterns'"
        )
        row = cursor.fetchone()
        assert row is not None

        sql = row[0]
        # Check for PRIMARY KEY clause with all three columns
        assert 'PRIMARY KEY' in sql
        assert 'result_type' in sql
        assert 'component_id' in sql
        assert 'layout_bucket' in sql

    def test_index_on_match_score_desc(self, library):
        """Test that there's an index on match_score DESC."""
        conn = library._get_conn()
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_component_usage_patterns_match_score'"
        )
        row = cursor.fetchone()
        assert row is not None


class TestComponentUsagePatternsStorage:
    """Tests for pattern storage and retrieval."""

    def test_record_usage_pattern_basic(self, library, sample_component):
        """Test basic pattern recording."""
        library.record_usage_pattern(
            component_id=sample_component.id,
            result_type="status:test",
            match_score=0.85,
            layout_bucket="normal"
        )

        conn = library._get_conn()
        row = conn.execute(
            """
            SELECT result_type, component_id, layout_bucket, match_score, sample_count
            FROM component_usage_patterns
            WHERE result_type = ? AND component_id = ? AND layout_bucket = ?
            """,
            ("status:test", sample_component.id, "normal")
        ).fetchone()

        assert row is not None
        assert row[0] == "status:test"
        assert row[1] == sample_component.id
        assert row[2] == "normal"
        assert row[3] == 0.85
        assert row[4] == 1  # sample_count starts at 1

    def test_record_usage_pattern_with_all_layouts(self, library, sample_component):
        """Test recording patterns for all layout buckets."""
        layouts = ['compact', 'normal', 'expanded']

        for layout in layouts:
            library.record_usage_pattern(
                component_id=sample_component.id,
                result_type="status:test",
                match_score=0.80 + (layouts.index(layout) * 0.05),
                layout_bucket=layout
            )

        conn = library._get_conn()
        rows = conn.execute(
            """
            SELECT layout_bucket, match_score
            FROM component_usage_patterns
            WHERE result_type = ? AND component_id = ?
            ORDER BY layout_bucket
            """,
            ("status:test", sample_component.id)
        ).fetchall()

        assert len(rows) == 3

        # Create a map for verification (ordering may vary)
        layout_map = {row[0]: row[1] for row in rows}

        # Verify all layouts are present
        assert 'compact' in layout_map
        assert 'normal' in layout_map
        assert 'expanded' in layout_map

        # Verify the scores were stored correctly
        expected_scores = {
            'compact': 0.80,
            'normal': 0.85,
            'expanded': 0.90
        }
        for layout, score in layout_map.items():
            expected = expected_scores[layout]
            assert abs(score - expected) < 0.01

    def test_record_usage_pattern_updates_existing(self, library, sample_component):
        """Test that recording the same pattern updates existing entry."""
        # First recording
        library.record_usage_pattern(
            component_id=sample_component.id,
            result_type="status:test",
            match_score=0.80,
            layout_bucket="normal"
        )

        time.sleep(0.1)  # Small delay to ensure updated_at changes

        # Second recording with different score
        library.record_usage_pattern(
            component_id=sample_component.id,
            result_type="status:test",
            match_score=0.90,
            layout_bucket="normal"
        )

        conn = library._get_conn()
        row = conn.execute(
            """
            SELECT match_score, sample_count, updated_at
            FROM component_usage_patterns
            WHERE result_type = ? AND component_id = ? AND layout_bucket = ?
            """,
            ("status:test", sample_component.id, "normal")
        ).fetchone()

        assert row is not None
        # Match score should be averaged: (0.80 * 1 + 0.90) / 2 = 0.85
        assert abs(row[0] - 0.85) < 0.01  # Allow for floating point errors
        assert row[1] == 2  # sample_count incremented

    def test_select_component_by_result_type(self, library, sample_component):
        """Test selecting component by result_type."""
        # Record a pattern
        library.record_usage_pattern(
            component_id=sample_component.id,
            result_type="status:test",
            match_score=0.95,
            layout_bucket="normal"
        )

        # Select component
        component = library.select_component_for_result_type(
            result_type="status:test",
            match_threshold=0.7,
            layout_bucket="normal"
        )

        assert component is not None
        assert component.id == sample_component.id

    def test_select_component_below_threshold(self, library, sample_component):
        """Test that components below threshold are not selected."""
        # Record a pattern with low score
        library.record_usage_pattern(
            component_id=sample_component.id,
            result_type="status:test",
            match_score=0.60,
            layout_bucket="normal"
        )

        # Try to select with higher threshold
        component = library.select_component_for_result_type(
            result_type="status:test",
            match_threshold=0.7,
            layout_bucket="normal"
        )

        assert component is None

    def test_select_component_wrong_layout(self, library, sample_component):
        """Test that layout_bucket affects selection."""
        # Record pattern only for 'normal' layout
        library.record_usage_pattern(
            component_id=sample_component.id,
            result_type="status:test",
            match_score=0.95,
            layout_bucket="normal"
        )

        # Try to select for 'compact' layout
        component = library.select_component_for_result_type(
            result_type="status:test",
            match_threshold=0.7,
            layout_bucket="compact"
        )

        assert component is None

    def test_select_component_highest_score_first(self, library):
        """Test that highest match_score is selected when multiple components match."""
        # Create multiple components
        comp1 = library.create_component("comp-1", "Test 1", "<div>1</div>")
        comp2 = library.create_component("comp-2", "Test 2", "<div>2</div>")
        comp3 = library.create_component("comp-3", "Test 3", "<div>3</div>")

        # Record patterns with different scores
        library.record_usage_pattern(comp1.id, "status:test", 0.70, "normal")
        library.record_usage_pattern(comp2.id, "status:test", 0.95, "normal")
        library.record_usage_pattern(comp3.id, "status:test", 0.80, "normal")

        # Select should return comp2 (highest score)
        component = library.select_component_for_result_type("status:test", 0.6, "normal")

        assert component is not None
        assert component.id == comp2.id


class TestSeedPatterns:
    """Tests for seed pattern loading."""

    def test_load_seed_patterns(self, library):
        """Test loading seed patterns."""
        # Create components and use their actual IDs
        comp_k8s = library.create_component(
            name="k8s-status",
            description="Test k8s component",
            html_template="<div>k8s</div>"
        )
        comp_git = library.create_component(
            name="git-status",
            description="Test git component",
            html_template="<div>git</div>"
        )

        # Load seed patterns using the actual component IDs
        patterns = [
            ("status:kubernetes", comp_k8s.id, "normal", 0.95, 10),
            ("status:git", comp_git.id, "normal", 0.93, 15),
        ]
        loaded = load_seed_patterns(library, patterns)

        assert loaded == 2

        # Verify patterns were loaded
        conn = library._get_conn()
        rows = conn.execute(
            "SELECT COUNT(*) FROM component_usage_patterns"
        ).fetchone()

        assert rows[0] == 2

    def test_load_seed_patterns_skips_missing_components(self, library):
        """Test that seed patterns skip non-existent components."""
        # Don't create any components

        # Try to load seed patterns
        loaded = load_seed_patterns(library)

        assert loaded == 0  # All skipped due to missing components

    def test_ensure_seed_patterns_loads_when_empty(self, library):
        """Test that ensure_seed_patterns loads when table is empty."""
        # Create a component
        library.create_component("test-comp", "Test", "<div>test</div>")

        # Add a pattern that references the test component
        patterns = [("status:test", "test-comp", "normal", 0.85, 5)]

        # Mock the DEFAULT_SEED_PATTERNS
        import src.components.seed_patterns
        original = src.components.seed_patterns.DEFAULT_SEED_PATTERNS
        src.components.seed_patterns.DEFAULT_SEED_PATTERNS = patterns

        try:
            loaded = ensure_seed_patterns(library)
            assert loaded is True  # Should have loaded
        finally:
            src.components.seed_patterns.DEFAULT_SEED_PATTERNS = original

    def test_ensure_seed_patterns_skips_when_not_empty(self, library):
        """Test that ensure_seed_patterns skips when table has data."""
        # Create a component and add a pattern
        comp = library.create_component("test-comp", "Test", "<div>test</div>")
        library.record_usage_pattern(comp.id, "status:test", 0.85, "normal")

        loaded = ensure_seed_patterns(library)
        assert loaded is False  # Should skip


class TestAPIEndpoints:
    """Tests for usage patterns API endpoints."""

    def test_record_usage_pattern_api(self, client, library):
        """Test POST /api/v1/components/usage-patterns endpoint."""
        # Create a component
        comp = library.create_component("test-comp", "Test", "<div>test</div>")

        # Call the API
        response = client.post(
            "/api/v1/components/usage-patterns",
            json={
                "component_id": comp.id,
                "result_type": "status:test",
                "match_score": 0.92,
                "layout_bucket": "normal"
            }
        )

        # Print response for debugging if it fails
        if response.status_code != 200:
            print(f"Response status: {response.status_code}")
            print(f"Response body: {response.text}")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["pattern"]["component_id"] == comp.id
        assert data["pattern"]["result_type"] == "status:test"
        assert data["pattern"]["match_score"] == 0.92

    def test_record_usage_pattern_api_validation(self, client):
        """Test API validation for invalid inputs."""
        # Invalid match_score - FastAPI returns 422 for Pydantic validation errors
        response = client.post(
            "/api/v1/components/usage-patterns",
            json={
                "component_id": "comp-123",
                "result_type": "status:test",
                "match_score": 1.5,  # Invalid: > 1.0
            }
        )
        # Either 400 (custom validation) or 422 (Pydantic validation) is acceptable
        assert response.status_code in (400, 422)

        # Missing required fields - FastAPI returns 422 for Pydantic validation errors
        response = client.post(
            "/api/v1/components/usage-patterns",
            json={
                "component_id": "comp-123",
                # Missing result_type
                "match_score": 0.85
            }
        )
        assert response.status_code == 422

    def test_list_usage_patterns_api(self, client, library):
        """Test GET /api/v1/components/usage-patterns endpoint."""
        # Create component and add patterns
        comp = library.create_component("test-comp", "Test", "<div>test</div>")
        library.record_usage_pattern(comp.id, "status:test", 0.92, "normal")
        library.record_usage_pattern(comp.id, "action:test", 0.85, "compact")

        # List all patterns
        response = client.get("/api/v1/components/usage-patterns")
        assert response.status_code == 200
        data = response.json()
        assert "patterns" in data
        assert "count" in data
        assert len(data["patterns"]) == 2

        # Filter by result_type
        response = client.get(
            "/api/v1/components/usage-patterns?result_type=status:test"
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["patterns"]) == 1
        assert data["patterns"][0]["result_type"] == "status:test"


# Fixtures for pytest-asyncio
@pytest.fixture
def client(temp_db):
    """Create an HTTP client for testing API endpoints."""
    from fastapi.testclient import TestClient
    from src.main import app

    # Override the component library for testing
    import src.components.library
    original_singleton = src.components.library._library_instance
    test_library = ComponentLibrary(str(temp_db))
    src.components.library._library_instance = test_library

    # Override the global library in main.py
    import src.main
    original_main_library = src.main._component_library
    src.main._component_library = test_library

    with TestClient(app) as test_client:
        yield test_client

    # Cleanup
    test_library.close()
    src.components.library._library_instance = original_singleton
    src.main._component_library = original_main_library
