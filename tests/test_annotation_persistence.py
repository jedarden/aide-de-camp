"""
adc.annotation persistence tests (bead aidedeca-d0b9746d).

Covers the session-scoped persistence contract for client annotations:

- annotations persist and are isolated per session
- optional utterance/topic anchors resolve or are nulled when dangling
- malformed and oversized annotations are rejected and never persisted
- the payload never chooses the owning session
- session deletion removes annotations; topic deletion detaches the anchor
- handler and store failures never end the voice session

Decision record: docs/notes/aidedeca-d0b9746d-annotation-handling.md
"""

import pytest

import src.realtime.session as realtime_session
from src.realtime.session import VoiceSession

# --- helpers ------------------------------------------------------------------


class StubWebSocket:
    """Records outbound events; never raises."""

    def __init__(self):
        self.sent: list[dict] = []

    async def send_json(self, payload) -> None:
        self.sent.append(payload)


def make_voice_session(session_id: str, websocket: StubWebSocket) -> VoiceSession:
    return VoiceSession(
        websocket=websocket,
        model="test-model",
        api_key="test-key",
        session_id=session_id,
        system_message="test system message",
    )


def annotation_payload(
    text="a note", utterance_id=None, topic_id=None, **extra
) -> dict:
    annotation: dict = {"text": text}
    if utterance_id is not None:
        annotation["utterance_id"] = utterance_id
    if topic_id is not None:
        annotation["topic_id"] = topic_id
    annotation.update(extra)
    return {"type": "adc.annotation", "annotation": annotation}


def protocol_errors(websocket: StubWebSocket) -> list[dict]:
    return [m for m in websocket.sent if m.get("type") == "error"]


@pytest.fixture
def patched_store(test_db_store, monkeypatch):
    """Point src.realtime.session.get_store at the isolated test store."""

    async def fake_get_store():
        return test_db_store

    monkeypatch.setattr(realtime_session, "get_store", fake_get_store)
    return test_db_store


# --- store-level persistence --------------------------------------------------


async def test_annotation_persists_and_is_session_scoped(test_db_store) -> None:
    """Annotations persist and never leak across sessions."""
    session_a = await test_db_store.create_session()
    session_b = await test_db_store.create_session()

    await test_db_store.create_annotation(session_id=session_a, text="for a")
    await test_db_store.create_annotation(session_id=session_b, text="for b")

    rows_a = await test_db_store.get_annotations_for_session(session_a)
    rows_b = await test_db_store.get_annotations_for_session(session_b)

    assert [r["text"] for r in rows_a] == ["for a"]
    assert [r["text"] for r in rows_b] == ["for b"]
    assert all(r["session_id"] == session_a for r in rows_a)
    assert all(r["session_id"] == session_b for r in rows_b)


async def test_annotation_stores_optional_anchors(test_db_store) -> None:
    """utterance_id and topic_id anchors resolve when they exist."""
    session_id = await test_db_store.create_session()
    utterance_id = await test_db_store.create_utterance(session_id, "hello")
    topic_id = await test_db_store.create_topic(
        label="Topic", topic_type="research", scope="session", session_id=session_id
    )

    annotation_id = await test_db_store.create_annotation(
        session_id=session_id,
        text="anchored note",
        utterance_id=utterance_id,
        topic_id=topic_id,
    )

    by_session = await test_db_store.get_annotations_for_session(session_id)
    assert len(by_session) == 1
    assert by_session[0]["id"] == annotation_id
    assert by_session[0]["utterance_id"] == utterance_id
    assert by_session[0]["topic_id"] == topic_id
    assert by_session[0]["text"] == "anchored note"

    assert [r["id"] for r in await test_db_store.get_annotations_for_utterance(utterance_id)] == [
        annotation_id
    ]
    assert [r["id"] for r in await test_db_store.get_annotations_for_topic(topic_id)] == [
        annotation_id
    ]


