"""Test that state updates happen before logging in Telegram fallback."""

from datetime import datetime
from unittest.mock import MagicMock, patch
import pytest
import httpx

from src.telegram.fallback import TelegramFallback


class TestStateUpdateBeforeLogging:
    """Verify that state updates occur BEFORE logging in failure paths."""

    @pytest.mark.asyncio
    async def test_state_update_before_logging_on_http_failure(self):
        """Test that state is updated before logging when HTTP response is non-200."""
        fallback = TelegramFallback(bot_token="test_token")

        # Mock the HTTP client to return a 500 error
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"

        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value.__aenter__.return_value.post.return_value = mock_response
            mock_client_class.return_value.__aenter__.return_value.get.return_value = mock_response

            # Spy on the state tracker to capture call order
            original_mark_unreachable = fallback._state_tracker.mark_as_unreachable
            call_order = []

            def spy_mark_unreachable(timestamp):
                call_order.append('state_update')
                return original_mark_unreachable(timestamp)

            fallback._state_tracker.mark_as_unreachable = spy_mark_unreachable

            # Spy on logger to capture when logging happens
            with patch('src.telegram.fallback.logger') as mock_logger:
                def spy_warning(*args, **kwargs):
                    call_order.append('logging')

                mock_logger.warning.side_effect = spy_warning

                # Attempt to send a message
                await fallback.send_message(chat_id=123, message="test")

                # Verify state update happened BEFORE logging
                assert call_order == ['state_update', 'logging'], \
                    f"State update must happen before logging, got order: {call_order}"

                # Verify state was actually updated
                assert not fallback._state_tracker.is_reachable
                assert fallback._state_tracker.failure_count > 0

    @pytest.mark.asyncio
    async def test_state_update_before_logging_on_request_error(self):
        """Test that state is updated before logging when a RequestError occurs."""
        fallback = TelegramFallback(bot_token="test_token")

        # Mock the HTTP client to raise a RequestError
        mock_error = httpx.RequestError("Connection failed", request=MagicMock())

        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value.__aenter__.return_value.post.side_effect = mock_error
            mock_client_class.return_value.__aenter__.return_value.get.side_effect = mock_error

            # Spy on the state tracker to capture call order
            original_mark_unreachable = fallback._state_tracker.mark_as_unreachable
            call_order = []

            def spy_mark_unreachable(timestamp):
                call_order.append('state_update')
                return original_mark_unreachable(timestamp)

            fallback._state_tracker.mark_as_unreachable = spy_mark_unreachable

            # Spy on logger to capture when logging happens
            with patch('src.telegram.fallback.logger') as mock_logger:
                def spy_warning(*args, **kwargs):
                    call_order.append('logging')

                mock_logger.warning.side_effect = spy_warning

                # Attempt to send a message
                await fallback.send_message(chat_id=123, message="test")

                # Verify state update happened BEFORE logging
                assert call_order == ['state_update', 'logging'], \
                    f"State update must happen before logging, got order: {call_order}"

                # Verify state was actually updated
                assert not fallback._state_tracker.is_reachable
                assert fallback._state_tracker.failure_count > 0

    @pytest.mark.asyncio
    async def test_state_update_preserves_timestamp_on_failure(self):
        """Test that state update preserves the failure timestamp."""
        fallback = TelegramFallback(bot_token="test_token")

        # Mock the HTTP client to return a 500 error
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"

        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value.__aenter__.return_value.post.return_value = mock_response

            # Capture time before and after failure
            before_time = datetime.now()

            await fallback.send_message(chat_id=123, message="test")

            after_time = datetime.now()

            # Verify state tracker recorded a failure timestamp
            assert fallback._state_tracker.last_failure_time is not None
            assert before_time <= fallback._state_tracker.last_failure_time <= after_time

    @pytest.mark.asyncio
    async def test_state_update_increments_failure_count(self):
        """Test that state update increments failure count on each failure."""
        fallback = TelegramFallback(bot_token="test_token")

        # Mock the HTTP client to return errors
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"

        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value.__aenter__.return_value.post.return_value = mock_response

            # Initial state
            assert fallback._state_tracker.failure_count == 0

            # First failure
            await fallback.send_message(chat_id=123, message="test1")
            assert fallback._state_tracker.failure_count == 1

            # Second failure
            await fallback.send_message(chat_id=123, message="test2")
            assert fallback._state_tracker.failure_count == 2

            # Third failure
            await fallback.send_message(chat_id=123, message="test3")
            assert fallback._state_tracker.failure_count == 3


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
