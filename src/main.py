"""
ADC (aide-de-camp) - FastAPI Main Entry Point

Voice mode server using OpenAI Realtime API.
Replaces text input with voice session.
"""
import asyncio
import logging
import os
import time
import uuid
from logging import getLogger
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s %(name)s: %(message)s",
)

import httpx
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query
from fastapi.responses import JSONResponse, StreamingResponse, FileResponse
from pydantic import BaseModel

from .realtime.session import VoiceSession, load_voice_prompt, AVAILABLE_VOICES
from .realtime.dispatch import dispatch_intent, result_listener
from .realtime.continuity import handle_surface_switch
from ._version import read_version
from .session.store import get_store as session_store_get_store
from .memory.extraction import create_memory_handler
from .sse.broadcaster import SSEBroadcaster, get_broadcaster, EventType, SSEEvent
from .topic.model import TopicManager
from .watcher.daemon import BeadWatcher
from .telegram.fallback import get_telegram_fallback
from .surface.router import SurfaceRouter
from .feedback.processor import (
    get_feedback_processor,
    FeedbackRequest,
    FeedbackType,
    FeedbackResponse,
)
from .agents.self_modification import ArtifactType
from .components.library import get_library
from .components.hot_reload import get_reload_manager
from .monitoring.ambient import get_ambient_monitor
from .context.warmer import get_context_warmer
from .feedback.background_analysis import get_background_processor
from .intent.router import get_router as get_intent_router
from .escalate import escalate_intent, EscalateRequest
from .test.dispatch import router as test_router
from .environment.discovery import (
    scan_environment, set_registry,
    refresh_registry, start_background_refresh, stop_background_refresh,
    get_last_scan_at,
)
from .registry import get_registry as get_yaml_registry


logger = getLogger(__name__)
DEFAULT_MODEL = "gpt-4o-realtime-preview"
DEFAULT_VOICE = "alloy"

# Voice prompt path
VOICE_PROMPT_PATH = Path("/home/coding/aide-de-camp/prompts/voice.md")

# Session store
DB_PATH = Path("/home/coding/aide-de-camp/data/session.db")
CANVAS_PATH = Path("/home/coding/aide-de-camp/src/canvas/index.html")
# Canvas render helpers (createTopicCard + friends) — served separately so they
# are unit-testable headlessly (tests/e2e/canvas_dom_runner.js).
CANVAS_JS_PATH = Path("/home/coding/aide-de-camp/src/canvas/canvas.js")

# Global components
_store = None
_broadcaster: Optional[SSEBroadcaster] = None
_topic_manager: Optional[TopicManager] = None
_bead_watcher: Optional[BeadWatcher] = None
_surface_router: Optional[SurfaceRouter] = None
_feedback_processor = None
_component_library = None
_reload_manager = None
_ambient_monitor = None
_context_warmer = None
_background_processor = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    global _store, _broadcaster, _topic_manager, _bead_watcher, _surface_router
    global _feedback_processor, _component_library, _reload_manager
    global _ambient_monitor, _context_warmer, _background_processor

    logger.info("Starting aide-de-camp...")

    # Discover local + remote environment (git repos + bead workspaces)
    registry = await scan_environment()
    set_registry(registry)
    s = registry.summary()
    logger.info(f"Environment registry: {s['total_repos']} repos ({s['local_repos']} local, {s['remote_repos']} remote), {s['beaded_repos']} with beads")
    await start_background_refresh()

    # Initialize data directory
    DB_PATH.parent.mkdir(exist_ok=True)
    Path("/home/coding/aide-de-camp/data").mkdir(exist_ok=True)

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

    # Initialize component library
    _component_library = get_library()
    logger.info("Component library initialized")

    # Initialize hot-reload manager
    _reload_manager = get_reload_manager()
    logger.info("Hot-reload manager initialized")

    # Initialize feedback processor
    _feedback_processor = get_feedback_processor()
    logger.info("Feedback processor initialized")

    # Initialize ambient monitor (Phase 3)
    _ambient_monitor = get_ambient_monitor()
    await _ambient_monitor.start()
    logger.info("Ambient monitor started")

    # Initialize context warmer (Phase 3)
    _context_warmer = get_context_warmer()
    await _context_warmer.start()
    logger.info("Context warmer started")

    # Initialize background analysis processor (Phase 3)
    _background_processor = get_background_processor()
    await _background_processor.start()
    logger.info("Background analysis processor started")

    # Check Telegram bridge reachability
    try:
        telegram_fallback = get_telegram_fallback()
        bridge_available = await telegram_fallback.check_bridge_available()
        if bridge_available:
            logger.info(f"Telegram bridge reachable at {telegram_fallback.bridge_url}")
        else:
            logger.warning(
                f"Telegram bridge unreachable at {telegram_fallback.bridge_url}. "
                f"Telegram fallback will not be available."
            )
    except Exception as e:
        logger.warning(f"Failed to check Telegram bridge reachability: {e}")

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
    stop_background_refresh()
    if _bead_watcher:
        await _bead_watcher.stop()
    if _background_processor:
        await _background_processor.stop()
    if _context_warmer:
        await _context_warmer.stop()
    if _ambient_monitor:
        await _ambient_monitor.stop()
    if _broadcaster:
        await _broadcaster.stop()
    if _component_library:
        _component_library.close()
    if _store:
        await _store.close()
    logger.info("aide-de-camp shutdown complete")


app = FastAPI(title="ADC (aide-de-camp)", version=read_version(), lifespan=lifespan)

# Include test router
app.include_router(test_router, prefix="/api/v1", tags=["test"])


async def get_store():
    """Get or initialize the global session store."""
    global _store
    if _store is None:
        _store = session_store_get_store(DB_PATH)
        await _store.initialize()
    return _store


