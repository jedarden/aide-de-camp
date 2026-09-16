# Pluck Starvation Diagnostic Suite

## Overview

Automated diagnostic script for investigating pluck starvation alerts when beads become invisible to the ready frontier despite existing in the database.

## Script

**Location:** `scripts/diagnose_pluck_starvation.py`

**Purpose:** Comprehensive automated diagnostics that eliminate the need for human investigation when a starvation alert is raised.

## Diagnostic Checks

The script performs 5 comprehensive checks:

### 1. Bead Store Consistency
- Direct database query to count beads by status
- Detects assigned-but-open beads (stuck state)
- Identifies beads with dependencies
- Checks manually blocked beads

### 2. Checkpoint Freshness
- Compares current.json against forensic.jsonl
- Detects stale or inconsistent checkpoints
- Checks for publish.lock file (stalled sync)
- Validates issue counts match between files

### 3. Pluck Query Logic Validation
- Executes `bead list --ready --json` and captures results
- Logs the exact query results and ready frontier count
- Compares against existing pluck diagnostics
- Detects starvation conditions (open beads exist but no candidates)

### 4. Database Corruption Detection
- Runs `bead doctor --rehearse` (non-destructive test)
- Validates recovery capability from checkpoint
- Detects schema inconsistencies
- Checks for structural corruption

### 5. Configuration Validation
- Validates `.beads/config.json` format
- Checks `.needle.yaml` backend declaration
- Detects bead-rs vs bf mismatches
- Ensures configuration consistency

## Usage

### Basic Execution

```bash
# Run diagnostics on default workspace
.venv/bin/python3 scripts/diagnose_pluck_starvation.py

# Run on specific workspace
.venv/bin/python3 scripts/diagnose_pluck_starvation.py --workspace /path/to/workspace

# Quiet mode (only summary)
.venv/bin/python3 scripts/diagnose_pluck_starvation.py --quiet

# Custom output path
.venv/bin/python3 scripts/diagnose_pluck_starvation.py --output /tmp/my-report.json
```

### Output Format

The script generates a structured JSON report:

```json
{
  "metadata": {
    "workspace": "/home/coding/aide-de-camp",
    "timestamp": "2026-09-01T14:27:29.793403+00:00",
    "diagnostic_duration_seconds": 0.38,
    "overall_status": "HEALTHY",
    "overall_message": "No critical or high-severity issues detected"
  },
  "findings": [
    {
      "category": "database",
      "severity": "info",
      "severity_level": 1,
      "message": "Database contains 1537 beads (5 open, 2 in progress, 1530 closed)",
      "timestamp": "2026-09-01T14:27:29.794499+00:00",
      "details": { ... },
      "recommendation": "Run: bead doctor --repair"
    }
  ],
  "detailed_results": {
    "database": { ... },
    "checkpoint": { ... },
    "pluck_query": { ... },
    "corruption_check": { ... },
    "config": { ... }
  },
  "recommendations": [
    "[CRITICAL] Run: bead doctor --repair to fix database corruption",
    "[HIGH] Run: bead sync flush-only to synchronize checkpoint"
  ]
}
```

### Severity Levels

- **CRITICAL** (5): Data corruption or loss requiring immediate repair
- **HIGH** (4): Starvation confirmed, beads truly invisible to pluck
- **MEDIUM** (3): Potential issue detected, investigation recommended
- **LOW** (2): Minor inconsistency, informational
- **INFO** (1): Informational, no action required

## Integration with Starvation Alerts

The diagnostic suite is wired into the alert path end to end — no step needs a
human unless the automation is genuinely stuck:

```
bead-healthcheck.timer (every 15 min)
  └─ scripts/bead-healthcheck.sh
       └─ Step 5: scripts/enrich_starvation_alerts.py   (real run — see below)
            ├─ scripts/diagnose_pluck_starvation.py --quiet --output <report>
            ├─ scripts/bead_recovery_workflow.sh        (logs RECOVERY_SUMMARY
            │                                            to /tmp/bead-recovery.log)
            └─ bead update + bead label (+ bead close for proven verdicts)
```

The enricher finds every open bead titled `Starvation alert: ...` (plain
NEEDLE alerts and `[Unravel]` alternatives alike) that does not yet carry a
report, then writes into its notes: the report JSON path, `overall_status`,
top recommendations, the recovery workflow's RECOVERY_SUMMARY, and one
classification label:

