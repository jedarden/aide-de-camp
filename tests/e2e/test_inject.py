"""
Hermetic tests for the canvas test-data injection utilities (bead adc-5unt).

``TestDataInjector`` (tests/e2e/inject.py) is the async httpx client that the
Playwright/browser canvas suites use to set up known sessions + topics and tear
them down. These tests lock down its contract *without* needing a live server
or a browser:

- They drive the real FastAPI app in-process via httpx's ``ASGITransport`` (no
  socket, no ``uvicorn``), so they always run in CI.
- They point the session store at an isolated tmp SQLite file (via
  ``ADC_DB_PATH`` + a reset of the store singleton) so they never read or write
  the production ``data/session.db``.

What this suite locks down (the "inject + clean up, hermetically" contract):

1. **Session creation** — predictable prefixed IDs, auto-generated IDs, and
   idempotency (created=True the first time, False on a repeat).
2. **Topic injection** — a session can be injected with multiple topics that are
   all readable back through the same GET /topics endpoint the canvas uses.
3. **Cleanup** — every tracked session is deleted on ``aclose()``/``cleanup()``,
   removing its topics and results; ``async with`` teardown runs even on error.
4. **Isolation** — injected rows land in the tmp DB, never in the production
   session.db.
"""
import aiosqlite
import pytest

import src.main as main_mod
import src.session.store as store_mod
from src.topic.model import TopicManager
from tests.e2e.inject import (
    DEFAULT_BASE_URL,
    TEST_SESSION_PREFIX,
    TestDataInjector,
)

# The production store path — used *only* to assert test data never reaches it.
PROD_DB_PATH = store_mod.DEFAULT_DB_PATH


# --- fixtures --------------------------------------------------------------


@pytest.fixture
async def inj(tmp_path, monkeypatch):
    """An in-process TestDataInjector backed by an ISOLATED tmp DB.

    - Sets ``ADC_DB_PATH`` to a tmp file and resets the store singleton so the
      app's store is recreated at that path (never ``data/session.db``).
    - Wires ``main._topic_manager`` so GET /sessions/{id}/topics works without
      the full app lifespan (ASGITransport does not run lifespan startup).
    - On teardown: cleans up every tracked session via the injector, closes the
      httpx client, and restores the real singletons + env.
    """
    tmp_db = tmp_path / "test-session.db"
    monkeypatch.setenv("ADC_DB_PATH", str(tmp_db))

    # Save the process-wide singletons so other tests are unaffected.
    saved_store_singleton = store_mod._store
    saved_main_store = main_mod._store
    saved_topic_manager = main_mod._topic_manager

    # Force get_store() to rebuild at the tmp path on next call.
    store_mod._store = None
    main_mod._store = None
    main_mod._topic_manager = None

    store = store_mod.get_store()  # reads ADC_DB_PATH → tmp_db
    await store.initialize()
    main_mod._topic_manager = TopicManager(store)

    async with TestDataInjector(app=main_mod.app) as injector:
        yield injector, tmp_db

    # Restore — never leak the tmp store into the rest of the process.
    main_mod._topic_manager = saved_topic_manager
    main_mod._store = saved_main_store
    store_mod._store = saved_store_singleton


async def _count(db_path, sql, args=()):
    """Run a scalar COUNT(*) query against db_path; return the integer."""
    async with aiosqlite.connect(db_path) as db:
        async with db.execute(sql, args) as cur:
            row = await cur.fetchone()
            return int(row[0]) if row else 0


# --- 1. session creation ---------------------------------------------------


class TestSessionCreation:
    """create_session() honors explicit IDs, auto-generates prefixed IDs, and is idempotent."""

    async def test_explicit_predictable_id_is_tracked_and_prefixed(self, inj):
        injector, _ = inj
        data = await injector.create_session("my-scenario")
        assert data["session_id"] == "test-inject-my-scenario"
        assert data["created"] is True
        assert "test-inject-my-scenario" in injector.tracked_sessions

    async def test_auto_generated_id_has_test_prefix(self, inj):
        injector, _ = inj
        data = await injector.create_session()  # no explicit id
        sid = data["session_id"]
        assert sid.startswith(TEST_SESSION_PREFIX)
        assert data["created"] is True
        assert sid in injector.tracked_sessions

    async def test_create_is_idempotent(self, inj):
        injector, _ = inj
        first = await injector.create_session("dupe")
        second = await injector.create_session("dupe")
        assert first["session_id"] == second["session_id"] == "test-inject-dupe"
        assert first["created"] is True
        assert second["created"] is False  # already existed


