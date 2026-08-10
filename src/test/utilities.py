"""
Test Data Injection Utilities for Canvas Testing

Provides utilities for creating test sessions, topics, and results via API calls.
Supports test isolation with separate database files and cleanup functionality.
"""
import asyncio
import logging
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

import httpx

from .topic_injection import (
    IntentRoutingError,
    SynthesisError,
    TestTopicClient,
    TopicCreationError,
    TopicInjector,
)

logger = logging.getLogger(__name__)


class TestSessionClientError(RuntimeError):
    """Base exception raised by :class:`TestSessionClient`."""


class SessionCreationError(TestSessionClientError):
    """Raised when the test-session API cannot return a valid session."""


class TestSessionClient:
    """API client for creating and managing test sessions."""

    def __init__(
        self,
        base_url: str = "http://localhost:8000",
        test_db_path: Optional[Path] = None,
    ):
        """
        Initialize the test session client.

        Args:
            base_url: Base URL of the ADC server
            test_db_path: Optional path to isolated test database
        """
        self.base_url = base_url.rstrip("/")
        self.test_db_path = test_db_path
        self.client: Optional[httpx.AsyncClient] = None
        self._created_session_ids: List[str] = []
        self._created_surface_ids: List[str] = []
        self._created_surface_by_session: Dict[str, List[str]] = {}
        self._cleanup_lock = asyncio.Lock()

    async def __aenter__(self):
        """Async context manager entry."""
        if self.client is None or self.client.is_closed:
            self.client = httpx.AsyncClient(timeout=60.0)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit with cleanup."""
        await self.cleanup_all()
        if self.client:
            await self.client.aclose()

    async def create_session(
        self,
        session_id: Optional[str] = None,
    ) -> Dict[str, str]:
        """
        Create a test session via POST /api/v1/sessions.

        Args:
            session_id: Optional session ID (generated if not provided)

        Returns:
            Response containing ``session_id`` and ``created_at``.

        Raises:
            SessionCreationError: If the request fails or the API response is
                not a valid session response.
        """
        session_id = session_id or f"test-inject-{uuid4().hex[:12]}"

        if self.client is None or self.client.is_closed:
            raise SessionCreationError(
                "TestSessionClient is not open; use it as an async context manager"
            )

        try:
            response = await self.client.post(
                f"{self.base_url}/api/v1/sessions",
                json={"session_id": session_id},
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise SessionCreationError(
                f"Failed to create test session: HTTP {exc.response.status_code}"
            ) from exc
        except httpx.RequestError as exc:
            raise SessionCreationError(
                f"Failed to create test session: {exc}"
            ) from exc

        try:
            data = response.json()
        except ValueError as exc:
            raise SessionCreationError(
                "Failed to create test session: response was not valid JSON"
            ) from exc

        if not isinstance(data, dict):
            raise SessionCreationError(
                "Failed to create test session: response must be a JSON object"
            )

        response_session_id = data.get("session_id")
        created_at = data.get("created_at")
        if not isinstance(response_session_id, str) or not response_session_id.strip():
            raise SessionCreationError(
                "Failed to create test session: response is missing a valid session_id"
            )
        if not isinstance(created_at, str) or not created_at.strip():
            raise SessionCreationError(
                "Failed to create test session: response is missing a valid created_at timestamp"
            )

        async with self._cleanup_lock:
            self._created_session_ids.append(response_session_id)

        logger.info("[TEST] Created session: %s", response_session_id)
        return {"session_id": response_session_id, "created_at": created_at}

    async def register_surface(
        self,
        session_id: str,
        surface_type: str = "canvas",
    ) -> Dict[str, str]:
        """Register a surface for a session when a canvas test needs one."""
        if self.client is None or self.client.is_closed:
            raise TestSessionClientError(
                "TestSessionClient is not open; use it as an async context manager"
            )

        try:
            response = await self.client.post(
                f"{self.base_url}/api/v1/surfaces/register",
                json={"session_id": session_id, "surface_type": surface_type},
            )
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPStatusError as exc:
            raise TestSessionClientError(
                f"Failed to register surface: HTTP {exc.response.status_code}"
            ) from exc
        except httpx.RequestError as exc:
            raise TestSessionClientError(f"Failed to register surface: {exc}") from exc
        except ValueError as exc:
            raise TestSessionClientError(
                "Failed to register surface: response was not valid JSON"
            ) from exc

        surface_id = data.get("surface_id") if isinstance(data, dict) else None
        if not isinstance(surface_id, str) or not surface_id.strip():
            raise TestSessionClientError(
                "Failed to register surface: response is missing a valid surface_id"
            )

        async with self._cleanup_lock:
            self._created_surface_ids.append(surface_id)
            self._created_surface_by_session.setdefault(session_id, []).append(surface_id)
        return {"surface_id": surface_id, "session_id": session_id}

    async def dispatch_utterance(
        self,
        utterance: str,
        session_id: str,
        surface_id: Optional[str] = None,
        wait_for_results: bool = False,
        timeout_seconds: int = 30,
    ) -> Dict[str, Any]:
        """
        Dispatch a test utterance via POST /api/v1/test/dispatch.

        Args:
            utterance: Test utterance text
            session_id: Session ID
            surface_id: Optional surface ID for SSE broadcast
            wait_for_results: If True, wait for results before returning
            timeout_seconds: Max wait time for results

        Returns:
            Dispatch response with intent IDs and optional results
        """
        request_data = {
            "utterance": utterance,
            "session_id": session_id,
            "wait_for_results": wait_for_results,
            "timeout_seconds": timeout_seconds,
        }

        if surface_id:
            request_data["surface_id"] = surface_id

        response = await self.client.post(
            f"{self.base_url}/api/v1/test/dispatch",
            json=request_data,
        )

        response.raise_for_status()
        data = response.json()

        logger.info(
            f"[TEST] Dispatched utterance: {utterance[:50]}... "
            f"(intent_count: {data.get('intent_count')})"
        )
        return data

    async def create_synthetic_result(
        self,
        session_id: str,
        surface_id: Optional[str] = None,
        test_data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Create a synthetic result via POST /api/v1/test/dispatch-synthetic.

        Args:
            session_id: Session ID
            surface_id: Optional surface ID for SSE broadcast
            test_data: Optional custom test data

        Returns:
            Synthetic result response with all IDs
        """
        request_data = {
            "session_id": session_id,
        }

        if surface_id:
            request_data["surface_id"] = surface_id

        if test_data:
            request_data["test_data"] = test_data

        response = await self.client.post(
            f"{self.base_url}/api/v1/test/dispatch-synthetic",
            json=request_data,
        )

        response.raise_for_status()
        data = response.json()

        logger.info(f"[TEST] Created synthetic result: {data.get('result_id')}")
        return data

    async def get_session_topics(self, session_id: str) -> Dict[str, Any]:
        """
        Get topics for a session via GET /api/v1/sessions/{session_id}/topics.

        Args:
            session_id: Session ID

        Returns:
            Dict with list of topic cards
        """
        response = await self.client.get(
            f"{self.base_url}/api/v1/sessions/{session_id}/topics"
        )

        response.raise_for_status()
        return response.json()

    async def delete_result(
        self,
        session_id: str,
        result_id: str,
    ) -> Dict[str, Any]:
        """
        Delete a result via DELETE /api/v1/sessions/{session_id}/results/{result_id}.

        Args:
            session_id: Session ID
            result_id: Result ID to delete

        Returns:
            Deletion result
        """
        response = await self.client.delete(
            f"{self.base_url}/api/v1/sessions/{session_id}/results/{result_id}"
        )

        response.raise_for_status()
        logger.info(f"[TEST] Deleted result: {result_id}")
        return response.json()

    async def cleanup_session(self, session_id: str) -> bool:
        """
        Clean up all test data for a session.

        Args:
            session_id: Session ID to clean up

        Returns:
            True if cleanup successful
        """
        try:
            # Get all topics for the session
            topics_response = await self.get_session_topics(session_id)
            cards = topics_response.get("cards", [])

            # Delete each result (this cascades to intents and topics)
            failures = False
            for card in cards:
                result_id = card.get("result_id")
                if result_id:
                    try:
                        await self.delete_result(session_id, result_id)
                    except Exception as e:
                        logger.warning(f"[TEST] Failed to delete result {result_id}: {e}")
                        failures = True

            if failures:
                logger.warning(f"[TEST] Session remains queued for cleanup: {session_id}")
                return False
            logger.info(f"[TEST] Cleaned up session: {session_id}")
            return True

        except Exception as e:
            logger.error(f"[TEST] Session cleanup failed for {session_id}: {e}")
            return False

    async def cleanup_all(self) -> None:
        """Clean up all created sessions and data."""
        async with self._cleanup_lock:
            session_ids = list(dict.fromkeys(self._created_session_ids))
            cleaned_sessions = set()
            for session_id in session_ids:
                if await self.cleanup_session(session_id):
                    cleaned_sessions.add(session_id)

            # Bookkeeping is the local commit point: only confirmed cleanups
            # leave the registry. Failed IDs remain retryable. IDs registered
            # after the snapshot are preserved for the next cleanup pass.
            self._created_session_ids = [
                session_id for session_id in self._created_session_ids
                if session_id not in cleaned_sessions
            ]
            for session_id in cleaned_sessions:
                self._created_surface_by_session.pop(session_id, None)
            self._created_surface_ids = [
                surface_id
                for surfaces in self._created_surface_by_session.values()
                for surface_id in surfaces
            ]
            failed_sessions = [sid for sid in session_ids if sid not in cleaned_sessions]
            if failed_sessions:
                logger.error("[TEST] Retaining failed session cleanup IDs: %s", failed_sessions)
        if not failed_sessions:
            logger.info("[TEST] Cleaned up all test data")


