# `adc.annotation` handling — decision and contract

Bead: `aidedeca-d0b9746d`

Voice clients send `adc.annotation` over the `/voice` WebSocket. Until now the
server only logged the payload, so user-authored notes were lost on restart
and invisible to everything downstream. This note records the chosen behavior,
now implemented in `src/realtime/session.py` (`VoiceSession._handle_annotation`)
and `src/session/store.py` (the `annotations` table).

## Decision: annotations are persisted

An annotation is session-scoped user content, the same class of data as an
utterance. It gets a `annotations` row and survives restarts.

## Wire shape

```json
{
  "type": "adc.annotation",
  "event_id": "optional client-generated id",
  "annotation": {
    "text": "required, non-empty string, <= 4000 chars",
    "utterance_id": "optional anchor",
    "topic_id": "optional anchor",
    "...": "unknown keys are ignored"
  }
}
```

The envelope (`type`, `annotation` is an object, `extra="forbid"`, optional
`event_id`) is enforced by the schema layer (`src/realtime/schema.py`,
`AnnotationEvent`) before dispatch — see bead `aidedeca-d9007d2b`. The
*content* contract below is enforced by `VoiceSession._persist_annotation`.

## Associations

| Field | Source | Rule |
|---|---|---|
| `session_id` | the owning connection (`VoiceSession.session_id`) | Always set; a `session_id` inside the payload is ignored. Clients never name the session. |
| `utterance_id` | `annotation.utterance_id` | Optional. Must be a string when present and must resolve; a dangling id is nulled (with a warning) so the note survives. |
| `topic_id` | `annotation.topic_id` | Optional, same rule as utterances. |

Schema-level FKs (`annotations` → `sessions` CASCADE, → `utterances` CASCADE,
→ `topics` SET NULL) document the intent, but SQLite FK enforcement is off in
this store, so `delete_session` removes annotations explicitly and
`delete_topic` nulls the topic anchor — the note outlives the topic, matching
how `intents.topic_id` is handled.

## Malformed and oversized

All rejections reuse the shared protocol-error channel
(`type: "error"` with a structured `error` object, `event_type:
"adc.annotation"`) — no dedicated outbound event type. Handling never raises
into the session loop; a bad annotation cannot end a voice session.

| Condition | Error code | Persisted? |
|---|---|---|
| envelope invalid (schema layer) | `malformed_event` | no |
| `annotation` not an object (defense in depth) | `malformed_event` | no |
| `text` missing / not a string / whitespace-only | `malformed_event` | no |
| `utterance_id`/`topic_id` present but not a string | `malformed_event` | no |
| `text` > `MAX_ANNOTATION_TEXT_LENGTH` (4000 chars) | `annotation_oversized` | no — **rejected, never truncated**; a silently clipped note would corrupt user content and the client can resend shorter |
| store failure while persisting | `annotation_persist_failed` | no |

There is **no success ack**: silence means persisted, matching `adc.turn_done`
which also gets none. This keeps the outbound event surface unchanged (the
schema layer validates every outbound event; adding an ack type would be a
protocol change belonging to the schema bead).

## Storage

`annotations(id, session_id, created_at, utterance_id?, topic_id?, text)`.
Reads: `get_annotations_for_session` (the session-scoped view),
`get_annotations_for_utterance`, `get_annotations_for_topic`, all
oldest-first. Tests: `tests/test_annotation_persistence.py`.

## Boundaries / not decided here

- Frame-level WebSocket size limits (a multi-megabyte frame is rejected by the
  server before it becomes an event) — general transport hardening, not
  annotation-specific.
- No HTTP read endpoint or canvas rendering for annotations yet; a
  `GET /api/v1/sessions/{id}/annotations` surface would be the natural
  follow-up, proposed here only.
- No edit/delete API; annotations are append-only for now.
