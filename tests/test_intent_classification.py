"""
Intent classification + router→fetch-command mapping test suite (bead adc-1jxz).

This suite locks down two concerns that together form the routing contract:

1. **Classification parsing** — IntentRouter.classify_utterance() turns the raw
   LLM JSON envelope into IntentClassification objects with the right IntentType.
   The ZAI client is mocked (no live LLM), so these are deterministic. Each
   canned utterance is paired with the canned JSON response the router would
   realistically receive for it, and we assert the parsed IntentType matches.

2. **Router→fetch-command mapping** — for each classifiable intent type, the
   router's _map_intent_type() must resolve to the correct fetch IntentType,
   and get_fetch_commands() must return exactly the source set defined in
   FETCH_COMMAND_MATRIX (src/fetch/commands.py). This is the contract that the
   orchestrator depends on: a mis-mapped intent fetches the wrong sources (or
   none at all).

The pre-canned utterances below also serve as documentation of what each
intent type looks like in practice.
"""

import json
from pathlib import Path
from tempfile import NamedTemporaryFile
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.components.hot_reload import HotReloadManager
from src.fetch.commands import (
    FETCH_COMMAND_MATRIX,
    FetchSource,
    get_fetch_commands,
    get_required_sources,
)
from src.fetch.commands import (
    IntentType as FetchIntentType,
)
from src.intent.router import IntentRouter, IntentType

# --- pre-canned utterances --------------------------------------------------
# Each entry: (utterance, canned LLM JSON response, expected IntentType).
# The canned response is what the (mocked) ZAI client returns for that
# utterance — i.e. the segmentation/classification the router must reproduce.
CANNED_CLASSIFICATIONS = [
    (
        "how are the pods doing in ardenone-manager?",
        json.dumps([{
            "intent_type": "status",
            "project_slug": "ardenone-manager",
            "urgency": "normal",
            "utterance_fragment": "how are the pods doing in ardenone-manager?",
            "confidence": 0.95,
            "reasoning": "querying current cluster state",
        }]),
        IntentType.STATUS,
    ),
    (
        "restart the kalshi-tape deployment",
        json.dumps([{
            "intent_type": "action",
            "project_slug": "kalshi-tape",
            "urgency": "high",
            "utterance_fragment": "restart the kalshi-tape deployment",
            "confidence": 0.92,
            "reasoning": "execute a mutating command against a deployment",
        }]),
        IntentType.ACTION,
    ),
    (
        "let's sketch out a caching layer for the fetch orchestrator",
        json.dumps([{
            "intent_type": "brainstorm",
            "project_slug": "aide-de-camp",
            "urgency": "low",
            "utterance_fragment": "sketch out a caching layer for the fetch orchestrator",
            "confidence": 0.88,
            "reasoning": "open-ended design discussion",
        }]),
        IntentType.BRAINSTORM,
    ),
    (
        "show me the last 100 lines of the weather-fast logs",
        json.dumps([{
            "intent_type": "lookup",
            "project_slug": "kalshi-weather",
            "urgency": "normal",
            "utterance_fragment": "last 100 lines of the weather-fast logs",
            "confidence": 0.9,
            "reasoning": "fetching specific log information",
        }]),
        IntentType.LOOKUP,
    ),
    (
        "remind me to check the deploy at 5pm",
        json.dumps([{
            "intent_type": "reminder",
            "project_slug": None,
            "urgency": "normal",
            "utterance_fragment": "remind me to check the deploy at 5pm",
            "confidence": 0.93,
            "reasoning": "scheduling a reminder",
        }]),
        IntentType.REMINDER,
    ),
    (
        "add a new intent type for incident triage",
        json.dumps([{
            "intent_type": "self-modification",
            "project_slug": "aide-de-camp",
            "urgency": "normal",
            "utterance_fragment": "add a new intent type for incident triage",
            "confidence": 0.9,
            "reasoning": "instruction to modify the interface itself",
        }]),
        IntentType.SELF_MODIFICATION,
    ),
    (
        "set up an alert when pod restarts exceed 5",
        json.dumps([{
            "intent_type": "monitoring-config",
            "project_slug": None,
            "urgency": "normal",
            "utterance_fragment": "set up an alert when pod restarts exceed 5",
            "confidence": 0.87,
            "reasoning": "configuring an ambient monitoring rule",
        }]),
        IntentType.MONITORING_CONFIG,
    ),
    (
        "implement a Telegram digest feature for the canvas",
        json.dumps([{
            "intent_type": "task-profile",
            "project_slug": "aide-de-camp",
            "urgency": "normal",
            "utterance_fragment": "implement a Telegram digest feature for the canvas",
            "confidence": 0.91,
            "reasoning": "multi-step feature work that escalates to a NEEDLE bead",
        }]),
        IntentType.TASK_PROFILE,
    ),
    (
        "uh, what about the thing?",
        json.dumps([{
            "intent_type": "clarification",
            "project_slug": None,
            "urgency": "low",
            "utterance_fragment": "uh, what about the thing?",
            "confidence": 0.4,
            "reasoning": "ambiguous fragment below the confidence threshold",
        }]),
        IntentType.CLARIFICATION,
    ),
]


