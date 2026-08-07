"""
Test suite for canvas data injection utilities.

Verifies that the test utilities can create sessions, inject test data,
and clean up properly without affecting the production database.
"""
import asyncio
import pytest
import tempfile
from pathlib import Path

from src.test.utilities import (
    TestSessionClient,
    TestDataBuilder,
    TestDatabaseIsolation,
    TestFixture,
    create_test_session,
    dispatch_test_utterance,
    create_synthetic_test_result,
)


class TestSessionClientBasics:
    """Test basic TestSessionClient functionality."""

    @pytest.mark.asyncio
    async def test_create_session(self):
        """Test creating a test session via API."""
        async with TestSessionClient() as client:
            session_data = await client.create_session()

            assert "session_id" in session_data
            assert "surface_id" in session_data
            assert len(session_data["session_id"]) > 0
            # surface_id might not be present if registration fails, so we check
            if session_data.get("surface_id"):
                assert len(session_data["surface_id"]) > 0

    @pytest.mark.asyncio
    async def test_create_session_with_custom_id(self):
        """Test creating a session with a custom ID."""
        custom_id = "test-session-custom-123"
        async with TestSessionClient() as client:
            session_data = await client.create_session(session_id=custom_id)

            assert session_data["session_id"] == custom_id

    @pytest.mark.asyncio
    async def test_create_multiple_sessions(self):
        """Test creating multiple test sessions."""
        async with TestSessionClient() as client:
            session1 = await client.create_session()
            session2 = await client.create_session()

            assert session1["session_id"] != session2["session_id"]


class TestUtteranceDispatch:
    """Test utterance dispatch functionality."""

    @pytest.mark.asyncio
    async def test_dispatch_simple_utterance(self):
        """Test dispatching a simple test utterance."""
        async with TestSessionClient() as client:
            session_data = await client.create_session()

            response = await client.dispatch_utterance(
                utterance="test status check",
                session_id=session_data["session_id"],
            )

            assert "utterance_id" in response
            assert "session_id" in response
            assert "intent_count" in response
            assert response["session_id"] == session_data["session_id"]

    @pytest.mark.asyncio
    async def test_dispatch_with_surface_id(self):
        """Test dispatching with surface ID for SSE broadcast."""
        async with TestSessionClient() as client:
            session_data = await client.create_session()

            response = await client.dispatch_utterance(
                utterance="test with surface",
                session_id=session_data["session_id"],
                surface_id=session_data["surface_id"],
            )

            assert response["intent_count"] >= 0

    @pytest.mark.asyncio
    async def test_dispatch_multiple_utterances(self):
        """Test dispatching multiple utterances to the same session."""
        async with TestSessionClient() as client:
            session_data = await client.create_session()

            utterance1 = "check the system status"
            utterance2 = "find recent logs"

            response1 = await client.dispatch_utterance(
                utterance=utterance1,
                session_id=session_data["session_id"],
                surface_id=session_data["surface_id"],
            )

            response2 = await client.dispatch_utterance(
                utterance=utterance2,
                session_id=session_data["session_id"],
                surface_id=session_data["surface_id"],
            )

            assert response1["utterance_id"] != response2["utterance_id"]


class TestSyntheticResults:
    """Test synthetic result creation functionality."""

    @pytest.mark.asyncio
    async def test_create_basic_synthetic_result(self):
        """Test creating a basic synthetic result."""
        async with TestSessionClient() as client:
            session_data = await client.create_session()

            result = await client.create_synthetic_result(
                session_id=session_data["session_id"],
            )

            assert "utterance_id" in result
            assert "intent_id" in result
            assert "topic_id" in result
            assert "result_id" in result
            assert result["status"] == "resolved"

    @pytest.mark.asyncio
    async def test_create_synthetic_result_with_custom_data(self):
        """Test creating a synthetic result with custom test data."""
        async with TestSessionClient() as client:
            session_data = await client.create_session()

            test_data = {
                "utterance": "custom test utterance",
                "project_slug": "test-project",
                "intent_type": "status",
                "topic_label": "Custom Test Topic",
                "topic_type": "research",
                "summary": "Custom summary",
                "data": {"key": "value"},
                "urgency": "high",
                "result_type": "status",
            }

            result = await client.create_synthetic_result(
                session_id=session_data["session_id"],
                test_data=test_data,
            )

            assert result["summary"] == "Custom summary"
            assert result["urgency"] == "high"

    @pytest.mark.asyncio
    async def test_create_multiple_synthetic_results(self):
        """Test creating multiple synthetic results in a session."""
        async with TestSessionClient() as client:
            session_data = await client.create_session()

            result1 = await client.create_synthetic_result(
                session_id=session_data["session_id"],
                surface_id=session_data["surface_id"],
                test_data={"topic_label": "Topic 1"},
            )

            result2 = await client.create_synthetic_result(
                session_id=session_data["session_id"],
                surface_id=session_data["surface_id"],
                test_data={"topic_label": "Topic 2"},
            )

            assert result1["result_id"] != result2["result_id"]
            assert result1["topic_id"] != result2["topic_id"]


