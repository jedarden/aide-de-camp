"""Typed contracts for events exchanged by the ADC Realtime socket.

The browser-facing socket carries two related protocols: custom ``adc.*``
events and the small subset of Realtime events that ADC handles. Keeping the
contracts here makes the session loop reject bad input before it can mutate
voice, narration, or callback state.
"""

from __future__ import annotations

import json
from typing import Annotated, Any, Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr, field_validator

SUPPORTED_VOICES = (
    "alloy",
    "ash",
    "ballad",
    "coral",
    "echo",
    "sage",
    "shimmer",
    "verse",
)
Voice: TypeAlias = Literal["alloy", "ash", "ballad", "coral", "echo", "sage", "shimmer", "verse"]


class RealtimeEventModel(BaseModel):
    """Base model used by every event contract."""

    model_config = ConfigDict(extra="forbid", strict=True)


class _ClientEvent(RealtimeEventModel):
    event_id: StrictStr | None = None


class FunctionCallArgumentsDoneEvent(_ClientEvent):
    type: Literal["response.function_call_arguments.done"]
    name: Annotated[StrictStr, Field(min_length=1)]
    call_id: Annotated[StrictStr, Field(min_length=1)]
    arguments: StrictStr

    @field_validator("arguments")
    @classmethod
    def arguments_must_be_an_object(cls, value: str) -> str:
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError as exc:
            raise ValueError("arguments must contain valid JSON") from exc
        if not isinstance(parsed, dict):
            raise ValueError("arguments must contain a JSON object")
        return value


class AnnotationEvent(_ClientEvent):
    type: Literal["adc.annotation"]
    annotation: dict[str, Any]


class TurnDoneEvent(_ClientEvent):
    type: Literal["adc.turn_done"]
    user_text: StrictStr
    assistant_text: StrictStr


class SurfaceSwitchEvent(_ClientEvent):
    type: Literal["adc.surface_switch"]
    surface: Literal["audio", "canvas"]


class SessionVoice(RealtimeEventModel):
    voice: Voice


class SessionUpdateEvent(_ClientEvent):
    type: Literal["adc.session_update"]
    session: SessionVoice


class SessionUpdatedEvent(_ClientEvent):
    type: Literal["adc.session_updated"]
    request_id: Annotated[StrictStr, Field(min_length=1)]
    voice: Voice


class SessionUpdateFailedEvent(_ClientEvent):
    type: Literal["adc.session_update_failed"]
    request_id: Annotated[StrictStr, Field(min_length=1)]


class SpeakingStartedEvent(_ClientEvent):
    type: Literal["adc.speaking_started"]


class SpeakingStoppedEvent(_ClientEvent):
    type: Literal["adc.speaking_stopped"]


class ErrorDetails(RealtimeEventModel):
    """The object form used by the upstream Realtime API for errors."""

    type: StrictStr | None = None
    code: StrictStr | None = None
    message: StrictStr | None = None
    param: StrictStr | None = None
    event_id: StrictStr | None = None
    event_type: StrictStr | None = None


class ErrorEvent(_ClientEvent):
    type: Literal["error"]
    error: StrictStr | ErrorDetails


ClientEvent: TypeAlias = (
    FunctionCallArgumentsDoneEvent
    | AnnotationEvent
    | TurnDoneEvent
    | SurfaceSwitchEvent
    | SessionUpdateEvent
    | SessionUpdatedEvent
    | SessionUpdateFailedEvent
    | SpeakingStartedEvent
    | SpeakingStoppedEvent
    | ErrorEvent
)


class EphemeralConfig(RealtimeEventModel):
    client_secret: dict[str, Any]
    model: Annotated[StrictStr, Field(min_length=1)]

    @field_validator("client_secret")
    @classmethod
    def client_secret_must_not_be_empty(cls, value: dict[str, Any]) -> dict[str, Any]:
        if not value:
            raise ValueError("client_secret must not be empty")
        return value


class InitEvent(RealtimeEventModel):
    type: Literal["ag2.init"]
    config: EphemeralConfig
    init: list[Any]


class ServerSessionUpdateEvent(RealtimeEventModel):
    type: Literal["adc.session_update"]
    request_id: Annotated[StrictStr, Field(min_length=1)]
    voice: Voice
    config: EphemeralConfig


class SessionUpdateAppliedEvent(RealtimeEventModel):
    type: Literal["adc.session_update_applied"]
    request_id: Annotated[StrictStr, Field(min_length=1)] | None = None
    voice: Voice


