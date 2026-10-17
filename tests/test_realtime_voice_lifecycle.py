"""VoiceSession bootstrap and lifecycle coverage for the /voice surface.

Drives the documented voice-session lifecycle (docs/plan/plan.md, Phase 4)
end to end at the session boundary: bootstrap with an ephemeral Realtime
key, tool registration, a complete voice turn (tool-as-trigger dispatch,
async result narration, turn completion with memory extraction, surface
switch), disconnect cleanup, and the error paths.

The transport is a duplex in-memory WebSocket so every wait is bounded;
everything behind it — VoiceSession, event validation, the continuity
handler, the /voice endpoint guards — is the real implementation.
"""

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from src.realtime.continuity import handle_surface_switch
from src.realtime.session import VoiceSession

DISCONNECT = object()  # Sentinel: client closed the socket.


def test_canvas_loads_the_served_voice_client() -> None:
    from src.main import app

    html = (Path(__file__).parents[1] / "src/canvas/index.html").read_text()
    assert '<script src="/voice.js"></script>' in html
    assert 'id="btnVoice"' in html

    response = TestClient(app).get("/voice.js")
    assert response.status_code == 200
    assert "ADCVoiceClient" in response.text


class FakeWebSocket:
    """In-memory duplex websocket with the surface VoiceSession uses."""

    def __init__(self, query_params: dict[str, str] | None = None):
        self.query_params = query_params or {}
        self._client: asyncio.Queue = asyncio.Queue()
        self.server: asyncio.Queue = asyncio.Queue()
        self.accepted = False
        self.close_code: int | None = None
        self.close_reason: str | None = None

    async def accept(self) -> None:
        self.accepted = True

    async def send_json(self, data: dict) -> None:
        await self.server.put(data)

    async def receive_json(self) -> dict:
        item = await self._client.get()
        if item is DISCONNECT:
            raise WebSocketDisconnect(code=1000)
        return item

    async def close(self, code: int = 1000, reason: str = "") -> None:
        self.close_code = code
        self.close_reason = reason

    async def client_send(self, data: dict) -> None:
        await self._client.put(data)

    async def client_disconnect(self) -> None:
        await self._client.put(DISCONNECT)

    async def next_message(self, timeout: float = 3.0) -> dict:
        return await asyncio.wait_for(self.server.get(), timeout)

    async def expect_no_message(self, window: float = 1.0) -> None:
        await asyncio.sleep(window)
        if not self.server.empty():
            raise AssertionError(f"unexpected message: {self.server.get_nowait()}")


def make_session(voice: str = "alloy") -> tuple[VoiceSession, FakeWebSocket]:
    websocket = FakeWebSocket()
    session = VoiceSession(
        websocket=websocket,
        model="gpt-4o-realtime-preview",
        api_key="test-key",
        session_id="lifecycle-session",
        system_message="Test instructions",
        voice=voice,
    )
    session._get_ephemeral_key = AsyncMock(
        return_value={
            "client_secret": {"value": "ephemeral-token"},
            "model": session.model,
        }
    )
    return session, websocket


async def run_session(session: VoiceSession) -> asyncio.Task:
    return asyncio.create_task(session.run())


async def wait_for_condition(condition, timeout: float = 3.0) -> None:
    async def poll() -> None:
        while not condition():
            await asyncio.sleep(0.02)

    await asyncio.wait_for(poll(), timeout)


# -----------------------------------------------------------------------------
# Bootstrap
# -----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_bootstrap_sends_init_with_ephemeral_config() -> None:
    session, websocket = make_session()
    task = await run_session(session)

    init = await websocket.next_message()
    assert init["type"] == "ag2.init"
    assert init["config"] == {
        "client_secret": {"value": "ephemeral-token"},
        "model": session.model,
    }
    assert init["init"] == []
    session._get_ephemeral_key.assert_awaited_once()

    await websocket.client_disconnect()
    await asyncio.wait_for(task, 3)


