# Atomic Cleanup Designs

**Status:** approved implementation design
**Review date:** 2026-08-09
**Scope:** file, resource, and shared-state cleanup catalogues for aide-de-camp
**Owner:** adc-m2zkcx

## Purpose and decision

This document turns the cleanup catalogue into implementation-ready designs. It
defines the linearization point for each operation, the synchronization or
transaction boundary, and the recovery behavior when a later step fails. It is
design guidance; it does not change production code.

The catalogue sources are:

- `RESOURCE_CLEANUP_ATOMICITY_ANALYSIS.md`: 12 resource operations.
- `STATE_CLEANUP_ATOMICITY_ANALYSIS.md`: 51 state entries, including grouped
  entries that cover multiple related locations.
- The file-operation audit at `/home/coding/scratch/atomicity-audit-report.md`:
  eight non-atomic file writes, plus the append-only confirmation log and
  already-safe file deletions. The file entries are reproduced here so this
  design remains usable without the scratch report.

“Atomic” means that observers see one complete logical state, not that every
`await`, socket close, or filesystem unlink can be rolled back physically. An
external close is therefore represented as a claim/finalize protocol, and an
external side effect is represented as an idempotent state machine or durable
outbox.

## Common implementation contract

Every replacement below must satisfy these rules:

1. **Define the commit point.** Publish a new immutable snapshot, commit a SQL
   transaction, atomically replace a file, or record a state-machine
   transition. Do not call a multi-step operation “atomic” merely because one
   dictionary operation is atomic in CPython.
2. **Make retries safe.** Missing entries, already-closed handles, repeated
   stop calls, and duplicate acknowledgements must be successful no-ops or
   return the existing terminal result. Use an operation ID, generation, or
   content hash when a side effect can be repeated.
3. **Claim before awaiting.** Under the owner lock, move work from `ready` to
   `in_flight` (or detach a resource). Release the lock before I/O. On success
   finalize; on failure or cancellation restore the claim or leave a durable
   retry record.
4. **Never publish metadata early.** Build and validate a complete replacement
   off to the side. Swap the pointer and all metadata together under one lock.
   Keep the old value if parsing, I/O, cancellation, or validation fails.
5. **Use one owner lock.** All readers and writers of a shared structure must
   use the same lock, or the structure must be explicitly single-event-loop
   owned. Lock-free fast paths are valid only with immutable snapshots and a
   generation/version check.
6. **Do not hold an asyncio lock over external I/O.** The lock protects the
   claim and final state transition; it must not be held while awaiting a
   socket close, database call, task, or broadcast.
7. **Preserve unfinished work.** A timeout is not success. Keep unfinished
   tasks, queue items, approvals, or database rows discoverable for retry and
   report a degraded/partial result.
8. **Aggregate shutdown errors.** One cleanup failure must not skip independent
   cleanups. Run every step, collect per-resource exceptions, and only report
   complete shutdown when all required terminal states are reached.
9. **Test the failure boundary.** For each operation test repeat calls,
   concurrent callers, cancellation/error at every awaited step, and recovery
   after a process restart where durable state is involved.

## Reusable atomic patterns

### P1 — Same-directory temporary file then replace

Use for complete-file replacement. Serialize writers with a per-path lock or
compare the source generation before committing. Create a uniquely named temp
file in the target directory, write and validate it, flush and `fsync` it, then
call `os.replace(temp, target)`. Optionally `fsync` the directory for crash
durability. The replace is the commit point: readers see the old complete file
or the new complete file.

On any pre-commit failure, close the descriptor and unlink only the temp file
owned by this operation. On a concurrent writer, use a lock or reject the
replace when the expected target hash/mtime no longer matches. Never put the
temp file in another filesystem, and never use a predictable shared temp name.

### P2 — Idempotent delete with ownership validation

