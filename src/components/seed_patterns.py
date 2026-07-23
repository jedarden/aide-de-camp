"""
Seed data loader for component_usage_patterns table.

Provides initial mappings for common result types to components.
This can be called during initialization or testing.
"""

import logging
import time
from typing import Optional

from .library import ComponentLibrary

logger = logging.getLogger(__name__)


# Seed data: list of (result_type, component_id, layout_bucket, match_score, sample_count) tuples
# Note: component_id references must exist in the components table
DEFAULT_SEED_PATTERNS = [
    # Kubernetes status patterns
    ("status:kubernetes", "comp-k8s-status", "normal", 0.95, 10),
    ("status:kubernetes", "comp-k8s-status", "compact", 0.90, 5),
    ("status:kubernetes", "comp-k8s-status", "expanded", 0.92, 8),

    # Git status patterns
    ("status:git", "comp-git-status", "normal", 0.93, 15),
    ("status:git", "comp-git-status", "compact", 0.88, 7),

    # CI/CD status patterns
    ("status:ci", "comp-ci-status", "normal", 0.91, 12),
    ("status:ci", "comp-ci-status", "expanded", 0.94, 6),

    # Generic action patterns
    ("action:general", "comp-action-card", "normal", 0.85, 20),
    ("action:general", "comp-action-card", "compact", 0.82, 10),

    # Lookup patterns for logs
    ("lookup:logs:general", "comp-logs-viewer", "expanded", 0.96, 25),
    ("lookup:logs:general", "comp-logs-viewer", "normal", 0.94, 18),

    # Lookup patterns for configuration
    ("lookup:config:general", "comp-config-viewer", "normal", 0.89, 14),

    # Monitoring patterns
    ("monitoring:kubernetes", "comp-monitoring-card", "normal", 0.92, 8),
    ("monitoring:kubernetes", "comp-monitoring-card", "expanded", 0.95, 5),

    # General fallback patterns (for unmatched result types)
    ("status:general", "comp-generic-status", "normal", 0.70, 30),
    ("action:general", "comp-generic-action", "normal", 0.70, 25),
    ("lookup:general", "comp-generic-lookup", "normal", 0.70, 20),
]


def load_seed_patterns(
    library: ComponentLibrary,
    patterns: Optional[list[tuple[str, str, str, float, int]]] = None,
) -> int:
    """
    Load seed data into component_usage_patterns table.

    Args:
        library: The component library instance
        patterns: Optional list of (result_type, component_id, layout_bucket, match_score, sample_count) tuples.
                  If not provided, uses DEFAULT_SEED_PATTERNS.

    Returns:
        Number of patterns loaded (excluding conflicts)
    """
    if patterns is None:
        patterns = DEFAULT_SEED_PATTERNS

    conn = library._get_conn()
    now = int(time.time())
    loaded = 0

    for result_type, component_id, layout_bucket, match_score, sample_count in patterns:
        try:
            # Check if component exists
            component = library.get_component(component_id)
            if not component:
                logger.warning(
                    f"Skipping seed pattern: component '{component_id}' does not exist"
                )
                continue

            # Insert or ignore the pattern
            conn.execute(
                """
                INSERT OR IGNORE INTO component_usage_patterns
                (result_type, component_id, layout_bucket, match_score, sample_count, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (result_type, component_id, layout_bucket, match_score, sample_count, now)
            )
            loaded += 1

        except Exception as e:
            logger.error(f"Failed to load seed pattern ({result_type}, {component_id}): {e}")

    conn.commit()
    logger.info(f"Loaded {loaded} seed patterns into component_usage_patterns")
    return loaded


def ensure_seed_patterns(library: ComponentLibrary) -> bool:
    """
    Ensure seed patterns exist, loading them if the table is empty.

    This is a convenience function that checks if the component_usage_patterns
    table is empty and loads seed data if it is.

    Args:
        library: The component library instance

    Returns:
        True if seed patterns were loaded, False if they already existed
    """
    conn = library._get_conn()

    # Check if table is empty
    row = conn.execute(
        "SELECT COUNT(*) FROM component_usage_patterns"
    ).fetchone()

    if row and row[0] == 0:
        logger.info("component_usage_patterns table is empty, loading seed data")
        load_seed_patterns(library)
        return True
    else:
        logger.info(f"component_usage_patterns table has {row[0]} existing patterns, skipping seed load")
        return False