@app.get("/health")
async def health_check():
    """Health check endpoint.

    Returns overall service status and watcher liveness block (alive, last_tick_at,
    tick_count, interval). Watcher alive is true only while the task is running
    AND last_tick_at is within 2x the poll interval. If _bead_watcher is None
    (failed start), watcher.alive is false.
    """
    response = {
        "status": "ok",
        "service": "adc-voice",
    }
    if _bead_watcher is not None:
        response["watcher"] = _bead_watcher.health_snapshot()
    else:
        # Watcher failed to start or not initialized
        response["watcher"] = {
            "alive": False,
            "last_tick_at": None,
            "tick_count": 0,
            "interval": 0,
        }
    return response


@app.get("/")
async def serve_canvas():
    """
    Serve the canvas HTML page (Phase 0 minimal surface).

    This is the main entry point for the aide-de-camp interface.
    """
    return FileResponse(CANVAS_PATH)


@app.get("/canvas.js")
async def serve_canvas_js():
    """Serve the canvas render helpers (createTopicCard + friends).

    Loaded by index.html via ``<script src="/canvas.js">``. Kept as a separate
    module so the rendering logic is unit-testable headlessly
    (``tests/e2e/canvas_dom_runner.js``) without spinning up a browser.
    """
    return FileResponse(CANVAS_JS_PATH, media_type="application/javascript")


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
    audio_surface_id = await store.register_surface(session_id, "audio")
    surface_id = audio_surface_id
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

    # Memory extraction handler for turn completion
    memory_handler = create_memory_handler(session_id=session_id, api_key=api_key)
    if memory_handler:
        logger.info(f"Memory extraction enabled for session: {session_id}")

    # Create voice session
    voice = VoiceSession(
        websocket=websocket,
        model=DEFAULT_MODEL,
        api_key=api_key,
        session_id=session_id,
        system_message=voice_prompt,
        voice=DEFAULT_VOICE,
        logger=logger,
        on_turn_done=memory_handler.on_turn_done if memory_handler else None,
        on_surface_switch=on_surface_switch,
    )

    # Start result listener background task
    listener_task = None
    try:
        listener_task = asyncio.create_task(
            result_listener(session_id, voice, audio_surface_id)
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
    Intent router endpoint.

    Classifies utterances into intent types and routes to appropriate strands.
    Task-profile intents are escalated to NEEDLE beads.
    Other intents are routed to fetch + synthesize strands.
    """
    utterance = request.get("utterance", "")
    utterance_id = request.get("utterance_id")
    session_id = request.get("session_id")

    logger.info(f"Routing utterance: {utterance[:100]}...")

    store = await get_store()
    router = get_intent_router(store)

    # Generate utterance ID if not provided
    if not utterance_id:
        utterance_id = str(uuid.uuid4())

    # Create utterance record
    await store.create_utterance(session_id, utterance, utterance_id)

    # Route the utterance
    try:
        routed_intents = await router.route_utterance(
            utterance=utterance,
            utterance_id=utterance_id,
            session_id=session_id,
        )

        # Process each routed intent
        intent_results = []
        for routed_intent in routed_intents:
            # Create intent record in store
            classification = routed_intent.classification
            await store.create_intent(
                utterance_id=utterance_id,
                session_id=session_id,
                project_slug=classification.project_slug,
                intent_type=classification.intent_type.value,
                lookup_kind=classification.lookup_kind,
            )

            # Process the intent (escalate or fetch+synthesize)
            result = await router.process_intent(routed_intent)
            intent_results.append(result)

        return {
            "utterance_id": utterance_id,
            "intents": intent_results,
        }

    except Exception as e:
        logger.error(f"Router error: {e}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"error": f"Router error: {str(e)}"}
        )


@app.post("/dispatch")
async def dispatch_intent(request: dict):
    """
    Dispatch endpoint: router → N parallel synthesize calls → SSE stream.

    Phase 0 core query loop:
    1. Routes utterance to intents via intent router
    2. For each intent, runs fetch + synthesize strands in parallel
    3. Streams results via SSE to active canvas
    4. Returns acknowledgment with intent IDs

    Returns acknowledgment immediately with intent IDs for tracking.
    Results are streamed via SSE to connected canvas surfaces.
    """
    utterance = request.get("utterance", "")
    utterance_id = request.get("utterance_id")
    session_id = request.get("session_id")
    surface_id = request.get("surface_id")

    logger.info(f"Dispatching utterance: {utterance[:100]}...")

    store = await get_store()
    router = get_intent_router(store)

    # Generate utterance ID if not provided
    if not utterance_id:
        utterance_id = str(uuid.uuid4())

    # Create utterance record
    await store.create_utterance(session_id, utterance, utterance_id)

    # Route the utterance
    try:
        routed_intents = await router.route_utterance(
            utterance=utterance,
            utterance_id=utterance_id,
            session_id=session_id,
        )

        # Create intent records and process in parallel
        intent_tasks = []
        intent_ids = []

        for routed_intent in routed_intents:
            # Create intent record in store
            classification = routed_intent.classification
            await store.create_intent(
                utterance_id=utterance_id,
                session_id=session_id,
                project_slug=classification.project_slug,
                intent_type=classification.intent_type.value,
                lookup_kind=classification.lookup_kind,
            )
            intent_ids.append(routed_intent.intent_id)

            # Create task for parallel processing
            task = asyncio.create_task(
                router.process_intent(routed_intent),
                name=f"process_{routed_intent.intent_id[:8]}"
            )
            intent_tasks.append((routed_intent.intent_id, task))

        # Process intents in parallel and stream results via SSE
        async def stream_results():
            """Process intents and stream results to SSE."""
            results = []

            for intent_id, task in intent_tasks:
                try:
                    result = await task
                    results.append(result)

                    # Broadcast result_created so canvas reloads topics
                    if _broadcaster and surface_id:
                        emit_start = time.monotonic()
                        # Include rendered card HTML in SSE so canvas injects it directly
                        # (Component card when matched, fallback when card_fallback=True)
                        sse_data = {
                            "intent_id": intent_id,
                            "topic_id": result.get("topic_id"),
                            "summary": result.get("summary"),
                            "urgency": result.get("urgency"),
                        }
                        # Add component_id when available (for canvas tracking)
                        if result.get("component_id") is not None:
                            sse_data["component_id"] = result["component_id"]
                        # Add card_fallback flag when available (signals client to use fallback)
                        if result.get("card_fallback") is not None:
                            sse_data["card_fallback"] = result["card_fallback"]

                        await _broadcaster.broadcast(
                            SSEEvent(
                                event_type="result_created",
                                target_surface_id=surface_id,
                                data=sse_data,
                                rendered_html=result.get("rendered_html"),
                            )
                        )
                        # Record the SSE emit cost for this intent thread
                        # (Latency Budget & Instrumentation). Non-fatal.
                        try:
                            await store.record_dispatch_timings(
                                intent_id,
                                sse_emit_ms=int((time.monotonic() - emit_start) * 1000),
                            )
                        except Exception as te:
                            logger.warning(f"sse_emit timing not recorded for {intent_id}: {te}")

                except Exception as e:
                    logger.error(f"Intent processing failed: {e}")
                    results.append({
                        "intent_id": intent_id,
                        "status": "error",
                        "error": str(e),
                    })

            return results

        # Start parallel processing in background
        asyncio.create_task(stream_results())

        # Return acknowledgment immediately
        return {
            "utterance_id": utterance_id,
            "session_id": session_id,
            "intent_count": len(intent_ids),
            "intent_ids": intent_ids,
            "status": "dispatched",
            "message": f"Dispatched {len(intent_ids)} intents for parallel processing",
        }

    except Exception as e:
        logger.error(f"Dispatch error: {e}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"error": f"Dispatch error: {str(e)}"}
        )


@app.post("/api/v1/timings")
async def report_client_timings(request: dict):
    """Record client-reported dispatch timings for an intent thread.

    The server-side stages (router/fetch/synthesize/escalate/sse_emit_ms) are
    recorded by the router and the /dispatch endpoint; this endpoint is the wire
    for the two client-reported stages in the latency budget — STT final
    transcript (stt_ms) and first card render (first_render_ms) — which only the
    client can measure (see Latency Budget & Instrumentation in docs/plan/plan.md).
    Both are nullable: a dispatch with no client reporter (the text box, the
    /api/v1/test/dispatch harness) simply never calls this and those columns
    stay NULL.

    Body: {"intent_id": "...", "stt_ms": 312, "first_render_ms": 90}
    Either timing field is optional; intent_id is required.
    """
    intent_id = request.get("intent_id")
    if not intent_id:
        return JSONResponse(
            status_code=400,
            content={"error": "intent_id is required"},
        )

    fields: dict[str, int] = {}
    for name in ("stt_ms", "first_render_ms"):
        value = request.get(name)
        if value is not None:
            fields[name] = int(value)

    store = await get_store()
    try:
        # Upserts into the existing server-written row (created_at unchanged);
        # if no server row exists yet this still creates one keyed by the
        # client-reported intent_id so the timing is never lost.
        await store.record_dispatch_timings(intent_id, **fields)
    except Exception as e:
        logger.warning(f"client timings not recorded for {intent_id}: {e}")
        return JSONResponse(
            status_code=500,
            content={"error": f"Failed to record timings: {e}"},
        )

    return {"ok": True, "intent_id": intent_id, "recorded": list(fields.keys())}


@app.get("/api/v1/timings/percentiles")
async def get_latency_percentiles_endpoint(since: int | None = None):
    """Aggregate p50/p95 per dispatch stage (Latency Budget & Instrumentation).

    Returns ``{stage: {"p50": ms, "p95": ms, "count": n}}`` for every stage
    that has at least one captured sample. The latency-baseline bead consumes
    the un-windowed store helper directly; this endpoint exposes the same
    numbers over HTTP for the Phase 5 rehearsal checklist and on-demand
    inspection. Optional ``since`` (unix timestamp) windows to recent
    dispatches only.
    """
    store = await get_store()
    return await store.get_latency_percentiles(since=since)


@app.post("/escalate")
async def escalate_endpoint(request: dict):
    """
    Escalate an intent to a NEEDLE bead for durable async handling.

    For task-profile intents that require tracking and async execution:
    - Formulates bead body via LLM
    - Creates bead via bf CLI
    - Returns pending-card spec
    """
    utterance = request.get("utterance", "")
    utterance_id = request.get("utterance_id")
    session_id = request.get("session_id")
    intent_type = request.get("intent_type", "task-profile")
    project_slug = request.get("project_slug")
    topic_id = request.get("topic_id")
    metadata = request.get("metadata", {})
    context = request.get("context", {})

    logger.info(f"Escalating intent for session {session_id}: {utterance[:100]}...")

    # Create escalate request
    escalate_request = EscalateRequest(
        intent_id=str(uuid.uuid4()),
        session_id=session_id,
        utterance=utterance,
        intent_type=intent_type,
        project_slug=project_slug,
        topic_id=topic_id,
        context=context,
        metadata=metadata,
    )

    # Store the intent
    store = await get_store()
    if utterance_id:
        intent_id = await store.create_intent(
            utterance_id=utterance_id,
            session_id=session_id,
            project_slug=project_slug,
            intent_type=intent_type,
        )
        escalate_request.intent_id = intent_id

    try:
        # Escalate to bead
        result = await escalate_intent(escalate_request)

        logger.info(f"Escalated intent {escalate_request.intent_id} to bead {result.bead_id}")

        return {
            "intent_id": result.intent_id,
            "bead_id": result.bead_id,
            "status": result.status,
            "pending_card": result.pending_card,
        }

    except Exception as e:
        logger.error(f"Escalate failed: {e}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"error": f"Escalate failed: {str(e)}"}
        )


@app.get("/api/v1/environment")
async def get_environment():
    """Return the discovered environment: all git repos and bead workspaces across all hosts."""
    from .environment.discovery import get_registry
    import time
    registry = get_registry()
    if not registry:
        return {"error": "Registry not yet initialized"}
    entries = [
        {
            "name": e.name,
            "slug": e.slug,
            "path": str(e.path),
            "host": e.host,
            "display_path": e.display_path,
            "has_beads": e.has_beads,
            "remote_url": e.remote_url,
            "remote_name": e.remote_name,
        }
        for e in sorted(registry.all_entries(), key=lambda x: (x.host or "", x.slug))
    ]
    summary = registry.summary()
    return {
        "total_repos": summary["total_repos"],
        "beaded_repos": summary["beaded_repos"],
        "local_repos": summary["local_repos"],
        "remote_repos": summary["remote_repos"],
        "remote_hosts": summary["remote_hosts"],
        "last_scan_at": get_last_scan_at(),
        "repos": entries,
    }


@app.get("/api/v1/registry")
async def get_registry_endpoint():
    """Return the merged project registry (config/registry.yaml + discovery).

    This is the DB-independent data source for the first-run welcome card (the
    built-in family #2 — see plan, Component Library → Built-in cards, and Cold
    start & demo seed). The welcome card renders even against an empty
    components.db because the project list comes from this YAML-backed registry,
    not the component DB. Returns only the welcome-relevant fields per project
    (slug, name, description, intent_support, aliases) so no internal paths leak
    to the served frontend.
    """
    reg = get_yaml_registry()
    projects = []
    for slug, entry in (reg.get("projects") or {}).items():
        projects.append({
            "slug": slug,
            "name": slug,
            "description": entry.get("description") or "",
            "intent_support": entry.get("intent_support") or [],
            "aliases": entry.get("aliases") or [],
        })
    return {"projects": projects}


@app.post("/api/v1/environment/refresh")
async def trigger_environment_refresh():
    """Trigger an immediate environment rescan to discover new repos."""
    import time
    registry = await refresh_registry()
    s = registry.summary()
    return {
        "status": "refreshed",
        "total_repos": s["total_repos"],
        "local_repos": s["local_repos"],
        "remote_repos": s["remote_repos"],
        "remote_hosts": s["remote_hosts"],
        "beaded_repos": s["beaded_repos"],
        "scanned_at": get_last_scan_at(),
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


# =============================================================================
# API v1 Endpoints
# =============================================================================

# Pydantic models for API requests/responses
class SurfaceRegisterRequest(BaseModel):
    session_id: str
    surface_type: str


class HeartbeatRequest(BaseModel):
    session_id: str
    surface_id: str


class FeedbackRequestModel(BaseModel):
    feedback: str
    feedback_type: str = "self_modification"
    context: Optional[dict] = None
    session_id: Optional[str] = None
    require_approval: bool = True


class ApprovalRequest(BaseModel):
    approval_id: str


class RollbackRequest(BaseModel):
    artifact_name: str
    artifact_type: str


class ComponentCreateRequest(BaseModel):
    name: str
    description: str
    html_template: str
    change_note: str = "Initial version"


class ComponentUpdateRequest(BaseModel):
    component_id: str
    html_template: str
    change_note: str


class ComponentIterateRequest(BaseModel):
    component_id: str
    feedback: str
    result_data: Optional[dict] = None


class UsagePatternRecord(BaseModel):
    """Request body for recording component usage patterns."""
    component_id: str
    result_type: str
    match_score: float
    layout_bucket: str = "normal"


# Canvas and Surface endpoints
@app.post("/api/v1/surfaces/register")
async def api_v1_register_surface(request: SurfaceRegisterRequest):
    """Register a new surface for a session."""
    store = await get_store()

    # Get or create session
    session = await store.get_session(request.session_id)
    if not session:
        session_id = await store.create_session()
        logger.info(f"Created new session: {session_id}")
    else:
        session_id = request.session_id

    # Register surface
    surface_id = await store.register_surface(
        session_id,
        request.surface_type
    )

    return {
        "surface_id": surface_id,
        "session_id": session_id
    }


@app.post("/api/v1/surfaces/heartbeat")
async def api_v1_heartbeat(request: HeartbeatRequest):
    """Update surface heartbeat."""
    store = await get_store()
    await store.update_surface_heartbeat(request.surface_id)
    return {"status": "ok"}


@app.get("/api/v1/sessions/{session_id}/topics")
async def api_v1_get_session_topics(session_id: str):
    """Get active topic cards for a session (canvas format)."""
    if not _topic_manager:
        return JSONResponse(
            status_code=503,
            content={"error": "Topic manager not initialized"}
        )

    cards = await _topic_manager.get_active_topic_cards(session_id)
    return {
        "cards": [card.to_dict() for card in cards]
    }


@app.delete("/api/v1/sessions/{session_id}/results/{result_id}")
async def api_v1_delete_result(session_id: str, result_id: str):
    """Delete a result card by ID, ensuring it belongs to the specified session.

    Used by the canvas to dismiss stuck/failed cards.
    Returns the number of results deleted (0 or 1).
    """
    store = await get_store()

    # Delete the result with session isolation
    deletion_result = await store.delete_result(result_id, session_id)

    return deletion_result


@app.get("/api/v1/sse")
async def api_v1_sse(
    session_id: str,
    surface_id: Optional[str] = None,
    surface_type: str = "canvas"
):
    """
    Server-Sent Events endpoint for canvas connections.

    Provides real-time updates for topics, results, and component updates.
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
        surface_id = await store.register_surface(session_id, surface_type)
        logger.info(f"Registered {surface_type} surface: {surface_id}")
    else:
        await store.update_surface_heartbeat(surface_id)

    # Create SSE connection
    connection = broadcaster.register(
        surface_id=surface_id,
        session_id=session_id,
        surface_type=surface_type,
    )

    # Send workload summary on connect
    summary = await store.get_workload_summary(session_id)

    async def event_stream():
        try:
            # Send initial connection event
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
            "X-Accel-Buffering": "no",
        },
    )


