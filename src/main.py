"""
ADC (aide-de-camp) - FastAPI Main Entry Point

Voice mode server using OpenAI Realtime API.
Replaces text input with voice session.
"""
import asyncio
import os
import uuid
from logging import getLogger
from pathlib import Path

import httpx
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, StreamingResponse, FileResponse
from pydantic import BaseModel

from .realtime.session import VoiceSession, load_voice_prompt, AVAILABLE_VOICES
from .realtime.dispatch import dispatch_intent, result_listener
from .realtime.continuity import handle_surface_switch
from .session.store import get_store as session_store_get_store
from .sse.broadcaster import SSEBroadcaster, get_broadcaster, EventType, SSEEvent
from .topic.model import TopicManager
from .watcher.daemon import BeadWatcher
from .telegram.fallback import get_telegram_fallback
from .surface.router import SurfaceRouter


logger = getLogger(__name__)
DEFAULT_MODEL = "gpt-4o-realtime-preview"
DEFAULT_VOICE = "alloy"

# Voice prompt path
VOICE_PROMPT_PATH = Path("/home/coding/aide-de-camp/prompts/voice.md")

# Session store
DB_PATH = Path("/home/coding/aide-de-camp/data/session.db")
CANVAS_PATH = Path("/home/coding/aide-de-camp/src/canvas/index.html")

# Global components
_store = None
_broadcaster: Optional[SSEBroadcaster] = None
_topic_manager: Optional[TopicManager] = None
_bead_watcher: Optional[BeadWatcher] = None
_surface_router: Optional[SurfaceRouter] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    global _store, _broadcaster, _topic_manager, _bead_watcher, _surface_router

    logger.info("Starting aide-de-camp...")

    # Initialize data directory
    DB_PATH.parent.mkdir(exist_ok=True)

    # Initialize session store
    _store = session_store_get_store(DB_PATH)
    await _store.initialize()
    logger.info(f"Session store initialized: {DB_PATH}")

    # Initialize SSE broadcaster
    _broadcaster = get_broadcaster()
    await _broadcaster.start()
    logger.info("SSE broadcaster started")

    # Initialize topic manager
    _topic_manager = TopicManager(_store)
    logger.info("Topic manager initialized")

    # Initialize surface router
    _surface_router = SurfaceRouter(_store)
    logger.info("Surface router initialized")

    # Initialize bead watcher
    try:
        _bead_watcher = BeadWatcher(_store, _surface_router)
        await _bead_watcher.start()
        logger.info("Bead watcher started")
    except Exception as e:
        logger.warning(f"Bead watcher failed to start: {e}")
        _bead_watcher = None

    logger.info("aide-de-camp ready")
    yield

    # Shutdown
    logger.info("Shutting down aide-de-camp...")
    if _bead_watcher:
        await _bead_watcher.stop()
    if _broadcaster:
        await _broadcaster.stop()
    if _store:
        await _store.close()
    logger.info("aide-de-camp shutdown complete")


app = FastAPI(title="ADC (aide-de-camp)", version="0.1.0", lifespan=lifespan)


async def get_store():
    """Get or initialize the global session store."""
    global _store
    if _store is None:
        _store = session_store_get_store(DB_PATH)
        await _store.initialize()
    return _store


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "ok", "service": "adc-voice"}