class TestTopicsRetrieval:
    """Test topics retrieval functionality."""

    @pytest.mark.asyncio
    async def test_get_empty_session_topics(self):
        """Test getting topics from an empty session."""
        async with TestSessionClient() as client:
            session_data = await client.create_session()

            topics = await client.get_session_topics(session_data["session_id"])

            assert "cards" in topics
            # Should be empty or very few topics for a new session
            assert isinstance(topics["cards"], list)

    @pytest.mark.asyncio
    async def test_get_topics_after_synthetic_result(self):
        """Test getting topics after creating a synthetic result."""
        async with TestSessionClient() as client:
            session_data = await client.create_session()

            await client.create_synthetic_result(
                session_id=session_data["session_id"],
                surface_id=session_data["surface_id"],
            )

            topics = await client.get_session_topics(session_data["session_id"])

            assert "cards" in topics
            # Should have at least one topic now
            assert len(topics["cards"]) >= 1


class TestCleanup:
    """Test cleanup functionality."""

    @pytest.mark.asyncio
    async def test_cleanup_single_session(self):
        """Test cleaning up a single session."""
        async with TestSessionClient() as client:
            session_data = await client.create_session()

            # Create some test data
            await client.create_synthetic_result(
                session_id=session_data["session_id"],
            )

            # Clean up
            success = await client.cleanup_session(session_data["session_id"])
            assert success is True

    @pytest.mark.asyncio
    async def test_automatic_cleanup_on_exit(self):
        """Test automatic cleanup when exiting context manager."""
        async with TestSessionClient() as client:
            session_data = await client.create_session()
            session_id = session_data["session_id"]

            # Create test data
            await client.create_synthetic_result(
                session_id=session_id,
            )

        # After exiting context, cleanup should have run automatically
        # (Verification would require checking the database state)


class TestDataBuilders:
    """Test TestDataBuilder functionality."""

    def test_build_test_utterance(self):
        """Test building a test utterance."""
        builder = TestDataBuilder()
        utterance = builder.build_test_utterance(
            text="test utterance",
            intent_type="status",
        )

        assert utterance == "test utterance"

    def test_build_test_utterance_empty_validation(self):
        """Test that empty utterances are rejected."""
        builder = TestDataBuilder()
        with pytest.raises(ValueError):
            builder.build_test_utterance(text="")

    def test_build_synthetic_data(self):
        """Test building synthetic test data."""
        builder = TestDataBuilder()
        data = builder.build_synthetic_data(
            utterance="test",
            project_slug="test-project",
            intent_type="status",
        )

        assert data["utterance"] == "test"
        assert data["project_slug"] == "test-project"
        assert data["intent_type"] == "status"
        assert data["test_mode"] is True
        assert data["synthetic"] is True

    def test_build_multi_intent_scenario(self):
        """Test building multi-intent scenarios."""
        builder = TestDataBuilder()
        scenarios = builder.build_multi_intent_scenario()

        assert len(scenarios) > 0
        assert "utterance" in scenarios[0]
        assert "expected_intent_count" in scenarios[0]


class TestDatabaseIsolations:
    """Test database isolation utilities."""

    def test_create_temp_db_path(self):
        """Test creating a temporary database path."""
        isolation = TestDatabaseIsolation()
        temp_path = isolation.create_temp_db_path()

        assert isinstance(temp_path, Path)
        assert temp_path.parent.exists()
        assert temp_path.suffix == ".db"

    def test_create_in_memory_db_string(self):
        """Test creating an in-memory database connection string."""
        isolation = TestDatabaseIsolation()
        conn_str = isolation.create_in_memory_db_connection_string()

        assert conn_str == ":memory:"


class TestTestFixture:
    """Test the comprehensive TestFixture."""

    @pytest.mark.asyncio
    async def test_fixture_basic_usage(self):
        """Test basic TestFixture usage."""
        async with TestFixture() as fixture:
            assert fixture.session_id is not None
            assert fixture.surface_id is not None

    @pytest.mark.asyncio
    async def test_fixture_dispatch(self):
        """Test dispatching through the fixture."""
        async with TestFixture() as fixture:
            response = await fixture.dispatch("test utterance")

            assert "utterance_id" in response
            assert "intent_count" in response

    @pytest.mark.asyncio
    async def test_fixture_create_synthetic(self):
        """Test creating synthetic result through the fixture."""
        async with TestFixture() as fixture:
            result = await fixture.create_synthetic()

            assert "result_id" in result
            assert result["status"] == "resolved"

    @pytest.mark.asyncio
    async def test_fixture_get_topics(self):
        """Test getting topics through the fixture."""
        async with TestFixture() as fixture:
            # Create some test data
            await fixture.create_synthetic()

            topics = await fixture.get_topics()

            assert "cards" in topics