# Expected fetch sources per router IntentType, mirroring FETCH_COMMAND_MATRIX
# in src/fetch/commands.py. Update these in lock-step when the matrix changes
# intentionally — a divergence here means the router is fetching the wrong
# (or no) sources for an intent type.
EXPECTED_FETCH_SOURCES = {
    IntentType.STATUS: {
        FetchSource.FS_EXPLORE, FetchSource.FS_README, FetchSource.KUBECTL_PODS,
        FetchSource.ARGOCD_APP, FetchSource.GIT_LOG, FetchSource.BEAD_LIST,
        FetchSource.CI_STATUS,
    },
    IntentType.ACTION: {
        FetchSource.KUBECTL_PODS, FetchSource.KUBECTL_DEPLOYMENTS,
        FetchSource.ARGOCD_APP, FetchSource.GIT_STATUS, FetchSource.BEAD_LIST,
    },
    IntentType.BRAINSTORM: {
        FetchSource.FS_EXPLORE, FetchSource.FS_README, FetchSource.COMPONENTS,
        FetchSource.GIT_LOG, FetchSource.TOPIC_CONTEXT,
    },
    IntentType.LOOKUP: {
        FetchSource.FS_HOME, FetchSource.FS_EXPLORE, FetchSource.FS_README,
        FetchSource.LOGS, FetchSource.EVENTS, FetchSource.KUBECTL_PODS,
    },
    IntentType.REMINDER: {FetchSource.REMINDERS},
    IntentType.SELF_MODIFICATION: {
        FetchSource.SESSION_STATE, FetchSource.COMPONENTS, FetchSource.GIT_LOG,
    },
    IntentType.MONITORING_CONFIG: {
        FetchSource.COMPONENTS, FetchSource.KUBECTL_PODS,
    },
}

# Required fetch sources per router IntentType (the sources the orchestrator
# treats as mandatory for that intent). Mirrors required=True in the matrix.
EXPECTED_REQUIRED_SOURCES = {
    IntentType.STATUS: set(),
    IntentType.ACTION: {
        FetchSource.KUBECTL_PODS, FetchSource.KUBECTL_DEPLOYMENTS,
        FetchSource.ARGOCD_APP,
    },
    IntentType.BRAINSTORM: set(),
    IntentType.LOOKUP: set(),
    IntentType.REMINDER: {FetchSource.REMINDERS},
    IntentType.SELF_MODIFICATION: {FetchSource.SESSION_STATE},
    IntentType.MONITORING_CONFIG: {FetchSource.COMPONENTS},
}


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


def _make_router_with_response(router, response_text):
    """Wire a mock ZAI client onto the router that returns response_text."""
    mock_client = AsyncMock()
    mock_client.call_simple = AsyncMock(return_value=response_text)
    router._zai_client = mock_client
    return router


# --- 1. classification parsing ---------------------------------------------