def test_predictable_session_id_sanitizes_label():
    """The static helper collapses unsafe chars and falls back when empty."""
    assert TestDataInjector.predictable_session_id("Pods in iad!").startswith(TEST_SESSION_PREFIX)
    assert TestDataInjector.predictable_session_id("Pods in iad!") == "test-inject-Pods-in-iad"
    assert TestDataInjector.predictable_session_id("   ").startswith(TEST_SESSION_PREFIX)


def test_constructor_rejects_ambiguous_transport():
    """Passing both app= and a non-default base_url is a programming error."""
    with pytest.raises(ValueError):
        TestDataInjector(base_url="http://example:9000", app=object())


def test_default_base_url_points_at_local_canvas():
    """Live-server default targets the canvas on :8000."""
    assert DEFAULT_BASE_URL == "http://localhost:8000"


# --- 2. topic injection ----------------------------------------------------


class TestTopicInjection:
    """inject_session_with_topics() writes topics that GET /topics can read back."""

    async def test_inject_session_with_multiple_topics(self, inj):
        injector, _ = inj
        specs = [
            {"label": "Pods", "topic_type": "project", "summary": "3 pods running"},
            {"label": "Builds", "topic_type": "project", "summary": "build green"},
            {"label": "Weather", "topic_type": "research", "summary": "rain tomorrow"},
        ]
        result = await injector.inject_session_with_topics("test-inject-multi", specs)

        assert result["session_id"] == "test-inject-multi"
        assert result["topic_count"] == 3
        assert len(result["topics"]) == 3
        # Each direct-injected topic reports a topic_id + result_id.
        for t in result["topics"]:
            assert t["status"] == "created"
            assert t["topic_id"]
            assert t["result_id"]

        # Read back through the SAME endpoint the canvas uses.
        cards = await injector.get_topics("test-inject-multi")
        labels = {c["topic"]["label"] for c in cards}
        assert {"Pods", "Builds", "Weather"} <= labels

    async def test_inject_topic_direct_returns_ids(self, inj):
        injector, _ = inj
        await injector.create_session("test-inject-single")
        data = await injector.inject_topic(
            "test-inject-single", label="Solo", summary="one result"
        )
        assert data["label"] == "Solo"
        assert data["topic_id"] and data["result_id"]

        cards = await injector.get_topics("test-inject-single")
        assert any(c["topic"]["label"] == "Solo" for c in cards)

    async def test_inject_topic_dispatch_requires_utterance(self, inj):
        """The LLM-backed dispatch path refuses to run without an utterance."""
        injector, _ = inj
        with pytest.raises(ValueError):
            await injector.inject_topic("test-inject-x", label="x", via="dispatch")
        with pytest.raises(ValueError):
            await injector.inject_topic("test-inject-x", via="dispatch")  # no label either


# --- 3. cleanup ------------------------------------------------------------


