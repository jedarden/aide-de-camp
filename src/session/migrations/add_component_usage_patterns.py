"""
Migration 002: Create component_usage_patterns table.

This migration creates the component_usage_patterns table which tracks
which components are typically used for each result_type and layout combination.

The table uses a composite primary key (result_type, component_id, layout_bucket)
to prevent duplicate pattern entries and includes a match_score for ranking.

Up migration: Creates the component_usage_patterns table with indexes.
Down migration: Drops the component_usage_patterns table.
"""

import logging
import sqlite3
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def migrate_up(db_path: Path) -> None:
    """Create component_usage_patterns table.

    This migration is idempotent - it checks if the table exists
    before creating it, so it can be run multiple times safely.

    Args:
        db_path: Path to the SQLite database file
    """
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()

        # Check if component_usage_patterns table already exists
        cursor.execute("""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name='component_usage_patterns'
        """)

        if cursor.fetchone():
            logger.info("Migration 002: component_usage_patterns table already exists, skipping")
            return

        logger.info("Migration 002: Creating component_usage_patterns table")

        # Create the component_usage_patterns table
        cursor.execute("""
            CREATE TABLE component_usage_patterns (
                result_type TEXT NOT NULL,
                component_id TEXT NOT NULL,
                layout_bucket TEXT NOT NULL,
                match_score REAL NOT NULL,
                sample_count INTEGER NOT NULL DEFAULT 1,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (result_type, component_id, layout_bucket)
            )
        """)

        # Create index on match_score for efficient ranking queries
        cursor.execute("""
            CREATE INDEX idx_component_usage_patterns_match_score
            ON component_usage_patterns(match_score DESC)
        """)

        conn.commit()
        logger.info("Migration 002: Successfully created component_usage_patterns table")

    except Exception as e:
        conn.rollback()
        logger.error(f"Migration 002 failed: {e}")
        raise
    finally:
        conn.close()


def migrate_down(db_path: Path) -> None:
    """Remove component_usage_patterns table.

    WARNING: This will permanently delete the component_usage_patterns table and all data.
    Use with caution - this operation cannot be undone.

    Args:
        db_path: Path to the SQLite database file
    """
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()

        # Check if component_usage_patterns table exists
        cursor.execute("""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name='component_usage_patterns'
        """)

        if not cursor.fetchone():
            logger.info("Migration 002 down: component_usage_patterns table does not exist, skipping")
            return

        logger.warning("Migration 002 down: Removing component_usage_patterns table")

        # Drop the index first
        cursor.execute("DROP INDEX IF EXISTS idx_component_usage_patterns_match_score")

        # Drop the table
        cursor.execute("DROP TABLE component_usage_patterns")

        conn.commit()
        logger.info("Migration 002 down: Successfully removed component_usage_patterns table")

    except Exception as e:
        conn.rollback()
        logger.error(f"Migration 002 down failed: {e}")
        raise
    finally:
        conn.close()


def get_migration_version(db_path: Path) -> Optional[int]:
    """Get the current migration version from the database.

    Returns None if no migrations have been run.

    Args:
        db_path: Path to the SQLite database file

    Returns:
        The current migration version, or None if no migrations table exists
    """
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()

        # Check if migrations table exists
        cursor.execute("""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name='schema_migrations'
        """)
        if not cursor.fetchone():
            return None

        # Get current version
        cursor.execute("SELECT version FROM schema_migrations WHERE id = 1")
        result = cursor.fetchone()
        return result[0] if result else None

    finally:
        conn.close()


def set_migration_version(db_path: Path, version: int) -> None:
    """Set the current migration version in the database.

    Args:
        db_path: Path to the SQLite database file
        version: The migration version to set
    """
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()

        # Create migrations table if it doesn't exist
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS schema_migrations (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                version INTEGER NOT NULL,
                applied_at INTEGER NOT NULL
            )
        """)

        # Update or insert version
        now = int(__import__('time').time())
        cursor.execute("""
            INSERT OR REPLACE INTO schema_migrations (id, version, applied_at)
            VALUES (1, ?, ?)
        """, (version, now))

        conn.commit()

    finally:
        conn.close()


def run_migration(db_path: Path, target_version: Optional[int] = None) -> None:
    """Run migrations to bring the database to the target version.

    Args:
        db_path: Path to the SQLite database file
        target_version: Target migration version (None = migrate to latest)
    """
    current_version = get_migration_version(db_path) or 0
    latest_version = 2  # This migration file

    if target_version is None:
        target_version = latest_version

    if current_version == target_version:
        logger.info(f"Database is already at version {target_version}")
        return

    if current_version < target_version:
        # Migrate up
        if target_version >= 2 and current_version < 2:
            migrate_up(db_path)
            set_migration_version(db_path, 2)
    else:
        # Migrate down
        if target_version < 2 and current_version >= 2:
            migrate_down(db_path)
            set_migration_version(db_path, 1)


if __name__ == "__main__":
    # Allow running the migration directly from command line
    import sys

    db_path_arg = sys.argv[1] if len(sys.argv) > 1 else "/home/coding/aide-de-camp/data/session.db"
    db_path = Path(db_path_arg)

    action = sys.argv[2] if len(sys.argv) > 2 else "up"

    if action == "up":
        migrate_up(db_path)
        version = get_migration_version(db_path) or 0
        if version < 2:
            set_migration_version(db_path, 2)
    elif action == "down":
        migrate_down(db_path)
        set_migration_version(db_path, 1)
    else:
        print(f"Unknown action: {action}")
        print("Usage: python add_component_usage_patterns.py <db_path> [up|down]")
        sys.exit(1)
