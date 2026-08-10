# State Cleanup Operations: Atomicity and Failure-Risk Catalog

**Analysis date:** 2026-08-09
**Scope:** State cleanup and state replacement paths in `src/`, including global
registries, in-memory caches, per-session state, pending work, and
session-persistent cache/state tables.

## Method and atomicity model

Child 1 (`adc-qkz2qm`) reported the state category as global variables, caches,
registries, and shared state. Its discovery notes did not retain a path-by-path
state list, so the state search was reproduced against the current tree using
cache/registry/state names, `clear`, `pop`, `del`, reset/invalidate methods,
pending/history containers, and task registries. Resource-only closes and file
deletion are covered by the sibling resource/file reports; entries below are
included when the cleanup also mutates a shared state structure.

“Atomic” here means that callers cannot observe a partially applied logical
operation. A single Python `dict.clear()`, assignment, or SQL `DELETE` is an
individual operation, but it is not automatically atomic with the other state
updates or with an awaited external action. Synchronous code is effectively
non-interleavable on one asyncio event loop; the unprotected paths remain unsafe
if called from multiple threads or if their surrounding operation is expanded
to include an `await`.

## Risk summary

| Risk | Main consequence |
| --- | --- |
| High | A failed or concurrent cleanup can leave a global registry, monitor set, or user-visible pending work in a misleading state, or lose state before durable work succeeds. |
| Medium | Partial session state, stale cache entries, duplicate work, or test isolation failures are possible; recovery usually occurs on the next refresh/retry. |
| Low | The mutation is a single operation or protected by a lock/transaction, but callers can still observe stale state or the operation is not safe across threads. |

## Catalog

### Global registries and configuration caches

#### S-01 — YAML project registry cache refresh

- **Location:** `src/registry.py:405-426`
- **Pattern:** The stale check is performed lock-free; under `_cache_lock`, `_cache` is replaced at line 425 and `_cache_at` is assigned separately at line 426. The two values are therefore not one published snapshot.
- **Risk:** Medium.
- **Failure modes:** A concurrent fast-path reader can return the old cache while a forced rebuild is in progress, or see the new cache with the old timestamp. A rebuild exception leaves the old cache, but no explicit invalidation/rollback state is recorded.
- **Midway impact:** Readers can perform redundant rebuilds or use a registry/cache-age pair that does not describe the same version. The lock protects the slow path, but not the fast-path read.

#### S-02 — Environment registry replacement/refresh

- **Locations:** `src/environment/discovery.py:349-358` and `src/environment/discovery.py:375-388`
- **Pattern:** `set_registry()` replaces the global pointer without taking `_registry_lock`; `refresh_registry()` updates `_last_scan_at` before the awaited `scan_environment()` call and replaces `_registry` only after the scan succeeds.
- **Risk:** High.
- **Failure modes:** An unsynchronized startup/test replacement can race with a reader or refresh. Scan failure, timeout, or cancellation after line 384 leaves the old registry paired with a new “last scanned” timestamp. A caller can also read the lock-free registry while a refresh is in progress.
- **Midway impact:** Health/routing consumers believe fresh environment data exists when the registry is stale, so an old project/cluster mapping can be used without an obvious stale marker.

#### S-03 — Background environment refresh stop

- **Location:** `src/environment/discovery.py:419-429`
- **Pattern:** `Task.cancel()` is followed immediately by `_background_refresh_task = None`; the cancelled task is not awaited.
- **Risk:** Medium.
- **Failure modes:** Cancellation is delayed or suppressed while the task is inside a scan. A subsequent `start_background_refresh()` can create a replacement task while the old task is still able to publish a registry update.
- **Midway impact:** Duplicate refresh loops, updates after shutdown, or a registry write from an obsolete task can survive the intended cleanup.

#### S-04 — Global topic registry initialization

