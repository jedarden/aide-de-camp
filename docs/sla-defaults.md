# SLA Defaults and Per-Project Overrides

## Overview

The aide-de-camp SLA (Service Level Agreement) system provides configurable deadline tracking for async bead-backed tasks. Each intent type has a default SLA duration, and projects can override these defaults at the project level.

## Default SLA Hours per Intent Type

Default SLA durations are defined in `src/session/store.py`:

```python
DEFAULT_SLA_HOURS: dict[str, float] = {
    "task-profile": 6.0,    # 6 hours for async bead-backed tasks
    "status": 0.008,        # 30 seconds for hot-path status intents
    "action": 0.008,        # 30 seconds for hot-path action intents
    "lookup": 0.008,        # 30 seconds for hot-path lookup intents
    "brainstorm": 0.5,      # 30 minutes for brainstorm (may need user iteration)
    "reminder": 24.0,       # 24 hours for reminders
}
```

### Intent Type Categories

1. **Async/Task Intents** (hours scale)
   - `task-profile`: 6.0h - Default for bead-backed async tasks
   - `reminder`: 24.0h - Long-running reminder tasks
   - `brainstorm`: 0.5h - Collaborative sessions needing user iteration

2. **Hot-Path Intents** (seconds scale)
   - `status`: 30s - Quick status lookups (kubectl get, git log, etc.)
   - `action`: 30s - Fast actions (delete pod, restart, etc.)
   - `lookup`: 30s - Information lookups (config docs, logs, etc.)

## Per-Project Configuration

Projects can override default SLA durations in `config/registry.yaml`:

```yaml
projects:
  options-pipeline:
    description: "Options data pipeline on apexalgo-iad"
    sla_overrides:
      task-profile: 4.0  # 4 hours (override default 6h)
      action: 1.0        # 1 hour (override default 30s)
```

### Override Resolution Order

When a bead is created, SLA hours are resolved in this order:

1. **Project override** (if defined): `project.sla_overrides[intent_type]`
2. **Intent type default**: `DEFAULT_SLA_HOURS[intent_type]`
3. **Fallback default**: `6.0` hours (if neither 1 nor 2 apply)

## Implementation Details

### SLA Computation at Bead Creation

The escalate handler computes `sla_deadline` at bead creation time:

```python
# src/escalate/handler.py, line 621
async def _create_bead_watch(
    self,
    bead_ref: str,
    project_slug: str | None,
    intent_type: str,
) -> None:
    from ..registry import get_project

    sla_hours = None

    # 1. Check per-project, per-intent-type SLA override
    if project_slug:
        project = get_project(project_slug)
        if project:
            sla_overrides = project.get("sla_overrides", {})
            if sla_overrides and intent_type in sla_overrides:
                sla_hours = sla_overrides.get(intent_type)

    # 2. Create bead_watch row (sla_deadline computed here)
    store = await self._get_store()
    await store.create_bead_watch(
        bead_ref=bead_ref,
        sla_hours=sla_hours,  # None → uses DEFAULT_SLA_HOURS[intent_type]
        intent_type=intent_type,
    )
```

### Storage in bead_watch Table

The SLA deadline is stored in the `bead_watch` table:

```sql
CREATE TABLE IF NOT EXISTS bead_watch (
    bead_ref           TEXT PRIMARY KEY,
    sla_deadline       INTEGER NOT NULL,  -- Unix timestamp when SLA expires
    sla_flagged_at     INTEGER,           -- Timestamp when SLA was flagged
    -- ...
);
```

### Deadline Calculation

```python
# src/session/store.py, line 1323
async def create_bead_watch(
    self,
    bead_ref: str,
    sla_hours: float | None = None,
    intent_type: str = "task-profile",
) -> None:
    # Resolve SLA deadline
    if sla_hours is None:
        sla_hours = DEFAULT_SLA_HOURS.get(intent_type, 6.0)
    now = int(datetime.now().timestamp())
    sla_deadline = int(now + (sla_hours * 3600))

    # Store in bead_watch table
    await db.execute(
        """INSERT OR REPLACE INTO bead_watch
           (bead_ref, refusal_count, comment_high_water, sla_deadline, created_at)
           VALUES (?, 0, 0, ?, ?)""",
        (bead_ref, sla_deadline, now),
    )
```

## Circuit Breaker Integration

The SLA system integrates with the circuit breaker:

