# Bead Health Check - Automated Ready Frontier Monitoring

## Overview

Automated health check that monitors the bead ready frontier and applies auto-repair when starvation conditions are detected. This prevents the recurrence of bead starvation by catching it early and applying known repairs before the workspace fully starves.

## How It Works

The health check script (`scripts/bead_healthcheck.sh`) runs periodically (every 15 minutes by default) and:

1. **Collects statistics**: Counts ready beads and total open beads
2. **Evaluates health**: Compares against configurable thresholds
3. **Auto-repair**: When triggered, runs:
   - `bead doctor --repair` - Fixes stale indexes and views
   - Assigned-but-open bead detection - Identifies stuck beads
   - `bead sync flush-only` - Verifies database vs checkpoint consistency
4. **Re-verification**: Re-checks counts after repairs
5. **Logging**: All actions logged to `/tmp/bead-healthcheck.log` with timestamps

## Thresholds

Default thresholds (configurable in the script):
- **Ready bead threshold**: 5 minimum ready beads
- **Open bead threshold**: 50 total open beads

**Trigger condition**: `< 5 ready beads when > 50 total open beads exist`

## Installation

```bash
# Install the systemd timer
./scripts/install_bead_healthcheck.sh

# Or manually:
ln -sf /home/coding/aide-de-camp/deploy/bead-healthcheck.service ~/.config/systemd/user/
ln -sf /home/coding/aide-de-camp/deploy/bead-healthcheck.timer ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable bead-healthcheck.timer
systemctl --user start bead-healthcheck.timer
```

## Usage

### Manual Execution

```bash
# Run health check manually
./scripts/bead_healthcheck.sh

# View logs
tail -f /tmp/bead-healthcheck.log

# Check timer status
systemctl --user status bead-healthcheck.timer

# View next scheduled runs
systemctl --user list-timers bead-healthcheck.timer
```

### Management

```bash
# Disable the timer
systemctl --user disable bead-healthcheck.timer --now

# Re-enable the timer
systemctl --user enable bead-healthcheck.timer
systemctl --user start bead-healthcheck.timer

# View service logs
journalctl --user -u bead-healthcheck.service -f
```

## Log Format

```
[2026-09-01T06:27:41Z] === Bead Health Check Started ===
[2026-09-01T06:27:41Z] Collecting bead statistics...
[2026-09-01T06:27:41Z] Ready beads: 15
[2026-09-01T06:27:41Z] Total open beads: 15
[2026-09-01T06:27:41Z] ✓ Health check passed: ready frontier is healthy
[2026-09-01T06:27:41Z] === Bead Health Check Completed ===
```

When auto-repair is triggered, you'll see detailed steps:
```
[2026-09-01T06:30:00Z] ALERT: Starvation condition detected!
[2026-09-01T06:30:00Z] Starting auto-repair sequence...
[2026-09-01T06:30:01Z] Step 1: Running bead doctor --repair
[2026-09-01T06:30:05Z] ✓ bead doctor --repair completed successfully
[2026-09-01T06:30:05Z] Step 2: Checking for assigned-but-open beads
[2026-09-01T06:30:06Z] Found 3 assigned-but-open beads
[2026-09-01T06:30:06Z] Step 3: Running bead sync flush-only
[2026-09-01T06:30:08Z] ✓ Auto-repair successful: ready count restored to threshold
```

## Files

- `scripts/bead_healthcheck.sh` - Main health check script
- `scripts/install_bead_healthcheck.sh` - Installation helper
- `deploy/bead-healthcheck.service` - Systemd service unit
- `deploy/bead-healthcheck.timer` - Systemd timer unit
- `/tmp/bead-healthcheck.log` - Execution log

## Configuration

Edit the threshold variables in `scripts/bead_healthcheck.sh`:
```bash
READY_BEAD_THRESHOLD=5
OPEN_BEAD_THRESHOLD=50
```

Edit the schedule in `deploy/bead-healthcheck.timer`:
```ini
[Timer]
OnCalendar=*:0,15,30,45  # Every 15 minutes
```

## Testing

The script was successfully tested on 2026-09-01:
- Ready beads: 15 (threshold: 5) ✓
- Total open beads: 15 (threshold: 50) ✓
- Health check passed, no auto-repair required

## Related Issues

- Resolves starvation alert bead: `aidedeca-5c892d85`
- Prevents recurrence of bead starvation in the workspace
