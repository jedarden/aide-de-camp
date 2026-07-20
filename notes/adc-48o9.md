# adc-48o9 — Starvation alert: beads invisible to worker

**Resolution:** queue-pollution cleanup (not a config error). Deleted 21 test-originated
beads and flushed. Open count dropped 29 → 16; the genuinely-pluckable real work was
always there.

## Diagnosis

The alert claimed "Pluck found none" and suggested checking `exclude_labels`,
workspace path, and filter configuration. None of those were actually wrong:

- **Pluck config** (`~/.config/needle/config.yaml`, `strands.pluck`):
  `exclude_labels: [deferred, human, blocked]`, `split_after_failures: 3`. Correct.
- **Workspace:** `/home/coding/aide-de-camp` is a registered `strands.explore` workspace
  with its own `.beads/`. Path is fine.
- **Genuinely pluckable beads existed** the whole time: `adc-372c`, `adc-d2sp`,
  `adc-5tl0`, `adc-7czu`, `adc-2482`, `adc-1c8o` (open, unassigned, no blocker, not
  deferred/human/blocked).

### Root cause: queue pollution, not misconfiguration

21 beads carried `intent_id=test-1` + `session_id=session-1` labels — the exact encoding
`escalate/handler.py._create_bead` writes (pinned in `tests/test_bead_watcher.py:41-49`).
All 21 were `"kubectl delete pod"` **action** beads with **no target pod name** — i.e.
non-executable test artifacts leaked into the live bead DB. 13 of them were `open`,
inflating the "open" count and presenting workers with unworkable items that bounce
on pickup (see `adc-blg1`'s `failure-count:5` for the same failure-bounce pattern;
`split_after_failures: 3` then splits/defers them, generating more noise).

Breakdown of the 21 deleted:
- 13 open (the direct starvation-signal inflators)
- 7 closed + 1 resolved (inert, but would have been archived by `br rotate` and
  mis-counted as real history/velocity)

Nothing depended on any of them (verified against the `dependencies` table).

## Action taken

```bash
for id in <21 ids>; do br delete "$id"; done
br sync --flush-only          # persist db → issues.jsonl (mutations don't auto-flush)
sqlite3 .beads/beads.db "PRAGMA integrity_check;"   # ok
```

Post-cleanup: 103 total / **16 open** / 3 in-progress / 0 test-pollution. Integrity `ok`.
Deletions are soft (`deleted_at` set in db); the JSONL checkpoint simply omits deleted
beads, so the change is fully reversible via git history.

## Remaining queue shape (16 open)

| Category | Beads | Pluckable? |
|---|---|---|
| Deferred / umbrella | `adc-lc4, adc-388, adc-wa9, adc-44u, adc-hyqc, adc-blg1` | no (excluded) |
| Human-gated | `adc-5zs` | no (excluded) |
| Dependency-blocked (Telegram first-failure chain) | `adc-4hvx, adc-15u0, adc-20p9` | no (blocked) |
| Real, ready | `adc-372c, adc-d2sp, adc-5tl0, adc-7czu, adc-2482, adc-1c8o` | **yes (6)** |

## Follow-ups (not addressed here — owned by other beads)

1. **`adc-47l2` is committed-but-unclosed** (`e809712 feat(telegram): rate-limit…`),
   yet still `in_progress` and blocking the entire Telegram first-failure chain
   (`adc-4hvx ← adc-15u0 ← adc-20p9 ← adc-47l2`). Closing it unblocks 3 beads.
   Deeper in, `adc-blg1 ← adc-1dbu` is transitively blocked — separate investigation.
2. **`adc-1c8o` carries `ops-gated`** but it is *not* in Pluck's `exclude_labels`, so
   it WILL be plucked despite being security-gated. Consider adding `ops-gated` to
   `strands.pluck.exclude_labels` in `~/.config/needle/config.yaml` (global config,
   outside this repo).
3. **Source of the leak:** the escalate handler created 21 beads for a single
   `intent_id=test-1`. Confirm whether a test or a stuck dispatch loop is feeding the
   real `.beads/beads.db` and harden the entry point (the test endpoint work in
   `adc-blg1` / `adc-3mc5` is the likely source).
