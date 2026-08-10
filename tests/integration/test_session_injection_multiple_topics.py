"""End-to-end session injection coverage for multiple topics.

This test deliberately uses the live HTTP service rather than an ASGI or mock
transport.  ``ADC_TEST_DB_PATH`` must point at the isolated database configured
for that service.  The test is skipped without an explicit isolated database so
it can never write test rows to production ``data/session.db`` by accident.
"""

from __future__ import annotations

import os
from pathlib import Path

import aiosqlite
import httpx
import pytest

from src.session.store import SessionStore
from src.test.topic_injection import TestTopicClient as TopicClient
from src.test.utilities import (
    TestDataBuilder,
    TestDataCleanup,
)
from src.test.utilities import (
    TestSessionClient as SessionClient,
)

BASE_URL = os.environ.get("ADC_TEST_BASE_URL", "http://localhost:8000")
ISOLATED_DATABASE_PATH = os.environ.get("ADC_TEST_DB_PATH") or os.environ.get(
    "ADC_DB_PATH"
)
DATABASE_PATH = Path(ISOLATED_DATABASE_PATH) if ISOLATED_DATABASE_PATH else None


class _DeterministicTopicClient(TopicClient):
    """Use the real deterministic topic endpoint with the shared batch client."""

    async def create_topic(
        self,
        utterance: str,
        session_id: str,
        surface_id: str,
        *,
        known_topic_ids: set[str] | None = None,
    ) -> dict:
        """Create one topic through HTTP and normalize its test response."""
        client = self._require_client()
        response = await client.post(
            self.dispatch_url,
            json={
                "session_id": session_id,
                "label": utterance,
                "type": "project",
                "summary": f"Injected result for {utterance}",
            },
        )
        response.raise_for_status()
        data = response.json()
        data["result"] = {"result_id": data["result_id"]}
        return data


def _server_is_up() -> bool:
    """Return whether the required real ADC HTTP endpoints are available."""
    try:
        with httpx.Client(timeout=2.0) as client:
            if client.get(f"{BASE_URL}/health").status_code != 200:
                return False
            openapi = client.get(f"{BASE_URL}/openapi.json")
            if openapi.status_code != 200:
                return False
            paths = openapi.json().get("paths", {})
            return (
                "/api/v1/sessions" in paths
                and "/api/v1/test/test/create-topic" in paths
                and "/api/v1/sessions/{session_id}/topics" in paths
            )
    except httpx.HTTPError:
        return False


def _has_isolated_database() -> bool:
    """Require an explicit non-production database for the live test."""
    if DATABASE_PATH is None:
        return False
    return DATABASE_PATH.resolve() != Path(
        "/home/coding/aide-de-camp/data/session.db"
    ).resolve()


pytestmark = [
    pytest.mark.skipif(
        not _server_is_up(),
        reason="ADC server is not running at ADC_TEST_BASE_URL",
    ),
    pytest.mark.skipif(
        not _has_isolated_database(),
        reason="ADC_TEST_DB_PATH or ADC_DB_PATH must point to a non-production database",
    ),
]


async def _row_count(db_path: Path, query: str, parameters: tuple[str, ...]) -> int:
    """Return a scalar count from the service database."""
    async with aiosqlite.connect(db_path) as db:
        async with db.execute(query, parameters) as cursor:
            row = await cursor.fetchone()
    return int(row[0]) if row else 0


async def _session_data_counts(db_path: Path, session_id: str) -> dict[str, int]:
    """Count every session-owned row type that the injection path can create."""
    queries = {
        "sessions": "SELECT COUNT(*) FROM sessions WHERE id = ?",
        "surfaces": "SELECT COUNT(*) FROM surfaces WHERE session_id = ?",
        "utterances": "SELECT COUNT(*) FROM utterances WHERE session_id = ?",
        "intents": "SELECT COUNT(*) FROM intents WHERE session_id = ?",
        "results": "SELECT COUNT(*) FROM results WHERE session_id = ?",
        "topics": "SELECT COUNT(*) FROM topics WHERE session_id = ?",
        "intent_topics": (
            "SELECT COUNT(*) FROM intent_topics "
            "WHERE intent_id IN (SELECT id FROM intents WHERE session_id = ?)"
        ),
        "dispatch_timings": "SELECT COUNT(*) FROM dispatch_timings WHERE session_id = ?",
        "topic_context_cache": (
            "SELECT COUNT(*) FROM topic_context_cache "
            "WHERE topic_id IN (SELECT id FROM topics WHERE session_id = ?)"
        ),
        "card_cache": (
            "SELECT COUNT(*) FROM card_cache "
            "WHERE result_id IN (SELECT id FROM results WHERE session_id = ?)"
        ),
    }
    return {
        table: await _row_count(db_path, query, (session_id,))
        for table, query in queries.items()
    }


