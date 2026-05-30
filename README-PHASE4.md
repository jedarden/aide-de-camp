# ADC (aide-de-camp) - Phase 4: Audio Surface

## Overview

Phase 4 implements the voice mode using OpenAI's Realtime API. This provides full voice interaction with ADC, replacing the text input path with a tool-as-trigger model where results arrive asynchronously.

## Implementation

### Core Components

1. **VoiceSession** (`src/realtime/session.py`)
   - OpenAI Realtime API WebRTC session management
   - Tool registration and handling
   - Result queue for async delivery
   - Surface switch event handling
   - Voice change support

2. **Voice Prompt** (`prompts/voice.md`)
   - Comprehensive system prompt for the voice model
   - Defines narration style, batching, urgency handling
   - Multi-turn topic tracking guidelines
   - Audio-to-canvas continuity behavior

3. **Dispatch Handler** (`src/realtime/dispatch.py`)
   - `dispatch_intent()` tool handler
   - Returns acknowledgment immediately
   - Results arrive via async result listener
   - Placeholder router endpoint

4. **Session Continuity** (`src/realtime/continuity.py`)
   - Audio-to-canvas session continuity
   - Pending result tracking
   - Surface switch event handling

5. **Session Store** (`src/session/store.py`)
   - SQLite-based with WAL mode for concurrent access
   - Tables: sessions, surfaces, utterances, intents, results, topics
   - Supports bead watcher and background analysis

6. **Main Application** (`src/main.py`)
   - FastAPI entry point
   - `/voice` WebSocket endpoint
   - `/router` placeholder endpoint
   - Health check endpoint

### Key Features

- **Tool-as-Trigger Model**: `dispatch_intent()` returns ack immediately; results arrive async
- **Urgency-Tiered Narration**:
  - Critical: Interrupt immediately
  - High: Wait for natural pause
  - Normal: Batch within ~5s window
  - Low: Narrate only if idle
- **Audio-to-Canvas Continuity**: Pending results rendered to canvas on surface switch
- **Hot-Reload Prompts**: Voice prompt reloaded on each session turn
- **Session Persistence**: SQLite WAL mode for concurrent access

### Voice Prompt Design

The `prompts/voice.md` file defines:
- **Identity**: ADC (aide-de-camp), universal personal interface
- **Core Responsibilities**: Listen, route, acknowledge, narrate, track
- **Tool Behavior**: Immediate acknowledgment, async results
- **Urgency Handling**: Detailed guidance per urgency level
- **Topic Tracking**: Multi-turn context management
- **Batching Rules**: When and how to batch results
- **Surface Continuity**: How to handle audio-to-canvas transitions
- **Narration Style**: Natural, conversational, efficient
- **Error Handling**: Clear user-facing error messages

### Running the Server

```bash
# Set API key
export OPENAI_API_KEY="sk-..."

# Install dependencies
pip install -r requirements.txt

# Run server
uvicorn src.main:app --host 0.0.0.0 --port 8000
```

### API Endpoints

- `GET /health` - Health check
- `WS /voice?session_id=<id>` - Voice session WebSocket
- `POST /router` - Intent router (placeholder for Phase 1)

### WebSocket Events

**Client → Server:**
- `response.function_call_arguments.done` - Tool call completion
- `adc.annotation` - Client annotations
- `adc.turn_done` - Turn completion (for memory extraction)
- `adc.surface_switch` - Surface type change (audio → canvas)

**Server → Client:**
- `ag2.init` - WebRTC bootstrap with ephemeral key
- `adc.session_update` - Session parameter changes (voice)
- `conversation.item.create` - Tool result output
- `adc.surface_switch_ack` - Surface switch acknowledgment
- `error` - Error message

### Result Flow

```
User utterance
  → dispatch_intent() tool called
  → Router returns ack immediately
  → Voice model: "On it."
  → (async) Router creates intents
  → (async) Fetch + Synthesize strands execute
  → (async) Results written to session store
  → Result listener polls store
  → Results pushed to VoiceSession
  → Voice model narrates at appropriate moment
```

### Surface Switch Flow

```
User switches from audio to canvas
  → Client sends adc.surface_switch event
  → on_surface_switch() handler called
  → Get pending results from VoiceSession
  → Send acknowledgment with catch-up summary
  → Canvas renders pending results
  → Session continuity maintained
```

## Files Created

```
aide-de-camp/
├── prompts/
│   └── voice.md                 # Voice model system prompt
├── config/                      # (directory for future config files)
├── data/                        # (directory for SQLite databases)
├── src/
│   ├── __init__.py
│   ├── main.py                  # FastAPI entry point
│   ├── realtime/
│   │   ├── __init__.py
│   │   ├── session.py          # VoiceSession implementation
│   │   ├── dispatch.py         # dispatch_intent handler
│   │   └── continuity.py       # Audio-to-canvas continuity
│   └── session/
│       ├── __init__.py
│       └── store.py            # Session store (SQLite)
└── requirements.txt
```

## Next Steps (Future Phases)

- **Phase 1**: Implement intent router with LLM-based segmentation
- **Phase 1**: Implement fetch strand with command matrix execution
- **Phase 1**: Implement synthesize strand for result generation
- **Phase 2**: Add memory extraction on turn done
- **Phase 2**: Implement self-modification agent integration
- **Phase 3**: Add ambient monitoring and pre-warmed context

## Notes

- The router endpoint (`/router`) is currently a placeholder that returns dummy results
- Result listener polls the session store; in production, use SSE or pub/sub
- Voice prompt is hot-reloaded on each session turn (read from disk per invocation)
- Canvas rendering and component library are not yet implemented (Phase 1+)
- Memory extraction is a TODO (needs DUCK-E-style memory module)
