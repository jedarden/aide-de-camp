"""
Persistence + SSE broadcast unit tests (bead adc-18as).

Hermetic, network-free tests for the two modules that turn a synthesized
result into something the user sees:

- src/session/store.py — SessionStore persists topics, intents, and results
  to SQLite. The same code backs data/session.db in production; these tests
  point it at an isolated tmp DB so they never touch real session data.
- src/sse/broadcaster.py — SSEBroadcaster routes events to connected
  surfaces, and broadcast_result() emits the ``result_created`` event the
  canvas listens for.

What this suite locks down (the "results are stored and surfaced" contract):

1. **Result persistence** — create_result() writes a row whose ``data`` is
   valid round-trip JSON, ``surfaced_at`` is set on creation, and
   get_latest_result_for_topic() returns it; the previous_result_id / diff
   chain links sequential results, and the topic's result_count increments.
2. **Topic records** — create_topic() persists type/scope/project_slugs,
   find_or_create_topic() is idempotent within a session (created=False on a
   hit) and is scoped per-session, global-scope topics are visible to every
   session, and update_topic_activity() bumps last_active.
3. **SSE result_created** — broadcast_result() emits a ``result_created``
   event; it reaches every surface in the target session, target_surface_id
   narrows delivery to one surface, exclude_surface_id omits the origin, and
   a session with no matching connections yields zero deliveries without
   erroring.
4. **Integration** — persisting a result via the store and broadcasting it
   via broadcast_result() delivers an SSE event whose payload matches the DB
   row.
"""

import asyncio
import json
from pathlib import Path

import aiosqlite
import pytest

import src.session.store as store_mod
from src.session.store import SessionStore
from src.sse.broadcaster import (
    EventType,
    SSEBroadcaster,
    SSEEvent,
    broadcast_result,
)

# --- fixtures --------------------------------------------------------------


@pytest.fixture
async def store(tmp_path: Path) -> SessionStore:
    """An isolated SessionStore on a tmp DB (same code as production session.db)."""
    db_path = tmp_path / "session.db"
    s = SessionStore(db_path)
    await s.initialize()
    yield s
    await s.close()


@pytest.fixture
async def broadcaster() -> SSEBroadcaster:
    """A fresh SSEBroadcaster per test — never the process-wide singleton."""
    b = SSEBroadcaster()
    await b.start()
    yield b
    await b.stop()


async def _seed(store: SessionStore, topic_label: str = "K8s Status") -> dict:
    """Create a full session→surface→utterance→intent→topic chain; return ids."""
    session_id = await store.create_session()
    surface_id = await store.register_surface(session_id, "canvas")
    utterance_id = await store.create_utterance(session_id, "check pods")
    topic_id = await store.create_topic(
        label=topic_label,
        topic_type="project",
        project_slugs=["k8s"],
        scope="session",
        session_id=session_id,
    )
    intent_id = await store.create_intent(
        utterance_id=utterance_id,
        session_id=session_id,
        project_slug="k8s",
        intent_type="lookup",
    )
    return {
        "session_id": session_id,
        "surface_id": surface_id,
        "utterance_id": utterance_id,
        "topic_id": topic_id,
        "intent_id": intent_id,
    }


# --- 1. result persistence -------------------------------------------------