- **Location:** `src/topic/model.py:343-353`
- **Pattern:** `_topic_registry` is assigned before the awaited `add_common_aliases()` batch completes.
- **Risk:** High.
- **Failure modes:** Cancellation or an exception while registering aliases leaves a non-`None` registry with no or only some aliases. Later callers skip initialization because the global pointer is already set.
- **Midway impact:** Alias resolution silently fails or returns incomplete results for the rest of the process. The outer lock serializes initialization but does not roll back the pointer.

#### S-05 — Cluster endpoint cache reset

- **Location:** `src/fetch/clusters.py:93-97`
- **Pattern:** `_cache` and `_cache_mtime` are cleared in two assignments without a lock.
- **Risk:** Medium.
- **Failure modes:** A concurrent reader can observe `None` with the old mtime, or the old cache with a `None` mtime. A concurrent reload can then repopulate one field based on a different file version.
- **Midway impact:** Unnecessary reloads, stale endpoint resolution, or a test/application caller receiving a mixed cache state. The hook is mostly used by tests, which lowers operational likelihood.

#### S-05A — Fetch-command configuration cache refresh

- **Location:** `src/fetch/commands.py:157-205`
- **Pattern:** The cache and mtime are read lock-free; after parse/validation, `_fetch_config_cache` and `_fetch_config_mtime` are published in separate assignments.
- **Risk:** Medium.
- **Failure modes:** Concurrent callers can perform duplicate reloads or observe a cache/mtime pair from different file versions. A parse/validation error is raised before publication, which preserves the old cache but does not coordinate readers.
- **Midway impact:** Fetch timeouts can be selected from stale or mismatched configuration until a later reload.

#### S-06 — Monitoring configuration cache invalidation

- **Location:** `src/monitoring/config_loader.py:136-140`
- **Pattern:** `_cache` is set to `None` under `self._lock`, while `is_cached()` and `cache_age_seconds` read it without that lock.
- **Risk:** Low.
- **Failure modes:** A lock-free status reader can report the prior cache during invalidation. If the next reload fails, the previous valid configuration has already been discarded.
- **Midway impact:** A transient “not cached” state or repeated file load; a failed reload propagates to the caller rather than restoring the old configuration. The invalidation itself is protected for normal asyncio callers.

#### S-06A — Hot-reload artifact/cache replacement

- **Location:** `src/components/hot_reload.py:531-568`
- **Pattern:** `force_reload()` updates the artifact content, mtime, and last-check timestamp before parsing and replacing `_cache[name]`.
- **Risk:** Medium.
- **Failure modes:** A parse failure after the artifact metadata update leaves new metadata paired with old parsed content; a concurrent reader can observe the pair during replacement because the method does not hold the manager’s `RLock`.
- **Midway impact:** `get_mtime()` can report a new artifact while `get_config()` returns the old value, or later change detection can be suppressed until another edit.

#### S-07 — Intent cache expiry sweep

- **Location:** `src/intent/router.py:82-155`
- **Pattern:** Expired keys are collected and then `_cache` is replaced by a dict comprehension. The code documents this as atomic, but no lock protects it from thread access or concurrent cache writers.
- **Risk:** Low.
- **Failure modes:** A thread can mutate the dictionary while it is being iterated, or a concurrent write can be lost when the replacement dictionary is published. On one asyncio loop there is no `await` in the sweep, so tasks do not interleave during the rebuild.
- **Midway impact:** A `RuntimeError`, lost newly cached classification, or retained expired entries; the next request can rebuild the cache again.

#### S-08 — Intent cache clear and statistics reset

- **Location:** `src/intent/router.py:174-179`
- **Pattern:** `_cache.clear()`, `_cache_hits = 0`, and `_cache_misses = 0` are separate mutations with no lock.
- **Risk:** Medium.
- **Failure modes:** A concurrent request can add a hit/miss between the clear and counter resets, or read an empty cache with old statistics. Threaded tests/callers can race on the dictionary.
- **Midway impact:** Incorrect hit-rate telemetry and classifications repopulating a cache whose counters no longer describe its contents.

#### S-09 — Public global router-cache reset

