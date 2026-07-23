"""
Intent Router - classifies utterances and routes to appropriate strands.

Uses LLM to classify intents by type and project, then routes:
- task-profile intents → escalate strand (bead creation)
- other intents → fetch + synthesize strands
"""
import asyncio
import json
import time
import uuid
from dataclasses import dataclass
from enum import Enum
from logging import getLogger
from pathlib import Path
from typing import Any, Optional

from ..components.hot_reload import get_reload_manager
from ..escalate.handler import EscalateRequest, escalate_intent
from ..escalate.llm import get_zai_client, ModelClass
from ..instrument.timings import DispatchTimings
from ..session.store import get_store
from ..fetch.commands import FetchRequest, FetchContext, IntentType as FetchIntentType
from ..fetch.orchestrator import execute_fetch
from ..synthesize.strand import SynthesizeRequest, synthesize_intent


logger = getLogger(__name__)


class IntentType(Enum):
    """Intent types that the router can classify."""
    STATUS = "status"
    ACTION = "action"
    BRAINSTORM = "brainstorm"
    LOOKUP = "lookup"
    REMINDER = "reminder"
    SELF_MODIFICATION = "self-modification"
    MONITORING_CONFIG = "monitoring-config"
    TASK_PROFILE = "task-profile"  # Escalate to NEEDLE bead
    CLARIFICATION = "clarification"  # Needs user input


@dataclass
class IntentClassification:
    """Result of intent classification."""
    intent_type: IntentType
    project_slug: str | None = None
    confidence: float = 1.0
    utterance_fragment: str = ""
    reasoning: str = ""
    urgency: str = "normal"  # critical, high, normal, low


@dataclass
class RoutedIntent:
    """A routed intent ready for processing."""
    intent_id: str
    classification: IntentClassification
    session_id: str
    utterance: str
    # router_ms is measured once around classify_utterance() in route_utterance
    # (one LLM call per utterance) and shared across every intent thread from
    # that utterance — see Latency Budget & Instrumentation in docs/plan/plan.md.
    router_ms: int | None = None


# Path to the router segmentation prompt. Read from disk on each classify_utterance()
# call so edits to prompts/router.md take effect without a server restart (hot-reload),
# matching the pattern in src/synthesize/strand.py (SYNTHESIZE_PROMPT_PATH).
ROUTER_PROMPT_PATH = Path("/home/coding/aide-de-camp/prompts/router.md")

# Fallback used only if the prompt file cannot be read at runtime.
_ROUTER_PROMPT_FALLBACK = (
    "You are the Intent Router for aide-de-camp. Segment the utterance into "
    "distinct intent threads, classify each, and return ONLY a JSON array of "
    "intent objects."
)