class SessionUpdateRejectedEvent(RealtimeEventModel):
    type: Literal["adc.session_update_rejected"]
    reason: Annotated[StrictStr, Field(min_length=1)]
    available_voices: list[Voice]


class ToolResultItem(RealtimeEventModel):
    type: Literal["function_call_output"]
    call_id: Annotated[StrictStr, Field(min_length=1)]
    output: StrictStr


class ToolResultEvent(RealtimeEventModel):
    type: Literal["conversation.item.create"]
    item: ToolResultItem


class SurfaceSwitchAckEvent(RealtimeEventModel):
    type: Literal["adc.surface_switch_ack"]
    surface: Literal["audio", "canvas"]
    pending_count: StrictInt = Field(ge=0)
    summary: StrictStr


class NarrationResult(RealtimeEventModel):
    intent_id: StrictStr | None = None
    topic_id: StrictStr | None = None
    summary: StrictStr | None = None
    urgency: Literal["critical", "high", "normal", "low"] | None = None


class NarrationEvent(RealtimeEventModel):
    type: Literal["adc.narrate_results"]
    results: list[NarrationResult]
    grouped_by_topic: dict[str, list[StrictStr | None]]


ServerEvent: TypeAlias = (
    InitEvent
    | ServerSessionUpdateEvent
    | SessionUpdateAppliedEvent
    | SessionUpdateRejectedEvent
    | ToolResultEvent
    | SurfaceSwitchAckEvent
    | NarrationEvent
    | ErrorEvent
)


_CLIENT_EVENT_MODELS: dict[str, type[RealtimeEventModel]] = {
    "response.function_call_arguments.done": FunctionCallArgumentsDoneEvent,
    "adc.annotation": AnnotationEvent,
    "adc.turn_done": TurnDoneEvent,
    "adc.surface_switch": SurfaceSwitchEvent,
    "adc.session_update": SessionUpdateEvent,
    "adc.session_updated": SessionUpdatedEvent,
    "adc.session_update_failed": SessionUpdateFailedEvent,
    "adc.speaking_started": SpeakingStartedEvent,
    "adc.speaking_stopped": SpeakingStoppedEvent,
    "error": ErrorEvent,
}

_SERVER_EVENT_MODELS: dict[str, type[RealtimeEventModel]] = {
    "ag2.init": InitEvent,
    "adc.session_update": ServerSessionUpdateEvent,
    "adc.session_update_applied": SessionUpdateAppliedEvent,
    "adc.session_update_rejected": SessionUpdateRejectedEvent,
    "conversation.item.create": ToolResultEvent,
    "adc.surface_switch_ack": SurfaceSwitchAckEvent,
    "adc.narrate_results": NarrationEvent,
    "error": ErrorEvent,
}


class EventValidationError(ValueError):
    """A protocol validation failure with a stable wire error code."""

    def __init__(self, code: str, message: str, event_type: Any = None):
        self.code = code
        self.message = message
        self.event_type = event_type
        suffix = f" ({event_type})" if event_type is not None else ""
        super().__init__(f"{code}{suffix}: {message}")


def _validate(
    payload: Any,
    models: dict[str, type[RealtimeEventModel]],
    direction: str,
) -> RealtimeEventModel:
    if not isinstance(payload, dict):
        raise EventValidationError("malformed_event", "event must be a JSON object")

    event_type = payload.get("type")
    if not isinstance(event_type, str) or not event_type:
        raise EventValidationError("malformed_event", "event.type must be a non-empty string")
    model = models.get(event_type)
    if model is None:
        raise EventValidationError("unknown_event", f"unsupported {direction} event", event_type)
    try:
        return model.model_validate(payload)
    except Exception as exc:
        # Pydantic's detailed error is useful in logs, while the stable code is
        # what the wire protocol exposes.
        raise EventValidationError("malformed_event", str(exc), event_type) from exc


def validate_client_event(payload: Any) -> ClientEvent:
    """Validate and return one event accepted from the browser."""

    return _validate(payload, _CLIENT_EVENT_MODELS, "client")  # type: ignore[return-value]


def validate_server_event(payload: Any) -> ServerEvent:
    """Validate and return one event emitted to the browser."""

    return _validate(payload, _SERVER_EVENT_MODELS, "server")  # type: ignore[return-value]


# Convenient aliases for callers that use the shorter protocol terminology.
validate_event = validate_client_event
FunctionCallCompletionEvent = FunctionCallArgumentsDoneEvent
FunctionCallOutputEvent = ToolResultEvent
