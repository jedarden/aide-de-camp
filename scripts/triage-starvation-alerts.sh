#!/run/current-system/sw/bin/bash
# Automated triage of starvation-alert beads: attach evidence, then close or escalate.
#
# Port of tradegraph's scripts/triage-starvation-alerts.mjs (the unit scheduled
# by bead-starvation-alert-triage.timer there) to this workspace. NEEDLE files a
# "Starvation alert: beads invisible in <workspace>" bead when the pluck
# waterfall finds no candidates, and those alerts carry the `human` label so no
# autonomous worker claims them - without this triage they sit until a person
# reads them, which for aidedeca-3e43d981 (evidence-free, closed by hand) meant
# days of queue noise.
#
# For every OPEN bead labeled `starvation-alert` this script
#
#   1. runs scripts/diagnose_pluck_starvation.py against the live store and
#      attaches a summary note (report path, overall status, decision basis)
#      via `bead update --notes`,
#   2. closes the alert - stripping the `human` label first - when the close is
#      proven by BOTH sides of the evidence:
#        - the alert itself is evidence-free (its payload reported 0 open and
#          0 excluded beads - the alert contradicted its own title), OR the
#          fresh diagnostics report is HEALTHY, AND
#        - a live frontier re-check finds no unexplained open bead: every open
#          non-alert bead is either human-labeled, manually blocked, assigned,
#          waiting on an unclosed blocker, or already in the ready frontier.
#      The live re-check is not optional: a HEALTHY report alone cannot prove
#      safety, because the report does not flag ready-filter bugs (the exact
#      2026-08-29 incident shape - beads ready-eligible but invisible to
#      `bead list --ready` - produces an info finding, not a high one).
#   3. keeps the alert open with the `human` label for HIGH_RISK/CRITICAL
#      reports (adding the label when missing so no worker claims it), and
#      never touches a bead a worker holds (in_progress claims win).
#
# Coordination with scripts/enrich_starvation_alerts.py (run every 15 min by
# bead-healthcheck.timer): the enricher finds alert beads by title and skips
# enriched ones; this script finds them by the `starvation-alert` label and
# skips ones it already kept for human review. Whichever runs first attaches
# its evidence; a bead this triage keeps open is still eligible for the
# enricher's recovery pass, which can close it later from stronger evidence.
#
# Exit codes: 0 triage pass complete (kept-for-human is a decision, not a
# failure); 1 at least one alert failed to process (retried next pass);
# 2 usage; 3 live state could not be read.

set -euo pipefail

# The systemd user manager runs with a minimal PATH that excludes ~/.local/bin
# and ~/.cargo/bin (and on some launches the NixOS system dir); every external
# this script calls - bead, jq, timeout, date - must resolve without it.
export PATH="$HOME/.local/bin:$HOME/.cargo/bin:/run/current-system/sw/bin:/usr/bin:/bin:$PATH"

WORKSPACE_DIR="${WORKSPACE_DIR:-/home/coding/aide-de-camp}"
LOG_FILE="${LOG_FILE:-/tmp/bead-starvation-triage.log}"
REPORT_DIR="${REPORT_DIR:-/tmp}"
# bead list silently caps output at --limit (default 100); the frontier
# re-check resolves blocker statuses against the full fetch
BEAD_LIST_LIMIT="${BEAD_LIST_LIMIT:-999999}"

STARVATION_ALERT_LABEL="starvation-alert"
HUMAN_LABEL="human"
# Present in a bead's notes once this script has recorded a triage decision.
TRIAGE_MARKER="Starvation triage (automated):"
KEPT_DECISION="- Decision: kept-for-human"
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

  --dry-run   Print the triage decision each alert would get, from a fresh
              diagnostics report and live frontier re-check, without mutating
              anything (no bead update/label/close).

Exit codes:
  0  triage pass complete
  1  at least one alert failed to process
  2  usage error
  3  live bead state could not be read
EOF
            exit 0
            ;;
        *)
            echo "Unknown argument: $arg (supported: --dry-run)" >&2
            exit 2
            ;;
    esac
done

