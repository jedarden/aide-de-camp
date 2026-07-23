# Verification: CLI-Only Bead-Close Detection (adc-qw85)

## Status: ✅ VERIFIED — Already Shipped

The CLI-only bead-close detection with close-timestamp high-water mark was **already implemented and shipped** in commit `15c228d`:
```
feat(watcher): CLI-only bead-close detection with close-timestamp HWM (adc-qw85)
```

## Acceptance Criteria Verification

### 1. ✅ Closing a test bead via bf is detected within one interval
- `_poll_closed_beads()` (daemon.py:303-357) emits beads closed strictly after `_close_highwater`
- `_run_bf_list_closed()` (daemon.py:378-447) runs `bf list --status closed --json` each tick
- Poll interval defaults to 30 seconds (CHECK_INTERVAL_SECONDS)

### 2. ✅ High-water mark prevents re-emission after restart
- `_close_highwater: Optional[float]` (daemon.py:139) tracks newest close timestamp processed
- On first tick after restart, baseline is set from existing backlog: `self._close_highwater = parsed[-1][0]` (line 333)
- Baseline tick emits nothing: `return []` (line 339) — only closures AFTER the mark surface

### 3. ✅ No direct .beads/ file reads
```bash
$ grep -rn "\.beads/" src/watcher/
# No matches found ✅
```
All legacy code removed:
- `BEADS_JSONL` constant — deleted
- `beads_jsonl` ctor param — deleted
- `_read_terminal_events()` method — deleted
- `_processed_beads` set — deleted (replaced by `_close_highwater`)

### 4. ✅ bf subprocess failure is logged, not fatal
`_run_bf_list_closed()` handles all failure modes gracefully:
- `FileNotFoundError` → logged, returns `[]` (lines 402-408)
- `OSError` on spawn → logged, returns `[]` (lines 409-411)
- `asyncio.TimeoutError` → logged, returns `[]` (lines 417-424)
- Non-zero exit code → logged, returns `[]` (lines 426-432)
- Unparseable JSON line → logged per line, continues (lines 443-446)

## Implementation Summary

**Key constants:**
- `BF_BIN = "bf"` (daemon.py:68)
- `BF_WORKSPACE = "/home/coding/aide-de-camp"` (daemon.py:73)
- `SUBPROCESS_TIMEOUT_SECONDS = 10.0` (daemon.py:77)

**Key methods:**
- `_run_bf_list_closed()` (daemon.py:378-447) — subprocess call to `bf list --status closed --json`
- `_parse_close_epoch()` (daemon.py:360-376) — parses RFC3339 `closed_at` to UTC epoch
- `_poll_closed_beads()` (daemon.py:303-357) — HWM filtering logic

**Scope guard:** The watcher emits closed-bead records to `_process_bead_event()` (daemon.py:474+), which routes to surfaces. It does NOT resolve intents or write results itself — child 4 owns the close → result path.

## Beads-Workspace Scoping

Per the plan, all bf invocations run from the aide-de-camp repo workspace:
```python
BF_WORKSPACE = "/home/coding/aide-de-camp"
```
The subprocess uses `cwd=self._bf_workspace` (line 398) so bf sees every bead this app owns.

---

**Verified:** 2026-07-22
**Commit:** 15c228d (already shipped)
