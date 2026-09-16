#!/run/current-system/sw/bin/bash
# Automated ready frontier health check: classify every run, repair only when large
#
# Every pass runs the cheap unconditional steps — the assigned-but-open sweep,
# the checkpoint freshness flush, and a full frontier classification — no matter
# how small the workspace is. The earlier version exited early whenever total
# open beads were below TOTAL_OPEN_THRESHOLD, which for this workspace is every
# run, so the starvation this workspace actually experiences was invisible to
# the automation built to catch it. Two starvation triggers now respond to the
# shapes that actually occur: the heavyweight bead_recovery_workflow.sh behind
# the high-volume thresholds (TOTAL_OPEN >= 50), and the low-volume shape
# (ready frontier empty while open beads exist) answered with the read-only
# diagnostic suite plus a report path in the log. The sweep clears an assignee
# only once its worker is proven heartbeat-dead — a live assignee is never
# cleared. Step 3b resolves or defers the underspecified beads that starve the
# frontier — open and dependency-free but unactionable as written — from
# read-only live evidence, so they become claimable or leave the frontier
# honestly. Step 6 unblocks beads whose notes record a credential-read failure
# by confirming the secret via the write-only provisioning identity and
# recording the runtime delivery, so no human grant sits on that path. A run
# that cannot read the queue or classify the frontier exits 3 — an unknown
# state is never reported as healthy.

set -euo pipefail

# Configuration (env-overridable so a verification run can exercise the repair
# path without waiting for the live queue to hit the production thresholds)
WORKSPACE_DIR="${WORKSPACE_DIR:-/home/coding/aide-de-camp}"
LOG_FILE="${LOG_FILE:-/tmp/bead-healthcheck.log}"
READY_THRESHOLD="${READY_THRESHOLD:-5}"
TOTAL_OPEN_THRESHOLD="${TOTAL_OPEN_THRESHOLD:-50}"
# An assignee whose worker's latest .beads/heartbeats.jsonl entry is older
# than this is gone; its assigned-but-open beads are repairable. 30 minutes
# spans two timer ticks, so a live worker idling between polls never reads
# as dead.
HEARTBEAT_STALE_SECONDS="${HEARTBEAT_STALE_SECONDS:-1800}"
# bead list silently caps output at --limit (default 100); sweep the whole queue
BEAD_LIST_LIMIT="${BEAD_LIST_LIMIT:-999999}"
ID_CLIP=8   # chars of each id kept in the structured classification line
            # (ids share the workspace prefix, so keep the unique tail)
TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

DRY_RUN=false
for arg in "$@"; do
    case "$arg" in
        --dry-run)
            DRY_RUN=true
            ;;
        -h|--help)
            cat <<EOF
Usage: $(basename "$0") [--dry-run]

  --dry-run   Report starvation findings and the assigned-but-open beads that
              would be cleared, without mutating anything (no bead updates, no
              recovery workflow, no checkpoint flush). The frontier
              classification, the read-only passes of the starvation-alert
              enrichment and the credential-gated unblock, and the low-volume
              diagnostic suite run either way.

An assignee is only ever cleared after its worker is proven heartbeat-dead
(no .beads/heartbeats.jsonl entry within HEARTBEAT_STALE_SECONDS); a live
assignee is never cleared, whatever the frontier looks like.

Exit codes:
  0  no starvation — frontier healthy, or thin with every open bead explained
  1  genuine starvation — thin frontier with unexplained open bead(s)
  2  usage error
  3  health could not be determined (unreadable queue, failed classification)
EOF
            exit 0
            ;;
        *)
            echo "Unknown argument: $arg (supported: --dry-run)" >&2
            exit 2
            ;;
    esac
done

# Ensure we're in the workspace directory
cd "$WORKSPACE_DIR"

# Logging function
log() {
    local level="$1"
    shift
    local message="$*"
    echo "[$TIMESTAMP] [$level] $message" | tee -a "$LOG_FILE"
}

# An unreadable queue or an unclassifiable frontier is an *unknown* state, and
# a healthcheck must never report "unknown" as "healthy": exit nonzero so the
# timer's failure stays visible instead of silently clearing the alert.
# (tee-to-stderr so the message survives being called inside a $( ) capture.)
die() {
    echo "[$TIMESTAMP] [ERROR] $*" | tee -a "$LOG_FILE" >&2
    exit 3
}

