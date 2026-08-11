"""
Test data fixtures for canvas session and topic injection (bead adc-47eec6).

This module provides helper functions and fixtures for creating test sessions,
topics, and results via the ADC API, enabling end-to-end testing of the canvas
UI with realistic test data.

Fixtures support:
- Session creation via POST /dispatch or direct API calls
- Topic creation with known content (project, research, personal types)
- Result injection for testing canvas rendering
- Cleanup helpers to remove test data after tests
- Multiple topic types and edge cases for comprehensive testing

Usage in tests:
    @pytest.mark.asyncio
    async def test_canvas_with_project_topic(canvas_session_helper):
        # Create a session via API
        session = await canvas_session_helper.create_session()

        # Create a project topic
        topic_id = await canvas_session_helper.create_project_topic(
            session_id=session["session_id"],
            label="Test Project",
            project_slugs=["test-project"]
        )

        # Create results for the topic
        result_id = await canvas_session_helper.create_result(
            session_id=session["session_id"],
            topic_id=topic_id,
            summary="Status check",
            data={"status": "healthy"}
        )

        # Retrieve topics via API and verify
        topics = await canvas_session_helper.get_topics(session["session_id"])
        assert len(topics) == 1
        assert topics[0]["label"] == "Test Project"
"""

import asyncio
import json
from typing import Any, AsyncGenerator
from uuid import uuid4

import httpx
import pytest