Use for a disposable file, directory, or registry entry. Validate the exact
path and ownership first; for a filesystem lock, verify that it is stale and
belongs to this repository before touching it. Prefer `unlink(missing_ok=True)`
or `pop(key, None)` for a single item. For a directory, atomically rename the
owned stale directory to a unique quarantine name, then remove the quarantine
tree. This prevents a new owner from being deleted after the stale check.

Deletion failures remain observable and retryable. Never broaden a cleanup glob,
delete a lock merely because it exists, or treat `PermissionError` as success.

### P3 — Immutable snapshot swap

Build a complete replacement in local variables, including related metadata such
as a timestamp, generation, counters, or task list. Under one lock, swap one
container object (prefer a small dataclass/tuple) and increment its generation.
Readers take one snapshot and use the values from that snapshot. A failed build
does not mutate the current snapshot. A writer that started from an old
generation must retry or discard its result rather than overwrite a newer
write.

### P4 — Claim, perform, finalize

Use for external resources and asynchronous work. Under a lock, transition an
item from `OPEN`/`PENDING` to `CLOSING`/`IN_FLIGHT` exactly once and detach it
from the active set. Perform the close, narration, broadcast, or API call
outside the lock. Under the lock, record `CLOSED`, `FAILED_RETRYABLE`, or
`COMPLETED_NOT_NOTIFIED`. A second caller observes the in-flight/terminal state
instead of repeating the side effect. A retry worker owns failed claims.

### P5 — Single-flight lifecycle state machine

Represent long-lived services with `STOPPED`, `RUNNING`, `STOPPING`, and
`FAILED_STOP` (or equivalent) plus one stop task. The first stop caller owns
the transition to `STOPPING`; later callers await the same stop task. Snapshot
all task handles under a lock, cancel every handle, await with a deadline using
`return_exceptions=True`, and close clients in a `finally` block. Clear a handle
only after its task is done. If the deadline expires, retain the handle and
return a degraded result so another stop can retry.

### P6 — Transaction plus cross-layer outbox

Use one SQL transaction for related rows. For a side effect outside the
database, write an outbox/state row in the same transaction, commit, and let a
worker perform the side effect with an idempotency key. Mark the outbox row
complete only after success. This avoids pretending that a database commit and
an SSE broadcast, file write, or external API call form one ACID transaction.

On cancellation before commit, roll back. After commit, retry the outbox row;
do not delete it merely because the first notification attempt failed.

### P7 — Claim/ack/nack queue drain

Use for pending narration, catch-up results, and test cleanup IDs. Under a lock,
move a batch to `in_flight` with a token and leave newly queued items in the
ready queue. Call the consumer outside the lock. `ack` removes the token after
success; `nack` returns it to the queue (or a durable retry/dead-letter queue)
with bounded backoff. Preserve ordering and deduplicate by item ID.

### P8 — Quiesce, swap, and drain

Use for cache/limiter/monitor replacement where old callers can still hold a
reference. Stop admitting new work to the old generation, wait for leases to
drain or explicitly let old operations finish, then publish the new generation.
Never replace a global pointer while old tasks can still publish into shared
state without a generation check.

## File operations

### File replacement matrix

