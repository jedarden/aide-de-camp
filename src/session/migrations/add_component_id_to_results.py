"""
Migration 003: Add component_id column to results table.

This migration adds a component_id column to track which component
rendered each result, allowing us to analyze component adoption
and understand which rendering path each result took.
"""

import aiosqlite
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


async def up(db_path: Path) -> None:
    """Add component_id column to results table."""
    async with aiosqlite.connect(db_path) as db:
        # Check if migration already ran
        cursor = await db.execute("PRAGMA table_info(results)")
        columns = {row[1] for row in await cursor.fetchall()}

        if 'component_id' in columns:
            logger.info("Migration 003: component_id column already exists, skipping")
            return

        logger.info("Migration 003: Adding component_id column to results table")

        # Add component_id column
        await db.execute(
            "ALTER TABLE results ADD COLUMN component_id TEXT"
        )

        # Create index for component lookups
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_results_component_id "
            "ON results(component_id)"
        )

        # Backfill component_id from card_cache where possible
        # This connects historical results to their components
        await db.execute("""
            UPDATE results
            SET component_id = (
                SELECT cc.component_id
                FROM card_cache cc
                WHERE cc.result_id = results.id
                LIMIT 1
            )
            WHERE component_id IS NULL
        """)

        await db.commit()

        # Count how many results now have component_id
        cursor = await db.execute(
            "SELECT COUNT(*) FROM results WHERE component_id IS NOT NULL"
        )
        count = (await cursor.fetchone())[0]
        logger.info(f"Migration 003: Backfilled component_id for {count} historical results")


async def down(db_path: Path) -> None:
    """Remove component_id column from results table."""
    async with aiosqlite.connect(db_path) as db:
        # SQLite doesn't support DROP COLUMN directly, so we recreate the table
        logger.info("Migration 003 down: Removing component_id from results table")

        # Get existing data
        await db.execute("BEGIN IMMEDIATE TRANSACTION")

        try:
            # Create new table without component_id
            await db.execute("""
                CREATE TABLE results_new (
                    id          TEXT PRIMARY KEY,
                    intent_id   TEXT,
                    topic_id    TEXT NOT NULL,
                    session_id  TEXT NOT NULL,
                    summary     TEXT NOT NULL,
                    data        TEXT NOT NULL,
                    urgency     TEXT NOT NULL CHECK(urgency IN ('critical', 'high', 'normal', 'low')) DEFAULT 'normal',
                    result_type TEXT,
                    card_fallback INTEGER NOT NULL DEFAULT 0 CHECK(card_fallback IN (0, 1)),
                    created_at  INTEGER NOT NULL,
                    surfaced_at INTEGER,
                    acked_at    INTEGER,
                    previous_result_id TEXT,
                    diff_summary TEXT,
                    diff_data    TEXT,
                    FOREIGN KEY (intent_id) REFERENCES intents(id) ON DELETE CASCADE,
                    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE,
                    FOREIGN KEY (topic_id) REFERENCES topics(id) ON DELETE CASCADE,
                    FOREIGN KEY (previous_result_id) REFERENCES results(id) ON DELETE SET NULL
                )
            """)

            # Copy data (excluding component_id)
            await db.execute("""
                INSERT INTO results_new (id, intent_id, topic_id, session_id, summary, data, urgency, result_type, card_fallback, created_at, surfaced_at, acked_at, previous_result_id, diff_summary, diff_data)
                SELECT id, intent_id, topic_id, session_id, summary, data, urgency, result_type, card_fallback, created_at, surfaced_at, acked_at, previous_result_id, diff_summary, diff_data
                FROM results
            """)

            # Recreate indexes
            await db.execute("DROP INDEX IF EXISTS idx_results_session")
            await db.execute("DROP INDEX IF EXISTS idx_results_topic")
            await db.execute("DROP INDEX IF EXISTS idx_results_created")
            await db.execute("DROP INDEX IF EXISTS idx_results_previous")
            await db.execute("DROP INDEX IF EXISTS idx_results_component_id")

            await db.execute("CREATE INDEX idx_results_session ON results_new(session_id)")
            await db.execute("CREATE INDEX idx_results_topic ON results_new(topic_id)")
            await db.execute("CREATE INDEX idx_results_created ON results_new(created_at)")
            await db.execute("CREATE INDEX idx_results_previous ON results_new(previous_result_id)")

            # Drop old table and rename new one
            await db.execute("DROP TABLE results")
            await db.execute("ALTER TABLE results_new RENAME TO results")

            await db.commit()
            logger.info("Migration 003 down: Completed successfully")

        except Exception as e:
            await db.rollback()
            logger.error(f"Migration 003 down failed: {e}")
            raise
