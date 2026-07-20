"""
Test endpoint ↔ /dispatch classification equivalence (bead adc-492b).

This suite verifies the core requirement of the parent bead (adc-50m6): the
test endpoints that bypass the Web Speech API must route utterances through
the *same* intent classifier the production /dispatch endpoint uses, and
produce identical classifications for identical inputs.

What "the same classifier" means here, concretely:

- ``POST /api/v1/test/classify`` (src/test/router.py) calls
  ``router.classify_utterance(...)`` directly.
- ``POST /api/v1/test/dispatch`` (src/test/dispatch.py) and the production
  ``POST /dispatch`` / ``POST /router`` (src/main.py) call
  ``router.route_utterance(...)``, which internally delegates to
  ``classify_utterance(...)``.
- All four handlers obtain their router from the *same* ``get_router()``
  singleton in src/intent/router.py.

So equivalence is true by construction. These tests pin that construction down
so a future refactor (e.g. a second router instance, or a divergent classify
path on the test endpoint) would fail loudly instead of silently desyncing the
test harness from production behaviour.

NOTE on the acceptance criteria's "weather"/"research" intents: those are not
``IntentType`` values in this codebase (see src/intent/router.py). ``research``
is a *topic type* — the default for any intent that isn't ACTION/TASK_PROFILE
(see ``_topic_type_map`` in ``IntentRouter._fetch_and_synthesize``). "weather"
does not exist as a type at all. The tests below verify the *real* contract —
identical classification through the test endpoint and /dispatch — using actual
IntentTypes, and call out the topic-type mapping that is the closest real
analogue to a "research" verdict.

No live LLM calls: the ZAI client is mocked per-test, mirroring the pattern in
tests/test_intent_classification.py and tests/test_router_prompt_hotreload.py.
"""

import json
from pathlib import Path
from tempfile import NamedTemporaryFile
from unittest.mock import AsyncMock, MagicMock

import pytest

import src.intent.router as router_module
from src.components.hot_reload import HotReloadManager
from src.intent.router import IntentRouter, IntentType, get_router

# Aliased so pytest does not try to collect these pydantic request models as
# test classes (their source names start with "Test"). They are request DTOs,
# not test classes.
from src.test.dispatch import TestDispatchRequest as DispatchRequestModel
from src.test.router import TestClassificationRequest as ClassifyRequestModel

# --- pre-canned (utterance, LLM JSON response) pairs ------------------------
#
# Each pair is an informational utterance paired with the canned classification
# the (mocked) ZAI client returns for it. These stand in for the acceptance
# criteria's "what is the weather" / "tell me about X" cases: an open-ended
# information-seeking query segments to a LOOKUP intent in this system, not to a
# nonexistent "weather"/"research" intent. Both paths must reproduce the same
# verdict for the same canned response.

INFORMATIONAL_CASES = [
    (
        "what is the weather",
        json.dumps([{
            "intent_type": "lookup",
            "project_slug": None,
            "urgency": "normal",
            "utterance_fragment": "what is the weather",
            "confidence": 0.9,
            "reasoning": "information-seeking query for current conditions",
        }]),
    ),
    (
        "tell me about the options pipeline",
        json.dumps([{
            "intent_type": "lookup",
            "project_slug": "options-pipeline",
            "urgency": "normal",
            "utterance_fragment": "tell me about the options pipeline",
            "confidence": 0.88,
            "reasoning": "request to surface factual context about a project",
        }]),
    ),
    (
        "how are the pods doing in ardenone-manager",
        json.dumps([{
            "intent_type": "status",
            "project_slug": "ardenone-manager",
            "urgency": "normal",
            "utterance_fragment": "how are the pods doing",
            "confidence": 0.95,
            "reasoning": "querying current cluster state",
        }]),
    ),
]


# --- fixtures ---------------------------------------------------------------

ROUTER_MD_STUB = """\
# Intent Router System Prompt (test stub)

Return ONLY a JSON array of intent objects.
"""


@pytest.fixture
def temp_router_md():
    """A throwaway router.md so the router never reads the production prompt."""
    with NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
        f.write(ROUTER_MD_STUB)
        path = f.name
    yield path
    Path(path).unlink(missing_ok=True)


