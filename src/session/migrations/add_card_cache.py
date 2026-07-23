"""
Migration 004: Create card_cache table.

This migration creates the card_cache table which stores pre-rendered HTML
for result components. This enables server-side rendering of component cards
and avoids repeated rendering for the same result.

The table uses a composite primary key (result_id, component_id, layout_bucket)
to allow multiple cached variations per result (e.g., different layouts).

Up migration: Creates the card_cache table with indexes.
Down migration: Drops the card_cache table.
"""

import logging
import sqlite3
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def migrate_up(db_path: Path) -> None:
    """Create card_cache table.

    This migration is idempotent - it checks if the table exists
    before creating it, so it can be run multiple times safely.

    Args:
        db_path: Path to the SQLite database file
    """
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()

        # Check if card_cache table already exists
        cursor.execute("""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name='card_cache'
        """)

        if cursor.fetchone():
            logger.info("Migration 004: card_cache table already exists, skipping")
            return

        logger.info("Migration 004: Creating card_cache table")

        # Create the card_cache table
        cursor.execute("""
            CREATE TABLE card_cache (
                result_id TEXT NOT NULL,
                component_id TEXT NOT NULL,
                layout_bucket TEXT NOT NULL,
                rendered_html TEXT NOT NULL,
                created_at INTEGER NOT NULL,
                PRIMARY KEY (result_id, component_id, layout_bucket)
            )
        """)

        # Create index on result_id for efficient lookups
        cursor.execute("""
            CREATE INDEX idx_card_cache_result_id
            ON card_cache(result_id)
        """)

        conn.commit()
        logger.info("Migration 004: Successfully created card_cache table")

    except Exception as e:
        conn.rollback()
        logger.error(f"Migration 004 failed: {e}")
        raise
    finally:
        conn.close()


def migrate_down(db_path: Path) -> None:
    """Remove card_cache table.

    WARNING: This will permanently delete the card_cache table and all data.
    Use with caution - this operation cannot be undone.

    Args:
        db_path: Path to the SQLite database file
    """
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()

        # Check if card_cache table exists
        cursor.execute("""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name='card_cache'
        """)

        if not cursor.fetchone():
            logger.info("Migration 004 down: card_cache table does not exist, skipping")
            return

        logger.warning("Migration 004 down: Removing card_cache table")

        # Drop the index first
        cursor.execute("DROP INDEX IF EXISTS idx_card_cache_result_id")

        # Drop the table
        cursor.execute("DROP TABLE card_cache")

        conn.commit()
        logger.info("Migration 004 down: Successfully removed card_cache table")

    except Exception as e:
        conn.rollback()
        logger.error(f"Migration 004 down failed: {e}")
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
    latest_version = 4  # This migration file

    if target_version is None:
        target_version = latest_version

    if current_version == target_version:
        logger.info(f"Database is already at version {target_version}")
        return

    if current_version < target_version:
        # Migrate up
        if target_version >= 4 and current_version < 4:
            migrate_up(db_path)
            set_migration_version(db_path, 4)
    else:
        # Migrate down
        if target_version < 4 and current_version >= 4:
            migrate_down(db_path)
            set_migration_version(db_path, 3)


if __name__ == "__main__":
    # Allow running the migration directly from command line
    import sys

    db_path_arg = sys.argv[1] if len(sys.argv) > 1 else "/home/coding/aide-de-camp/data/session.db"
    db_path = Path(db_path_arg)

    action = sys.argv[2] if len(sys.argv) > 2 else "up"

    if action == "up":
        migrate_up(db_path)
        version = get_migration_version(db_path) or 0
        if version < 4:
            set_migration_version(db_path, 4)
    elif action == "down":
        migrate_down(db_path)
        set_migration_version(db_path, 3)
    else:
        print(f"Unknown action: {action}")
        print("Usage: python add_card_cache.py <db_path> [up|down]")
        sys.exit(1)
