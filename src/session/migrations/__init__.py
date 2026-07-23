"""
Database migrations for the aide-de-camp session store.

Migrations are numbered sequentially and should be run in order.
Each migration file should implement:
- migrate_up(db_path): Applies the migration
- migrate_down(db_path): Rolls back the migration
"""

from . import add_result_type
from . import add_component_usage_patterns
from . import seed_component_patterns

__all__ = ["add_result_type", "add_component_usage_patterns", "seed_component_patterns"]
