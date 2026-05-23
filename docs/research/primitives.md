# Data Primitives: Are Beads Still Right?

## What Beads Provide

- Durable append-only storage (JSONL, survives crashes)
- Status lifecycle (open → in_progress → closed)
- Assignee tracking and claim/release semantics
- Label-based filtering
- Dependency links (blocking/blocked-by)
- NEEDLE integration (workers poll for open beads)

This is a specific contract. The question is whether each kind of data in
stream-dispatch actually needs it.

---

## Data Audit

### Task-profile work items (research, coding, long-running analysis)
**Beads: yes.**
This is exactly what beads are for. NEEDLE integration is the point. Lifecycle,
retry, assignee, dependencies — all needed. No change.

### Exceptions (items needing human judgment)
**Beads: yes.**
NEEDLE's existing `HUMAN` label already models this correctly. The exception queue
is a projection over open HUMAN beads. No new primitive needed.

### Live-profile intents
**Beads: no.**
A live intent lives for seconds. Creating a bead, having NEEDLE claim it, work it,
and close it within 10 seconds is overhead in the wrong direction. The bead
lifecycle was designed for work that takes minutes to hours.
→ Live intents are transient records in a lightweight session store.

### Sessions
**Beads: no.**
A session never "closes" in the bead sense — it's a persistent context entity
with surfaces, queues, and history. Its lifecycle is orthogonal to work items.
Modelling a session as a bead would require contorting both the session semantics
and the bead model.
→ Sessions are records in a dedicated SQLite store.

### Surface state (which surfaces are connected)
**Beads: no.**
This is operational state that changes by the second — a WebSocket connects,
disconnects, reconnects. Append-only JSONL is the wrong durability model for
connection state that has no meaningful history.
→ Surfaces are rows in the session store, updated in place.

### Result queue (completed results not yet surfaced)
**Beads: no.**
Results are ephemeral — they exist until acknowledged, then they're done. No
dependency graph, no assignee, no NEEDLE integration. A result isn't work to be
done; it's a response waiting to be delivered.
→ Results are rows in the session store with a `surfaced_at` timestamp.

### Conversation history (prior utterances for context)
**Beads: no.**
Utterances are a log, not work items. The useful query is "give me the last N
utterances in session X in chronological order" — a simple table scan, not a
bead dependency traversal.
→ Utterances are rows in the session store.

---

## Two Storage Primitives

The system needs two stores, not one:

### 1. Beads (existing)
For discrete work units with agent lifecycle semantics.

- Task-profile intents (what NEEDLE processes)
- HUMAN exceptions (already modelled correctly)
- Nothing else

### 2. Session store (new, lightweight SQLite)
For conversational and operational state.

```sql
sessions (
  id          TEXT PRIMARY KEY,
  created_at  INTEGER,
  last_active INTEGER,
  primary_surface_id TEXT
)

surfaces (
  id          TEXT PRIMARY KEY,
  session_id  TEXT,
  type        TEXT,  -- 'web' | 'audio' | 'telegram'
  state       TEXT,  -- 'connected' | 'disconnected'
  always_available INTEGER,
  last_seen   INTEGER
)

utterances (
  id          TEXT PRIMARY KEY,
  session_id  TEXT,
  raw_text    TEXT,
  created_at  INTEGER
)

intents (
  id          TEXT PRIMARY KEY,
  utterance_id TEXT,
  session_id  TEXT,
  project_slug TEXT,
  intent_type TEXT,
  status      TEXT,  -- 'pending' | 'dispatched' | 'complete' | 'failed'
  bead_ref    TEXT,  -- set if escalated to a task bead
  created_at  INTEGER,
  resolved_at INTEGER
)

results (
  id          TEXT PRIMARY KEY,
  intent_id   TEXT,
  session_id  TEXT,
  summary     TEXT,
  card_spec   TEXT,  -- JSON
  urgency     TEXT,
  created_at  INTEGER,
  surfaced_at INTEGER,
  acked_at    INTEGER
)
```

This store has no NEEDLE integration, no claim semantics, no label filtering.
It's a fast, simple operational database. The bead watcher reads from it
(to know which session a completing bead belongs to) and writes to it
(to record the result). The router reads and writes it for every intent.

---

## The Bead ↔ Session Store Bridge

When a task-profile intent is escalated to a bead, a foreign key flows in
one direction: the `intents` table records `bead_ref`. The bead body records
`session_id` in its text (not a structured field — the bead watcher parses it).

The bead watcher is the bridge process: it watches for bead closure events,
reads `session_id` from the closed bead's body, looks up the active surface
in the session store, and routes the result. It writes a row to `results`.

No bead needs to know about the session store schema. No session store entry
needs to know about bead internals beyond the bead ID.

---

## Summary

| Data | Primitive | Reason |
|------|-----------|--------|
| Task work items | Bead | NEEDLE integration, lifecycle, retry |
| HUMAN exceptions | Bead (HUMAN label) | Already correct |
| Sessions | Session store | Persistent context, not work |
| Surfaces | Session store | Operational connection state |
| Live intents | Session store | Transient, seconds-lived |
| Results | Session store | Ephemeral delivery queue |
| Utterance history | Session store | Log, not work items |

Beads remain the right primitive for work. They are not the right primitive
for conversation. The session store is new but small — a single SQLite file
with five tables, no migrations needed at prototype scale.