class TestCleanup:
    """Tracked sessions are fully removed on cleanup/aclose, even on error."""

    async def test_delete_session_removes_topics_and_results(self, inj):
        injector, tmp_db = inj
        sid = "test-inject-cleanup"
        await injector.inject_session_with_topics(
            sid,
            [{"label": "A", "summary": "a"}, {"label": "B", "summary": "b"}],
        )
        # Data is present before cleanup.
        assert await _count(tmp_db, "SELECT COUNT(*) FROM topics WHERE session_id = ?", (sid,)) == 2
        assert await _count(tmp_db, "SELECT COUNT(*) FROM results WHERE session_id = ?", (sid,)) == 2

        summary = await injector.delete_session(sid)
        assert summary["status"] == "deleted"
        assert summary["session_removed"] == 1
        assert summary["topics_removed"] == 2
        assert sid not in injector.tracked_sessions

        # Everything tied to the session is gone.
        assert await _count(tmp_db, "SELECT COUNT(*) FROM sessions WHERE id = ?", (sid,)) == 0
        assert await _count(tmp_db, "SELECT COUNT(*) FROM topics WHERE session_id = ?", (sid,)) == 0
        assert await _count(tmp_db, "SELECT COUNT(*) FROM results WHERE session_id = ?", (sid,)) == 0

    async def test_cleanup_removes_all_tracked_sessions(self, inj):
        injector, tmp_db = inj
        for sid in ("test-inject-batch-1", "test-inject-batch-2", "test-inject-batch-3"):
            await injector.inject_session_with_topics(sid, [{"label": "T", "summary": "s"}])

        removed = await injector.cleanup()
        assert sorted(removed) == [
            "test-inject-batch-1",
            "test-inject-batch-2",
            "test-inject-batch-3",
        ]
        assert injector.tracked_sessions == []
        assert await _count(tmp_db, "SELECT COUNT(*) FROM sessions WHERE id LIKE 'test-inject-batch-%'") == 0

    async def test_context_manager_cleans_up_on_success(self, inj):
        """The `async with` form deletes tracked sessions on normal exit."""
        injector, tmp_db = inj  # fixture wraps the injector in `async with`
        sid = "test-inject-ctx"
        await injector.inject_session_with_topics(sid, [{"label": "C", "summary": "c"}])
        assert await _count(tmp_db, "SELECT COUNT(*) FROM sessions WHERE id = ?", (sid,)) == 1
        # When the fixture's `async with` exits, aclose() → cleanup() runs.

    async def test_context_manager_cleans_up_on_error(self, tmp_path, monkeypatch):
        """Teardown must run even when the test body raises."""
        monkeypatch.setenv("ADC_DB_PATH", str(tmp_path / "err.db"))
        saved_store = store_mod._store
        saved_main_store = main_mod._store
        saved_tm = main_mod._topic_manager
        store_mod._store = None
        main_mod._store = None
        main_mod._topic_manager = None
        store = store_mod.get_store()
        await store.initialize()
        main_mod._topic_manager = TopicManager(store)
        sid = "test-inject-raises"
        created = []

        try:
            async with TestDataInjector(app=main_mod.app) as injector:
                await injector.create_session(sid)
                created.append(sid)
                raise RuntimeError("simulated test failure")
        except RuntimeError:
            pass
        finally:
            main_mod._topic_manager = saved_tm
            main_mod._store = saved_main_store
            store_mod._store = saved_store

        # The session created inside the failing body was cleaned up on exit.
        assert created == [sid]
        assert await _count(tmp_path / "err.db", "SELECT COUNT(*) FROM sessions WHERE id = ?", (sid,)) == 0


# --- 4. isolation ----------------------------------------------------------


class TestIsolation:
    """Injected data lands in the tmp DB and NEVER in production session.db."""

    async def test_data_lands_in_tmp_db_not_production(self, inj):
        injector, tmp_db = inj
        sid = "test-inject-isolation"
        await injector.inject_session_with_topics(
            sid, [{"label": "Iso", "summary": "isolated"}]
        )

        # Present in the tmp store the injector was pointed at.
        assert await _count(tmp_db, "SELECT COUNT(*) FROM sessions WHERE id = ?", (sid,)) == 1
        assert await _count(tmp_db, "SELECT COUNT(*) FROM topics WHERE session_id = ?", (sid,)) == 1

        # Absent from the production store — this is the core isolation promise.
        assert await _count(PROD_DB_PATH, "SELECT COUNT(*) FROM sessions WHERE id = ?", (sid,)) == 0
        assert await _count(PROD_DB_PATH, "SELECT COUNT(*) FROM topics WHERE session_id = ?", (sid,)) == 0

    async def test_cleanup_does_not_touch_production(self, inj):
        """Deleting an isolated session never writes to the production DB."""
        injector, tmp_db = inj
        sid = "test-inject-iso-cleanup"
        await injector.inject_session_with_topics(sid, [{"label": "X", "summary": "x"}])
        await injector.delete_session(sid)

        assert await _count(tmp_db, "SELECT COUNT(*) FROM sessions WHERE id = ?", (sid,)) == 0
        assert await _count(PROD_DB_PATH, "SELECT COUNT(*) FROM sessions WHERE id = ?", (sid,)) == 0