async def test_annotation_without_anchors_defaults_null(test_db_store) -> None:
    """A bare annotation stores NULL anchors."""
    session_id = await test_db_store.create_session()

    await test_db_store.create_annotation(session_id=session_id, text="bare")

    (row,) = await test_db_store.get_annotations_for_session(session_id)
    assert row["utterance_id"] is None
    assert row["topic_id"] is None


async def test_annotations_ordered_oldest_first(test_db_store) -> None:
    """Session reads come back oldest first."""
    session_id = await test_db_store.create_session()

    for i in range(3):
        await test_db_store.create_annotation(session_id=session_id, text=f"note {i}")

    rows = await test_db_store.get_annotations_for_session(session_id)
    assert [r["text"] for r in rows] == ["note 0", "note 1", "note 2"]


async def test_delete_session_removes_annotations(test_db_store) -> None:
    """Session teardown removes the session's annotations (FKs are not enforced)."""
    session_id = await test_db_store.create_session()
    await test_db_store.create_annotation(session_id=session_id, text="doomed")

    await test_db_store.delete_session(session_id)

    assert await test_db_store.get_annotations_for_session(session_id) == []


async def test_delete_topic_detaches_annotation_anchor(test_db_store) -> None:
    """Deleting a topic nulls the anchor; the annotation itself survives."""
    session_id = await test_db_store.create_session()
    topic_id = await test_db_store.create_topic(
        label="Doomed", topic_type="adhoc", scope="session", session_id=session_id
    )
    await test_db_store.create_annotation(
        session_id=session_id, text="survivor", topic_id=topic_id
    )

    await test_db_store.delete_topic(topic_id)

    (row,) = await test_db_store.get_annotations_for_session(session_id)
    assert row["text"] == "survivor"
    assert row["topic_id"] is None


# --- handler-level behavior -----------------------------------------------------


async def test_valid_annotation_persists_under_connection_session(patched_store) -> None:
    """A valid annotation persists under the connection's session, not the payload's."""
    ws = StubWebSocket()
    session = make_voice_session("conn-session", ws)

    await session._handle_annotation(
        annotation_payload("remember this", session_id="client-claimed-session")
    )

    rows = await patched_store.get_annotations_for_session("conn-session")
    assert len(rows) == 1
    assert rows[0]["text"] == "remember this"
    assert rows[0]["session_id"] == "conn-session"
    # Rejections are the only client-visible signal; success is silent.
    assert protocol_errors(ws) == []


async def test_valid_annotation_resolves_anchors(patched_store) -> None:
    """Anchors that exist land on the persisted row."""
    session_id = await patched_store.create_session()
    utterance_id = await patched_store.create_utterance(session_id, "utterance")
    topic_id = await patched_store.create_topic(
        label="Topic", topic_type="adhoc", scope="session", session_id=session_id
    )
    ws = StubWebSocket()
    session = make_voice_session(session_id, ws)

    await session._handle_annotation(
        annotation_payload("note", utterance_id=utterance_id, topic_id=topic_id)
    )

    (row,) = await patched_store.get_annotations_for_session(session_id)
    assert row["utterance_id"] == utterance_id
    assert row["topic_id"] == topic_id
    assert protocol_errors(ws) == []


async def test_dangling_anchors_are_nulled_not_dropped(patched_store) -> None:
    """Unknown utterance/topic refs persist as NULL instead of losing the note."""
    session_id = await patched_store.create_session()
    ws = StubWebSocket()
    session = make_voice_session(session_id, ws)

    await session._handle_annotation(
        annotation_payload(
            "note with a dangling anchor",
            utterance_id="no-such-utterance",
            topic_id="no-such-topic",
        )
    )

    (row,) = await patched_store.get_annotations_for_session(session_id)
    assert row["text"] == "note with a dangling anchor"
    assert row["utterance_id"] is None
    assert row["topic_id"] is None
    assert protocol_errors(ws) == []