# Feedback and Self-Modification endpoints
@app.post("/api/v1/feedback")
async def api_v1_process_feedback(request: FeedbackRequestModel):
    """
    Process user feedback for self-modification or component iteration.

    Returns a diff for approval or confirmation of application.
    """
    if not _feedback_processor:
        return JSONResponse(
            status_code=503,
            content={"error": "Feedback processor not initialized"}
        )

    # Map string to enum
    feedback_type_map = {
        "self_modification": FeedbackType.SELF_MODIFICATION,
        "component_iteration": FeedbackType.COMPONENT_ITERATION,
        "routing_correction": FeedbackType.ROUTING_CORRECTION,
        "behavior_adjustment": FeedbackType.BEHAVIOR_ADJUSTMENT,
    }

    feedback_type = feedback_type_map.get(
        request.feedback_type,
        FeedbackType.SELF_MODIFICATION
    )

    feedback_req = FeedbackRequest(
        feedback=request.feedback,
        feedback_type=feedback_type,
        context=request.context,
        session_id=request.session_id,
        require_approval=request.require_approval
    )

    response = await _feedback_processor.process_feedback(feedback_req)

    return {
        "status": response.status,
        "message": response.message,
        "confidence": response.confidence,
        "artifact_name": response.artifact_name,
        "artifact_type": response.artifact_type.value if response.artifact_type else None,
        "approval_id": getattr(response, 'approval_id', None),
        "diff": {
            "artifact_name": response.diff.artifact_name,
            "artifact_type": response.diff.artifact_type.value,
            "change_summary": response.diff.change_summary,
            "confidence": response.diff.confidence,
            # Don't include full before/after in response to save space
            # Client can fetch separately if needed
        } if response.diff else None
    }