@pytest.mark.asyncio
async def test_bootstrap_failure_sends_error_and_closes_1011() -> None:
    session, websocket = make_session()
    session._get_ephemeral_key = AsyncMock(side_effect=RuntimeError("proxy down"))
    task = await run_session(session)

    error = await websocket.next_message()
    assert error["type"] == "error"
    assert error["error"]["code"] == "session_init_failed"
    assert error["error"]["message"] == "Failed to initialize voice session"

    await asyncio.wait_for(task, 3)
    assert websocket.close_code == 1011
    assert websocket.close_reason == "Session initialization failed"


@pytest.mark.asyncio
async def test_bootstrap_timeout_closes_without_waiting_for_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.realtime import session as session_module

    session, websocket = make_session()
    monkeypatch.setattr(session_module, "EPHEMERAL_KEY_TIMEOUT", 0.01)

    async def stalled_key() -> dict:
        await asyncio.sleep(60)
        return {}

    session._get_ephemeral_key = stalled_key
    await asyncio.wait_for(session.run(), 1)

    assert (await websocket.next_message())["error"]["code"] == "session_init_failed"
    assert websocket.close_code == 1011


@pytest.mark.asyncio
async def test_ephemeral_exchange_registers_tools_and_exposes_only_client_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.realtime import session as session_module

    session, _ = make_session()
    session.register_tool(
        "dispatch_intent",
        "Dispatch an utterance",
        AsyncMock(),
        {"type": "object", "properties": {"utterance": {"type": "string"}}},
    )
    requests = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "client_secret": {"value": "ephemeral-token"},
                "model": session.model,
                "server_secret": "must-stay-server-side",
            },
        )

    transport = httpx.MockTransport(respond)
    original_client = httpx.AsyncClient
    monkeypatch.setattr(
        session_module.httpx,
        "AsyncClient",
        lambda **kwargs: original_client(transport=transport, **kwargs),
    )

    config = await VoiceSession._get_ephemeral_key(session)
    assert config == {
        "client_secret": {"value": "ephemeral-token"},
        "model": session.model,
    }
    assert len(requests) == 1
    request = requests[0]
    assert request.url.path == "/v1/realtime/sessions"
    assert request.headers["Authorization"] == "Bearer test-key"
    body = json.loads(request.content)
    assert body["tools"] == session.tools
    assert body["instructions"] == "Test instructions"
    assert body["voice"] == "alloy"
    assert body["input_audio_transcription"] == {"model": "whisper-1"}


@pytest.mark.asyncio
async def test_ephemeral_exchange_rejects_missing_client_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.realtime import session as session_module

    session, _ = make_session()
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, json={"model": session.model})
    )
    original_client = httpx.AsyncClient
    monkeypatch.setattr(
        session_module.httpx,
        "AsyncClient",
        lambda **kwargs: original_client(transport=transport, **kwargs),
    )

    with pytest.raises(ValueError, match="usable client secret"):
        await VoiceSession._get_ephemeral_key(session)


@pytest.mark.asyncio
async def test_unexpected_session_error_reports_failure_and_closes() -> None:
    session, websocket = make_session()

    async def broken_receive() -> dict:
        raise RuntimeError("internal receive failure")

    websocket.receive_json = broken_receive
    await session.run()

    assert (await websocket.next_message())["type"] == "ag2.init"
    assert await websocket.next_message() == {
        "type": "error",
        "error": {
            "code": "session_failed",
            "message": "Voice session ended unexpectedly",
        },
    }
    assert websocket.close_code == 1011