class TestIntentClassification:
    """Each pre-canned utterance classifies to its expected IntentType."""

    @pytest.mark.parametrize(
        "utterance,canned_response,expected_type",
        CANNED_CLASSIFICATIONS,
        ids=[c[2].value for c in CANNED_CLASSIFICATIONS],
    )
    @pytest.mark.asyncio
    async def test_utterance_classifies_to_expected_intent(
        self, router, utterance, canned_response, expected_type
    ):
        r = _make_router_with_response(router, canned_response)

        classifications = await r.classify_utterance(utterance, "session-test")

        assert len(classifications) == 1
        assert classifications[0].intent_type == expected_type
        # The fragment is propagated from the canned response, not dropped.
        assert classifications[0].utterance_fragment

    @pytest.mark.asyncio
    async def test_classification_preserves_project_slug_and_urgency(self, router):
        """project_slug and urgency from the LLM response reach the object."""
        canned = json.dumps([{
            "intent_type": "status",
            "project_slug": "kalshi-weather",
            "urgency": "critical",
            "utterance_fragment": "is weather-fast down?",
            "confidence": 0.97,
            "reasoning": "production health check",
        }])
        r = _make_router_with_response(router, canned)

        [classification] = await r.classify_utterance(
            "is weather-fast down?", "session-test"
        )

        assert classification.project_slug == "kalshi-weather"
        assert classification.urgency == "critical"
        assert classification.confidence == pytest.approx(0.97)
        assert classification.reasoning == "production health check"

    @pytest.mark.asyncio
    async def test_unknown_intent_string_falls_back_to_status(self, router):
        """An unrecognized intent_type string degrades to STATUS, not a crash."""
        canned = json.dumps([{
            "intent_type": "this-intent-does-not-exist",
            "utterance_fragment": "mystery",
        }])
        r = _make_router_with_response(router, canned)

        [classification] = await r.classify_utterance("mystery", "session-test")

        assert classification.intent_type == IntentType.STATUS


# --- 2. markdown fence stripping -------------------------------------------

class TestMarkdownFenceStripping:
    """GLM-4.7 wraps JSON in ```json ... ``` fences; the router must strip them."""

    @pytest.mark.asyncio
    async def test_fenced_json_parses_correctly(self, router):
        fenced = "```json\n" + json.dumps([{
            "intent_type": "lookup",
            "utterance_fragment": "show me the logs",
            "confidence": 0.9,
        }]) + "\n```"
        r = _make_router_with_response(router, fenced)

        [classification] = await r.classify_utterance(
            "show me the logs", "session-test"
        )

        assert classification.intent_type == IntentType.LOOKUP

    @pytest.mark.asyncio
    async def test_unfenced_json_still_parses(self, router):
        """Bare JSON (no fences) must keep working — stripping is conditional."""
        bare = json.dumps([{
            "intent_type": "reminder",
            "utterance_fragment": "remind me",
        }])
        r = _make_router_with_response(router, bare)

        [classification] = await r.classify_utterance("remind me", "session-test")

        assert classification.intent_type == IntentType.REMINDER


# --- 3. multi-intent segmentation ------------------------------------------

class TestMultiIntentSegmentation:
    """A compound utterance segments into multiple distinct intents."""

    @pytest.mark.asyncio
    async def test_deploy_then_check_yields_action_and_status(self, router):
        canned = json.dumps([
            {
                "intent_type": "action",
                "project_slug": "options-pipeline",
                "urgency": "high",
                "utterance_fragment": "deploy the pipeline",
                "confidence": 0.9,
                "reasoning": "first",
            },
            {
                "intent_type": "status",
                "project_slug": "options-pipeline",
                "urgency": "normal",
                "utterance_fragment": "check if it synced",
                "confidence": 0.88,
                "reasoning": "second",
            },
        ])
        r = _make_router_with_response(router, canned)

        classifications = await r.classify_utterance(
            "deploy the pipeline and check if it synced", "session-test"
        )

        assert [c.intent_type for c in classifications] == [
            IntentType.ACTION,
            IntentType.STATUS,
        ]
        assert classifications[0].utterance_fragment == "deploy the pipeline"
        assert classifications[1].utterance_fragment == "check if it synced"


# --- 4. router → fetch command mapping -------------------------------------

