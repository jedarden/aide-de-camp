# Automated Bead Recovery System

## Overview

The aide-de-camp workspace has a comprehensive automated recovery system that detects and resolves bead starvation issues without human intervention. This system handles the two most common causes of bead invisibility:

1. **Stale checkpoint** - Checkpoint hasn't been flushed recently, making beads invisible to queries
2. **Silent database corruption** - Database corruption that prevents beads from being queried

## Components

### 1. Health Check Daemon (`bead-healthcheck.service`)

Runs every 15 minutes via `bead-healthcheck.timer` to monitor the ready frontier health.

**Configuration:**
- **Trigger:** Every 15 minutes (`OnCalendar=*:0/15`)
- **Thresholds:**
  - Ready beads < 5 → triggers recovery
  - Total open beads ≥ 50 → requires diagnostic
- **Log file:** `/tmp/bead-healthcheck.log`

**What it monitors:**
- Ready bead count (beads available for pluck)
- Total open bead count
- Checkpoint freshness
- Database integrity

### 2. Recovery Workflow (`bead_recovery_workflow.sh`)

Comprehensive 7-step recovery process invoked automatically when starvation is detected.

**Steps:**
1. **Check checkpoint freshness** - Verifies if last checkpoint flush was > 1 hour ago
2. **Force checkpoint publication** - Runs `bead sync flush-only` if checkpoint is stale
3. **Verify bead visibility** - Queries `bead list --status open --json` to confirm beads are accessible
4. **Detect corruption** - Runs `bead doctor --rehearse` to identify database issues without mutation
5. **Recover from checkpoint** - If corruption detected, runs `bead init && bead sync import-only --restore-into-empty` using forensic checkpoint
6. **Verify recovery** - Re-queries open beads to confirm recovery succeeded
7. **Report results** - Logs structured summary with all metrics and outcomes

**Log file:** `/tmp/bead-recovery.log`

### 3. Diagnostic Suite (`diagnose_pluck_starvation.py`)

Comprehensive diagnostic tool for manual investigation of starvation issues.

**Capabilities:**
- Direct database consistency checks
- Checkpoint freshness verification
- Pluck query logic validation
- Database corruption detection
- Configuration validation (bead-rs vs bf mismatch)

**Output:** Structured JSON report with findings, severity levels, and recommendations.

## How It Works

### Normal Operation

1. **Health check runs** every 15 minutes
2. **Queries ready beads** - `bead list --ready --json`
3. **Queries total open beads** - `bead list --status open --json`
4. **Compares against thresholds**
   - If ready beads ≥ 5 → **HEALTHY** (exit success)
   - If total open beads < 50 → **HEALTHY** (exit success)

### Starvation Detection

When thresholds are triggered:
1. **Health check detects starvation** (ready < 5 AND open ≥ 50)
2. **Invokes comprehensive recovery workflow** automatically
3. **Recovery workflow executes all 7 steps**
4. **Health check verifies recovery** by re-querying bead counts
5. **Reports success/failure** via structured logs

### Recovery Scenarios

#### Scenario 1: Stale Checkpoint

```
✓ Checkpoint is stale (> 1 hour old)
✓ Running: bead sync flush-only
✓ Checkpoint published successfully
✓ Bead visibility confirmed
✓ Recovery successful
```

#### Scenario 2: Database Corruption

```
✓ Checkpoint is fresh
✗ No open beads found - possible workspace corruption
✓ Running: bead doctor --rehearse
✓ No corruption detected (rehearsal passed)
✓ Running: bead init && bead sync import-only --restore-into-empty
✓ Database rebuilt from forensic checkpoint
✓ Recovery verified: beads are visible
✓ Recovery successful
```

#### Scenario 3: Severe Corruption

```
✓ Checkpoint is fresh
✗ No open beads found
✓ Running: bead doctor --rehearse
✗ Corruption detected
⚠ Manual intervention required
```

## Log Files

### Health Check Log
**Location:** `/tmp/bead-healthcheck.log`

**Sample output:**
```
[2026-09-01T15:00:00Z] [INFO] === Starting bead health check ===
[2026-09-01T15:00:00Z] [INFO] Ready beads: 0
[2026-09-01T15:00:00Z] [INFO] Total open beads: 1537
[2026-09-01T15:00:00Z] [ERROR] STARVATION DETECTED
[2026-09-01T15:00:00Z] [INFO] Executing comprehensive recovery workflow...
[2026-09-01T15:00:01Z] ✓ Recovery verified: beads are visible
[2026-09-01T15:00:01Z] [INFO] === Health check complete - REPAIR SUCCESSFUL ===
```

### Recovery Workflow Log
**Location:** `/tmp/bead-recovery.log`

**Structured summary:**
```
=== RECOVERY_SUMMARY ===
checkpoint_age_seconds: 199
checkpoint_stale: false
open_beads_before: 0
open_beads_after: 4
recovery_successful: true
timestamp: 2026-09-01T15:00:01Z
=== END_RECOVERY_SUMMARY ===
```

## Manual Invocation

### Run Recovery Workflow Manually

```bash
./scripts/bead_recovery_workflow.sh
```

### Run Health Check Manually

```bash
./scripts/bead-healthcheck.sh
```