# -----------------------------------------------------------------------------
# Tool registration
# -----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_register_tool_builds_realtime_tool_schema() -> None:
    session, _ = make_session()
    handler = AsyncMock(return_value="done")
    parameters = {
        "type": "object",
        "properties": {"utterance": {"type": "string"}},
        "required": ["utterance"],
    }

    session.register_tool(
        name="dispatch_intent",
        description="Route an utterance.",
        handler=handler,
        parameters=parameters,
    )

    assert session.tool_handlers["dispatch_intent"] is handler
    assert session.tools == [
        {
            "type": "function",
            "name": "dispatch_intent",
            "description": "Route an utterance.",
            "parameters": parameters,
        }
    ]


# -----------------------------------------------------------------------------
# Complete voice turn
# -----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_complete_voice_turn_end_to_end() -> None:
    session, websocket = make_session()
    on_turn_done = AsyncMock()

    async def surface_switch(surface_type: str) -> dict:
        # Mirrors the /voice endpoint's handler: real continuity logic,
        # endpoint-shaped acknowledgement payload.
        result = await handle_surface_switch(surface_type, session.session_id, session)
        await websocket.send_json(
            {
                "type": "adc.surface_switch_ack",
                "surface": surface_type,
                "pending_count": len(result["pending_results"]),
                "summary": result["catch_up_summary"],
            }
        )

    session.on_turn_done = on_turn_done
    session.on_surface_switch = surface_switch

    async def dispatch_intent(utterance: str) -> str:
        # Tool-as-trigger: acknowledge immediately, deliver the result
        # out-of-band the way the fetch/synthesize strand does.
        assert utterance == "what is the status of whisper-stt?"
        asyncio.get_running_loop().call_later(
            0.05,
            lambda: asyncio.ensure_future(
                session.push_result(
                    {
                        "intent_id": "intent-e2e-1",
                        "topic_id": "topic-e2e-1",
                        "summary": "whisper-stt deploy is healthy",
                        "urgency": "critical",
                        "data": {"project": "whisper-stt"},
                    }
                )
            ),
        )
        return "On it."

    session.register_tool(
        name="dispatch_intent",
        description="Dispatch an utterance.",
        handler=dispatch_intent,
        parameters={
            "type": "object",
            "properties": {"utterance": {"type": "string"}},
            "required": ["utterance"],
        },
    )

    task = await run_session(session)

    # 1. Bootstrap
    init = await websocket.next_message()
    assert init["type"] == "ag2.init"

    # 2. The browser issues a dispatch_intent tool call for the utterance.
    await websocket.client_send(
        {
            "type": "response.function_call_arguments.done",
            "name": "dispatch_intent",
            "call_id": "call-e2e-1",
            "arguments": '{"utterance": "what is the status of whisper-stt?"}',
        }
    )

    # 3. The ack travels back as the tool output.
    tool_output = await websocket.next_message()
    assert tool_output["type"] == "conversation.item.create"
    assert tool_output["item"]["call_id"] == "call-e2e-1"
    assert tool_output["item"]["type"] == "function_call_output"
    assert tool_output["item"]["output"] == "On it."

    # 4. The async result is narrated at the next loop tick.
    narration = await websocket.next_message()
    assert narration["type"] == "adc.narrate_results"
    assert narration["results"] == [
        {
            "intent_id": "intent-e2e-1",
            "topic_id": "topic-e2e-1",
            "summary": "whisper-stt deploy is healthy",
            "urgency": "critical",
        }
    ]
    assert narration["grouped_by_topic"] == {"topic-e2e-1": ["whisper-stt deploy is healthy"]}

    # 5. The turn completes; the memory-extraction callback fires.
    await websocket.client_send(
        {
            "type": "adc.turn_done",
            "user_text": "what is the status of whisper-stt?",
            "assistant_text": "On it. whisper-stt deploy is healthy",
        }
    )
    await wait_for_condition(lambda: on_turn_done.await_count == 1)
    on_turn_done.assert_awaited_once_with(
        "what is the status of whisper-stt?",
        "On it. whisper-stt deploy is healthy",
    )

    # 6. The user moves to the canvas; pending results are handed over.
    await websocket.client_send({"type": "adc.surface_switch", "surface": "canvas"})
    ack = await websocket.next_message()
    assert ack["type"] == "adc.surface_switch_ack"
    assert ack["surface"] == "canvas"
    assert ack["pending_count"] == 1
    assert "one result waiting" in ack["summary"]
    assert session.pending_results == []

    # 7. The client hangs up; the session loop ends cleanly.
    await websocket.client_disconnect()
    await asyncio.wait_for(task, 3)
    assert task.exception() is None


