# Cleanup Operations Reference

This guide is the implementation reference for temporary-file, backup, and
state cleanup in aide-de-camp. It describes the invariant each operation
protects and the failure behavior that tests must preserve.

## Core invariants

1. A published file is either the previous complete generation or the new
   complete generation. No reader may observe a partially written file.
2. A cleanup owner claims a path before deleting it when another process could
   also select it. Claims use a same-directory atomic rename to a unique
   quarantine name.
3. Cleanup is idempotent. A path removed by a competing owner is already in the
   desired final state and must not turn a successful cleanup into an error.
4. A failed staging cleanup is observable in logs/results and must not mask the
   original write or publication error.
5. Temporary names are unique and scoped to the target directory. Cleanup must
   not use a fixed probe name or delete a path after an `exists()` check that
   can become stale.

## Pattern catalog

### Atomic writes and backups

`src/utils/atomic_write.py` is the central file-publication utility.

`atomic_write()` follows this transaction:

```text
validate content
  -> create unique staging file beside target
  -> write, fsync, and verify staging content
  -> os.replace(staging, target)       [publication commit point]
  -> best-effort idempotent staging/orphan cleanup
```

The staging file is created with `tempfile.mkstemp()` in the target directory,
so `os.replace()` stays on one filesystem. A per-path process-local re-entrant
lock serializes same-process writers. The old target remains untouched until
the replace succeeds. A failed write removes the staging path with
`unlink(missing_ok=True)` without replacing the original exception.

When `create_backup=True`, `_atomic_backup()` copies the source into a unique
staging backup beside the final `.bak` path, then publishes that backup with
`os.replace()`. A failed copy or backup publication removes only its staging
file; an existing backup and the source remain unchanged.

`atomic_write_rollback()` uses the same staging and replace pattern for callers
that need to perform work inside a context manager. Its per-path lock spans
the caller's block and the final replace, which prevents two read/modify/write
transactions from publishing stale snapshots out of order. An exception in
the block or at publication removes the staging path and preserves the target.

### Orphaned temporary files

`cleanup_orphaned_temp_files()` is for startup or recovery sweeps. It first
validates that the requested path is a directory, snapshots only the caller's
glob, and unlinks each matching file with `missing_ok=True`. A concurrent owner
winning the race is success for the filesystem post-condition (the file is
absent). Permission and other OS errors are collected in the detailed result;
`raise_on_failure=True` escalates them after the sweep.

The sweep is deliberately scoped: callers must pass the specific directory and
pattern they own. It does not recursively scan an arbitrary system temporary
directory.

### Atomic append

`atomic_append()` protects append-only records such as
`src/confirmations/confirmed_deletions.py`.

The per-path lock serializes the read/merge/publish transaction. The new record
is staged first; for an existing target the complete old-plus-new snapshot is
published through `_atomic_write_impl()`. For a new target the stage is
published with `os.replace()`. The staging file is cleaned only after
publication, so a cleanup failure cannot cause the append to be retried and
duplicate the record.

### Deployment persistence and backup retention

The deployment persistence paths use the core utility for final JSON files:

- `src/persistence/deployment_persistence.py` stages `.tmp_backup` files in the
  target directory and renames them into place. Error cleanup is idempotent
  unlinking and logs cleanup failures without masking the original operation.
- `persist_whisper_stt_deployment.py` stages backup copies and publishes them
  with `Path.replace()`. Retention cleanup first renames an old backup to a
  unique `.deleting_*.tmp` quarantine. That rename is the claim point. If the
  subsequent unlink fails, the quarantine is restored to the original backup
  name, preventing both silent data loss and hidden temporary-file leaks.

### Freeze sentinel

`src/freeze.py` guards the sentinel transition with `_freeze_lock`.
Creating `data/FREEZE` uses `atomic_write()`. Removing it is a single-file
`unlink(missing_ok=True)`: unlink is the atomic filesystem operation, and the
missing-file case is already the desired unfrozen state. Permission failures
are raised so the observable frozen state is not falsely reported as cleared.

### Git validation cleanup

`src/action/steps/git_validation.py` has two cleanup families:

- `check_file_permissions()` creates a unique `.write_test_temp-*.tmp` probe
  with `mkstemp()`, closes it, and removes it idempotently. The unique name
  prevents one validator from deleting another validator's probe.
- `check_and_clean_git_locks()` atomically renames each known Git state path to
  a unique `.adc-cleanup-*` quarantine before deleting it. A concurrent owner
  that removed the original path is harmless. A rebase quarantine is a
  directory; recursive deletion is not itself atomic, but the atomic rename
  gives this operation exclusive ownership and prevents a new Git state path
  from being recursively deleted.

## What is intentionally not a filesystem transaction

Not every operation named “cleanup” deletes a file:

- SSE connections, prefetch entries, queues, and pending diffs are in-memory
  collections. They use locks, snapshots, or replacement/rebuild patterns to
  avoid mutating a collection while it is being iterated.
- Session and SQLite cleanup is governed by database transactions and foreign
  keys, not filesystem rename semantics.
- `pytest`'s `tmp_path` and `TemporaryDirectory` own their test directories.
  Tests should use those fixtures rather than creating persistent temporary
  paths. Any manually-created fixture file must be uniquely owned and removed
  in `finally`/fixture teardown.

These are different atomicity domains and should not be “fixed” by adding
filesystem renames around in-memory or database state.

## Review checklist

For a new cleanup path, confirm:

- Is the target a file, a directory tree, an in-memory collection, or a
  database record? Choose the matching transaction model.
- For file publication, is the staging file unique, in the target directory,
  fully written/validated, and published with `os.replace()`/`Path.replace()`?
- For deletion under concurrency, is the exact path claimed before deletion?
- Does cleanup use `missing_ok=True` (or handle `FileNotFoundError`) without an
  `exists()` check immediately before unlink?
- If deletion fails after a quarantine rename, is the original path restored or
  is the unrecoverable quarantine surfaced explicitly?
- Does every failure path close descriptors and leave no operation-owned
  staging file?
- Are tests asserting both the preserved/published target and the absence of
  operation-owned temporary files?

## Verification commands

Run the focused cleanup suite:

```bash
pytest -q \
  tests/test_atomic_write.py \
  tests/test_atomic_cleanup_operations.py \
  tests/test_cleanup_edge_cases.py \
  tests/test_deployment_backup_cleanup.py \
  tests/validation/test_git_validation.py
```

After any test run, inspect for repository-owned staging patterns:

```bash
find . -path './.git' -prune -o -path './.beads' -prune -o \
  -type f \( -name '*.tmp' -o -name '*.tmp_backup' -o -name '*.bak' \) -print
```

The command may show intentionally retained application backups (for example,
`.backups/*_backup_*`); it must not show operation-owned staging names such as
`.foo.tmp_<operation>_*.tmp`, `.deleting_*.tmp`, or `.adc-cleanup-*` after the
operation has completed.

The comprehensive suite is `pytest -q`. It may include unrelated integration
tests that require external services; report those separately from deterministic
cleanup failures.

## Test coverage map

The cleanup tests cover successful publication, permission errors, simulated
`ENOSPC`, retry cleanup, rollback failures, concurrent orphan sweeps, append
failures, backup publication failures, backup-retention rollback, and the
end-to-end failed-transaction/startup-sweep path. Every failure test asserts
the relevant old target, new target, or temporary-file post-condition.
