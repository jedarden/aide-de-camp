"""
Migration 001: Add result_type column to results table.

This migration adds the result_type TEXT column to the results table,
which is used for component card selection in the UI.

Up migration: Adds the result_type column if it doesn't exist.
Down migration: Removes the result_type column (use with caution).
"""

import logging
import sqlite3
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def migrate_up(db_path: Path) -> None:
    """Add result_type column to results table.

    This migration is idempotent - it checks if the column exists
    before adding it, so it can be run multiple times safely.

    Args:
        db_path: Path to the SQLite database file
    """
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()

        # Check if result_type column already exists
        cursor.execute("PRAGMA table_info(results)")
        columns = {row[1] for row in cursor.fetchall()}

        if "result_type" in columns:
            logger.info("Migration 001: result_type column already exists, skipping")
            return

        logger.info("Migration 001: Adding result_type column to results table")

        # Add the result_type column
        cursor.execute("ALTER TABLE results ADD COLUMN result_type TEXT")

        conn.commit()
        logger.info("Migration 001: Successfully added result_type column")

    except Exception as e:
        conn.rollback()
        logger.error(f"Migration 001 failed: {e}")
        raise
    finally:
        conn.close()


def migrate_down(db_path: Path) -> None:
    """Remove result_type column from results table.

    WARNING: This will permanently delete the result_type column and all data.
    Use with caution - this operation cannot be undone easily.

    Args:
        db_path: Path to the SQLite database file
    """
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()

        # Check if result_type column exists
        cursor.execute("PRAGMA table_info(results)")
        columns = {row[1] for row in cursor.fetchall()}

        if "result_type" not in columns:
            logger.info("Migration 001 down: result_type column does not exist, skipping")
            return

        logger.warning("Migration 001 down: Removing result_type column from results table")

        # SQLite doesn't support ALTER TABLE DROP COLUMN directly until version 3.35.0
        # We need to recreate the table without the column

        # Start transaction
        conn.execute("BEGIN IMMEDIATE TRANSACTION")

        try:
            # Get all columns EXCEPT result_type
            cursor.execute("PRAGMA table_info(results)")
            all_columns = [row[1] for row in cursor.fetchall() if row[1] != 'result_type']

            # Build column lists for CREATE and INSERT
            create_columns = []
            for col_name in all_columns:
                # Get column details
                cursor.execute(f"PRAGMA table_info(results)")
                for row in cursor.fetchall():
                    if row[1] == col_name:
                        col_type = row[2]
                        not_null = " NOT NULL" if row[3] > 0 else ""
                        default_val = f" DEFAULT {row[4]}" if row[4] is not None else ""
                        create_columns.append(f"{col_name} {col_type}{not_null}{default_val}")
                        break

            # Create new table without result_type column
            create_sql = f"""
                CREATE TABLE results_new (
                    {', '.join(create_columns)},
                    FOREIGN KEY (intent_id) REFERENCES intents(id) ON DELETE CASCADE,
                    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE,
                    FOREIGN KEY (topic_id) REFERENCES topics(id) ON DELETE CASCADE,
                    FOREIGN KEY (previous_result_id) REFERENCES results(id) ON DELETE SET NULL
                )
            """
            cursor.execute(create_sql)

            # Copy data from old table to new table (excluding result_type)
            column_list = ", ".join(all_columns)
            cursor.execute(f"""
                INSERT INTO results_new ({column_list})
                SELECT {column_list}
                FROM results
            """)

            # Recreate indexes
            cursor.execute("DROP INDEX IF EXISTS idx_results_session")
            cursor.execute("DROP INDEX IF EXISTS idx_results_topic")
            cursor.execute("DROP INDEX IF EXISTS idx_results_created")
            cursor.execute("DROP INDEX IF EXISTS idx_results_previous")

            cursor.execute("CREATE INDEX idx_results_session ON results_new(session_id)")
            cursor.execute("CREATE INDEX idx_results_topic ON results_new(topic_id)")
            cursor.execute("CREATE INDEX idx_results_created ON results_new(created_at)")
            cursor.execute("CREATE INDEX idx_results_previous ON results_new(previous_result_id)")

            # Drop old table and rename new table
            cursor.execute("DROP TABLE results")
            cursor.execute("ALTER TABLE results_new RENAME TO results")

            conn.commit()
            logger.info("Migration 001 down: Successfully removed result_type column")

        except Exception as e:
            conn.rollback()
            logger.error(f"Migration 001 down failed during table recreation: {e}")
            raise

    except Exception as e:
        conn.rollback()
        logger.error(f"Migration 001 down failed: {e}")
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
    latest_version = 1  # This migration file

    if target_version is None:
        target_version = latest_version

    if current_version == target_version:
        logger.info(f"Database is already at version {target_version}")
        return

    if current_version < target_version:
        # Migrate up
        if target_version >= 1 and current_version < 1:
            migrate_up(db_path)
            set_migration_version(db_path, 1)
    else:
        # Migrate down
        if target_version < 1 and current_version >= 1:
            migrate_down(db_path)
            set_migration_version(db_path, 0)


if __name__ == "__main__":
    # Allow running the migration directly from command line
    import sys

    db_path_arg = sys.argv[1] if len(sys.argv) > 1 else "/home/coding/aide-de-camp/data/session.db"
    db_path = Path(db_path_arg)

    action = sys.argv[2] if len(sys.argv) > 2 else "up"

    if action == "up":
        migrate_up(db_path)
        set_migration_version(db_path, 1)
    elif action == "down":
        migrate_down(db_path)
        set_migration_version(db_path, 0)
    else:
        print(f"Unknown action: {action}")
        print("Usage: python 001_add_result_type.py <db_path> [up|down]")
        sys.exit(1)
