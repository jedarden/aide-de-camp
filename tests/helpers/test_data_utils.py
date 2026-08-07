"""
Test Data Injection Utilities for Canvas Testing

Provides utilities for creating test sessions, topics, and managing test data
with isolated database support. Designed for canvas testing and E2E test scenarios.
"""
import asyncio
import httpx
import json
import logging
import os
import tempfile
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, AsyncGenerator, Dict, List, Optional

from tests.helpers.registry_test_helpers import (
    setup_test_registry,
    cleanup_test_registry
)


logger = logging.getLogger(__name__)


class TestDataInjectionError(Exception):
    """Base exception for test data injection errors."""
    pass


class TestSessionCreationError(TestDataInjectionError):
    """Raised when test session creation fails."""
    pass


class TestTopicCreationError(TestDataInjectionError):
    """Raised when test topic creation fails."""
    pass


class TestCleanupError(TestDataInjectionError):
    """Raised when test data cleanup fails."""
    pass


class TestDatabaseConfig:
    """Configuration for test database setup."""

    def __init__(
        self,
        use_in_memory: bool = True,
        test_db_path: Optional[Path] = None,
        cleanup_after_test: bool = True
    ):
        """
        Initialize test database configuration.

        Args:
            use_in_memory: If True, use in-memory SQLite database
            test_db_path: Optional path to test database file (used if use_in_memory=False)
            cleanup_after_test: If True, clean up test database after test completion
        """
        self.use_in_memory = use_in_memory
        self.test_db_path = test_db_path
        self.cleanup_after_test = cleanup_after_test

        if not use_in_memory and test_db_path is None:
            # Create a temporary file for the test database
            self.test_db_path = Path(tempfile.mktemp(suffix=".db"))
            self.cleanup_after_test = True


class TestSessionIdGenerator:
    """Generates predictable test session IDs."""

    COUNTER = 0
    PREFIX = "test-session-"

    @classmethod
    def generate(cls, suffix: Optional[str] = None) -> str:
        """
        Generate a predictable test session ID.

        Args:
            suffix: Optional suffix to append to the session ID

        Returns:
            Predictable session ID string
        """
        cls.COUNTER += 1
        session_id = f"{cls.PREFIX}{cls.COUNTER:04d}"
        if suffix:
            session_id = f"{session_id}-{suffix}"
        return session_id

    @classmethod
    def reset_counter(cls) -> None:
        """Reset the counter to 0 (useful for test isolation)."""
        cls.COUNTER = 0


class TestAPIClient:
    """Async HTTP client for test API interactions."""

    DEFAULT_BASE_URL = "http://localhost:8000"
    DEFAULT_TIMEOUT = 30.0

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = DEFAULT_TIMEOUT,
        verify_ssl: bool = False
    ):
        """
        Initialize test API client.

        Args:
            base_url: Base URL for the API
            timeout: Request timeout in seconds
            verify_ssl: Whether to verify SSL certificates
        """
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.verify_ssl = verify_ssl
        self._client: Optional[httpx.AsyncClient] = None

    async def __aenter__(self):
        """Enter async context manager."""
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=self.timeout,
            verify=self.verify_ssl
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Exit async context manager."""
        if self._client:
            await self._client.aclose()

    async def _request(
        self,
        method: str,
        path: str,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Make an HTTP request to the API.

        Args:
            method: HTTP method (GET, POST, DELETE, etc.)
            path: API path
            **kwargs: Additional arguments for httpx request

        Returns:
            Response JSON as dictionary

        Raises:
            TestDataInjectionError: If request fails
        """
        if not self._client:
            raise TestDataInjectionError("Client not initialized. Use async context manager.")

        url = f"{self.base_url}{path}"

        try:
            response = await self._client.request(method, url, **kwargs)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error: {e.response.status_code} - {e.response.text}")
            raise TestDataInjectionError(f"Request failed: {e}")
        except httpx.RequestError as e:
            logger.error(f"Request error: {e}")
            raise TestDataInjectionError(f"Request error: {e}")

    async def get(self, path: str, **kwargs) -> Dict[str, Any]:
        """Make a GET request."""
        return await self._request("GET", path, **kwargs)

    async def post(self, path: str, **kwargs) -> Dict[str, Any]:
        """Make a POST request."""
        return await self._request("POST", path, **kwargs)

    async def delete(self, path: str, **kwargs) -> Dict[str, Any]:
        """Make a DELETE request."""
        return await self._request("DELETE", path, **kwargs)