1. **SLA Flagging**: Beads past `sla_deadline` are flagged via `sla_flagged_at`
2. **Fencing Thresholds**: Beads are fenced (marked `status=blocked`) when:
   - Refusal count ≥ 3 (`CIRCUIT_BREAKER_REFUSAL_THRESHOLD`)
   - Age > 24h without progress (`CIRCUIT_BREAKER_AGE_THRESHOLD_HOURS`)

## Monitoring and Visibility

### SLA Exceeded Query

```python
# Get beads past SLA deadline but not yet flagged
past_sla = await store.get_beads_past_sla()
```

### Circuit Breaker Query

```python
# Get beads meeting fencing criteria
needs_fencing = await store.get_beads_needing_fencing()
```

## Testing

Comprehensive tests verify SLA functionality:

```bash
# Test default SLA constants
pytest tests/test_circuit_breaker.py::TestSLADefaults -xvs

# Test per-project overrides
pytest tests/test_circuit_breaker.py::TestPerProjectSLAOverrides -xvs

# Test bead_watch lifecycle
pytest tests/test_circuit_breaker.py::TestBeadWatchLifecycle -xvs

# Test SLA tracking and flagging
pytest tests/test_circuit_breaker.py::TestSLATracking -xvs
```

## Examples

### Example 1: Default SLA for Task-Profile

```python
# Create bead for task-profile intent (no project override)
await store.create_bead_watch(
    bead_ref="adc-123",
    intent_type="task-profile",
)
# sla_deadline ≈ now + 6 hours (DEFAULT_SLA_HOURS["task-profile"])
```

### Example 2: Per-Project Override

```yaml
# config/registry.yaml
projects:
  aide-de-camp:
    sla_overrides:
      task-profile: 8.0  # 8 hours for aide-de-camp task beads
```

```python
# Create bead for aide-de-camp project (uses override)
await handler._create_bead_watch(
    bead_ref="adc-456",
    project_slug="aide-de-camp",
    intent_type="task-profile",
)
# sla_deadline ≈ now + 8 hours (project override)
```

### Example 3: Hot-Path Intent SLA

```python
# Create bead for status intent (hot-path)
await store.create_bead_watch(
    bead_ref="status-789",
    intent_type="status",
)
# sla_deadline ≈ now + 30 seconds (DEFAULT_SLA_HOURS["status"])
```

## Configuration File Format

The SLA configuration lives in `config/registry.yaml` under each project:

```yaml
projects:
  <project-slug>:
    description: "Project description"
    cluster: <cluster-name>
    namespace: <namespace>
    sla_overrides:
      <intent-type>: <duration-in-hours>
      # Example:
      # task-profile: 4.0
      # action: 1.0
    # ... other project config
```

### Valid Intent Types for SLA Overrides

- `task-profile` - Bead-backed async tasks
- `status` - Status check intents
- `action` - Action execution intents
- `lookup` - Information lookup intents
- `brainstorm` - Collaborative brainstorming
- `reminder` - Reminder tasks

## Related Documentation

- **Plan**: `docs/plan/plan.md` - Async Path, Circuit Breaker, Visible Aging
- **Tests**: `tests/test_circuit_breaker.py` - Comprehensive test suite
- **Schema**: `src/session/store.py` - bead_watch table schema and operations
- **Registry**: `config/registry.yaml` - Project SLA override configuration

## Troubleshooting

### SLA Not Being Applied

1. Check `DEFAULT_SLA_HOURS` constants in `src/session/store.py`
2. Verify project config in `config/registry.yaml` has `sla_overrides` key
3. Confirm intent_type matches a key in `sla_overrides` or `DEFAULT_SLA_HOURS`
4. Check logs for "Using per-project SLA override" messages

### SLA Deadline Not Stored

1. Verify `bead_watch` table exists (check schema migration)
2. Check `sla_deadline` column is NOT NULL constraint
3. Review escalate handler logs for bead creation errors
4. Run `pytest tests/test_circuit_breaker.py::TestBeadWatchLifecycle` to verify storage

### Per-Project Override Not Working

1. Confirm `project_slug` is passed to `_create_bead_watch()`
2. Verify `get_project(project_slug)` returns project dict
3. Check project has `sla_overrides` dict with correct intent_type key
4. Test with `pytest tests/test_circuit_breaker.py::TestPerProjectSLAOverrides`
