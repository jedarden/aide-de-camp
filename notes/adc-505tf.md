# adc-505tf — `bf list --status closed` subprocess invocation

**Parent:** adc-qw85 (Bead Watcher, plan §10 — CLI-only bead-close detection)
**Status at pickup:** already implemented by the parent bead. This note records
the verification and closes the granular split-child.

## What was asked

Replace the deleted direct `.beads/` read path in the watch tick with CLI
detection: each tick runs `bf list --status closed --json` via
`asyncio.create_subprocess_exec` from the aide-de-camp checkout
(`cwd=/home/coding/aide-de-camp`; plan "Beads-Workspace Scoping"), parses the
JSONL stdout into a list of bead-record dicts (one JSON object per line; a
malformed line is skipped, not fatal), with binary/path/cwd injectable for
tests via `bf_bin` / `bf_workspace` ctor args. This child only fetches raw
closed-bead records — it does NOT dedup, resolve intents, or write results.

## Finding: scope already absorbed by the parent commit

The parent bead adc-qw85 was implemented wholesale in commit **15c228d**
(`feat(watcher): CLI-only bead-close detection with close-timestamp HWM`),
which landed this child's exact scope as the cleanly-factored
`BeadWatcher._run_bf_list_closed()` method, plus the supporting constants,
injectable constructor args, and the full test suite. No additional code is
needed — a second implementation would only duplicate what is committed.

## Acceptance-criteria → code mapping (all satisfied)

| Criterion | Evidence in `src/watcher/daemon.py` |
|-----------|--------------------------------------|
| A tick runs `bf list --status closed` | `create_subprocess_exec(self._bf_bin, "list", "--status", "closed", "--json", cwd=self._bf_workspace, …)` (lines 395–401) |
| Returns the set of closed bead records from the adc workspace | `_run_bf_list_closed() -> list[dict]`; `BF_WORKSPACE = "/home/coding/aide-de-camp"` |
| bf runs from the correct cwd; binary resolved via PATH by default | `BF_BIN = "bf"` (PATH-resolved); `cwd=self._bf_workspace` |
| Records emitted to next stage carry bead_id + close timestamp | `BeadEvent(bead_id=rec.get("id"), timestamp=int(ts), data=rec)` — the full record (incl. raw `closed_at`) is preserved on `data` |
| via `asyncio.create_subprocess_exec` | line 395 |
| JSONL parse; malformed line skipped, not fatal | per-line `try/except json.JSONDecodeError` logs + continues |
| Binary/path/cwd injectable via ctor args | `bf_bin`, `bf_workspace`, `subprocess_timeout_seconds` params (lines 83–85) |
| Fetches raw records only — no dedup / intent resolution / writes | `_run_bf_list_closed` returns raw `list[dict]`; HWM + routing live in `_poll_closed_beads` / `_process_bead_event` |

## Verification

```
$ .venv/bin/python -m pytest tests/test_bead_watcher.py -q
..............................................  [100%]
46 passed in 0.33s
```

Includes `TestRunBfListClosed` (the 6 wrapper tests: happy path, missing
binary, spawn OSError, non-zero exit, timeout+kills-proc, malformed-line
skipping) and `TestRealBfEndToEnd`, which exercised the **real** `bf` CLI
(`bf` is on PATH, so the tests ran rather than skipped):

```
tests/test_bead_watcher.py::TestRealBfEndToEnd::test_detects_new_closure_within_one_tick PASSED
tests/test_bead_watcher.py::TestRealBfEndToEnd::test_restart_does_not_redeliver PASSED
```

The real CLI confirms the JSONL format the parser assumes (one JSON object per
line, `id` + nanosecond-precision RFC3339 `closed_at`):

```
$ bf list --status closed --json -w /home/coding/aide-de-camp | head -1 | cut -c1-160
{"id":"adc-2aepu","title":"Remove the direct .beads/ read path from the bead watcher","description":"Parent: adc-qw85 …
```

`grep '.beads/' src/watcher` is clean — the direct-read path this child was
meant to replace is already gone (verified and closed by sibling adc-2aepu,
commit b34bad9).

## Outcome

No file changes to `src/` or `tests/` — the implementation and tests are
already committed and passing. This note is the commit artifact for the bead.
