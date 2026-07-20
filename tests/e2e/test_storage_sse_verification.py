"""
E2E Test: Verify Storage and SSE Broadcast via Test Endpoint

Verifies that results from POST /api/v1/test/dispatch are:
1. Correctly stored in the session database (SQLite)
2. Broadcast via SSE to connected canvas surfaces
3. Storage payload matches /dispatch payload

Child of: adc-3mc5

These tests run against a live server on localhost:8000 (start it with
`nohup .venv/bin/python -m uvicorn src.main:app --host 0.0.0.0 --port 8000 &`).
They exercise real LLM classification/synthesis via the ZAI proxy, so they are
slow (tens of seconds) and need network access to the proxy.

Correctness notes (these were bugs in the original version of this file):
  * The `intent_ids` returned by the dispatch endpoints are router-internal
    correlation ids, NOT the `intents.id` primary key (store.create_intent
    mints its own id; the router's id is only used as the results.intent_id /
    intent_topics FK). So DB rows must be located by `session_id` (+utterance_id),
    never by the returned intent_id.
  * A POST issued while an SSE `client.stream(...)` is open on the *same*
    httpx.AsyncClient raises httpx.StreamConsumed. Use a separate client for the
    in-stream POST.
  * The SSE endpoint remaps `session_id` to a fresh id when no session row
    exists (main.py create_session() bug), so pre-create the session row before
    opening the SSE stream when you care about the id.
"""
import asyncio
import json
import time
import uuid
from pathlib import Path

import aiosqlite
import httpx
import pytest

API_BASE_URL = "http://localhost:8000"
DB_PATH = Path("/home/coding/aide-de-camp/data/session.db")


def _sid(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


async def _ensure_session(session_id: str) -> None:
    """Pre-create the session row so /sse does not remap session_id."""
    async with aiosqlite.connect(DB_PATH) as db:
        now = int(time.time())
        await db.execute(
            "INSERT OR IGNORE INTO sessions (id, created_at, last_active) VALUES (?, ?, ?)",
            (session_id, now, now),
        )
        await db.commit()


def _server_is_up() -> bool:
    try:
        return httpx.get(f"{API_BASE_URL}/health", timeout=2).status_code == 200
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _server_is_up(),
    reason="ADC server is not running on localhost:8000",
)