| ID | Catalogued location and operation | Atomic alternative | Implementation and edge-case guidance |
| --- | --- | --- | --- |
| F-01 | `src/memory/store.py:205-206` — direct memory JSON write | P1, via the central `atomic_write` utility | Serialize the complete JSON document before opening the temp file; validate JSON; write to a same-directory unique temp, flush/fsync, then replace. Serialize concurrent saves with the store lock. A disk-full or encoding error leaves the previous memory file intact and removes only this attempt’s temp file. |
| F-02 | `src/freeze.py:98` — freeze sentinel content write | P1 | Write the sentinel to a temp file and replace the sentinel only after the full marker is present. Pair `set_frozen(False)` with P2 and a process-local lock. A failed enable keeps the previous state; a missing sentinel on disable is an idempotent success. |
| F-03 | `src/agents/self_modification.py:628-629` — prompt artifact write | P1 plus expected-version check | Compute and validate the new prompt before claiming the artifact. Under the artifact lock, compare the expected hash, then replace atomically and record the operation ID. A competing edit causes a conflict/retry, not an overwrite; preserve a backup until verification succeeds. |
| F-04 | `src/agents/self_modification.py:645-646` — configuration artifact write | P1 plus schema validation | Render and parse the complete config in memory, validate required fields, then replace. Use the same per-artifact lock and expected hash as F-03. If validation, permission, or fsync fails, the prior configuration remains active and the temp is cleaned. |
| F-05 | `src/agents/self_modification.py:705-706` — rollback artifact write | P1 with compare-and-swap | Treat rollback as a new versioned write, not an in-place copy. Verify that the live artifact still has the failed change’s hash, write the known-good backup to a same-directory temp, validate it, and replace. If another actor changed the artifact, stop and report a conflict; never destroy the newer change. |
| F-06 | `src/cli/config.py:76-77` — config rewrite after server URL change | P1 | Render all lines first and replace the complete config under a per-path lock. Keep file permissions/ownership from the old file where required. A failed write leaves the prior CLI configuration usable. |
| F-07 | `src/cli/config.py:120-121` — config rewrite after session ID change | P1 | Use the same helper and lock as F-06; do not maintain two write implementations. The operation ID and expected generation prevent an older command from replacing a newer session ID. |
| F-08 | `src/action/steps/gitops.py:423-424` — YAML manifest write | P1 plus parse-before-publish | Serialize and parse the YAML before the replace, then atomically replace the manifest. Lock per manifest and compare the checkout/index generation before commit. On failure, leave the old manifest and report the write as failed so git retry logic does not commit a partial file. |
| F-09 | `src/confirmations/confirmed_deletions.py:97-98` — append-only confirmation record | Append record under an exclusive file lock, or P1 snapshot rewrite if compaction is required | Append one complete JSON line, flush/fsync, and treat a short write as failure. Do not rewrite the whole log for a normal append. If a single record is lost, previous records remain valid; use a unique confirmation ID for retry deduplication. |

### File deletion and temporary-file cleanup

The file audit found no unsafe deletion that needs a replacement transaction.
The implementation pattern is still explicit:

- Temp cleanup in `src/utils/atomic_write.py`, `src/components/hot_reload.py`,
  `src/memory/store.py`, `src/persistence/deployment_persistence.py`, and
  `src/freeze.py` uses P2: close first, verify the path has the operation’s
  private prefix/parent, then `unlink(missing_ok=True)` in a `finally` block.
- The freeze sentinel and validation test file use exact-path P2 and are safe to
  repeat. A missing target is success; an unexpected path or permission error
  is not silently swallowed.
- Git lock cleanup in `src/action/steps/git_validation.py` must use P2’s stale
  ownership check. For a lock directory, rename it to a unique quarantine path
  before `rmtree`; never remove a live lock or recursively delete a repository
  path based only on a glob.

## Resource operations

The resource catalogue has 12 entries. R-01 and R-02 also appear as S-34 in the
state catalogue; implement one shared broadcaster protocol, not two fixes.

