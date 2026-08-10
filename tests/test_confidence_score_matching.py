"""Regression tests for confidence-score equivalence between endpoints.

/dispatch returns an acknowledgement rather than the routed classifications,
so these tests observe the classifications at the router boundary while the
production endpoint is handling the request.  The direct
/api/v1/test/test/intent-classify endpoint is then compared with those same
classifications.

The acceptable variance is an absolute difference of at most 0.01.  This is
the existing endpoint-comparison contract and is deliberately large enough
for JSON/float representation differences while still detecting a meaningful
confidence-scoring regression.  Deterministic fast-path classifications are
expected to be identical (and currently have zero observed variance).
"""

from __future__ import annotations

from typing import Any

import pytest

from src.intent.unified_comparison import compare_confidence_scores
from tests.helpers.endpoint_comparison import send_to_both_endpoints

CONFIDENCE_TOLERANCE = 0.01

INTENT_CASES = [
    pytest.param("how are the pods doing", "status", id="status"),
    pytest.param("restart the nap-api deployment", "action", id="action"),
    pytest.param(
        "brainstorm ways to improve service reliability",
        "brainstorm",
        id="brainstorm",
    ),
    pytest.param("show me the recent logs for nap-api", "lookup", id="lookup"),
    pytest.param(
        "queue up a research task for the failed deployment",
        "task-profile",
        id="task-profile",
    ),
]


class _DispatchClassificationCapture:
    """Proxy the production router and retain routed classifications by ID."""

    def __init__(self) -> None:
        self.delegate: Any = None
        self.classifications_by_utterance_id: dict[str, list[dict[str, Any]]] = {}

    async def route_utterance(
        self, *, utterance: str, utterance_id: str, session_id: str
    ) -> Any:
        routed_intents = await self.delegate.route_utterance(
            utterance=utterance,
            utterance_id=utterance_id,
            session_id=session_id,
        )
        self.classifications_by_utterance_id[utterance_id] = [
            self._serialize_classification(routed_intent.classification)
            for routed_intent in routed_intents
        ]
        return routed_intents

    @staticmethod
    def _serialize_classification(classification: Any) -> dict[str, Any]:
        intent_type = classification.intent_type
        if hasattr(intent_type, "value"):
            intent_type = intent_type.value

        return {
            "intent_type": intent_type,
            "confidence": classification.confidence,
        }

    def __getattr__(self, name: str) -> Any:
        if self.delegate is None:
            raise AttributeError(name)
        return getattr(self.delegate, name)


@pytest.fixture
def endpoint_context(monkeypatch: pytest.MonkeyPatch):
    """Expose production routed classifications without changing endpoint code."""

    import src.main as main_module
    from src.intent.router import clear_router_cache

    clear_router_cache()
    capture = _DispatchClassificationCapture()
    original_get_router = main_module.get_intent_router

    def get_capturing_router(store: Any = None) -> _DispatchClassificationCapture:
        capture.delegate = original_get_router(store)
        return capture

    monkeypatch.setattr(main_module, "get_intent_router", get_capturing_router)
    return main_module.app, capture


