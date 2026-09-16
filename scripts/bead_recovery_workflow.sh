#!/usr/bin/env bash
# Automated bead workspace recovery workflow
# Handles the most common starvation causes: stale checkpoint and silent corruption
# Logs all actions to /tmp/bead-recovery.log with timestamps

set -euo pipefail

# Configuration
STALE_THRESHOLD_SECONDS=3600  # 1 hour
LOG_FILE="/tmp/bead-recovery.log"
WORKSPACE_DIR="/home/coding/aide-de-camp"
CHECKPOINT_DIR="$WORKSPACE_DIR/.beads/checkpoint"
FORENSIC_CHECKPOINT="$CHECKPOINT_DIR/forensic.jsonl"

# Timestamp function
log() {
    local timestamp
    timestamp=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
    echo "[$timestamp] $*" | tee -a "$LOG_FILE"
}

# Error handling
error_exit() {
    log "ERROR: $*"
    exit 1
}

# Change to workspace directory
cd "$WORKSPACE_DIR" || error_exit "Failed to cd to workspace: $WORKSPACE_DIR"

# Resolve the bead CLI once. The systemd user manager runs callers with a
# minimal PATH that does not include ~/.local/bin or ~/.cargo/bin, where the
# bead wrapper and binaries live — under the timer a bare `bead` fails with
# "command not found" and set -e aborts the whole workflow mid-run. A BEAD_BIN
# override (scripts/enrich_starvation_alerts.py sets it) wins over discovery.
if [ -n "${BEAD_BIN:-}" ] && [ -x "${BEAD_BIN:-}" ]; then
    :
elif command -v bead >/dev/null 2>&1; then
    BEAD_BIN="$(command -v bead)"
elif [ -x "$HOME/.local/bin/bead" ]; then
    BEAD_BIN="$HOME/.local/bin/bead"
elif [ -x "$HOME/.cargo/bin/bead" ]; then
    BEAD_BIN="$HOME/.cargo/bin/bead"
else
    error_exit "no usable bead CLI found (looked on PATH, ~/.local/bin/bead, ~/.cargo/bin/bead)"
fi
bead() { "$BEAD_BIN" "$@"; }

log "=== Bead Recovery Workflow Started ==="
log "Working directory: $WORKSPACE_DIR"

# Step 1: Check if checkpoint is stale
log "Step 1: Checking checkpoint freshness..."

if [ ! -f "$CHECKPOINT_DIR/current.json" ]; then
    log "WARNING: No current.json checkpoint found"
    current_age_seconds=$((STALE_THRESHOLD_SECONDS + 1))
else
    current_mtime=$(stat -c %Y "$CHECKPOINT_DIR/current.json" 2>/dev/null || echo "0")
    current_time=$(date +%s)
    current_age_seconds=$((current_time - current_mtime))
fi

log "Checkpoint age: $current_age_seconds seconds (threshold: $STALE_THRESHOLD_SECONDS)"

if [ "$current_age_seconds" -gt "$STALE_THRESHOLD_SECONDS" ]; then
    log "⚠ Checkpoint is stale (> 1 hour old)"

    # Step 2: Force checkpoint publication
    log "Step 2: Running bead sync flush-only to force checkpoint publication..."
    if bead sync flush-only 2>&1 | tee -a "$LOG_FILE"; then
        log "✓ bead sync flush-only completed successfully"
    else
        log "✗ bead sync flush-only failed (exit code: $?)"
        log "Continuing with verification..."
    fi
else
    log "✓ Checkpoint is fresh (< 1 hour old)"
fi