cd "$WORKSPACE_DIR"

log() {
    local level="$1"
    shift
    local message="$*"
    echo "[$TIMESTAMP] [$level] $message" | tee -a "$LOG_FILE"
}

# An unreadable store is an unknown state, and unknown must never be reported
# as triaged: exit 3 so the timer's failure stays visible.
die() {
    echo "[$TIMESTAMP] [ERROR] $*" | tee -a "$LOG_FILE" >&2
    exit 3
}

# Resolve the bead CLI. The systemd user manager runs units with a minimal
# PATH that does not include ~/.local/bin or ~/.cargo/bin, where this box's
# bead wrapper and binaries actually live (same resolution as
# bead-healthcheck.sh and diagnose_pluck_starvation.py).
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
# not required - after a NixOS rebuild wipes .venv the triage still runs.
if [ -x "$WORKSPACE_DIR/.venv/bin/python" ]; then
    ADC_PYTHON="$WORKSPACE_DIR/.venv/bin/python"
else
    ADC_PYTHON="$(command -v python3 || true)"
fi
[ -n "$ADC_PYTHON" ] || die "no python interpreter found (.venv/bin/python and python3 both unavailable)"

# Run a bead list and emit exactly one flat JSON array of bead objects.
# `bead list --json` emits compact JSONL, prints a bare "[]" for an empty
# result, and has been seen emitting nested arrays; slurp-and-flatten
# normalizes every shape. A nonzero return must never become an empty array -
# that would read a broken store as "nothing to triage".
bead_list() {
    local out
    if ! out="$(bead list "$@" --json --limit "$BEAD_LIST_LIMIT" 2>>"$LOG_FILE" \
            | jq -s 'map(if type == "array" then .[] else . end)')"; then
        log ERROR "bead list ${*:-<all>} failed - the store is unreadable, not empty"
        return 1
    fi
    printf '%s\n' "$out"
}

# Read one bead as raw JSON via `bead show --json` (the CLI wraps the single
# bead in an array; a bare dict is accepted too).
read_bead() {
    local id="$1" out
    if ! out="$(bead show --json "$id" 2>>"$LOG_FILE")"; then
        return 1
    fi
    printf '%s' "$out" | jq -c --arg id "$id" '
        map(if type == "array" then .[] else . end)
        | map(select(.id == $id)) | .[0]
    '
}