- **Location:** `src/intent/router.py:1639-1654`
- **Pattern:** The global router pointer is read, then its cache is cleared without coordinating with classification calls.
- **Risk:** Medium.
- **Failure modes:** A classification can be using an entry while the test/reset hook clears the same cache, or another thread can replace/use `_router` between the check and mutation.
- **Midway impact:** Nondeterministic cache misses and reset statistics; a test may not actually isolate itself from a request already in flight.

### In-memory per-session and result state

#### S-10 — Expired speculative-prefetch entry

- **Location:** `src/context/prefetch.py:404-417`
- **Pattern:** `cache_key in _cache` is checked, validity is evaluated, and the key is deleted as separate operations.
- **Risk:** Low.
- **Failure modes:** A thread can remove or replace the key between the check and `del`; the object can also be replaced after validity was checked.
- **Midway impact:** `KeyError`, a stale value being returned, or a fresh replacement being deleted. The no-`await` code is safe against normal same-loop task interleaving.

#### S-11 — Speculative-prefetch expiry sweep

- **Location:** `src/context/prefetch.py:435-455`
- **Pattern:** Expired keys are identified, then `_cache` is replaced with a filtered dictionary. No lock coordinates this replacement with prefetch writers.
- **Risk:** Medium.
- **Failure modes:** A concurrent writer’s newly completed entry can disappear from the replacement dictionary; a threaded reader can iterate the old dictionary while it is being replaced.
- **Midway impact:** Lost prefetch results and avoidable refetches. The replacement is all-at-once for same-loop callers, so the main exposure is cross-thread use or future awaits added to the routine.

#### S-12 — Speculative-prefetch session history clear

- **Location:** `src/context/prefetch.py:468-472`
- **Pattern:** The session key is checked and then deleted from `_recent_utterances` without a lock.
- **Risk:** Medium.
- **Failure modes:** A concurrent utterance append can race with the delete; a concurrent delete can make the checked key disappear before `del`.
- **Midway impact:** History from a newly received utterance can be lost, or cleanup can raise and leave the caller believing the session was cleared.

#### S-13 — Diff cache expiration and clear

- **Location:** `src/diff/engine.py:254-272`
- **Pattern:** Expired entries use `del`; `clear_cache(topic_id)` uses `pop`, and the all-topics form uses `clear`. None is synchronized with cache reads/writes.
- **Risk:** Medium.
- **Failure modes:** A concurrent update can be removed by an expiration/clear operation, or a read can obtain a result immediately before it is invalidated. Cross-thread calls can raise during the check/delete sequence.
- **Midway impact:** Stale or missing “previous result” context, causing an incorrect diff or an unnecessary full comparison.

#### S-14 — Conversation session clear

- **Location:** `src/conversation/tracker.py:270-275`
- **Pattern:** `_focus`, `_history`, and `_recent_topics` are popped one at a time with no transaction or lock.
- **Risk:** Medium.
- **Failure modes:** An exception or concurrent update between pops leaves only some session state removed; a new turn can be appended while the old session is being cleared.
- **Midway impact:** Cross-session context leakage or a session that has history but no focus (or vice versa), producing wrong disambiguation.

#### S-15 — Feedback acknowledgement tracking removal

- **Location:** `src/feedback/signals.py:86-95`
- **Pattern:** The result creation timestamp is deleted before the awaited `_store_signal()` persistence operation.
- **Risk:** Medium.
- **Failure modes:** Database failure, cancellation, or timeout after line 95 prevents the signal from being persisted, and a retry sees no timestamp. Duplicate acknowledgements can race with the check when callers are threaded.
- **Midway impact:** Acknowledgement-latency data is permanently lost and cannot be retried from the in-memory tracker.

#### S-16 — Feedback session tracking clear

- **Location:** `src/feedback/signals.py:422-426`
- **Pattern:** Recent utterances and surface-switch lists are removed by two independent `pop` calls.
- **Risk:** Medium.
- **Failure modes:** A concurrent event can repopulate one structure after it was cleared, or a thread can observe one list missing and the other present.
- **Midway impact:** Partial feedback history and inconsistent background-analysis input for that session.