# Step 3: Verify bead visibility
log "Step 3: Verifying bead visibility with bead list --status open --json..."
# Count beads in a captured `bead list --json` payload. Output is compact JSONL
# that has also been seen as nested arrays, so slurp-and-flatten before counting
# (the same normalization bead-healthcheck.sh applies) — a bare `jq -s length`
# would count lines, not beads. An empty or failed capture counts as 0, which
# here routes to the deep-recovery branch below rather than masking anything:
# unlike in the healthcheck, "unreadable" and "empty" deserve the same response.
count_payload() {
    local n
    n="$(echo "$1" | jq -s 'map(if type == "array" then .[] else . end) | length' 2>/dev/null || true)"
    echo "${n:-0}"
}
# --limit overrides the CLI's silent default cap (100): a workspace with more
# than 100 open beads would otherwise count as 100, and this count decides
# whether the deep-recovery branch below runs at all.
bead_list_output=$(bead list --status open --json --limit 999999 2>/dev/null) \
    || log "WARN: bead list --status open failed - treating the queue as unreadable (count 0) so recovery still runs"
open_count_before=$(count_payload "$bead_list_output")

log "Open beads count: $open_count_before"

if [ "$open_count_before" -eq 0 ]; then
    log "⚠ No open beads found - possible workspace corruption"

    # Step 4: Check for corruption with bead doctor --rehearse
    log "Step 4: Running bead doctor --rehearse for corruption detection..."

    if bead doctor --rehearse 2>&1 | tee -a "$LOG_FILE"; then
        log "✓ bead doctor --rehearse passed (no corruption detected)"

        # Step 5: If rehearsal passes, attempt recovery from forensic checkpoint
        if [ -f "$FORENSIC_CHECKPOINT" ] && [ -s "$FORENSIC_CHECKPOINT" ]; then
            log "Step 5: Forensic checkpoint found, attempting recovery..."
            log "Running: bead init && bead sync import-only --restore-into-empty"

            # Backup current database if it exists
            if [ -f "$WORKSPACE_DIR/.beads/beads.db" ]; then
                backup_file="$WORKSPACE_DIR/.beads/beads.db.backup-$(date +%s)"
                log "Backing up current database to: $backup_file"
                cp "$WORKSPACE_DIR/.beads/beads.db" "$backup_file"
            fi

            # Initialize and restore
            if bead init 2>&1 | tee -a "$LOG_FILE"; then
                log "✓ bead init completed successfully"

                if bead sync import-only --input "$FORENSIC_CHECKPOINT" --restore-into-empty --actor automated-recovery 2>&1 | tee -a "$LOG_FILE"; then
                    log "✓ bead sync import-only completed successfully"
                    recovery_successful=true
                else
                    log "✗ bead sync import-only failed (exit code: $?)"
                    recovery_successful=false
                fi
            else
                log "✗ bead init failed (exit code: $?)"
                recovery_successful=false
            fi
        else
            log "⚠ No forensic checkpoint found or file is empty"
            log "Forensic checkpoint path: $FORENSIC_CHECKPOINT"
            recovery_successful=false
        fi
    else
        log "✗ bead doctor --rehearse failed (exit code: $?)"
        log "Corruption may be severe - manual intervention required"
        recovery_successful=false
    fi
else
    log "✓ Bead visibility confirmed: $open_count_before open beads found"
    recovery_successful=true
fi

# Step 6: Verify recovery
if [ "$recovery_successful" = true ]; then
    log "Step 6: Verifying recovery by querying for open beads again..."
    bead_list_output=$(bead list --status open --json --limit 999999 2>/dev/null) || true
    open_count_after=$(count_payload "$bead_list_output")

    log "Open beads count after recovery: $open_count_after"

    if [ "$open_count_after" -gt 0 ]; then
        log "✓ Recovery verified: beads are visible"
    else
        log "⚠ Recovery incomplete: no beads visible after recovery"
        log "Manual investigation may be required"
    fi
else
    log "Step 6: Recovery verification skipped - recovery did not complete"
fi