# Count the open beads the live frontier cannot account for: not an alert, not
# human-labeled, not manually blocked, not assigned, not waiting on an
# unclosed blocker - yet absent from `bead list --ready`. This is the replay
# guard tradegraph's triage applies before closing anything: a close needs the
# live state to agree with the report, not just the report to be quiet.
#
# Inputs (as slurpfile arguments): $open, $ready, $all.
UNEXPLAINED_JQ='
($ready[0] // [] | map(.id)) as $ready_ids
| ($all[0] // []
    | map(select(.id != null) | {(.id): (.status // .effective_status // "unknown")})
    | add // {}) as $status_of
| [ ($open[0] // [])[]
    | .id as $bid
    | select(((.labels // []) | index("starvation-alert")) == null)
    | select(((.labels // []) | index("human")) == null)
    | select((.manual_blocked // false) != true)
    | select(.assignee == null)
    | select(([(.dependencies // [])[]
                | select(.kind == "blocks")
                | .blocker
                | if . == null then empty else ($status_of[.] // "unknown") end]
              | any(. != "closed")) == false)
    | select(($ready_ids | index($bid)) == null)
    | $bid ]
'

# Extract "**Field:** N" from an alert payload; prints nothing when the field
# is absent or malformed, which callers treat as "could not parse".
parse_payload_count() {
    printf '%s\n' "$1" | sed -n "s/^\*\*$2:\*\* \([0-9][0-9]*\)$/\1/p" | head -n1
}

# A report path that does not collide with one written in the same second
# (same pattern as enrich_starvation_alerts.py's unique_report_path).
unique_report_path() {
    local candidate="$REPORT_DIR/triage-starvation-diagnostic-$1.json" n=2
    while [ -e "$candidate" ]; do
        candidate="$REPORT_DIR/triage-starvation-diagnostic-$1-$n.json"
        n=$((n + 1))
    done
    printf '%s' "$candidate"
}

log INFO "=== Starting starvation-alert triage ==="
if [ "$DRY_RUN" = true ]; then
    log INFO "[dry-run] No mutations will be performed"
fi

# Discovery and the live frontier re-check share these fetches.
TMP_OPEN="$(mktemp)"
TMP_READY="$(mktemp)"
TMP_ALL="$(mktemp)"
trap 'rm -f "$TMP_OPEN" "$TMP_READY" "$TMP_ALL"' EXIT

bead_list --status open > "$TMP_OPEN" || die "cannot list open beads - store is unreadable"
bead_list --ready > "$TMP_READY" || die "cannot list the ready frontier - store is unreadable"
bead_list > "$TMP_ALL" || die "cannot list all beads - store is unreadable"

if ! UNEXPLAINED_IDS="$(jq -nc \
        --slurpfile open "$TMP_OPEN" \
        --slurpfile ready "$TMP_READY" \
        --slurpfile all "$TMP_ALL" \
        "$UNEXPLAINED_JQ")"; then
    die "frontier re-check failed - cannot prove any close today"
fi
UNEXPLAINED_COUNT=$(jq 'length' <<<"$UNEXPLAINED_IDS")
log INFO "Live frontier re-check: $UNEXPLAINED_COUNT unexplained open bead(s)"

ALERT_IDS="$(jq -r '.[]
    | select(((.labels // []) | index("starvation-alert")) != null)
    | .id' "$TMP_OPEN")" \
    || die "cannot filter starvation-alert beads from the open list"

TRIAGED=0
CLOSED=0
KEPT=0
SKIPPED=0
FAILED=0

for bead_id in $ALERT_IDS; do
    bead_json="$(jq -c --arg id "$bead_id" 'map(select(.id == $id)) | .[0]' "$TMP_OPEN")"
    notes="$(jq -r '.notes // ""' <<<"$bead_json")"

    # Already triaged: a kept-for-human decision is final for this script (the
    # enricher's recovery pass remains its safety net). A close decision that
    # failed mid-flight leaves the bead open, so it is retried here.
    if grep -qF "$TRIAGE_MARKER" <<<"$notes" && grep -qF "$KEPT_DECISION" <<<"$notes"; then
        log INFO "SKIP $bead_id: already triaged (kept for human review)"
        SKIPPED=$((SKIPPED + 1))
        continue
    fi

    labels="$(jq -r '.labels // [] | join(",")' <<<"$bead_json")"
    description="$(jq -r '.description // ""' <<<"$bead_json")"
    title="$(jq -r '.title // ""' <<<"$bead_json")"
    log INFO "Triaging $bead_id: ${title}"

    # 1. Fresh diagnostics against the live store.
    STAMP=$(date -u +"%Y%m%d_%H%M%S")
    REPORT_PATH="$(unique_report_path "$STAMP")"
    if ! timeout 180 "$ADC_PYTHON" "$WORKSPACE_DIR/scripts/diagnose_pluck_starvation.py" \
            --workspace "$WORKSPACE_DIR" --quiet --output "$REPORT_PATH" \
            --bead-bin "$BEAD_BIN" >> "$LOG_FILE" 2>&1; then
        log ERROR "diagnostics failed for $bead_id - leaving the alert untouched for retry"
        FAILED=$((FAILED + 1))
        continue
    fi
    if ! OVERALL="$(jq -r '.metadata.overall_status // "UNKNOWN"' "$REPORT_PATH" 2>>"$LOG_FILE")"; then
        log ERROR "diagnostics report $REPORT_PATH is unreadable for $bead_id"
        FAILED=$((FAILED + 1))
        continue
    fi

    # 2. The alert's own counts. The 2026-08-29 alert shape is
    #    "**Open beads:** 0 / **Excluded beads:** 0" under a title claiming
    #    beads were invisible - evidence-free by contradiction.
    PAYLOAD_OPEN="$(parse_payload_count "$description" "Open beads")"
    PAYLOAD_EXCLUDED="$(parse_payload_count "$description" "Excluded beads")"
    EVIDENCE_FREE=false
    if [ "${PAYLOAD_OPEN:-x}" = "0" ] && [ "${PAYLOAD_EXCLUDED:-x}" = "0" ]; then
        EVIDENCE_FREE=true
    fi

    # 3. Decision. A close needs the proving side (evidence-free payload or
    #    HEALTHY report) AND a live frontier with nothing unexplained. A
    #    HIGH/CRITICAL report loses only to an evidence-free payload plus a
    #    clean live re-check: the report's CRITICAL can come from the stale
    #    pluck-diagnostics snapshot on disk, which says nothing about the
    #    store the re-check just measured (see enrich_starvation_alerts.py).
    if [ "$EVIDENCE_FREE" = true ]; then
        PROOF="evidence-free alert (payload reported 0 open and 0 excluded beads)"
    elif [ "$OVERALL" = "HEALTHY" ]; then
        PROOF="diagnostics report is HEALTHY"
    else
        PROOF=""
    fi
    if [ -n "$PROOF" ] && [ "$UNEXPLAINED_COUNT" -eq 0 ]; then
        DECISION=closed
        BASIS="$PROOF; live frontier re-check fully explained"
    else
        DECISION=kept-for-human
        if [ -z "$PROOF" ]; then
            BASIS="diagnostics report is $OVERALL"
        else
            BASIS="$PROOF contradicted by live frontier re-check"
        fi
        if [ "$UNEXPLAINED_COUNT" -gt 0 ]; then
            BASIS="$BASIS - $UNEXPLAINED_COUNT unexplained open bead(s) keep the starvation signal live"
        fi
    fi

    NOTE="$TRIAGE_MARKER
- Decision: $DECISION
- Diagnostics report: $REPORT_PATH
- Report overall status: $OVERALL
- Alert payload: open=${PAYLOAD_OPEN:-unparsed} excluded=${PAYLOAD_EXCLUDED:-unparsed}
- Basis: $BASIS
- Live frontier re-check: $UNEXPLAINED_COUNT unexplained open bead(s)
- Triaged at: $TIMESTAMP"

    RECS="$(jq -r '.recommendations[0:3][]? // empty' "$REPORT_PATH" 2>>"$LOG_FILE" || true)"
    if [ -n "$RECS" ]; then
        NOTE="$NOTE
- Top recommendations:"
        while IFS= read -r rec; do
            NOTE="$NOTE
  - $rec"
        done <<<"$RECS"
    fi

    if [ "$DRY_RUN" = true ]; then
        log INFO "[dry-run] TRIAGE_DECISION $bead_id $DECISION (basis: $BASIS; report: $REPORT_PATH status: $OVERALL)"
        if [ "$DECISION" = closed ]; then CLOSED=$((CLOSED + 1)); else KEPT=$((KEPT + 1)); fi
        continue
    fi

    # 4. Attach the note. `bead update --notes` REPLACES the whole field, so
    #    the current notes are read back and combined, and the update carries
    #    --if-revision from that same read: a concurrent edit exits 4 loudly
    #    instead of destroying either side's text. The bead is re-read (not
    #    taken from the discovery snapshot) so the revision is current.
    if ! CURRENT="$(read_bead "$bead_id")" || [ "$CURRENT" = "null" ]; then
        log ERROR "cannot re-read $bead_id before annotating - skipping"
        FAILED=$((FAILED + 1))
        continue
    fi
    CURRENT_STATUS="$(jq -r '.status // .effective_status // ""' <<<"$CURRENT")"
    if [ "$CURRENT_STATUS" != "open" ]; then
        log INFO "SKIP $bead_id: no longer open (now: ${CURRENT_STATUS:-unknown}) - a live claim or close wins"
        SKIPPED=$((SKIPPED + 1))
        continue
    fi
    EXISTING_NOTES="$(jq -r '.notes // ""' <<<"$CURRENT")"
    REVISION="$(jq -r '.revision // empty' <<<"$CURRENT")"
    if [ -n "$EXISTING_NOTES" ]; then
        COMBINED="$EXISTING_NOTES

$NOTE"
    else
        COMBINED="$NOTE"
    fi
    UPDATE_ARGS=(update "$bead_id" --notes "$COMBINED")
    if [ -n "$REVISION" ]; then UPDATE_ARGS+=(--if-revision "$REVISION"); fi
    if ! bead "${UPDATE_ARGS[@]}" >> "$LOG_FILE" 2>&1; then
        log ERROR "note update failed for $bead_id (concurrent edit?) - retrying next pass"
        FAILED=$((FAILED + 1))
        continue
    fi

    # 5. Act on the decision.
    if [ "$DECISION" = closed ]; then
        if [[ ",$labels," == *",$HUMAN_LABEL,"* ]]; then
            if ! bead label remove "$bead_id" --label "$HUMAN_LABEL" >> "$LOG_FILE" 2>&1; then
                log ERROR "human-label strip failed for $bead_id - note attached, close deferred to next pass"
                FAILED=$((FAILED + 1))
                continue
            fi
        fi
        # `bead label remove` has no revision guard, so re-read before closing:
        # the close itself must be guarded against a concurrent modification.
        if ! REFRESHED="$(read_bead "$bead_id")" || [ "$REFRESHED" = "null" ]; then
            log ERROR "cannot re-read $bead_id before closing - close deferred to next pass"
            FAILED=$((FAILED + 1))
            continue
        fi
        REFRESHED_STATUS="$(jq -r '.status // .effective_status // ""' <<<"$REFRESHED")"
        REFRESHED_LABELS="$(jq -r '.labels // [] | join(",")' <<<"$REFRESHED")"
        if [ "$REFRESHED_STATUS" != "open" ] \
                || [[ ",$REFRESHED_LABELS," != *",$STARVATION_ALERT_LABEL,"* ]]; then
            log ERROR "$bead_id changed while stripping its human label (status: ${REFRESHED_STATUS:-unknown}) - refusing to auto-close"
            FAILED=$((FAILED + 1))
            continue
        fi
        REFRESHED_REVISION="$(jq -r '.revision // empty' <<<"$REFRESHED")"
        CLOSE_REASON="Auto-triaged: $BASIS (diagnostics report: $REPORT_PATH)"
        CLOSE_ARGS=(close "$bead_id" --reason "$CLOSE_REASON")
        if [ -n "$REFRESHED_REVISION" ]; then CLOSE_ARGS+=(--if-revision "$REFRESHED_REVISION"); fi
        if ! bead "${CLOSE_ARGS[@]}" >> "$LOG_FILE" 2>&1; then
            log ERROR "close failed for $bead_id - note attached, retrying next pass"
            FAILED=$((FAILED + 1))
            continue
        fi
        log INFO "TRIAGE_DECISION $bead_id closed ($BASIS; report: $REPORT_PATH)"
        CLOSED=$((CLOSED + 1))
    else
        # Keep the human label only where a human is actually needed - and
        # make sure it is present, so no autonomous worker claims the alert
        # while it waits (add is idempotent).
        if ! bead label add "$bead_id" --label "$HUMAN_LABEL" >> "$LOG_FILE" 2>&1; then
            log ERROR "human-label add failed for $bead_id - note attached, retrying next pass"
            FAILED=$((FAILED + 1))
            continue
        fi
        log INFO "TRIAGE_DECISION $bead_id kept-for-human ($BASIS; report: $REPORT_PATH)"
        KEPT=$((KEPT + 1))
    fi
    TRIAGED=$((TRIAGED + 1))
done

log INFO "TRIAGE_SUMMARY alerts=$((TRIAGED + SKIPPED)) triaged=$TRIAGED closed=$CLOSED kept=$KEPT skipped=$SKIPPED failed=$FAILED unexplained_live=$UNEXPLAINED_COUNT"
if [ "$FAILED" -gt 0 ]; then
    log ERROR "=== Triage pass complete with $FAILED failure(s) ==="
    exit 1
fi
log INFO "=== Triage pass complete ==="
exit 0