class IntentRouter:
    """
    Intent Router classifies utterances and routes to appropriate strands.

    For task-profile intents, routes to escalate strand for bead creation.
    For other intents, routes to fetch + synthesize strands (TODO).
    """

    def __init__(self, store=None, prompt_path: Optional[Path] = None):
        self.store = store
        self.prompt_path = prompt_path or ROUTER_PROMPT_PATH
        self._zai_client = None
        self._reload_manager = None

    async def _get_zai_client(self):
        """Get or create ZAI client."""
        if self._zai_client is None:
            self._zai_client = get_zai_client()
        return self._zai_client

    async def _get_store(self):
        """Get or create session store."""
        if self.store is None:
            self.store = get_store()
        return self.store

    def _get_reload_manager(self):
        """Get or create the hot-reload manager (lazy singleton)."""
        if self._reload_manager is None:
            self._reload_manager = get_reload_manager()
        return self._reload_manager

    def _load_router_prompt(self) -> str:
        """Load the router segmentation prompt from disk (hot-reload, per call)."""
        try:
            return self.prompt_path.read_text()
        except Exception as e:
            logger.error(f"Failed to load router prompt from {self.prompt_path}: {e}")
            return _ROUTER_PROMPT_FALLBACK

    def _load_urgency_prompt(self) -> str:
        """
        Load the urgency classification prompt from disk via the hot-reload manager.

        prompts/urgency.md is a separately hot-reloadable artifact (registered in
        src/components/hot_reload.py). Splicing it here keeps urgency guidance
        editable independently of the segmentation prompt. Returns "" on failure
        so the router still functions without urgency guidance.
        """
        try:
            return self._get_reload_manager().get_prompt("urgency")
        except Exception as e:
            logger.warning(f"Failed to load urgency prompt: {e}")
            return ""

    def _build_system_prompt(self) -> str:
        """Build the full system prompt: segmentation prompt + urgency rules."""
        system_prompt = self._load_router_prompt()
        urgency_prompt = self._load_urgency_prompt()
        if urgency_prompt:
            system_prompt = (
                f"{system_prompt}\n\n## Urgency Classification Rules\n\n{urgency_prompt}"
            )
        return system_prompt

    async def classify_utterance(
        self,
        utterance: str,
        session_id: str,
    ) -> list[IntentClassification]:
        """
        Classify an utterance into intents.

        Uses LLM to segment and classify the utterance.

        Args:
            utterance: The user utterance
            session_id: Session ID for context

        Returns:
            List of IntentClassification objects
        """
        client = await self._get_zai_client()

        # Build user message with session context if available
        store = await self._get_store()
        session_context = ""
        try:
            session = await store.get_session(session_id)
            if session:
                # Get recent intents for context
                recent_intents = await store.get_recent_intents(session_id, limit=5)
                if recent_intents:
                    session_context = "\n\nRecent intents in this session:\n"
                    for intent in recent_intents:
                        session_context += f"- {intent.get('utterance', '')} ({intent.get('intent_type', 'unknown')})\n"
        except Exception as e:
            logger.warning(f"Failed to get session context: {e}")

        user_message = f"Classify this utterance:\n\n{utterance}{session_context}"

        logger.info(f"Classifying utterance for session {session_id}")

        # Build system prompt per call from prompts/router.md (+ urgency rules),
        # so edits to either prompt take effect without a server restart.
        system_prompt = self._build_system_prompt()

        try:
            response = await client.call_simple(
                system_prompt=system_prompt,
                user_message=user_message,
                model=ModelClass.SONNET.value,
                max_tokens=2048,
                temperature=0.3,  # Lower temperature for consistent classification
            )

            # Strip markdown code fences if present (ZAI proxy wraps in ```json...```)
            raw = response.strip()
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[-1]
                raw = raw.rsplit("```", 1)[0].strip()

            # Parse JSON response
            intents_data = json.loads(raw)
            classifications = []

            for intent_data in intents_data:
                # Map string to IntentType enum
                intent_type_str = intent_data.get("intent_type", "status")
                try:
                    intent_type = IntentType(intent_type_str)
                except ValueError:
                    logger.warning(f"Unknown intent type: {intent_type_str}")
                    intent_type = IntentType.STATUS

                classification = IntentClassification(
                    intent_type=intent_type,
                    project_slug=intent_data.get("project_slug"),
                    confidence=float(intent_data.get("confidence", 0.8)),
                    utterance_fragment=intent_data.get("utterance_fragment", utterance),
                    reasoning=intent_data.get("reasoning", ""),
                    urgency=intent_data.get("urgency", "normal"),
                )
                classifications.append(classification)

            logger.info(f"Classified {len(classifications)} intents from utterance")
            return classifications

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse router response as JSON: {e}")
            # Fallback: return single status intent
            return [
                IntentClassification(
                    intent_type=IntentType.STATUS,
                    utterance_fragment=utterance,
                    confidence=0.5,
                    reasoning="Classification failed, defaulting to status",
                )
            ]
        except Exception as e:
            logger.error(f"Classification failed: {e}")
            raise

    async def route_utterance(
        self,
        utterance: str,
        utterance_id: str,
        session_id: str,
    ) -> list[RoutedIntent]:
        """
        Route an utterance to appropriate strands.

        Classifies the utterance and routes each intent to the correct strand.

        Args:
            utterance: The user utterance
            utterance_id: Unique ID for this utterance
            session_id: Session ID

        Returns:
            List of RoutedIntent objects
        """
        # Classify the utterance (one LLM call per utterance — the router stage
        # is shared across every intent thread it produces, so its duration is
        # measured once here and stamped onto each RoutedIntent).
        classify_start = time.monotonic()
        classifications = await self.classify_utterance(utterance, session_id)
        router_ms = int((time.monotonic() - classify_start) * 1000)

        routed_intents = []
        for classification in classifications:
            # Create intent ID
            intent_id = str(uuid.uuid4())

            routed_intent = RoutedIntent(
                intent_id=intent_id,
                classification=classification,
                session_id=session_id,
                utterance=classification.utterance_fragment,
                router_ms=router_ms,
            )
            routed_intents.append(routed_intent)

        return routed_intents

    async def process_intent(
        self,
        routed_intent: RoutedIntent,
    ) -> dict:
        """
        Process a routed intent by dispatching to the appropriate strand.

        Args:
            routed_intent: The routed intent to process

        Returns:
            Result dictionary with status and data
        """
        classification = routed_intent.classification

        # Capture per-stage timings for this dispatch and persist one
        # dispatch_timings row (see Latency Budget & Instrumentation). Each
        # branch records the stages it measures; router_ms is shared across
        # the utterance's threads and was stamped on the RoutedIntent. Capture
        # is non-fatal: a persistence failure logs and moves on, never breaking
        # the dispatch itself.
        timings = DispatchTimings()
        timings.record("router_ms", routed_intent.router_ms)

        try:
            # For task-profile intents, escalate to bead
            if classification.intent_type == IntentType.TASK_PROFILE:
                result = await self._escalate_to_bead(routed_intent, timings)
            else:
                # For other intents, fetch then synthesize
                result = await self._fetch_and_synthesize(routed_intent, timings)
        except Exception:
            # Persist whatever was captured before the failure, then re-raise.
            await self._persist_timings(routed_intent.intent_id, timings)
            raise

        await self._persist_timings(routed_intent.intent_id, timings)
        return result

    async def _persist_timings(
        self,
        intent_id: str,
        timings: DispatchTimings,
    ) -> None:
        """Persist the captured dispatch timings. Non-fatal on error."""
        try:
            store = await self._get_store()
            await store.record_dispatch_timings(intent_id, **timings.to_fields())
        except Exception as e:
            logger.warning(f"dispatch timings not recorded for {intent_id}: {e}")

    async def _fetch_and_synthesize(
        self,
        routed_intent: RoutedIntent,
        timings: DispatchTimings,
    ) -> dict:
        """
        Fetch context then synthesize into structured result.

        Args:
            routed_intent: The routed intent to process
            timings: Per-stage timing collector; records fetch_first_source_ms,
                fetch_total_ms, and synthesize_total_ms.

        Returns:
            Result dictionary with synthesized data
        """
        classification = routed_intent.classification

        logger.info(
            f"Fetching and synthesizing intent {routed_intent.intent_id} "
            f"(type: {classification.intent_type.value})"
        )

        try:
            # Step 1: Fetch context — resolve project slug to local repo path
            fetch_intent_type = self._map_intent_type(classification.intent_type)

            from ..environment.discovery import get_registry
            from ..registry import get_project
            repo_path = None
            ssh_target = None
            host_alias = None
            registry = get_registry()
            if registry and classification.project_slug:
                entry = registry.lookup(classification.project_slug)
                if entry:
                    repo_path = str(entry.path)
                    ssh_target = entry.ssh_target
                    host_alias = entry.host
                    location = entry.display_path
                    logger.info(f"Resolved '{classification.project_slug}' → {location}")
                else:
                    logger.info(f"No repo found for slug '{classification.project_slug}'")

            # YAML registry entry carries cluster/namespace/argocd_app — cluster
            # drives ArgoCD endpoint resolution (bead adc-1ejh: the fetch strand
            # resolves {argocd_api} from `cluster` via config/clusters.yaml).
            # argocd_app defaults to the slug when omitted (see _fetch_argocd_app).
            project_cfg = (
                get_project(classification.project_slug)
                if classification.project_slug else None
            )

            fetch_request = FetchRequest(
                intent_id=routed_intent.intent_id,
                intent_type=fetch_intent_type,
                session_id=routed_intent.session_id,
                context=FetchContext(
                    project_slug=classification.project_slug,
                    session_id=routed_intent.session_id,
                    repo_path=repo_path,
                    ssh_target=ssh_target,
                    host_alias=host_alias,
                    cluster=project_cfg.get("cluster") if project_cfg else None,
                    namespace=project_cfg.get("namespace") if project_cfg else None,
                    app_name=project_cfg.get("argocd_app") if project_cfg else None,
                ),
            )

            # fetch_first_source_ms = time from fetch start to the first source
            # resolving (success/fail/timeout — the first progress state on the
            # pending card). fetch_total_ms = the fetch window close.
            fetch_start = timings.clock()
            first_source_at: list[float | None] = [None]

            def _on_first_source(_source, _result) -> None:
                if first_source_at[0] is None:
                    first_source_at[0] = timings.clock()

            fetch_result = await execute_fetch(fetch_request, _on_first_source)
            timings.record("fetch_total_ms", fetch_result.total_duration_ms)
            if first_source_at[0] is not None:
                timings.record(
                    "fetch_first_source_ms",
                    timings.elapsed_ms(fetch_start, first_source_at[0]),
                )

            # Step 2: Synthesize result
            synthesize_request = SynthesizeRequest(
                intent_id=routed_intent.intent_id,
                intent_type=fetch_intent_type,
                utterance=routed_intent.utterance,
                project_slug=classification.project_slug,
                fetched_context=fetch_result,
                urgency=classification.urgency,
            )

            synth_start = timings.clock()
            synthesize_result = await synthesize_intent(synthesize_request)
            timings.record("synthesize_total_ms", timings.elapsed_ms(synth_start))
            # synthesize_first_token_ms is not measurable on the current
            # call_simple path (no token stream) and is left NULL until the
            # synthesize strand streams — see src/instrument/timings.py.

            # Persist result to session store so loadTopics() can display it
            store = get_store()
            _topic_type_map = {
                IntentType.ACTION: "project",
                IntentType.TASK_PROFILE: "project",
            }
            topic_type = _topic_type_map.get(classification.intent_type, "research")
            topic_id, _ = await store.find_or_create_topic(
                label=classification.utterance_fragment or routed_intent.utterance[:80],
                topic_type=topic_type,
                project_slugs=[classification.project_slug] if classification.project_slug else [],
                session_id=routed_intent.session_id,
            )
            await store.link_intent_to_topic(routed_intent.intent_id, topic_id)
            result_id = await store.create_result(
                intent_id=routed_intent.intent_id,
                topic_id=topic_id,
                session_id=routed_intent.session_id,
                summary=synthesize_result.summary,
                data=synthesize_result.data,
                urgency=synthesize_result.urgency.value,
            )

            return {
                "intent_id": routed_intent.intent_id,
                "intent_type": classification.intent_type.value,
                "status": "resolved",
                "topic_id": topic_id,
                "result_id": result_id,
                "data": synthesize_result.data,
                "summary": synthesize_result.summary,
                "urgency": synthesize_result.urgency.value,
                "coverage": synthesize_result.coverage,
                "caveats": synthesize_result.caveats,
                "message": "Intent synthesized successfully",
            }

        except Exception as e:
            logger.error(f"Fetch/synthesize failed for intent {routed_intent.intent_id}: {e}")
            return {
                "intent_id": routed_intent.intent_id,
                "intent_type": classification.intent_type.value,
                "status": "error",
                "error": str(e),
                "message": "Failed to fetch or synthesize intent",
            }

    def _map_intent_type(self, intent_type: IntentType) -> FetchIntentType:
        """Map router IntentType to fetch IntentType."""
        # Map enum values by string
        type_map = {
            IntentType.STATUS: FetchIntentType.STATUS,
            IntentType.ACTION: FetchIntentType.ACTION,
            IntentType.BRAINSTORM: FetchIntentType.BRAINSTORM,
            IntentType.LOOKUP: FetchIntentType.LOOKUP,
            IntentType.REMINDER: FetchIntentType.REMINDER,
            IntentType.SELF_MODIFICATION: FetchIntentType.SELF_MODIFICATION,
            IntentType.MONITORING_CONFIG: FetchIntentType.MONITORING_CONFIG,
        }
        return type_map.get(intent_type, FetchIntentType.STATUS)

    async def _escalate_to_bead(
        self,
        routed_intent: RoutedIntent,
        timings: DispatchTimings,
    ) -> dict:
        """
        Escalate a task-profile intent to a NEEDLE bead.

        Args:
            routed_intent: The routed intent to escalate
            timings: Per-stage timing collector; records escalate_ms.

        Returns:
            Result dictionary with pending card
        """
        classification = routed_intent.classification

        # Build escalate request
        escalate_request = EscalateRequest(
            intent_id=routed_intent.intent_id,
            session_id=routed_intent.session_id,
            utterance=routed_intent.utterance,
            intent_type=classification.intent_type.value,
            project_slug=classification.project_slug,
            context={
                "reasoning": classification.reasoning,
                "urgency": classification.urgency,
            },
            metadata={
                "urgency": classification.urgency,
                "confidence": classification.confidence,
            },
        )

        try:
            # Escalate to bead — escalate_ms budgets formulation + validation +
            # bf create (task-profile dispatches only; NULL for hot-path rows).
            esc_start = timings.clock()
            result = await escalate_intent(escalate_request)
            timings.record("escalate_ms", timings.elapsed_ms(esc_start))

            return {
                "intent_id": routed_intent.intent_id,
                "intent_type": classification.intent_type.value,
                "status": "escalated",
                "bead_id": result.bead_id,
                "pending_card": result.pending_card,
                "message": f"Escalated to bead {result.bead_id}",
            }

        except Exception as e:
            logger.error(f"Escalation failed for intent {routed_intent.intent_id}: {e}")
            return {
                "intent_id": routed_intent.intent_id,
                "intent_type": classification.intent_type.value,
                "status": "error",
                "error": str(e),
                "message": "Failed to escalate to bead",
            }


# Global router instance
_router: Optional[IntentRouter] = None


def get_router(store=None) -> IntentRouter:
    """Get or create the global intent router instance."""
    global _router
    if _router is None:
        _router = IntentRouter(store=store)
    return _router