#### S-17 — Approved feedback change removal

- **Location:** `src/feedback/processor.py:187-212`
- **Pattern:** The diff is applied externally, then removed from `_pending_approvals`, then an awaited SSE broadcast is attempted. There is no lock, idempotency claim, or compensation path.
- **Risk:** High.
- **Failure modes:** Two approvals can both apply the same diff and race on `del`; a broadcast failure occurs after the pending item is removed; a cancellation leaves the artifact changed but the UI unaware.
- **Midway impact:** Duplicate self-modification, an approval that cannot be retried, or a permanently stale approval card/UI state.

#### S-18 — Rejected feedback change removal

- **Location:** `src/feedback/processor.py:234-255`
- **Pattern:** `reject_diff()` runs before `_pending_approvals[approval_id]` is deleted; the two operations are not one transaction.
- **Risk:** Medium.
- **Failure modes:** Rejection raises and leaves the approval pending, or concurrent rejects both invoke the external rejection and the second delete raises `KeyError`.
- **Midway impact:** Rejected work can be presented as still actionable, or a rejection request fails after the underlying diff was already rejected.

#### S-19 — Ambient monitor configuration reload

- **Location:** `src/monitoring/ambient.py:726-746`
- **Pattern:** `self.tasks` is replaced with only the ticker before old monitor tasks finish; old tasks are cancelled/gathered, then new tasks are appended after an awaited config load.
- **Risk:** High.
- **Failure modes:** `load_config()` fails or is cancelled after old tasks were removed from the registry; a task can finish/cancel between snapshot and gather; a newly created task can be appended while another reload is running.
- **Midway impact:** Monitoring silently stops with no task handles to restart it, or old and new monitor tasks overlap and emit duplicate state changes.

#### S-20 — Ambient monitor stop state cleanup

- **Location:** `src/monitoring/ambient.py:705-724`
- **Pattern:** `running` is set false, tasks are cancelled, `gather()` is awaited, then `tasks.clear()` and `_ticker_task = None` run before the HTTP client close completes.
- **Risk:** High.
- **Failure modes:** A task/client cancellation or close failure interrupts the sequence; the state list can be cleared while a task still has work, and an exception prevents the final cleanup.
- **Midway impact:** The service reports stopped while background tasks or the HTTP client remain active. This overlaps the resource risk documented in `RESOURCE_CLEANUP_ATOMICITY_ANALYSIS.md`.

#### S-20A — Context-warmer stop state cleanup

- **Location:** `src/context/warmer.py:280-289`
- **Pattern:** `running` is set false, the task is cancelled/awaited, but the task reference is not cleared and there is no compensation if the await fails.
- **Risk:** Medium.
- **Failure modes:** Cancellation can be delayed or raise a non-`CancelledError`; a later `start()` sees a done task and replaces it, while callers can still hold the old reference.
- **Midway impact:** Shutdown can report success while the warmer task remains active or startup can retain confusing stale task state.

#### S-20B — Background-analysis processor stop state cleanup

- **Location:** `src/feedback/background_analysis.py:580-589`
- **Pattern:** `running` is cleared and the task is cancelled/awaited in sequence, with no task-reference reset or retry state.
- **Risk:** Medium.
- **Failure modes:** A cancellation/await failure interrupts the stop path; a repeated stop/start can race on the same task handle.
- **Midway impact:** Background analysis may continue after shutdown or fail to restart cleanly, and queued feedback work can be processed twice or not at all.

#### S-21 — High-urgency batch drain

- **Locations:** `src/realtime/batching.py:228-233` and `src/realtime/batching.py:251-260`
- **Pattern:** The timeout path removes one item from `_waiting_for_pause` before awaiting narration; the pause-signal path copies the list and clears it before the awaited narration callback.
- **Risk:** Medium.
- **Failure modes:** Callback failure/cancellation after removal/clear loses the pending results; a concurrent queue operation can add or remove entries while the copy is being drained.
- **Midway impact:** A result waiting for a natural pause is not narrated and is no longer available for retry.

