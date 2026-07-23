"""
Migration 003: Seed component_usage_patterns table.

This migration populates the component_usage_patterns table with initial seed data
defining mappings between result types and UI components based on the design in:
docs/design/component_usage_patterns_seed_data.md

The seed data provides:
- Project-specific patterns (ibkr-mcp, adc, k8s, git)
- Result type categories (status, lookup, action, monitoring)
- Layout variants (compact, normal, expanded)
- Match scores reflecting confidence level (0.0-1.0)

Up migration: Inserts seed pattern data into component_usage_patterns table.
Down migration: Removes all seed pattern data from component_usage_patterns table.
"""

import logging
import sqlite3
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Seed patterns based on docs/design/component_usage_patterns_seed_data.md
# Format: (result_type, component_id, layout_bucket, match_score, sample_count)
SEED_PATTERNS = [
    # Category: Status Results
    # Project-specific status patterns
    ("status:ibkr-mcp", "comp-ibkr-status", "normal", 0.95, 25),
    ("status:ibkr-mcp", "comp-ibkr-status", "compact", 0.90, 10),
    ("status:adc", "comp-adc-status", "normal", 0.95, 20),
    ("status:adc", "comp-adc-status", "compact", 0.88, 8),

    # Kubernetes status patterns
    ("status:k8s", "comp-k8s-pod-status", "normal", 0.94, 30),
    ("status:k8s", "comp-k8s-pod-status", "compact", 0.89, 15),
    ("status:k8s", "comp-k8s-deployment-status", "normal", 0.92, 18),
    ("status:k8s", "comp-k8s-service-status", "compact", 0.91, 12),

    # Git operations status
    ("status:git", "comp-git-status", "normal", 0.93, 22),
    ("status:git", "comp-git-status", "compact", 0.87, 11),
    ("status:git", "comp-git-commit-info", "normal", 0.91, 16),

    # CI/CD status
    ("status:ci", "comp-ci-pipeline-status", "normal", 0.96, 28),
    ("status:ci", "comp-ci-pipeline-status", "compact", 0.90, 14),
    ("status:ci", "comp-ci-build-status", "expanded", 0.92, 10),

    # Category: Lookup Results
    # Logs lookup patterns
    ("lookup:logs:ibkr-mcp", "comp-logs-viewer", "expanded", 0.96, 40),
    ("lookup:logs:ibkr-mcp", "comp-logs-viewer", "normal", 0.93, 25),
    ("lookup:logs:adc", "comp-logs-viewer", "expanded", 0.95, 35),
    ("lookup:logs:adc", "comp-logs-viewer", "normal", 0.92, 20),
    ("lookup:logs:k8s", "comp-k8s-logs", "expanded", 0.97, 50),
    ("lookup:logs:general", "comp-logs-viewer", "expanded", 0.85, 15),

    # Config lookup patterns
    ("lookup:config:ibkr-mcp", "comp-config-viewer", "normal", 0.92, 18),
    ("lookup:config:ibkr-mcp", "comp-config-viewer", "expanded", 0.94, 12),
    ("lookup:config:adc", "comp-config-viewer", "normal", 0.91, 15),
    ("lookup:config:k8s", "comp-k8s-config", "expanded", 0.95, 30),
    ("lookup:config:general", "comp-config-viewer", "normal", 0.82, 10),

    # Metrics lookup patterns
    ("lookup:metrics:k8s", "comp-k8s-metrics", "normal", 0.93, 20),
    ("lookup:metrics:k8s", "comp-k8s-metrics", "expanded", 0.95, 15),

    # Category: Action Results
    # General action patterns
    ("action:general", "comp-action-result", "normal", 0.85, 20),
    ("action:general", "comp-action-result", "compact", 0.80, 10),

    # Deployment actions
    ("action:deploy", "comp-deployment-result", "normal", 0.92, 25),
    ("action:deploy", "comp-deployment-result", "expanded", 0.90, 12),

    # Restart actions
    ("action:restart", "comp-restart-result", "compact", 0.91, 18),
    ("action:restart", "comp-restart-result", "normal", 0.88, 14),

    # Scaling actions
    ("action:scale", "comp-scale-result", "normal", 0.90, 16),
    ("action:scale", "comp-scale-result", "expanded", 0.87, 8),

    # Category: Monitoring Results
    # Kubernetes monitoring
    ("monitoring:k8s", "comp-k8s-monitoring", "normal", 0.94, 35),
    ("monitoring:k8s", "comp-k8s-monitoring", "expanded", 0.96, 25),
    ("monitoring:k8s", "comp-k8s-monitoring", "compact", 0.88, 15),

    # Application monitoring
    ("monitoring:adc", "comp-adc-metrics", "normal", 0.91, 20),
    ("monitoring:ibkr-mcp", "comp-ibkr-metrics", "normal", 0.90, 18),

    # General monitoring
    ("monitoring:general", "comp-monitoring-card", "normal", 0.82, 12),

    # Category: Fallback Patterns (Generic Components)
    ("status:general", "comp-generic-status", "normal", 0.70, 30),
    ("status:general", "comp-generic-status", "compact", 0.68, 15),
    ("action:general", "comp-generic-action", "normal", 0.70, 25),
    ("lookup:general", "comp-generic-lookup", "normal", 0.70, 20),
    ("monitoring:general", "comp-generic-monitoring", "normal", 0.70, 18),
    ("compound:general", "comp-generic-compound", "expanded", 0.70, 22),
]