@pytest.mark.asyncio
async def test_session_injection_stores_and_cleans_multiple_topics() -> None:
    """Create, verify, and fully remove three topics through real HTTP APIs."""
    assert DATABASE_PATH is not None
    # The isolated test database makes this stable ID safe to reuse between
    # runs and keeps failures easy to reproduce.
    session_id = "test-inject-multi-topic"
    scenario = [
        TestDataBuilder.build_synthetic_data(
            utterance="check the deployment status for the api service",
            project_slug="api-service",
            topic_label="API service deployment",
            topic_type="project",
            summary="API service deployment is healthy",
        ),
        TestDataBuilder.build_synthetic_data(
            utterance="review recent database migration results",
            project_slug="database-migrations",
            topic_label="Database migrations",
            topic_type="research",
            summary="Database migrations completed successfully",
        ),
        TestDataBuilder.build_synthetic_data(
            utterance="check the background worker health",
            project_slug="background-worker",
            topic_label="Background worker",
            topic_type="project",
            summary="Background worker is processing normally",
        ),
    ]

    session_client = SessionClient(base_url=BASE_URL)
    topic_client = _DeterministicTopicClient(
        base_url=BASE_URL,
        dispatch_url=f"{BASE_URL}/api/v1/test/test/create-topic",
    )
    store = SessionStore(DATABASE_PATH)

    try:
        await store.initialize()
        async with session_client, topic_client:
            created_session = await session_client.create_session(session_id)
            assert created_session["session_id"] == session_id

            surface = await session_client.register_surface(session_id)
            surface_id = surface["surface_id"]

            utterances = [
                TestDataBuilder.build_test_utterance(
                    item["topic_label"],
                    intent_type=item["intent_type"],
                    project_slug=item["project_slug"],
                )
                for item in scenario
            ]
            injected = await topic_client.create_topics(
                utterances,
                session_id=session_id,
                surface_id=surface_id,
            )

            assert len(injected) == len(scenario) == 3
            topic_ids = [item["topic_id"] for item in injected]
            assert len(set(topic_ids)) == len(topic_ids)
            assert all(item.get("result") is not None for item in injected)

            topics_response = await session_client.get_session_topics(session_id)
            cards = topics_response["cards"]
            cards_by_id = {card["topic"]["id"]: card for card in cards}

            assert len(cards_by_id) == len(scenario)
            assert set(topic_ids) == set(cards_by_id)
            assert all(
                card["topic"]["session_id"] == session_id
                for card in cards_by_id.values()
            )

            stored_topics = await store.get_active_topics(session_id)
            stored_by_id = {topic["id"]: topic for topic in stored_topics}
            assert set(topic_ids) <= set(stored_by_id)
            assert all(
                stored_by_id[topic_id]["session_id"] == session_id
                for topic_id in topic_ids
            )
            assert await _row_count(
                DATABASE_PATH,
                "SELECT COUNT(*) FROM topics WHERE session_id = ?",
                (session_id,),
            ) == len(scenario)

            summary = await session_client.delete_session(session_id)
            assert summary["session_removed"] == 1

            final_counts = await _session_data_counts(DATABASE_PATH, session_id)
            assert final_counts == {table: 0 for table in final_counts}
    finally:
        # If setup or an assertion fails, remove the same scoped IDs before the
        # store closes so a failed integration run cannot leak test data.
        fallback_cleanup = TestDataCleanup(store, session_ids=[session_id])
        await fallback_cleanup.cleanup()
        await store.close()