@pytest.mark.asyncio
async def test_disconnect_mid_turn_preserves_pending_results() -> None:
    """A drop mid-turn must not lose results claimed for canvas catch-up."""
    session, websocket = make_session()
    task = await run_session(session)

    await websocket.next_message()  # ag2.init

    result = {
        "intent_id": "intent-drop-1",
        "topic_id": "topic-drop-1",
        "summary": "result before the drop",
        "urgency": "critical",
        "data": {},
    }
    await session.push_result(result)
    await websocket.client_disconnect()

    await asyncio.wait_for(task, 3)
    assert task.exception() is None

    claimed = await session.get_pending_results()
    assert claimed == [result]
    session.ack_pending_results(claimed)
    assert session.pending_results == []


# -----------------------------------------------------------------------------
# Tool-call error handling keeps the session alive
# -----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tool_call_error_paths_keep_session_alive() -> None:
    session, websocket = make_session()

    async def broken_handler() -> str:
        raise RuntimeError("handler exploded")

    session.register_tool(
        name="broken",
        description="Always raises.",
        handler=broken_handler,
        parameters={"type": "object", "properties": {}},
    )

    task = await run_session(session)
    await websocket.next_message()  # ag2.init

    # Unknown tool gets an error output...
    await websocket.client_send(
        {
            "type": "response.function_call_arguments.done",
            "name": "no_such_tool",
            "call_id": "call-unknown-1",
            "arguments": "{}",
        }
    )
    unknown = await websocket.next_message()
    assert unknown["item"]["call_id"] == "call-unknown-1"
    assert unknown["item"]["output"] == '{"error": "No handler: no_such_tool"}'

    # ...a raising handler gets an error output...
    await websocket.client_send(
        {
            "type": "response.function_call_arguments.done",
            "name": "broken",
            "call_id": "call-broken-1",
            "arguments": "{}",
        }
    )
    failed = await websocket.next_message()
    assert failed["item"]["call_id"] == "call-broken-1"
    assert "handler exploded" in failed["item"]["output"]

    # ...and the session still serves the next turn.
    await websocket.client_send(
        {
            "type": "adc.speaking_started",
        }
    )
    await wait_for_condition(lambda: session._is_speaking)

    await websocket.client_disconnect()
    await asyncio.wait_for(task, 3)
    assert task.exception() is None


# -----------------------------------------------------------------------------
# /voice endpoint guards
# -----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_voice_endpoint_rejects_missing_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.main import voice_session

    websocket = FakeWebSocket(query_params={"session_id": "guard-session"})
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    task = asyncio.create_task(voice_session(websocket))
    error = await websocket.next_message()
    assert error == {"type": "error", "error": "OpenAI API key not configured"}

    await asyncio.wait_for(task, 3)
    assert websocket.accepted
    assert websocket.close_code == 1011
    assert websocket.close_reason == "API key missing"


@pytest.mark.asyncio
async def test_voice_endpoint_closes_if_setup_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    from src import main as main_module

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(
        main_module, "get_store", AsyncMock(side_effect=RuntimeError("database unavailable"))
    )
    websocket = FakeWebSocket(query_params={"session_id": "setup-failure"})

    await main_module.voice_session(websocket)

    assert await websocket.next_message() == {
        "type": "error",
        "error": {"code": "session_failed", "message": "Voice session could not start"},
    }
    assert websocket.close_code == 1011


