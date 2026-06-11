"""
ADC Realtime Session

Voice mode implementation using OpenAI Realtime API.
Tool-as-trigger model: dispatch_intent() returns ack immediately; results arrive async.
Based on DUCK-E scaffolding but adapted for ADC's async result delivery pattern.
"""
import asyncio
import httpx
import json
import os
import time
from logging import Logger, getLogger
from pathlib import Path
from typing import Any, Callable, Optional

OPENAI_PROXY_URL = os.environ.get("OPENAI_PROXY_URL", "https://openai-proxy.ardenone.com:8444")

from fastapi import WebSocket
from starlette.websockets import WebSocketDisconnect


AVAILABLE_VOICES = [
    "alloy", "ash", "ballad", "coral", "echo",
    "fable", "nova", "onyx", "sage", "shimmer", "verse"
]

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
        self.tools.append({
            "type": "function",
            "name": name,
            "description": description,
            "parameters": parameters,
        })

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
        """Change voice via session.update event."""
        if voice not in AVAILABLE_VOICES:
            return (
                f"Invalid voice '{voice}'. "
                f"Available: {', '.join(AVAILABLE_VOICES)}"
            )

        try:
            self.logger.info(f"Changing voice to: {voice}")
            self.voice = voice

            await self.websocket.send_json({
                "type": "adc.session_update",
                "update": {
                    "type": "session.update",
                    "session": {"voice": voice},
                },
            })
            return f"Voice changed to {voice}."
        except Exception as e:
            self.logger.error(f"Failed to change voice: {e}", exc_info=True)
            return f"Failed to change voice: {str(e)}"

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
        self.pending_results.append(result)

        self.logger.info(json.dumps({
            "event": "result_queued",
            "intent_id": result.get("intent_id"),
            "urgency": result.get("urgency"),
            "summary": result.get("summary")[:100],
            "ts": time.time(),
        }))

    async def get_pending_results(self) -> list[dict[str, Any]]:
        """
        Return pending results for canvas catch-up.
        Clears the pending list after returning.
        """
        results = self.pending_results.copy()
        self.pending_results.clear()
        return results

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
            idle_time = min(
                now - self._user_last_spoke,
                now - self.last_narration_time
            )
            return idle_time >= 10.0  # 10 seconds of idle

        return False

    async def _collect_results_to_narrate(self) -> list[dict[str, Any]]:
        """
        Collect results from the queue that should be narrated now.

        Returns results grouped by urgency, respecting batching rules.
        """
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
        ready = [r for r in to_narrate if self._should_narrate_now(r)]

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
        await self.websocket.send_json({
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
        })

        self.logger.info(json.dumps({
            "event": "narration.sent",
            "count": len(results),
            "urgencies": [r.get("urgency") for r in results],
            "ts": time.time(),
        }))

    async def run(self) -> None:
        """Main session loop."""
        try:
            session_data = await self._get_ephemeral_key()
        except Exception as e:
            self.logger.error(f"Failed to get ephemeral key: {e}", exc_info=True)
            await self.websocket.send_json({
                "type": "error",
                "error": f"Failed to initialize session: {str(e)}",
            })
            await self.websocket.close(code=1011, reason="Session initialization failed")
            return

        await self.websocket.send_json({
            "type": "ag2.init",
            "config": session_data,
            "init": [],
        })

        try:
            while True:
                # Wait for websocket messages with timeout to check results
                try:
                    data = await asyncio.wait_for(
                        self.websocket.receive_json(),
                        timeout=0.5  # Check results every 500ms
                    )
                    msg_type = data.get("type", "")

                    if msg_type == "response.function_call_arguments.done":
                        await self._handle_tool_call(data)
                    elif msg_type == "adc.annotation":
                        annotation = data.get("annotation", {})
                        self.logger.info(f"Annotation: {annotation}")
                    elif msg_type == "adc.turn_done":
                        if self.on_turn_done:
                            user_text = data.get("user_text", "")
                            assistant_text = data.get("assistant_text", "")
                            asyncio.create_task(
                                self.on_turn_done(user_text, assistant_text)
                            )
                        # Update user activity tracking
                        self._user_last_spoke = time.time()
                    elif msg_type == "adc.surface_switch":
                        # User switching from audio to canvas
                        surface_type = data.get("surface", "canvas")
                        if self.on_surface_switch:
                            await self.on_surface_switch(surface_type)
                    elif msg_type == "adc.speaking_started":
                        self._is_speaking = True
                    elif msg_type == "adc.speaking_stopped":
                        self._is_speaking = False

                except asyncio.TimeoutError:
                    # Timeout is expected - check for results to narrate
                    pass

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
        t_received = time.monotonic()

        self.logger.info(json.dumps({
            "event": "tool_call.received",
            "tool": name,
            "call_id": call_id,
            "ts": time.time(),
        }))

        try:
            args = json.loads(data.get("arguments", "{}"))
        except json.JSONDecodeError:
            args = {}

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

        self.logger.info(json.dumps({
            "event": "tool_call.handler_done",
            "tool": name,
            "call_id": call_id,
            "result_size": len(str(result)),
            "handler_duration_ms": round((t_handler_end - t_handler_start) * 1000, 1),
            "ts": time.time(),
        }))

        await self._send_tool_result(call_id, str(result))

        t_sent = time.monotonic()
        self.logger.info(json.dumps({
            "event": "tool_call.result_sent",
            "tool": name,
            "call_id": call_id,
            "total_duration_ms": round((t_sent - t_received) * 1000, 1),
            "ts": time.time(),
        }))

    async def _send_tool_result(self, call_id: str, result: str) -> None:
        """Send tool result back to client."""
        await self.websocket.send_json({
            "type": "conversation.item.create",
            "item": {
                "type": "function_call_output",
                "call_id": call_id,
                "output": result,
            },
        })


def load_voice_prompt(prompt_path: Path) -> str:
    """Load voice system prompt from file."""
    if prompt_path.exists():
        return prompt_path.read_text()
    return (
        "You are ADC (aide-de-camp), a universal personal interface. "
        "You route voice input to parallel agents and narrate results efficiently."
    )