| ID | Catalogued location and operation | Atomic alternative | Implementation and edge-case guidance |
| --- | --- | --- | --- |
| R-01 | `src/sse/broadcaster.py:129-134` — connection unregister | P4 with a lock-protected `pop` | Add one registry lock and make unregister `pop(connection_id, None)`. Capture the connection while holding the lock, publish the removal once, and do any logging/queue signaling after releasing it. A second unregister is a no-op and never raises `KeyError`. |
| R-02 | `src/sse/broadcaster.py:253-288` — dead-connection cleanup loop | P4: claim/mark closing, then signal and finalize | Under the registry lock, claim only entries whose heartbeat/version still matches the scan. Signal the detached connection outside the lock; if its queue is full, use the stream-drop/cancellation fallback and still finalize registry removal in `finally`. A stale scan cannot remove a newly heartbeating connection, and one queue failure cannot leak the registry entry. |
| R-03 | `src/session/connection_monitor.py:256-288` — stats update, removal, and handle close | P4 with `OPEN → CLOSING → CLOSED/FAILED` | Under `_lock`, claim and detach the stats record exactly once. Decrement active tracking in the claim, close the actual connection outside the lock, then finalize closed duration or retryable close failure under `_lock`; make the counter update part of the same logical transition. Do not hold an asyncio lock across `conn.close()`. Repeated finalizers see the terminal record and do not double-decrement. |
| R-04 | `src/monitoring/ambient.py:705-724` — ambient monitor stop | P5 | Add a single-flight stop gate. Snapshot ticker/monitor tasks and client, set `STOPPING`, cancel all tasks, await them with a bounded deadline and `return_exceptions=True`, and always attempt client close in `finally`. Clear handles only when done. On timeout or close failure retain a retryable failed-stop state and report the individual failures; do not advertise `STOPPED` while work remains. |
| R-05 | `src/main.py:202-218` — application shutdown sequence | P5 plus a cleanup barrier | Represent each service as an independent cleanup step with a timeout. Stop independent services concurrently or in dependency order, but always run every step and collect exceptions. Close the component library/store in `finally`; log “shutdown complete” only when all required resources reached terminal state. There is no safe rollback that restarts a partially stopped service, so retain failed steps for retry and return an aggregated degraded result. |
| R-06 | `src/sse/broadcaster.py:243-247` — generator `finally` unregister | P2/P4 idempotent finalizer | Call the idempotent R-01 operation from `finally`, catch/log only cleanup errors, and preserve the generator’s original exception or `CancelledError`. A cleanup race is a normal no-op, not an exception that masks cancellation. |
| R-07 | `src/sse/broadcaster.py:101-110` — broadcaster stop | P5 | Guard `start`/`stop` with one lifecycle lock and one shared stop task. Set `STOPPING` before cancellation, await the cleanup task, clear its handle only after completion, and set `STOPPED` at the commit point. A timeout leaves the task handle and permits a later retry; repeated `stop()` awaits the same result. |
| R-08 | `src/session/store.py:769-773` — WAL checkpoint during close | P5 close gate plus SQLite durability protocol | A WAL checkpoint is not a rollback-able transaction. First prevent new store work, finish/commit active transactions, set a busy timeout, and run bounded retries for `BUSY/LOCKED`. Prefer `PASSIVE`/`FULL` fallback over manual WAL deletion; `TRUNCATE` is an optimization. Close the checkpoint connection in `finally`. If checkpointing remains busy, report degraded close while leaving the WAL for SQLite recovery—never claim data loss or delete the WAL by hand. |
| R-09 | `src/feedback/processor.py:202,246` — pending approval deletion | P4/P6 approval state machine | Replace direct deletion with `PENDING → APPLYING/REJECTING → APPLIED/REJECTED/FAILED_RETRYABLE`. Claim the approval under a lock using approval ID and diff hash, perform the external operation once, and remove/archive only after success. Persist an outbox or “applied-not-broadcast” state before the awaited SSE notification. Concurrent approval calls observe the in-flight/terminal state. |
| R-10 | `src/feedback/signals.py:95` — result creation timestamp deletion | P4 with ack idempotency | Claim the timestamp under a lock but retain it in an in-flight record. Persist the signal first; remove the record only after persistence succeeds. On failure/cancellation, restore the claim if no newer timestamp exists, or retain it for retry. Key retries by result ID and acknowledgement event ID so the signal cannot be duplicated. |
| R-11 | `src/context/prefetch.py:411,471` — expired cache and utterance deletion | P3 for cache, P2/P3 per-session history | Use a cache lock and conditional `pop(key, None)` keyed by entry identity/generation. For expiry sweeps, remove only entries still equal to the scanned generation, so a fresh prefetch is not deleted. Warm a replacement before publishing it and use a per-key single-flight lock to prevent a stampede. Clear session history by swapping a per-session state object/generation so new utterances after the clear are retained. |
| R-12 | `src/watcher/daemon.py:212-226` — supervisor/watch/ambient cancellation | P5 | Snapshot all three task handles under a lifecycle lock, cancel every task even if a preceding `cancel()` call fails, await all with `gather(return_exceptions=True)`, and retain any unfinished handle. Transition to `STOPPED` only after the set is empty. Repeated calls are idempotent and return an aggregate error if a task cannot be stopped. |