@pytest.mark.asyncio
async def test_voice_endpoint_complete_turn_and_disconnect_cleanup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Drive the public /voice handler through bootstrap, tool, turn and hangup."""
    from src import main as main_module

    store = SimpleNamespace(
        get_session=AsyncMock(return_value={"id": "endpoint-session"}),
        register_surface=AsyncMock(return_value="audio-surface-1"),
        mark_surface_disconnected=AsyncMock(),
    )
    memory = SimpleNamespace(on_turn_done=AsyncMock())
    listener_cancelled = asyncio.Event()
    provisioning_voices = []

    async def fake_key(self: VoiceSession, voice: str | None = None) -> dict:
        provisioning_voices.append(voice or self.voice)
        return {
            "client_secret": {"value": "ephemeral-for-" + (voice or self.voice)},
            "model": self.model,
        }

    async def fake_listener(*args) -> None:
        try:
            await asyncio.Future()
        finally:
            listener_cancelled.set()

    async def fake_dispatch(utterance: str, session_id: str, voice: VoiceSession) -> str:
        assert utterance == "status of the service?"
        assert session_id == "endpoint-session"
        await voice.push_result(
            {
                "intent_id": "endpoint-intent",
                "topic_id": "endpoint-topic",
                "summary": "service is healthy",
                "urgency": "critical",
            }
        )
        return "On it."

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(main_module, "get_store", AsyncMock(return_value=store))
    monkeypatch.setattr(
        main_module,
        "VOICE_PROMPT_PATH",
        Path(__file__).parents[1] / "prompts/voice.md",
    )
    monkeypatch.setattr(main_module, "create_memory_handler", lambda **kwargs: memory)
    monkeypatch.setattr(main_module, "result_listener", fake_listener)
    monkeypatch.setattr(main_module, "dispatch_intent_tool", fake_dispatch)
    monkeypatch.setattr(VoiceSession, "_get_ephemeral_key", fake_key)

    websocket = FakeWebSocket(query_params={"session_id": "endpoint-session"})
    task = asyncio.create_task(main_module.voice_session(websocket))

    init = await websocket.next_message()
    assert init["type"] == "ag2.init"
    assert init["config"]["client_secret"]["value"] == "ephemeral-for-alloy"
    await websocket.client_send(
        {
            "type": "response.function_call_arguments.done",
            "name": "dispatch_intent",
            "call_id": "endpoint-call",
            "arguments": '{"utterance":"status of the service?"}',
        }
    )
    output = await websocket.next_message()
    assert output["item"]["call_id"] == "endpoint-call"
    assert output["item"]["output"] == "On it."
    narration = await websocket.next_message()
    assert narration["type"] == "adc.narrate_results"
    assert narration["results"][0]["summary"] == "service is healthy"

    await websocket.client_send(
        {
            "type": "adc.turn_done",
            "user_text": "status of the service?",
            "assistant_text": "On it. service is healthy",
        }
    )
    await wait_for_condition(lambda: memory.on_turn_done.await_count == 1)
    memory.on_turn_done.assert_awaited_once_with(
        "status of the service?", "On it. service is healthy"
    )

    await websocket.client_send({"type": "adc.session_update", "session": {"voice": "coral"}})
    update = await websocket.next_message()
    assert update["type"] == "adc.session_update"
    assert update["config"]["client_secret"]["value"] == "ephemeral-for-coral"
    await websocket.client_send(
        {"type": "adc.session_updated", "request_id": update["request_id"], "voice": "coral"}
    )
    applied = await websocket.next_message()
    assert applied["type"] == "adc.session_update_applied"
    assert provisioning_voices == ["alloy", "coral"]

    await websocket.client_disconnect()
    await asyncio.wait_for(task, 3)
    assert listener_cancelled.is_set()
    store.mark_surface_disconnected.assert_awaited_once_with("audio-surface-1")
