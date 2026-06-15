"""
Intent Router - classifies utterances and routes to appropriate strands.

Uses LLM to classify intents by type and project, then routes:
- task-profile intents → escalate strand (bead creation)
- other intents → fetch + synthesize strands
"""
import asyncio
import json
import uuid
from dataclasses import dataclass
from enum import Enum
from logging import getLogger
from typing import Any, Optional

from ..escalate.handler import EscalateRequest, escalate_intent
from ..escalate.llm import get_zai_client, ModelClass
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


# Router system prompt
ROUTER_SYSTEM_PROMPT = """You are the Intent Router for aide-de-camp, a universal personal interface that routes user utterances to parallel agents across multiple projects and domains.

## Your Role

Given a user utterance (stream-of-consciousness voice or text), you must:
1. **Segment** the utterance into distinct intent threads
2. **Classify** each thread by intent type
3. **Route** each thread to the correct project
4. **Assign** urgency tier

## Output Format

Return a JSON array of intent objects:

```json
[
  {
    "intent_type": "status|action|brainstorm|lookup|reminder|self-modification|monitoring-config|task-profile",
    "project_slug": "project-id or null",
    "urgency": "critical|high|normal|low",
    "utterance_fragment": "the specific fragment this intent covers",
    "confidence": 0.0-1.0,
    "reasoning": "brief explanation of classification"
  }
]
```

## Intent Types

- **status**: Query current state (pods, pipelines, deployments, beads)
- **action**: Execute a command (deploy, restart, create)
- **brainstorm**: Explore options, design, architecture discussion
- **lookup**: Find specific information (logs, configs, docs)
- **reminder**: Set or query reminders
- **self-modification**: Instructions to improve the interface itself
- **monitoring-config**: Configure ambient monitoring rules
- **task-profile**: Durable async work items that escalate to NEEDLE beads

## Task-Profile Classification

Route to **task-profile** when:
- User explicitly requests tracking ("make me a bead for...", "track this as...")
- Intent requires multi-step implementation work
- Request involves creating/modifying features or infrastructure
- Complexity exceeds single-turn synthesis
- Action verbs: "implement", "add", "create", "fix", "investigate", "refactor"
- Scope indicators: "feature", "bug", "optimization", "migration"

Task-profile intents are escalated to NEEDLE beads for durable async handling.

## Urgency Tiers

- **critical**: Blocking production, security incident, immediate action required
- **high**: Important but not blocking, user is actively waiting
- **normal**: Routine query, no time pressure
- **low**: Background research, nice-to-have, can be deferred

## Routing Logic

Use available project context to map utterances to projects:
- Look for direct project name matches
- Check aliases (e.g., "the pipeline" → "options-pipeline")
- Use context from previous utterances in the session
- If ambiguous, set confidence < 0.7 and the system will clarify

## Segmentation Guidelines

- Split multi-part utterances: "how's the pipeline and what about the ibkr mcp" → two intents
- Keep related clauses together: "are the pods running and healthy" → one intent
- Extract compound workflows: "deploy the pipeline and check if it synced" → two intents (action, then status)

## Confidence Threshold

- **confidence >= 0.9**: Dispatch immediately
- **confidence 0.7-0.9**: Dispatch but flag for possible clarification
- **confidence < 0.7**: Return intent_type "clarification" with the ambiguous fragment

Return ONLY the JSON array. No explanations."""


class IntentRouter:
    """
    Intent Router classifies utterances and routes to appropriate strands.

    For task-profile intents, routes to escalate strand for bead creation.
    For other intents, routes to fetch + synthesize strands (TODO).
    """

    def __init__(self, store=None):
        self.store = store
        self._zai_client = None

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

        try:
            response = await client.call_simple(
                system_prompt=ROUTER_SYSTEM_PROMPT,
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
        # Classify the utterance
        classifications = await self.classify_utterance(utterance, session_id)

        routed_intents = []
        for classification in classifications:
            # Create intent ID
            intent_id = str(uuid.uuid4())

            routed_intent = RoutedIntent(
                intent_id=intent_id,
                classification=classification,
                session_id=session_id,
                utterance=classification.utterance_fragment,
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

        # For task-profile intents, escalate to bead
        if classification.intent_type == IntentType.TASK_PROFILE:
            return await self._escalate_to_bead(routed_intent)

        # For other intents, fetch then synthesize
        return await self._fetch_and_synthesize(routed_intent)

    async def _fetch_and_synthesize(
        self,
        routed_intent: RoutedIntent,
    ) -> dict:
        """
        Fetch context then synthesize into structured result.

        Args:
            routed_intent: The routed intent to process

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
                ),
            )

            fetch_result = await execute_fetch(fetch_request)

            # Step 2: Synthesize result
            synthesize_request = SynthesizeRequest(
                intent_id=routed_intent.intent_id,
                intent_type=fetch_intent_type,
                utterance=routed_intent.utterance,
                project_slug=classification.project_slug,
                fetched_context=fetch_result,
                urgency=classification.urgency,
            )

            synthesize_result = await synthesize_intent(synthesize_request)

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
    ) -> dict:
        """
        Escalate a task-profile intent to a NEEDLE bead.

        Args:
            routed_intent: The routed intent to escalate

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
            # Escalate to bead
            result = await escalate_intent(escalate_request)

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