## Shared-state operations

The state matrix below maps every entry in `STATE_CLEANUP_ATOMICITY_ANALYSIS.md`
to a concrete replacement. Entries with multiple source locations share one
protocol and should share one helper rather than accumulating local variants.

### Registries and configuration caches

| ID | Location | Atomic alternative and implementation guidance |
| --- | --- | --- |
| S-01 | `src/registry.py:405-426` | P3: build `(cache, cache_at, generation)` completely, then swap that one snapshot under `_cache_lock`. Fast readers read one immutable snapshot; a failed rebuild leaves the old pair intact. |
| S-02 | `src/environment/discovery.py:349-358,375-388` | P3 plus a refresh generation: scan and validate first, then under `_registry_lock` publish registry and `_last_scan_at` together. `set_registry()` takes the same lock. On scan failure retain the old timestamp or mark it stale; never advance freshness before the awaited scan succeeds. |
| S-03 | `src/environment/discovery.py:419-429` | P5: transition to stopping, cancel and await the old refresh task, and clear its handle only after it is done. A generation token prevents an obsolete task from publishing after a replacement starts. |
| S-04 | `src/topic/model.py:343-353` | P3: construct a private registry and complete `add_common_aliases()` before publishing `_topic_registry`. Publish only once under the initialization lock; exception/cancellation discards the private object and leaves the pointer unset. |
| S-05 | `src/fetch/clusters.py:93-97` | P3: replace cache and mtime with one locked `CacheSnapshot`. If invalidation is required, swap to a single empty snapshot; readers never see mixed `None`/old-mtime state. A concurrent reload must compare generations before publishing. |
| S-05A | `src/fetch/commands.py:157-205` | P3: parse and validate locally, then publish config and mtime as one tuple under a lock. Failed parsing keeps the previous valid tuple; concurrent callers may share one single-flight load rather than overwrite one another. |
| S-06 | `src/monitoring/config_loader.py:136-140` | Use a locked immutable cache state with an invalidation generation. Do not discard the last valid config before a replacement is ready; a failed load retains it and reports stale status. Status properties read the same snapshot as the loader. |
| S-06A | `src/components/hot_reload.py:531-568` | P3: parse/validate content first, then publish content, mtime, check time, and parsed cache in one locked snapshot. A failed parse leaves all old metadata; an old reload cannot overwrite a newer generation. |
| S-07 | `src/intent/router.py:82-155` | Perform expiry selection and snapshot replacement under the cache owner lock, or use a single event-loop owner. Preserve entries added after the scan by comparing entry generations before deletion. Do not replace a map from an unlocked snapshot. |
| S-08 | `src/intent/router.py:174-179` | P3: replace a `RouterCacheState(cache, hits, misses, generation)` object under one lock. Cache writers/readers use that lock or immutable snapshot semantics, so counters and contents are reset at one publication point. |
| S-09 | `src/intent/router.py:1639-1654` | Add a router lifecycle lock and atomically swap in a fresh cache/statistics generation. In-flight classifications finish against the old router; new calls use the new pointer. Do not clear an object still used by another generation. |

### Per-session and result state