class TestDataBuilder:
    """Builder for creating structured test data."""

    @staticmethod
    def build_test_utterance(
        text: str,
        intent_type: str = "status",
        project_slug: Optional[str] = None,
    ) -> str:
        """
        Build a test utterance with expected characteristics.

        Args:
            text: Utterance text
            intent_type: Expected intent type
            project_slug: Expected project slug

        Returns:
            The utterance text (unchanged, but validates inputs)
        """
        if not text or not text.strip():
            raise ValueError("Utterance text must be non-empty")

        return text

    @staticmethod
    def build_synthetic_data(
        utterance: str = "Test utterance",
        project_slug: str = "test-project",
        intent_type: str = "status",
        topic_label: str = "Test Topic",
        topic_type: str = "research",
        summary: str = "Test result summary",
        data: Optional[Dict[str, Any]] = None,
        urgency: str = "normal",
        result_type: str = "status",
    ) -> Dict[str, Any]:
        """
        Build synthetic test data matching the /dispatch structure.

        Args:
            utterance: Test utterance text
            project_slug: Project slug for the test
            intent_type: Intent type
            topic_label: Topic label
            topic_type: Topic type
            summary: Result summary
            data: Optional custom data dict
            urgency: Result urgency level
            result_type: Result type for component matching

        Returns:
            Complete test data dictionary
        """
        default_data = {
            "test_mode": True,
            "synthetic": True,
            "message": "Synthetic test result",
        }

        if data:
            default_data.update(data)

        return {
            "utterance": utterance,
            "project_slug": project_slug,
            "intent_type": intent_type,
            "topic_label": topic_label,
            "topic_type": topic_type,
            "summary": summary,
            "data": default_data,
            "urgency": urgency,
            "result_type": result_type,
        }

    @staticmethod
    def build_multi_intent_scenario() -> List[Dict[str, Any]]:
        """
        Build a multi-intent test scenario.

        Returns:
            List of test utterances that should generate multiple intents
        """
        return [
            {
                "name": "multi_status",
                "utterance": "check the pipeline and also look at the ibkr status",
                "expected_intent_count": 2,
                "expected_intents": ["status", "status"],
            },
            {
                "name": "lookup_and_status",
                "utterance": "find recent logs and tell me the system health",
                "expected_intent_count": 2,
                "expected_intents": ["lookup", "status"],
            },
        ]


