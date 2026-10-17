"""Runtime voice replacement and result continuity for the ADC voice socket."""

from unittest.mock import AsyncMock

import pytest
from starlette.websockets import WebSocketDisconnect

from src.realtime.session import AVAILABLE_VOICES, VoiceSession


def make_session() -> tuple[VoiceSession, AsyncMock]:
    websocket = AsyncMock()
    session = VoiceSession(
        websocket=websocket,
        model="gpt-4o-realtime-preview",
        api_key="test-key",
        session_id="test-session",
        system_message="Test instructions",
    )
    session._get_ephemeral_key = AsyncMock(
        side_effect=lambda voice=None: {
            "client_secret": {"value": f"token-for-{voice or session.voice}"},
            "model": session.model,
        }
    )
    return session, websocket


@pytest.mark.asyncio
async def test_active_voice_change_reconnects_and_preserves_pending_results() -> None:
    session, websocket = make_session()
    result = {"intent_id": "intent-1", "summary": "Important result", "urgency": "critical"}
    await session.push_result(result)

    step = 0

    async def receive_json() -> dict:
        nonlocal step
        step += 1
        if step == 1:
            return {"type": "adc.session_update", "session": {"voice": "coral"}}
        if step == 2:
            request = next(
                call.args[0]
                for call in websocket.send_json.call_args_list
                if call.args[0]["type"] == "adc.session_update"
            )
            # The original voice remains active until the client confirms its peer.
            assert session.voice == "alloy"
            assert session.result_queue.qsize() == 1
            assert session.pending_results == [result]
            return {
                "type": "adc.session_updated",
                "request_id": request["request_id"],
                "voice": "coral",
            }
        raise WebSocketDisconnect(code=1000)

    websocket.receive_json.side_effect = receive_json
    await session.run()

    events = [call.args[0] for call in websocket.send_json.call_args_list]
    request = next(event for event in events if event["type"] == "adc.session_update")
    assert set(request) == {"type", "request_id", "voice", "config"}
    assert request["voice"] == "coral"
    assert request["config"] == {
        "client_secret": {"value": "token-for-coral"},
        "model": session.model,
    }
    assert session._get_ephemeral_key.await_args_list[-1].kwargs == {"voice": "coral"}
    assert {"type": "adc.session_update_applied", "request_id": request["request_id"], "voice": "coral"} in events
    assert any(event["type"] == "adc.narrate_results" and event["results"][0]["intent_id"] == "intent-1" for event in events)
    assert session.voice == "coral"
    assert await session.get_pending_results() == [result]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [
        {"type": "adc.session_update", "session": {"voice": "fable"}},
        {"type": "adc.session_update", "session": {"voice": 1}},
        {"type": "adc.session_update", "session": {"voice": "coral", "model": "other"}},
        {"type": "adc.session_update", "update": {"session": {"voice": "coral"}}},
        {"type": "adc.session_update", "session": {"voice": "coral"}, "extra": True},
    ],
)
async def test_rejects_unsupported_or_malformed_voice_request(payload: dict) -> None:
    session, websocket = make_session()
    await session._handle_session_update(payload)

    websocket.send_json.assert_awaited_once()
    response = websocket.send_json.await_args.args[0]
    assert response["type"] == "adc.session_update_rejected"
    assert response["available_voices"] == AVAILABLE_VOICES
    session._get_ephemeral_key.assert_not_awaited()
    assert session.voice == "alloy"


@pytest.mark.asyncio
async def test_tool_request_and_stale_confirmation() -> None:
    session, websocket = make_session()

    assert "Invalid voice" in await session.change_voice("nova")
    session._get_ephemeral_key.assert_not_awaited()
    assert websocket.send_json.await_count == 0

    assert await session.change_voice("sage") == "Voice change to sage requested."
    request = websocket.send_json.await_args.args[0]
    assert await session.change_voice("coral") == "A voice change is already in progress."
    await session._handle_session_updated({"request_id": "stale", "voice": "sage"})
    await session._handle_session_updated({"request_id": request["request_id"], "voice": "coral"})
    assert session.voice == "alloy"
    await session._handle_session_updated({"request_id": request["request_id"], "voice": "sage"})
    assert session.voice == "sage"
    assert await session.change_voice("sage") == "Voice is already sage."


@pytest.mark.asyncio
async def test_failed_provisioning_keeps_old_voice_and_results() -> None:
    session, websocket = make_session()
    session._get_ephemeral_key = AsyncMock(side_effect=RuntimeError("provider unavailable"))
    result = {"intent_id": "intent-2", "summary": "Later", "urgency": "critical"}
    await session.push_result(result)

    await session._handle_session_update({"type": "adc.session_update", "session": {"voice": "coral"}})

    assert session.voice == "alloy"
    assert session._pending_voice_change is None
    assert session.result_queue.qsize() == 1
    assert session.pending_results == [result]
    assert websocket.send_json.await_args.args[0]["type"] == "adc.session_update_rejected"


@pytest.mark.asyncio
async def test_client_failure_resumes_queued_narration() -> None:
    session, websocket = make_session()
    result = {"intent_id": "intent-3", "summary": "Still waiting", "urgency": "critical"}
    await session.push_result(result)
    await session.change_voice("verse")
    request = websocket.send_json.await_args.args[0]

    assert await session._collect_results_to_narrate() == []
    await session._handle_session_update_failed({"request_id": request["request_id"]})

    assert session.voice == "alloy"
    assert await session._collect_results_to_narrate() == [result]
    assert session.pending_results == [result]
    assert websocket.send_json.await_args.args[0]["type"] == "adc.session_update_rejected"


@pytest.mark.asyncio
async def test_deferred_result_survives_voice_replacement() -> None:
    session, websocket = make_session()
    session._is_speaking = True
    result = {"intent_id": "intent-4", "summary": "Wait for pause", "urgency": "high"}
    await session.push_result(result)

    await session.change_voice("echo")
    request = websocket.send_json.await_args.args[0]
    await session._handle_session_updated({"request_id": request["request_id"], "voice": "echo"})

    assert await session._collect_results_to_narrate() == []
    assert session.result_queue.qsize() == 1
    session._is_speaking = False
    assert await session._collect_results_to_narrate() == [result]
    assert session.pending_results == [result]


@pytest.mark.asyncio
async def test_voice_change_timeout_releases_pending_narration(monkeypatch: pytest.MonkeyPatch) -> None:
    session, websocket = make_session()
    result = {"intent_id": "intent-5", "summary": "After timeout", "urgency": "critical"}
    await session.push_result(result)
    await session.change_voice("ballad")
    requested_at = session._pending_voice_change["requested_at"]
    monkeypatch.setattr("src.realtime.session.time.monotonic", lambda: requested_at + 31)

    await session._expire_voice_change()

    assert session.voice == "alloy"
    assert session._pending_voice_change is None
    assert await session._collect_results_to_narrate() == [result]
    assert websocket.send_json.await_args.args[0]["type"] == "adc.session_update_rejected"


@pytest.mark.asyncio
async def test_current_voice_request_is_acknowledged_without_reconnect() -> None:
    session, websocket = make_session()

    await session._handle_session_update({"type": "adc.session_update", "session": {"voice": "alloy"}})

    session._get_ephemeral_key.assert_not_awaited()
    websocket.send_json.assert_awaited_once_with({
        "type": "adc.session_update_applied",
        "voice": "alloy",
    })