@pytest.mark.parametrize("payload", [{}, {"annotation": "not-a-dict"}, {"annotation": None}])
async def test_malformed_envelope_is_rejected(patched_store, payload) -> None:
    """A missing or non-object annotation is rejected and not persisted."""
    ws = StubWebSocket()
    session = make_voice_session("s", ws)

    await session._handle_annotation(payload)

    assert await patched_store.get_annotations_for_session("s") == []
    (error,) = protocol_errors(ws)
    assert error["error"]["code"] == "malformed_event"
    assert error["error"]["event_type"] == "adc.annotation"


@pytest.mark.parametrize("text", [None, 123, "", "   "])
async def test_malformed_text_is_rejected(patched_store, text) -> None:
    """text must be a non-empty string; anything else is rejected."""
    ws = StubWebSocket()
    session = make_voice_session("s", ws)

    await session._handle_annotation(annotation_payload(text=text))

    assert await patched_store.get_annotations_for_session("s") == []
    (error,) = protocol_errors(ws)
    assert error["error"]["code"] == "malformed_event"


async def test_oversized_text_is_rejected_not_truncated(patched_store) -> None:
    """Oversized annotations are rejected whole — never silently clipped."""
    ws = StubWebSocket()
    session = make_voice_session("s", ws)
    oversized = "x" * (realtime_session.MAX_ANNOTATION_TEXT_LENGTH + 1)

    await session._handle_annotation(annotation_payload(oversized))

    assert await patched_store.get_annotations_for_session("s") == []
    (error,) = protocol_errors(ws)
    assert error["error"]["code"] == "annotation_oversized"


async def test_text_at_the_limit_persists(patched_store) -> None:
    """The boundary itself is accepted."""
    session_id = await patched_store.create_session()
    ws = StubWebSocket()
    session = make_voice_session(session_id, ws)
    at_limit = "y" * realtime_session.MAX_ANNOTATION_TEXT_LENGTH

    await session._handle_annotation(annotation_payload(at_limit))

    (row,) = await patched_store.get_annotations_for_session(session_id)
    assert row["text"] == at_limit


@pytest.mark.parametrize(
    "field", ["utterance_id", "topic_id"]
)
async def test_non_string_anchor_is_rejected(patched_store, field) -> None:
    """A non-string anchor is a malformed annotation, not a coercion."""
    ws = StubWebSocket()
    session = make_voice_session("s", ws)

    await session._handle_annotation(annotation_payload("note", **{field: 12345}))

    assert await patched_store.get_annotations_for_session("s") == []
    (error,) = protocol_errors(ws)
    assert error["error"]["code"] == "malformed_event"


async def test_unknown_annotation_fields_are_ignored(patched_store) -> None:
    """Extra keys inside the annotation do not block persistence."""
    session_id = await patched_store.create_session()
    ws = StubWebSocket()
    session = make_voice_session(session_id, ws)

    await session._handle_annotation(
        annotation_payload("note", client_version=3, color="blue")
    )

    (row,) = await patched_store.get_annotations_for_session(session_id)
    assert row["text"] == "note"


async def test_store_failure_sends_protocol_error_without_raising(
    patched_store, monkeypatch
) -> None:
    """A persist failure becomes annotation_persist_failed and never propagates."""

    async def failing_create_annotation(*args, **kwargs):
        raise RuntimeError("disk on fire")

    monkeypatch.setattr(
        patched_store, "create_annotation", failing_create_annotation
    )
    ws = StubWebSocket()
    session = make_voice_session("s", ws)

    # Must not raise even though the store did.
    await session._handle_annotation(annotation_payload("note"))

    (error,) = protocol_errors(ws)
    assert error["error"]["code"] == "annotation_persist_failed"


async def test_annotation_via_client_event_path_persists(patched_store) -> None:
    """The full validate → dedupe → dispatch path persists a valid annotation."""
    session_id = await patched_store.create_session()
    ws = StubWebSocket()
    session = make_voice_session(session_id, ws)

    await session._handle_client_event(
        annotation_payload("routed through validation")
    )

    (row,) = await patched_store.get_annotations_for_session(session_id)
    assert row["text"] == "routed through validation"
    assert protocol_errors(ws) == []