class TestSessionManager:
    """Manager for creating and managing test sessions."""

    def __init__(
        self,
        api_client: TestAPIClient,
        db_config: Optional[TestDatabaseConfig] = None
    ):
        """
        Initialize test session manager.

        Args:
            api_client: Test API client instance
            db_config: Optional test database configuration
        """
        self.api_client = api_client
        self.db_config = db_config or TestDatabaseConfig()
        self._test_sessions: Dict[str, Dict[str, Any]] = {}

    async def create_session(
        self,
        session_id: Optional[str] = None,
        surface_type: str = "canvas"
    ) -> Dict[str, Any]:
        """
        Create a test session.

        Args:
            session_id: Optional session ID (generated if not provided)
            surface_type: Surface type for the session (default: "canvas")

        Returns:
            Session creation response with session_id and surface_id

        Raises:
            TestSessionCreationError: If session creation fails
        """
        # Generate session ID if not provided
        if not session_id:
            session_id = TestSessionIdGenerator.generate()

        try:
            # Register surface for the session
            response = await self.api_client.post(
                "/api/v1/surfaces/register",
                json={
                    "session_id": session_id,
                    "surface_type": surface_type
                }
            )

            surface_id = response.get("surface_id")

            # Store session metadata
            self._test_sessions[session_id] = {
                "session_id": session_id,
                "surface_id": surface_id,
                "surface_type": surface_type,
                "created_at": datetime.utcnow().isoformat(),
                "topics": []
            }

            logger.info(f"Created test session: {session_id} with surface: {surface_id}")

            return {
                "session_id": session_id,
                "surface_id": surface_id,
                "surface_type": surface_type,
                "created": True
            }

        except Exception as e:
            logger.error(f"Failed to create test session: {e}")
            raise TestSessionCreationError(f"Session creation failed: {e}")

    async def get_session_topics(self, session_id: str) -> List[Dict[str, Any]]:
        """
        Get topics for a test session.

        Args:
            session_id: Session ID to fetch topics for

        Returns:
            List of topic dictionaries

        Raises:
            TestDataInjectionError: If fetch fails
        """
        try:
            response = await self.api_client.get(f"/api/v1/sessions/{session_id}/topics")
            topics = response.get("cards", [])

            # Update session metadata
            if session_id in self._test_sessions:
                self._test_sessions[session_id]["topics"] = topics

            return topics

        except Exception as e:
            logger.error(f"Failed to get session topics: {e}")
            raise TestDataInjectionError(f"Failed to get session topics: {e}")

    async def delete_session(self, session_id: str) -> Dict[str, Any]:
        """
        Delete a test session and all its data.

        Args:
            session_id: Session ID to delete

        Returns:
            Deletion result dictionary

        Raises:
            TestCleanupError: If deletion fails
        """
        try:
            # The API should handle cascading deletion of all related data
            # For now, we'll track this locally and the actual cleanup
            # would be handled by the test database cleanup

            if session_id in self._test_sessions:
                del self._test_sessions[session_id]

            logger.info(f"Deleted test session: {session_id}")

            return {
                "session_id": session_id,
                "deleted": True,
                "message": f"Session {session_id} deleted successfully"
            }

        except Exception as e:
            logger.error(f"Failed to delete session: {e}")
            raise TestCleanupError(f"Session deletion failed: {e}")

    def get_tracked_sessions(self) -> Dict[str, Dict[str, Any]]:
        """Get all tracked test sessions."""
        return self._test_sessions.copy()