### Run Comprehensive Diagnostics

```bash
./scripts/diagnose_pluck_starvation.py
# With custom workspace:
./scripts/diagnose_pluck_starvation.py --workspace /path/to/workspace
# Quiet mode (summary only):
./scripts/diagnose_pluck_starvation.py --quiet
```

## System Status Verification

### Check if Timer is Active

```bash
systemctl --user status bead-healthcheck.timer
```

### View Recent Health Check Logs

```bash
# Systemd journal
journalctl --user -u bead-healthcheck.service -n 50

# Log file
tail -f /tmp/bead-healthcheck.log
```

### View Recovery Logs

```bash
tail -f /tmp/bead-recovery.log
```

## Configuration

### Adjust Thresholds

Edit `scripts/bead-healthcheck.sh`:

```bash
READY_THRESHOLD=5           # Minimum ready beads required
TOTAL_OPEN_THRESHOLD=50     # Minimum total open beads to trigger diagnostic
```

### Adjust Checkpoint Threshold

Edit `scripts/bead_recovery_workflow.sh`:

```bash
STALE_THRESHOLD_SECONDS=3600  # 1 hour
```

### Adjust Check Frequency

Edit `deploy/bead-healthcheck.timer`:

```ini
[Timer]
# Run every N minutes
OnCalendar=*:0/N
```

Then reload:

```bash
systemctl --user daemon-reload
systemctl --user restart bead-healthcheck.timer
```

## Integration with NEEDLE

This recovery system is designed to work seamlessly with NEEDLE fleet workers:

- **Non-invasive** - Workers can continue running during recovery
- **Idempotent** - Safe to run multiple times
- **Atomic operations** - Uses `bead sync flush-only` and `bead doctor --rehearse` for safe operations
- **Checkpoint-based recovery** - Uses durable forensic checkpoint for reliable restoration

## Failure Modes and Recovery

### Recovery Workflow Fails

If the recovery workflow fails (exit code != 0):

1. **Check logs** - `/tmp/bead-recovery.log` for detailed error messages
2. **Run diagnostics** - `./scripts/diagnose_pluck_starvation.py` for comprehensive analysis
3. **Manual intervention** - May be required if:
   - Forensic checkpoint is missing or corrupted
   - Database corruption is too severe for automated recovery
   - Workspace configuration is invalid

### Health Check Timer Stops

If the timer is not running:

```bash
# Check status
systemctl --user status bead-healthcheck.timer

# Restart if stopped
systemctl --user start bead-healthcheck.timer

# Enable if disabled
systemctl --user enable bead-healthcheck.timer
```

## Monitoring and Alerting

### Key Metrics to Monitor

1. **Ready bead count** - Should be > 0 in active workspace
2. **Recovery frequency** - Frequent recoveries indicate underlying issues
3. **Recovery success rate** - Should be near 100%
4. **Checkpoint freshness** - Should be < 1 hour old

### Alert Conditions

- **Recovery fails** - Check logs immediately
- **Recovery runs more than once per hour** - Investigate root cause
- **Ready count remains 0 after recovery** - Manual intervention required

## Related Documentation

- [Bead-rs CLI Reference](../../../.beads/docs/bead-rs-cli.md) - Bead command documentation
- [NEEDLE Fleet Operations](../../../NEEDLE/docs/fleet-operations.md) - Fleet worker management
- [Workspace Recovery Guide](../../../docs/workspace-recovery.md) - Manual recovery procedures

## Troubleshooting

### Issue: Recovery completes but beads still invisible

**Possible causes:**
1. Checkpoint was also stale
2. Database corruption beyond recovery
3. Configuration mismatch (bead-rs vs bf)

**Resolution:**
```bash
# Run comprehensive diagnostics
./scripts/diagnose_pluck_starvation.py

# Check configuration
cat .beads/config.json
cat .needle.yaml | grep backend

# Manual recovery if needed
bead doctor --repair
bead sync flush-only
```

### Issue: Recovery runs frequently

**Possible causes:**
1. Checkpoint not auto-flushing (R026 activation not applied)
2. Database corruption recurring
3. Worker claiming/releasing beads rapidly

**Resolution:**
```bash
# Check checkpoint auto-flush configuration
cat .beads/config.json | grep auto_flush

# Check recent recovery logs
grep "recovery_successful: false" /tmp/bead-recovery.log | tail -10
```

### Issue: Health check timer misses scheduled runs

**Possible causes:**
1. System was asleep
2. systemd user session not running
3. Timer disabled

**Resolution:**
```bash
# Verify timer is active
systemctl --user list-timers | grep bead-healthcheck

# Check next scheduled run
systemctl --user status bead-healthcheck.timer

# Manually trigger health check
systemctl --user start bead-healthcheck.service
```

## Design Principles

1. **Safety first** - All operations use read-only checks before mutation
2. **Idempotent** - Safe to run multiple times without side effects
3. **Transparent logging** - Every operation logged with timestamp and outcome
4. **Graceful degradation** - Falls back to basic repairs if comprehensive workflow unavailable
5. **Non-disruptive** - Workers can continue running during recovery
6. **Durable recovery** - Uses forensic checkpoint as single source of truth
