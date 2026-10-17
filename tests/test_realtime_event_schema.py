"""Realtime wire contracts and negative-path event handling."""

import asyncio
from unittest.mock import AsyncMock

import pytest
from starlette.websockets import WebSocketDisconnect

from src.realtime.schema import (
    EventValidationError,
    validate_client_event,
    validate_server_event,
)
from src.realtime.session import VoiceSession


def test_client_contracts_accept_supported_payloads() -> None:
    payloads = [
        {
            "type": "response.function_call_arguments.done",
            "call_id": "call-1",
            "name": "dispatch_intent",
            "arguments": '{"utterance":"hello"}',
        },
        {"type": "adc.annotation", "annotation": {"topic": "weather"}},
        {"type": "adc.turn_done", "user_text": "hello", "assistant_text": "Hi"},
        {"type": "adc.surface_switch", "surface": "canvas"},
        {"type": "adc.session_update", "session": {"voice": "coral"}},
        {"type": "adc.session_updated", "request_id": "request-1", "voice": "coral"},
        {"type": "adc.session_update_failed", "request_id": "request-1"},
        {"type": "adc.speaking_started"},
        {"type": "adc.speaking_stopped"},
        {"type": "error", "error": {"code": "provider_error", "message": "retry"}},
    ]

    for payload in payloads:
        assert validate_client_event(payload).type == payload["type"]


@pytest.mark.parametrize(
    "payload",
    [
        {"type": "response.function_call_arguments.done", "call_id": "c", "name": "tool"},
        {
            "type": "response.function_call_arguments.done",
            "call_id": "c",
            "name": "tool",
            "arguments": "not-json",
        },
        {"type": "adc.annotation", "annotation": "not-an-object"},
        {"type": "adc.turn_done", "user_text": "hello"},
        {"type": "adc.surface_switch", "surface": "mobile"},
        {"type": "adc.session_update", "session": {"voice": "nova"}},
        {"type": "adc.session_update", "session": {"voice": "coral"}, "extra": True},
        {"type": "adc.session_updated", "request_id": "request-1", "voice": 1},
        {"type": "adc.session_update_failed"},
    ],
)
def test_malformed_payloads_are_rejected(payload: dict) -> None:
    with pytest.raises(EventValidationError) as exc_info:
        validate_client_event(payload)

    assert exc_info.value.code == "malformed_event"


def test_unknown_event_is_rejected_without_a_fallback_handler() -> None:
    with pytest.raises(EventValidationError) as exc_info:
        validate_client_event({"type": "adc.future_event", "value": "ignored"})

    assert exc_info.value.code == "unknown_event"


def test_tool_result_contract_rejects_unknown_fields() -> None:
    valid = {
        "type": "conversation.item.create",
        "item": {"type": "function_call_output", "call_id": "call-1", "output": "ok"},
    }
    assert validate_server_event(valid).type == "conversation.item.create"

    with pytest.raises(EventValidationError) as exc_info:
        validate_server_event({**valid, "request_id": "unexpected"})

    assert exc_info.value.code == "malformed_event"


def make_session(**kwargs) -> tuple[VoiceSession, AsyncMock]:
    websocket = AsyncMock()
    session = VoiceSession(
        websocket=websocket,
        model="gpt-4o-realtime-preview",
        api_key="test-key",
        session_id="test-session",
        system_message="Test instructions",
        **kwargs,
    )
    session._get_ephemeral_key = AsyncMock(
        return_value={
            "client_secret": {"value": "ephemeral"},
            "model": session.model,
        }
    )
    return session, websocket


@pytest.mark.asyncio
async def test_run_reports_malformed_unknown_and_duplicate_events() -> None:
    on_turn_done = AsyncMock()
    session, websocket = make_session(on_turn_done=on_turn_done)
    received = iter(
        [
            {"type": "adc.turn_done"},
            {"type": "adc.unknown"},
            {"type": "adc.turn_done", "user_text": "hello", "assistant_text": "Hi"},
            {"type": "adc.turn_done", "user_text": "hello", "assistant_text": "Hi"},
        ]
    )

    async def receive_json() -> dict:
        try:
            return next(received)
        except StopIteration as exc:
            raise WebSocketDisconnect(code=1000) from exc

    websocket.receive_json.side_effect = receive_json
    await session.run()
    await asyncio.sleep(0)

    errors = [event["error"] for event in _sent_events(websocket) if event["type"] == "error"]
    assert [error["code"] for error in errors] == [
        "malformed_event",
        "unknown_event",
        "duplicate_event",
    ]
    on_turn_done.assert_awaited_once_with("hello", "Hi")


@pytest.mark.asyncio
async def test_duplicate_function_call_is_not_executed_twice() -> None:
    session, websocket = make_session()
    handler = AsyncMock(return_value="ack")
    session.register_tool("dispatch_intent", "dispatch", handler, {"type": "object"})
    call = {
        "type": "response.function_call_arguments.done",
        "call_id": "call-1",
        "name": "dispatch_intent",
        "arguments": "{}",
    }

    await session._handle_client_event(call)
    await session._handle_client_event(call)

    handler.assert_awaited_once_with()
    events = _sent_events(websocket)
    assert sum(event["type"] == "conversation.item.create" for event in events) == 1
    assert any(
        event["type"] == "error" and event["error"]["code"] == "duplicate_event" for event in events
    )


@pytest.mark.asyncio
async def test_session_confirmation_before_request_is_out_of_order() -> None:
    session, websocket = make_session()

    await session._handle_client_event(
        {
            "type": "adc.session_updated",
            "request_id": "missing-request",
            "voice": "coral",
        }
    )

    assert session.voice == "alloy"
    assert _sent_events(websocket) == [
        {
            "type": "error",
            "error": {
                "code": "out_of_order",
                "message": "no matching voice change is pending",
                "event_type": None,
            },
        }
    ]


def _sent_events(websocket: AsyncMock) -> list[dict]:
    return [call.args[0] for call in websocket.send_json.await_args_list]
