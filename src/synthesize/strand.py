"""
Synthesize strand: converts fetched context into structured results.

Takes raw data from fetch sources and produces:
- Structured data for the component library
- Conversational summary for audio mode
- Urgency classification

Reads prompts/synthesize.md per invocation (hot-reload).
"""

import json
from dataclasses import dataclass
from enum import Enum
from logging import getLogger
from pathlib import Path
from typing import Any, Optional

from ..components.hot_reload import get_reload_manager
from ..escalate.llm import get_zai_client, ModelClass
from ..fetch.commands import FetchResult, IntentType
from ..llm.response_parser import strip_markdown_fences, ParseLLMError


logger = getLogger(__name__)

# Path to synthesize prompt
SYNTHESIZE_PROMPT_PATH = Path("/home/coding/aide-de-camp/prompts/synthesize.md")


class Urgency(Enum):
    """Result urgency levels."""
    CRITICAL = "critical"
    HIGH = "high"
    NORMAL = "normal"
    LOW = "low"


@dataclass
class SynthesizeRequest:
    """Request to synthesize a fetched intent."""
    intent_id: str
    intent_type: IntentType
    utterance: str
    project_slug: Optional[str] = None
    fetched_context: Optional[FetchResult] = None
    urgency: str = "normal"


@dataclass
class SynthesizeResult:
    """Result from synthesize strand."""
    intent_id: str
    data: dict  # Structured data for component rendering
    summary: str  # 2-3 sentence narration for audio mode
    urgency: Urgency
    coverage: Optional[dict] = None  # Which fetch sources succeeded
    caveats: Optional[list[str]] = None  # Caveats from fetch failures


