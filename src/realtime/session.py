"""
ADC Realtime Session

Voice mode implementation using OpenAI Realtime API.
Tool-as-trigger model: dispatch_intent() returns ack immediately; results arrive async.
Based on DUCK-E scaffolding but adapted for ADC's async result delivery pattern.
"""

import asyncio
import json
import os
import threading
import time
from logging import Logger, getLogger
from pathlib import Path
from typing import Any, Callable, Optional
from uuid import uuid4

import httpx
from fastapi import WebSocket
from starlette.websockets import WebSocketDisconnect

from .schema import (
    AnnotationEvent,
    ErrorEvent,
    EventValidationError,
    FunctionCallArgumentsDoneEvent,
    SessionUpdatedEvent,
    SessionUpdateEvent,
    SessionUpdateFailedEvent,
    SpeakingStartedEvent,
    SpeakingStoppedEvent,
    SurfaceSwitchEvent,
    TurnDoneEvent,
    validate_client_event,
    validate_server_event,
)

OPENAI_PROXY_URL = os.environ.get("OPENAI_PROXY_URL", "https://openai-proxy.ardenone.com:8444")


AVAILABLE_VOICES = [
    "alloy",
    "ash",
    "ballad",
    "coral",
    "echo",
    "sage",
    "shimmer",
    "verse",
]

VOICE_CHANGE_TIMEOUT = 30.0

URGENCY_LEVELS = ["critical", "high", "normal", "low"]

# Urgency priorities for narration (lower = higher priority)
URGENCY_PRIORITY = {
    "critical": 0,
    "high": 1,
    "normal": 2,
    "low": 3,
}


