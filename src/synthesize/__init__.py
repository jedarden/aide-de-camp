"""
Synthesize strand: converts fetched context into structured results.

Uses LLM to synthesize raw fetch data into:
- Structured data for component rendering
- Conversational summary for audio narration
- Urgency classification for routing
"""

from .strand import (
    SynthesizeRequest,
    SynthesizeResult,
    synthesize_intent,
    get_synthesize_strand,
)

__all__ = [
    "SynthesizeRequest",
    "SynthesizeResult",
    "synthesize_intent",
    "get_synthesize_strand",
]