@app.post("/api/v1/feedback/approve")
async def api_v1_approve_change(request: ApprovalRequest):
    """Approve and apply a pending change."""
    if not _feedback_processor:
        return JSONResponse(
            status_code=503,
            content={"error": "Feedback processor not initialized"}
        )

    response = await _feedback_processor.approve_change(request.approval_id)

    return {
        "status": response.status,
        "message": response.message,
        "artifact_name": response.artifact_name,
    }


@app.post("/api/v1/feedback/reject")
async def api_v1_reject_change(request: ApprovalRequest, reason: Optional[str] = None):
    """Reject a pending change."""
    if not _feedback_processor:
        return JSONResponse(
            status_code=503,
            content={"error": "Feedback processor not initialized"}
        )

    response = await _feedback_processor.reject_change(request.approval_id, reason)

    return {
        "status": response.status,
        "message": response.message,
    }


@app.get("/api/v1/feedback/pending")
async def api_v1_list_pending():
    """List all pending feedback approvals."""
    if not _feedback_processor:
        return JSONResponse(
            status_code=503,
            content={"error": "Feedback processor not initialized"}
        )

    return {
        "pending": _feedback_processor.list_pending_approvals()
    }


@app.post("/api/v1/feedback/rollback")
async def api_v1_rollback(request: RollbackRequest):
    """Rollback an artifact to its previous version."""
    if not _feedback_processor:
        return JSONResponse(
            status_code=503,
            content={"error": "Feedback processor not initialized"}
        )

    # Map string to enum
    artifact_type_map = {
        "prompt": ArtifactType.PROMPT,
        "config": ArtifactType.CONFIG,
        "component": ArtifactType.COMPONENT,
    }

    artifact_type = artifact_type_map.get(
        request.artifact_type,
        ArtifactType.PROMPT
    )

    response = await _feedback_processor.rollback(
        request.artifact_name,
        artifact_type
    )

    return {
        "status": response.status,
        "message": response.message,
    }


