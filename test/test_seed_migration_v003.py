"""
Tests for seed migration v003 (seed_component_patterns.py).

Comprehensive tests to verify seed migration loads correctly and data integrity is maintained.
Tests include:
- Seed data loads without errors
- All result_type values are valid
- All component_id references exist
- Match scores in valid range (0.0-1.0)
- No duplicate patterns
- Expected count of patterns created
"""

import pytest
import sqlite3
import time
from pathlib import Path
import tempfile
import os
import sys

# Add src directory to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from src.session.migrations.seed_component_patterns import (
    migrate_up,
    migrate_down,
    get_migration_version,
    set_migration_version,
    SEED_PATTERNS,
)


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
def db_with_schema(temp_db):
    """Create a temporary database with component_usage_patterns schema."""
    # Create the component_usage_patterns table
    conn = sqlite3.connect(temp_db)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS component_usage_patterns (
            result_type TEXT NOT NULL,
            component_id TEXT NOT NULL,
            layout_bucket TEXT NOT NULL DEFAULT 'normal',
            match_score REAL NOT NULL,
            sample_count INTEGER NOT NULL DEFAULT 1,
            updated_at INTEGER NOT NULL,
            PRIMARY KEY (result_type, component_id, layout_bucket)
        )
    """)

    # Create the index for match_score
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_component_usage_patterns_match_score
        ON component_usage_patterns(match_score DESC)
    """)

    # Create components table for foreign key validation
    conn.execute("""
        CREATE TABLE IF NOT EXISTS components (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT,
            html_template TEXT NOT NULL,
            version INTEGER NOT NULL DEFAULT 1,
            created_at INTEGER NOT NULL,
            last_used INTEGER,
            usage_count INTEGER NOT NULL DEFAULT 0
        )
    """)

    conn.commit()
    conn.close()
    return temp_db


@pytest.fixture
def db_with_components(db_with_schema):
    """Create database with schema and all required test components."""
    conn = sqlite3.connect(db_with_schema)

    # Collect all unique component_ids from SEED_PATTERNS
    component_ids = set()
    for result_type, component_id, layout_bucket, match_score, sample_count in SEED_PATTERNS:
        component_ids.add(component_id)

    # Create all required components
    now = int(time.time())
    for component_id in component_ids:
        conn.execute("""
            INSERT OR IGNORE INTO components (id, name, description, html_template, created_at)
            VALUES (?, ?, ?, ?, ?)
        """, (component_id, f"Test {component_id}", f"Test component for {component_id}",
              '<div class="test-card">{{summary}}</div>', now))

    conn.commit()
    conn.close()
    return db_with_schema