#### S-22A — Normal batch timer removal

- **Location:** `src/realtime/batching.py:235-249`
- **Pattern:** Ready items are removed one by one from `_pending` before `_narrate_now(ready)` awaits the narration callback.
- **Risk:** Medium.
- **Failure modes:** A callback failure after removal drops the batch; a second timer or flush can race with the membership check and alter the set of items narrated.
- **Midway impact:** Normal-urgency results can disappear from the queue without being narrated.

#### S-23 — Idle batch drain

- **Location:** `src/realtime/batching.py:262-273`
- **Pattern:** `_session_active` is changed and `_pending` is copied/cleared before `_narrate_now()` awaits the callback.
- **Risk:** Medium.
- **Failure modes:** Callback failure loses the copied batch. A result queued around the state transition can be narrated in the wrong batch or remain pending unexpectedly.
- **Midway impact:** User-visible low/normal notifications can be dropped during an idle transition.

#### S-24 — Explicit batch flush

- **Location:** `src/realtime/batching.py:279-286`
- **Pattern:** Both pending lists are combined, then cleared before awaited narration; the callback error is logged and swallowed by `_narrate_now()`.
- **Risk:** High.
- **Failure modes:** Narration failure after the clear is non-retryable; concurrent timer tasks may also remove an item while the flush is building its combined list.
- **Midway impact:** A shutdown or surface transition can permanently drop all queued narration results.

#### S-25 — Realtime session catch-up drain

- **Location:** `src/realtime/session.py:187-194`
- **Pattern:** `pending_results` is copied and cleared before the caller processes the returned list.
- **Risk:** Medium.
- **Failure modes:** Caller cancellation/crash after return loses the catch-up batch; the list is not protected from threaded `push_result()` calls.
- **Midway impact:** A canvas surface switch can miss results that were pending for it. Same-loop execution is non-interleavable because there is no await in the drain itself.

### Shared trackers and reset hooks

#### S-25A — Telegram bridge reachable reset

- **Location:** `src/telegram/state_tracker.py:24-33`
- **Pattern:** Reachability, timestamp, failure count, and dedup flag are reset in four assignments without a lock.
- **Risk:** Medium.
- **Failure modes:** A concurrent failure update can overwrite one field after the reset, producing a reachable state with a failure timestamp/count or an incorrect dedup flag.
- **Midway impact:** First-failure alerts are suppressed or repeated incorrectly. The methods are synchronous and safe from same-loop task interleaving, but not from threaded access.

#### S-26 — Telegram failure-count reset

- **Location:** `src/telegram/state_tracker.py:94-100`
- **Pattern:** The failure counter is reset independently of reachability and last-failure timestamp.
- **Risk:** Low.
- **Failure modes:** A concurrent failure increment can be lost, leaving a lower count than the actual streak; other state fields intentionally remain unchanged.
- **Midway impact:** Monitoring reports an inaccurate consecutive-failure count, but reachability state is not otherwise corrupted.

#### S-27 — Telegram first-failure re-arm

- **Location:** `src/telegram/fallback.py:547-565`
- **Pattern:** Several dedup fields and the failure-type set are reset as one logical operation.
- **Risk:** Low.
- **Failure modes:** A failure handler not using `_first_failure_lock` could observe a partial reset; current first-failure update paths use the same lock, so normal asyncio use is serialized.
- **Midway impact:** At worst, one failure is logged using the old/new dedup window. This is the best-protected reset in the catalog, not a high-risk non-atomic path.

#### S-28 — Pod input collector reset

- **Location:** `src/escalate/pod_input.py:173-176`
- **Pattern:** `_selected_pod` is cleared and `_available_pods` is replaced separately, with no lock around the global collector.
- **Risk:** Medium.
- **Failure modes:** A concurrent prompt can read a new pod list with an old selection or vice versa; a selection can be lost during reset.
- **Midway impact:** A deletion confirmation can target no pod or a selection from a previous interaction.