# Resolve the bead CLI once. The systemd user manager runs this unit with a
# minimal PATH that does not include ~/.local/bin or ~/.cargo/bin, where the
# bead wrapper and binaries live — under the timer a bare `bead` fails with
# "command not found" and every run dies before any check executes. A shell
# function shadows the binary for every call site below without touching them.
if command -v bead >/dev/null 2>&1; then
    BEAD_BIN="$(command -v bead)"
elif [ -x "$HOME/.local/bin/bead" ]; then
    BEAD_BIN="$HOME/.local/bin/bead"
elif [ -x "$HOME/.cargo/bin/bead" ]; then
    BEAD_BIN="$HOME/.cargo/bin/bead"
else
    die "no usable bead CLI found (looked on PATH, ~/.local/bin/bead, ~/.cargo/bin/bead)"
fi
bead() { "$BEAD_BIN" "$@"; }

# The diagnostic suite is stdlib-only, so the venv interpreter is preferred but
# not required — after a NixOS rebuild wipes .venv the triage step still runs.
if [ -x "$WORKSPACE_DIR/.venv/bin/python" ]; then
    ADC_PYTHON="$WORKSPACE_DIR/.venv/bin/python"
else
    ADC_PYTHON="$(command -v python3 || true)"
fi
[ -n "$ADC_PYTHON" ] || die "no python interpreter found (.venv/bin/python and python3 both unavailable)"

# The dry-run flag array shared by the enrichment steps (3b, 5, 6). It must be
# built with a real conditional, not ${DRY_RUN:+...}: that expansion tests
# non-emptiness, and DRY_RUN holds the STRING "false" on a normal run, so it
# collapsed to a permanently-on --dry-run and the timer enriched nothing for
# days while logging "would enrich".
ENRICH_DRY_RUN=()
if [ "$DRY_RUN" = true ]; then
    ENRICH_DRY_RUN=(--dry-run)
fi

# Run bead list and emit exactly one flat JSON array of bead objects.
# `bead list --json` emits compact JSONL (one object per line) but prints a bare
# "[]" for an empty result, so slurp-and-flatten normalizes both shapes before
# counting — otherwise an empty queue counts as 1.
#
# An unreadable queue returns nonzero instead of "[]". Falling back to an empty
# array on failure (transient sqlite contention, lock timeout) turns a real
# frontier into a zero count, and a zero count reads as "nothing to explain" —
# the healthcheck would report a broken workspace as healthy. Callers die on a
# nonzero return; they must never convert it into a number.
bead_list() {
    local out
    if ! out="$(bead list "$@" --json --limit "$BEAD_LIST_LIMIT" 2>>"$LOG_FILE" \
            | jq -s 'map(if type == "array" then .[] else . end)')"; then
        log ERROR "bead list ${*:-<all>} failed - the queue is unreadable, not empty"
        return 1
    fi
    printf '%s\n' "$out"
}

count_beads() {
    local src out
    src="$(bead_list "$@")" || die "cannot count the frontier - bead list is unavailable"
    out="$(jq '. | length' <<<"$src")" || die "cannot count the frontier - jq failed on bead list output"
    printf '%s\n' "$out"
}

# Classify every open bead into exactly one bucket (first match wins):
#   human_blocked       manual_blocked, or the human label — a person set it aside
#   dependency_blocked  at least one blocker that is not closed
#   deferred            deferred base or effective status
#   assigned_stuck      assignee set while base status is still open — unclaimable
#                       (claim order skips assignees) yet not actively worked
#                       (work in flight is in_progress)
#   ready               present in the ready frontier — visible, nothing to explain
#   unexplained         not ready and none of the above — the starvation signal
#
# A frontier below READY_THRESHOLD is only starvation when unexplained beads
# exist: a frontier whose open beads are all visible or all explained is merely
# small, not starving. Blocker statuses come from a full workspace fetch; a
# blocker missing from it counts as unclosed.
CLASSIFY_JQ='
def clip: ($clip | tonumber) as $max
  | map(if length > $max then .[(length - $max):] else . end);