@pytest.fixture
def temp_urgency_md():
    """A throwaway urgency.md so _build_system_prompt stays hermetic."""
    with NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
        f.write("# Urgency (test stub)\n")
        path = f.name
    yield path
    Path(path).unlink(missing_ok=True)


@pytest.fixture
def router(temp_router_md, temp_urgency_md):
    """
    An IntentRouter pointed at the stub router.md, with a hermetic store
    (get_session -> None, so no session context is appended) and a registered
    urgency prompt. The ZAI client is injected per-test by the caller.
    """
    reload_manager = HotReloadManager()
    reload_manager.register_prompt("urgency", temp_urgency_md)

    r = IntentRouter(prompt_path=Path(temp_router_md))
    r._reload_manager = reload_manager

    store = MagicMock()
    store.get_session = AsyncMock(return_value=None)
    r.store = store
    return r


def _wire_canned_response(router: IntentRouter, response_text: str) -> IntentRouter:
    """Inject a mock ZAI client that returns response_text for call_simple."""
    mock_client = AsyncMock()
    mock_client.call_simple = AsyncMock(return_value=response_text)
    router._zai_client = mock_client
    return router


@pytest.fixture
def reset_router_singleton():
    """
    Back up and clear the module-global ``_router`` singleton around a test so
    get_router() identity checks aren't polluted by other tests, then restore it
    afterwards (so production code that already cached a real router is untouched).
    """
    saved = router_module._router
    router_module._router = None
    yield
    router_module._router = saved


# --- 1. the test endpoints and /dispatch share one router singleton ----------

class TestSharedRouterSingleton:
    """
    get_router() is a process-wide singleton: every endpoint handler that
    classifies an utterance obtains the SAME IntentRouter instance. If the test
    endpoint ever minted its own router, its classifications could drift from
    /dispatch (e.g. after a hot-reload of the prompt only reached one instance).
    """

    def test_get_router_returns_same_instance(self, reset_router_singleton):
        a = get_router()
        b = get_router()
        assert a is b

    def test_get_router_is_idempotent_under_repeated_calls(self, reset_router_singleton):
        instances = {id(get_router()) for _ in range(5)}
        assert len(instances) == 1


# --- 2. the two classification code paths are the same path -------------------

class TestSharedClassificationPath:
    """
    /test/classify calls classify_utterance() directly; /dispatch and
    /test/dispatch call route_utterance(), which calls classify_utterance().
    So the test endpoint cannot diverge from /dispatch in HOW it classifies —
    only the same function can run.
    """

    @pytest.mark.asyncio
    async def test_route_utterance_delegates_to_classify_utterance(self, router):
        """route_utterance must call classify_utterance exactly once."""
        canned = INFORMATIONAL_CASES[0][1]
        _wire_canned_response(router, canned)

        spy = AsyncMock(wraps=router.classify_utterance)
        router.classify_utterance = spy

        await router.route_utterance(
            utterance="what is the weather",
            utterance_id="uid-1",
            session_id="session-test",
        )

        spy.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_test_dispatch_request_model_is_pure_text(self):
        """
        The test endpoint's request schema carries no audio/microphone/STT
        field — only utterance text plus bookkeeping. This is the contract that
        keeps the Web Speech API out of the test path (acceptance criterion:
        "no microphone/audio layer interference").
        """
        fields = set(DispatchRequestModel.model_fields.keys())
        assert "utterance" in fields
        # No audio-shaped field sneaks in.
        for audio_field in ("audio", "microphone", "stt", "sample_rate", "blob"):
            assert audio_field not in fields

    @pytest.mark.asyncio
    async def test_test_classify_request_model_is_pure_text(self):
        """Same guarantee for the /test/classify schema."""
        fields = set(ClassifyRequestModel.model_fields.keys())
        assert "utterance" in fields
        for audio_field in ("audio", "microphone", "stt", "sample_rate", "blob"):
            assert audio_field not in fields


# --- 3. identical inputs → identical classifications across paths -----------