class SynthesizeStrand:
    """
    Synthesize strand: LLM-powered result synthesis.

    Takes fetched context and produces structured results with:
    - Component-ready data
    - Conversational summary
    - Urgency classification
    """

    def __init__(self, prompt_path: Optional[Path] = None):
        self.prompt_path = prompt_path or SYNTHESIZE_PROMPT_PATH
        self._zai_client = None
        self._reload_manager = None

    async def _get_zai_client(self):
        """Get or create ZAI client."""
        if self._zai_client is None:
            self._zai_client = get_zai_client()
        return self._zai_client

    def _get_reload_manager(self):
        """Get or create the hot-reload manager (lazy singleton)."""
        if self._reload_manager is None:
            self._reload_manager = get_reload_manager()
        return self._reload_manager

    def _load_prompt(self) -> str:
        """Load synthesize prompt from disk (hot-reload)."""
        try:
            return self.prompt_path.read_text()
        except Exception as e:
            logger.error(f"Failed to load synthesize prompt: {e}")
            return "You are a helpful assistant that synthesizes data into structured results."

    def _load_urgency_prompt(self) -> str:
        """
        Load urgency classification rules from prompts/urgency.md (hot-reload).

        urgency.md is a separately hot-reloadable artifact registered in
        src/components/hot_reload.py. Returns "" on failure so synthesis still
        functions without urgency guidance.
        """
        try:
            return self._get_reload_manager().get_prompt("urgency")
        except Exception as e:
            logger.warning(f"Failed to load urgency prompt: {e}")
            return ""

    async def synthesize(self, request: SynthesizeRequest) -> SynthesizeResult:
        """
        Synthesize fetched context into structured result.

        Args:
            request: SynthesizeRequest with fetched context

        Returns:
            SynthesizeResult with data, summary, and urgency
        """
        synthesize_start = time.perf_counter()

        client = await self._get_zai_client()

        # Measure prompt construction time
        prompt_start = time.perf_counter()
        prompt = self._load_prompt()

        # Splice urgency.md rules into the system prompt (hot-reloadable).
        urgency_prompt = self._load_urgency_prompt()
        if urgency_prompt:
            system_prompt = f"{prompt}\n\n## Urgency Classification Rules\n\n{urgency_prompt}"
        else:
            system_prompt = prompt

        # Build user message with intent spec and fetched context
        user_message = self._build_user_message(request)
        prompt_ms = (time.perf_counter() - prompt_start) * 1000

        logger.debug(
            f"synthesize_timing phase=prompt_construction duration_ms={prompt_ms:.2f} "
            f"intent_id={request.intent_id[:8]}"
        )

        logger.info(f"Synthesizing intent {request.intent_id}")

        try:
            # Measure LLM call time
            llm_start = time.perf_counter()
            response = await client.call_simple(
                system_prompt=system_prompt,
                user_message=user_message,
                model=ModelClass.HAIKU.value,  # Use Haiku for faster synthesis
                max_tokens=1024,  # Reduced from 4096 - most outputs are smaller
                temperature=0.3,  # Lower temperature for more deterministic, faster outputs
            )
            llm_ms = (time.perf_counter() - llm_start) * 1000

            logger.debug(
                f"synthesize_timing phase=llm_call duration_ms={llm_ms:.2f} "
                f"intent_id={request.intent_id[:8]}"
            )

            # Measure JSON parsing time
            parse_start = time.perf_counter()
            # Parse JSON response using centralized parser
            # Note: Synthesize uses fallback result pattern (not corrective retry)
            # because fetch operations are expensive and should not be discarded.
            # See docs/error-handling-standardization.md for pattern comparison.
            try:
                result_data = parse_llm_response(response)
            except ParseLLMError as e:
                logger.error(f"Failed to parse synthesize response: {e}")
                # Fall through to fallback result below
                raise json.JSONDecodeError(str(e), doc="", pos=0) from e
            parse_ms = (time.perf_counter() - parse_start) * 1000

            logger.debug(
                f"synthesize_timing phase=json_parse duration_ms={parse_ms:.2f} "
                f"intent_id={request.intent_id[:8]}"
            )

            # Measure result processing time
            process_start = time.perf_counter()

            # Extract fields
            data = result_data.get("data", {})
            summary = result_data.get("summary", "")
            urgency_str = result_data.get("urgency", request.urgency)

            # Map urgency string to enum
            try:
                urgency = Urgency(urgency_str)
            except ValueError:
                urgency = Urgency.NORMAL

            # Build coverage and caveats from fetch result
            coverage = None
            caveats = None
            if request.fetched_context:
                coverage = {
                    "total_sources": request.fetched_context.coverage.total_sources,
                    "succeeded": len(request.fetched_context.coverage.succeeded),
                    "timed_out": len(request.fetched_context.coverage.timed_out),
                    "failed": len(request.fetched_context.coverage.failed),
                }
                caveats = request.fetched_context.caveats

            result = SynthesizeResult(
                intent_id=request.intent_id,
                data=data,
                summary=summary,
                urgency=urgency,
                coverage=coverage,
                caveats=caveats,
            )

            process_ms = (time.perf_counter() - process_start) * 1000
            total_ms = (time.perf_counter() - synthesize_start) * 1000

            logger.debug(
                f"synthesize_timing phase=result_process duration_ms={process_ms:.2f} "
                f"phase=total duration_ms={total_ms:.2f} "
                f"intent_id={request.intent_id[:8]} "
                f"data_fields={len(data)} "
                f"urgency={urgency.value}"
            )

            logger.info(
                f"Synthesis complete for intent {request.intent_id}: "
                f"{len(data)} data fields, urgency={urgency.value} ({total_ms:.0f}ms)"
            )

            return result

        except json.JSONDecodeError as e:
            """
            Synthesize uses fallback result pattern (not corrective retry).

            Reasoning: Synthesize runs AFTER expensive fetch operations.
            Fetch data already obtained — should never be discarded.
            Fallback result allows displaying raw data in degraded-state UX.
            No retry needed (would re-run expensive fetch operations).

            See docs/error-handling-standardization.md for pattern comparison.
            """
            logger.error(f"Failed to parse synthesize response as JSON: {e}")
            # Fallback: return minimal result with error context
            return SynthesizeResult(
                intent_id=request.intent_id,
                data={
                    "type": "error",
                    "error": "Failed to parse synthesis response",
                    "parse_error": str(e),  # Preserve error details for debugging
                },
                summary="An error occurred while processing the result.",
                urgency=Urgency.NORMAL,
            )
        except Exception as e:
            logger.error(f"Synthesis failed for intent {request.intent_id}: {e}")
            raise

    def _build_user_message(self, request: SynthesizeRequest) -> str:
        """Build user message for LLM call."""
        lines = [
            f"## Intent Specification",
            f"Intent Type: {request.intent_type.value}",
            f"Project: {request.project_slug or 'none'}",
            f"Urgency: {request.urgency}",
            f"",
            f"## Utterance",
            f"{request.utterance}",
            f"",
        ]

        if request.fetched_context:
            lines.append("## Fetched Context")

            # Add results from each source
            for source, source_result in request.fetched_context.sources.items():
                lines.append(f"\n### {source.value}")
                if source_result.status == "success":
                    # Pretty-print the data
                    lines.append(f"```json")
                    lines.append(json.dumps(source_result.data, indent=2))
                    lines.append(f"```")
                else:
                    lines.append(f"Status: {source_result.status}")
                    if source_result.error:
                        lines.append(f"Error: {source_result.error}")

            # Add coverage info
            if request.fetched_context.caveats:
                lines.append(f"\n## Caveats")
                for caveat in request.fetched_context.caveats:
                    lines.append(f"- {caveat}")

        lines.append(f"\nPlease synthesize this into a structured result.")
        return "\n".join(lines)


# Global synthesize strand instance
_synthesize_strand: Optional[SynthesizeStrand] = None


def get_synthesize_strand(prompt_path: Optional[Path] = None) -> SynthesizeStrand:
    """Get or create the global synthesize strand instance."""
    global _synthesize_strand
    if _synthesize_strand is None:
        _synthesize_strand = SynthesizeStrand(prompt_path=prompt_path)
    return _synthesize_strand


async def synthesize_intent(request: SynthesizeRequest) -> SynthesizeResult:
    """
    Convenience function to synthesize an intent.

    Args:
        request: SynthesizeRequest

    Returns:
        SynthesizeResult
    """
    strand = get_synthesize_strand()
    return await strand.synthesize(request)
