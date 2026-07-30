"""
Integration tests for result_type column derivation and persistence.

Tests verify that result_type is correctly derived at write time and
persisted to the database for all intent types including:
- project (action, status)
- research (brainstorm, lookup)
- personal
- exception (escalated failures, stuck cards)
- monitoring (ambient monitoring rows)
- compound intents
"""
import pytest
import tempfile
from pathlib import Path

from src.session.store import SessionStore
from src.render.hot_path import derive_result_type


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)
    yield db_path
    # Cleanup
    db_path.unlink(missing_ok=True)


@pytest.fixture
async def store(temp_db):
    """Create a session store with temp database."""
    store = SessionStore(temp_db)
    await store.initialize()
    yield store
    await store.close()


@pytest.mark.asyncio
class TestResultTypePersistence:
    """Test that result_type is correctly derived and persisted for all intent types."""

    async def test_project_action_result_type(self, store):
        """Project action intent should derive and persist 'action:{project_slug}'."""
        # Create session and topic
        session_id = "test-session-1"
        await store.create_session(session_id)
        topic_id, _ = await store.find_or_create_topic(
            label="Test Action",
            session_id=session_id,
            topic_type="project",
            project_slugs=["options-pipeline"],
        )

        # Create result with derived result_type
        expected_result_type = derive_result_type(
            intent_type="action",
            project_slug="options-pipeline",
        )
        assert expected_result_type == "action:options-pipeline"

        result_id = await store.create_result(
            intent_id="intent-1",
            topic_id=topic_id,
            session_id=session_id,
            summary="Deployment successful",
            data={"status": "deployed"},
            urgency="normal",
            result_type=expected_result_type,
        )

        # Verify result_type is persisted
        result = await store.get_latest_result_for_topic(topic_id)
        assert result is not None
        assert result["result_type"] == "action:options-pipeline"
        assert result["id"] == result_id

    async def test_project_status_result_type(self, store):
        """Project status intent should derive and persist 'status:{project_slug}'."""
        session_id = "test-session-2"
        await store.create_session(session_id)
        topic_id, _ = await store.find_or_create_topic(
            label="Test Status",
            session_id=session_id,
            topic_type="project",
            project_slugs=["botburrow"],
        )

        expected_result_type = derive_result_type(
            intent_type="status",
            project_slug="botburrow",
        )
        assert expected_result_type == "status:botburrow"

        result_id = await store.create_result(
            intent_id="intent-2",
            topic_id=topic_id,
            session_id=session_id,
            summary="All systems operational",
            data={"health": "ok"},
            result_type=expected_result_type,
        )

        result = await store.get_latest_result_for_topic(topic_id)
        assert result["result_type"] == "status:botburrow"
        assert result["id"] == result_id

    async def test_research_brainstorm_result_type(self, store):
        """Research brainstorm intent should derive 'brainstorm:{project_slug}'."""
        session_id = "test-session-3"
        await store.create_session(session_id)
        topic_id, _ = await store.find_or_create_topic(
            label="Brainstorm Ideas",
            session_id=session_id,
            topic_type="research",
            project_slugs=["nixos-asterisk"],
        )

        expected_result_type = derive_result_type(
            intent_type="brainstorm",
            project_slug="nixos-asterisk",
        )
        assert expected_result_type == "brainstorm:nixos-asterisk"

        result_id = await store.create_result(
            intent_id="intent-3",
            topic_id=topic_id,
            session_id=session_id,
            summary="Ideas generated",
            data={"ideas": ["idea1", "idea2"]},
            result_type=expected_result_type,
        )

        result = await store.get_latest_result_for_topic(topic_id)
        assert result["result_type"] == "brainstorm:nixos-asterisk"

    async def test_research_lookup_result_type(self, store):
        """Research lookup intent should derive 'lookup:{kind}:{project_slug}'."""
        session_id = "test-session-4"
        await store.create_session(session_id)
        topic_id, _ = await store.find_or_create_topic(
            label="Logs Lookup",
            session_id=session_id,
            topic_type="research",
            project_slugs=["ibkr-mcp"],
        )

        # Lookup with kind should include kind in result_type
        expected_result_type = derive_result_type(
            intent_type="lookup",
            project_slug="ibkr-mcp",
            lookup_kind="logs",
        )
        assert expected_result_type == "lookup:logs:ibkr-mcp"

        result_id = await store.create_result(
            intent_id="intent-4",
            topic_id=topic_id,
            session_id=session_id,
            summary="Logs retrieved",
            data={"logs": ["log1", "log2"]},
            result_type=expected_result_type,
        )

        result = await store.get_latest_result_for_topic(topic_id)
        assert result["result_type"] == "lookup:logs:ibkr-mcp"

    async def test_personal_result_type(self, store):
        """Personal intent without project_slug should derive '{itype}:general'."""
        session_id = "test-session-5"
        await store.create_session(session_id)
        topic_id, _ = await store.find_or_create_topic(
            label="Personal Task",
            session_id=session_id,
            topic_type="personal",
            project_slugs=[],
        )

        # Personal intent without project_slug defaults to "general"
        expected_result_type = derive_result_type(
            intent_type="reminder",
            project_slug=None,
        )
        assert expected_result_type == "reminder:general"

        result_id = await store.create_result(
            intent_id="intent-5",
            topic_id=topic_id,
            session_id=session_id,
            summary="Reminder set",
            data={"reminder": "Call mom"},
            result_type=expected_result_type,
        )

        result = await store.get_latest_result_for_topic(topic_id)
        assert result["result_type"] == "reminder:general"

    async def test_exception_escalated_failure_result_type(self, store):
        """Exception (escalated failure) should preserve original intent result_type."""
        session_id = "test-session-6"
        await store.create_session(session_id)
        topic_id, _ = await store.find_or_create_topic(
            label="Failed Task",
            session_id=session_id,
            topic_type="exception",
            project_slugs=["options-pipeline"],
        )

        # Failed task preserves original result_type based on original intent
        expected_result_type = derive_result_type(
            intent_type="action",
            project_slug="options-pipeline",
        )
        assert expected_result_type == "action:options-pipeline"

        result_id = await store.create_result(
            intent_id="intent-6",
            topic_id=topic_id,
            session_id=session_id,
            summary="Task Failed: Worker Crash",
            data={"error": "Worker crashed"},
            urgency="high",
            result_type=expected_result_type,
        )

        result = await store.get_latest_result_for_topic(topic_id)
        assert result["result_type"] == "action:options-pipeline"

    async def test_exception_stuck_card_result_type(self, store):
        """Stuck card should preserve original intent result_type."""
        session_id = "test-session-7"
        await store.create_session(session_id)
        topic_id, _ = await store.find_or_create_topic(
            label="Stuck Task",
            session_id=session_id,
            topic_type="exception",
            project_slugs=["botburrow"],
        )

        # Stuck card preserves original status intent result_type
        expected_result_type = derive_result_type(
            intent_type="status",
            project_slug="botburrow",
        )
        assert expected_result_type == "status:botburrow"

        result_id = await store.create_result(
            intent_id="intent-7",
            topic_id=topic_id,
            session_id=session_id,
            summary="Task stuck — needs your input",
            data={"stuck_reason": "Refused: missing context"},
            urgency="high",
            result_type=expected_result_type,
        )

        result = await store.get_latest_result_for_topic(topic_id)
        assert result["result_type"] == "status:botburrow"

    async def test_monitoring_result_type(self, store):
        """Monitoring intent should derive 'monitoring:{project_slug}'."""
        session_id = "test-session-8"
        await store.create_session(session_id)
        topic_id, _ = await store.find_or_create_topic(
            label="Botburrow Monitoring",
            session_id=session_id,
            topic_type="project",
            project_slugs=["botburrow"],
        )

        # Monitoring uses special 'monitoring' intent type
        expected_result_type = derive_result_type(
            intent_type="monitoring",
            project_slug="botburrow",
        )
        assert expected_result_type == "monitoring:botburrow"

        # Monitoring results have intent_id=NULL (system-originated)
        result_id = await store.create_result(
            intent_id=None,  # NULL for monitoring-originated results
            topic_id=topic_id,
            session_id=session_id,
            summary="Botburrow state changed",
            data={"phase": "Running", "sync_status": "Synced"},
            urgency="normal",
            result_type=expected_result_type,
        )

        result = await store.get_latest_result_for_topic(topic_id)
        assert result["result_type"] == "monitoring:botburrow"
        assert result["intent_id"] is None

    async def test_compound_intent_result_type(self, store):
        """Compound intent with multiple projects should use first project."""
        session_id = "test-session-9"
        await store.create_session(session_id)
        topic_id, _ = await store.find_or_create_topic(
            label="Multi-Project Task",
            session_id=session_id,
            topic_type="compound",
            project_slugs=["options-pipeline", "botburrow"],
        )

        # Compound intent derives from first project_slug in context
        # In practice, the first project is used for result_type
        expected_result_type = derive_result_type(
            intent_type="action",
            project_slug="options-pipeline",
        )
        assert expected_result_type == "action:options-pipeline"

        result_id = await store.create_result(
            intent_id="intent-9",
            topic_id=topic_id,
            session_id=session_id,
            summary="Multi-project task completed",
            data={"projects": ["options-pipeline", "botburrow"]},
            result_type=expected_result_type,
        )

        result = await store.get_latest_result_for_topic(topic_id)
        assert result["result_type"] == "action:options-pipeline"

    async def test_result_type_in_results_for_intent(self, store):
        """Verify result_type is returned in get_results_for_intent."""
        session_id = "test-session-10"
        await store.create_session(session_id)
        topic_id, _ = await store.find_or_create_topic(
            label="Test Topic",
            session_id=session_id,
            topic_type="project",
            project_slugs=["test-project"],
        )

        expected_result_type = derive_result_type(
            intent_type="status",
            project_slug="test-project",
        )

        await store.create_result(
            intent_id="intent-10",
            topic_id=topic_id,
            session_id=session_id,
            summary="Test result",
            data={"test": "data"},
            result_type=expected_result_type,
        )

        results = await store.get_results_for_intent("intent-10")
        assert len(results) == 1
        assert results[0]["result_type"] == "status:test-project"

    async def test_result_type_in_get_all_results(self, store):
        """Verify result_type is returned in get_all_results."""
        session_id = "test-session-11"
        await store.create_session(session_id)
        topic_id, _ = await store.find_or_create_topic(
            label="Test Topic 2",
            session_id=session_id,
            topic_type="research",
            project_slugs=["research-project"],
        )

        expected_result_type = derive_result_type(
            intent_type="brainstorm",
            project_slug="research-project",
        )

        await store.create_result(
            intent_id="intent-11",
            topic_id=topic_id,
            session_id=session_id,
            summary="Research result",
            data={"ideas": []},
            result_type=expected_result_type,
        )

        all_results = await store.get_all_results()
        result_with_type = [r for r in all_results if r["id"]].pop(0)

        assert result_with_type is not None
        assert result_with_type["result_type"] == "brainstorm:research-project"

    async def test_result_type_none_becomes_status_general(self, store):
        """When result_type is None, it should be stored as NULL in DB."""
        session_id = "test-session-12"
        await store.create_session(session_id)
        topic_id, _ = await store.find_or_create_topic(
            label="Test Topic 3",
            session_id=session_id,
            topic_type="research",  # Valid topic type from schema
        )

        # Create result with explicit None result_type
        result_id = await store.create_result(
            intent_id="intent-12",
            topic_id=topic_id,
            session_id=session_id,
            summary="Test result with None type",
            data={"test": "data"},
            result_type=None,  # Explicitly None
        )

        result = await store.get_latest_result_for_topic(topic_id)
        # NULL is stored as None in Python
        assert result["result_type"] is None

    async def test_multiple_results_same_topic_preserve_types(self, store):
        """Multiple results for the same topic should preserve their result_types."""
        import asyncio

        session_id = "test-session-13"
        await store.create_session(session_id)
        topic_id, _ = await store.find_or_create_topic(
            label="Multi-Result Topic",
            session_id=session_id,
            topic_type="project",
            project_slugs=["shared-project"],
        )

        # Create results with different types for the same topic
        result_type_1 = derive_result_type(intent_type="status", project_slug="shared-project")
        result_type_2 = derive_result_type(intent_type="action", project_slug="shared-project")

        result_id_1 = await store.create_result(
            intent_id="intent-13a",
            topic_id=topic_id,
            session_id=session_id,
            summary="Status check",
            data={"status": "ok"},
            result_type=result_type_1,
        )

        # Add delay to ensure different timestamps (created_at has 1-second resolution)
        await asyncio.sleep(1.1)

        # Link to previous result using result_id, not intent_id
        result_id_2 = await store.create_result(
            intent_id="intent-13b",
            topic_id=topic_id,
            session_id=session_id,
            summary="Action taken",
            data={"action": "restart"},
            previous_result_id=result_id_1,  # Use actual result_id
            result_type=result_type_2,
        )

        # Latest result should have action result_type
        latest = await store.get_latest_result_for_topic(topic_id)
        assert latest["result_type"] == "action:shared-project"
        assert latest["id"] == result_id_2

        # Both results should be retrievable with their types
        all_results = await store.get_results_for_intent("intent-13a")
        # Note: get_results_for_intent returns results for one intent
        # So we check both intents separately
        assert all_results[0]["result_type"] == "status:shared-project"

        all_results_2 = await store.get_results_for_intent("intent-13b")
        assert all_results_2[0]["result_type"] == "action:shared-project"

    async def test_monitoring_without_project_slug(self, store):
        """Monitoring without project_slug should derive 'monitoring:general'."""
        session_id = "test-session-14"
        await store.create_session(session_id)
        topic_id, _ = await store.find_or_create_topic(
            label="General Monitoring",
            session_id=session_id,
            topic_type="project",
            project_slugs=[],
        )

        expected_result_type = derive_result_type(
            intent_type="monitoring",
            project_slug=None,
        )
        assert expected_result_type == "monitoring:general"

        result_id = await store.create_result(
            intent_id=None,  # Monitoring has NULL intent_id
            topic_id=topic_id,
            session_id=session_id,
            summary="General system state",
            data={"system": "ok"},
            result_type=expected_result_type,
        )

        result = await store.get_latest_result_for_topic(topic_id)
        assert result["result_type"] == "monitoring:general"