#### S-29 — Pending self-modification diffs clear/reject

- **Locations:** `src/agents/self_modification.py:859-862` and `src/agents/self_modification.py:908-914`
- **Pattern:** A rejected diff is removed with `list.remove()` and the bulk hook clears `_pending_diffs` in place; neither operation is coordinated with diff creation/approval.
- **Risk:** Medium.
- **Failure modes:** A newly proposed diff can be cleared, or a reader can hold a list snapshot that no longer corresponds to the agent’s pending set. A concurrent reject can remove a diff between the membership test and `remove()`.
- **Midway impact:** Pending approvals disappear from the in-memory queue and cannot be applied unless recreated from the originating request.

#### S-30 — Global retry statistics reset

- **Location:** `src/utils/git_retry.py:359-408`
- **Pattern:** Five counters/history fields are reset by separate assignments on the global `RetryTracker`.
- **Risk:** Medium.
- **Failure modes:** A concurrent `record_attempt()` can increment an old counter while the history is replaced, producing counters that do not match the history.
- **Midway impact:** Reliability metrics and retry diagnostics become internally inconsistent; the underlying git operation is not rolled back.

#### S-31 — Latency metrics calculator reset

- **Location:** `src/victorialogs/metrics.py:28-36`
- **Pattern:** Three sample collections are replaced separately.
- **Risk:** Medium.
- **Failure modes:** A concurrent `add_value()` can append to one old list while another list has already been replaced; a reader can observe mismatched sample lengths.
- **Midway impact:** Percentiles and error reports can be calculated from different measurement windows.

#### S-32 — Connection monitor state reset

- **Locations:** `src/session/connection_monitor.py:115-120`, `src/session/connection_monitor.py:393-400`, and `src/session/connection_monitor.py:448-451`
- **Pattern:** The counter reset uses five assignments; the monitor reset then clears connections, replaces stats, resets the counter/history/alert flag under a different lock boundary; the global reset replaces the monitor pointer without stopping or awaiting the old monitor.
- **Risk:** Low.
- **Failure modes:** A caller that acquired a connection before reset can be omitted from the new stats; a future change that raises between mutations could leave a partial reset. The current lock makes normal asyncio access serialized.
- **Midway impact:** Test baselines can be wrong, old weak references can retain stale monitoring metadata, and an old monitor can continue recording after the global pointer has changed. Active application connections are not closed by this test reset.

#### S-32A — Global concurrency-limiter replacement

- **Location:** `src/concurrency/limit.py:87-97`
- **Pattern:** The global `_limiter` pointer is replaced with a new semaphore without draining or coordinating users of the old limiter.
- **Risk:** Medium.
- **Failure modes:** In-flight callers retain the old semaphore while new callers use the new one; a reset during a wait can split the intended concurrency budget.
- **Midway impact:** More than the configured number of operations can run, or a waiter can remain attached to an obsolete limiter. The hook is primarily test-facing.

#### S-33 — SSE subscriber registry removal

- **Location:** `src/sse/events.py:75-78`
- **Pattern:** `pop(sub_id, None)` mutates the shared subscriber registry without a lock; broadcasting separately snapshots the values.
- **Risk:** Low.
- **Failure modes:** Cross-thread register/unregister/broadcast races; a broadcast snapshot can still contain a queue just removed.
- **Midway impact:** One extra event may be delivered, or a subscriber registration can be lost. The idempotent single `pop` is safe for same-loop async callers.

#### S-34 — SSE broadcaster connection registry cleanup (cross-catalog)

- **Locations:** `src/sse/broadcaster.py:129-134` and `src/sse/broadcaster.py:253-288`
- **Pattern:** Unregister uses a membership test, reference read, and dictionary deletion as separate unprotected operations. The cleanup loop builds a dead-connection snapshot, attempts a queue write, and then unregisters later; the snapshot, queue write, and deletion are not one transaction.
- **Risk:** High.
- **Failure modes:** Concurrent cleanup can delete the connection between the test and `del`, raising `KeyError`; a stale snapshot can refer to an already removed connection; queue-full/error paths can prevent unregister; an exception in an SSE `finally` block can suppress the original cancellation/error.
- **Midway impact:** The event-generator task can terminate with a stale connection entry or an uncompleted SSE response, and dead connections can remain in the shared registry. This is also catalogued in the resource-cleanup report because the registry owns live connection state.