| Label | Meaning | Bead |
|---|---|---|
| `starvation:auto-recovered` | recovery restored the frontier / visibility | closed |
| `starvation:false-positive` | frontier reads empty, diagnostics prove healthy | closed |
| `starvation:legitimately-blocked` | every open bead manual/dependency blocked | stays open |
| `starvation:unresolved` | starvation survived automated recovery | stays open |

Two operational details that have each broken this chain silently before:

- The healthcheck must build its `--dry-run` flag for the enricher with a real
  conditional, never `${DRY_RUN:+--dry-run}` — that expansion tests
  non-emptiness, and `DRY_RUN=false` is non-empty, so it pinned the enricher
  to dry-run and no alert was ever enriched while the logs said "would enrich".
- `bead update --notes` replaces the whole notes field. The enricher reads the
  current notes back first and writes the combination under `--if-revision`,
  so enrichment can never erase investigation notes a bead already carries.

## Example Outputs

### Healthy Workspace

```
Overall Status: HEALTHY
Duration: 0.38 seconds
Findings: 6
Output: /tmp/pluck-starvation-diagnostic-20260901_142730.json

Top Recommendations:
  • [MEDIUM] Check if bead sync is running; if stalled, remove publish.lock
```

### Starvation Detected

```
Overall Status: CRITICAL
Duration: 0.42 seconds
Findings: 8
Output: /tmp/pluck-starvation-diagnostic-20260901_142108.json

Top Recommendations:
  • [CRITICAL] Run: bead doctor --repair to fix database corruption
  • [HIGH] Run: bead sync flush-only to synchronize checkpoint
  • [MEDIUM] Review full output with: bead doctor --rehearse
```

## Common Issues and Remediations

### Database Schema Error
**Finding:** `Database error: no such column: issue_id`
**Cause:** Dependencies table uses `blocked_issue_id` and `blocker_issue_id`
**Fix:** Script automatically handles correct schema

### Checkpoint Inconsistency
**Finding:** `current.json reports 1537 issues but forensic.jsonl has 8904 lines`
**Cause:** forensic.jsonl contains both issues AND events (not just issues)
**Fix:** Script now counts only issue records for comparison

### JSON Parsing Error
**Finding:** `Could not parse bead list --ready output`
**Cause:** Output is JSONL (one object per line), a bare `[]` when empty, and has been seen as nested arrays
**Fix:** `parse_bead_payload()` flattens every shape to one list of bead dicts — an empty frontier counts 0, never 1, and never reaches dict-only consumers as a list

## Runtime Requirements

- Python 3.8+
- sqlite3 module (standard library)
- bead CLI (bead-rs) in PATH
- Read access to `.beads/` directory
- Write access to `/tmp/` for output

## Performance

- **Typical runtime:** ~4 seconds on this workspace (the `bead doctor --rehearse` corruption check dominates at ~3s)
- **Timeout:** 60 seconds for the rehearse subprocess, 120 seconds for the whole suite when invoked from the enricher
- **Memory usage:** Minimal (direct database queries)
- **Disk I/O:** Reads database and checkpoint files only

## Maintenance

The script is self-contained and requires no external dependencies beyond the Python standard library. Update considerations:

1. **Schema changes:** If bead-rs database schema changes, update SQL queries
2. **New bead CLI versions:** Test with new `bead doctor --rehearse` output format
3. **Additional checks:** Add new diagnostic categories following existing pattern

## Testing

Verify script works correctly:

```bash
# Test on healthy workspace
.venv/bin/python3 scripts/diagnose_pluck_starvation.py

# Test with quiet mode
.venv/bin/python3 scripts/diagnose_pluck_starvation.py --quiet

# Verify JSON output validity
jq . /tmp/pluck-starvation-diagnostic-*.json
```

## Related Files

- `scripts/bead-healthcheck.sh` — Ready frontier health check; Step 5 invokes the enricher every pass
- `scripts/enrich_starvation_alerts.py` — attaches reports and classification labels to alert beads
- `scripts/bead_recovery_workflow.sh` — recovery pass behind the enricher; writes RECOVERY_SUMMARY to /tmp/bead-recovery.log
- `deploy/bead-healthcheck.service` / `.timer` — the 15-minute timer (symlinked from `~/.config/systemd/user/`)
- `tests/test_enrich_starvation_alerts.py` — unit tests for the enricher
- `docs/notes/bead-health-check.md` — Health check documentation
- `.beads/diagnostics/pluck-diagnostics.json` — Existing pluck diagnostics
