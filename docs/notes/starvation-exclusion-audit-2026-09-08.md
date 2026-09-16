# Starvation Exclusion Audit — 2026-09-08 (alert aidedeca-f8209532)

Re-audit performed by unravel bead `aidedeca-c8e0bccf`, extending the 2026-08-29
investigation recorded on alert bead `aidedeca-f8209532` ("Starvation alert: beads
invisible in "). Method: mechanical classification of every non-closed bead the
ready frontier excludes, from `bead list --ready --json` vs `bead list --status
open|in_progress --json`, cross-checked with the read-only five-check diagnostic
suite (`scripts/diagnose_pluck_starvation.py`).

## Headline

- **The ready frontier is not empty.** `bead list --ready` returns 14 candidates
  (snapshot 2026-09-08T08:33Z). No starvation exists to explain.
- **Every excluded bead is mechanically explained. Zero unexplained exclusions.**
- The alert was already closed 2026-08-29T07:16Z as benign; this audit re-confirms
  that closure and corrects one claim in its original note (see below).

## Diagnostic suite verdict

`HEALTHY` — report `/tmp/pluck-diag-aidedeca-c8e0bccf.json` (run 2026-09-08T08:31Z):

| Check | Result |
|---|---|
| Bead store consistency | 1565 beads (15 open / 4 in_progress / 1546 closed at run time); assigned-but-open = 0; manually blocked = 0 |
| Checkpoint freshness | current.json 1565 issues == forensic.jsonl 1565 issue records — fresh |
| Pluck query (`bead list --ready`) | executed OK; 13–14 candidates; `.beads/diagnostics/pluck-diagnostics.json`: total_open_beads=15, final_candidate_count=13 |
| Corruption (`bead doctor --rehearse`) | clean, rc=0, no corruption indicators |
| Config | `.beads/config.json` and `.needle.yaml` both bead-rs, no mismatch |

Only medium finding: `publish.lock` exists while the checkpoint is demonstrably
current — an artifact of concurrent fleet writers on this shared workspace, not a
frontier factor.

## Classification table (snapshot 2026-09-08T08:33Z)

19 non-closed beads (16 open + 3 in_progress). Ready frontier: 14. Excluded: 5.

| Bead | Class | Evidence |
|---|---|---|
| `aidedeca-808326df` | in-progress | live claim, assignee `claude-code-glm-5.3-flash-glm-seam` |
| `aidedeca-b3891999` | in-progress | live claim, assignee `claude-code-glm-5.3-flash-glm-adc` |
| `aidedeca-c8e0bccf` | in-progress | live claim, assignee `claude-code-glm-5.3-flash-glm-spaxel2` (this audit) |
| `aidedeca-e1c65eb0` | dependency-blocked | sole blocker `aidedeca-cc3840fe` is open |
| `aidedeca-faf4e5bd` | dependency-blocked | sole blocker `aidedeca-cc3840fe` is open |
| 14 remaining open beads | **in frontier (ready)** | open ∧ unassigned ∧ no dependencies ∧ not manually blocked ∧ no pluck exclude_label |

Ready set: `aidedeca-0467e64a`, `2a3e09ac`, `69ecf16f`, `7c87573e`, `871026b6`,
`89429bf7`, `8d444d73`, `b332cbe4`, `be51beed`, `cc3840fe`, `cebb0f5d`,
`cf602801`, `dbf7c65b`, `eefec13e`.

Per-class totals: **14 ready · 3 in-progress · 2 dependency-blocked ·
0 assigned-but-open · 0 deferred · 0 manually-blocked · 0 label-excluded ·
0 unexplained.**

Note: the open/in_progress split shifts by ±2 between snapshots as live NEEDLE
workers claim and release beads on this shared checkout (observed 14+5 at 08:28,
16+3 at 08:33). Bucket membership is stable; totals are not hand-tuned.

## Label-gate verification (correction to the 2026-08-29 closure note)

The original closure note claimed the frontier was "likely" filtering
`umbrella` / `verification-failed` beads and called that intentional. The collected
config history does not support it:

- `.needle.yaml` `strands.pluck.exclude_labels` has contained exactly
  `intent_type=task-profile`, `intent_id=test-1`, `session_id=session-1` since
  introduction (commit `2e4048fc`, 2026-07-24 "exclude rehearsal/test-fixture beads
  from fleet dispatch"), survived the bead-rs migration unchanged (`6343b039`,
  2026-08-14), and is unchanged at HEAD. **`umbrella` and `verification-failed`
  were never configured exclusions.**
- Live counter-proof: `aidedeca-8d444d73` carries `verification-failed` and **is in
  the ready frontier right now.**
- No non-closed bead carries any configured exclude_label, so label exclusion
  currently excludes nothing.
- The one bead the 08-29 note attributed to the label gate — `aidedeca-a1ba8617`
  ("kubectl delete pod") — is closed; its own notes record a **policy-block**
  (CLAUDE.md kubectl-mutation prohibition + the `org-rule-guard` PreToolUse hook)
  requiring user clarification, not a label gate. Its exclusion can no longer be
  replayed from collected data because the bead is closed, but nothing today
  behaves the way that explanation required.

Frontier semantics verified empirically: ready = `status=open` ∧ `assignee IS NULL`
∧ no unclosed blocker ∧ `manual_blocked=0` ∧ no `exclude_labels` match. The query
matches its documented behavior exactly on every one of the 19 non-closed beads —
no evidence the frontier query is lying.

## Historical beads from the 08-29 classification

All three are closed: `aidedeca-a1ba8617` (2026-08-29T12:18Z), `aidedeca-fd9798bb`
(2026-08-29T11:09Z), `aidedeca-215fd564` (2026-08-30T13:46Z). The 2026-09-07
assigned-but-open test fixtures (`aidedeca-2580bcad`, `aidedeca-230f56eb`) are also
closed.

## Alert-emitter defect (context, not this alert's cause)

The alert body filed as "Workspace: (empty) · Open beads: 0 · Excluded beads: 0"
while open beads existed — the self-contradicting emitter template. Root-cause work
on the emitter is tracked in unravel children `aidedeca-cebb0f5d`,
`aidedeca-cf602801`, `aidedeca-89429bf7` (NEEDLE `src/strand/pluck.rs`).

## Verdict

**Proven benign.** Frontier correctly populated (not empty), all exclusions
mechanically explained, zero unexplained exclusions, diagnostic suite HEALTHY. No
defect bead warranted. The alert remains closed as originally closed
2026-08-29T07:16Z; re-confirmed 2026-09-08 by `aidedeca-c8e0bccf`.