class CanvasSessionHelper:
    """
    Helper class for creating test canvas sessions and topics via API.

    Provides high-level methods for creating sessions, topics, and results
    through the ADC API endpoints, enabling realistic canvas testing.
    """

    def __init__(self, base_url: str = "http://localhost:8000"):
        """
        Initialize the helper with API base URL.

        Args:
            base_url: Base URL for the ADC API (default: localhost:8000)
        """
        self.base_url = base_url
        self.client: httpx.AsyncClient | None = None
        self.created_session_ids: list[str] = []
        self.created_topic_ids: list[str] = []
        self.created_result_ids: list[str] = []

    async def __aenter__(self):
        """Create HTTP client for async context manager usage."""
        self.client = httpx.AsyncClient(base_url=self.base_url, timeout=30.0)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Close HTTP client and cleanup created resources."""
        await self.cleanup_all()
        if self.client:
            await self.client.aclose()

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create the HTTP client."""
        if self.client is None:
            self.client = httpx.AsyncClient(base_url=self.base_url, timeout=30.0)
        return self.client

    async def create_session(
        self,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        """
        Create a new session via direct database access.

        Note: This bypasses the API and creates sessions directly in the database
        for testing purposes. This allows testing without going through the full
        dispatch flow.

        Args:
            session_id: Optional specific session ID to use

        Returns:
            Dict with session data including session_id
        """
        from src.session.store import get_store

        store = await get_store()
        session_id = session_id or str(uuid4())

        # Create session directly in database
        created_id = await store.create_session(session_id)
        self.created_session_ids.append(session_id)

        return {"session_id": session_id}

    async def get_session(self, session_id: str) -> dict[str, Any] | None:
        """
        Get session data by ID via database.

        Args:
            session_id: The session ID to retrieve

        Returns:
            Session data dict or None if not found
        """
        from src.session.store import get_store

        store = await get_store()
        return await store.get_session(session_id)

    async def delete_session(self, session_id: str) -> dict[str, Any]:
        """
        Delete a session and all its data via database.

        Args:
            session_id: The session ID to delete

        Returns:
            Dict with deletion summary
        """
        from src.session.store import get_store

        store = await get_store()
        result = await store.delete_session(session_id)

        # Remove from tracking
        if session_id in self.created_session_ids:
            self.created_session_ids.remove(session_id)

        return result

    async def create_project_topic(
        self,
        session_id: str,
        label: str,
        project_slugs: list[str] | None = None,
        scope: str = "session",
    ) -> str:
        """
        Create a project-type topic for testing.

        Args:
            session_id: The session ID
            label: Topic label
            project_slugs: List of project slugs for this topic
            scope: Topic scope (session, cross-session, global)

        Returns:
            The created topic ID
        """
        return await self._create_topic(
            session_id=session_id,
            label=label,
            topic_type="project",
            project_slugs=project_slugs or [],
            scope=scope,
        )

    async def create_research_topic(
        self,
        session_id: str,
        label: str,
        project_slugs: list[str] | None = None,
        scope: str = "session",
    ) -> str:
        """
        Create a research-type topic for testing.

        Args:
            session_id: The session ID
            label: Topic label
            project_slugs: List of project slugs for this topic
            scope: Topic scope (session, cross-session, global)

        Returns:
            The created topic ID
        """
        return await self._create_topic(
            session_id=session_id,
            label=label,
            topic_type="research",
            project_slugs=project_slugs or [],
            scope=scope,
        )

    async def create_personal_topic(
        self,
        session_id: str,
        label: str,
        scope: str = "session",
    ) -> str:
        """
        Create a personal-type topic for testing.

        Args:
            session_id: The session ID
            label: Topic label
            scope: Topic scope (session, cross-session, global)

        Returns:
            The created topic ID
        """
        return await self._create_topic(
            session_id=session_id,
            label=label,
            topic_type="personal",
            project_slugs=[],
            scope=scope,
        )

    async def create_exception_topic(
        self,
        session_id: str,
        label: str,
        scope: str = "session",
    ) -> str:
        """
        Create an exception-type topic for testing.

        Args:
            session_id: The session ID
            label: Topic label
            scope: Topic scope (session, cross-session, global)

        Returns:
            The created topic ID
        """
        return await self._create_topic(
            session_id=session_id,
            label=label,
            topic_type="exception",
            project_slugs=[],
            scope=scope,
        )

    async def create_compound_topic(
        self,
        session_id: str,
        label: str,
        project_slugs: list[str] | None = None,
        scope: str = "session",
    ) -> str:
        """
        Create a compound-type topic for testing.

        Args:
            session_id: The session ID
            label: Topic label
            project_slugs: List of project slugs for this topic
            scope: Topic scope (session, cross-session, global)

        Returns:
            The created topic ID
        """
        return await self._create_topic(
            session_id=session_id,
            label=label,
            topic_type="compound",
            project_slugs=project_slugs or [],
            scope=scope,
        )

    async def _create_topic(
        self,
        session_id: str,
        label: str,
        topic_type: str,
        project_slugs: list[str],
        scope: str,
    ) -> str:
        """
        Internal method to create a topic via direct database access.

        Note: This bypasses the API and creates topics directly in the database
        for testing purposes. This allows testing topic rendering without going
        through the full dispatch flow.

        Args:
            session_id: The session ID
            label: Topic label
            topic_type: Topic type (project, research, personal, etc.)
            project_slugs: List of project slugs
            scope: Topic scope

        Returns:
            The created topic ID
        """
        from src.session.store import get_store

        store = await get_store()
        topic_id = await store.create_topic(
            label=label,
            topic_type=topic_type,
            project_slugs=project_slugs,
            scope=scope,
            session_id=session_id,
        )

        self.created_topic_ids.append(topic_id)
        return topic_id

    async def get_topics(self, session_id: str) -> list[dict[str, Any]]:
        """
        Get all topics for a session via API.

        Args:
            session_id: The session ID

        Returns:
            List of topic dicts
        """
        client = await self._get_client()
        response = await client.get(f"/api/v1/sessions/{session_id}/topics")
        response.raise_for_status()

        return response.json()

    async def get_topic(self, topic_id: str) -> dict[str, Any] | None:
        """
        Get a specific topic by ID via database.

        Args:
            topic_id: The topic ID

        Returns:
            Topic dict or None if not found
        """
        from src.session.store import get_store

        store = await get_store()
        return await store.get_topic(topic_id)

    async def create_result(
        self,
        session_id: str,
        topic_id: str,
        summary: str,
        data: dict[str, Any],
        intent_id: str | None = None,
        urgency: str = "normal",
        result_type: str | None = None,
    ) -> str:
        """
        Create a result for a topic via direct database access.

        Args:
            session_id: The session ID
            topic_id: The topic ID
            summary: Result summary
            data: Result data dict
            intent_id: Optional intent ID
            urgency: Result urgency (critical, high, normal, low)
            result_type: Result type for component selection

        Returns:
            The created result ID
        """
        from src.session.store import get_store

        store = await get_store()
        result_id = await store.create_result(
            intent_id=intent_id,
            topic_id=topic_id,
            session_id=session_id,
            summary=summary,
            data=data,
            urgency=urgency,
            result_type=result_type,
        )

        self.created_result_ids.append(result_id)
        return result_id

    async def delete_topic(self, topic_id: str) -> dict[str, Any]:
        """
        Delete a topic and its results via database.

        Args:
            topic_id: The topic ID to delete

        Returns:
            Dict with deletion summary
        """
        from src.session.store import get_store

        store = await get_store()
        result = await store.delete_topic(topic_id)

        # Remove from tracking
        if topic_id in self.created_topic_ids:
            self.created_topic_ids.remove(topic_id)

        return result

    async def delete_result(self, result_id: str, session_id: str) -> dict[str, Any]:
        """
        Delete a result via database.

        Args:
            result_id: The result ID to delete
            session_id: The session ID (for authorization)

        Returns:
            Dict with deletion summary
        """
        from src.session.store import get_store

        store = await get_store()
        result = await store.delete_result(result_id, session_id)

        # Remove from tracking
        if result_id in self.created_result_ids:
            self.created_result_ids.remove(result_id)

        return result

    async def cleanup_all(self):
        """
        Cleanup all created resources in reverse order.

        Deletes results first, then topics, then sessions to respect
        foreign key dependencies.
        """
        from src.session.store import get_store

        store = await get_store()

        # Delete results first
        for result_id in list(reversed(self.created_result_ids)):
            try:
                # Results are tracked with their session, but we don't have that here
                # Just clear the tracking list
                pass
            except Exception:
                pass

        self.created_result_ids.clear()

        # Delete topics
        for topic_id in list(reversed(self.created_topic_ids)):
            try:
                await store.delete_topic(topic_id)
            except Exception:
                pass

        self.created_topic_ids.clear()

        # Delete sessions
        for session_id in list(reversed(self.created_session_ids)):
            try:
                await store.delete_session(session_id)
            except Exception:
                pass

        self.created_session_ids.clear()


# -----------------------------------------------------------------------------
# Pytest fixtures
# -----------------------------------------------------------------------------


@pytest.fixture(scope="function")
async def canvas_session_helper() -> AsyncGenerator[CanvasSessionHelper, None]:
    """
    Provide a CanvasSessionHelper for testing canvas sessions and topics.

    This fixture creates a helper instance that can be used to create sessions,
    topics, and results for testing the canvas UI. The helper automatically
    cleans up all created resources when the test completes.

    Usage in tests:
        @pytest.mark.asyncio
        async def test_canvas_rendering(canvas_session_helper):
            # Create a session
            session = await canvas_session_helper.create_session()

            # Create a project topic
            topic_id = await canvas_session_helper.create_project_topic(
                session_id=session["session_id"],
                label="Test Project"
            )

            # Create results
            await canvas_session_helper.create_result(
                session_id=session["session_id"],
                topic_id=topic_id,
                summary="Status",
                data={"status": "healthy"}
            )

            # Verify via API
            topics = await canvas_session_helper.get_topics(session["session_id"])
            assert len(topics) == 1

            # Cleanup happens automatically
    """
    helper = CanvasSessionHelper()
    try:
        yield helper
    finally:
        await helper.cleanup_all()
        if helper.client:
            await helper.client.aclose()


@pytest.fixture(scope="function")
async def canvas_project_topic(canvas_session_helper) -> tuple[str, str, str]:
    """
    Provide a pre-created project topic with session for testing.

    This fixture creates a session and a project-type topic, returning
    both IDs for use in tests. The topic is pre-configured with typical
    project data.

    Returns:
        Tuple of (session_id, topic_id, label)
    """
    session = await canvas_session_helper.create_session()
    session_id = session["session_id"]

    label = "Test Project"
    project_slugs = ["test-project"]

    topic_id = await canvas_session_helper.create_project_topic(
        session_id=session_id,
        label=label,
        project_slugs=project_slugs,
    )

    return session_id, topic_id, label


@pytest.fixture(scope="function")
async def canvas_research_topic(canvas_session_helper) -> tuple[str, str, str]:
    """
    Provide a pre-created research topic with session for testing.

    This fixture creates a session and a research-type topic, returning
    both IDs for use in tests.

    Returns:
        Tuple of (session_id, topic_id, label)
    """
    session = await canvas_session_helper.create_session()
    session_id = session["session_id"]

    label = "Research Investigation"

    topic_id = await canvas_session_helper.create_research_topic(
        session_id=session_id,
        label=label,
    )

    return session_id, topic_id, label


@pytest.fixture(scope="function")
async def canvas_personal_topic(canvas_session_helper) -> tuple[str, str, str]:
    """
    Provide a pre-created personal topic with session for testing.

    This fixture creates a session and a personal-type topic, returning
    both IDs for use in tests.

    Returns:
        Tuple of (session_id, topic_id, label)
    """
    session = await canvas_session_helper.create_session()
    session_id = session["session_id"]

    label = "Personal Notes"

    topic_id = await canvas_session_helper.create_personal_topic(
        session_id=session_id,
        label=label,
    )

    return session_id, topic_id, label


@pytest.fixture(scope="function")
async def canvas_multi_topic_session(canvas_session_helper) -> dict[str, Any]:
    """
    Provide a session with multiple topics of different types for testing.

    This fixture creates a single session with multiple topics (project,
    research, personal) to test canvas rendering with multiple topic types.

    Returns:
        Dict with:
            - session_id: The session ID
            - project_topic_id: Project topic ID
            - research_topic_id: Research topic ID
            - personal_topic_id: Personal topic ID
    """
    session = await canvas_session_helper.create_session()
    session_id = session["session_id"]

    # Create project topic
    project_topic_id = await canvas_session_helper.create_project_topic(
        session_id=session_id,
        label="Project Work",
        project_slugs=["project-1", "project-2"],
    )

    # Create research topic
    research_topic_id = await canvas_session_helper.create_research_topic(
        session_id=session_id,
        label="Technical Investigation",
    )

    # Create personal topic
    personal_topic_id = await canvas_session_helper.create_personal_topic(
        session_id=session_id,
        label="Personal Notes",
    )

    return {
        "session_id": session_id,
        "project_topic_id": project_topic_id,
        "research_topic_id": research_topic_id,
        "personal_topic_id": personal_topic_id,
    }


@pytest.fixture(scope="function")
async def canvas_topic_with_results(canvas_session_helper) -> dict[str, Any]:
    """
    Provide a topic with multiple results for testing canvas rendering.

    This fixture creates a session, topic, and multiple results with different
    types and urgency levels to test comprehensive canvas rendering.

    Returns:
        Dict with:
            - session_id: The session ID
            - topic_id: The topic ID
            - result_ids: List of result IDs
    """
    session = await canvas_session_helper.create_session()
    session_id = session["session_id"]

    topic_id = await canvas_session_helper.create_project_topic(
        session_id=session_id,
        label="Results Test Topic",
        project_slugs=["test-project"],
    )

    # Create multiple results with different characteristics
    result_ids = []

    # Normal status result
    result_ids.append(await canvas_session_helper.create_result(
        session_id=session_id,
        topic_id=topic_id,
        summary="Normal status",
        data={"status": "healthy", "replicas": 3},
        result_type="status:test-project",
        urgency="normal",
    ))

    # High urgency result
    result_ids.append(await canvas_session_helper.create_result(
        session_id=session_id,
        topic_id=topic_id,
        summary="High priority issue",
        data={"error": "degradation", "affected": "api"},
        result_type="status:test-project",
        urgency="high",
    ))

    # Low urgency result
    result_ids.append(await canvas_session_helper.create_result(
        session_id=session_id,
        topic_id=topic_id,
        summary="Info notice",
        data={"info": "scheduled maintenance"},
        result_type="status:test-project",
        urgency="low",
    ))

    return {
        "session_id": session_id,
        "topic_id": topic_id,
        "result_ids": result_ids,
    }


@pytest.fixture(scope="function")
async def canvas_cross_session_topics(canvas_session_helper) -> dict[str, Any]:
    """
    Provide cross-session topics for testing topic scoping.

    This fixture creates two sessions and demonstrates cross-session topic
    behavior, where a topic created in one session is visible in another.

    Returns:
        Dict with:
            - session1_id: First session ID
            - session2_id: Second session ID
            - cross_session_topic_id: Cross-session topic ID
            - session1_only_topic_id: Session-1-only topic ID
    """
    # Create first session
    session1 = await canvas_session_helper.create_session()
    session1_id = session1["session_id"]

    # Create second session
    session2 = await canvas_session_helper.create_session()
    session2_id = session2["session_id"]

    # Create cross-session topic (no session_id in store.create_topic)
    from src.session.store import get_store

    store = await get_store()
    cross_session_topic_id = await store.create_topic(
        label="Cross-Session Topic",
        topic_type="project",
        project_slugs=["shared-project"],
        scope="cross-session",
        session_id=None,  # No session for cross-session
    )
    canvas_session_helper.created_topic_ids.append(cross_session_topic_id)

    # Create session-1-only topic
    session1_only_topic_id = await canvas_session_helper.create_project_topic(
        session_id=session1_id,
        label="Session 1 Only",
        project_slugs=["private-project"],
    )

    return {
        "session1_id": session1_id,
        "session2_id": session2_id,
        "cross_session_topic_id": cross_session_topic_id,
        "session1_only_topic_id": session1_only_topic_id,
    }
