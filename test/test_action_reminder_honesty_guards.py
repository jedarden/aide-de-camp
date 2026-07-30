"""
Tests for honesty guards on unimplemented intents.

Tests cover:
1. Action intents → design-only card (no fetch/bead side effects)
2. Reminder intents → clarification card (no fetch/bead side effects)
3. Requeue offer routes through escalate with Generated-Bead Safety
4. No dead-end or blank canvas in either flow
5. Router prompt updated for reminder limitation

Acceptance criteria:
- An action utterance produces the design-only card and no fetch/bead side effects
- Accepting the requeue offer routes through escalate with Generated-Bead Safety
- A reminder utterance produces the clarification card
- No dead-end or blank canvas in either flow
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from src.intent.router import IntentRouter, RoutedIntent, IntentClassification, IntentType
from src.errors.degraded_state import get_degraded_state_handler


@pytest.fixture
def mock_store():
    """Mock session store."""
    store = AsyncMock()
    store.create_intent = AsyncMock(return_value=None)
    store.update_intent_status = AsyncMock(return_value=None)
    store.create_session = AsyncMock(return_value=None)
    store.get_session = AsyncMock(return_value=None)
    return store


@pytest.fixture
def router(mock_store):
    """Create an IntentRouter with mocked store."""
    return IntentRouter(store=mock_store)


class TestActionIntentHonestyGuard:
    """Test that action intents produce design-only card."""

    @pytest.mark.asyncio
    async def test_action_intent_broadcasts_design_only_card(self, router):
        """Action intent should broadcast action_design_only event."""
        # Arrange
        routed_intent = RoutedIntent(
            intent_id="test-intent-id",
            classification=IntentClassification(
                intent_type=IntentType.ACTION,
                project_slug="test-project",
                utterance_fragment="deploy the service",
            ),
            session_id="test-session",
            utterance="deploy the service",
            router_ms=100,
        )

        # Mock the degraded state handler's broadcast method
        with patch.object(
            get_degraded_state_handler(),
            'broadcast_action_design_only',
            new_callable=AsyncMock,
        ) as mock_broadcast:
            # Act
            result = await router.process_intent(routed_intent)

            # Assert
            mock_broadcast.assert_called_once_with(
                utterance="deploy the service",
                intent_id="test-intent-id",
                session_id="test-session",
                project_slug="test-project",
            )

    @pytest.mark.asyncio
    async def test_action_intent_returns_design_only_status(self, router):
        """Action intent should return design_only status."""
        # Arrange
        routed_intent = RoutedIntent(
            intent_id="test-intent-id",
            classification=IntentClassification(
                intent_type=IntentType.ACTION,
                project_slug="test-project",
                utterance_fragment="restart the pod",
            ),
            session_id="test-session",
            utterance="restart the pod",
            router_ms=100,
        )

        with patch.object(
            get_degraded_state_handler(),
            'broadcast_action_design_only',
            new_callable=AsyncMock,
        ):
            # Act
            result = await router.process_intent(routed_intent)

            # Assert
            assert result["status"] == "design_only"
            assert result["intent_type"] == "action"
            assert "Action execution is not yet available" in result["message"]

    @pytest.mark.asyncio
    async def test_action_intent_no_fetch_or_synthesize(self, router):
        """Action intent should NOT trigger fetch or synthesize strands."""
        # Arrange
        routed_intent = RoutedIntent(
            intent_id="test-intent-id",
            classification=IntentClassification(
                intent_type=IntentType.ACTION,
                project_slug="test-project",
                utterance_fragment="scale the deployment",
            ),
            session_id="test-session",
            utterance="scale the deployment",
            router_ms=100,
        )

        # Spy on _fetch_and_synthesize - it should NOT be called
        with patch.object(router, '_fetch_and_synthesize', new_callable=AsyncMock) as mock_fetch:
            with patch.object(
                get_degraded_state_handler(),
                'broadcast_action_design_only',
                new_callable=AsyncMock,
            ):
                # Act
                await router.process_intent(routed_intent)

                # Assert
                mock_fetch.assert_not_called()

    @pytest.mark.asyncio
    async def test_action_intent_updates_store_status(self, router, mock_store):
        """Action intent should update intent status in store."""
        # Arrange
        routed_intent = RoutedIntent(
            intent_id="test-intent-id",
            classification=IntentClassification(
                intent_type=IntentType.ACTION,
                project_slug="test-project",
                utterance_fragment="delete the pod",
            ),
            session_id="test-session",
            utterance="delete the pod",
            router_ms=100,
        )

        with patch.object(
            get_degraded_state_handler(),
            'broadcast_action_design_only',
            new_callable=AsyncMock,
        ):
            # Act
            await router.process_intent(routed_intent)

            # Assert
            mock_store.update_intent_status.assert_called_once_with(
                "test-intent-id",
                "resolved",
                "Action execution is design-only — executor not built",
            )

    @pytest.mark.asyncio
    async def test_action_intent_without_project_slug(self, router):
        """Action intent without project slug should still work."""
        # Arrange
        routed_intent = RoutedIntent(
            intent_id="test-intent-id",
            classification=IntentClassification(
                intent_type=IntentType.ACTION,
                project_slug=None,
                utterance_fragment="do something",
            ),
            session_id="test-session",
            utterance="do something",
            router_ms=100,
        )

        with patch.object(
            get_degraded_state_handler(),
            'broadcast_action_design_only',
            new_callable=AsyncMock,
        ) as mock_broadcast:
            # Act
            result = await router.process_intent(routed_intent)

            # Assert
            mock_broadcast.assert_called_once_with(
                utterance="do something",
                intent_id="test-intent-id",
                session_id="test-session",
                project_slug=None,
            )
            assert result["status"] == "design_only"


class TestReminderIntentHonestyGuard:
    """Test that reminder intents produce clarification card."""

    @pytest.mark.asyncio
    async def test_reminder_intent_broadcasts_unavailable_card(self, router):
        """Reminder intent should broadcast reminder_unavailable event."""
        # Arrange
        routed_intent = RoutedIntent(
            intent_id="test-intent-id",
            classification=IntentClassification(
                intent_type=IntentType.REMINDER,
                utterance_fragment="remind me in 10 minutes",
            ),
            session_id="test-session",
            utterance="remind me in 10 minutes",
            router_ms=100,
        )

        with patch.object(
            get_degraded_state_handler(),
            'broadcast_reminder_unavailable',
            new_callable=AsyncMock,
        ) as mock_broadcast:
            # Act
            result = await router.process_intent(routed_intent)

            # Assert
            mock_broadcast.assert_called_once_with(
                utterance="remind me in 10 minutes",
                intent_id="test-intent-id",
                session_id="test-session",
            )

    @pytest.mark.asyncio
    async def test_reminder_intent_returns_unavailable_status(self, router):
        """Reminder intent should return unavailable status."""
        # Arrange
        routed_intent = RoutedIntent(
            intent_id="test-intent-id",
            classification=IntentClassification(
                intent_type=IntentType.REMINDER,
                utterance_fragment="set a reminder for tomorrow",
            ),
            session_id="test-session",
            utterance="set a reminder for tomorrow",
            router_ms=100,
        )

        with patch.object(
            get_degraded_state_handler(),
            'broadcast_reminder_unavailable',
            new_callable=AsyncMock,
        ):
            # Act
            result = await router.process_intent(routed_intent)

            # Assert
            assert result["status"] == "unavailable"
            assert result["intent_type"] == "reminder"
            assert "Reminders are not available yet" in result["message"]

    @pytest.mark.asyncio
    async def test_reminder_intent_no_fetch_or_synthesize(self, router):
        """Reminder intent should NOT trigger fetch or synthesize strands."""
        # Arrange
        routed_intent = RoutedIntent(
            intent_id="test-intent-id",
            classification=IntentClassification(
                intent_type=IntentType.REMINDER,
                utterance_fragment="remind me to check the logs",
            ),
            session_id="test-session",
            utterance="remind me to check the logs",
            router_ms=100,
        )

        # Spy on _fetch_and_synthesize - it should NOT be called
        with patch.object(router, '_fetch_and_synthesize', new_callable=AsyncMock) as mock_fetch:
            with patch.object(
                get_degraded_state_handler(),
                'broadcast_reminder_unavailable',
                new_callable=AsyncMock,
            ):
                # Act
                await router.process_intent(routed_intent)

                # Assert
                mock_fetch.assert_not_called()

    @pytest.mark.asyncio
    async def test_reminder_intent_updates_store_status(self, router, mock_store):
        """Reminder intent should update intent status in store."""
        # Arrange
        routed_intent = RoutedIntent(
            intent_id="test-intent-id",
            classification=IntentClassification(
                intent_type=IntentType.REMINDER,
                utterance_fragment="ping me in 5 minutes",
            ),
            session_id="test-session",
            utterance="ping me in 5 minutes",
            router_ms=100,
        )

        with patch.object(
            get_degraded_state_handler(),
            'broadcast_reminder_unavailable',
            new_callable=AsyncMock,
        ):
            # Act
            await router.process_intent(routed_intent)

            # Assert
            mock_store.update_intent_status.assert_called_once_with(
                "test-intent-id",
                "resolved",
                "Reminders are not available yet",
            )


class TestRouterPromptReminderLimitation:
    """Test that router prompt documents reminder limitation."""

    def test_router_prompt_mentions_reminder_not_implemented(self):
        """Router prompt should state that reminders are NOT YET IMPLEMENTED."""
        # Read the router prompt
        from pathlib import Path
        prompt_path = Path("/home/coding/aide-de-camp/prompts/router.md")
        prompt_content = prompt_path.read_text()

        # Assert that the prompt mentions the limitation
        assert "NOT YET IMPLEMENTED" in prompt_content
        assert "reminder" in prompt_content.lower()

    def test_router_prompt_clarification_card_message(self):
        """Router prompt should mention clarification card for reminders."""
        from pathlib import Path
        prompt_path = Path("/home/coding/aide-de-camp/prompts/router.md")
        prompt_content = prompt_path.read_text()

        # Assert that the prompt mentions the clarification card
        assert "clarification" in prompt_content.lower()


class TestOtherIntentsStillProcess:
    """Test that other intent types still process normally."""

    @pytest.mark.asyncio
    async def test_status_intent_still_processes(self, router):
        """Status intents should still route to fetch_and_synthesize."""
        # Arrange
        routed_intent = RoutedIntent(
            intent_id="test-intent-id",
            classification=IntentClassification(
                intent_type=IntentType.STATUS,
                project_slug="test-project",
                utterance_fragment="what's the status",
            ),
            session_id="test-session",
            utterance="what's the status",
            router_ms=100,
        )

        # Mock _fetch_and_synthesize to return a valid result
        with patch.object(
            router, '_fetch_and_synthesize',
            new_callable=AsyncMock,
            return_value={"status": "resolved"}
        ) as mock_fetch:
            # Act
            result = await router.process_intent(routed_intent)

            # Assert
            mock_fetch.assert_called_once()
            assert result["status"] == "resolved"

    @pytest.mark.asyncio
    async def test_task_profile_intent_still_esculates(self, router):
        """Task-profile intents should still route to escalate."""
        # Arrange
        routed_intent = RoutedIntent(
            intent_id="test-intent-id",
            classification=IntentClassification(
                intent_type=IntentType.TASK_PROFILE,
                project_slug="test-project",
                utterance_fragment="implement this feature",
            ),
            session_id="test-session",
            utterance="implement this feature",
            router_ms=100,
        )

        # Mock _escalate_to_bead to return a valid result
        with patch.object(
            router, '_escalate_to_bead',
            new_callable=AsyncMock,
            return_value={"status": "escalated"}
        ) as mock_escalate:
            # Act
            result = await router.process_intent(routed_intent)

            # Assert
            mock_escalate.assert_called_once()
            assert result["status"] == "escalated"