class TestStorageSSEVerification:
    """Verify storage and SSE broadcast via the test endpoint."""

    async def test_dispatch_storage_in_database(self):
        """Utterance, intent, and result rows persist to SQLite with correct linkage.

        Uses wait_for_results=True so the result is guaranteed stored before we
        query. Rows are located by session_id/utterance_id (the returned
        intent_id is a correlation id, not the intents.id PK).
        """
        session_id = _sid("test-storage")
        utterance = "verify storage and database persistence"
        await _ensure_session(session_id)

        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(
                f"{API_BASE_URL}/api/v1/test/dispatch",
                json={
                    "utterance": utterance,
                    "session_id": session_id,
                    "wait_for_results": True,
                    "timeout_seconds": 50,
                },
            )
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["status"] == "completed"
        assert data["session_id"] == session_id
        utterance_id = data["utterance_id"]
        assert len(data.get("results") or []) >= 1

        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row

            utterance_rows = await db.execute_fetchall(
                "SELECT id, session_id, raw_text FROM utterances WHERE id = ? AND session_id = ?",
                (utterance_id, session_id),
            )
            assert utterance_rows, "utterance not stored"
            assert utterance_rows[0]["raw_text"] == utterance

            intent_rows = await db.execute_fetchall(
                "SELECT * FROM intents WHERE session_id = ? AND utterance_id = ?",
                (session_id, utterance_id),
            )
            assert intent_rows, "no intent stored for utterance"
            for row in intent_rows:
                assert row["intent_type"] is not None
                assert row["status"] in ("pending", "dispatched", "resolved")

            result_rows = await db.execute_fetchall(
                "SELECT * FROM results WHERE session_id = ?", (session_id,)
            )
            assert result_rows, "no result stored"
            for row in result_rows:
                assert row["summary"]
                assert row["data"]
                assert row["topic_id"]

            # result -> topic -> session linkage
            linked = await db.execute_fetchall(
                """SELECT t.id FROM topics t
                   JOIN results r ON r.topic_id = t.id
                   WHERE r.session_id = ?""",
                (session_id,),
            )
            assert linked, "result not linked to a topic"

    async def test_dispatch_sse_broadcast(self):
        """A result_created SSE event reaches the surface_id given to /test/dispatch."""
        session_id = _sid("test-sse")
        surface_id = f"surface-{uuid.uuid4().hex[:12]}"
        utterance = "verify sse broadcast reaches canvas"
        await _ensure_session(session_id)

        received: list[dict] = []
        ready = asyncio.Event()

        async def listen():
            # Dedicated client + connection for the stream — a POST on the same
            # client while streaming raises httpx.StreamConsumed.
            async with httpx.AsyncClient() as sse_client:
                async with sse_client.stream(
                    "GET",
                    f"{API_BASE_URL}/api/v1/sse",
                    params={"session_id": session_id, "surface_id": surface_id, "surface_type": "canvas"},
                    timeout=None,
                ) as sse_response:
                    assert sse_response.status_code == 200
                    event_type = None
                    async for line in sse_response.aiter_lines():
                        if line.startswith("event: "):
                            event_type = line[len("event: "):].strip()
                            if event_type == "connected":
                                ready.set()
                        elif line.startswith("data: ") and event_type == "result_created":
                            received.append({"type": event_type, "data": json.loads(line[len("data: "):])})
                            return

        listener = asyncio.create_task(listen())
        try:
            await asyncio.wait_for(ready.wait(), timeout=10)
            await asyncio.sleep(0.3)  # let the connection register in the broadcaster

            async with httpx.AsyncClient(timeout=60) as client:
                dispatch = await client.post(
                    f"{API_BASE_URL}/api/v1/test/dispatch",
                    json={
                        "utterance": utterance,
                        "session_id": session_id,
                        "surface_id": surface_id,
                        "wait_for_results": False,
                    },
                )
            assert dispatch.status_code == 200, dispatch.text
            assert dispatch.json()["status"] == "dispatched"

            await asyncio.wait_for(asyncio.shield(listener), timeout=60)
        finally:
            if not listener.done():
                listener.cancel()

        assert received, "no result_created event received on surface_id"
        event = received[0]
        assert event["type"] == "result_created"
        payload = event["data"]
        assert {"intent_id", "topic_id", "summary", "urgency"}.issubset(payload.keys()), payload

    async def test_dispatch_matches_main_endpoint(self):
        """test/dispatch and /dispatch store structurally identical rows."""
        utterance = "compare test dispatch with main dispatch"
        test_session = _sid("cmp-test")
        main_session = _sid("cmp-main")
        await _ensure_session(test_session)
        await _ensure_session(main_session)

        async with httpx.AsyncClient(timeout=90) as client:
            test_resp = await client.post(
                f"{API_BASE_URL}/api/v1/test/dispatch",
                json={"utterance": utterance, "session_id": test_session, "wait_for_results": True,
                      "timeout_seconds": 80},
            )
            main_resp = await client.post(
                f"{API_BASE_URL}/dispatch",
                json={"utterance": utterance, "session_id": main_session,
                      "surface_id": f"surface-{uuid.uuid4().hex[:8]}"},
            )
        assert test_resp.status_code == 200, test_resp.text
        assert main_resp.status_code == 200, main_resp.text
        test_data, main_data = test_resp.json(), main_resp.json()

        # Both endpoints surface the same dispatch-ack fields.
        for key in ("utterance_id", "session_id", "intent_count", "intent_ids"):
            assert key in test_data, key
            assert key in main_data, key

        # Give /dispatch's background fetch+synthesize (real LLM) time to land.
        await asyncio.sleep(8)

        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            test_intents = await db.execute_fetchall(
                "SELECT * FROM intents WHERE session_id = ?", (test_session,))
            main_intents = await db.execute_fetchall(
                "SELECT * FROM intents WHERE session_id = ?", (main_session,))

        assert test_intents, "test/dispatch stored no intents"
        assert main_intents, "/dispatch stored no intents"
        # Intent row schema is identical across endpoints.
        assert set(test_intents[0].keys()) == set(main_intents[0].keys())

    async def test_broadcast_timing_matches_dispatch(self):
        """/test/dispatch returns immediately; the SSE event arrives afterwards."""
        session_id = _sid("test-timing")
        surface_id = f"surface-{uuid.uuid4().hex[:12]}"
        utterance = "verify broadcast timing"
        await _ensure_session(session_id)

        result_at: list[float] = []
        ready = asyncio.Event()

        async def listen():
            async with httpx.AsyncClient() as sse_client:
                async with sse_client.stream(
                    "GET", f"{API_BASE_URL}/api/v1/sse",
                    params={"session_id": session_id, "surface_id": surface_id, "surface_type": "canvas"},
                    timeout=None,
                ) as sse_response:
                    assert sse_response.status_code == 200
                    async for line in sse_response.aiter_lines():
                        if line.startswith("event: ") and line[len("event: "):].strip() == "connected":
                            ready.set()
                        if "result_created" in line and line.startswith("event: "):
                            result_at.append(time.time())
                            return

        listener = asyncio.create_task(listen())
        try:
            await asyncio.wait_for(ready.wait(), timeout=10)
            await asyncio.sleep(0.3)
            t0 = time.time()
            async with httpx.AsyncClient(timeout=60) as client:
                dispatch = await client.post(
                    f"{API_BASE_URL}/api/v1/test/dispatch",
                    json={"utterance": utterance, "session_id": session_id,
                          "surface_id": surface_id, "wait_for_results": False},
                )
            dispatch_elapsed = time.time() - t0
            assert dispatch.status_code == 200, dispatch.text
            # Dispatch acks fast; processing + broadcast happen in the background.
            assert dispatch_elapsed < 5.0, f"dispatch took {dispatch_elapsed:.2f}s (should be near-instant)"
            await asyncio.wait_for(asyncio.shield(listener), timeout=60)
        finally:
            if not listener.done():
                listener.cancel()

        assert result_at, "no result_created event received"

    async def test_result_created_event_payload(self):
        """The result_created event carries intent_id/topic_id/summary/urgency."""
        session_id = _sid("test-payload")
        surface_id = f"surface-{uuid.uuid4().hex[:12]}"
        utterance = "verify sse event payload structure"
        await _ensure_session(session_id)

        captured: list[dict] = []
        ready = asyncio.Event()

        async def listen():
            async with httpx.AsyncClient() as sse_client:
                async with sse_client.stream(
                    "GET", f"{API_BASE_URL}/api/v1/sse",
                    params={"session_id": session_id, "surface_id": surface_id, "surface_type": "canvas"},
                    timeout=None,
                ) as sse_response:
                    assert sse_response.status_code == 200
                    event_type = None
                    async for line in sse_response.aiter_lines():
                        if line.startswith("event: "):
                            event_type = line[len("event: "):].strip()
                            if event_type == "connected":
                                ready.set()
                        elif line.startswith("data: ") and event_type == "result_created":
                            captured.append(json.loads(line[len("data: "):]))
                            return

        listener = asyncio.create_task(listen())
        try:
            await asyncio.wait_for(ready.wait(), timeout=10)
            await asyncio.sleep(0.3)
            async with httpx.AsyncClient(timeout=60) as client:
                dispatch = await client.post(
                    f"{API_BASE_URL}/api/v1/test/dispatch",
                    json={"utterance": utterance, "session_id": session_id,
                          "surface_id": surface_id, "wait_for_results": False},
                )
            assert dispatch.status_code == 200, dispatch.text
            await asyncio.wait_for(asyncio.shield(listener), timeout=60)
        finally:
            if not listener.done():
                listener.cancel()

        assert captured, "no result_created event captured"
        event = captured[0]
        assert {"intent_id", "topic_id", "summary", "urgency"}.issubset(event.keys()), event


if __name__ == "__main__":
    import sys

    print("🧪 Storage + SSE verification (standalone)")
    print("=" * 60)
    health = httpx.get(f"{API_BASE_URL}/health", timeout=2)
    if health.status_code != 200:
        print(f"❌ server down (HTTP {health.status_code})"); sys.exit(1)
    print("✅ server running\n")

    inst = TestStorageSSEVerification()
    for name in [
        "test_dispatch_storage_in_database",
        "test_dispatch_sse_broadcast",
        "test_dispatch_matches_main_endpoint",
        "test_broadcast_timing_matches_dispatch",
        "test_result_created_event_payload",
    ]:
        print(f"\n[{name}]")
        print("-" * 60)
        asyncio.run(getattr(inst, name)())
        print("  ✅ passed")
    print("\n" + "=" * 60)
    print("✅ ALL TESTS PASSED")