class TestIntentToFetchCommandMapping:
    """The router maps each intent to the correct fetch source set."""

    @pytest.mark.parametrize("intent_type", list(EXPECTED_FETCH_SOURCES))
    def test_map_intent_type_resolves_correctly(self, intent_type):
        """_map_intent_type maps router IntentType → fetch IntentType."""
        router = IntentRouter()
        mapped = router._map_intent_type(intent_type)
        assert mapped == FetchIntentType(intent_type.value)

    @pytest.mark.parametrize("intent_type", list(EXPECTED_FETCH_SOURCES))
    def test_fetch_command_source_set_matches_matrix(self, intent_type):
        """
        For each fetchable intent, the source set returned by
        get_fetch_commands matches the matrix (order-independent). A divergence
        means an intent fetches the wrong — or no — sources.
        """
        mapped = IntentRouter()._map_intent_type(intent_type)
        specs = get_fetch_commands(mapped)
        actual_sources = {spec.source for spec in specs}

        assert actual_sources == EXPECTED_FETCH_SOURCES[intent_type], (
            f"Source set for {intent_type.value} diverged from expected"
        )

    @pytest.mark.parametrize("intent_type", list(EXPECTED_REQUIRED_SOURCES))
    def test_required_sources_match_matrix(self, intent_type):
        """Required sources for each intent match the matrix's required=True set."""
        mapped = IntentRouter()._map_intent_type(intent_type)
        required = set(get_required_sources(mapped))

        assert required == EXPECTED_REQUIRED_SOURCES[intent_type], (
            f"Required sources for {intent_type.value} diverged from expected"
        )

    def test_expected_sets_are_consistent_with_matrix_definition(self):
        """
        Guard against the EXPECTED_* dicts and FETCH_COMMAND_MATRIX drifting
        apart silently: every fetchable intent present in the matrix must have
        an expected entry, and vice-versa.

        Compared on .value strings because FETCH_COMMAND_MATRIX is keyed by the
        fetch IntentType while EXPECTED_FETCH_SOURCES is keyed by the router
        IntentType — sibling enums that share value strings (the same contract
        _map_intent_type relies on) but are distinct classes.
        """
        matrix_values = {t.value for t in FETCH_COMMAND_MATRIX}
        expected_values = {t.value for t in EXPECTED_FETCH_SOURCES}

        # TASK_PROFILE/CLARIFICATION are intentionally absent from EXPECTED_*
        # (TASK_PROFILE escalates instead of fetching; CLARIFICATION is a
        # non-dispatched meta-type). Every *other* matrix intent must be covered.
        assert expected_values == matrix_values, (
            "EXPECTED_FETCH_SOURCES does not cover exactly the fetch matrix"
        )

    def test_action_intent_has_required_sources_others_optional(self):
        """
        ACTION is the canonical 'required source' intent: its required sources
        are a proper non-empty subset of its full source set, and the
        orchestrator will treat their failure as blocking.
        """
        mapped = IntentRouter()._map_intent_type(IntentType.ACTION)
        full = {s.source for s in get_fetch_commands(mapped)}
        required = set(get_required_sources(mapped))

        assert required  # non-empty
        assert required.issubset(full)  # required ⊆ full
        assert FetchSource.KUBECTL_DEPLOYMENTS in required  # the action-specific source


# --- 5. meta-type handling: TASK_PROFILE & CLARIFICATION --------------------

class TestMetaTypeHandling:
    """
    TASK_PROFILE and CLARIFICATION are not dispatched to the fetch pipeline:
    TASK_PROFILE escalates to a NEEDLE bead, CLARIFICATION awaits user input.
    Neither should resolve fetch commands.
    """

    @pytest.mark.asyncio
    async def test_task_profile_classifies_but_does_not_fetch(self, router):
        canned = json.dumps([{
            "intent_type": "task-profile",
            "utterance_fragment": "implement the digest feature",
            "confidence": 0.9,
        }])
        r = _make_router_with_response(router, canned)

        [classification] = await r.classify_utterance(
            "implement the digest feature", "session-test"
        )

        # Classified correctly...
        assert classification.intent_type == IntentType.TASK_PROFILE
        # ...but its string value is not a key in the fetch matrix, so it would
        # never resolve real fetch sources (process_intent escalates instead).
        mapped = r._map_intent_type(IntentType.TASK_PROFILE)
        # The default fallback is STATUS, proving TASK_PROFILE has no dedicated
        # fetch mapping of its own.
        assert mapped == FetchIntentType.STATUS

    @pytest.mark.asyncio
    async def test_clarification_is_not_a_fetch_intent(self, router):
        """CLARIFICATION is a meta-type with no dedicated fetch mapping."""
        canned = json.dumps([{
            "intent_type": "clarification",
            "utterance_fragment": "what?",
            "confidence": 0.3,
        }])
        r = _make_router_with_response(router, canned)

        [classification] = await r.classify_utterance("what?", "session-test")

        assert classification.intent_type == IntentType.CLARIFICATION
        # Its value is absent from the fetch matrix.
        assert classification.intent_type.value not in {
            t.value for t in FETCH_COMMAND_MATRIX
        }


# --- 6. malformed-response fallback ----------------------------------------

class TestFallbackOnMalformedResponse:
    """A non-JSON LLM response must degrade to a single STATUS intent, not raise."""

    @pytest.mark.asyncio
    async def test_unparseable_response_defaults_to_status(self, router):
        r = _make_router_with_response(router, "this is not json at all")

        classifications = await r.classify_utterance(
            "something happened", "session-test"
        )

        assert len(classifications) == 1
        assert classifications[0].intent_type == IntentType.STATUS
        assert classifications[0].confidence < 0.6  # flagged as low-confidence