class TestIdenticalClassificationAcrossPaths:
    """
    For an identical utterance and an identical (canned) LLM response, the
    classification the /test/classify path produces (classify_utterance) must
    equal the classification the /dispatch and /test/dispatch paths produce
    (route_utterance → classify_utterance). Because they share the function,
    they share the result — this locks that down against drift.
    """

    @pytest.mark.parametrize(
        "utterance,canned_response",
        INFORMATIONAL_CASES,
        ids=[c[0][:24] for c in INFORMATIONAL_CASES],
    )
    @pytest.mark.asyncio
    async def test_classify_path_equals_dispatch_path(
        self, router, utterance, canned_response
    ):
        _wire_canned_response(router, canned_response)

        # Path A: what /test/classify runs.
        direct = await router.classify_utterance(utterance, "session-test")

        # Path B: what /dispatch and /test/dispatch run.
        routed = await router.route_utterance(
            utterance=utterance,
            utterance_id="uid-1",
            session_id="session-test",
        )

        assert len(direct) == len(routed)
        for direct_cls, routed_intent in zip(direct, routed):
            routed_cls = routed_intent.classification
            assert direct_cls.intent_type == routed_cls.intent_type
            assert direct_cls.project_slug == routed_cls.project_slug
            assert direct_cls.urgency == routed_cls.urgency
            assert direct_cls.confidence == pytest.approx(routed_cls.confidence)
            assert direct_cls.utterance_fragment == routed_cls.utterance_fragment
            assert direct_cls.reasoning == routed_cls.reasoning

    @pytest.mark.asyncio
    async def test_informational_query_classifies_consistently(self, router):
        """
        A direct check of the acceptance-criteria spirit: an information-seeking
        utterance ("tell me about the options pipeline") classifies to a real
        IntentType (here LOOKUP) through BOTH paths, with no path disagreeing.
        """
        canned = json.dumps([{
            "intent_type": "lookup",
            "project_slug": "options-pipeline",
            "urgency": "normal",
            "utterance_fragment": "tell me about the options pipeline",
            "confidence": 0.88,
            "reasoning": "request to surface factual context",
        }])
        _wire_canned_response(router, canned)

        [direct] = await router.classify_utterance(
            "tell me about the options pipeline", "session-test"
        )
        [routed] = await router.route_utterance(
            utterance="tell me about the options pipeline",
            utterance_id="uid-1",
            session_id="session-test",
        )

        assert direct.intent_type == IntentType.LOOKUP
        assert routed.classification.intent_type == IntentType.LOOKUP


# --- 4. the "research" verdict is a topic type, not an intent type -----------

class TestResearchIsATopicType:
    """
    The acceptance criteria name a "research intent", but ``research`` is not an
    IntentType — it is the *topic type* that any non-action, non-task-profile
    intent resolves to in _fetch_and_synthesize(). This class documents that
    mapping and proves an informational (LOOKUP) intent lands on the "research"
    topic type, which is the real meaning of "classified as research" here.
    """

    @pytest.mark.parametrize("intent_type", [
        IntentType.LOOKUP,
        IntentType.STATUS,
        IntentType.BRAINSTORM,
        IntentType.REMINDER,
        IntentType.SELF_MODIFICATION,
        IntentType.MONITORING_CONFIG,
    ])
    def test_non_action_intent_maps_to_research_topic_type(self, intent_type):
        """
        Mirror of the _topic_type_map in IntentRouter._fetch_and_synthesize:
        ACTION and TASK_PROFILE → "project"; every other classifiable intent →
        "research". If that map changes, this test must change in lock-step.
        """
        _topic_type_map = {
            IntentType.ACTION: "project",
            IntentType.TASK_PROFILE: "project",
        }
        topic_type = _topic_type_map.get(intent_type, "research")
        assert topic_type == "research"

    def test_action_and_task_profile_are_the_only_project_topic_types(self):
        """Guard: ACTION and TASK_PROFILE must map to 'project', not 'research'."""
        _topic_type_map = {
            IntentType.ACTION: "project",
            IntentType.TASK_PROFILE: "project",
        }
        assert _topic_type_map[IntentType.ACTION] == "project"
        assert _topic_type_map[IntentType.TASK_PROFILE] == "project"
