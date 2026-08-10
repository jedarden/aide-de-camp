"""Contract tests for production and test dispatch response behavior."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from httpx import ASGITransport

from src.api.models import DispatchRequest, DispatchResponse
from src.main import app
from src.test.router import dispatch as dispatch_test_endpoint


def _empty_router():
    router = MagicMock()
    router.route_utterance = AsyncMock(return_value=[])
    return router


def _store():
    store = MagicMock()
    store.get_session = AsyncMock(return_value=None)
    store.create_session = AsyncMock()
    store.create_utterance = AsyncMock()
    return store


@pytest.mark.asyncio
async def test_test_dispatch_uses_production_response_envelope():
    store = _store()
    router = _empty_router()
    request = DispatchRequest(
        utterance="  check the test endpoint  ",
        session_id="session-contract",
        surface_id="surface-contract",
        utterance_id="utterance-contract",
    )

    with patch("src.session.store.get_store", new=AsyncMock(return_value=store)), patch(
        "src.intent.router.get_router", return_value=router
    ):
        transport = ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            http_response = await client.post(
                "/api/v1/test/dispatch",
                json=request.model_dump(exclude_none=True),
            )

    assert http_response.status_code == 200
    payload = http_response.json()
    DispatchResponse.model_validate(payload)
    assert set(payload) == {"success", "message", "data"}
    assert payload["success"] is True
    assert payload["data"] == {
        "utterance_id": "utterance-contract",
        "session_id": "session-contract",
        "intent_count": 0,
        "intent_ids": [],
        "status": "dispatched",
        "utterance_confirmation": "check the test endpoint",
    }


@pytest.mark.asyncio
async def test_test_dispatch_router_errors_match_production_error_payload():
    store = _store()
    router = _empty_router()
    router.route_utterance.side_effect = RuntimeError("router unavailable")
    request = DispatchRequest(
        utterance="check the test endpoint",
        session_id="session-contract",
        surface_id="surface-contract",
    )

    with patch("src.session.store.get_store", new=AsyncMock(return_value=store)), patch(
        "src.intent.router.get_router", return_value=router
    ):
        response = await dispatch_test_endpoint(request)

    assert response.status_code == 500
    assert response.body == b'{"error":"Dispatch error: router unavailable"}'


@pytest.mark.asyncio
async def test_dispatch_endpoints_use_same_validation_status_and_shape():
    invalid_payload = {"utterance": "check"}
    transport = ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        production = await client.post("/dispatch", json=invalid_payload)
        test = await client.post("/api/v1/test/dispatch", json=invalid_payload)

    assert production.status_code == 400
    assert test.status_code == production.status_code
    assert set(production.json()) == set(test.json()) == {
        "error",
        "detail",
        "errors",
        "status",
    }
