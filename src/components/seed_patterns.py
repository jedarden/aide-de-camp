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
#
# Design Document: See docs/design/component_usage_patterns_seed_data.md for full rationale
# and scoring guidelines. Match scores are 0.0-1.0, with 0.7 being the hot-path threshold.
DEFAULT_SEED_PATTERNS = [
    # ================================================================================
    # STATUS RESULTS
    # ================================================================================

    # Project-specific status patterns (highest scores for exact fit)
    ("status:ibkr-mcp", "comp-ibkr-status", "normal", 0.95, 25),
    ("status:ibkr-mcp", "comp-ibkr-status", "compact", 0.90, 10),
    ("status:adc", "comp-adc-status", "normal", 0.95, 20),
    ("status:adc", "comp-adc-status", "compact", 0.88, 8),

    # Kubernetes status patterns (well-defined schemas, high scores)
    ("status:k8s", "comp-k8s-pod-status", "normal", 0.94, 30),
    ("status:k8s", "comp-k8s-pod-status", "compact", 0.89, 15),
    ("status:k8s", "comp-k8s-deployment-status", "normal", 0.92, 18),
    ("status:k8s", "comp-k8s-service-status", "compact", 0.91, 12),

    # Git operations status
    ("status:git", "comp-git-status", "normal", 0.93, 22),
    ("status:git", "comp-git-status", "compact", 0.87, 11),
    ("status:git", "comp-git-commit-info", "normal", 0.91, 16),

    # CI/CD status (highly structured, highest scores)
    ("status:ci", "comp-ci-pipeline-status", "normal", 0.96, 28),
    ("status:ci", "comp-ci-pipeline-status", "compact", 0.90, 14),
    ("status:ci", "comp-ci-build-status", "expanded", 0.92, 10),

    # ================================================================================
    # LOOKUP RESULTS
    # ================================================================================

    # Logs lookup patterns (specific structure, highest scores)
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

    # Metrics lookup patterns (structured numerical data)
    ("lookup:metrics:k8s", "comp-k8s-metrics", "normal", 0.93, 20),
    ("lookup:metrics:k8s", "comp-k8s-metrics", "expanded", 0.95, 15),

    # ================================================================================
    # ACTION RESULTS
    # ================================================================================

    # General action patterns (moderate scores due to wide variability)
    ("action:general", "comp-action-result", "normal", 0.85, 20),
    ("action:general", "comp-action-result", "compact", 0.80, 10),

    # Deployment actions
    ("action:deploy", "comp-deployment-result", "normal", 0.92, 25),
    ("action:deploy", "comp-deployment-result", "expanded", 0.90, 12),

    # Restart actions (compact works well for binary results)
    ("action:restart", "comp-restart-result", "compact", 0.91, 18),
    ("action:restart", "comp-restart-result", "normal", 0.88, 14),

    # Scaling actions
    ("action:scale", "comp-scale-result", "normal", 0.90, 16),
    ("action:scale", "comp-scale-result", "expanded", 0.87, 8),

    # ================================================================================
    # MONITORING RESULTS
    # ================================================================================

    # Kubernetes monitoring (well-structured metrics, high scores)
    ("monitoring:k8s", "comp-k8s-monitoring", "normal", 0.94, 35),
    ("monitoring:k8s", "comp-k8s-monitoring", "expanded", 0.96, 25),
    ("monitoring:k8s", "comp-k8s-monitoring", "compact", 0.88, 15),

    # Application monitoring (project-specific)
    ("monitoring:adc", "comp-adc-metrics", "normal", 0.91, 20),
    ("monitoring:ibkr-mcp", "comp-ibkr-metrics", "normal", 0.90, 18),

    # General monitoring
    ("monitoring:general", "comp-monitoring-card", "normal", 0.82, 12),

    # ================================================================================
    # FALLBACK PATTERNS (Generic Components)
    # ================================================================================

    # All generic patterns score exactly 0.70 (at threshold)
    # Sample counts reflect high usage but low specificity
    ("status:general", "comp-generic-status", "normal", 0.70, 30),
    ("status:general", "comp-generic-status", "compact", 0.68, 15),
    ("action:general", "comp-generic-action", "normal", 0.70, 25),
    ("lookup:general", "comp-generic-lookup", "normal", 0.70, 20),
    ("monitoring:general", "comp-generic-monitoring", "normal", 0.70, 18),
    ("compound:general", "comp-generic-compound", "expanded", 0.70, 22),
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