# Component Library endpoints
@app.get("/api/v1/components")
async def api_v1_list_components(limit: int = 50):
    """List all components in the library."""
    if not _component_library:
        return JSONResponse(
            status_code=503,
            content={"error": "Component library not initialized"}
        )

    components = _component_library.list_components(limit=limit)
    return {
        "components": [
            {
                "id": c.id,
                "name": c.name,
                "description": c.description,
                "version": c.version,
                "usage_count": c.usage_count,
                "last_used": c.last_used,
            }
            for c in components
        ]
    }


# =============================================================================
# Usage patterns routes (must come before /{component_id} routes to avoid conflicts)
# =============================================================================

@app.post("/api/v1/patterns")
async def api_v1_record_pattern(request: UsagePatternRecord):
    """Record or update a component usage pattern.

    Simple endpoint for recording component usage patterns.
    Upserts pattern (update if exists, insert if new) and sets updated_at to current timestamp.

    Request body:
        - result_type: str - The type of result
        - component_id: str - The component that was used
        - layout_bucket: str - The layout bucket used (default 'normal')
        - match_score: float - How well the component matched (0.0-1.0)

    Returns:
        {"status": "ok", "pattern": {...}} on success
    """
    if not _component_library:
        return JSONResponse(
            status_code=503,
            content={"error": "Component library not initialized"}
        )

    try:
        # Validate inputs
        if not request.component_id or not request.result_type:
            return JSONResponse(
                status_code=400,
                content={"error": "component_id and result_type are required"}
            )

        if not 0.0 <= request.match_score <= 1.0:
            return JSONResponse(
                status_code=400,
                content={"error": "match_score must be between 0.0 and 1.0"}
            )

        if request.layout_bucket not in _component_library.LAYOUT_BUCKETS:
            return JSONResponse(
                status_code=400,
                content={"error": f"layout_bucket must be one of {', '.join(_component_library.LAYOUT_BUCKETS)}"}
            )

        # Record the pattern (upsert: update if exists, insert if new)
        _component_library.record_usage_pattern(
            component_id=request.component_id,
            result_type=request.result_type,
            match_score=request.match_score,
            layout_bucket=request.layout_bucket,
        )

        logger.info(
            f"Recorded usage pattern: component={request.component_id}, "
            f"result_type={request.result_type}, layout_bucket={request.layout_bucket}, "
            f"match_score={request.match_score}"
        )

        return {
            "status": "ok",
            "pattern": {
                "component_id": request.component_id,
                "result_type": request.result_type,
                "layout_bucket": request.layout_bucket,
                "match_score": request.match_score,
            }
        }

    except Exception as e:
        logger.error(f"Failed to record usage pattern: {e}")
        return JSONResponse(
            status_code=500,
            content={"error": f"Failed to record usage pattern: {str(e)}"}
        )