class TestDatabaseIsolation:
    """Utilities for creating isolated test databases."""

    @staticmethod
    def create_temp_db_path() -> Path:
        """
        Create a temporary database file path for isolated testing.

        Returns:
            Path to temporary database file
        """
        temp_dir = Path(tempfile.mkdtemp())
        db_path = temp_dir / "test_session.db"
        return db_path

    @staticmethod
    def create_in_memory_db_connection_string() -> str:
        """
        Get an in-memory database connection string.

        Returns:
            Connection string for in-memory SQLite database
        """
        return ":memory:"


class TestFixture:
    """
    Comprehensive test fixture for canvas testing.

    Combines session management, test data injection, and cleanup
    in a single easy-to-use interface.
    """

    def __init__(
        self,
        base_url: str = "http://localhost:8000",
        auto_cleanup: bool = True,
    ):
        """
        Initialize the test fixture.

        Args:
            base_url: Base URL of the ADC server
            auto_cleanup: If True, automatically clean up on exit
        """
        self.base_url = base_url.rstrip("/")
        self.auto_cleanup = auto_cleanup
        self._client: Optional[TestSessionClient] = None
        self._session_id: Optional[str] = None
        self._surface_id: Optional[str] = None

    async def __aenter__(self):
        """Async context manager entry."""
        self._client = TestSessionClient(base_url=self.base_url)
        await self._client.__aenter__()

        # Create a default test session
        session_data = await self._client.create_session()
        self._session_id = session_data.get("session_id")
        surface_data = await self._client.register_surface(self._session_id)
        self._surface_id = surface_data.get("surface_id")

        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self.auto_cleanup and self._client:
            await self._client.cleanup_all()
            await self._client.__aexit__(exc_type, exc_val, exc_tb)

    async def dispatch(self, utterance: str, **kwargs) -> Dict[str, Any]:
        """Dispatch a test utterance."""
        if not self._client:
            raise RuntimeError("TestFixture not initialized. Use as async context manager.")

        return await self._client.dispatch_utterance(
            utterance=utterance,
            session_id=self._session_id,
            surface_id=self._surface_id,
            **kwargs
        )

    async def create_synthetic(self, test_data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Create a synthetic test result."""
        if not self._client:
            raise RuntimeError("TestFixture not initialized. Use as async context manager.")

        return await self._client.create_synthetic_result(
            session_id=self._session_id,
            surface_id=self._surface_id,
            test_data=test_data,
        )

    async def get_topics(self) -> Dict[str, Any]:
        """Get topics for the test session."""
        if not self._client:
            raise RuntimeError("TestFixture not initialized. Use as async context manager.")

        return await self._client.get_session_topics(self._session_id)

    @property
    def session_id(self) -> str:
        """Get the test session ID."""
        if not self._session_id:
            raise RuntimeError("TestFixture not initialized. Use as async context manager.")
        return self._session_id

    @property
    def surface_id(self) -> str:
        """Get the test surface ID."""
        if not self._surface_id:
            raise RuntimeError("TestFixture not initialized. Use as async context manager.")
        return self._surface_id


# Convenience functions for quick testing
async def create_test_session(
    base_url: str = "http://localhost:8000",
    session_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Quick function to create a test session.

    Args:
        base_url: Base URL of the ADC server
        session_id: Optional session ID

    Returns:
        Session data dict
    """
    async with TestSessionClient(base_url=base_url) as client:
        return await client.create_session(session_id=session_id)


async def dispatch_test_utterance(
    utterance: str,
    session_id: str,
    base_url: str = "http://localhost:8000",
    surface_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Quick function to dispatch a test utterance.

    Args:
        utterance: Test utterance text
        session_id: Session ID
        base_url: Base URL of the ADC server
        surface_id: Optional surface ID

    Returns:
        Dispatch response dict
    """
    async with TestSessionClient(base_url=base_url) as client:
        return await client.dispatch_utterance(
            utterance=utterance,
            session_id=session_id,
            surface_id=surface_id,
        )


async def create_synthetic_test_result(
    session_id: str,
    base_url: str = "http://localhost:8000",
    surface_id: Optional[str] = None,
    test_data: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Quick function to create a synthetic test result.

    Args:
        session_id: Session ID
        base_url: Base URL of the ADC server
        surface_id: Optional surface ID
        test_data: Optional custom test data

    Returns:
        Synthetic result response dict
    """
    async with TestSessionClient(base_url=base_url) as client:
        return await client.create_synthetic_result(
            session_id=session_id,
            surface_id=surface_id,
            test_data=test_data,
        )
# ---------------------------------------------------------------------------
# Database cleanup helpers
# ---------------------------------------------------------------------------


def _unique_ids(ids: Optional[List[str]]) -> List[str]:
    """Return non-empty IDs once, preserving their input order."""
    if ids is None:
        return []

    unique: List[str] = []
    seen = set()
    for value in ids:
        if not isinstance(value, str) or not value:
            raise ValueError("cleanup IDs must be non-empty strings")
        if value not in seen:
            seen.add(value)
            unique.append(value)
    return unique


async def _assert_no_rows(store: Any, table: str, column: str, value: str) -> None:
    """Assert that a cleanup predicate no longer matches any database row."""
    import aiosqlite

    async with aiosqlite.connect(store.db_path) as db:
        async with db.execute(
            f"SELECT COUNT(*) FROM {table} WHERE {column} = ?",  # noqa: S608
            (value,),
        ) as cursor:
            row = await cursor.fetchone()

    count = int(row[0]) if row else 0
    assert count == 0, (
        f"cleanup left {count} rows in {table} for {column}={value!r}; "
        "test data was not fully removed"
    )


async def cleanup_test_sessions(
    store: Any,
    session_ids: Optional[List[str]] = None,
) -> Dict[str, Dict[str, int]]:
    """Delete test sessions and verify their rows are gone.

    The actual deletion is delegated to ``SessionStore.delete_session()``,
    which uses explicit ``DELETE ... WHERE`` statements in a transaction. The
    checks here intentionally query the database after each deletion so a
    teardown cannot silently pass while leaving a session or its topics behind.
    """
    summaries: Dict[str, Dict[str, int]] = {}
    for session_id in _unique_ids(session_ids):
        summaries[session_id] = await store.delete_session(session_id)
        await _assert_no_rows(store, "sessions", "id", session_id)
        await _assert_no_rows(store, "surfaces", "session_id", session_id)
        await _assert_no_rows(store, "utterances", "session_id", session_id)
        await _assert_no_rows(store, "intents", "session_id", session_id)
        await _assert_no_rows(store, "results", "session_id", session_id)
        await _assert_no_rows(store, "topics", "session_id", session_id)
    return summaries


async def cleanup_test_topics(
    store: Any,
    topic_ids: Optional[List[str]] = None,
) -> Dict[str, Dict[str, int]]:
    """Delete test topics and verify their topic-owned rows are gone."""
    summaries: Dict[str, Dict[str, int]] = {}
    for topic_id in _unique_ids(topic_ids):
        summaries[topic_id] = await store.delete_topic(topic_id)
        await _assert_no_rows(store, "topics", "id", topic_id)
        await _assert_no_rows(store, "results", "topic_id", topic_id)
        await _assert_no_rows(store, "topic_context_cache", "topic_id", topic_id)
        await _assert_no_rows(store, "intent_topics", "topic_id", topic_id)
        await _assert_no_rows(store, "feedback_signals", "topic_id", topic_id)
    return summaries


async def cleanup_test_data(
    store: Any,
    session_ids: Optional[List[str]] = None,
    topic_ids: Optional[List[str]] = None,
) -> Dict[str, Dict[str, Dict[str, int]]]:
    """Delete a batch of test sessions and topics.

    Sessions are removed first, making the operation safe when ``topic_ids``
    includes topics owned by one of the sessions. The subsequent topic cleanup
    is idempotent for those already-removed IDs.
    """
    return {
        "sessions": await cleanup_test_sessions(store, session_ids),
        "topics": await cleanup_test_topics(store, topic_ids),
    }


class TestDataCleanup:
    """ID registry used by the pytest teardown fixture.

    Tests register IDs as they create data, for example::

        cleanup.add_session(session_id)
        cleanup.add_topic(topic_id)

    The fixture calls :meth:`cleanup` after the test body, including when the
    test fails. IDs may also be supplied to the constructor for indirect
    parametrized fixtures.
    """

    __test__ = False

    def __init__(
        self,
        store: Any,
        session_ids: Optional[List[str]] = None,
        topic_ids: Optional[List[str]] = None,
    ) -> None:
        self.store = store
        self.session_ids = _unique_ids(session_ids)
        self.topic_ids = _unique_ids(topic_ids)

    def add_session(self, session_id: str) -> str:
        """Register one session ID for teardown."""
        self.session_ids = _unique_ids([*self.session_ids, session_id])
        return session_id

    track_session = add_session

    def add_topic(self, topic_id: str) -> str:
        """Register one topic ID for teardown."""
        self.topic_ids = _unique_ids([*self.topic_ids, topic_id])
        return topic_id

    track_topic = add_topic

    async def cleanup(self) -> Dict[str, Dict[str, Dict[str, int]]]:
        """Delete all registered IDs and assert that no matching rows remain."""
        result = await cleanup_test_data(
            self.store,
            session_ids=self.session_ids,
            topic_ids=self.topic_ids,
        )
        self.session_ids.clear()
        self.topic_ids.clear()
        return result