#### S-34A — SSE broadcaster stop state transition

- **Location:** `src/sse/broadcaster.py:101-110`
- **Pattern:** `_running` is set false before the cleanup task is cancelled and awaited; the task handle is not atomically retired with the state transition.
- **Risk:** Medium.
- **Failure modes:** A stop caller can race with start/broadcast, or cancellation/await can fail after the broadcaster has advertised itself as stopped.
- **Midway impact:** Dead-connection cleanup can stop while connections remain registered, or a later start can reuse a task that is already cancelling.

### Persistent session state and caches

#### S-35 — Session deletion transaction

- **Location:** `src/session/store.py:871-943`
- **Pattern:** Multiple child/parent `DELETE` statements are issued sequentially and committed once at line 941. This is transactionally atomic for SQLite errors, but the cleanup is logically incomplete for `dispatch_timings` rows keyed by the routed thread ID rather than the store intent ID.
- **Risk:** Medium.
- **Failure modes:** A database error before commit rolls back the batch; a successful commit can still leave unmatched timing rows. Cancellation/connection failure after a statement and before commit relies on SQLite rollback on connection close.
- **Midway impact:** Normally no partial deletion is visible, but orphaned timing rows can survive a supposedly complete session teardown and contaminate later metrics.

#### S-36 — Result deletion versus card-cache state

- **Location:** `src/session/store.py:1367-1380`
- **Pattern:** The result row is deleted and committed as one SQL statement, but `card_cache` is not deleted in the same operation and has no result foreign key in the schema.
- **Risk:** Medium.
- **Failure modes:** Result deletion succeeds while cached HTML remains; a later cache lookup can return data for a nonexistent result. If a future second cleanup is added, failure between the two commits would reproduce the same split state.
- **Midway impact:** Stale rendered cards and cache growth; a result can appear deleted in the database while its presentation remains available through cache paths.

#### S-37 — Card-cache invalidation operations

- **Location:** `src/session/store.py:1468-1512` and `src/components/library.py:514-521`
- **Pattern:** Each implementation executes a `DELETE` and commits it, but invalidation is not coordinated with a renderer that may read/write a cache entry between lookup and deletion.
- **Risk:** Low.
- **Failure modes:** A concurrent render can recreate an entry after invalidation, or a caller can use a cache row read before invalidation. A commit error leaves the old cache intact.
- **Midway impact:** Stale HTML is served until the next invalidation/expiry. The individual SQL delete is atomic and has no partial-row state.

#### S-38 — Topic-context, approval, confirmation, and bead-watch cleanup

- **Locations:** `src/context/warmer.py:240-245`, `src/session/store.py:1810-1827`, `src/session/store.py:2323-2330`, `src/session/store.py:2471-2484`, and `src/session/store.py:2606-2625`
- **Pattern:** Each method performs one `DELETE` or one status `UPDATE` followed by `commit()`; cleanup is not part of a larger transaction with the in-memory monitor/worker state that consumes it.
- **Risk:** Low for database atomicity; Medium for cross-layer consistency.
- **Failure modes:** Database commit failure leaves the row unchanged. A worker can remove an in-memory reference or act on a fetched row before the database cleanup commits; another worker can race with expiration.
- **Midway impact:** A stale approval/watch/context row can be retried or reported once more, or an expired context can be briefly reused. No partial SQL row is exposed.

#### S-38A — Session reformulation-count reset

- **Location:** `src/session/store.py:857-869`
- **Pattern:** A session’s persisted counter is reset with one `UPDATE` and commit, but the in-memory/router decision that triggered the reset is not part of the same transaction.
- **Risk:** Low.
- **Failure modes:** Commit failure leaves the prior count; a concurrent reformulation can increment based on the old value after the reset.
- **Midway impact:** A session can be allowed or denied reformulation based on a stale count. The SQL statement itself is atomic.