@app.get("/api/v1/patterns")
async def api_v1_get_patterns(result_type: str = Query(..., description="Result type to filter patterns (required)")):
    """Get component usage patterns by result_type.

    Query params:
        result_type: Filter by result type (required)

    Returns:
        {"patterns": [...]} ordered by match_score DESC
        404 if no patterns found for the result_type
    """
    if not _component_library:
        return JSONResponse(
            status_code=503,
            content={"error": "Component library not initialized"}
        )

    try:
        import sqlite3

        conn = _component_library._get_conn()

        # Query patterns for the specified result_type, ordered by match_score DESC
        query = """
            SELECT result_type, component_id, layout_bucket, match_score, sample_count, updated_at
            FROM component_usage_patterns
            WHERE result_type = ?
            ORDER BY match_score DESC, sample_count DESC
        """

        rows = conn.execute(query, (result_type,)).fetchall()

        # Return 404 if no patterns found
        if not rows:
            return JSONResponse(
                status_code=404,
                content={"error": f"No patterns found for result_type: {result_type}"}
            )

        patterns = [
            {
                "result_type": row[0],
                "component_id": row[1],
                "layout_bucket": row[2],
                "match_score": row[3],
                "sample_count": row[4],
                "updated_at": row[5],
            }
            for row in rows
        ]

        return {
            "patterns": patterns,
            "count": len(patterns),
        }

    except Exception as e:
        logger.error(f"Failed to get usage patterns: {e}")
        return JSONResponse(
            status_code=500,
            content={"error": f"Failed to get usage patterns: {str(e)}"}
        )


@app.post("/api/v1/components/usage-patterns")
async def api_v1_record_usage_pattern(request: UsagePatternRecord):
    """Record or update a component usage pattern.

    Called by the UI-regen agent to record pattern mappings discovered during
    component generation or iteration. This endpoint updates the
    component_usage_patterns table with the latest match score and usage data.

    Returns:
        {"status": "ok", "pattern": {...}} on success
    """
    if not _component_library:
        return JSONResponse(
            status_code=503,
            content={"error": "Component library not initialized"}
        )

    try:
        # Validate inputs
        if not request.component_id or not request.result_type:
            return JSONResponse(
                status_code=400,
                content={"error": "component_id and result_type are required"}
            )

        if not 0.0 <= request.match_score <= 1.0:
            return JSONResponse(
                status_code=400,
                content={"error": "match_score must be between 0.0 and 1.0"}
            )

        if request.layout_bucket not in _component_library.LAYOUT_BUCKETS:
            return JSONResponse(
                status_code=400,
                content={"error": f"layout_bucket must be one of {', '.join(_component_library.LAYOUT_BUCKETS)}"}
            )

        # Record the pattern
        _component_library.record_usage_pattern(
            component_id=request.component_id,
            result_type=request.result_type,
            match_score=request.match_score,
            layout_bucket=request.layout_bucket,
        )

        logger.info(
            f"Recorded usage pattern: component={request.component_id}, "
            f"result_type={request.result_type}, layout_bucket={request.layout_bucket}, "
            f"match_score={request.match_score}"
        )

        return {
            "status": "ok",
            "pattern": {
                "component_id": request.component_id,
                "result_type": request.result_type,
                "layout_bucket": request.layout_bucket,
                "match_score": request.match_score,
            }
        }

    except Exception as e:
        logger.error(f"Failed to record usage pattern: {e}")
        return JSONResponse(
            status_code=500,
            content={"error": f"Failed to record usage pattern: {str(e)}"}
        )


@app.get("/api/v1/components/usage-patterns")
async def api_v1_list_usage_patterns(
    result_type: Optional[str] = Query(None, description="Filter by result type"),
    component_id: Optional[str] = Query(None, description="Filter by component ID"),
    limit: int = Query(100, description="Maximum number of patterns to return"),
):
    """List component usage patterns, optionally filtered.

    Query params:
        result_type: Filter by result type (optional)
        component_id: Filter by component ID (optional)
        limit: Maximum number of patterns to return (default 100)

    Returns:
        {"patterns": [...], "count": <total>}
    """
    if not _component_library:
        return JSONResponse(
            status_code=503,
            content={"error": "Component library not initialized"}
        )

    try:
        import sqlite3

        conn = _component_library._get_conn()

        # Build query with filters
        where_clauses = []
        params = []

        if result_type:
            where_clauses.append("result_type = ?")
            params.append(result_type)

        if component_id:
            where_clauses.append("component_id = ?")
            params.append(component_id)

        where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"

        query = f"""
            SELECT result_type, component_id, layout_bucket, match_score, sample_count, updated_at
            FROM component_usage_patterns
            WHERE {where_sql}
            ORDER BY match_score DESC, sample_count DESC
            LIMIT ?
        """

        params.append(limit)

        rows = conn.execute(query, params).fetchall()

        patterns = [
            {
                "result_type": row[0],
                "component_id": row[1],
                "layout_bucket": row[2],
                "match_score": row[3],
                "sample_count": row[4],
                "updated_at": row[5],
            }
            for row in rows
        ]

        # Get total count
        count_query = f"SELECT COUNT(*) FROM component_usage_patterns WHERE {where_sql}"
        count_params = params[:-1]  # Exclude limit
        total = conn.execute(count_query, count_params).fetchone()[0]

        return {
            "patterns": patterns,
            "count": total,
        }

    except Exception as e:
        logger.error(f"Failed to list usage patterns: {e}")
        return JSONResponse(
            status_code=500,
            content={"error": f"Failed to list usage patterns: {str(e)}"}
        )


