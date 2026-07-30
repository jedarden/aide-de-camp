# adc-4my9q — close-timestamp high-water mark dedup

**Parent:** adc-qw85 (Bead Watcher, plan §10 — CLI-only bead-close detection)
**Status at pickup:** already implemented by the parent bead. This note records
the verification and closes the granular split-child.

## What was asked

Replace the former in-memory `_processed_beads` ID-set dedup (which re-delivered
the entire closed backlog on every restart) with a **close-timestamp high-water
mark**:

- `self._close_highwater` holds the newest close time (UTC epoch seconds) already
  processed. It is in-memory only, so it is lost on restart.
- Each tick emits only beads closed **strictly after** the mark, then advances
  the mark to the newest close seen this tick.
- On the first poll — and after any restart, since the mark is in-memory — seed
  the mark to the newest existing close time and **emit nothing**, so a restart
  re-reads the backlog but does not re-deliver it.
- Parse bf's `closed_at` (RFC3339, up to nanosecond precision, trailing `Z`) to
  UTC epoch seconds robustly; an unparseable close time is skipped, not fatal.

## Finding: scope already absorbed by the parent commit

The parent bead adc-qw85 was implemented wholesale in commit **15c228d**
(`feat(watcher): CLI-only bead-close detection with close-timestamp HWM`), which
landed this child's exact scope as the `BeadWatcher._close_highwater` field plus
the cleanly-factored `_poll_closed_beads()` / `_parse_close_epoch()` methods and
a dedicated `TestHighWaterMark` suite. The `_processed_beads` ID set it replaces
was deleted in that same commit (verified and closed by sibling adc-2aepu,
commit fc6cb39). No additional code is needed — a second implementation would
only duplicate what is committed.

## Acceptance-criteria → code mapping (all satisfied)

| Criterion | Evidence in `src/watcher/daemon.py` |
|-----------|--------------------------------------|
| Replaces the in-memory `_processed_beads` ID-set dedup with `_close_highwater` | `self._close_highwater: Optional[float] = None` (line 139); comment "adc-qw85: replaces the former in-memory _processed_beads ID set" (line 138). `grep _processed_beads src/` → no hits. |
| Mark holds the newest close time (UTC epoch seconds) already processed | In-memory float field, set on baseline (line 333) and advanced (line 356) |
| First poll / after restart: seed to newest existing close, emit nothing | baseline branch: `if self._close_highwater is None:` → `self._close_highwater = parsed[-1][0]`; `return []` (lines 330–339) |
| Each tick emits only beads closed strictly AFTER the mark | `if ts <= self._close_highwater: continue` — `<=`, so equal is excluded (line 344) |
| Then advance the mark to newest close seen this tick | `self._close_highwater = parsed[-1][0]` (line 356); `parsed` is sorted ascending so `[-1]` is the max |
| Parse RFC3339 `closed_at` (nanosecond precision, trailing `Z`) → UTC epoch | `_parse_close_epoch` via `datetime.fromisoformat(closed_at).timestamp()` (line 373); fromisoformat (3.11+) accepts nanos + `Z` and yields a UTC-aware datetime, so `.timestamp()` is correct regardless of host TZ |
| Unparseable close time skipped, not fatal | parse loop: `ts = _parse_close_epoch(rec.get("closed_at"))`; `if ts is None: continue` (lines 324–327); `_parse_close_epoch` returns None + logs a warning on `ValueError`/`TypeError` (lines 374–376) |

## Acceptance-criteria → test mapping (all satisfied)

`tests/test_bead_watcher.py::TestHighWaterMark` (7 tests):

| Acceptance criterion | Test |
|----------------------|------|
| After a restart, a bead at or below the mark is NOT re-emitted | `test_bead_at_or_below_hwm_not_emitted` (strictly-newer only; `==` excluded) and `test_restart_does_not_redeliver_backlog` (new instance, same backlog → re-baseline, nothing re-delivered) |
| A newly-closed bead (close ts > mark) emitted exactly once, mark advances | `test_emits_only_strictly_newer_closure` (one emitted, mark advances to newest) and `test_newer_closure_between_ticks_delivered` (baseline tick emits nothing; a strictly-newer closure on the next tick is delivered) |
| First-tick baseline emits nothing while still seeding the mark | `test_first_tick_baselines_and_emits_nothing` (`_close_highwater` is None → `_poll_closed_beads()` returns `[]` and the mark is seeded to the newest close) |

Robustness: `test_unparseable_closed_at_skipped` (a malformed and a missing
`closed_at` are dropped; a later well-formed newer record still surfaces) and
`TestParseCloseEpoch` (nanosecond-`Z`, seconds-`Z`, malformed→None, chronological
ordering).

## Verification

```
$ command -v bf && bf --version
/home/coding/.local/bin/bf
bf 0.3.0

$ .venv/bin/python -m pytest tests/test_bead_watcher.py -q
..............................................  [100%]
46 passed in 0.33s
```

Includes `TestHighWaterMark`, `TestParseCloseEpoch`, and `TestRealBfEndToEnd`,
which exercised the **real** `bf` CLI (`bf` 0.3.0 is on PATH, so the tests ran
rather than skipped):

```
tests/test_bead_watcher.py::TestRealBfEndToEnd::test_detects_new_closure_within_one_tick PASSED
tests/test_bead_watcher.py::TestRealBfEndToEnd::test_restart_does_not_redeliver       PASSED
```

`grep -rn _processed_beads src/` → only the allowed historical comment at
`daemon.py:138` ("adc-qw85: replaces the former in-memory _processed_beads ID
set"). The ID-set dedup this child replaces is gone — no field, no usage —
removed by the parent in 15c228d (verified by sibling adc-2aepu, commit fc6cb39).

## Outcome

No file changes to `src/` or `tests/` — the implementation and tests are already
committed and passing. This note is the commit artifact for the bead.