class TestResultPersistence:
    """create_result() must persist a complete, retrievable result row."""

    @pytest.mark.asyncio
    async def test_result_row_round_trips_all_fields(self, store):
        ids = await _seed(store)
        data = {"pods": [{"name": "web-0", "phase": "Running"}], "count": 1}
        result_id = await store.create_result(
            intent_id=ids["intent_id"],
            topic_id=ids["topic_id"],
            session_id=ids["session_id"],
            summary="1 pod running",
            data=data,
            urgency="normal",
        )

        row = await store.get_latest_result_for_topic(ids["topic_id"])
        assert row is not None
        assert row["id"] == result_id
        assert row["intent_id"] == ids["intent_id"]
        assert row["topic_id"] == ids["topic_id"]
        assert row["session_id"] == ids["session_id"]
        assert row["summary"] == "1 pod running"
        assert row["urgency"] == "normal"

    @pytest.mark.asyncio
    async def test_data_field_is_valid_round_trip_json(self, store):
        ids = await _seed(store)
        data = {"a": 1, "nested": {"b": [2, 3]}, "ok": True}

        await store.create_result(
            intent_id=ids["intent_id"],
            topic_id=ids["topic_id"],
            session_id=ids["session_id"],
            summary="s",
            data=data,
        )

        row = await store.get_latest_result_for_topic(ids["topic_id"])
        # Stored as a JSON string; parsing must reproduce the exact dict.
        assert isinstance(row["data"], str)
        assert json.loads(row["data"]) == data

    @pytest.mark.asyncio
    async def test_surfaced_at_set_on_creation(self, store):
        ids = await _seed(store)

        await store.create_result(
            intent_id=ids["intent_id"],
            topic_id=ids["topic_id"],
            session_id=ids["session_id"],
            summary="s",
            data={},
        )

        row = await store.get_latest_result_for_topic(ids["topic_id"])
        assert row["surfaced_at"] is not None

    @pytest.mark.asyncio
    async def test_latest_result_is_the_most_recent(self, store):
        ids = await _seed(store)
        first = await store.create_result(
            intent_id=ids["intent_id"],
            topic_id=ids["topic_id"],
            session_id=ids["session_id"],
            summary="first",
            data={"n": 1},
        )
        second = await store.create_result(
            intent_id=ids["intent_id"],
            topic_id=ids["topic_id"],
            session_id=ids["session_id"],
            summary="second",
            data={"n": 2},
        )
        # created_at is integer-second resolution, so two rapid inserts can tie
        # and make ORDER BY created_at DESC ambiguous. Pin distinct ordered
        # timestamps so "second" is unambiguously the latest.
        async with aiosqlite.connect(store.db_path) as db:
            await db.execute("UPDATE results SET created_at = 100 WHERE id = ?", (first,))
            await db.execute("UPDATE results SET created_at = 200 WHERE id = ?", (second,))
            await db.commit()

        row = await store.get_latest_result_for_topic(ids["topic_id"])
        assert row["id"] == second
        assert row["summary"] == "second"

    @pytest.mark.asyncio
    async def test_diff_chain_links_sequential_results(self, store):
        ids = await _seed(store)
        first = await store.create_result(
            intent_id=ids["intent_id"],
            topic_id=ids["topic_id"],
            session_id=ids["session_id"],
            summary="first",
            data={"cpu": 50},
        )
        second = await store.create_result(
            intent_id=ids["intent_id"],
            topic_id=ids["topic_id"],
            session_id=ids["session_id"],
            summary="updated",
            data={"cpu": 60},
            previous_result_id=first,
            diff_summary="cpu changed",
            diff_data={"fields": [{"field_name": "cpu", "old_value": 50, "new_value": 60}]},
        )
        # See test_latest_result_is_the_most_recent: pin ordered timestamps.
        async with aiosqlite.connect(store.db_path) as db:
            await db.execute("UPDATE results SET created_at = 100 WHERE id = ?", (first,))
            await db.execute("UPDATE results SET created_at = 200 WHERE id = ?", (second,))
            await db.commit()

        row = await store.get_latest_result_for_topic(ids["topic_id"])
        assert row["id"] == second
        assert row["previous_result_id"] == first
        assert row["diff_summary"] == "cpu changed"
        assert json.loads(row["diff_data"])["fields"][0]["new_value"] == 60

    @pytest.mark.asyncio
    async def test_topic_result_count_increments(self, store):
        ids = await _seed(store)
        assert (await store.get_active_topics(ids["session_id"]))[0]["result_count"] == 0

        await store.create_result(
            intent_id=ids["intent_id"],
            topic_id=ids["topic_id"],
            session_id=ids["session_id"],
            summary="one",
            data={},
        )
        assert (await store.get_active_topics(ids["session_id"]))[0]["result_count"] == 1

        await store.create_result(
            intent_id=ids["intent_id"],
            topic_id=ids["topic_id"],
            session_id=ids["session_id"],
            summary="two",
            data={},
        )
        assert (await store.get_active_topics(ids["session_id"]))[0]["result_count"] == 2


# --- 1b. production factory path -------------------------------------------


