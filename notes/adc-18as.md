# adc-18as — Verify persistence and SSE broadcast work

## Outcome

**Complete.** The persistence + SSE broadcast verification suite was already
implemented, committed (`a67cfc1`), and pushed to `origin/main` by a prior run
of this bead. This pass re-verified every acceptance criterion and closed the
bead (the prior run committed/pushed but never closed it).

## Acceptance criteria — all met

| Criterion | Covered by | Status |
|-----------|-----------|--------|
| Results are stored in session.db | `TestResultPersistence`, `TestStoreFactory` | ✅ |
| SSE broadcaster sends `result_created` events | `TestSSEResultCreated` | ✅ |
| Topic records created/updated correctly | `TestTopicRecords` | ✅ |
| All tests pass | 21/21 in the target file | ✅ |

## Test file

`tests/test_persistence_sse.py` — 21 hermetic, network-free tests
(no LLM, no kubectl, no real canvas). Key guarantees locked down:

- `create_result()` writes a row whose `data` round-trips as JSON,
  `surfaced_at` is set on creation, and `get_latest_result_for_topic()`
  returns it; the `previous_result_id` / `diff_*` chain links sequential
  results; the topic's `result_count` increments.
- `get_store()` (the production factory the router calls) routes persistence
  to the configured `session.db` via `ADC_DB_PATH`, and a result survives a
  fresh independent connection — proving it is flushed to disk, not held in
  memory. The process-wide singleton does not leak a different path.
- `create_topic()` persists type/scope/project_slugs; `find_or_create_topic()`
  is idempotent within a session and scoped per-session; global-scope topics
  are visible to every session; `update_topic_activity()` bumps `last_active`.
- `broadcast_result()` emits a `result_created` event; it reaches every
  surface in the target session, `target_surface_id` narrows to one,
  `exclude_surface_id` omits the origin, and a session with no matching
  connections returns 0 deliveries without erroring. SSE wire format verified.
- Integration: persisting a result via the store and broadcasting it yields an
  SSE event whose payload matches the DB row.

## Verification run (this pass)

```
$ .venv/bin/python -m pytest tests/test_persistence_sse.py -v
============================== 21 passed in 0.81s ==============================
```

Broader regression check (excluding `tests/e2e`):

```
$ .venv/bin/python -m pytest tests/ -q --ignore=tests/e2e --ignore=tests/test_exceptions_routing.py
279 passed in 2.12s
```

## Pre-existing, unrelated failure (not a regression from this bead)

`tests/test_exceptions_routing.py::TestAutoApprove::test_escalate_intent_auto_approves_read_only`
fails (`assert 'pending' == 'completed'`). This is in the **escalate handler**,
last touched by telegram-bridge work in `2bc24b0` — entirely outside this
bead's persistence/SSE scope. It fails on the committed tree with no changes
from this bead, so it is pre-existing and tracked separately. Recorded here so
a future agent does not mistake it for an adc-18as regression.

## Dependency

`adc-1mzt` (verify fetch + synthesis strands execute) is **closed** — the
blocking dependency this bead required is satisfied.
