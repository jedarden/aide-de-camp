# Session Store Migrations

This directory contains database migrations for the aide-de-camp session store.

## Migration Files

Each migration file is named after what it does (e.g., `add_result_type.py`) and should implement:

- `migrate_up(db_path: Path)` - Applies the migration
- `migrate_down(db_path: Path)` - Rolls back the migration
- `get_migration_version(db_path: Path) -> Optional[int]` - Gets current version
- `set_migration_version(db_path: Path, version: int)` - Sets current version
- `run_migration(db_path: Path, target_version: Optional[int])` - Runs migrations

## Running Migrations

### Direct usage

```python
from pathlib import Path
from src.session.migrations.add_result_type import migrate_up, set_migration_version

db_path = Path("data/session.db")
migrate_up(db_path)
set_migration_version(db_path, 1)
```

### Command line

```bash
.venv/bin/python src/session/migrations/add_result_type.py /path/to/session.db up
.venv/bin/python src/session/migrations/add_result_type.py /path/to/session.db down
```

## Migration History

| Version | Migration | Description |
|---------|-----------|-------------|
| 001 | add_result_type | Add result_type TEXT column to results table for component card selection |
| 002 | add_component_usage_patterns | Create component_usage_patterns table for component selection tracking |

## Notes

- Migrations are idempotent - they can be run multiple times safely
- The `schema_migrations` table tracks which migrations have been applied
- Always test migrations on a copy of production data before running live
- The inline migration logic in `src/session/store.py` runs automatically on startup, but standalone migration files provide explicit control and rollback capability