| ID | Location | Atomic alternative and implementation guidance |
| --- | --- | --- |
| S-10 | `src/context/prefetch.py:404-417` | P2/P3: under the cache lock, `pop` only when the value is the same expired object observed by the caller. A missing key or replaced fresh entry is a no-op; never perform check-then-`del` without the lock. |
| S-11 | `src/context/prefetch.py:435-455` | P3 with conditional generation filtering. Build the filtered map under the cache lock, or delete expired keys one-by-one under that lock while preserving entries created after the scan. A writer cannot be lost by a whole-map replacement. |
| S-12 | `src/context/prefetch.py:468-472` | Use a per-session lock/state object and an epoch. Clear the old history in one swap; appends carrying the new epoch remain in the new list. `pop` missing is an idempotent success. |
| S-13 | `src/diff/engine.py:254-272` | Guard cache reads/writes/expiry with one lock and attach a generation to each entry. `clear_cache(topic)` swaps/removes only the requested generation; all-topic clear swaps the entire cache object. A result captured before invalidation remains internally consistent. |
| S-14 | `src/conversation/tracker.py:270-275` | Replace the three per-session fields with one `ConversationState` and atomically swap it for an empty state under a session lock. New turns use the new generation; in-flight readers keep the old immutable state and cannot observe half-cleared context. |
| S-15 | `src/feedback/signals.py:86-95` | Use the R-10 claim/persist/finalize protocol. The timestamp remains recoverable until `_store_signal()` commits. A newer creation timestamp wins a compare-and-swap restore, preventing an old acknowledgement from restoring stale state. |
| S-16 | `src/feedback/signals.py:422-426` | Store recent utterances and surface switches in one per-session state object. Under the session lock swap to an empty state; events after the swap append only to the new object. A failed downstream analysis does not partially clear either list. |
| S-17 | `src/feedback/processor.py:187-212` | Use R-09/P6: claim by approval ID, apply the diff with an idempotency key, commit an applied/outbox record, then notify. A broadcast failure produces `APPLIED_NOT_BROADCAST`, not deletion; retries notify without reapplying the diff. |
| S-18 | `src/feedback/processor.py:234-255` | Use the same state machine for rejection. Claim once, make `reject_diff` idempotent, then finalize the approval. If rejection fails, retain `FAILED_RETRYABLE`; if it succeeds, a repeated reject returns the terminal result without another side effect. |
| S-19 | `src/monitoring/ambient.py:726-746` | P8: keep old monitor tasks registered while loading and validating the new config. Create/validate the new generation first, atomically swap the task generation, then cancel and drain old tasks. If load or task creation fails, continue the old generation; never replace the registry with a partial task list. |
| S-20 | `src/monitoring/ambient.py:705-724` | Use R-04/P5. The lifecycle state, task snapshot, and client ownership are one stop operation; cancellation, gather, and client close each run from a `finally`/aggregate-error path. Do not clear task state before the tasks are done. |
| S-20A | `src/context/warmer.py:280-289` | P5: set `STOPPING`, cancel/await the warmer task with a deadline, then clear the handle and publish `STOPPED`. If await fails, retain the handle in `FAILED_STOP` for retry; repeated stop is single-flight. |
| S-20B | `src/feedback/background_analysis.py:580-589` | Apply the same P5 lifecycle. Keep queued work and the task handle until cancellation is confirmed; use a retryable stop result rather than silently dropping analysis or allowing start to race with the old task. |
| S-21 | `src/realtime/batching.py:228-233,251-260` | P7: claim high-urgency results into an in-flight batch before awaiting narration. Ack only after narration succeeds; nack/requeue on error or cancellation. A per-session sequence prevents a pause callback and timeout callback from claiming the same item. |
| S-22A | `src/realtime/batching.py:235-249` | P7 for normal timer batches. Claim a stable list with item IDs under the batching lock, narrate outside it, and ack/nack the token. New items added during narration remain in the next batch. |
| S-23 | `src/realtime/batching.py:262-273` | Treat the idle transition and batch claim as one locked state transition. Set the session epoch, claim the existing batch, then narrate; failures requeue the claimed items under that epoch. Results arriving after the transition are not cleared accidentally. |
| S-24 | `src/realtime/batching.py:279-286` | P7 with a durable or in-memory retry queue. Do not clear both pending lists until `_narrate_now` succeeds; preserve the token when the callback fails and expose the flush failure. Shutdown can retry the batch before declaring the surface drained. |
| S-25 | `src/realtime/session.py:187-194` | Return a claim token rather than destructively clearing `pending_results`, or keep the copied batch in an in-flight map until the caller acknowledges processing. Cancellation requeues it; `push_result` uses a lock and monotonically increasing sequence. |