def _scores_for_dispatch_and_test(
    dispatch_result: dict[str, Any],
    test_result: dict[str, Any],
    capture: _DispatchClassificationCapture,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return the captured production and direct-test classifications."""

    dispatch_classifications = capture.classifications_by_utterance_id.get(
        dispatch_result["utterance_id"]
    )
    assert dispatch_classifications is not None

    test_classifications = test_result.get("classifications", [])
    assert len(dispatch_classifications) == len(test_classifications)
    return dispatch_classifications, test_classifications


@pytest.mark.asyncio
@pytest.mark.parametrize("utterance, expected_intent_type", INTENT_CASES)
async def test_confidence_scores_match_for_each_intent_type(
    endpoint_context,
    utterance: str,
    expected_intent_type: str,
) -> None:
    """Every supported deterministic intent keeps the same confidence score."""

    app, capture = endpoint_context
    dispatch_result, test_result = await send_to_both_endpoints(
        utterance=utterance,
        session_id=f"confidence-{expected_intent_type}",
        surface_id=f"confidence-surface-{expected_intent_type}",
        app=app,
    )
    dispatch_classifications, test_classifications = _scores_for_dispatch_and_test(
        dispatch_result, test_result, capture
    )

    assert [item["intent_type"] for item in dispatch_classifications] == [
        expected_intent_type
    ]
    assert [item["intent_type"] for item in test_classifications] == [
        expected_intent_type
    ]

    dispatch_confidence = dispatch_classifications[0]["confidence"]
    test_confidence = test_classifications[0]["confidence"]
    assert 0.0 <= dispatch_confidence <= 1.0
    assert 0.0 <= test_confidence <= 1.0
    assert compare_confidence_scores(
        dispatch_confidence,
        test_confidence,
        tolerance=CONFIDENCE_TOLERANCE,
    )
    assert abs(dispatch_confidence - test_confidence) <= CONFIDENCE_TOLERANCE


@pytest.mark.asyncio
async def test_equal_confidence_scores_are_preserved_for_tied_multi_intent_results(
    endpoint_context,
) -> None:
    """A multi-intent result with tied scores remains tied across endpoints."""

    app, capture = endpoint_context
    dispatch_result, test_result = await send_to_both_endpoints(
        utterance="check pod status, and show recent logs",
        session_id="confidence-tied-multi-intent",
        surface_id="confidence-tied-surface",
        app=app,
    )
    dispatch_classifications, test_classifications = _scores_for_dispatch_and_test(
        dispatch_result, test_result, capture
    )

    assert [item["intent_type"] for item in dispatch_classifications] == [
        "status",
        "lookup",
    ]
    assert [item["intent_type"] for item in test_classifications] == [
        "status",
        "lookup",
    ]
    assert len(dispatch_classifications) == 2
    assert dispatch_classifications[0]["confidence"] == dispatch_classifications[1][
        "confidence"
    ]
    assert test_classifications[0]["confidence"] == test_classifications[1]["confidence"]

    for dispatch_classification, test_classification in zip(
        dispatch_classifications,
        test_classifications,
    ):
        assert compare_confidence_scores(
            dispatch_classification["confidence"],
            test_classification["confidence"],
            tolerance=CONFIDENCE_TOLERANCE,
        )


@pytest.mark.parametrize(
    ("dispatch_confidence", "test_confidence"),
    [
        pytest.param(0.0, 0.0, id="low-exact-zero"),
        pytest.param(0.0, 0.009999, id="low-within-tolerance"),
        pytest.param(0.5, 0.500001, id="middle-within-tolerance"),
        pytest.param(0.999999, 1.0, id="high-within-tolerance"),
        pytest.param(1.0, 1.0, id="high-exact-one"),
    ],
)
def test_confidence_comparison_covers_the_full_score_range(
    dispatch_confidence: float,
    test_confidence: float,
) -> None:
    """Boundary and representative scores compare safely with float tolerance."""

    assert compare_confidence_scores(
        dispatch_confidence,
        test_confidence,
        tolerance=CONFIDENCE_TOLERANCE,
    )


@pytest.mark.parametrize(
    ("dispatch_confidence", "test_confidence"),
    [
        pytest.param(0.0, 0.010001, id="low-outside-tolerance"),
        pytest.param(0.5, 0.511, id="middle-outside-tolerance"),
        pytest.param(0.989, 1.0, id="high-outside-tolerance"),
    ],
)
def test_confidence_comparison_rejects_variance_above_tolerance(
    dispatch_confidence: float,
    test_confidence: float,
) -> None:
    """A score difference above the documented variance remains a failure."""

    assert not compare_confidence_scores(
        dispatch_confidence,
        test_confidence,
        tolerance=CONFIDENCE_TOLERANCE,
    )


@pytest.mark.parametrize(
    ("dispatch_confidence", "test_confidence"),
    [
        pytest.param(None, 0.5, id="missing-dispatch-score"),
        pytest.param(0.5, None, id="missing-test-score"),
        pytest.param(float("nan"), 0.5, id="nan-dispatch-score"),
        pytest.param(0.5, float("nan"), id="nan-test-score"),
    ],
)
def test_invalid_confidence_scores_do_not_match(
    dispatch_confidence: Any,
    test_confidence: Any,
) -> None:
    """Missing or non-finite confidence values cannot hide a regression."""

    assert not compare_confidence_scores(
        dispatch_confidence,
        test_confidence,
        tolerance=CONFIDENCE_TOLERANCE,
    )
