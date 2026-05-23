# Topic Model: Organizing Across Utterances

## Separation of Concerns

**Card**: a rendering artifact. A way to present a result on a surface at a
moment in time. Ephemeral — it can be re-rendered, resized, replaced, or
dismissed. Not a record of anything. The same result can produce a different
card depending on screen size, how many other topics are active, or which
surface is rendering it.

**Topic / Thought**: a persistent concern the user has. The organizing entity.
Accumulates intents and results over time. Survives sessions.

**Intent**: a specific question or request within a topic at a point in time.

**Result**: the data returned by an agent for an intent. Stored. The source of
truth that cards are rendered from.

The relationship: topics contain intents, intents produce results, results are
rendered as cards. Cards are generated fresh at render time — they are not stored
and not the record of anything. If the canvas reflows, cards are regenerated from
the underlying results.

The **topic** is the right organizing primitive. Cards are simply how topics
surface their current state on a given surface.

---

## Topics and Threads

A **topic** is a persistent named concern — something the user returns to across
multiple utterances, possibly across multiple sessions. Topics are the organizing
layer above intents.

A **thread** is the history of intents and results for a topic. The canvas shows
threads. Cards accumulate inside threads. A thread can be active (pending or recent
results), quiet (nothing new), or archived (collapsed).

```
Canvas (each topic rendered as a card showing its current state)

[options pipeline]          [kalshi-tape deploy]        [pdftract naming]
────────────────────        ─────────────────────       ──────────────────
caught up ✓                 running 1/1 ✓               8 candidates ready
last event 4m ago           :abc123 synced              [expand to see list]
[history ↓]                 [history ↓]                 [history ↓]
```

The canvas shows one card per active topic — the current state of that topic,
rendered appropriately for the available space. If the topic has history (prior
intents and results), that's accessible but not the default view. The card is
not a record of a past query; it's a live view of the topic's current state.

When new results arrive for a topic, its card updates in place — not a new card
appended to a list.

### Topic Types

| Type | Example | Anchored to |
|------|---------|-------------|
| Project-anchored | "options pipeline" | A project slug in the registry |
| Compound | "kalshi-tape deploy" | A workflow template (image-repo + declarative-config) |
| Ad hoc | "pdftract naming" | A label/phrase, no registry entry |
| Exception | "blocked: auth decision" | A HUMAN bead |

---

## Topic Creation and Resolution

### How a topic is created

1. **Named by the user**: "check the options pipeline" → topic label extracted: "options pipeline"
2. **Inferred from routing**: intent routes to project `options-pipeline` → topic auto-named from project
3. **Compound template match**: intent matches `container-deploy` workflow → compound topic created
4. **Escalated task**: task bead created → thread created for that bead's lifecycle

### How vague references resolve

"Is it still behind?" — the router resolves against:

1. **Active threads**: any thread with a pending or recent result; if exactly one, that's "it"
2. **Most recently active thread**: last thread with user interaction
3. **Disambiguation**: if ambiguous, voice model asks; canvas shows quick-select

Vague references don't require searching all of session history — just the active
thread set, which is small. The thread model is what makes vague reference resolution
tractable.

---

## Topic Persistence

Topics have three scopes:

### Session-scoped (default)
Lives for the duration of a session. Good for: ad hoc research, one-off queries.
Thread disappears when the session archives.

### Cross-session (persistent)
Survives session boundaries. Good for: recurring project concerns, ongoing work.
The user asking about the options pipeline today and tomorrow sees one continuous thread.

Promotion from session-scoped to cross-session: automatic when a topic appears in
more than one session, or manual ("track this").

### Workspace-global (permanent)
Pinned threads that always appear on the canvas. Good for: the most critical projects,
standing exception queues, always-on monitoring threads.

---

## Canvas Layout: Thread-Organized

The canvas is a set of live thread columns (or rows in narrow mode), sorted by
last-active time descending. The most recently touched thread is prominent;
quiet threads compress.

```
Wide canvas:

[options pipeline]      [kalshi-tape deploy]    [exceptions]
─────────────────       ────────────────────    ────────────
• 15:17 caught up ✓     • 10:18 running 1/1 ✓   • blocked: auth
• 11:22 behind [!]      • 10:16 deployed          decision needed
• 09:04 current         • 10:15 CI passed        [respond]

[pdftract naming]       [ibkr-mcp]
─────────────────       ──────────
• 16:01 8 candidates    • quiet
  [expand]

```

Thread headers are persistent — even a quiet thread with no recent activity stays
visible as a header, so the user knows the system has it in scope. Fully archived
threads collapse to a single line in an "archived" section.

---

## The Exceptions Thread

Exceptions always occupy a fixed, prominent position on the canvas — regardless of
when they were created. They don't sort by recency; they sort by urgency. This is
the dead letter queue surface: always visible, always actionable.

In audio mode, the exceptions thread surfaces differently: the voice model periodically
checks if any unresolved exceptions exist and raises them at a natural pause, prioritized
by urgency tier.

---

## Session Store Schema Update

```sql
topics (
  id            TEXT PRIMARY KEY,
  label         TEXT,                -- "options pipeline", "kalshi-tape deploy"
  type          TEXT,                -- 'project' | 'compound' | 'adhoc' | 'exception'
  project_slugs TEXT,               -- JSON array, e.g. ["options-pipeline"]
  scope         TEXT,               -- 'session' | 'cross-session' | 'global'
  session_id    TEXT,               -- NULL if cross-session or global
  created_at    INTEGER,
  last_active   INTEGER,
  archived_at   INTEGER
)

intent_topics (
  intent_id     TEXT,
  topic_id      TEXT
  -- many-to-many: one intent can touch multiple topics (compound workflow)
)
```

Results are linked to intents; intents are linked to topics. The current state
of a topic is its most recent result. Cards are not stored — they are generated
from results at render time by the UI-regen agent, sized and styled for the
current surface and canvas layout.

---

## Audio Mode: Topic Navigation

Without a canvas, threads are navigated by name:
- "What's the status of the options pipeline thread?" → reads the most recent result
- "Any exceptions?" → reads the exception queue
- "What am I tracking?" → lists active topic labels
- "Catch me up" → reads one-line summaries of all active threads with new results

The voice model uses topic labels, not card IDs. The user never has to know about
internal identifiers.

---

## Open Questions

1. **Topic deduplication**: "options pipeline" and "the pipeline" and "it" all resolve
   to the same topic. How aggressively does the system deduplicate? Probably LLM-assisted
   at intent routing time, using the active topic set as candidates.

2. **Topic splitting**: "options pipeline" might encompass both aggregator and enrichment
   workers, which sometimes need to be discussed separately. Does the system split topics
   when the user gets more specific, or always keep them merged?

3. **Thread depth**: how many historical entries does a thread show before collapsing?
   Probably 3-5 visible, rest behind a "show history" affordance.

4. **Cross-session topic identity**: if a topic is promoted to cross-session, does it
   accumulate across all future sessions, or does each session get its own thread that
   links back to a parent topic? The latter feels right — daily context is different from
   all-time context.