# =============================================================================
# Component-specific routes (/{component_id} routes must come after specific paths)
# =============================================================================

@app.get("/api/v1/components/{component_id}")
async def api_v1_get_component(component_id: str):
    """Get a component by ID."""
    if not _component_library:
        return JSONResponse(
            status_code=503,
            content={"error": "Component library not initialized"}
        )

    component = _component_library.get_component(component_id)
    if not component:
        return JSONResponse(
            status_code=404,
            content={"error": "Component not found"}
        )

    return {
        "id": component.id,
        "name": component.name,
        "description": component.description,
        "html_template": component.html_template,
        "version": component.version,
        "usage_count": component.usage_count,
        "last_used": component.last_used,
    }


@app.post("/api/v1/components")
async def api_v1_create_component(request: ComponentCreateRequest):
    """Create a new component."""
    if not _component_library:
        return JSONResponse(
            status_code=503,
            content={"error": "Component library not initialized"}
        )

    component = _component_library.create_component(
        name=request.name,
        description=request.description,
        html_template=request.html_template,
        change_note=request.change_note
    )

    return {
        "id": component.id,
        "name": component.name,
        "version": component.version,
        "message": f"Component '{component.name}' created",
    }


@app.post("/api/v1/components/{component_id}")
async def api_v1_update_component(component_id: str, request: ComponentUpdateRequest):
    """Update a component to a new version."""
    if not _component_library:
        return JSONResponse(
            status_code=503,
            content={"error": "Component library not initialized"}
        )

    updated = _component_library.update_component(
        component_id=component_id,
        html_template=request.html_template,
        change_note=request.change_note
    )

    if not updated:
        return JSONResponse(
            status_code=404,
            content={"error": "Component not found"}
        )

    # Broadcast component update via SSE so connected canvases update in place.
    broadcaster = get_broadcaster()
    await broadcaster.broadcast(
        SSEEvent(
            event_type=EventType.COMPONENT_UPDATED,
            data={
                "component_id": updated.id,
                "version": updated.version,
            },
        )
    )

    return {
        "id": updated.id,
        "name": updated.name,
        "version": updated.version,
        "message": f"Component '{updated.name}' updated to version {updated.version}",
    }


@app.post("/api/v1/components/{component_id}/iterate")
async def api_v1_iterate_component(component_id: str, request: ComponentIterateRequest):
    """Iterate a component based on user feedback."""
    if not _feedback_processor:
        return JSONResponse(
            status_code=503,
            content={"error": "Feedback processor not initialized"}
        )

    # Use the feedback processor to handle component iteration
    feedback_req = FeedbackRequest(
        feedback=request.feedback,
        feedback_type=FeedbackType.COMPONENT_ITERATION,
        context={"component_id": component_id, "result_data": request.result_data},
        require_approval=False  # Auto-apply component iterations
    )

    response = await _feedback_processor.process_feedback(feedback_req)

    return {
        "status": response.status,
        "message": response.message,
        "component_name": response.artifact_name,
    }


@app.get("/api/v1/components/{component_id}/history")
async def api_v1_get_component_history(component_id: str):
    """Get version history for a component."""
    if not _component_library:
        return JSONResponse(
            status_code=503,
            content={"error": "Component library not initialized"}
        )

    history = _component_library.get_component_history(component_id)
    return {
        "history": [
            {
                "component_id": h.component_id,
                "version": h.version,
                "created_at": h.created_at,
                "change_note": h.change_note,
            }
            for h in history
        ]
    }


@app.get("/api/v1/artifacts")
async def api_v1_list_artifacts():
    """List all hot-reloadable artifacts."""
    if not _reload_manager:
        return JSONResponse(
            status_code=503,
            content={"error": "Hot-reload manager not initialized"}
        )

    return {
        "artifacts": _reload_manager.list_artifacts()
    }


@app.get("/api/v1/artifacts/{artifact_name}")
async def api_v1_get_artifact(artifact_name: str):
    """Get an artifact's current content."""
    if not _reload_manager:
        return JSONResponse(
            status_code=503,
            content={"error": "Hot-reload manager not initialized"}
        )

    try:
        # Try as prompt first
        content = _reload_manager.get_prompt(artifact_name)
        artifact_type = "prompt"
    except KeyError:
        try:
            # Try as config
            content = _reload_manager.get_config(artifact_name)
            artifact_type = "config"
        except KeyError:
            return JSONResponse(
                status_code=404,
                content={"error": "Artifact not found"}
            )

    return {
        "name": artifact_name,
        "type": artifact_type,
        "content": content if artifact_type == "prompt" else str(content),
    }


@app.post("/api/v1/artifacts/{artifact_name}/reload")
async def api_v1_reload_artifact(artifact_name: str):
    """Force reload an artifact from disk."""
    if not _reload_manager:
        return JSONResponse(
            status_code=503,
            content={"error": "Hot-reload manager not initialized"}
        )

    try:
        _reload_manager.force_reload(artifact_name)
        return {
            "status": "ok",
            "message": f"Artifact '{artifact_name}' reloaded"
        }
    except KeyError:
        return JSONResponse(
            status_code=404,
            content={"error": "Artifact not found"}
        )