@app.websocket("/voice")
async def voice_session(websocket: WebSocket):
    """
    Voice session endpoint using OpenAI Realtime API.

    Handles:
    - WebRTC connection establishment
    - Tool-as-trigger dispatch_intent calls
    - Async result delivery for narration
    - Surface switch events (audio-to-canvas continuity)
    """
    await websocket.accept()

    # Get session ID from query param or create new
    session_id = websocket.query_params.get("session_id") or str(uuid.uuid4())

    logger.info(f"Voice session connecting: {session_id}")

    # Get API key from environment
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        await websocket.send_json({
            "type": "error",
            "error": "OpenAI API key not configured"
        })
        await websocket.close(code=1011, reason="API key missing")
        return

    # Get or create session
    store = await get_store()
    session = await store.get_session(session_id)
    if not session:
        session_id = await store.create_session()
        logger.info(f"Created new session: {session_id}")

    # Register audio surface
    surface_id = await store.register_surface(session_id, "audio")
    logger.info(f"Registered audio surface: {surface_id}")

    # Load voice prompt
    voice_prompt = load_voice_prompt(VOICE_PROMPT_PATH)

    # Surface switch handler for audio-to-canvas continuity
    async def on_surface_switch(surface_type: str) -> None:
        """Handle surface switch event (audio -> canvas)."""
        logger.info(f"Surface switch: {surface_type}")
        try:
            result = await handle_surface_switch(surface_type, session_id, voice)
            # Send acknowledgment to client
            await websocket.send_json({
                "type": "adc.surface_switch_ack",
                "surface": surface_type,
                "pending_count": len(result["pending_results"]),
                "summary": result["catch_up_summary"],
            })
        except Exception as e:
            logger.error(f"Surface switch error: {e}", exc_info=True)

    # Create voice session
    voice = VoiceSession(
        websocket=websocket,
        model=DEFAULT_MODEL,
        api_key=api_key,
        session_id=session_id,
        system_message=voice_prompt,
        voice=DEFAULT_VOICE,
        logger=logger,
        on_turn_done=None,  # TODO: add memory extraction
        on_surface_switch=on_surface_switch,
    )

    # Start result listener background task
    listener_task = None
    try:
        listener_task = asyncio.create_task(
            result_listener(session_id, voice)
        )

        # Register dispatch_intent tool
        voice.register_tool(
            name="dispatch_intent",
            description=(
                "Dispatch a user utterance to the intent router. "
                "Returns acknowledgment immediately; results arrive asynchronously. "
                "Use this for any utterance that requires system action."
            ),
            handler=lambda utterance: dispatch_intent(utterance, session_id, voice),
            parameters={
                "type": "object",
                "properties": {
                    "utterance": {
                        "type": "string",
                        "description": "The user's utterance to route"
                    }
                },
                "required": ["utterance"]
            }
        )

        # Register change_voice tool
        async def handle_voice_change(voice: str) -> str:
            return await voice.change_voice(voice)

        voice.register_tool(
            name="change_voice",
            description=f"Change the assistant's voice. Available: {', '.join(AVAILABLE_VOICES)}",
            handler=handle_voice_change,
            parameters={
                "type": "object",
                "properties": {
                    "voice": {
                        "type": "string",
                        "enum": AVAILABLE_VOICES,
                        "description": "The voice to switch to"
                    }
                },
                "required": ["voice"]
            }
        )

        # Run the session
        await voice.run()

    except WebSocketDisconnect:
        logger.info(f"Voice session disconnected: {session_id}")
    except Exception as e:
        logger.error(f"Voice session error: {e}", exc_info=True)
        try:
            await websocket.send_json({
                "type": "error",
                "error": str(e)
            })
        except:
            pass
    finally:
        # Cancel listener task
        if listener_task:
            listener_task.cancel()
            try:
                await listener_task
            except asyncio.CancelledError:
                pass

        # Mark surface disconnected
        await store.mark_surface_disconnected(surface_id)
        logger.info(f"Voice session ended: {session_id}")