### Shared trackers and reset hooks

| ID | Location | Atomic alternative and implementation guidance |
| --- | --- | --- |
| S-25A | `src/telegram/state_tracker.py:24-33` | P3: put reachability, timestamp, failure count, and dedup flag in one immutable state object and replace it under `_first_failure_lock`. A failure arriving concurrently is serialized after the reset and cannot rebuild a mixed state. |
| S-26 | `src/telegram/state_tracker.py:94-100` | Use the same lock and replace the count with a compare-and-swap on the expected failure epoch. If a failure was recorded after the reset began, preserve it rather than overwriting it with zero. |
| S-27 | `src/telegram/fallback.py:547-565` | Keep the existing first-failure lock as the commit boundary for all dedup fields and the failure-type set. Build a new state, swap once, and make the reset idempotent; handlers outside the lock must use a generation token. |
| S-28 | `src/escalate/pod_input.py:173-176` | P3: replace selected pod and available-pod list with one collector snapshot under a collector lock. Confirmation reads one snapshot and checks its generation, so it cannot combine a new list with an old selection. |
| S-29 | `src/agents/self_modification.py:859-862,908-914` | Represent each pending diff as a versioned state and replace the pending collection rather than mutating it in place. Reject/apply claims one diff under a lock; bulk clear captures a cutoff generation and preserves proposals created after it. |
| S-30 | `src/utils/git_retry.py:359-408` | P3: replace all retry counters/history with one `RetryStats` object under the tracker lock. `record_attempt` and reset serialize against the same generation; a reset cannot produce counters that describe a different history list. |
| S-31 | `src/victorialogs/metrics.py:28-36` | Replace all sample collections with one immutable metrics-window object under a lock. Writers either append to the current generation or retry after reset; readers take one window snapshot for percentile calculation. |
| S-32 | `src/session/connection_monitor.py:115-120,393-400,448-451` | P8: quiesce the old monitor, prevent new tracked connections, await/close or account for existing handles, then swap a fresh monitor under the global lock. For test reset, explicitly document whether active connections are carried over; never replace the global pointer while the old monitor can still write shared stats. |
| S-32A | `src/concurrency/limit.py:87-97` | Use generation-tagged limiter leases. Stop admitting new acquisitions on the old limiter, wait for holders/waiters to drain, then publish the new semaphore. A test reset may publish a new generation immediately only if old callers retain isolated capacity and the test asserts that boundary. |
| S-33 | `src/sse/events.py:75-78` | Protect register/unregister/broadcast snapshot creation with one subscriber lock. `pop(id, None)` is the idempotent commit; a broadcast already holding a snapshot may deliver one final event, which should be the documented contract. Never mutate a snapshot while broadcasting. |
| S-34 | `src/sse/broadcaster.py:129-134,253-288` | Use the shared R-01/R-02 lock-protected claim protocol. The generator, heartbeat, broadcaster, and timeout loop all use the same registry owner and generation; stale timeout snapshots cannot delete a renewed connection. |
| S-34A | `src/sse/broadcaster.py:101-110` | Use R-07/P5. Couple `_running`, the cleanup-task handle, and lifecycle generation in one state object; stop is single-flight and does not clear the task handle until cancellation is confirmed. |

### Persistent state and caches