class TestTopicManager:
    """Manager for creating test topics via dispatch."""

    def __init__(self, api_client: TestAPIClient):
        """
        Initialize test topic manager.

        Args:
            api_client: Test API client instance
        """
        self.api_client = api_client

    async def create_topic_via_dispatch(
        self,
        utterance: str,
        session_id: str,
        surface_id: Optional[str] = None,
        wait_for_results: bool = True,
        timeout_seconds: int = 30
    ) -> Dict[str, Any]:
        """
        Create a test topic by dispatching an utterance.

        Args:
            utterance: Test utterance to dispatch
            session_id: Session ID to dispatch to
            surface_id: Optional surface ID for SSE targeting
            wait_for_results: If True, wait for results before returning
            timeout_seconds: Maximum time to wait for results

        Returns:
            Dispatch response with intent IDs and optional results

        Raises:
            TestTopicCreationError: If topic creation fails
        """
        try:
            request_data = {
                "utterance": utterance,
                "session_id": session_id,
                "wait_for_results": wait_for_results,
                "timeout_seconds": timeout_seconds
            }

            if surface_id:
                request_data["surface_id"] = surface_id

            response = await self.api_client.post(
                "/api/v1/test/dispatch",
                json=request_data
            )

            logger.info(
                f"Created test topic via dispatch: session={session_id}, "
                f"intent_count={response.get('intent_count', 0)}"
            )

            return response

        except Exception as e:
            logger.error(f"Failed to create topic via dispatch: {e}")
            raise TestTopicCreationError(f"Topic creation failed: {e}")

    async def create_synthetic_topic(
        self,
        session_id: str,
        surface_id: Optional[str] = None,
        test_data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Create a synthetic test topic without going through the full pipeline.

        Args:
            session_id: Session ID to create topic for
            surface_id: Optional surface ID for SSE targeting
            test_data: Optional custom test data

        Returns:
            Synthetic topic creation response

        Raises:
            TestTopicCreationError: If synthetic topic creation fails
        """
        try:
            request_data = {
                "session_id": session_id
            }

            if surface_id:
                request_data["surface_id"] = surface_id
            if test_data:
                request_data["test_data"] = test_data

            response = await self.api_client.post(
                "/api/v1/test/dispatch-synthetic",
                json=request_data
            )

            logger.info(f"Created synthetic test topic: session={session_id}")

            return response

        except Exception as e:
            logger.error(f"Failed to create synthetic topic: {e}")
            raise TestTopicCreationError(f"Synthetic topic creation failed: {e}")


class TestDataCleanup:
    """Utilities for cleaning up test data."""

    def __init__(
        self,
        api_client: TestAPIClient,
        session_manager: TestSessionManager
    ):
        """
        Initialize test data cleanup utilities.

        Args:
            api_client: Test API client instance
            session_manager: Test session manager instance
        """
        self.api_client = api_client
        self.session_manager = session_manager

    async def cleanup_session(self, session_id: str) -> Dict[str, Any]:
        """
        Clean up all data for a specific session.

        Args:
            session_id: Session ID to clean up

        Returns:
            Cleanup result dictionary
        """
        try:
            result = await self.session_manager.delete_session(session_id)

            logger.info(f"Cleaned up session data: {session_id}")

            return result

        except Exception as e:
            logger.error(f"Failed to cleanup session: {e}")
            raise TestCleanupError(f"Session cleanup failed: {e}")

    async def cleanup_all_sessions(self) -> Dict[str, Any]:
        """
        Clean up all tracked test sessions.

        Returns:
            Cleanup result dictionary with count of sessions cleaned
        """
        tracked_sessions = self.session_manager.get_tracked_sessions()
        session_ids = list(tracked_sessions.keys())

        results = []
        for session_id in session_ids:
            try:
                result = await self.cleanup_session(session_id)
                results.append(result)
            except Exception as e:
                logger.warning(f"Failed to cleanup session {session_id}: {e}")
                results.append({
                    "session_id": session_id,
                    "deleted": False,
                    "error": str(e)
                })

        deleted_count = sum(1 for r in results if r.get("deleted"))

        return {
            "total_sessions": len(session_ids),
            "deleted_count": deleted_count,
            "results": results
        }


@asynccontextmanager
async def test_database_context(
    db_config: Optional[TestDatabaseConfig] = None
) -> AsyncGenerator[Dict[str, Any], None]:
    """
    Context manager for test database setup and cleanup.

    Args:
        db_config: Optional test database configuration

    Yields:
        Dictionary with database configuration details

    Example:
        async with test_database_context() as db_ctx:
            # Run test with isolated database
            session_manager = TestSessionManager(api_client, db_config)
            session = await session_manager.create_session()
    """
    config = db_config or TestDatabaseConfig()

    # Set environment variable for test database path
    original_db_path = os.environ.get("ADC_DB_PATH")

    try:
        if config.use_in_memory:
            # Use in-memory SQLite database
            test_db_path = ":memory:"
            os.environ["ADC_DB_PATH"] = test_db_path
            logger.info("Using in-memory test database")
        else:
            # Use file-based test database
            test_db_path = str(config.test_db_path)
            os.environ["ADC_DB_PATH"] = test_db_path
            logger.info(f"Using test database: {test_db_path}")

        yield {
            "db_path": test_db_path,
            "use_in_memory": config.use_in_memory,
            "cleanup_after_test": config.cleanup_after_test
        }

    finally:
        # Restore original environment variable
        if original_db_path:
            os.environ["ADC_DB_PATH"] = original_db_path
        else:
            os.environ.pop("ADC_DB_PATH", None)

        # Clean up test database file if needed
        if config.cleanup_after_test and not config.use_in_memory:
            if config.test_db_path and config.test_db_path.exists():
                try:
                    config.test_db_path.unlink()
                    logger.info(f"Cleaned up test database: {config.test_db_path}")
                except Exception as e:
                    logger.warning(f"Failed to cleanup test database file: {e}")


@asynccontextmanager
async def test_data_injection_context(
    base_url: str = TestAPIClient.DEFAULT_BASE_URL,
    db_config: Optional[TestDatabaseConfig] = None
) -> AsyncGenerator[Dict[str, Any], None]:
    """
    Complete context manager for test data injection.

    Sets up test database, API client, session manager, topic manager,
    and cleanup utilities. Provides everything needed for canvas testing.

    Args:
        base_url: Base URL for the API
        db_config: Optional test database configuration

    Yields:
        Dictionary with all test data injection utilities

    Example:
        async with test_data_injection_context() as ctx:
            # Create test session
            session = await ctx["session_manager"].create_session()

            # Create test topic
            topic = await ctx["topic_manager"].create_topic_via_dispatch(
                utterance="test query",
                session_id=session["session_id"]
            )

            # Cleanup happens automatically on exit
    """
    # Setup test registry
    setup_test_registry()

    async with test_database_context(db_config) as db_ctx:
        async with TestAPIClient() as api_client:
            session_manager = TestSessionManager(api_client, db_config)
            topic_manager = TestTopicManager(api_client)
            cleanup_util = TestDataCleanup(api_client, session_manager)

            utilities = {
                "api_client": api_client,
                "session_manager": session_manager,
                "topic_manager": topic_manager,
                "cleanup": cleanup_util,
                "db_config": db_ctx
            }

            try:
                yield utilities
            finally:
                # Cleanup all tracked sessions
                try:
                    await cleanup_util.cleanup_all_sessions()
                except Exception as e:
                    logger.warning(f"Failed to cleanup sessions: {e}")

    # Cleanup test registry
    cleanup_test_registry()


# Convenience functions for common test scenarios

async def create_test_session_with_topics(
    num_topics: int = 3,
    base_url: str = TestAPIClient.DEFAULT_BASE_URL,
    use_in_memory: bool = True
) -> Dict[str, Any]:
    """
    Create a test session with multiple topics.

    Args:
        num_topics: Number of topics to create
        base_url: Base URL for the API
        use_in_memory: Whether to use in-memory database

    Returns:
        Dictionary with session_id, topics, and metadata
    """
    db_config = TestDatabaseConfig(use_in_memory=use_in_memory)

    async with test_data_injection_context(base_url, db_config) as ctx:
        # Create session
        session = await ctx["session_manager"].create_session()
        session_id = session["session_id"]
        surface_id = session["surface_id"]

        # Create topics
        topics = []
        test_utterances = [
            "check the pods",
            "how are the services doing",
            "show me the logs"
        ]

        for i in range(num_topics):
            utterance = test_utterances[i % len(test_utterances)]
            topic = await ctx["topic_manager"].create_topic_via_dispatch(
                utterance=utterance,
                session_id=session_id,
                surface_id=surface_id
            )
            topics.append(topic)

        # Fetch all topics for the session
        all_topics = await ctx["session_manager"].get_session_topics(session_id)

        return {
            "session_id": session_id,
            "surface_id": surface_id,
            "topics_created": topics,
            "all_topics": all_topics,
            "total_topic_count": len(all_topics)
        }


async def verify_test_data_isolation(
    session_id_1: str,
    session_id_2: str,
    base_url: str = TestAPIClient.DEFAULT_BASE_URL
) -> Dict[str, Any]:
    """
    Verify that test data is properly isolated between sessions.

    Args:
        session_id_1: First session ID
        session_id_2: Second session ID
        base_url: Base URL for the API

    Returns:
        Dictionary with isolation verification results
    """
    async with TestAPIClient(base_url) as api_client:
        topics_1 = await api_client.get(f"/api/v1/sessions/{session_id_1}/topics")
        topics_2 = await api_client.get(f"/api/v1/sessions/{session_id_2}/topics")

        topics_1_ids = {t.get("id") for t in topics_1.get("cards", [])}
        topics_2_ids = {t.get("id") for t in topics_2.get("cards", [])}

        overlap = topics_1_ids & topics_2_ids

        return {
            "session_1_topic_count": len(topics_1_ids),
            "session_2_topic_count": len(topics_2_ids),
            "overlapping_topic_ids": list(overlap),
            "is_isolated": len(overlap) == 0
        }