# Step 7: Replenish the ready frontier when it is legitimately empty
# A zero ready count is usually *correct* — every open bead manually blocked,
# dependency-blocked, deferred, or in flight — not starvation to repair. The
# replenisher re-verifies that independently (corruption via doctor --rehearse,
# stale assignees, and open beads the frontier query cannot explain all make it
# refuse rather than paper over the state) and only then mints replacement work
# from the workspace's own backlog: stub-inventory findings, TODO/FIXME
# markers, and unchecked plan items. Cap 5 per run, labelled auto:replenished,
# deduped against open beads by title and target file, with same-file beads
# serialized via --depends-on attached inside the create transaction. It only
# ever issues `bead create` — existing beads, manually blocked ones included,
# are never modified or unblocked.
ready_output=$(bead list --ready --json --limit 999999 2>/dev/null) || true
ready_count_before_replenish=$(count_payload "$ready_output")
log "Step 7: Ready frontier count: $ready_count_before_replenish"

replenish_outcome="skipped_frontier_not_empty"
if [ "$ready_count_before_replenish" -eq 0 ]; then
    log "⚠ Ready frontier is empty - running diagnostics-gated replenishment..."

    if [ -x "$WORKSPACE_DIR/.venv/bin/python" ]; then
        ADC_PYTHON="$WORKSPACE_DIR/.venv/bin/python"
    else
        ADC_PYTHON="$(command -v python3 || true)"
    fi
    REPLENISH_SCRIPT="$WORKSPACE_DIR/scripts/replenish_ready_frontier.py"

    if [ -n "$ADC_PYTHON" ] && [ -f "$REPLENISH_SCRIPT" ]; then
        # The replenisher is stdlib-only, so the venv is a preference, not a
        # requirement. BEAD_BIN is passed explicitly because the systemd user
        # manager's PATH does not include ~/.local/bin.
        if "$ADC_PYTHON" "$REPLENISH_SCRIPT" \
                --workspace "$WORKSPACE_DIR" \
                --bead-bin "$BEAD_BIN" \
                --output /tmp/bead-replenish-report.json 2>&1 | tee -a "$LOG_FILE"; then
            replenish_outcome="$(jq -r '.outcome // "unknown"' /tmp/bead-replenish-report.json 2>/dev/null || echo "unknown")"
            log "✓ Replenishment ran to completion (outcome: $replenish_outcome)"
        else
            replenish_outcome="error"
            log "✗ replenish_ready_frontier.py failed - see /tmp/bead-replenish-report.json"
        fi
    else
        replenish_outcome="unavailable"
        log "WARN: replenisher unavailable (python: ${ADC_PYTHON:-none}, script: $REPLENISH_SCRIPT)"
    fi

    ready_output=$(bead list --ready --json --limit 999999 2>/dev/null) || true
    ready_count_after_replenish=$(count_payload "$ready_output")
    log "Ready frontier after replenishment attempt: $ready_count_after_replenish"
else
    log "✓ Ready frontier has candidates - no replenishment needed"
fi

# Step 8: Report success/failure via structured logs
log "Step 8: Structured recovery report"
log "=== RECOVERY_SUMMARY ==="
log "checkpoint_age_seconds: $current_age_seconds"
log "checkpoint_stale: $([ "$current_age_seconds" -gt "$STALE_THRESHOLD_SECONDS" ] && echo "true" || echo "false")"
log "open_beads_before: $open_count_before"
log "open_beads_after: ${open_count_after:-0}"
log "recovery_successful: $recovery_successful"
log "ready_count_before_replenish: $ready_count_before_replenish"
log "replenish_outcome: $replenish_outcome"
log "ready_count_after_replenish: ${ready_count_after_replenish:-n/a}"
log "timestamp: $(date -u +"%Y-%m-%dT%H:%M:%SZ")"
log "=== END_RECOVERY_SUMMARY ==="

if [ "$recovery_successful" = true ] && [ "${open_count_after:-0}" -gt 0 ]; then
    log "✓ Recovery workflow completed successfully"
else
    log "⚠ Recovery workflow completed with issues"
    log "Manual investigation may be required"
fi

log "=== Bead Recovery Workflow Completed ==="
echo ""

exit 0
