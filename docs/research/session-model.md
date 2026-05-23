# Session Model: Identity, Surface Routing, and Human-as-Exception-Handler

---

## The Problem with Surface-Coupled Sessions

A session is not a surface. If the session is coupled to a surface (a WebSocket
connection, a Telegram chat, an audio call), state is lost when the surface
changes and the system has no principled way to route results when multiple
surfaces exist simultaneously.

The right model: a **logical session** is a persistent entity. Surfaces are
transient windows into it. The session persists whether or not any surface is
currently connected.

---

## Session State (Surface-Agnostic)

```
Session {
  id:               string          # stable identifier, survives all surface changes
  intent_history:   [Intent]        # everything ever asked in this session
  pending_intents:  [Intent]        # work in progress
  result_queue:     [Result]        # completed results not yet acknowledged
  exception_queue:  [Exception]     # items requiring human judgment
  surfaces:         [Surface]       # currently connected surfaces
  primary_surface:  SurfaceId?      # where to route next result
  last_active:      timestamp
}

Surface {
  id:       string
  type:     "web" | "audio" | "telegram" | ...
  state:    "connected" | "disconnected"
  always_available: bool   # telegram = true; web/audio = false (require active connection)
  last_seen: timestamp
}
```

The session lives in a central store (SQLite alongside `.beads/`, or a dedicated
table). No surface holds authoritative state.

---

## Surface Routing Rules

When a result or exception arrives, the system routes it using this priority order:

1. **Origin surface** (if still connected): where the utterance came from
2. **Most recently active connected surface**: user switched surfaces mid-session
3. **Any connected surface**: user has multiple surfaces open simultaneously
4. **Always-available fallback** (Telegram): no surfaces currently connected

```
Result arrives for session S
  │
  ├─ Is the origin surface connected?          → route there
  ├─ Is any surface connected?                 → route to most recently active
  └─ No surfaces connected                     → route to always-available fallback
```

"Most recently active" is updated whenever the user interacts on a surface
(speaks, types, dismisses a card). A surface that goes dark for N minutes is
deprioritized even if technically still connected.

### Simultaneous Surfaces

A user might have the web canvas open on their desk while listening via audio
on their phone. Results should go to the canvas visually AND be acknowledged
briefly by the voice model. This is the normal multi-surface case, not an edge
case. The routing layer sends to all connected surfaces simultaneously, with
surface-appropriate formatting (card spec → canvas, summary → audio narration).

---

## Human as Exception Handler

The core interaction model shift: **human in the loop** (human approves every
step) → **human as exception handler** (human resolves only what automated
processing cannot).

This is the dead letter queue (DLQ) pattern applied to agent work:

```
Normal flow:
  intent → workers → result → surfaced to user
  (human never involved, fully automated)

Exception flow:
  intent → worker hits decision it can't make
         → exception routed to human attention queue
         → human resolves
         → work resumes
  (human involved only at the exception point)
```

The human's attention is the scarcest resource in the system. The system should
protect it by routing only genuine exceptions — not progress updates, not
confirmations, not results that don't require action.

### What Is an Exception

| Type | Example | Requires human because... |
|------|---------|--------------------------|
| Blocked work | A coding task needs a design decision before proceeding | Worker can't continue without a value judgment |
| Ambiguous input | Router can't confidently route the utterance | Intent is unclear even after LLM parsing |
| Failed work | Worker exhausted retries, still failing | Automated recovery failed |
| Irreversible action | Worker about to write to prod, push to main | System policy requires sign-off |
| Conflicting signals | Two data sources disagree on state | System can't determine ground truth |

### What Is NOT an Exception

| Type | Handling |
|------|----------|
| Completed result | Pushed to surface, narrated in audio, card in canvas |
| Long-running work | Pending card shown, no human needed |
| Routine status | Worker returns summary, surfaces it |
| Informational research | Worker completes, surfaces at next pause |

The test: *could the system proceed without the human?* If yes, it should. Only
route to the human queue when the answer is no.

---

## The Exception Queue

The exception queue is the DLQ. It accumulates items that need human judgment
and surfaces them at an appropriate time — not as interruptions, but as a
managed inbox the human drains at their pace.

```
Exception {
  id:           string
  session_id:   string
  bead_ref?:    string            # the blocked bead, if applicable
  type:         ExceptionType
  urgency:      "critical" | "high" | "normal"
  title:        string            # one line, what decision is needed
  context:      string            # why it ended up here, what the worker tried
  options?:     [string]          # suggested responses if the system can propose them
  created_at:   timestamp
  resolved_at?: timestamp
  resolution?:  string
}
```

The voice model surfaces exceptions from the queue the same way it surfaces
results — at a natural pause, prioritized by urgency. A critical exception
(prod write, cascading failure) may interrupt. A normal exception (design
decision, routing ambiguity) waits.

The canvas shows an exceptions panel alongside the result cards. Each exception
is a card with a decision prompt.

### Resolving an Exception

The human responds via whichever surface is active:
- **Audio**: "approve that" / "cancel it" / "go with option two"
- **Canvas**: click a button on the exception card, or type a response
- **Telegram**: reply to the notification message

The resolution re-enters as a bead comment or bead close, unblocking downstream
work. The human's response is the same regardless of surface — the adapter
translates it to `br close` or `br comment`.

---

## Conversation Continuity Across Surfaces

Because session state is surface-agnostic, continuity is automatic:

```
User (audio, on the go): "check the options pipeline status"
  → intent dispatched, session S created
  → voice model: "checking that now"

[user sits down at desk, opens web canvas]
  → web surface connects, registers with session S
  → pending intents visible as pending cards on canvas
  → result arrives → routed to canvas (most recently active)
  → canvas shows status card
  → audio surface (still open) briefly acknowledges: "pipeline status is in"

[user picks up phone later, audio only]
  → web surface disconnected
  → 2 exceptions in queue from earlier
  → voice model: "while you were away — two things need your attention..."
```

No state is lost. No re-asking. The session is the continuity primitive.

---

## Relationship to Existing HUMAN Beads

NEEDLE's existing `HUMAN` bead label is a proto-exception-queue — it's already
the mechanism for workers to escalate to a human. The gap is delivery: HUMAN
beads are pull-based (human must notice them). The exception queue makes them
push-based (the session model routes them to the human's active surface).

No changes to the bead data model needed. The exception queue is a projection
over HUMAN beads plus session-originated exceptions. The bead watcher watches
for HUMAN bead creation the same way it watches for bead closure.

---

## Open Questions

1. **Session creation**: when does a new session start vs. resuming an existing one?
   Probably: same session within a time window (e.g. same calendar day), new session
   after extended idle. User can also explicitly start a new session ("new session"
   voice command).

2. **Exception urgency classification**: who sets urgency — the worker, or a
   classification pass after the exception is created? Worker-set is simpler;
   post-classification allows a consistent policy without each worker needing
   to reason about it.

3. **Result acknowledgment**: does the user need to explicitly acknowledge a
   result before it's removed from the queue, or does surfacing it count as
   acknowledgment? Explicit ack for exceptions; implicit (surfaced = acknowledged)
   for normal results.

4. **Multi-user sessions**: not in scope initially, but the surface registry
   could support multiple users on a session (e.g. shared team view on the canvas).
   Worth not architecting against it.