| ID | Location | Atomic alternative and implementation guidance |
| --- | --- | --- |
| S-35 | `src/session/store.py:871-943` | P6: keep all session/child/timing deletes in one transaction, using the routed thread ID for `dispatch_timings`; add foreign keys/cascades where appropriate. On any SQL error or cancellation before commit, roll back. Repeating deletion is safe because deletes target the same IDs. |
| S-36 | `src/session/store.py:1367-1380` | Delete the result and its card-cache rows in one transaction, preferably with a foreign key `ON DELETE CASCADE`. Renderer writes use a result/cache generation or the same per-result lock, so a render cannot recreate a stale cache after the delete commit. |
| S-37 | `src/session/store.py:1468-1512`, `src/components/library.py:514-521` | Keep the SQL delete atomic, then add cache-generation invalidation. A renderer must check the generation before publishing a newly rendered entry; a commit failure leaves the old entry and is retryable rather than falsely cleared. |
| S-38 | `src/context/warmer.py:240-245`; `src/session/store.py:1810-1827,2323-2330,2471-2484,2606-2625` | Use a P6 transaction for related rows and a worker/outbox state for the in-memory consumer. Claim a row before acting, commit the terminal status/delete, then remove the in-memory reference. If the commit fails, keep the reference and retry; concurrent workers use a conditional update/claim token. |
| S-38A | `src/session/store.py:857-869` | Make the counter reset a conditional single `UPDATE ... WHERE count = expected` in a transaction. The router passes the generation it evaluated; a concurrent increment causes a retry instead of silently losing the increment. |
| S-39 | `src/memory/store.py:152-187` | Parse and validate the persisted document into local `facts`/`data` structures first. Under the store lock swap both in-memory structures as one snapshot. Any parse/cancellation failure preserves the old in-memory snapshot and the valid disk file. |
| S-40 | `src/memory/store.py:244-255,189-203` | Build the candidate fact list with eviction in memory, persist it through P1, and swap the live in-memory list only after the file replace succeeds. On disk failure retain the old facts and retry; never pop an old fact before durable commit. |

### Test and import state

| ID | Location | Atomic alternative and implementation guidance |
| --- | --- | --- |
| S-41 | `src/test/utilities.py:221-259` | P7: claim each created ID, delete it idempotently, and remove it from bookkeeping only on confirmed success or “already absent.” Retain failed IDs for retry, aggregate failures, and make the fixture fail rather than report clean isolation when data remains. |
| S-42 | `src/test/narration.py:296-302,579-594` | Give each test session a lock/owner namespace. Pop one session idempotently under that lock, and clear only the fixture’s owned IDs; never call a global `.clear()` while another test can register. A concurrent request sees either the complete old session or no session. |
| S-43 | `src/action/__init__.py:69-77` | Keep validation sets local to the import function and clean them in `finally`; if module globals are unavoidable, delete each exact temporary name from a `finally` block. Import serialization already prevents normal task races, but an exception must not leave temporary globals behind. |

## Verification and review requirements

The implementation work following this design should add or retain tests for:

- two or more concurrent cleanup callers, including repeated calls after the
  first caller wins;
- injected failure after every claim, await, commit, replace, broadcast, and
  close step;
- cancellation and timeout with proof that unfinished work remains retryable;
- stale generation/version attempts that must not delete or overwrite newer
  state;
- process restart/reopen for files, SQLite WAL, outbox rows, and pending work;
- absence of orphaned temp files and preservation of old file contents after a
  failed replacement;
- shutdown error aggregation and truthful terminal-state logging.

### Review record

This design was self-reviewed against the acceptance criteria on 2026-08-09:

- every file, resource, and state catalogue entry has a mapped alternative;
- each mapping names a pattern and a commit/linearization point;
- partial failures, cancellation, retries, and concurrent access are addressed;
- the design explicitly avoids claiming that external I/O is rollback-able;
- duplicate catalogue coverage (S-34/R-01/R-02 and S-34A/R-07) is directed to
  one shared implementation protocol.

**Decision:** approved as the implementation baseline for the downstream
atomic-cleanup implementation bead, subject to normal code review of the
resulting changes and tests.