#### S-39 — Memory-store reload reconstruction

- **Location:** `src/memory/store.py:152-187`
- **Pattern:** `_facts` is cleared before the persisted facts are parsed and appended; `_data` is also repaired in place before reconstruction completes.
- **Risk:** Medium.
- **Failure modes:** Unexpected parsing/conversion failure, cancellation in a threaded caller, or concurrent reads can expose an empty/partially reconstructed fact list. The old in-memory snapshot is not retained for rollback.
- **Midway impact:** Conversation memory temporarily or permanently loses facts even though the on-disk file is still valid.

#### S-40 — Memory-store capacity eviction before persistence

- **Location:** `src/memory/store.py:244-255` (eviction) and `src/memory/store.py:189-203` (save)
- **Pattern:** The oldest fact is popped from memory before the subsequent atomic file save succeeds.
- **Risk:** Medium.
- **Failure modes:** Disk-full/permission failure leaves memory with the fact removed while disk retains it; a later save can persist the reduced list and make the loss durable.
- **Midway impact:** The oldest user fact can disappear from the durable memory store despite the attempted add failing.

### Test-only and import-time state cleanup

These are not production cleanup paths, but child 1’s whole-codebase search found
them and they can affect isolation.

#### S-41 — Test session cleanup loop and bookkeeping reset

- **Location:** `src/test/utilities.py:221-259`
- **Pattern:** Each session is deleted in a loop, per-item failures are logged and ignored, then the created-ID sets are cleared unconditionally.
- **Risk:** Medium (test-only).
- **Failure modes:** A failed API deletion is followed by local bookkeeping deletion; a later test cannot retry the failed cleanup.
- **Midway impact:** Test data leaks across runs while the helper reports cleanup complete, causing flaky isolation and misleading verification.

#### S-42 — Narration test-session registry cleanup

- **Locations:** `src/test/narration.py:296-302` and `src/test/narration.py:579-594`
- **Pattern:** A shared dictionary is modified with `del` or `.clear()` without a lock.
- **Risk:** Medium (test-only).
- **Failure modes:** Concurrent test requests can delete a session while it is being read or clear sessions created by another test.
- **Midway impact:** Test sessions disappear unexpectedly, or stale session objects survive a partial cleanup.

#### S-43 — Import-time namespace cleanup

- **Location:** `src/action/__init__.py:69-77`
- **Pattern:** Temporary validation sets are created, checked, and deleted from module globals in two `del` targets.
- **Risk:** Low.
- **Failure modes:** Import failure before deletion leaves temporary globals; another import cannot observe a partially executed module reliably because Python import serialization applies.
- **Midway impact:** Only module namespace pollution or an import error; no application state or durable data is lost.

## Priority recommendations

1. Publish registry replacements only after the complete new value is built. For
   the environment/topic registries, keep the old pointer and timestamp until
   every awaited initialization step succeeds.
2. Add an ownership lock or an explicit state machine around ambient reload/stop,
   and retain task handles until cancellation and client close have completed.
3. Make pending approval and pending-result transitions idempotent: persist or
   mark completion, perform the external action, and only then remove state, or
   retain a retryable “completed-but-not-broadcast” record.
4. Protect shared in-memory clear/reset paths with the same lock used by their
   writers, or document and enforce single-event-loop ownership.
5. Keep session cache deletion in the same transaction as result deletion, or
   add the missing foreign-key/cascade relationship and test the teardown
   invariant.
6. Test cleanup helpers should clear local bookkeeping only for successfully
   deleted records; retain failures for retry and report the helper as failed.

## Verification notes

The catalog was checked against the current source with `rg` searches for
`clear`, `invalidate`, `reset`, `cleanup`, `pop`, `del`, cache/registry names,
and global shared-state declarations. Line numbers refer to the worktree at
analysis time. No source or test behavior was changed by this task.
