"""
Escalate strand - handles task-profile intents requiring durable async handling.

For intents that need to be tracked as beads:
- formulate bead body via LLM (sonnet-class via ZAI proxy)
- create bead using br CLI
- return pending-card spec with bead reference

The bead watcher bridges bead closure to result delivery.
"""

from .handler import (
    escalate_intent,
    get_escalate_handler,
    EscalateRequest,
    EscalateResult,
    EscalateHandler,
    EscalateError,
    BeadCreationError,
)

__all__ = [
    "escalate_intent",
    "get_escalate_handler",
    "EscalateRequest",
    "EscalateResult",
    "EscalateHandler",
    "EscalateError",
    "BeadCreationError",
]
