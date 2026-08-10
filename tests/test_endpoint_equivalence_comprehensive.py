"""Equivalence coverage for the production and direct-classification endpoints.

The production ``/dispatch`` response is an acknowledgement and does not
include the full classification object.  The test captures the
``RoutedIntent.classification`` values returned by the production route while
it is handling the request, then compares those values with the response from
``/test/intent-classify`` using the unified comparison utility.
"""

from __future__ import annotations

from typing import Any

import pytest

from src.intent.unified_comparison import compare_classifications
from tests.helpers.endpoint_comparison import (
    RequestValidationError,
    compare_classification_counts,
    send_to_both_endpoints,
)

INTENT_CASES = [
    pytest.param(
        "how are the pods doing",
        ["status"],
        id="status-question",
    ),
    pytest.param(
        "is the cluster healthy?",
        ["status"],
        id="status-health",
    ),
    pytest.param(
        "restart the nap-api deployment",
        ["action"],
        id="action-restart",
    ),
    pytest.param(
        "deploy the latest nap-api image",
        ["action"],
        id="action-deploy",
    ),
    pytest.param(
        "brainstorm ways to improve service reliability",
        ["brainstorm"],
        id="brainstorm",
    ),
    pytest.param(
        "show me the recent logs for nap-api",
        ["lookup"],
        id="lookup-logs",
    ),
    pytest.param(
        "show the deployment configuration for nap-api",
        ["lookup"],
        id="lookup-config",
    ),
    pytest.param(
        "explain the architecture of the nap-api service",
        ["lookup"],
        id="lookup-docs",
    ),
    pytest.param(
        "tell me about the nap-api service",
        ["lookup"],
        id="lookup-general",
    ),
    pytest.param(
        "queue up a research task for the failed deployment",
        ["task-profile"],
        id="task-profile",
    ),
    pytest.param(
        "check pod status, and show recent logs",
        ["status", "lookup"],
        id="multi-intent",
    ),
    pytest.param(
        "check pod status @ prod [api-v2] #blue & green",
        ["status"],
        id="special-characters",
    ),
    pytest.param(
        "check pod status 🚀 — namespace: production",
        ["status"],
        id="unicode-and-punctuation",
    ),
]


def _classification_to_dict(classification: Any) -> dict[str, Any]:
    """Serialize the classification object routed by ``/dispatch``."""

    intent_type = classification.intent_type
    if hasattr(intent_type, "value"):
        intent_type = intent_type.value

    return {
        "intent_type": intent_type,
        "project_slug": classification.project_slug,
        "confidence": classification.confidence,
        "utterance_fragment": classification.utterance_fragment,
        "reasoning": classification.reasoning,
        "urgency": classification.urgency,
        "lookup_kind": classification.lookup_kind,
    }


class _DispatchClassificationCapture:
    """Proxy a router while retaining the classifications it actually routes."""

    def __init__(self) -> None:
        self.delegate = None
        self.classifications_by_utterance_id: dict[str, list[dict[str, Any]]] = {}

    async def route_utterance(self, *, utterance: str, utterance_id: str, session_id: str):
        routed_intents = await self.delegate.route_utterance(
            utterance=utterance,
            utterance_id=utterance_id,
            session_id=session_id,
        )
        self.classifications_by_utterance_id[utterance_id] = [
            _classification_to_dict(routed_intent.classification)
            for routed_intent in routed_intents
        ]
        return routed_intents

    def __getattr__(self, name: str) -> Any:
        """Delegate processing methods used after routing to the real router."""

        if self.delegate is None:
            raise AttributeError(name)
        return getattr(self.delegate, name)


@pytest.fixture
def endpoint_context(monkeypatch):
    """Provide the app with a router proxy for observing production dispatch."""

    import src.main as main_module
    from src.intent.router import clear_router_cache

    clear_router_cache()
    capture = _DispatchClassificationCapture()
    original_get_router = main_module.get_intent_router

    def get_capturing_router(store=None):
        capture.delegate = original_get_router(store)
        return capture

    monkeypatch.setattr(main_module, "get_intent_router", get_capturing_router)
    return main_module.app, capture


@pytest.mark.asyncio
@pytest.mark.parametrize("utterance, expected_intent_types", INTENT_CASES)
async def test_dispatch_and_intent_classify_are_equivalent(
    endpoint_context,
    utterance: str,
    expected_intent_types: list[str],
):
    """Send every utterance to both endpoints and compare all classifications."""

    app, capture = endpoint_context
    dispatch_result, test_result = await send_to_both_endpoints(
        utterance=utterance,
        session_id=f"endpoint-equivalence-{abs(hash(utterance))}",
        surface_id=f"surface-{abs(hash(utterance))}",
        app=app,
    )

    counts = compare_classification_counts(dispatch_result, test_result)
    assert counts["match"], (
        f"Classification count mismatch for {utterance!r}: "
        f"dispatch={counts['dispatch_count']} test={counts['test_count']}"
    )

    utterance_id = dispatch_result["utterance_id"]
    dispatch_classifications = capture.classifications_by_utterance_id.get(utterance_id)
    assert dispatch_classifications is not None, (
        f"/dispatch did not expose routed classifications for utterance {utterance_id}"
    )

    test_intent_types = [item["intent_type"] for item in test_result["classifications"]]
    dispatch_intent_types = [item["intent_type"] for item in dispatch_classifications]
    assert test_intent_types == expected_intent_types
    assert dispatch_intent_types == expected_intent_types

    comparison = compare_classifications(
        {"classifications": dispatch_classifications},
        test_result,
        confidence_tolerance=0.01,
    )
    assert comparison.overall_match, (
        f"Classification mismatch for {utterance!r}: {comparison.summary}; "
        f"details={[result.diffs for result in comparison.results]}"
    )


@pytest.mark.asyncio
async def test_empty_utterance_is_rejected_by_comparison_helper(endpoint_context):
    """The shared helper rejects empty input before either endpoint is called."""

    app, _capture = endpoint_context
    with pytest.raises(RequestValidationError, match="non-empty string"):
        await send_to_both_endpoints(utterance="", app=app)


@pytest.mark.asyncio
async def test_whitespace_only_utterance_is_rejected_by_comparison_helper(endpoint_context):
    """Whitespace-only input is handled as an invalid empty utterance."""

    app, _capture = endpoint_context
    with pytest.raises(RequestValidationError, match="non-empty string"):
        await send_to_both_endpoints(utterance="  \n\t  ", app=app)