($open[0] // []) as $open
| ($ready[0] // []) as $ready
| ($all[0] // []) as $all
| ($all | map({(.id): .status}) | add // {}) as $status_of
| [ $open[]
    | .id as $id
    | if .manual_blocked == true or ((.labels // []) | index("human") != null) then
        "human_blocked"
      elif ([.dependencies[]?.blocker | $status_of[.] // "unknown"] | any(. != "closed")) then
        "dependency_blocked"
      elif .status == "deferred" or .effective_status == "deferred" then
        "deferred"
      elif .assignee != null then
        "assigned_stuck"
      elif ([ $ready[] | .id ] | index($id)) != null then
        "ready"
      else
        "unexplained"
      end
    | {bucket: ., id: $id} ]
| group_by(.bucket)
| map({(.[0].bucket): [.[].id]})
| add // {}
| . as $buckets
| {
    total_open: ($open | length),
    ready: ($ready | length),
    human_blocked: (($buckets.human_blocked // []) | length),
    dependency_blocked: (($buckets.dependency_blocked // []) | length),
    deferred: (($buckets.deferred // []) | length),
    assigned_stuck: (($buckets.assigned_stuck // []) | length),
    ready_visible: (($buckets.ready // []) | length),
    unexplained: (($buckets.unexplained // []) | length),
    human_blocked_ids: (($buckets.human_blocked // []) | clip),
    dependency_blocked_ids: (($buckets.dependency_blocked // []) | clip),
    assigned_stuck_ids: (($buckets.assigned_stuck // []) | clip),
    unexplained_ids: (($buckets.unexplained // []) | clip)
  }
'

# Frontier classification — read-only, so it also runs under --dry-run.
# Sets the CLASSIFICATION global (one compact JSON line) and returns nonzero
# when the frontier cannot be classified; the caller dies on that rather than
# reading an unknown state as healthy. CLASSIFICATION is only assigned on
# success — a failed assignment must not clobber it with an empty string.
classify_frontier() {
    local tmp_open tmp_ready tmp_all out
    tmp_open="$(mktemp)"
    tmp_ready="$(mktemp)"
    tmp_all="$(mktemp)"
    bead_list --status open > "$tmp_open" || { rm -f "$tmp_open" "$tmp_ready" "$tmp_all"; return 1; }
    bead_list --ready > "$tmp_ready" || { rm -f "$tmp_open" "$tmp_ready" "$tmp_all"; return 1; }
    bead_list > "$tmp_all" || { rm -f "$tmp_open" "$tmp_ready" "$tmp_all"; return 1; }
    if ! out="$(jq -nc \
        --arg clip "$ID_CLIP" \
        --slurpfile open "$tmp_open" \
        --slurpfile ready "$tmp_ready" \
        --slurpfile all "$tmp_all" \
        "$CLASSIFY_JQ")"; then
        rm -f "$tmp_open" "$tmp_ready" "$tmp_all"
        return 1
    fi
    rm -f "$tmp_open" "$tmp_ready" "$tmp_all"
    CLASSIFICATION="$out"
}

log INFO "=== Starting bead health check ==="

# Get current bead counts
log INFO "Collecting bead statistics..."
READY_COUNT=$(count_beads --ready)
TOTAL_OPEN=$(count_beads --status open)

log INFO "Ready beads: $READY_COUNT"
log INFO "Total open beads: $TOTAL_OPEN"

if [ "$DRY_RUN" = true ]; then
    log INFO "[dry-run] No mutations will be performed"
fi

# Step 1: heavyweight recovery — only for a large frontier that is starving
# (both thresholds). Every smaller frontier still gets Steps 2-4 below. The
# invocations are guarded with `if !` so a failing repair can never abort the
# rest of the run under set -e.
if [ "$TOTAL_OPEN" -ge "$TOTAL_OPEN_THRESHOLD" ] && [ "$READY_COUNT" -lt "$READY_THRESHOLD" ]; then
    log WARN "Threshold triggered: $READY_COUNT ready beads (< $READY_THRESHOLD) with $TOTAL_OPEN total open beads (>=$TOTAL_OPEN_THRESHOLD)"
    log ERROR "STARVATION DETECTED - Invoking comprehensive automated recovery workflow..."

    # Run the comprehensive recovery workflow which handles:
    # 1. Stale checkpoint detection and flush
    # 2. Bead visibility verification
    # 3. Corruption detection via bead doctor --rehearse
    # 4. Full database recovery from forensic checkpoint if needed
    # 5. Post-recovery verification
    # 6. Structured logging
    if [ "$DRY_RUN" = true ]; then
        log INFO "[dry-run] Would run the comprehensive recovery workflow - skipped"
    elif [ -x "$WORKSPACE_DIR/scripts/bead_recovery_workflow.sh" ]; then
        log INFO "Executing comprehensive recovery workflow..."
        if ! "$WORKSPACE_DIR/scripts/bead_recovery_workflow.sh" 2>&1 | tee -a "$LOG_FILE"; then
            log ERROR "Comprehensive recovery workflow failed - continuing with classification"
        fi
    else
        log ERROR "Recovery workflow script not found or not executable: $WORKSPACE_DIR/scripts/bead_recovery_workflow.sh"
        log ERROR "Falling back to basic repairs..."
        # Fallback to basic repairs if comprehensive workflow is unavailable
        log INFO "Step 1: Running bead doctor --repair to fix stale indexes and views"
        if ! bead doctor --repair >> "$LOG_FILE" 2>&1; then
            log ERROR "bead doctor --repair failed - continuing with classification"
        fi
    fi

    # Re-check counts after repair
    log INFO "Re-checking bead counts after repairs..."
    NEW_READY_COUNT=$(count_beads --ready)
    NEW_TOTAL_OPEN=$(count_beads --status open)

    log INFO "Post-repair ready beads: $NEW_READY_COUNT"
    log INFO "Post-repair total open beads: $NEW_TOTAL_OPEN"

    # Calculate improvement
    IMPROVEMENT=$((NEW_READY_COUNT - READY_COUNT))
    if [ "$IMPROVEMENT" -gt 0 ]; then
        log INFO "Health check improved ready count by $IMPROVEMENT beads"
    elif [ "$IMPROVEMENT" -lt 0 ]; then
        log WARN "Ready count decreased by $((-IMPROVEMENT)) beads during repair"
    else
        log INFO "Ready count unchanged after repairs"
    fi
fi

# Step 1b: low-volume starvation trigger — the shape this workspace actually
# hits. TOTAL_OPEN_THRESHOLD is 50 while this queue holds single-digit open
# counts, so Step 1's heavyweight branch never fires here; yet a ready
# frontier of zero with open work still present is starvation at any volume.
# The response is evidence, not heavy machinery: run the five-check read-only
# diagnostic suite (bead store, checkpoint freshness, pluck query, corruption
# rehearsal, config consistency — docs/notes/pluck-starvation-diagnostic-suite.md)
# and log the report path, so the tick that observes the shape also produces
# the report a human triages it with. The suite is read-only, so it runs under
# --dry-run too. --output is passed explicitly because --quiet suppresses the
# summary line that would otherwise print the path; the status is read back
# from the report file (verify by property, not by trusting the exit code
# alone). Disjoint from Step 1 by design: at >= TOTAL_OPEN_THRESHOLD open
# beads the heavyweight branch owns the response.
if [ "$READY_COUNT" -eq 0 ] && [ "$TOTAL_OPEN" -gt 0 ] && [ "$TOTAL_OPEN" -lt "$TOTAL_OPEN_THRESHOLD" ]; then
    log WARN "Low-volume starvation trigger: ready frontier is empty while $TOTAL_OPEN open bead(s) exist (< $TOTAL_OPEN_THRESHOLD)"
    DIAG_REPORT="/tmp/pluck-starvation-diagnostic-$(date -u +%Y%m%d_%H%M%S).json"
    if ! "$ADC_PYTHON" "$WORKSPACE_DIR/scripts/diagnose_pluck_starvation.py" \
            --workspace "$WORKSPACE_DIR" --quiet \
            --bead-bin "$BEAD_BIN" --output "$DIAG_REPORT" >> "$LOG_FILE" 2>&1; then
        log ERROR "Diagnostic suite failed - expected no report at $DIAG_REPORT"
    elif [ -s "$DIAG_REPORT" ] && jq -e '.metadata.overall_status' "$DIAG_REPORT" >/dev/null 2>&1; then
        DIAG_STATUS="$(jq -r '.metadata.overall_status' "$DIAG_REPORT")"
        log WARN "Diagnostic report: $DIAG_REPORT (overall_status=$DIAG_STATUS)"
    else
        log ERROR "Diagnostic suite reported success but left no readable report at $DIAG_REPORT"
    fi
fi

# Heartbeat liveness for the Step 2 sweep. Heartbeats live at
# .beads/heartbeats.jsonl as JSONL with "worker" and "ts" (RFC3339). Worker
# names are short ("glm53-adc") while assignees are the full dispatch
# identity ("claude-code-glm-5.3-glm53-adc"), so a worker maps to an assignee
# by equality or dash-suffix — never bare containment, or worker "glm-adc"
# would falsely match assignee "...-glm53-adc" and a live worker's claims
# would be cleared.
HEARTBEATS_FILE="$WORKSPACE_DIR/.beads/heartbeats.jsonl"

# Print the newest heartbeat ts for the worker an assignee maps to, nothing
# when no entry names it. Returns 1 only when the heartbeats file exists but
# cannot be parsed — the caller must treat liveness as unknown and refuse to
# clear. A missing file is a legitimate "no worker has a heartbeat" state,
# indistinguishable in effect from an empty one, and returns 0 with no output.
assignee_latest_heartbeat() {
    local assignee="$1" latest
    [ -f "$HEARTBEATS_FILE" ] || return 0
    if ! latest="$(jq -rs --arg a "$assignee" \
        'map(.worker as $w | select($a == $w or ($a | endswith("-" + $w))))
         | map(.ts) | max' "$HEARTBEATS_FILE" 2>/dev/null)"; then
        return 1
    fi
    [ -n "$latest" ] && [ "$latest" != "null" ] && printf '%s\n' "$latest"
    return 0
}

# Liveness verdict for an assignee: 0 = live (heartbeated within
# HEARTBEAT_STALE_SECONDS), 1 = dead (no entry, or newest is stale),
# 2 = unknown (heartbeats unreadable / ts unparsable). Only a 1 ever permits
# clearing — an unknown must read as "possibly live" so a broken heartbeats
# file can never cause a live worker's claims to be cleared.
assignee_is_live() {
    local latest ts_epoch
    latest="$(assignee_latest_heartbeat "$1")" || return 2
    [ -n "$latest" ] || return 1
    ts_epoch="$(date -u -d "$latest" +%s 2>/dev/null)" || return 2
    [ "$ts_epoch" -ge $(( $(date -u +%s) - HEARTBEAT_STALE_SECONDS )) ]
}

# Step 2: assigned-but-open sweep — every pass.
# A bead with base status open plus an assignee is invisible to the ready
# frontier (which only surfaces open + unassigned) and so can never be claimed,
# while `bead release` deliberately refuses it because release only acts on
# in_progress work. The sanctioned remedy is `bead update <id> --clear-assignee`.
#
# Permission to clear is heartbeat liveness, not frontier size: an assignee
# whose worker still heartbeats may hold a live claim and is NEVER cleared,
# however starved the frontier looks; one whose worker has no heartbeat newer
# than HEARTBEAT_STALE_SECONDS is gone, and its assigned-but-open beads are
# the known silent-starvation shape. (Work a worker is actually operating on
# is in_progress, never assigned+open — but a live heartbeat outranks even
# that inference and protects the assignment regardless.)
log INFO "Step 2: Checking for assigned-but-open beads"
ASSIGNED_OPEN_BEADS="$(bead_list --status open \
    | jq '[.[] | select(.assignee != null and .status == "open")]')" \
    || die "cannot sweep assigned-but-open beads - bead list is unavailable"
ASSIGNED_OPEN=$(echo "$ASSIGNED_OPEN_BEADS" | jq 'length')
READY_BEFORE=$(count_beads --ready)

if [ "$ASSIGNED_OPEN" -eq 0 ]; then
    log INFO "No assigned-but-open beads found"
else
    log INFO "Found $ASSIGNED_OPEN assigned-but-open beads (invisible to the ready frontier); checking assignee heartbeats"
    echo "$ASSIGNED_OPEN_BEADS" | jq -r '.[] | "  \(.id) [assignee=\(.assignee)] \(.title)"' >> "$LOG_FILE"

    CLEARED=0
    DEAD=0
    UNKNOWN=0
    while read -r bead_id assignee; do
        [ -z "$bead_id" ] && continue
        # Capture, don't test: a bare `assignee_is_live ...` returning 1 (dead)
        # or 2 (unknown) would trip errexit before the case ever runs — the
        # nonzero codes ARE the answer, not a failure. `|| liveness=$?` keeps
        # the call in a conditional context where set -e stays quiet.
        liveness=0
        assignee_is_live "$assignee" || liveness=$?
        case $liveness in
            0)
                log INFO "Assignee heartbeat live (<= ${HEARTBEAT_STALE_SECONDS}s old) - never clearing: $bead_id [$assignee]"
                ;;
            2)
                UNKNOWN=$((UNKNOWN + 1))
                log ERROR "Cannot determine heartbeat liveness for assignee $assignee - leaving $bead_id untouched"
                ;;
            1)
                DEAD=$((DEAD + 1))
                if [ "$DRY_RUN" = true ]; then
                    log INFO "[dry-run] Would clear heartbeat-dead assignee [$assignee]: $bead_id"
                elif bead update "$bead_id" --clear-assignee >> "$LOG_FILE" 2>&1; then
                    log INFO "Cleared heartbeat-dead assignee [$assignee]: $bead_id"
                    CLEARED=$((CLEARED + 1))
                else
                    log ERROR "Failed to clear assignee: $bead_id"
                fi
                ;;
        esac
    done < <(echo "$ASSIGNED_OPEN_BEADS" | jq -r '.[] | "\(.id) \(.assignee)"')

    if [ "$DEAD" -eq 0 ] && [ "$UNKNOWN" -eq 0 ]; then
        log INFO "All $ASSIGNED_OPEN assigned-but-open bead(s) have live assignees - nothing cleared"
    elif [ "$DEAD" -eq 0 ]; then
        log INFO "No heartbeat-dead assignees ($UNKNOWN with unknown liveness left untouched) - nothing cleared"
    elif [ "$DRY_RUN" = true ]; then
        # "up to": a swept bead with an unclosed blocker re-enters open+unassigned
        # but still not the frontier, so the projected count is a ceiling, not an
        # equality — the real path re-queries instead of projecting.
        log INFO "[dry-run] Clearing $DEAD heartbeat-dead assignee(s) would move the ready frontier $READY_BEFORE -> up to $((READY_BEFORE + DEAD)) (beads with open blockers stay hidden)"
    else
        # The repair sequence the shape calls for: publish the clears to the
        # checkpoint, then re-measure the frontier the beads were hidden from.
        # Step 3's unconditional flush below makes this one idempotent.
        if ! bead sync flush-only >> "$LOG_FILE" 2>&1; then
            log ERROR "bead sync flush-only after assignee repair failed - checkpoint may lag the database"
        fi
        READY_AFTER=$(count_beads --ready)
        log INFO "Heartbeat sweep cleared $CLEARED of $DEAD heartbeat-dead assignee(s) ($((ASSIGNED_OPEN - DEAD - UNKNOWN)) live, $UNKNOWN unknown liveness left in place); ready frontier $READY_BEFORE -> $READY_AFTER"
    fi
fi

# Step 3: Verify database vs checkpoint consistency — every pass. A mutation
# can commit while publication is suppressed, so flush unconditionally.
if [ "$DRY_RUN" = true ]; then
    log INFO "[dry-run] Would run bead sync flush-only - skipped"
else
    log INFO "Step 3: Running bead sync flush-only to verify consistency"
    if ! bead sync flush-only >> "$LOG_FILE" 2>&1; then
        log ERROR "bead sync flush-only failed - continuing with classification"
    fi
fi

# Step 3b: enrich underspecified beads — every pass, before the classification
# so the same run's verdict reflects any deferral. An open, dependency-free
# bead whose notes carry an awaiting-user-input marker ("kubectl delete pod"
# with no pod name or namespace — aidedeca-a1ba8617 sat that way for two
# weeks) is exactly the frontier-invisible shape pluck reports: claimable in
# principle, unactionable in practice, and until now only a human could decide
# its fate. scripts/enrich_underspecified_beads.py gives that decision a
# deterministic first pass: it resolves the missing parameter from live
# evidence (the bead's own notes thread, read-only
# `kubectl --server=<proxy> get pods -A` filtered by the bead's stated
# context, the git log) and appends the specifics to the bead's notes when
# exactly one candidate matches, making it genuinely claimable; zero or
# several candidates defer the bead out of the frontier with the count stated
# ("underspecified: N candidates, needs disambiguation"), so it leaves the
# frontier honestly instead of starving it. Beads a human set aside
# (manual_blocked, the human label) and beads with an assignee are untouched.
# Cluster verbs are read-only by construction — any mutation belongs to
# declarative-config. With no qualifying bead present it is one read-only
# bead list. Under --dry-run it stays read-only too (no bead updates).
log INFO "Step 3b: Resolving or deferring underspecified beads awaiting user input"
if ! "$ADC_PYTHON" "$WORKSPACE_DIR/scripts/enrich_underspecified_beads.py" \
        --workspace "$WORKSPACE_DIR" --bead-bin "$BEAD_BIN" \
        "${ENRICH_DRY_RUN[@]}" --json >> "$LOG_FILE" 2>&1; then
    log ERROR "Underspecified bead enrichment failed - an unactionable bead may keep starving the frontier"
fi

# Step 4: frontier classification — every pass, at any workspace size.
log INFO "Step 4: Classifying the ready frontier"
CLASSIFICATION='{}'
if ! classify_frontier; then
    die "frontier classification failed - cannot distinguish starvation from a small clean frontier"
fi
log INFO "FRONTIER_CLASSIFICATION $CLASSIFICATION"

# Step 5: attach the automated diagnostics to starvation alert beads — every
# pass, before the final verdict, so an alert is enriched within one timer
# period of being filed instead of reaching a human with no evidence attached.
# The enricher finds beads titled "Starvation alert: ..." that do not carry a
# report yet, runs diagnose_pluck_starvation.py plus bead_recovery_workflow.sh,
# and writes the report path, overall status, recommendations and a
# classification label into the bead. With no unenriched alert present it does
# nothing beyond three read-only bead lists. Under --dry-run it stays
# read-only too (no bead updates, no recovery workflow).
#
# The dry-run flag for Step 5 arrives via ENRICH_DRY_RUN, defined above Step 1.
log INFO "Step 5: Enriching unenriched starvation alert beads with the diagnostic suite"
if ! "$ADC_PYTHON" "$WORKSPACE_DIR/scripts/enrich_starvation_alerts.py" \
        --workspace "$WORKSPACE_DIR" --bead-bin "$BEAD_BIN" \
        --log-file /tmp/bead-recovery.log \
        "${ENRICH_DRY_RUN[@]}" --json >> "$LOG_FILE" 2>&1; then
    log ERROR "Starvation alert enrichment failed - an alert may reach a human without a diagnostics report"
fi

# Step 6: unblock credential-gated beads — every pass. A bead whose notes
# record an "OpenBao permission denied" / cannot-read-secret failure starves
# the frontier because the fix looks like it needs a human grant. It does
# not: scripts/unblock_credential_gated_beads.py confirms the path exists
# via the WRITE-ONLY provisioning identity (metadata only — a value is never
# read, here or anywhere), records the runtime delivery the consuming
# process performs at start (the unit's ExecStartPre fetch), verifies by
# property only (file mode 600 + status endpoint), and appends the result to
# the bead so its dependents become claimable without a human in the path.
# With no candidate present it is three read-only bead lists.
log INFO "Step 6: Checking for beads blocked on credential-read failures"
if ! "$ADC_PYTHON" "$WORKSPACE_DIR/scripts/unblock_credential_gated_beads.py" \
        --workspace "$WORKSPACE_DIR" --bead-bin "$BEAD_BIN" \
        "${ENRICH_DRY_RUN[@]}" --json >> "$LOG_FILE" 2>&1; then
    log ERROR "Credential-gated bead unblock failed - a credential-blocked bead may stay invisible to its dependents"
fi

READY_FINAL=$(jq -r '.ready // 0' <<<"$CLASSIFICATION")
UNEXPLAINED=$(jq -r '.unexplained // 0' <<<"$CLASSIFICATION")
# Final status determination: starvation needs both a thin frontier and open
# beads that are neither in it nor explained by any known cause. A thin
# frontier whose beads are all visible or all explained is not starvation.
if [ "$READY_FINAL" -lt "$READY_THRESHOLD" ] && [ "$UNEXPLAINED" -gt 0 ]; then
    log ERROR "GENUINE STARVATION: $UNEXPLAINED unexplained open bead(s) not reachable through a ready frontier of $READY_FINAL (< $READY_THRESHOLD)"
    if [ "$DRY_RUN" = true ]; then
        log INFO "=== Dry run complete - no mutations were made ==="
    else
        log ERROR "=== Health check complete - STARVATION CONFIRMED ==="
    fi
    exit 1
fi

log INFO "No starvation: $READY_FINAL ready bead(s) with $UNEXPLAINED unexplained (threshold $READY_THRESHOLD)"
if [ "$DRY_RUN" = true ]; then
    log INFO "=== Dry run complete - no mutations were made ==="
else
    log INFO "=== Health check complete - HEALTHY ==="
fi
exit 0