def migrate_up(db_path: Path) -> None:
    """Populate component_usage_patterns table with seed data.

    This migration is idempotent - it uses INSERT OR IGNORE to skip
    existing patterns, so it can be run multiple times safely.

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
            logger.warning("Migration 003: component_usage_patterns table does not exist, run migration 002 first")
            return

        # Check if seed data already exists
        cursor.execute("SELECT COUNT(*) FROM component_usage_patterns")
        existing_count = cursor.fetchone()[0]

        if existing_count >= len(SEED_PATTERNS):
            logger.info(f"Migration 003: Seed data already exists ({existing_count} patterns), skipping")
            return

        logger.info(f"Migration 003: Seeding component_usage_patterns with {len(SEED_PATTERNS)} patterns")

        # Insert seed patterns using INSERT OR IGNORE for idempotence
        insert_count = 0
        for result_type, component_id, layout_bucket, match_score, sample_count in SEED_PATTERNS:
            try:
                cursor.execute("""
                    INSERT OR IGNORE INTO component_usage_patterns
                    (result_type, component_id, layout_bucket, match_score, sample_count, updated_at)
                    VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                """, (result_type, component_id, layout_bucket, match_score, sample_count))
                if cursor.rowcount > 0:
                    insert_count += 1
            except sqlite3.Error as e:
                logger.warning(f"Failed to insert pattern ({result_type}, {component_id}, {layout_bucket}): {e}")

        conn.commit()
        logger.info(f"Migration 003: Successfully seeded {insert_count} patterns")

    except Exception as e:
        conn.rollback()
        logger.error(f"Migration 003 failed: {e}")
        raise
    finally:
        conn.close()


def migrate_down(db_path: Path) -> None:
    """Remove all seed pattern data from component_usage_patterns table.

    WARNING: This will remove all pattern data that matches the seed set.
    Use with caution.

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
            logger.info("Migration 003 down: component_usage_patterns table does not exist, skipping")
            return

        logger.warning("Migration 003 down: Removing all seed pattern data")

        # Delete all patterns that match our seed set
        # We delete by (result_type, component_id, layout_bucket) tuples
        delete_count = 0
        for result_type, component_id, layout_bucket, _, _ in SEED_PATTERNS:
            cursor.execute("""
                DELETE FROM component_usage_patterns
                WHERE result_type = ? AND component_id = ? AND layout_bucket = ?
            """, (result_type, component_id, layout_bucket))
            delete_count += cursor.rowcount

        conn.commit()
        logger.info(f"Migration 003 down: Successfully removed {delete_count} patterns")

    except Exception as e:
        conn.rollback()
        logger.error(f"Migration 003 down failed: {e}")
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
    latest_version = 3  # This migration file

    if target_version is None:
        target_version = latest_version

    if current_version == target_version:
        logger.info(f"Database is already at version {target_version}")
        return

    if current_version < target_version:
        # Migrate up
        if target_version >= 3 and current_version < 3:
            migrate_up(db_path)
            set_migration_version(db_path, 3)
    else:
        # Migrate down
        if target_version < 3 and current_version >= 3:
            migrate_down(db_path)
            set_migration_version(db_path, 2)


if __name__ == "__main__":
    # Allow running the migration directly from command line
    import sys

    db_path_arg = sys.argv[1] if len(sys.argv) > 1 else "/home/coding/aide-de-camp/data/session.db"
    db_path = Path(db_path_arg)

    action = sys.argv[2] if len(sys.argv) > 2 else "up"

    if action == "up":
        migrate_up(db_path)
        version = get_migration_version(db_path) or 0
        if version < 3:
            set_migration_version(db_path, 3)
    elif action == "down":
        migrate_down(db_path)
        set_migration_version(db_path, 2)
    else:
        print(f"Unknown action: {action}")
        print("Usage: python seed_component_patterns.py <db_path> [up|down]")
        sys.exit(1)
