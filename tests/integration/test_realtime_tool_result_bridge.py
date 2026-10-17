"""
Integration tests for the Realtime tool-call-to-result bridge.

Covers the full voice-mode arc against a real session store:

1. dispatch_intent tool registration → immediate acknowledgment delivered
   as the tool output (never a coroutine repr).
2. Delayed result: a result the synthesize strand writes after the ack is
   correlated back to the dispatched intent, injected into the VoiceSession,
   and narrated on the voice websocket while also reaching the canvas via SSE.
3. Error delivery: a router outage surfaces as an error acknowledgment on
   the tool output path.
4. Pending-result delivery on an audio-to-canvas surface switch, including
   the ack (and nack-on-failure) claim semantics.
"""
import asyncio
import json
from contextlib import suppress
from unittest.mock import patch
from uuid import uuid4

import aiosqlite
import httpx
import pytest

from src.main import register_voice_tools
from src.realtime import continuity as continuity_module
from src.realtime import dispatch as dispatch_module
from src.realtime.continuity import handle_surface_switch
from src.realtime.session import VoiceSession
from src.session.store import SessionStore
from src.sse.broadcaster import EventType

ROUTER_URL = "http://localhost:8000/router"


class FakeWebSocket:
    """Minimal WebSocket double: records sends, replays queued client messages.

    ``receive_json`` blocks until a client message is queued, so the session
    loop falls through its 0.5s receive timeout and keeps polling for results
    to narrate — the same timing a real idle client produces.
    """

    def __init__(self):
        self.sent: list[dict] = []
        self.inbox: asyncio.Queue = asyncio.Queue()

    async def send_json(self, payload):
        self.sent.append(payload)

    async def receive_json(self):
        return await self.inbox.get()

    def put_client_message(self, message: dict) -> None:
        self.inbox.put_nowait(message)

    def sent_of_type(self, msg_type: str) -> list[dict]:
        return [p for p in self.sent if p.get("type") == msg_type]


