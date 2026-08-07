# ADC src/ Structure Audit - Bead adc-27eah

**Completed:** 2026-08-06  
**Bead ID:** adc-27eah  
**Task:** Audit actual src/ directory structure

## Summary

Complete inventory of `src/` module structure completed. Identified 31 top-level modules with 111 Python files total.

## Key Findings

### Top-Level Standalone Files
- `src/main.py` - FastAPI app entry point (78KB)
- `src/registry.py` - Module registry (12KB)
- `src/calculate_deployment_metrics.py` - Deployment metrics
- `src/freeze.py`, `src/_version.py`, `src/__init__.py`

### Module Inventory (31 modules)

**Core Pipeline:**
- `src/action/` - Action execution (executor, models, registry, steps, steps/)
- `src/fetch/` - Data fetching (clusters, commands, orchestrator)
- `src/intent/` - Intent routing (router, deterministic_router)
- `src/synthesize/` - Result synthesis (strand)
- `src/cli/` - CLI (commands, config, main, sse)

**State Management:**
- `src/session/` - Session persistence (store, migrations/)
- `src/sse/` - Server-sent events (broadcaster, events)
- `src/surface/` - Surface routing (router)
- `src/realtime/` - Real-time processing (batching, continuity, dispatch, session)
- `src/conversation/` - Conversation tracking
- `src/memory/` - Memory operations (extraction, store)
- `src/topic/` - Topic model

**LLM & Intelligence:**
- `src/llm/` - LLM utilities (response_parser)
- `src/agents/` - Agent implementations (self_modification, ui_regen)

**Validation & Quality:**
- `src/validation/` - Validation orchestration (6 files)
- `src/bead_validation/` - Bead validation
- `src/errors/` - Error handling

**Infrastructure:**
- `src/monitoring/` - Monitoring (ambient, config_loader)
- `src/instrument/` - Instrumentation
- `src/environment/` - Environment discovery
- `src/concurrency/` - Concurrency control
- `src/persistence/` - Persistence layer

**UI & Rendering:**
- `src/canvas/` - Canvas UI
- `src/render/` - Rendering utilities
- `src/components/` - UI components

**Specialized Features:**
- `src/escalate/` - Escalation handling
- `src/feedback/` - Feedback processing
- `src/stt/` - Speech-to-text
- `src/telegram/` - Telegram integration
- `src/diff/` - Diff engine

**Testing:**
- `src/test/` - Test utilities (fixtures/)

## Modules with Subdirectories
1. `src/action/steps/`
2. `src/session/migrations/`
3. `src/test/fixtures/`

## Next Steps

The full audit is saved at `/tmp/adc-src-structure-audit.md`. Use this to update plan.md documentation with any modules not yet covered in the architectural documentation.