class VoiceSession:
    """
    Manages a single OpenAI Realtime API WebRTC session for ADC voice mode.

    Key differences from DUCK-E:
    - Tool-as-trigger: dispatch_intent returns ack immediately
    - Async result delivery: results pushed via result queue and narrated at appropriate moments
    - Urgency-tiered narration: critical interrupts, high waits for pause, normal/low batched
    - Session continuity: pending results tracked for canvas catch-up on surface switch

    Responsibilities:
    - Obtain ephemeral key from OpenAI (server-side)
    - Send ag2.init to browser to bootstrap WebRTC
    - Relay tool calls (dispatch_intent) to backend, return ack immediately
    - Receive async results and queue for narration
    - Handle surface switch events for audio-to-canvas continuity
    """

    def __init__(
        self,
        websocket: WebSocket,
        model: str,
        api_key: str,
        session_id: str,
        system_message: str,
        voice: str = "alloy",
        logger: Optional[Logger] = None,
        on_turn_done: Optional[Callable] = None,
        on_surface_switch: Optional[Callable] = None,
    ):
        self.websocket = websocket
        self.model = model
        self.api_key = api_key
        self.session_id = session_id
        self.system_message = system_message
        self.voice = voice
        self.logger = logger or getLogger(__name__)
        self.on_turn_done = on_turn_done  # async (user_text, assistant_text) -> None
        self.on_surface_switch = on_surface_switch  # async (surface_type) -> None

        self.tools: list[dict[str, Any]] = []
        self.tool_handlers: dict[str, Callable] = {}

        # Result queue for async delivery
        self.result_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self.pending_results: list[dict[str, Any]] = []  # For canvas catch-up
        self._pending_lock = threading.RLock()
        self._pending_in_flight: dict[str, list[dict[str, Any]]] = {}
        self._pending_voice_change: Optional[dict[str, Any]] = None
        self._seen_events: set[str] = set()
        self._completed_tool_calls: set[str] = set()
        self._completed_voice_change_requests: set[str] = set()

        # Narration state
        self.last_narration_time = 0.0
        self.narration_batch_window = 5.0  # Seconds to batch normal/low results
        self._is_speaking = False  # Track if assistant is currently speaking
        self._user_last_spoke = 0.0  # Track when user last spoke

    def register_tool(
        self,
        name: str,
        description: str,
        handler: Callable,
        parameters: dict[str, Any],
    ) -> None:
        """Register a callable tool handler."""
        self.tool_handlers[name] = handler
        self.tools.append(
            {
                "type": "function",
                "name": name,
                "description": description,
                "parameters": parameters,
            }
        )

    async def _get_ephemeral_key(self, voice: Optional[str] = None) -> dict[str, Any]:
        """
        Obtain ephemeral key from OpenAI /v1/realtime/sessions.
        Returns sanitized config (client_secret + model only).
        """
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{OPENAI_PROXY_URL}/v1/realtime/sessions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.model,
                    "voice": voice or self.voice,
                    "instructions": self.system_message,
                    "tools": self.tools,
                    "input_audio_transcription": {"model": "whisper-1"},
                },
            )
            resp.raise_for_status()
            data = resp.json()

        return {
            "client_secret": data["client_secret"],
            "model": data.get("model", self.model),
        }

    async def change_voice(self, voice: str) -> str:
        """Request a fresh Realtime connection with a supported voice.

        Realtime cannot update the voice after its first audio output. The
        browser reconnects its WebRTC peer with the fresh credentials, while
        this VoiceSession keeps its result queues and canvas catch-up state.
        """
        if not isinstance(voice, str) or voice not in AVAILABLE_VOICES:
            return f"Invalid voice '{voice}'. Available: {', '.join(AVAILABLE_VOICES)}"
        if self._pending_voice_change:
            return "A voice change is already in progress."
        if voice == self.voice:
            return f"Voice is already {voice}."

        try:
            config = await self._get_ephemeral_key(voice=voice)
            request_id = str(uuid4())
            self._pending_voice_change = {
                "request_id": request_id,
                "voice": voice,
                "requested_at": time.monotonic(),
            }
            await self._send_event(
                {
                    "type": "adc.session_update",
                    "request_id": request_id,
                    "voice": voice,
                    "config": config,
                }
            )
            self.logger.info("Requested voice change to %s", voice)
            return f"Voice change to {voice} requested."
        except Exception as e:
            self._pending_voice_change = None
            self.logger.error(f"Failed to change voice: {e}", exc_info=True)
            return f"Failed to change voice: {str(e)}"

    async def _handle_session_update(self, data: dict[str, Any]) -> None:
        """Validate a direct client voice-change request."""
        session = data.get("session")
        if (
            set(data).difference({"type", "session", "event_id"})
            or not isinstance(session, dict)
            or set(session) != {"voice"}
            or not isinstance(session["voice"], str)
            or session["voice"] not in AVAILABLE_VOICES
        ):
            await self._reject_voice_change("Expected session.voice with a supported voice")
            return

        if session["voice"] == self.voice and not self._pending_voice_change:
            await self._send_event(
                {
                    "type": "adc.session_update_applied",
                    "voice": self.voice,
                }
            )
            return

        result = await self.change_voice(session["voice"])
        if (
            result.startswith("Invalid voice")
            or result.startswith("Failed to change")
            or result.startswith("A voice change")
        ):
            await self._reject_voice_change(result)

    async def _reject_voice_change(self, reason: str) -> None:
        await self._send_event(
            {
                "type": "adc.session_update_rejected",
                "reason": reason,
                "available_voices": AVAILABLE_VOICES,
            }
        )

    async def _handle_session_updated(self, data: dict[str, Any]) -> None:
        """Accept confirmation only for the outstanding WebRTC replacement."""
        pending = self._pending_voice_change
        request_id = data.get("request_id")
        if request_id in self._completed_voice_change_requests:
            await self._send_protocol_error("duplicate_event", "voice change was already completed")
            return
        if not pending or request_id != pending["request_id"]:
            await self._send_protocol_error("out_of_order", "no matching voice change is pending")
            return
        if data.get("voice") != pending["voice"]:
            await self._send_protocol_error(
                "out_of_order", "voice confirmation does not match the request"
            )
            return
        self.voice = pending["voice"]
        self._pending_voice_change = None
        self._completed_voice_change_requests.add(pending["request_id"])
        self.logger.info("Voice change applied: %s", self.voice)
        await self._send_event(
            {
                "type": "adc.session_update_applied",
                "request_id": pending["request_id"],
                "voice": self.voice,
            }
        )

    async def _handle_session_update_failed(self, data: dict[str, Any]) -> None:
        pending = self._pending_voice_change
        request_id = data.get("request_id")
        if request_id in self._completed_voice_change_requests:
            await self._send_protocol_error("duplicate_event", "voice change was already completed")
        elif pending and request_id == pending["request_id"]:
            self._pending_voice_change = None
            self._completed_voice_change_requests.add(request_id)
            await self._reject_voice_change("Client could not activate the new voice")
        else:
            await self._send_protocol_error("out_of_order", "no matching voice change is pending")

    async def _expire_voice_change(self) -> None:
        pending = self._pending_voice_change
        if pending and time.monotonic() - pending["requested_at"] >= VOICE_CHANGE_TIMEOUT:
            self._pending_voice_change = None
            await self._reject_voice_change("Voice change timed out before client confirmation")

    async def push_result(self, result: dict[str, Any]) -> None:
        """
        Push an async result to the queue for narration.

        Result format:
        {
            "intent_id": str,
            "summary": str,
            "urgency": "critical" | "high" | "normal" | "low",
            "data": dict,
            "surfaced_at": float (timestamp),
        }
        """
        result["surfaced_at"] = time.time()
        await self.result_queue.put(result)

        # Track for canvas catch-up
        with self._pending_lock:
            self.pending_results.append(result)

        self.logger.info(
            json.dumps(
                {
                    "event": "result_queued",
                    "intent_id": result.get("intent_id"),
                    "urgency": result.get("urgency"),
                    "summary": result.get("summary")[:100],
                    "ts": time.time(),
                }
            )
        )

    async def get_pending_results(self) -> list[dict[str, Any]]:
        """
        Return pending results for canvas catch-up.
        Clears the pending list after returning.
        """
        with self._pending_lock:
            results = list(self.pending_results)
            if not results:
                return []
            # Claim before returning. The caller can acknowledge or requeue
            # the same batch if processing/canvas delivery fails.
            token = str(uuid4())
            self.pending_results = []
            self._pending_in_flight[token] = results
        return results

    def ack_pending_results(self, results: list[dict[str, Any]]) -> None:
        """Acknowledge a catch-up batch after the caller consumes it."""
        with self._pending_lock:
            for token, claimed in list(self._pending_in_flight.items()):
                if claimed is results or claimed == results:
                    self._pending_in_flight.pop(token, None)
                    return

    def nack_pending_results(self, results: list[dict[str, Any]]) -> None:
        """Return an unconsumed catch-up batch to the ready queue."""
        with self._pending_lock:
            for token, claimed in list(self._pending_in_flight.items()):
                if claimed is results or claimed == results:
                    self._pending_in_flight.pop(token, None)
                    # Requeue at the front so result order survives retry.
                    self.pending_results[0:0] = claimed
                    return

    def _should_narrate_now(self, result: dict[str, Any]) -> bool:
        """
        Determine if a result should be narrated now based on urgency and state.

        Rules:
        - Critical: Always interrupt immediately
        - High: Wait for natural pause (not mid-sentence)
        - Normal: Batch within ~5s window or at topic transition
        - Low: Only if conversation is idle
        """
        urgency = result.get("urgency", "normal")
        now = time.time()

        if urgency == "critical":
            return True  # Always interrupt

        if urgency == "high":
            # Wait for pause in assistant speaking
            return not self._is_speaking

        if urgency == "normal":
            # Batch within window or at topic transition
            time_since_last = now - self.last_narration_time
            return time_since_last >= self.narration_batch_window

        if urgency == "low":
            # Only if idle (no user or assistant activity recently)
            idle_time = min(now - self._user_last_spoke, now - self.last_narration_time)
            return idle_time >= 10.0  # 10 seconds of idle

        return False

    async def _collect_results_to_narrate(self) -> list[dict[str, Any]]:
        """
        Collect results from the queue that should be narrated now.

        Returns results grouped by urgency, respecting batching rules.
        """
        # The browser is replacing its WebRTC peer; retain every result until
        # the new peer is ready (or the request times out).
        if self._pending_voice_change:
            return []

        to_narrate = []
        now = time.time()

        # Drain the queue (non-blocking)
        while not self.result_queue.empty():
            try:
                result = self.result_queue.get_nowait()
                to_narrate.append(result)
            except asyncio.QueueEmpty:
                break

        if not to_narrate:
            return []

        # Sort by urgency priority (critical first)
        to_narrate.sort(key=lambda r: URGENCY_PRIORITY.get(r.get("urgency", "normal"), 99))

        # Filter based on what should be narrated now
        ready = []
        deferred = []
        for result in to_narrate:
            (ready if self._should_narrate_now(result) else deferred).append(result)
        for result in deferred:
            self.result_queue.put_nowait(result)

        # For batching: group normal/low results together
        if ready:
            self.last_narration_time = now

        return ready

    async def _send_narration_event(self, results: list[dict[str, Any]]) -> None:
        """
        Send a narration event to the client.

        Results are batched by topic for efficient narration.
        """
        if not results:
            return

        # Group by topic_id
        by_topic: dict[str, list[dict]] = {}
        for result in results:
            topic_id = result.get("topic_id", "general")
            if topic_id not in by_topic:
                by_topic[topic_id] = []
            by_topic[topic_id].append(result)

        # Send batched event
        await self._send_event(
            {
                "type": "adc.narrate_results",
                "results": [
                    {
                        "intent_id": r.get("intent_id"),
                        "topic_id": r.get("topic_id"),
                        "summary": r.get("summary"),
                        "urgency": r.get("urgency"),
                    }
                    for r in results
                ],
                "grouped_by_topic": {
                    topic_id: [r.get("summary") for r in topic_results]
                    for topic_id, topic_results in by_topic.items()
                },
            }
        )

        self.logger.info(
            json.dumps(
                {
                    "event": "narration.sent",
                    "count": len(results),
                    "urgencies": [r.get("urgency") for r in results],
                    "ts": time.time(),
                }
            )
        )

    async def _send_event(self, payload: dict[str, Any]) -> None:
        """Validate an outbound event before it crosses the WebSocket."""
        validate_server_event(payload)
        await self.websocket.send_json(payload)

    async def _send_protocol_error(
        self, code: str, message: str, event_type: str | None = None
    ) -> None:
        await self._send_event(
            {
                "type": "error",
                "error": {
                    "code": code,
                    "message": message,
                    "event_type": event_type,
                },
            }
        )

    def _event_key(self, event: Any) -> str:
        """Return an idempotency key for a validated event.

        Realtime events normally carry ``event_id``. ADC custom events from
        older clients do not, so their canonical payload is used as a safe
        fallback for exact retries.
        """
        event_id = getattr(event, "event_id", None)
        if event_id:
            return f"event_id:{event_id}"
        payload = event.model_dump(exclude_none=True)
        if isinstance(event, FunctionCallArgumentsDoneEvent):
            return f"tool_call:{event.call_id}"
        return json.dumps(payload, sort_keys=True, separators=(",", ":"))

    async def _handle_client_event(self, data: Any) -> None:
        """Validate, deduplicate, and dispatch one browser event."""
        try:
            event = validate_client_event(data)
        except EventValidationError as exc:
            await self._send_protocol_error(exc.code, exc.message, exc.event_type)
            return

        event_key = self._event_key(event)
        if event_key in self._seen_events:
            await self._send_protocol_error(
                "duplicate_event", "event was already processed", event.type
            )
            return
        self._seen_events.add(event_key)

        if isinstance(event, FunctionCallArgumentsDoneEvent):
            await self._handle_tool_call(event.model_dump(exclude_none=True))
        elif isinstance(event, SessionUpdateEvent):
            await self._handle_session_update(event.model_dump(exclude_none=True))
        elif isinstance(event, SessionUpdatedEvent):
            await self._handle_session_updated(event.model_dump(exclude_none=True))
        elif isinstance(event, SessionUpdateFailedEvent):
            await self._handle_session_update_failed(event.model_dump(exclude_none=True))
        elif isinstance(event, AnnotationEvent):
            self.logger.info("Annotation: %s", event.annotation)
        elif isinstance(event, TurnDoneEvent):
            if self.on_turn_done:
                asyncio.create_task(self.on_turn_done(event.user_text, event.assistant_text))
            self._user_last_spoke = time.time()
        elif isinstance(event, SurfaceSwitchEvent):
            if self.on_surface_switch:
                await self.on_surface_switch(event.surface)
        elif isinstance(event, SpeakingStartedEvent):
            self._is_speaking = True
        elif isinstance(event, SpeakingStoppedEvent):
            self._is_speaking = False
        elif isinstance(event, ErrorEvent):
            self.logger.error("Realtime client error: %s", event.error)

    async def run(self) -> None:
        """Main session loop."""
        try:
            session_data = await self._get_ephemeral_key()
        except Exception as e:
            self.logger.error(f"Failed to get ephemeral key: {e}", exc_info=True)
            await self._send_event(
                {
                    "type": "error",
                    "error": f"Failed to initialize session: {str(e)}",
                }
            )
            await self.websocket.close(code=1011, reason="Session initialization failed")
            return

        await self._send_event(
            {
                "type": "ag2.init",
                "config": session_data,
                "init": [],
            }
        )

        try:
            while True:
                # Wait for websocket messages with timeout to check results
                try:
                    data = await asyncio.wait_for(
                        self.websocket.receive_json(),
                        timeout=0.5,  # Check results every 500ms
                    )
                    await self._handle_client_event(data)

                except asyncio.TimeoutError:
                    # Timeout is expected - check for results to narrate
                    pass

                await self._expire_voice_change()

                # Check for results to narrate
                results_to_narrate = await self._collect_results_to_narrate()
                if results_to_narrate:
                    await self._send_narration_event(results_to_narrate)

        except WebSocketDisconnect:
            pass
        except Exception as e:
            self.logger.error(f"Session error: {e}", exc_info=True)

    async def _handle_tool_call(self, data: dict[str, Any]) -> None:
        """
        Execute a tool handler and return result.

        For dispatch_intent, this returns an ack immediately.
        Actual results arrive via push_result().
        """
        name = data.get("name")
        call_id = data.get("call_id")
        if call_id in self._completed_tool_calls:
            await self._send_protocol_error("duplicate_event", "tool call was already completed")
            return
        self._completed_tool_calls.add(call_id)
        t_received = time.monotonic()

        self.logger.info(
            json.dumps(
                {
                    "event": "tool_call.received",
                    "tool": name,
                    "call_id": call_id,
                    "ts": time.time(),
                }
            )
        )

        args = json.loads(data["arguments"])

        handler = self.tool_handlers.get(name)
        if not handler:
            self.logger.warning(f"No handler for tool: {name}")
            await self._send_tool_result(call_id, json.dumps({"error": f"No handler: {name}"}))
            return

        t_handler_start = time.monotonic()

        try:
            if asyncio.iscoroutinefunction(handler):
                result = await handler(**args)
            else:
                result = handler(**args)
        except Exception as e:
            self.logger.error(f"Tool handler error for '{name}': {e}", exc_info=True)
            result = json.dumps({"error": str(e)})

        t_handler_end = time.monotonic()

        self.logger.info(
            json.dumps(
                {
                    "event": "tool_call.handler_done",
                    "tool": name,
                    "call_id": call_id,
                    "result_size": len(str(result)),
                    "handler_duration_ms": round((t_handler_end - t_handler_start) * 1000, 1),
                    "ts": time.time(),
                }
            )
        )

        await self._send_tool_result(call_id, str(result))

        t_sent = time.monotonic()
        self.logger.info(
            json.dumps(
                {
                    "event": "tool_call.result_sent",
                    "tool": name,
                    "call_id": call_id,
                    "total_duration_ms": round((t_sent - t_received) * 1000, 1),
                    "ts": time.time(),
                }
            )
        )

    async def _send_tool_result(self, call_id: str, result: str) -> None:
        """Send tool result back to client."""
        await self._send_event(
            {
                "type": "conversation.item.create",
                "item": {
                    "type": "function_call_output",
                    "call_id": call_id,
                    "output": result,
                },
            }
        )


def load_voice_prompt(prompt_path: Path) -> str:
    """Load voice system prompt from file."""
    if prompt_path.exists():
        return prompt_path.read_text()
    return (
        "You are ADC (aide-de-camp), a universal personal interface. "
        "You route voice input to parallel agents and narrate results efficiently."
    )