# =============================================================================
# Phase 3: Responsiveness endpoints
# =============================================================================

@app.get("/api/v1/monitoring/status")
async def api_v1_monitoring_status():
    """Get ambient monitoring status."""
    if not _ambient_monitor:
        return JSONResponse(
            status_code=503,
            content={"error": "Ambient monitor not initialized"}
        )

    config = _ambient_monitor.config
    if config:
        return {
            "running": _ambient_monitor.running,
            "active_topics": len(config.active_topics),
            "topics": [
                {
                    "topic_id": t.topic_id,
                    "project_slug": t.project_slug,
                    "intent_type": t.intent_type,
                    "check_interval": t.check_interval,
                    "urgency": t.urgency,
                }
                for t in config.active_topics
            ],
            "exceptions": len(config.exceptions),
        }
    return {"running": _ambient_monitor.running, "active_topics": 0}


@app.post("/api/v1/monitoring/reload")
async def api_v1_monitoring_reload():
    """Reload monitoring configuration."""
    if not _ambient_monitor:
        return JSONResponse(
            status_code=503,
            content={"error": "Ambient monitor not initialized"}
        )

    await _ambient_monitor.reload_config()
    return {"status": "ok", "message": "Monitoring configuration reloaded"}


@app.get("/api/v1/context/status")
async def api_v1_context_status():
    """Get context warmer status."""
    if not _context_warmer:
        return JSONResponse(
            status_code=503,
            content={"error": "Context warmer not initialized"}
        )

    store = await get_store()
    active_topics = await store.get_active_topic_ids()

    return {
        "running": _context_warmer.running,
        "refresh_interval": _context_warmer.refresh_interval,
        "context_ttl": _context_warmer.context_ttl,
        "active_topics_count": len(active_topics),
    }


@app.post("/api/v1/context/warm")
async def api_v1_context_warm(request: dict):
    """Manually trigger context warming for a topic."""
    if not _context_warmer:
        return JSONResponse(
            status_code=503,
            content={"error": "Context warmer not initialized"}
        )

    topic_id = request.get("topic_id")
    project_slugs = request.get("project_slugs", [])

    if not topic_id or not project_slugs:
        return JSONResponse(
            status_code=400,
            content={"error": "Missing topic_id or project_slugs"}
        )

    await _context_warmer.warm_topic_context(topic_id, project_slugs)
    return {"status": "ok", "message": f"Context warmed for topic {topic_id}"}


@app.get("/api/v1/background/status")
async def api_v1_background_status():
    """Get background analysis processor status."""
    if not _background_processor:
        return JSONResponse(
            status_code=503,
            content={"error": "Background processor not initialized"}
        )

    stats = {
        "running": _background_processor.running,
        "check_interval": _background_processor.check_interval,
        "signal_threshold": _background_processor.signal_threshold,
    }

    return stats


@app.post("/api/v1/background/analyze")
async def api_v1_background_analyze():
    """Manually trigger background analysis."""
    if not _background_processor:
        return JSONResponse(
            status_code=503,
            content={"error": "Background processor not initialized"}
        )

    proposals = await _background_processor.analyze_signals()

    return {
        "proposals": [
            {
                "proposal_id": p.proposal_id,
                "artifact_type": p.artifact_type,
                "artifact_name": p.artifact_name,
                "change_summary": p.change_summary,
                "confidence": p.confidence,
                "signals_consulted": p.signals_consulted,
            }
            for p in proposals
        ]
    }


@app.get("/api/v1/status/telegram_bridge")
async def api_v1_telegram_bridge_status():
    """Get Telegram bridge reachability status."""
    try:
        telegram_fallback = get_telegram_fallback()
        status = telegram_fallback.get_bridge_status()
        return status
    except Exception as e:
        logger.error(f"Error getting Telegram bridge status: {e}")
        return JSONResponse(
            status_code=500,
            content={"error": f"Failed to get bridge status: {str(e)}"}
        )


# =============================================================================
# STT Fallback endpoints
# =============================================================================

class STTRequest(BaseModel):
    audio_data: str  # base64-encoded audio bytes
    format: str = "webm"  # audio format hint


@app.post("/api/v1/stt")
async def api_v1_stt_transcribe(request: STTRequest):
    """
    Transcribe audio using whisper-stt fallback service.

    Accepts base64-encoded audio (webm/opus from MediaRecorder) and
    returns transcribed text. For browsers without Web Speech API.

    Returns:
        {"status": "success", "text": "..."} on success
        {"error": "..."} on failure
    """
    import base64

    from .stt.fallback import get_stt_fallback

    # Validate audio_data
    if not request.audio_data:
        return JSONResponse(
            status_code=400,
            content={"error": "Missing audio_data"}
        )

    # Decode base64
    try:
        audio_bytes = base64.b64decode(request.audio_data)
    except Exception:
        return JSONResponse(
            status_code=400,
            content={"error": "Invalid base64 encoding"}
        )

    # Get STT fallback service and transcribe
    stt = get_stt_fallback()
    text = await stt.transcribe(audio_bytes, request.format)

    if text:
        return {
            "status": "success",
            "text": text
        }
    else:
        return JSONResponse(
            status_code=500,
            content={"error": "Transcription failed"}
        )


@app.get("/api/v1/status/stt")
async def api_v1_stt_status():
    """
    Get STT fallback service status.

    Returns:
        {
            "available": bool,
            "stt_url": str,
            "failure_count": int
        }
    """
    from .stt.fallback import get_stt_fallback

    stt = get_stt_fallback()
    return stt.get_status()


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