# --- 7. edge cases: empty/ambiguous inputs (bead adc-5qdx) ------------------
#
# The classes above cover the happy path for every IntentType plus malformed
# responses. This class closes the edge-case gap called out in the acceptance
# criteria — empty strings, whitespace-only input, zero-intent responses, and
# stripped-down LLM payloads missing optional fields. The ZAI client is still
# mocked, so each case is deterministic: we feed the exact JSON envelope the
# router would receive for that degenerate input and assert it degrades safely
# rather than raising.


class TestEdgeCases:
    """Empty, whitespace, and ambiguous inputs must classify without raising."""

    @pytest.mark.asyncio
    async def test_empty_string_utterance_classifies_to_clarification(self, router):
        """
        An empty utterance must flow through classify_utterance without raising.
        A realistic LLM response for empty input is a single low-confidence
        clarification; the router must reproduce that verdict.
        """
        canned = json.dumps([{
            "intent_type": "clarification",
            "utterance_fragment": "",
            "confidence": 0.2,
            "reasoning": "empty utterance, nothing to route",
        }])
        r = _make_router_with_response(router, canned)

        [classification] = await r.classify_utterance("", "session-test")

        assert classification.intent_type == IntentType.CLARIFICATION
        assert classification.utterance_fragment == ""

    @pytest.mark.asyncio
    async def test_whitespace_only_utterance_does_not_crash(self, router):
        """Whitespace-only input is no different structurally from empty."""
        canned = json.dumps([{
            "intent_type": "clarification",
            "utterance_fragment": "",
            "confidence": 0.1,
            "reasoning": "whitespace only",
        }])
        r = _make_router_with_response(router, canned)

        [classification] = await r.classify_utterance("   \n\t  ", "session-test")

        assert classification.intent_type == IntentType.CLARIFICATION

    @pytest.mark.asyncio
    async def test_empty_intent_array_returns_empty_list(self, router):
        """
        If the LLM segments the utterance into zero intents (empty JSON array),
        the router returns an empty list — not None, not a crash, not a
        synthesized fallback. Callers must tolerate [].
        """
        r = _make_router_with_response(router, "[]")

        classifications = await r.classify_utterance(
            "anything — model returned no intents", "session-test"
        )

        assert classifications == []

    @pytest.mark.asyncio
    async def test_missing_optional_fields_use_defaults(self, router):
        """
        The router must tolerate a minimal payload containing only intent_type.
        Every optional field falls back to a defined default rather than
        KeyError/AttributeError. Locks the .get()-with-default contract in
        classify_utterance against drift in the IntentClassification dataclass.
        """
        utterance = "show me the deploy status"
        canned = json.dumps([{"intent_type": "status"}])
        r = _make_router_with_response(router, canned)

        [classification] = await r.classify_utterance(utterance, "session-test")

        assert classification.intent_type == IntentType.STATUS
        assert classification.project_slug is None
        assert classification.urgency == "normal"
        assert classification.reasoning == ""
        # confidence default in the parser is 0.8 (NOT the dataclass's 1.0).
        assert classification.confidence == pytest.approx(0.8)
        # fragment falls back to the full utterance when the LLM omits it.
        assert classification.utterance_fragment == utterance

    @pytest.mark.asyncio
    async def test_deeply_ambiguous_fragment_routes_to_clarification(self, router):
        """
        Per prompts/router.md, confidence < 0.7 routes to clarification. A
        maximally ambiguous fragment ("hmm") yields a clarification intent with
        sub-threshold confidence — the router must surface that meta-type intact
        rather than forcing a best-guess dispatch.
        """
        canned = json.dumps([{
            "intent_type": "clarification",
            "utterance_fragment": "hmm",
            "confidence": 0.35,
            "reasoning": "no actionable signal in the utterance",
        }])
        r = _make_router_with_response(router, canned)

        [classification] = await r.classify_utterance("hmm", "session-test")

        assert classification.intent_type == IntentType.CLARIFICATION
        assert classification.confidence < 0.7

    @pytest.mark.asyncio
    async def test_missing_intent_type_field_defaults_to_status(self, router):
        """
        An intent object with no intent_type key at all must fall back to STATUS
        (the parser's documented default) rather than raising — mirrors the
        unknown-string fallback but for the field-absent case.
        """
        canned = json.dumps([{"utterance_fragment": "something"}])
        r = _make_router_with_response(router, canned)

        [classification] = await r.classify_utterance("something", "session-test")

        assert classification.intent_type == IntentType.STATUS