class TestConvenienceFunctions:
    """Test convenience functions."""

    @pytest.mark.asyncio
    async def test_create_test_session_function(self):
        """Test the convenience function for creating sessions."""
        session_data = await create_test_session()

        assert "session_id" in session_data
        assert "surface_id" in session_data

    @pytest.mark.asyncio
    async def test_dispatch_test_utterance_function(self):
        """Test the convenience function for dispatching."""
        session_data = await create_test_session()

        response = await dispatch_test_utterance(
            utterance="test",
            session_id=session_data["session_id"],
        )

        assert "utterance_id" in response

    @pytest.mark.asyncio
    async def test_create_synthetic_test_result_function(self):
        """Test the convenience function for synthetic results."""
        session_data = await create_test_session()

        result = await create_synthetic_test_result(
            session_id=session_data["session_id"],
        )

        assert "result_id" in result


class TestMultiTopicInjection:
    """Test injecting multiple topics into a session."""

    @pytest.mark.asyncio
    async def test_inject_multiple_topics(self):
        """Test creating a session with multiple topics."""
        async with TestFixture() as fixture:
            # Create multiple synthetic results (topics)
            topic1_data = {
                "topic_label": "First Topic",
                "summary": "First test result",
            }

            topic2_data = {
                "topic_label": "Second Topic",
                "summary": "Second test result",
            }

            topic3_data = {
                "topic_label": "Third Topic",
                "summary": "Third test result",
            }

            await fixture.create_synthetic(topic1_data)
            await fixture.create_synthetic(topic2_data)
            await fixture.create_synthetic(topic3_data)

            # Get all topics
            topics = await fixture.get_topics()

            # Verify we have multiple topics
            assert len(topics["cards"]) >= 3

    @pytest.mark.asyncio
    async def test_inject_different_topic_types(self):
        """Test creating topics of different types."""
        async with TestFixture() as fixture:
            # Create different types of topics
            research_topic = {
                "topic_type": "research",
                "topic_label": "Research Topic",
            }

            project_topic = {
                "topic_type": "project",
                "topic_label": "Project Topic",
            }

            personal_topic = {
                "topic_type": "personal",
                "topic_label": "Personal Topic",
            }

            await fixture.create_synthetic(research_topic)
            await fixture.create_synthetic(project_topic)
            await fixture.create_synthetic(personal_topic)

            topics = await fixture.get_topics()

            # Verify we have different topic types
            topic_types = {card.get("type") for card in topics["cards"]}
            assert len(topic_types) >= 2  # At least 2 different types


class TestIsolationFromProduction:
    """Test that test data doesn't affect production database."""

    @pytest.mark.asyncio
    async def test_test_data_isolation(self):
        """Test that test data is isolated from production."""
        # This test verifies that using a different test_db_path
        # would keep test data separate from production

        isolation = TestDatabaseIsolation()
        temp_path = isolation.create_temp_db_path()

        # The temp path should be different from production
        from src.session.store import DEFAULT_DB_PATH

        assert temp_path != DEFAULT_DB_PATH

        # Clean up temp path
        if temp_path.parent.exists():
            import shutil
            shutil.rmtree(temp_path.parent, ignore_errors=True)


# Integration tests that verify the full flow
class TestFullInjectionFlow:
    """Integration tests for the complete injection flow."""

    @pytest.mark.asyncio
    async def test_complete_canvas_test_flow(self):
        """Test the complete flow for canvas testing."""
        async with TestFixture() as fixture:
            # Simulate canvas testing scenario:
            # 1. Canvas connects (session created by fixture)
            # 2. User sends utterance
            response = await fixture.dispatch(
                "check the system status",
            )

            # 3. Verify dispatch succeeded
            assert response["intent_count"] >= 1

            # 4. Canvas polls for topics
            topics = await fixture.get_topics()

            # 5. Verify topics are available
            assert "cards" in topics

            # 6. Clean up happens automatically on exit
            # (verified by no errors on exit)

    @pytest.mark.asyncio
    async def test_multi_user_scenario(self):
        """Test simulating multiple users with separate sessions."""
        async with TestFixture() as fixture1:
            async with TestFixture() as fixture2:
                # Create different data in each session
                await fixture1.create_synthetic({"topic_label": "User1 Topic"})
                await fixture2.create_synthetic({"topic_label": "User2 Topic"})

                # Verify sessions are independent
                topics1 = await fixture1.get_topics()
                topics2 = await fixture2.get_topics()

                assert fixture1.session_id != fixture2.session_id


if __name__ == "__main__":
    # Run the tests
    pytest.main([__file__, "-v", "-s"])
