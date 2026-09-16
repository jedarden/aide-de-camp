# Bead Ready Frontier Health Check

Automated health monitoring and repair system for the bead workspace ready frontier. Prevents bead starvation by running periodic diagnostics and applying known repairs when thresholds are triggered.

## Problem Solved

The ready frontier can become invisible to workers due to:
- Stale database indexes or views
- Assigned-but-open beads (a known bug where beads retain assignees after being reopened)
- Database vs checkpoint inconsistency
- Other workspace corruption

This system catches these issues early and applies automated repairs before the workspace fully starves.

## How It Works

### Threshold Trigger Logic

The health check runs every 15 minutes and triggers diagnostics when:
- **Ready beads < 5** AND **Total open beads >= 50**

This logic prevents false positives in small workspaces while catching genuine starvation in active ones.

### Automated Repair Sequence

When thresholds are triggered, the system automatically runs:

1. **`bead doctor --repair`** — Fixes stale indexes and views
2. **Assigned-but-open bead detection** — Identifies and reports beads stuck in an assigned-but-open state
3. **`bead sync flush-only`** — Verifies database vs checkpoint consistency

### Post-Repair Verification

After repairs, the system re-checks bead counts and reports:
- Success if ready beads >= 5
- Incomplete if ready beads still < 5 (requires manual intervention)

## Installation

### Quick Start

```bash
# Run the setup script
./scripts/setup-bead-healthcheck.sh
```

This creates symlinks to systemd units and enables the timer. The health check will run every 15 minutes.

### Manual Setup

```bash
# Create symlinks
mkdir -p ~/.config/systemd/user
ln -sfT $(pwd)/deploy/bead-healthcheck.service ~/.config/systemd/user/bead-healthcheck.service
ln -sfT $(pwd)/deploy/bead-healthcheck.timer ~/.config/systemd/user/bead-healthcheck.timer

# Reload systemd and enable timer
systemctl --user daemon-reload
systemctl --user enable --now bead-healthcheck.timer
```

## Usage

### Check Status

```bash
# Check if timer is running
systemctl --user status bead-healthcheck.timer

# List next scheduled run times
systemctl --user list-timers bead-healthcheck.timer

# View recent logs
tail -f /tmp/bead-healthcheck.log
```

### Manual Trigger

```bash
# Run health check immediately
systemctl --user start bead-healthcheck

# Or run directly
./scripts/bead-healthcheck.sh
```

### Disable/Stop

```bash
# Stop and disable the timer
systemctl --user disable --now bead-healthcheck.timer
```

## Configuration

Edit `scripts/bead-healthcheck.sh` to adjust thresholds:

```bash
READY_THRESHOLD=5              # Minimum ready beads before starvation
TOTAL_OPEN_THRESHOLD=50        # Minimum total open beads to trigger check
```

## Log Format

Logs are written to `/tmp/bead-healthcheck.log` with structured timestamps:

```
[2026-09-01T13:12:39Z] [INFO] === Starting bead health check ===
[2026-09-01T13:12:39Z] [INFO] Collecting bead statistics...
[2026-09-01T13:12:39Z] [INFO] Ready beads: 4
[2026-09-01T13:12:39Z] [INFO] Total open beads: 4
[2026-09-01T13:12:39Z] [INFO] Total open beads (4) below threshold (50) - skipping diagnostic
[2026-09-01T13:12:39Z] [INFO] === Health check complete - no action needed ===
```

## Troubleshooting

### Health Check Not Running

```bash
# Check timer status
systemctl --user status bead-healthcheck.timer

# Check if service is enabled
systemctl --user is-enabled bead-healthcheck.timer

# View systemd logs
journalctl --user -u bead-healthcheck -n 50
```

### High Ready Count But No Work

This indicates a different issue (not starvation). Check:
- Are there actual unassigned open beads?
- Are dependencies blocking the ready frontier?
- Is there a worker available to claim beads?

### Repair Incomplete

If the health check reports "REPAIR INCOMPLETE":

1. Check `/tmp/bead-healthcheck.log` for specific errors
2. Run manual diagnostics:
   ```bash
   bead doctor
   bead list --ready
   bead list --status open --json | jq '[.[] | select(.assignee != null)]'
   ```
3. If issues persist, manual intervention may be required

## Files

- `scripts/bead-healthcheck.sh` — Main health check script
- `scripts/setup-bead-healthcheck.sh` — Installation script
- `deploy/bead-healthcheck.service` — Systemd service unit
- `deploy/bead-healthcheck.timer` — Systemd timer unit
- `/tmp/bead-healthcheck.log` — Health check logs

## Related Documentation

- `CLAUDE.md` — Bead system overview
- `memory/performance-analysis-locking-strategy.md` — Bead locking analysis
- Bead starvation alert beads (triggered when ready frontier is empty)