class TestStoreFactory:
    """get_store() is the production entry point the router calls to persist.

    The classes above instantiate SessionStore directly; these tests prove the
    real factory routes persistence to the configured ``session.db`` (via
    ADC_DB_PATH) — i.e. that a result really is "stored in session.db" through
    the same code path production uses, and that the process-wide singleton
    doesn't leak a different path between calls.
    """

    def test_factory_resolves_adc_db_path(self, tmp_path, monkeypatch):
        """With ADC_DB_PATH set, get_store() builds at that path, never the
        production default (data/session.db)."""
        tmp_db = tmp_path / "factory.db"
        monkeypatch.setenv("ADC_DB_PATH", str(tmp_db))
        monkeypatch.setattr(store_mod, "_store", None)  # force a rebuild

        store = store_mod.get_store()
        assert store.db_path == tmp_db

    def test_factory_caches_singleton(self, tmp_path, monkeypatch):
        """Repeated calls return the same cached instance — the router relies on
        this stable target, and a per-call rebuild could silently split paths."""
        monkeypatch.setenv("ADC_DB_PATH", str(tmp_path / "cached.db"))
        monkeypatch.setattr(store_mod, "_store", None)

        first = store_mod.get_store()
        second = store_mod.get_store()
        assert first is second

    @pytest.mark.asyncio
    async def test_result_persists_to_factory_db(self, tmp_path, monkeypatch):
        """A result written through get_store() lands on disk in the file
        ADC_DB_PATH points at, surviving a fresh independent connection."""
        tmp_db = tmp_path / "session.db"
        monkeypatch.setenv("ADC_DB_PATH", str(tmp_db))
        monkeypatch.setattr(store_mod, "_store", None)

        store = store_mod.get_store()
        await store.initialize()
        session_id = await store.create_session()
        topic_id = await store.create_topic(
            label="K8s", topic_type="project", session_id=session_id
        )
        utterance_id = await store.create_utterance(session_id, "check pods")
        intent_id = await store.create_intent(
            utterance_id=utterance_id,
            session_id=session_id,
            project_slug="k8s",
            intent_type="lookup",
        )
        data = {"pods": [{"name": "web-0"}], "count": 1}
        result_id = await store.create_result(
            intent_id=intent_id,
            topic_id=topic_id,
            session_id=session_id,
            summary="1 pod running",
            data=data,
        )
        await store.close()

        # Re-open the same file with a brand-new SessionStore — the row must
        # survive, proving it was flushed to disk and not held in memory.
        assert tmp_db.exists()
        reader = SessionStore(tmp_db)
        row = await reader.get_latest_result_for_topic(topic_id)
        assert row is not None
        assert row["id"] == result_id
        assert json.loads(row["data"]) == data


# --- 2. topic records ------------------------------------------------------


class TestTopicRecords:
    """Topics are created with the right shape and updated as work happens."""

    @pytest.mark.asyncio
    async def test_create_topic_persists_type_scope_and_slugs(self, store):
        session_id = await store.create_session()
        topic_id = await store.create_topic(
            label="Options Pipeline",
            topic_type="project",
            project_slugs=["options"],
            scope="session",
            session_id=session_id,
        )

        topics = await store.get_active_topics(session_id)
        assert len(topics) == 1
        t = topics[0]
        assert t["id"] == topic_id
        assert t["label"] == "Options Pipeline"
        assert t["type"] == "project"
        assert t["scope"] == "session"
        assert json.loads(t["project_slugs"]) == ["options"]

    @pytest.mark.asyncio
    async def test_find_or_create_returns_existing_without_duplicate(self, store):
        session_id = await store.create_session()

        first_id, created_first = await store.find_or_create_topic(
            label="K8s", session_id=session_id, topic_type="project"
        )
        again_id, created_again = await store.find_or_create_topic(
            label="K8s", session_id=session_id, topic_type="project"
        )

        assert created_first is True
        assert created_again is False
        assert again_id == first_id
        assert len(await store.get_active_topics(session_id)) == 1  # no duplicate

    @pytest.mark.asyncio
    async def test_find_or_create_is_session_scoped(self, store):
        """The same label in two different sessions yields two distinct topics."""
        s1 = await store.create_session()
        s2 = await store.create_session()

        t1, c1 = await store.find_or_create_topic(
            label="Status", session_id=s1, topic_type="research"
        )
        t2, c2 = await store.find_or_create_topic(
            label="Status", session_id=s2, topic_type="research"
        )

        assert c1 and c2
        assert t1 != t2

    @pytest.mark.asyncio
    async def test_global_topic_visible_to_every_session(self, store):
        """A global-scope topic shows up in any session's active-topics query."""
        s1 = await store.create_session()
        s2 = await store.create_session()
        await store.create_topic(
            label="Global Thing",
            topic_type="project",
            scope="global",
            session_id=None,
        )

        labels_s1 = {t["label"] for t in await store.get_active_topics(s1)}
        labels_s2 = {t["label"] for t in await store.get_active_topics(s2)}
        assert "Global Thing" in labels_s1
        assert "Global Thing" in labels_s2

    @pytest.mark.asyncio
    async def test_update_topic_activity_bumps_last_active(self, store):
        session_id = await store.create_session()
        topic_id = await store.create_topic(
            label="X", topic_type="project", session_id=session_id
        )
        # Force an artificially old last_active so the bump is observable
        # without a 1-second wall-clock wait (timestamps are integer seconds).
        async with aiosqlite.connect(store.db_path) as db:
            await db.execute("UPDATE topics SET last_active = 0 WHERE id = ?", (topic_id,))
            await db.commit()

        await store.update_topic_activity(topic_id)

        assert (await store.get_active_topics(session_id))[0]["last_active"] > 0


# --- 3. SSE result_created -------------------------------------------------