async def wait_until(predicate, description: str, timeout: float = 5.0):
    """Poll a predicate until it returns a truthy value or the timeout expires."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        result = predicate()
        if result:
            return result
        await asyncio.sleep(0.05)
    raise AssertionError(f"condition not met within {timeout}s: {description}")


class FakeRouterClient:
    """Stand-in for the httpx.AsyncClient the dispatch module constructs.

    ``behavior`` is a (kind, value) pair: ("ok", payload) returns the payload
    as the router response; ("error", exc) raises exc from the POST.
    """

    behavior = ("ok", {})

    def __init__(self, **kwargs):
        pass  # construction kwargs (timeout) are irrelevant to the fake

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        return False

    async def post(self, url, json=None):
        kind, value = type(self).behavior
        if kind == "error":
            raise value
        return httpx.Response(200, json=value, request=httpx.Request("POST", url))


class _HttpxStub:
    """Namespace so patching never mutates the real httpx module."""

    AsyncClient = FakeRouterClient
    # dispatch_intent's except clauses match on these exception types
    ConnectError = httpx.ConnectError
    HTTPStatusError = httpx.HTTPStatusError
    Response = httpx.Response
    Request = httpx.Request


@pytest.fixture
async def store(tmp_path):
    store = SessionStore(tmp_path / "voice_bridge.db")
    await store.initialize()
    return store


@pytest.fixture
def router_payload():
    """Router response with a single intent thread for the utterance."""
    intent_id = f"intent-{uuid4().hex[:8]}"
    return {"utterance_id": "u-1", "intents": [{"intent_id": intent_id,
                                                "intent_type": "status",
                                                "status": "dispatched"}]}


async def _make_session(store, monkeypatch, router_payload):
    """Wire a VoiceSession with the real tool registration and fakes."""
    session_id = f"voice-session-{uuid4().hex[:8]}"

    from src.sse.broadcaster import SSEBroadcaster

    broadcaster = SSEBroadcaster()

    async def _get_store():
        return store

    async def _get_ephemeral_key(self, voice=None):
        # client_secret as a dict keeps this compatible with the event
        # validation the realtime module gained for outgoing ag2.init frames.
        return {"client_secret": {"value": "test-secret"}, "model": self.model}

    monkeypatch.setattr(dispatch_module, "get_store", _get_store)
    monkeypatch.setattr(continuity_module, "get_broadcaster", lambda: broadcaster)
    monkeypatch.setattr(dispatch_module, "httpx", _HttpxStub)
    monkeypatch.setattr(VoiceSession, "_get_ephemeral_key", _get_ephemeral_key)
    FakeRouterClient.behavior = ("ok", router_payload)

    websocket = FakeWebSocket()
    voice = VoiceSession(
        websocket=websocket,
        model="gpt-4o-realtime-preview",
        api_key="test-key",
        session_id=session_id,
        system_message="test prompt",
    )
    register_voice_tools(voice, session_id)

    return session_id, broadcaster, websocket, voice


async def _start_tasks(voice, websocket, session_id):
    run_task = asyncio.create_task(voice.run())
    listener_task = asyncio.create_task(
        dispatch_module.result_listener(session_id, voice, use_batching=False)
    )
    return run_task, listener_task


async def _stop_tasks(run_task, listener_task):
    for task in (run_task, listener_task):
        task.cancel()
        with suppress(asyncio.CancelledError, Exception):
            await task


async def test_realtime_tool_call_to_result_bridge(store, monkeypatch, router_payload):
    """Ack → delayed result injection → narration → error delivery → switch."""
    session_id, broadcaster, websocket, voice = await _make_session(
        store, monkeypatch, router_payload
    )
    canvas_conn = broadcaster.register(f"canvas-{session_id}", session_id, "canvas")
    topic_id, _ = await store.find_or_create_topic(
        label="aide-de-camp status",
        session_id=session_id,
        topic_type="project",
    )

    run_task, listener_task = await _start_tasks(voice, websocket, session_id)
    try:
        # ------------------------------------------------------------------
        # 1. Registration + immediate acknowledgment: the tool call is answered
        #    with the dispatch ack text on the same call_id, not a coroutine
        #    repr, and the router's intent is registered for correlation.
        # ------------------------------------------------------------------
        websocket.put_client_message({
            "type": "response.function_call_arguments.done",
            "name": "dispatch_intent",
            "call_id": "call-ack-1",
            "arguments": json.dumps({"utterance": "what is the status of aide-de-camp?"}),
        })

        ack_payload = await wait_until(
            lambda: next(
                (p for p in websocket.sent_of_type("conversation.item.create")
                 if p.get("item", {}).get("call_id") == "call-ack-1"),
                None,
            ),
            "dispatch_intent tool output",
        )
        assert ack_payload["item"]["type"] == "function_call_output"
        assert ack_payload["item"]["output"] == "On it."

        intent_id = router_payload["intents"][0]["intent_id"]
        assert dispatch_module.get_session_intents(session_id) == [intent_id]

        # The utterance was persisted under the session before routing.
        async with aiosqlite.connect(store.db_path) as db:
            async with db.execute(
                "SELECT raw_text FROM utterances WHERE session_id = ?",
                (session_id,),
            ) as cursor:
                rows = await cursor.fetchall()
        assert [row[0] for row in rows] == ["what is the status of aide-de-camp?"]

        # ------------------------------------------------------------------
        # 2. Delayed result: the synthesize strand writes the result after the
        #    ack. The listener correlates it to the dispatched intent, injects
        #    it into the VoiceSession, narrates it on the voice websocket, and
        #    delivers it to canvas surfaces via SSE.
        # ------------------------------------------------------------------
        result_id = await store.create_result(
            intent_id=intent_id,
            topic_id=topic_id,
            session_id=session_id,
            summary="aide-de-camp is healthy: voice bridge wired",
            data={"status": "healthy"},
            urgency="high",
        )

        narration = await wait_until(
            lambda: next(
                (p for p in websocket.sent_of_type("adc.narrate_results")
                 if any(r.get("intent_id") == intent_id for r in p.get("results", []))),
                None,
            ),
            "narration of the delayed result",
        )
        narrated = narration["results"][0]
        assert narrated["summary"] == "aide-de-camp is healthy: voice bridge wired"
        assert narrated["urgency"] == "high"

        canvas_event = await asyncio.wait_for(canvas_conn.queue.get(), timeout=1.0)
        assert canvas_event.event_type == EventType.RESULT_CREATED
        assert canvas_event.data["intent_id"] == intent_id

        # The pushed result is queued for canvas catch-up on the session.
        pending_before_switch = await voice.get_pending_results()
        voice.nack_pending_results(pending_before_switch)

        # ------------------------------------------------------------------
        # 3. Error delivery: with the router unreachable, the tool call is
        #    answered with the router-unavailable acknowledgment and no new
        #    intents are registered.
        # ------------------------------------------------------------------
        FakeRouterClient.behavior = ("error", httpx.ConnectError("router down"))
        websocket.put_client_message({
            "type": "response.function_call_arguments.done",
            "name": "dispatch_intent",
            "call_id": "call-error-1",
            "arguments": json.dumps({"utterance": "and what about the cluster?"}),
        })

        error_payload = await wait_until(
            lambda: next(
                (p for p in websocket.sent_of_type("conversation.item.create")
                 if p.get("item", {}).get("call_id") == "call-error-1"),
                None,
            ),
            "error acknowledgment on the tool output path",
        )
        assert error_payload["item"]["output"] == (
            "I'm having trouble routing that request right now."
        )
        assert dispatch_module.get_session_intents(session_id) == [intent_id]

        # ------------------------------------------------------------------
        # 4. Surface switch: pending results are delivered to canvas, the
        #    claim is acknowledged, and a second switch reports all caught up.
        # ------------------------------------------------------------------
        canvas_events_before = canvas_conn.queue.qsize()
        outcome = await handle_surface_switch("canvas", session_id, voice)

        assert [r["intent_id"] for r in outcome["pending_results"]] == [intent_id]
        assert "one result" in outcome["catch_up_summary"]
        assert canvas_conn.queue.qsize() == canvas_events_before + 1

        switched = await asyncio.wait_for(canvas_conn.queue.get(), timeout=1.0)
        assert switched.event_type == EventType.RESULT_CREATED
        assert switched.data["summary"] == "aide-de-camp is healthy: voice bridge wired"

        caught_up = await handle_surface_switch("canvas", session_id, voice)
        assert caught_up["pending_results"] == []
        assert caught_up["catch_up_summary"] == (
            "All caught up — nothing new on the canvas."
        )

        # The store row keeps its identity through the whole bridge.
        stored = await store.get_result(result_id)
        assert stored["intent_id"] == intent_id
    finally:
        await _stop_tasks(run_task, listener_task)


async def test_surface_switch_nacks_when_canvas_delivery_fails(
    store, monkeypatch, router_payload
):
    """A failed canvas delivery hands the pending batch back for retry."""
    session_id, broadcaster, websocket, voice = await _make_session(
        store, monkeypatch, router_payload
    )

    result_data = {
        "intent_id": router_payload["intents"][0]["intent_id"],
        "topic_id": "topic-1",
        "summary": "queued while audio was up",
        "urgency": "high",
        "data": {"status": "ok"},
    }
    await voice.push_result(result_data)

    async def _failing_push_to_canvas(session_id, result, exclude_audio_surface_id=None):
        raise RuntimeError("canvas SSE down")

    with patch.object(continuity_module, "push_to_canvas", _failing_push_to_canvas):
        with pytest.raises(RuntimeError):
            await handle_surface_switch("canvas", session_id, voice)

    # The batch was handed back — nothing was lost.
    retry = await handle_surface_switch("canvas", session_id, voice)
    assert [r["intent_id"] for r in retry["pending_results"]] == [result_data["intent_id"]]