@app.post("/router")
async def route_intent(request: dict):
    """
    Intent router endpoint (placeholder for Phase 1).

    For now, returns a simple routing result.
    In full implementation, this calls the intent router LLM.
    """
    utterance = request.get("utterance", "")
    utterance_id = request.get("utterance_id")
    session_id = request.get("session_id")

    logger.info(f"Routing utterance: {utterance[:100]}...")

    # Placeholder: return a simple intent
    # Full implementation will call LLM-based router
    store = await get_store()

    # Create a placeholder intent
    intent_id = await store.create_intent(
        utterance_id=utterance_id or str(uuid.uuid4()),
        session_id=session_id,
        project_slug=None,
        intent_type="lookup",  # Placeholder
    )

    # For now, create a placeholder result immediately
    # In full implementation, results arrive from fetch+synthesize
    result_id = await store.create_result(
        intent_id=intent_id,
        topic_id=None,
        session_id=session_id,
        summary="This is a placeholder result. The full router will be implemented in Phase 1.",
        data={"status": "placeholder", "utterance": utterance},
        urgency="normal"
    )

    return {
        "intents": [
            {
                "id": intent_id,
                "intent_type": "lookup",
                "status": "resolved"
            }
        ],
        "results": [
            {
                "id": result_id,
                "summary": "Placeholder result"
            }
        ]
    }


@app.get("/events")
async def canvas_sse(
    session_id: str,
    surface_id: str | None = None,
):
    """
    Server-Sent Events endpoint for canvas connections.

    Provides real-time updates for:
    - Topic changes
    - New results
    - Intent status updates
    - Workload summaries

    Sends workload summary on connect for reconnection support.
    """
    broadcaster = get_broadcaster()

    # Get or create session
    store = await get_store()
    session = await store.get_session(session_id)
    if not session:
        session_id = await store.create_session()
        logger.info(f"Created new session: {session_id}")

    # Register or update surface
    if not surface_id:
        surface_id = await store.register_surface(session_id, "canvas")
        logger.info(f"Registered canvas surface: {surface_id}")
    else:
        await store.update_surface_heartbeat(surface_id)

    # Create SSE connection
    connection = broadcaster.register(
        surface_id=surface_id,
        session_id=session_id,
        surface_type="canvas",
    )

    # Send workload summary on connect
    summary = await store.get_workload_summary(session_id)

    async def event_stream():
        try:
            # Send initial connection event with workload summary
            yield broadcaster._format_sse("connected", {
                "surface_id": surface_id,
                "session_id": session_id,
            })

            yield broadcaster._format_sse("workload_summary", summary)

            # Send initial topic cards
            if _topic_manager:
                cards = await _topic_manager.get_active_topic_cards(session_id)
                yield broadcaster._format_sse("topic_cards", {
                    "cards": [card.to_dict() for card in cards]
                })

            # Stream events
            async for event_data in broadcaster.event_generator(connection):
                yield event_data

        except asyncio.CancelledError:
            logger.info(f"SSE stream cancelled for surface {surface_id}")
            raise

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        },
    )


@app.post("/heartbeat")
async def heartbeat(request: dict):
    """
    Heartbeat endpoint for canvas to update surface last_seen.

    Called periodically by the canvas to prevent surface from being marked idle.
    """
    session_id = request.get("session_id")
    surface_id = request.get("surface_id")

    if not session_id or not surface_id:
        return JSONResponse(
            status_code=400,
            content={"error": "Missing session_id or surface_id"}
        )

    store = await get_store()
    await store.update_surface_heartbeat(surface_id)

    return {"status": "ok"}


@app.get("/topics")
async def get_topics(session_id: str):
    """
    Get active topic cards for a session.

    Returns topics with staleness info for canvas rendering.
    """
    if not _topic_manager:
        return JSONResponse(
            status_code=503,
            content={"error": "Topic manager not initialized"}
        )

    cards = await _topic_manager.get_active_topic_cards(session_id)
    return {
        "topics": [card.to_dict() for card in cards]
    }


@app.on_event("startup")
async def startup():
    """Initialize session store on startup."""
    await get_store()
    logger.info("ADC voice server started")


@app.on_event("shutdown")
async def shutdown():
    """Close session store on shutdown."""
    global _store
    if _store:
        await _store.close()
        logger.info("ADC voice server stopped")