class TestSSEResultCreated:
    """The broadcaster routes result_created events to the right surfaces."""

    @pytest.mark.asyncio
    async def test_broadcast_result_emits_result_created(self, broadcaster, monkeypatch):
        # broadcast_result() pulls the global singleton; point it at our fresh
        # instance so the test never depends on process-wide state.
        monkeypatch.setattr("src.sse.broadcaster.get_broadcaster", lambda: broadcaster)

        conn = broadcaster.register(surface_id="canvas-1", session_id="s1", surface_type="canvas")
        sent = await broadcast_result(
            result={"result_id": "r1", "summary": "ok"}, session_id="s1"
        )

        assert sent == 1
        event = await conn.queue.get()
        assert event.event_type == EventType.RESULT_CREATED
        assert event.data["result_id"] == "r1"

    @pytest.mark.asyncio
    async def test_event_reaches_every_surface_in_session(self, broadcaster):
        c1 = broadcaster.register("canvas-1", "s1", "canvas")
        c2 = broadcaster.register("canvas-2", "s1", "canvas")
        other_session = broadcaster.register("canvas-9", "s2", "canvas")

        sent = await broadcaster.broadcast(
            SSEEvent(
                event_type=EventType.RESULT_CREATED,
                data={"result_id": "r1"},
                target_session_id="s1",
            )
        )

        assert sent == 2
        assert (await c1.queue.get()).event_type == EventType.RESULT_CREATED
        assert (await c2.queue.get()).event_type == EventType.RESULT_CREATED
        # The other session must not have received it.
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(other_session.queue.get(), timeout=0.1)

    @pytest.mark.asyncio
    async def test_target_surface_id_narrows_to_one(self, broadcaster):
        chosen = broadcaster.register("canvas-1", "s1", "canvas")
        sibling = broadcaster.register("canvas-2", "s1", "canvas")

        sent = await broadcaster.broadcast(
            SSEEvent(
                event_type=EventType.RESULT_CREATED,
                data={},
                target_session_id="s1",
                target_surface_id="canvas-1",
            )
        )

        assert sent == 1
        assert (await chosen.queue.get()).data == {}
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(sibling.queue.get(), timeout=0.1)

    @pytest.mark.asyncio
    async def test_exclude_surface_id_omits_origin(self, broadcaster):
        origin = broadcaster.register("canvas-1", "s1", "canvas")
        peer = broadcaster.register("canvas-2", "s1", "canvas")

        sent = await broadcaster.broadcast(
            SSEEvent(
                event_type=EventType.RESULT_CREATED,
                data={"msg": "hi"},
                target_session_id="s1",
                exclude_surface_id="canvas-1",
            )
        )

        assert sent == 1
        assert (await peer.queue.get()).data["msg"] == "hi"
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(origin.queue.get(), timeout=0.1)

    @pytest.mark.asyncio
    async def test_no_matching_recipients_returns_zero(self, broadcaster):
        broadcaster.register("canvas-1", "s1", "canvas")

        sent = await broadcaster.broadcast(
            SSEEvent(
                event_type=EventType.RESULT_CREATED,
                data={},
                target_session_id="no-such-session",
            )
        )

        assert sent == 0  # nothing crashed; nothing delivered

    @pytest.mark.asyncio
    async def test_sse_wire_format(self, broadcaster):
        formatted = broadcaster._format_sse("result_created", {"result_id": "r1"})
        assert formatted.startswith("event: result_created\n")
        assert "\ndata: " in formatted
        assert formatted.endswith("\n\n")


# --- 4. persistence + SSE integration --------------------------------------


class TestPersistenceSSEIntegration:
    """Persisting a result and broadcasting it yields a consistent SSE event."""

    @pytest.mark.asyncio
    async def test_broadcast_payload_matches_persisted_row(
        self, store, broadcaster, monkeypatch
    ):
        monkeypatch.setattr("src.sse.broadcaster.get_broadcaster", lambda: broadcaster)

        ids = await _seed(store)
        data = {"pods": [{"name": "web-0"}], "count": 1}
        result_id = await store.create_result(
            intent_id=ids["intent_id"],
            topic_id=ids["topic_id"],
            session_id=ids["session_id"],
            summary="1 pod running",
            data=data,
            urgency="normal",
        )

        conn = broadcaster.register(
            surface_id=ids["surface_id"],
            session_id=ids["session_id"],
            surface_type="canvas",
        )

        sent = await broadcast_result(
            result={
                "result_id": result_id,
                "intent_id": ids["intent_id"],
                "topic_id": ids["topic_id"],
                "summary": "1 pod running",
                "data": data,
                "urgency": "normal",
            },
            session_id=ids["session_id"],
            target_surface_id=ids["surface_id"],
        )

        # The event was delivered…
        assert sent == 1
        event = await conn.queue.get()
        assert event.event_type == EventType.RESULT_CREATED
        assert event.data["result_id"] == result_id
        assert event.data["summary"] == "1 pod running"
        # …and the store agrees the result exists for this topic.
        row = await store.get_latest_result_for_topic(ids["topic_id"])
        assert row["id"] == result_id
        assert json.loads(row["data"]) == data