class TestSeedMigrationV003:
    """Comprehensive tests for seed migration v003."""

    def test_migration_runs_without_errors(self, db_with_components):
        """Test that migrate_up executes without raising exceptions."""
        # Should not raise any exceptions
        migrate_up(db_with_components)

        # Verify migration version was not set by migrate_up (that's handled by run_migration)
        version = get_migration_version(db_with_components)
        # migrate_up doesn't set version, so it should still be None
        assert version is None

    def test_seed_data_creates_expected_count(self, db_with_components):
        """Test that seed migration creates exactly the expected number of patterns."""
        migrate_up(db_with_components)

        conn = sqlite3.connect(db_with_components)
        cursor = conn.execute("SELECT COUNT(*) FROM component_usage_patterns")
        count = cursor.fetchone()[0]
        conn.close()

        assert count == len(SEED_PATTERNS), f"Expected {len(SEED_PATTERNS)} patterns, got {count}"

    def test_all_result_types_valid(self, db_with_components):
        """Test that all result_type values follow the expected format."""
        migrate_up(db_with_components)

        conn = sqlite3.connect(db_with_components)
        cursor = conn.execute("SELECT DISTINCT result_type FROM component_usage_patterns")
        result_types = [row[0] for row in cursor.fetchall()]
        conn.close()

        # All result_types should be non-empty strings
        for rt in result_types:
            assert isinstance(rt, str), f"result_type {rt} is not a string"
            assert len(rt) > 0, f"result_type is empty"
            # Should follow pattern: category:project[:subtype]
            assert ':' in rt, f"result_type '{rt}' does not contain ':' separator"

            # Extract category (before first colon)
            category = rt.split(':')[0]
            valid_categories = {'status', 'lookup', 'action', 'monitoring', 'compound'}
            assert category in valid_categories, f"Invalid category '{category}' in result_type '{rt}'"

    def test_all_component_ids_exist(self, db_with_components):
        """Test that all component_id references exist in components table."""
        migrate_up(db_with_components)

        conn = sqlite3.connect(db_with_components)

        # Get all component_ids from patterns
        cursor = conn.execute("SELECT DISTINCT component_id FROM component_usage_patterns")
        pattern_component_ids = [row[0] for row in cursor.fetchall()]

        # Get all component_ids from components table
        cursor = conn.execute("SELECT id FROM components")
        existing_component_ids = {row[0] for row in cursor.fetchall()}

        conn.close()

        # Every component_id in patterns should exist in components
        for component_id in pattern_component_ids:
            assert component_id in existing_component_ids, f"component_id '{component_id}' not found in components table"

    def test_match_scores_in_valid_range(self, db_with_components):
        """Test that all match_scores are in the valid range [0.0, 1.0]."""
        migrate_up(db_with_components)

        conn = sqlite3.connect(db_with_components)
        cursor = conn.execute("SELECT match_score FROM component_usage_patterns")
        match_scores = [row[0] for row in cursor.fetchall()]
        conn.close()

        for score in match_scores:
            assert isinstance(score, (int, float)), f"match_score {score} is not a number"
            assert 0.0 <= score <= 1.0, f"match_score {score} is not in range [0.0, 1.0]"

    def test_no_duplicate_patterns(self, db_with_components):
        """Test that there are no duplicate (result_type, component_id, layout_bucket) tuples."""
        migrate_up(db_with_components)

        conn = sqlite3.connect(db_with_components)
        cursor = conn.execute("""
            SELECT result_type, component_id, layout_bucket, COUNT(*) as count
            FROM component_usage_patterns
            GROUP BY result_type, component_id, layout_bucket
            HAVING count > 1
        """)
        duplicates = cursor.fetchall()
        conn.close()

        assert len(duplicates) == 0, f"Found duplicates: {duplicates}"

    def test_primary_key_constraint(self, db_with_components):
        """Test that primary key constraint prevents duplicate inserts."""
        migrate_up(db_with_components)

        conn = sqlite3.connect(db_with_components)

        # Try to insert the first pattern again
        first_pattern = SEED_PATTERNS[0]
        result_type, component_id, layout_bucket, match_score, sample_count = first_pattern

        # This should fail due to PRIMARY KEY constraint
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("""
                INSERT INTO component_usage_patterns
                (result_type, component_id, layout_bucket, match_score, sample_count, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (result_type, component_id, layout_bucket, match_score, sample_count, int(time.time())))

        conn.close()

    def test_layout_buckets_valid(self, db_with_components):
        """Test that all layout_bucket values are valid."""
        migrate_up(db_with_components)

        valid_buckets = {'compact', 'normal', 'expanded'}

        conn = sqlite3.connect(db_with_components)
        cursor = conn.execute("SELECT DISTINCT layout_bucket FROM component_usage_patterns")
        layout_buckets = [row[0] for row in cursor.fetchall()]
        conn.close()

        for bucket in layout_buckets:
            assert bucket in valid_buckets, f"Invalid layout_bucket '{bucket}'"

    def test_sample_counts_positive(self, db_with_components):
        """Test that all sample_counts are positive integers."""
        migrate_up(db_with_components)

        conn = sqlite3.connect(db_with_components)
        cursor = conn.execute("SELECT sample_count FROM component_usage_patterns")
        sample_counts = [row[0] for row in cursor.fetchall()]
        conn.close()

        for count in sample_counts:
            assert isinstance(count, int), f"sample_count {count} is not an integer"
            assert count >= 0, f"sample_count {count} is negative"

    def test_updated_at_timestamps(self, db_with_components):
        """Test that all updated_at values are valid timestamps."""
        migrate_up(db_with_components)

        conn = sqlite3.connect(db_with_components)
        cursor = conn.execute("SELECT updated_at FROM component_usage_patterns")
        timestamps = [row[0] for row in cursor.fetchall()]
        conn.close()

        # All timestamps should be non-empty strings (CURRENT_TIMESTAMP format)
        for ts in timestamps:
            assert isinstance(ts, str), f"updated_at {ts} is not a string"
            assert len(ts) > 0, f"updated_at is empty"
            # Should be in format like '2026-07-23 17:07:48'
            assert '-' in ts and ':' in ts, f"updated_at {ts} doesn't look like a timestamp"

    def test_migration_idempotent(self, db_with_components):
        """Test that running migrate_up multiple times is idempotent."""
        # First migration
        migrate_up(db_with_components)

        conn = sqlite3.connect(db_with_components)
        cursor = conn.execute("SELECT COUNT(*) FROM component_usage_patterns")
        first_count = cursor.fetchone()[0]
        conn.close()

        # Second migration (should skip due to existing data)
        migrate_up(db_with_components)

        conn = sqlite3.connect(db_with_components)
        cursor = conn.execute("SELECT COUNT(*) FROM component_usage_patterns")
        second_count = cursor.fetchone()[0]
        conn.close()

        assert first_count == second_count, "Migration is not idempotent - count changed"

    def test_migrate_down_removes_all_seed_data(self, db_with_components):
        """Test that migrate_down removes all seed pattern data."""
        # First run migrate_up
        migrate_up(db_with_components)

        conn = sqlite3.connect(db_with_components)
        cursor = conn.execute("SELECT COUNT(*) FROM component_usage_patterns")
        count_after_up = cursor.fetchone()[0]
        conn.close()

        assert count_after_up == len(SEED_PATTERNS)

        # Now run migrate_down
        migrate_down(db_with_components)

        conn = sqlite3.connect(db_with_components)
        cursor = conn.execute("SELECT COUNT(*) FROM component_usage_patterns")
        count_after_down = cursor.fetchone()[0]
        conn.close()

        assert count_after_down == 0, f"migrate_down should remove all patterns, but {count_after_down} remain"

    def test_migrate_down_idempotent(self, db_with_components):
        """Test that running migrate_down multiple times is safe."""
        migrate_up(db_with_components)
        migrate_down(db_with_components)

        # Running migrate_down again should be safe (no errors)
        migrate_down(db_with_components)

        conn = sqlite3.connect(db_with_components)
        cursor = conn.execute("SELECT COUNT(*) FROM component_usage_patterns")
        count = cursor.fetchone()[0]
        conn.close()

        assert count == 0, "Table should still be empty after second migrate_down"

    def test_seed_patterns_constant_integrity(self):
        """Test that SEED_PATTERNS constant has valid structure."""
        # Check that SEED_PATTERNS is a list
        assert isinstance(SEED_PATTERNS, list), "SEED_PATTERNS should be a list"

        # Check that it's not empty
        assert len(SEED_PATTERNS) > 0, "SEED_PATTERNS should not be empty"

        # Check each pattern tuple
        for pattern in SEED_PATTERNS:
            assert isinstance(pattern, tuple), f"Pattern {pattern} is not a tuple"
            assert len(pattern) == 5, f"Pattern {pattern} should have 5 elements"

            result_type, component_id, layout_bucket, match_score, sample_count = pattern

            # Validate types
            assert isinstance(result_type, str), f"result_type should be string in {pattern}"
            assert isinstance(component_id, str), f"component_id should be string in {pattern}"
            assert isinstance(layout_bucket, str), f"layout_bucket should be string in {pattern}"
            assert isinstance(match_score, (int, float)), f"match_score should be number in {pattern}"
            assert isinstance(sample_count, int), f"sample_count should be int in {pattern}"

            # Validate values
            assert 0.0 <= match_score <= 1.0, f"match_score out of range in {pattern}"
            assert sample_count >= 0, f"sample_count negative in {pattern}"
            assert layout_bucket in {'compact', 'normal', 'expanded'}, f"Invalid layout_bucket in {pattern}"

    def test_missing_component_table_handling(self, temp_db):
        """Test that migration handles missing components table gracefully."""
        # Create only component_usage_patterns table (no components table)
        conn = sqlite3.connect(temp_db)
        conn.execute("""
            CREATE TABLE component_usage_patterns (
                result_type TEXT NOT NULL,
                component_id TEXT NOT NULL,
                layout_bucket TEXT NOT NULL DEFAULT 'normal',
                match_score REAL NOT NULL,
                sample_count INTEGER NOT NULL DEFAULT 1,
                updated_at INTEGER NOT NULL,
                PRIMARY KEY (result_type, component_id, layout_bucket)
            )
        """)
        conn.commit()
        conn.close()

        # Migration should still work (INSERT OR IGNORE handles foreign key issues if FK constraints are off)
        migrate_up(temp_db)

        # Verify patterns were inserted
        conn = sqlite3.connect(temp_db)
        cursor = conn.execute("SELECT COUNT(*) FROM component_usage_patterns")
        count = cursor.fetchone()[0]
        conn.close()

        assert count == len(SEED_PATTERNS)

    def test_migration_without_existing_table(self, temp_db):
        """Test that migration handles missing component_usage_patterns table gracefully."""
        # Don't create any tables

        # Migration should log warning but not crash
        migrate_up(temp_db)

        # No patterns should be created since table doesn't exist
        conn = sqlite3.connect(temp_db)
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='component_usage_patterns'")
        table_exists = cursor.fetchone() is not None
        conn.close()

        assert not table_exists, "Table should not exist"

    def test_migration_version_management(self, db_with_components):
        """Test migration version getter and setter."""
        # Initially no version
        version = get_migration_version(db_with_components)
        assert version is None, "Initial version should be None"

        # Set version to 2
        set_migration_version(db_with_components, 2)
        version = get_migration_version(db_with_components)
        assert version == 2, f"Version should be 2, got {version}"

        # Update version to 3
        set_migration_version(db_with_components, 3)
        version = get_migration_version(db_with_components)
        assert version == 3, f"Version should be 3, got {version}"

    def test_schema_migrations_table_creation(self, temp_db):
        """Test that set_migration_version creates schema_migrations table if needed."""
        # Should create table automatically
        set_migration_version(temp_db, 1)

        conn = sqlite3.connect(temp_db)
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='schema_migrations'")
        table_exists = cursor.fetchone() is not None
        conn.close()

        assert table_exists, "schema_migrations table should be created"

    def test_high_value_patterns_exist(self, db_with_components):
        """Test that critical high-score patterns are present."""
        migrate_up(db_with_components)

        conn = sqlite3.connect(db_with_components)

        # Check for some known high-score patterns
        high_score_patterns = [
            ("status:ci", "comp-ci-pipeline-status", "normal", 0.96),
            ("lookup:logs:k8s", "comp-k8s-logs", "expanded", 0.97),
            ("monitoring:k8s", "comp-k8s-monitoring", "expanded", 0.96),
        ]

        for result_type, component_id, layout_bucket, expected_score in high_score_patterns:
            cursor = conn.execute("""
                SELECT match_score FROM component_usage_patterns
                WHERE result_type = ? AND component_id = ? AND layout_bucket = ?
            """, (result_type, component_id, layout_bucket))
            result = cursor.fetchone()

            assert result is not None, f"Pattern {result_type}/{component_id}/{layout_bucket} not found"
            assert result[0] == expected_score, f"Expected score {expected_score}, got {result[0]}"

        conn.close()

    def test_all_categories_represented(self, db_with_components):
        """Test that all expected categories have seed patterns."""
        migrate_up(db_with_components)

        conn = sqlite3.connect(db_with_components)
        cursor = conn.execute("""
            SELECT DISTINCT substr(result_type, 1, instr(result_type, ':') - 1) as category
            FROM component_usage_patterns
        """)
        categories = {row[0] for row in cursor.fetchall()}
        conn.close()

        expected_categories = {'status', 'lookup', 'action', 'monitoring', 'compound'}
        assert categories == expected_categories, f"Expected categories {expected_categories}, got {categories}"

    def test_match_score_distribution(self, db_with_components):
        """Test that match scores have reasonable distribution."""
        migrate_up(db_with_components)

        conn = sqlite3.connect(db_with_components)
        cursor = conn.execute("SELECT match_score FROM component_usage_patterns")
        scores = [row[0] for row in cursor.fetchall()]
        conn.close()

        # Check score range
        min_score = min(scores)
        max_score = max(scores)
        avg_score = sum(scores) / len(scores)

        # Should have range covering 0.7 to 0.97
        assert min_score >= 0.68, f"Min score {min_score} too low"
        assert max_score <= 1.0, f"Max score {max_score} too high"

        # Average should be reasonable (most patterns should be mid-to-high confidence)
        assert 0.75 <= avg_score <= 0.95, f"Average score {avg_score} outside expected range"

    def test_migration_creates_updated_at_timestamps(self, db_with_components):
        """Test that migration sets current updated_at timestamps."""
        before_migration = int(time.time())
        migrate_up(db_with_components)
        after_migration = int(time.time())

        conn = sqlite3.connect(db_with_components)
        cursor = conn.execute("SELECT updated_at FROM component_usage_patterns LIMIT 1")
        result = cursor.fetchone()
        conn.close()

        assert result is not None, "Should have at least one pattern"
        updated_at = result[0]

        # Timestamp should be set as a non-empty string
        assert isinstance(updated_at, str), f"updated_at should be a string, got {type(updated_at)}"
        assert len(updated_at) > 0, "updated_at should not be empty"
        # Verify it's a timestamp-like string
        assert '-' in updated_at and ':' in updated_at, \
            f"updated_at {updated_at} doesn't look like a timestamp"


class TestSeedMigrationV003EdgeCases:
    """Edge case and error handling tests for seed migration v003."""

    def test_empty_seed_patterns_wont_break(self, db_with_schema):
        """Test behavior with empty patterns list (simulated by deleting after insert)."""
        conn = sqlite3.connect(db_with_schema)

        # Insert one pattern then delete it to test empty state
        conn.execute("""
            INSERT INTO component_usage_patterns
            (result_type, component_id, layout_bucket, match_score, sample_count, updated_at)
            VALUES ('test:pattern', 'comp-test', 'normal', 0.5, 1, ?)
        """, (int(time.time()),))
        conn.execute("DELETE FROM component_usage_patterns")
        conn.commit()
        conn.close()

        # Migration should handle empty state gracefully
        migrate_up(db_with_schema)

    def test_partial_existing_patterns(self, db_with_components):
        """Test migration when some patterns already exist."""
        conn = sqlite3.connect(db_with_components)

        # Insert a subset of patterns manually
        manual_patterns = SEED_PATTERNS[:5]
        now = int(time.time())
        for result_type, component_id, layout_bucket, match_score, sample_count in manual_patterns:
            conn.execute("""
                INSERT OR IGNORE INTO component_usage_patterns
                (result_type, component_id, layout_bucket, match_score, sample_count, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (result_type, component_id, layout_bucket, match_score, sample_count, now))
        conn.commit()
        conn.close()

        # Run migration
        migrate_up(db_with_components)

        # Verify all patterns exist (manual + migrated)
        conn = sqlite3.connect(db_with_components)
        cursor = conn.execute("SELECT COUNT(*) FROM component_usage_patterns")
        count = cursor.fetchone()[0]
        conn.close()

        # Should have all SEED_PATTERNS, no duplicates
        assert count == len(SEED_PATTERNS)

    def test_run_migration_integration(self, db_with_components):
        """Test the run_migration function that manages versioning."""
        from src.session.migrations.seed_component_patterns import run_migration

        # Initial migration to version 3
        run_migration(db_with_components, target_version=3)

        version = get_migration_version(db_with_components)
        assert version == 3, f"Version should be 3 after migration, got {version}"

        conn = sqlite3.connect(db_with_components)
        cursor = conn.execute("SELECT COUNT(*) FROM component_usage_patterns")
        count = cursor.fetchone()[0]
        conn.close()

        assert count == len(SEED_PATTERNS), f"Should have {len(SEED_PATTERNS)} patterns"

    def test_migration_down_from_version_3(self, db_with_components):
        """Test migrate_down when current version is 3."""
        from src.session.migrations.seed_component_patterns import run_migration

        # Migrate up to version 3
        run_migration(db_with_components, target_version=3)

        # Verify patterns exist
        conn = sqlite3.connect(db_with_components)
        cursor = conn.execute("SELECT COUNT(*) FROM component_usage_patterns")
        count = cursor.fetchone()[0]
        conn.close()

        assert count == len(SEED_PATTERNS)

        # Migrate down to version 2
        run_migration(db_with_components, target_version=2)

        version = get_migration_version(db_with_components)
        assert version == 2, f"Version should be 2 after down migration, got {version}"

        # Verify patterns removed
        conn = sqlite3.connect(db_with_components)
        cursor = conn.execute("SELECT COUNT(*) FROM component_usage_patterns")
        count = cursor.fetchone()[0]
        conn.close()

        assert count == 0, "All patterns should be removed after migrate_down"
