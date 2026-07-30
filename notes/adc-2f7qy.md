# adc-2f7qy — harden the detection tick and wire CLI detection into the watch loop

**Parent:** adc-qw85 (Bead Watcher, plan §10 — CLI-only bead-close detection)
**Status at pickup:** already implemented by the parent bead. This note records
the verification and closes the granular split-child.

## What was asked

Harden the detection tick (the placeholder left by child 1 / adc-4afi) and wire
the CLI detection into the watch loop, so that **every** failure mode is caught
and logged and yields "no new closures this tick":

- subprocess **timeout**, **non-zero exit**, **missing binary**, and **per-line
  parse failures** are each caught and logged, returning no new closures.
- **One tick's failure must NOT kill the watch task** — the lifespan supervisor
  from adc-4afi is the backstop.
- A caught failure must be **indistinguishable to callers from "no new
  closures"** — no exception escapes the tick body.
- **Scope guard:** this stage only emits closed-bead records to the next stage
  (child 4 consumes them); it does NOT resolve intents or write results. Bead
  id + close ts must remain available downstream.

## Finding: scope already absorbed by the parent commit

The parent bead adc-qw85 was implemented wholesale in commit **15c228d**
(`feat(watcher): CLI-only bead-close detection with close-timestamp HWM`).
That commit landed this child's exact scope — the real CLI tick wired into the
watch loop, with every failure mode guarded — replacing the no-op placeholder
left by adc-4afi. No additional code is needed: a second implementation would
only duplicate what is committed. (Same finding recorded by siblings adc-2aepu,
adc-505tf, adc-4my9q.)

## Wiring: CLI detection is in the live watch loop (no placeholder)

The placeholder from adc-4afi is gone. The tick body is a real chain straight
to the subprocess:

```
_watch_loop (daemon.py:264)
  └─ await self._check_for_events()              # :275
       └─ events = await self._poll_closed_beads()   # :299  (HWM filter)
            └─ records = await self._run_bf_list_closed()  # :318  (subprocess)
```

`grep -n placeholder src/watcher/daemon.py` → no hits. The only remaining
"no-op" string in the file (:553) is the documented Telegram-graceful-noop
comment, unrelated to the tick.

`_check_for_events` (daemon.py:290) emits the closed-bead records to
`_process_bead_event` (the downstream next stage — child 4 owns the
close → result path). Each `BeadEvent` carries the bead id, the close
timestamp (`timestamp=int(ts)`), and the full record on `data` (which
preserves the raw `closed_at`), so bead id + close ts remain available
downstream — the scope guard is satisfied at the detection layer.

## Acceptance-criteria → code mapping (all satisfied)

| Criterion | Evidence in `src/watcher/daemon.py` |
|-----------|--------------------------------------|
| Missing binary caught + logged, non-fatal | `except FileNotFoundError` → ERROR log "bf binary … not found … skipped this tick" → `return []` (:402–408) |
| Spawn OSError caught + logged | `except OSError as e` → ERROR log → `return []` (:409–411) |
| Subprocess timeout caught + logged | `except asyncio.TimeoutError` → `proc.kill()` + `await proc.wait()` → WARNING "timed out" → `return []` (:417–424) |
| Non-zero exit caught + logged | `if proc.returncode != 0:` → WARNING "exited N: <stderr>" → `return []` (:426–432) |
| Per-line parse failure caught + logged | per-line `try: json.loads(line) … except json.JSONDecodeError` → WARNING "Skipping unparseable … line N" → continues (:441–446) |
| Caught failure indistinguishable from "no closures" | every failure branch returns the same `[]` a clean-but-empty poll would; `_poll_closed_beads` then returns `[]` → `_check_for_events` iterates nothing |
| No exception escapes the tick body | all five failure modes caught inside `_run_bf_list_closed`; `_parse_close_epoch` absorbs its own `ValueError`/`TypeError` (:372–376); `_watch_loop` still catches any residual `Exception` as defence-in-depth (:278) |
| One tick's failure does not kill the task | `_run_bf_list_closed` returning `[]` makes the tick complete normally → `_stamp_tick()` advances → loop sleeps and ticks again (:283–286); the supervisor (adc-4afi) is the backstop if the task ever truly dies |

## Acceptance-criteria → test mapping (all satisfied)

`tests/test_bead_watcher.py` — `TestRunBfListClosed` (6 tests), the suite
targeting this child's robustness:

| Acceptance criterion | Test |
|----------------------|------|
| Missing binary logged, non-fatal, returns no closures | `test_missing_binary_returns_empty` — `bf_bin="/nope/…"` → recs == [] and an ERROR containing "not found" |
| Spawn OSError logged, non-fatal | `test_spawn_oserror_returns_empty` |
| Non-zero exit logged, non-fatal | `test_nonzero_exit_returns_empty` — recs == [] and a WARNING containing "exited 2" |
| Subprocess timeout logged, non-fatal, proc killed | `test_timeout_returns_empty_and_kills_proc` — recs == [], `proc.killed is True`, WARNING "timed out" |
| Per-line parse failure: one bad line does not discard the rest | `test_malformed_lines_skipped_others_kept` — both good records returned, 2 "unparseable" warnings |

The other two acceptance criteria:

| Acceptance criterion | Test |
|----------------------|------|
| Closing a test bead via bf is detected within one poll interval | `TestRealBfEndToEnd::test_detects_new_closure_within_one_tick` — exercises the **real** `bf` CLI: baseline emits nothing, a fresh `bf close` is detected on the next tick carrying its close ts |
| One tick's failure does not kill the watch task (task survives + keeps ticking) | `TestSupervisorRestart::test_transient_exception_does_not_trigger_restart` — a recurring per-tick `RuntimeError` is absorbed by the loop; no supervisor backoff is ever requested, `restart_count == 0`, and `tick_count >= 4` (it kept ticking) |

## Verification

```
$ command -v bf && bf --version
/home/coding/.local/bin/bf
bf 0.3.0

$ .venv/bin/python -m pytest tests/test_bead_watcher.py -q
..............................................  [100%]
46 passed in 0.32s

$ .venv/bin/python -m pytest tests/test_bead_watcher.py -v \
    -k "TestRunBfListClosed or TestRealBfEndToEnd or TestSupervisorRestart or TestHighWaterMark"
... 17 passed, 29 deselected in 0.31s
```

The real-CLI end-to-end tests **ran** (not skipped — `bf` 0.3.0 is on PATH),
confirming a real `bf close` is detected on the next tick:

```
tests/test_bead_watcher.py::TestRealBfEndToEnd::test_detects_new_closure_within_one_tick PASSED
tests/test_bead_watcher.py::TestRealBfEndToEnd::test_restart_does_not_redeliver       PASSED
```

## Outcome

No file changes to `src/` or `tests/` — the robust tick body and its wiring
into the watch loop are already committed and passing. This note is the commit
artifact for the bead.
